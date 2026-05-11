from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy.engine import Engine
from sqlmodel import Session, create_engine

from app.core.settings import get_settings


@lru_cache
def get_engine() -> Engine:
    """Lazy engine factory.

    Settings 経由で DATABASE_URL を読むため、import 時ではなく初回利用時に
    インスタンス化する。これにより Alembic / tests が独立に engine を作れる
    余地を残しつつ、本番経路では Settings の集約点を 1 つに保つ。
    """
    return create_engine(get_settings().database_url, pool_pre_ping=True)


def get_session() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session
