import os
from collections.abc import Iterator
from typing import Any

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from app import models  # noqa: F401  register tables
from app.core.db import get_session
from app.core.repositories.artist_repository import ArtistRepository
from app.core.settings import Settings
from app.main import app
from app.seed import seed_artists_if_empty

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://jazz:jazz@localhost:5432/jazz_test",
)


def make_settings_kwargs(**overrides: Any) -> dict[str, Any]:
    """テスト用 Settings のデフォルト kwargs を返す。

    値そのものは実 secret ではなくテスト専用プレースホルダ。env 依存にすると
    バッドケース (jwt_secret 31 文字等) の差し替えが煩雑になるため、ハードコード
    のままここに集約する。個別テストで上書きする時は overrides で渡す。
    """
    base: dict[str, Any] = {
        "database_url": TEST_DATABASE_URL,
        "spotify_client_id": "test-client-id",
        "spotify_client_secret": "test-client-secret",
        "spotify_redirect_uri": "http://localhost:8000/api/auth/callback",
        "jwt_secret": "x" * 32,
        "refresh_token_key": Fernet.generate_key().decode(),
    }
    base.update(overrides)
    return base


def make_settings(**overrides: Any) -> Settings:
    return Settings(**make_settings_kwargs(**overrides))


@pytest.fixture
def test_settings() -> Settings:
    return make_settings()


@pytest.fixture
def engine():
    eng = create_engine(TEST_DATABASE_URL)
    SQLModel.metadata.drop_all(eng)
    SQLModel.metadata.create_all(eng)
    yield eng
    SQLModel.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture
def session(engine) -> Iterator[Session]:
    with Session(engine) as s:
        yield s


@pytest.fixture
def seeded_session(session: Session) -> Session:
    seed_artists_if_empty(ArtistRepository(session))
    return session


def _client_with(session: Session) -> Iterator[TestClient]:
    def _override_get_session() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_session] = _override_get_session
    # Construct without `with` so the app's lifespan does NOT run; otherwise the
    # global engine would seed the dev DB during tests.
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def client(session: Session) -> Iterator[TestClient]:
    yield from _client_with(session)


@pytest.fixture
def seeded_client(seeded_session: Session) -> Iterator[TestClient]:
    yield from _client_with(seeded_session)
