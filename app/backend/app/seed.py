import json
from datetime import datetime
from pathlib import Path

from app.core.repositories.artist_repository import ArtistRepository
from app.models.artist import Artist

_SEEDS_DIR = Path(__file__).parent / "seeds"


def seed_artists_if_empty(repo: ArtistRepository) -> int:
    """Insert seed artists when the table is empty. Returns count inserted.

    現状 `seeds/artists.json` は items=[] にしてあり、artist は「ユーザが
    record を登録した時に Spotify 検索経由で動的追加される」運用に倒している
    (詳細は `RecordService.create` の auto-follow を参照)。
    """
    if repo.count() > 0:
        return 0
    payload = json.loads((_SEEDS_DIR / "artists.json").read_text(encoding="utf-8"))
    rows = [
        Artist(
            spotify_id=item["spotify_id"],
            name=item["name"],
            image_url=item.get("image_url"),
            source="seeded",
            added_at=datetime.fromisoformat(item["added_at"].replace("Z", "+00:00")),
        )
        for item in payload["items"]
    ]
    repo.bulk_insert(rows)
    return len(rows)
