import time
import uuid
from collections.abc import Iterator
from typing import Any
from unittest.mock import MagicMock

import jwt
import pytest
from fastapi.testclient import TestClient
from pytest_httpx import HTTPXMock
from sqlmodel import Session

from app.core.settings import (
    JWT_AUDIENCE,
    JWT_ISSUER,
    OAUTH_STATE_COOKIE_NAME,
    Settings,
    get_settings,
)
from app.main import app
from app.models.user import User
from app.services import auth_service as auth_service_module
from app.services.auth_service import AuthService
from tests.conftest import make_settings

# `test_settings` fixture は conftest で提供。本ファイルでは
# `allowed_spotify_user_id` を固定して使う必要があるので上書きする。
ALLOWED_USER = "owner-spotify-id"
COOKIE_NAME = "jl_session"  # Settings.cookie_name のデフォルトと一致


@pytest.fixture
def test_settings() -> Settings:  # type: ignore[no-redef]
    return make_settings(allowed_spotify_user_id=ALLOWED_USER)


@pytest.fixture
def auth_client(session: Session, test_settings: Settings) -> Iterator[TestClient]:
    """TestClient configured with overridden settings + DB session.

    Records / artists の dependency 上書きと同じパターンで get_settings を差し替える。
    """
    from app.core.db import get_session

    def _override_session() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_settings] = lambda: test_settings
    auth_service_module._state_store.clear()
    yield TestClient(app)
    app.dependency_overrides.clear()


def _spotify_token_response(refresh_token: str = "AQB-real-refresh-token") -> dict[str, Any]:
    return {
        "access_token": "BQA-access-token",
        "token_type": "Bearer",
        "expires_in": 3600,
        "refresh_token": refresh_token,
        "scope": "user-read-private user-read-email user-follow-read",
    }


def _spotify_me_response(spotify_id: str = ALLOWED_USER) -> dict[str, Any]:
    return {
        "id": spotify_id,
        "display_name": "Owner",
        "images": [{"url": "https://example.test/owner.jpg"}],
    }


def _login_and_capture_state(client: TestClient) -> tuple[str, str]:
    """Hit /login and return (state in URL, oauth_state cookie value)."""
    res = client.get("/api/auth/login", follow_redirects=False)
    assert res.status_code == 302
    location = res.headers["location"]
    state = location.split("state=")[-1]
    cookie_state = res.cookies[OAUTH_STATE_COOKIE_NAME]
    return state, cookie_state


# ---- /login ----


def test_login_redirects_to_spotify_with_state_cookie(auth_client: TestClient) -> None:
    res = auth_client.get("/api/auth/login", follow_redirects=False)
    assert res.status_code == 302
    location = res.headers["location"]
    assert location.startswith("https://accounts.spotify.com/authorize?")
    assert "state=" in location
    assert "scope=user-read-private+user-read-email+user-follow-read" in location
    assert OAUTH_STATE_COOKIE_NAME in res.cookies


# ---- /callback happy path ----


def test_callback_happy_path_sets_session_and_persists_user(
    auth_client: TestClient,
    httpx_mock: HTTPXMock,
    session: Session,
    test_settings: Settings,
) -> None:
    state, cookie_state = _login_and_capture_state(auth_client)

    httpx_mock.add_response(
        method="POST",
        url="https://accounts.spotify.com/api/token",
        json=_spotify_token_response(),
    )
    httpx_mock.add_response(
        method="GET",
        url="https://api.spotify.com/v1/me",
        json=_spotify_me_response(),
    )

    auth_client.cookies.set(OAUTH_STATE_COOKIE_NAME, cookie_state)
    res = auth_client.get(
        "/api/auth/callback",
        params={"code": "spotify-code", "state": state},
        follow_redirects=False,
    )

    assert res.status_code == 302
    assert res.headers["location"] == test_settings.frontend_base_url
    assert COOKIE_NAME in res.cookies

    rows = list(session.exec(_select_users()))
    assert len(rows) == 1
    user = rows[0]
    assert user.spotify_id == ALLOWED_USER
    assert user.display_name == "Owner"
    # refresh_token は Fernet 暗号化済みのため、平文と異なるはず
    assert user.refresh_token != "AQB-real-refresh-token"
    assert len(user.refresh_token) > len("AQB-real-refresh-token")


def test_callback_disallowed_user_returns_403(
    auth_client: TestClient,
    httpx_mock: HTTPXMock,
) -> None:
    state, cookie_state = _login_and_capture_state(auth_client)

    httpx_mock.add_response(
        method="POST",
        url="https://accounts.spotify.com/api/token",
        json=_spotify_token_response(),
    )
    httpx_mock.add_response(
        method="GET",
        url="https://api.spotify.com/v1/me",
        json=_spotify_me_response(spotify_id="intruder"),
    )

    auth_client.cookies.set(OAUTH_STATE_COOKIE_NAME, cookie_state)
    res = auth_client.get(
        "/api/auth/callback",
        params={"code": "spotify-code", "state": state},
        follow_redirects=False,
    )
    assert res.status_code == 403


