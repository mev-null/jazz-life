from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
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


@contextmanager
def session_scope() -> Iterator[Session]:
    """リクエストスコープ外 (バックグラウンドジョブ等) で使う session。

    `get_session` は FastAPI の generator dependency なので `with` で直接は
    使えない。こちらは普通の context manager として `with session_scope() as s:`
    で開ける。
    """
    with Session(get_engine()) as session:
        yield session


SessionFactory = Callable[[], AbstractContextManager[Session]]


def get_session_factory() -> SessionFactory:
    """「その都度新しい session を開けるファクトリ」を注入する dependency。

    バックグラウンドジョブはリクエスト終了後に走るため、リクエストスコープの
    session (`get_session`) は既に閉じている。代わりにこのファクトリを渡し、
    ジョブ内で `with factory() as session:` と専用 session を開く。テストでは
    この dependency を上書きしてテスト session を流し込める。
    """
    return session_scope
