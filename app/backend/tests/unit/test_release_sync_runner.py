"""ReleaseSyncRunner の多重起動防止 / フラグ解放の挙動テスト。

実際の sync (DB + Spotify) は integration テスト側で検証する。ここは in-memory
running フラグのライフサイクル (try_begin の排他、run 後の解放) に絞る。
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from uuid import uuid4

from app.services.release_sync_runner import ReleaseSyncRunner


def test_try_begin_is_mutually_exclusive() -> None:
    runner = ReleaseSyncRunner()
    assert runner.try_begin() is True
    assert runner.is_running is True
    # 実行中の再投入は弾く。
    assert runner.try_begin() is False


def test_run_resets_running_flag_even_on_crash() -> None:
    """session_factory が壊れても finally で running が必ず False に戻る。"""
    runner = ReleaseSyncRunner()
    assert runner.try_begin() is True

    @contextmanager
    def _boom_factory() -> Iterator[None]:
        raise RuntimeError("db down")
        yield  # pragma: no cover - 到達しない

    # spotify は触る前に factory が落ちるのでダミーで良い。
    runner.run(uuid4(), object(), date.today(), date.today(), _boom_factory)  # type: ignore[arg-type]

    assert runner.is_running is False
