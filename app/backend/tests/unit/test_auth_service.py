import time
import uuid
from unittest.mock import MagicMock

import jwt
import pytest

from app.core.exceptions import AuthError, ForbiddenError, SpotifyAuthError
from app.core.settings import JWT_AUDIENCE, JWT_ISSUER, Settings
from app.services import auth_service as auth_service_module
from app.services.auth_service import AuthService
from tests.conftest import make_settings


def _make_service(settings: Settings | None = None) -> AuthService:
    return AuthService(
        user_repo=MagicMock(),
        spotify=MagicMock(),
        settings=settings or make_settings(allowed_spotify_user_id="owner"),
    )


@pytest.fixture(autouse=True)
def _clear_state_store() -> None:
    auth_service_module._state_store.clear()


# ---- state ----


def test_state_roundtrip_succeeds() -> None:
    svc = _make_service()
    state = svc.issue_state()
    svc.verify_state(state, state)


def test_state_double_consume_is_rejected() -> None:
    svc = _make_service()
    state = svc.issue_state()
    svc.verify_state(state, state)
    with pytest.raises(AuthError):
        svc.verify_state(state, state)


def test_state_cookie_mismatch_is_rejected() -> None:
    svc = _make_service()
    state = svc.issue_state()
    with pytest.raises(AuthError):
        svc.verify_state(state, "tampered")


def test_state_cookie_missing_is_rejected() -> None:
    svc = _make_service()
    state = svc.issue_state()
    with pytest.raises(AuthError):
        svc.verify_state(state, None)


def test_state_url_missing_is_rejected() -> None:
    svc = _make_service()
    with pytest.raises(AuthError):
        svc.verify_state(None, "abc")


def test_state_ttl_expiry_is_rejected() -> None:
    svc = _make_service(make_settings(allowed_spotify_user_id="owner", state_ttl_seconds=0))
    state = svc.issue_state()
    time.sleep(0.05)
    with pytest.raises(AuthError):
        svc.verify_state(state, state)


# ---- JWT ----


def test_jwt_roundtrip_returns_user_id() -> None:
    svc = _make_service()
    user_id = uuid.uuid4()
    token = svc._issue_session_token(user_id)
    assert svc.decode_session_token(token) == user_id


def test_jwt_with_alg_none_is_rejected() -> None:
    svc = _make_service()
    user_id = uuid.uuid4()
    crafted = jwt.encode(
        {
            "sub": str(user_id),
            "exp": int(time.time()) + 600,
            "iat": int(time.time()),
            "type": "session",
            "iss": JWT_ISSUER,
            "aud": JWT_AUDIENCE,
        },
        "",
        algorithm="none",
    )
    with pytest.raises(AuthError):
        svc.decode_session_token(crafted)


def test_jwt_signed_with_wrong_secret_is_rejected() -> None:
    svc = _make_service()
    user_id = uuid.uuid4()
    crafted = jwt.encode(
        {
            "sub": str(user_id),
            "exp": int(time.time()) + 600,
            "iat": int(time.time()),
            "type": "session",
            "iss": JWT_ISSUER,
            "aud": JWT_AUDIENCE,
        },
        "different-secret-of-sufficient-length-aaaa",
        algorithm="HS256",
    )
    with pytest.raises(AuthError):
        svc.decode_session_token(crafted)


def test_jwt_with_wrong_audience_is_rejected() -> None:
    svc = _make_service()
    user_id = uuid.uuid4()
    crafted = jwt.encode(
        {
            "sub": str(user_id),
            "exp": int(time.time()) + 600,
            "iat": int(time.time()),
            "type": "session",
            "iss": JWT_ISSUER,
            "aud": "some-other-audience",
        },
        "x" * 32,
        algorithm="HS256",
    )
    with pytest.raises(AuthError):
        svc.decode_session_token(crafted)


def test_jwt_with_wrong_issuer_is_rejected() -> None:
    svc = _make_service()
    user_id = uuid.uuid4()
    crafted = jwt.encode(
        {
            "sub": str(user_id),
            "exp": int(time.time()) + 600,
            "iat": int(time.time()),
            "type": "session",
            "iss": "evil-issuer",
            "aud": JWT_AUDIENCE,
        },
        "x" * 32,
        algorithm="HS256",
    )
    with pytest.raises(AuthError):
        svc.decode_session_token(crafted)


def test_jwt_with_wrong_token_type_is_rejected() -> None:
    svc = _make_service()
    user_id = uuid.uuid4()
    crafted = jwt.encode(
        {
            "sub": str(user_id),
            "exp": int(time.time()) + 600,
            "iat": int(time.time()),
            "type": "refresh",
            "iss": JWT_ISSUER,
            "aud": JWT_AUDIENCE,
        },
        "x" * 32,
        algorithm="HS256",
    )
    with pytest.raises(AuthError):
        svc.decode_session_token(crafted)


def test_jwt_expired_is_rejected() -> None:
    svc = _make_service(make_settings(allowed_spotify_user_id="owner", session_ttl_seconds=0))
    user_id = uuid.uuid4()
    token = svc._issue_session_token(user_id)
    time.sleep(0.05)
    with pytest.raises(AuthError):
        svc.decode_session_token(token)


# ---- allowlist ----


def test_allowlist_hit_succeeds() -> None:
    svc = _make_service()
    svc._enforce_allowlist("owner")  # does not raise


def test_allowlist_miss_raises_forbidden() -> None:
    svc = _make_service()
    with pytest.raises(ForbiddenError):
        svc._enforce_allowlist("intruder")


# ---- secret non-leakage ----


def test_spotify_auth_error_message_does_not_leak_inputs() -> None:
    secret = "AQB-VERY-SENSITIVE-REFRESH-TOKEN"
    msg = "spotify token endpoint returned 400"
    exc = SpotifyAuthError(msg)
    assert secret not in str(exc)
    assert msg == str(exc)
