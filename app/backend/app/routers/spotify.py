"""Spotify Web API のプロキシ系エンドポイント。

現状は album 検索のみ。将来 ADR-003 PR-3 (`POST /api/records/from-release`) で
release lookup を足す際もここに集約する。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.exceptions import SpotifyApiError
from app.models.user import User
from app.routers.deps import get_current_user, get_spotify_app_client
from app.schemas.common import ListResponse
from app.schemas.spotify import SpotifyAlbumSummary
from app.services.spotify_app_client import SpotifyAppClient

router = APIRouter(prefix="/api/spotify", tags=["spotify"])


@router.get("/albums/search", response_model=ListResponse[SpotifyAlbumSummary])
def search_albums(
    q: str = Query(min_length=1, description="album title query"),
    artist: str | None = Query(default=None, description="artist name to refine the query"),
    # 2026-05 時点で Spotify Search は max=10 を超えると 400 を返す
    # (公式 doc は max=50 だが実挙動が乖離)。10 に絞って 400 を防ぐ。
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
