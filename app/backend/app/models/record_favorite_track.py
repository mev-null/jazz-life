import uuid

from sqlalchemy import Index, text
from sqlmodel import Field, SQLModel, UniqueConstraint


class RecordFavoriteTrack(SQLModel, table=True):
    """User_collection に紐づく per-user の「お気に入り曲」 (ADR-006 §2.8)。

    Spotify 検索結果由来の track を 1 曲ずつ追加し、各曲に短い `note` を書ける。
    `track_name` を非正規化保持し、`tracks` catalog テーブルは作らない (将来需要が
    出たら partial INDEX 経由で外出し可能)。`(user_collection_id, position)`
    複合 PK で順序保持、`(user_collection_id, spotify_track_id)` UNIQUE で同一
    collection 内の Spotify 曲重複を禁止 (manual = NULL は重複可)。
    """

    __tablename__ = "record_favorite_tracks"
    __table_args__ = (
        UniqueConstraint(
            "user_collection_id",
            "spotify_track_id",
            name="uq_record_favorite_tracks_collection_spotify",
        ),
        Index(
            "ix_record_favorite_tracks_spotify_track_id",
            "spotify_track_id",
            postgresql_where=text("spotify_track_id IS NOT NULL"),
        ),
    )

    user_collection_id: uuid.UUID = Field(
        foreign_key="user_collections.id",
        ondelete="CASCADE",
        primary_key=True,
    )
    position: int = Field(primary_key=True)
    spotify_track_id: str | None = Field(default=None, max_length=64)
    track_name: str = Field(max_length=300)
    note: str | None = Field(default=None, max_length=500)
