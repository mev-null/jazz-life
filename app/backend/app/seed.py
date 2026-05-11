import json
from datetime import datetime
from pathlib import Path
from uuid import UUID

from app.core.repositories.artist_repository import ArtistRepository
from app.core.repositories.record_repository import RecordRepository
from app.core.repositories.user_follow_repository import UserFollowRepository
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


def seed_user_follows_if_empty(
    user_id: UUID,
    follow_repo: UserFollowRepository,
    record_repo: RecordRepository,
) -> int:
    """user_follows が空のとき、既存 records の artist_id 群を follow に流し込む。

    Phase B-3 で「records 登録時に user_follows へも自動追加 (auto-follow)」を
    実装した後の世界では、新規ユーザはここで何も起きない (record 0 件のため)。
    既存ユーザ (auto-follow 実装前から records を持っている) のために
    one-shot backfill として残してある。

    artists マスタからではなく records からコピーする理由:
    - Spotify ID が確実に有効な (record 登録時に Spotify search 経由で確定済の)
      artist だけが対象になる
    - 「コレクションに無いがフォローだけしたい」アーティストは将来 Spotify
      follow 同期 (Phase B-4) で別経路として入れる

    `POST /api/releases/sync` の冒頭で lazy に呼ぶ。
    """
    if follow_repo.count_by_user(user_id) > 0:
        return 0
    artist_ids = sorted({r.artist_id for r in record_repo.list_all()})
    return follow_repo.bulk_insert(user_id, artist_ids)
