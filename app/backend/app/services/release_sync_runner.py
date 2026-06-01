"""release sync をリクエストから切り離してバックグラウンド実行するランナー。

sync (Spotify Get Artist's Albums をフォロー中アーティスト全件に対して呼ぶ) は
レート制限の都合で数十秒〜分単位かかりうる。これを HTTP リクエスト内で同期実行
するとレスポンスが返らず、フロントのローディング表示も破綻する。そこで:

- `POST /api/releases/sync` はジョブを投入して即 202 を返す
- 実行状態は in-memory フラグ (is_running) で持ち、フロントは `/sync-status` を
  polling して進捗を知る
- 多重起動は Lock 付きフラグで弾く (実行中の再投入は no-op)

uvicorn 1 worker 前提。プロセス再起動でフラグは自然リセットされるので running が
stuck することはない。マルチワーカー / 永続キューが必要になったら Phase B-4 の
APScheduler 移行で作り直す。
"""

from __future__ import annotations

import logging
import threading
from datetime import date
from uuid import UUID

from app.core.db import SessionFactory
from app.core.repositories.release_read_state_repository import (
    ReleaseReadStateRepository,
)
from app.core.repositories.release_repository import ReleaseRepository
from app.core.repositories.sync_status_repository import SyncStatusRepository
from app.core.repositories.user_follow_repository import UserFollowRepository
from app.services.release_service import ReleaseService, SyncResult
from app.services.spotify_app_client import SpotifyAppClient

logger = logging.getLogger("uvicorn.error")


class ReleaseSyncRunner:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._running = False
        # 直近に完走したジョブの結果 (件数 / partial エラー)。フロントが
        # 「partial: N ingested・rate limited」等を出すための情報源。in-memory
        # なのでプロセス再起動で None に戻る (sync-status の last_* と違い揮発)。
        self._last_result: SyncResult | None = None

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._running

    @property
    def last_result(self) -> SyncResult | None:
        with self._lock:
            return self._last_result

    def reset(self) -> None:
        """in-memory 状態を初期化する (主にテストの分離用)。"""
        with self._lock:
            self._running = False
            self._last_result = None

    def try_begin(self) -> bool:
        """実行権を確保できたら True。既に実行中なら False で投入を弾く。"""
        with self._lock:
            if self._running:
                return False
            self._running = True
            return True

    def run(
        self,
        user_id: UUID,
        spotify: SpotifyAppClient,
        since_date: date,
        until_date: date,
        session_factory: SessionFactory,
    ) -> None:
        """`try_begin()` で確保した実行権で sync を回す。終了時に必ずフラグを解放する。

        session はジョブ専用に開き直す (リクエストスコープの session は閉じている)。
        sync_for_user が per-artist エラーや全件失敗を sync_status に記録するので、
        ここでは予期せぬ例外だけログに残してフラグ解放に専念する。
        """
        try:
            with session_factory() as session:
                service = ReleaseService(
                    ReleaseRepository(session),
                    ReleaseReadStateRepository(session),
                    UserFollowRepository(session),
                    SyncStatusRepository(session),
                )
                result = service.sync_for_user(user_id, spotify, since_date, until_date)
                with self._lock:
                    self._last_result = result
                logger.info(
                    "release sync done: total=%d succeeded=%d ingested=%d",
                    result.artists_total,
                    result.artists_succeeded,
                    result.albums_ingested,
                )
        except Exception:
            logger.exception("release sync background job crashed")
        finally:
            with self._lock:
                self._running = False


# process-wide シングルトン (in-memory running フラグを共有するため)。
release_sync_runner = ReleaseSyncRunner()
