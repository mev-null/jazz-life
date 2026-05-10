import os
from collections.abc import Iterator

from sqlmodel import Session, create_engine

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql+psycopg://jazz:jazz@db:5432/jazz")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