def test_callback_state_cookie_mismatch_returns_400(
    auth_client: TestClient,
) -> None:
    state, _ = _login_and_capture_state(auth_client)
    auth_client.cookies.set(OAUTH_STATE_COOKIE_NAME, "tampered-cookie-state")
    res = auth_client.get(
        "/api/auth/callback",
        params={"code": "spotify-code", "state": state},
        follow_redirects=False,
    )
    assert res.status_code == 400


def test_callback_state_cookie_missing_returns_400(
    auth_client: TestClient,
) -> None:
    state, _ = _login_and_capture_state(auth_client)
    auth_client.cookies.clear()
    res = auth_client.get(
        "/api/auth/callback",
        params={"code": "spotify-code", "state": state},
        follow_redirects=False,
    )
    assert res.status_code == 400


def test_callback_unknown_state_returns_400(auth_client: TestClient) -> None:
    auth_client.cookies.set(OAUTH_STATE_COOKIE_NAME, "abc")
    res = auth_client.get(
        "/api/auth/callback",
        params={"code": "spotify-code", "state": "abc"},
        follow_redirects=False,
    )
    assert res.status_code == 400


def test_callback_with_error_param_returns_400(auth_client: TestClient) -> None:
    res = auth_client.get(
        "/api/auth/callback",
        params={"error": "access_denied"},
        follow_redirects=False,
    )
    assert res.status_code == 400


def test_callback_double_consume_of_state_returns_400(
    auth_client: TestClient,
    httpx_mock: HTTPXMock,
) -> None:
    state, cookie_state = _login_and_capture_state(auth_client)

    # 1st use succeeds
    httpx_mock.add_response(
        method="POST",
        url="https://accounts.spotify.com/api/token",
        json=_spotify_token_response(),
    )
    httpx_mock.add_response(
        method="GET",
        url="https://api.spotify.com/v1/me",
        json=_spotify_me_response(),
    )
    auth_client.cookies.set(OAUTH_STATE_COOKIE_NAME, cookie_state)
    first = auth_client.get(
        "/api/auth/callback",
        params={"code": "spotify-code", "state": state},
        follow_redirects=False,
    )
    assert first.status_code == 302

    # 2nd use of same state fails
    auth_client.cookies.set(OAUTH_STATE_COOKIE_NAME, cookie_state)
    second = auth_client.get(
        "/api/auth/callback",
        params={"code": "spotify-code", "state": state},
        follow_redirects=False,
    )
    assert second.status_code == 400


# ---- /me ----


def test_me_without_cookie_returns_401(auth_client: TestClient) -> None:
    auth_client.cookies.clear()
    res = auth_client.get("/api/auth/me")
    assert res.status_code == 401


def test_me_with_alg_none_token_returns_401(
    auth_client: TestClient,
) -> None:
    crafted = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "exp": int(time.time()) + 600,
            "iat": int(time.time()),
            "type": "session",
            "iss": JWT_ISSUER,
            "aud": JWT_AUDIENCE,
        },
        "",
        algorithm="none",
    )
    auth_client.cookies.set(COOKIE_NAME, crafted)
    res = auth_client.get("/api/auth/me")
    assert res.status_code == 401


def test_me_with_valid_cookie_returns_user(
    auth_client: TestClient,
    session: Session,
    test_settings: Settings,
) -> None:
    user = User(
        spotify_id=ALLOWED_USER,
        display_name="Owner",
        image_url="https://example.test/owner.jpg",
        refresh_token="encrypted-placeholder",
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    svc = AuthService(
        user_repo=MagicMock(),
        spotify=MagicMock(),
        settings=test_settings,
    )
    token = svc._issue_session_token(user.id)
    auth_client.cookies.set(COOKIE_NAME, token)

    res = auth_client.get("/api/auth/me")
    assert res.status_code == 200
    body = res.json()
    assert body == {
        "spotify_id": ALLOWED_USER,
        "display_name": "Owner",
        "image_url": "https://example.test/owner.jpg",
    }


# ---- /logout ----


def test_logout_clears_cookie(auth_client: TestClient) -> None:
    auth_client.cookies.set(COOKIE_NAME, "anything")
    res = auth_client.post("/api/auth/logout")
    assert res.status_code == 204
    set_cookie_header = res.headers.get("set-cookie", "")
    assert COOKIE_NAME in set_cookie_header
    # delete_cookie が打たれたことを確認 (max-age=0 or expires が過去)
    assert "Max-Age=0" in set_cookie_header or "1970" in set_cookie_header


# ---- helpers ----


def _select_users():
    from sqlmodel import select

    return select(User)
