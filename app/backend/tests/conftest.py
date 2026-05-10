import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from app import models  # noqa: F401  register tables
from app.core.db import get_session
from app.core.repositories.artist_repository import ArtistRepository
from app.main import app
from app.seed import seed_artists_if_empty

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://jazz:jazz@localhost:5432/jazz_test",
)


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
