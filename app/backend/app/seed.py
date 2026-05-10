import json
from datetime import datetime
from pathlib import Path

from app.core.repositories.artist_repository import ArtistRepository
from app.models.artist import Artist

_SEEDS_DIR = Path(__file__).parent / "seeds"


def seed_artists_if_empty(repo: ArtistRepository) -> int:
    """Insert seed artists when the table is empty. Returns count inserted."""
    if repo.count() > 0:
        return 0
    payload = json.loads((_SEEDS_DIR / "artists.json").read_text(encoding="utf-8"))
    rows = [
        Artist(
            spotify_id=item["spotify_id"],
            name=item["name"],
            image_url=item.get("image_url"),
            followed=item.get("followed", False),
            added_at=datetime.fromisoformat(item["added_at"].replace("Z", "+00:00")),
        )
        for item in payload["items"]
    ]
    repo.bulk_insert(rows)
    return len(rows)
