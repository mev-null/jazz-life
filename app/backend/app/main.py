import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session

from app.core.db import get_engine
from app.core.repositories.artist_repository import ArtistRepository
from app.routers import artists, auth, records, releases, spotify, user_follows
from app.seed import seed_artists_if_empty

_DEFAULT_CORS_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]


def _resolve_cors_allow_origins() -> list[str]:
    """CORS_ALLOW_ORIGINS を env から CSV で受け取り list 化する。

    Settings 経由で読みたいところだが、CORSMiddleware は app 初期化時に登録する
    必要があり、Settings() を module-level で評価すると test (env 未設定) が
    起動できなくなる。CORS だけは Settings から切り離して env を直読みする。
    """
    raw = os.environ.get("CORS_ALLOW_ORIGINS")
    if not raw:
        return _DEFAULT_CORS_ORIGINS
    parsed = [s.strip() for s in raw.split(",") if s.strip()]
    return parsed or _DEFAULT_CORS_ORIGINS


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    with Session(get_engine()) as session:
        seed_artists_if_empty(ArtistRepository(session))
    yield


app = FastAPI(title="jazz-life", version="0.1.0", lifespan=lifespan)

# 許可 origin は `CORS_ALLOW_ORIGINS` (CSV) で env から渡す。
# 既定: ローカル開発の Vite dev server 2 origin (localhost / 127.0.0.1)。
# 本番: Railway などにデプロイした frontend の origin に上書きする。
# Spotify が redirect URI に http://localhost を許容しなくなった (2025-04 以降) ため、
# ローカル運用も 127.0.0.1 経由で揃える。
app.add_middleware(
    CORSMiddleware,
    allow_origins=_resolve_cors_allow_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(artists.router)
app.include_router(records.router)
app.include_router(releases.router)
app.include_router(spotify.router)
app.include_router(user_follows.router)


@app.get("/")
def root() -> dict[str, str]:
    return {"app": "jazz-life", "version": "0.1.0"}


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
