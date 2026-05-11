from app.core.repositories.artist_repository import ArtistRepository
from app.models.artist import Artist
from app.schemas.artist import ArtistCreate


class ArtistService:
    def __init__(self, repo: ArtistRepository) -> None:
        self.repo = repo

    def list_all(self) -> list[Artist]:
        return self.repo.list_all()

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
