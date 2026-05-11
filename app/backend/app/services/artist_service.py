import logging

from app.core.exceptions import SpotifyApiError
from app.core.repositories.artist_repository import ArtistRepository
from app.models.artist import Artist
from app.schemas.artist import ArtistCreate
from app.services.spotify_app_client import SpotifyAppClient

logger = logging.getLogger("uvicorn.error")


class ArtistService:
    def __init__(self, repo: ArtistRepository) -> None:
        self.repo = repo

    def list_all(self) -> list[Artist]:
        return self.repo.list_all()

    def get_with_image_hydration(
        self,
        spotify_id: str,
        spotify: SpotifyAppClient,
    ) -> Artist | None:
        """単一 artist を取り、image_url が NULL なら Spotify から補完する。

        ArtistDetailModal を開いた時の `GET /api/artists/{id}` から呼ぶ。
        Spotify 側エラー (rate limit / 5xx / ネットワーク) は best-effort で
        握り潰し、ログを残す: 画像が無くても UI 側は initials fallback で
        動くので、ここで 502 を返してモーダル全体を壊すよりは null 画像で
        返した方が ux 上望ましい。
        """
        artist = self.repo.get(spotify_id)
        if artist is None:
            return None
        if artist.image_url is not None:
            return artist
        try:
            images = spotify.get_artists_images([spotify_id])
        except SpotifyApiError as exc:
            logger.warning("artist image hydration skipped for %s: %s", spotify_id, exc)
            return artist
        url = images.get(spotify_id)
        if not url:
            return artist
        updated = self.repo.update_image(spotify_id, url)
        return updated or artist

    def upsert(self, payload: ArtistCreate) -> Artist:
        """spotify_id をキーに upsert。既存なら既存を返し、無ければ新規作成。

        RecordFormModal が Spotify album を選んだ時に artist が DB に無いケースを
        想定。冪等性を担保するため idempotent な upsert にする (重複 POST でも
        409 を返さない設計)。
        """
        existing = self.repo.get(payload.spotify_id)
        if existing is not None:
            return existing
        artist = Artist(
            spotify_id=payload.spotify_id,
            name=payload.name,
            image_url=payload.image_url,
            source=payload.source,
        )
        return self.repo.add(artist)
