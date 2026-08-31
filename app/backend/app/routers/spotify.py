"""Proxy endpoints for the Spotify Web API.

Currently album search and artist search. When ADR-003 PR-3
(`POST /api/records/from-release`) adds release lookup, it should be
consolidated here as well.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.exceptions import SpotifyApiError
from app.models.user import User
from app.routers.deps import get_current_user, get_spotify_app_client
from app.schemas.common import ListResponse
from app.schemas.spotify import SpotifyAlbumSummary, SpotifyArtistSummary
from app.services.spotify_app_client import SpotifyAppClient

router = APIRouter(prefix="/api/spotify", tags=["spotify"])


@router.get("/artists/search", response_model=ListResponse[SpotifyArtistSummary])
def search_artists(
    q: str = Query(min_length=1, description="artist name query"),
    limit: int = Query(default=10, ge=1, le=10),
    _: User = Depends(get_current_user),
    client: SpotifyAppClient = Depends(get_spotify_app_client),
) -> ListResponse[SpotifyArtistSummary]:
    """Called from the add-follow modal on ArtistsPage.

    The UI takes the selected result through two steps to reach a follow:
    `POST /api/artists` (upsert) → `POST /api/user-follows`.
    """
    try:
        items = client.search_artists(query=q, limit=limit)
    except SpotifyApiError as exc:
        if exc.status_code == 429:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=str(exc),
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    return ListResponse[SpotifyArtistSummary](items=items)


@router.get("/albums/search", response_model=ListResponse[SpotifyAlbumSummary])
def search_albums(
    q: str = Query(min_length=1, description="album title query"),
    artist: str | None = Query(default=None, description="artist name to refine the query"),
    # As of 2026-05, Spotify Search returns 400 when limit exceeds 10
    # (the official docs say max=50, but actual behavior differs). Cap at 10.
    limit: int = Query(default=10, ge=1, le=10),
    _: User = Depends(get_current_user),
    client: SpotifyAppClient = Depends(get_spotify_app_client),
) -> ListResponse[SpotifyAlbumSummary]:
    try:
        items = client.search_albums(query=q, artist=artist, limit=limit)
    except SpotifyApiError as exc:
        if exc.status_code == 429:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=str(exc),
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    return ListResponse[SpotifyAlbumSummary](items=items)
