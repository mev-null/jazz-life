from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session

from app.core.db import get_engine
from app.core.repositories.artist_repository import ArtistRepository
from app.routers import artists, auth, records, spotify
from app.seed import seed_artists_if_empty


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    with Session(get_engine()) as session:
        seed_artists_if_empty(ArtistRepository(session))
    yield


app = FastAPI(title="jazz-life", version="0.1.0", lifespan=lifespan)

# Spotify が redirect URI に http://localhost を許容しなくなったため (2025-04 以降)、
# OAuth は 127.0.0.1 経由に揃える。cookie のホストスコープと CORS の origin 一致を
# 守るため、frontend も 127.0.0.1:5173 経由でアクセスする前提。両方の origin を
# allowlist に並べて、過渡期も既存リンクが切れないようにする。
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(artists.router)
app.include_router(records.router)
app.include_router(spotify.router)


@app.get("/")
def root() -> dict[str, str]:
    return {"app": "jazz-life", "version": "0.1.0"}


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
