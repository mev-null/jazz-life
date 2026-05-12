from datetime import UTC, datetime

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import Session

from app.models.sync import SyncStatus


class SyncStatusRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, source: str) -> SyncStatus | None:
        return self.session.get(SyncStatus, source)

    def mark_attempt(self, source: str) -> None:
        """sync 開始時に `last_attempt_at` を now() で更新する。

        Row が無ければ新規作成。`last_success_at` / `last_error` は触らない
        (前回成功時刻は次の成功までずっと残しておく)。
        """
        self._upsert(source, last_attempt_at=datetime.now(UTC))

    def mark_success(self, source: str) -> None:
        """sync 成功時に `last_success_at` を now() に、`last_error` を null に。"""
        now = datetime.now(UTC)
        self._upsert(
            source,
            last_attempt_at=now,
            last_success_at=now,
            last_error=None,
        )

    def mark_error(self, source: str, message: str) -> None:
        """sync 失敗時に `last_error` をセット。`last_success_at` は据え置き。"""
        self._upsert(
            source,
            last_attempt_at=datetime.now(UTC),
            last_error=message,
        )

    def _upsert(self, source: str, **fields: object) -> None:
        stmt = pg_insert(SyncStatus).values(source=source, **fields)
        stmt = stmt.on_conflict_do_update(
            index_elements=["source"],
            set_={k: v for k, v in fields.items()},
        )
        self.session.exec(stmt)  # type: ignore[call-overload]
        self.session.commit()
