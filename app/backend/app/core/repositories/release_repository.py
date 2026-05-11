from datetime import date

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import Session, and_, col, select

from app.models.release import Release


class ReleaseRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_window(self, from_date: date, to_date: date) -> list[Release]:
        """`release_date` が `[from_date, to_date]` の Release を新しい順で返す。

        Feed の「直近30日 / 今後の予定」表示用 (ADR-000 §220)。Phase B-3 では
        ingest 時点で `album` / `single` 以外を弾いているので、ここでは
        album_type フィルタは行わない。
        """
        stmt = (
            select(Release)
            .where(
                and_(
                    col(Release.release_date) >= from_date,
                    col(Release.release_date) <= to_date,
                )
            )
            .order_by(col(Release.release_date).desc())
        )
        return list(self.session.exec(stmt).all())

    def upsert_many(self, rows: list[Release]) -> int:
        """`spotify_id` を key にして bulk upsert する。

        Phase B-3 sync で Get Artist's Albums の結果を流し込む経路。`is_read /
        read_at` は touch しない (将来 backend 既読化したときに sync 再実行で
        既読状態が消えるのを防ぐ)。戻り値は upsert を試みた行数 (Postgres は
        ON CONFLICT DO UPDATE の場合に「実際に変更があった」行数を返さないため、
        新規 + 既存を区別しないラフな件数として扱う)。
        """
        if not rows:
            return 0
        payloads = [
            {
                "spotify_id": r.spotify_id,
                "artist_id": r.artist_id,
                "title": r.title,
                "album_type": r.album_type,
                "release_date": r.release_date,
                "image_url": r.image_url,
                "is_read": r.is_read,
                "read_at": r.read_at,
            }
            for r in rows
        ]
        stmt = pg_insert(Release).values(payloads)
        stmt = stmt.on_conflict_do_update(
            index_elements=["spotify_id"],
            set_={
                "artist_id": stmt.excluded.artist_id,
                "title": stmt.excluded.title,
                "album_type": stmt.excluded.album_type,
                "release_date": stmt.excluded.release_date,
                "image_url": stmt.excluded.image_url,
            },
        )
        self.session.exec(stmt)  # type: ignore[call-overload]
        self.session.commit()
        return len(rows)
