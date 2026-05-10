from app.core.repositories.artist_repository import ArtistRepository
from app.models.artist import Artist


class ArtistService:
    def __init__(self, repo: ArtistRepository) -> None:
        self.repo = repo

    def list_all(self) -> list[Artist]:
        return self.repo.list_all()
