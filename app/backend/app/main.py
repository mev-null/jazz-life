from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session

from app.core.db import engine
from app.core.repositories.artist_repository import ArtistRepository
from app.routers import artists, records
from app.seed import seed_artists_if_empty


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    with Session(engine) as session:
        seed_artists_if_empty(ArtistRepository(session))
    yield


app = FastAPI(title="jazz-life", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(artists.router)
app.include_router(records.router)


@app.get("/")
def root() -> dict[str, str]:
    return {"app": "jazz-life", "version": "0.1.0"}


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
