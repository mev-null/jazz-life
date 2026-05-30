"""RecognitionService の単体テスト (ADR-016)。

AudD の HTTP レスポンスを pytest-httpx で stub し、`RecognitionResult` への
正規化 / no-match / トークン未設定 / 上流エラー の各経路を検証する。
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from pytest_httpx import HTTPXMock

from app.core.exceptions import RecognitionError
from app.services.recognition_service import AUDD_URL, RecognitionService

_AUDIO = b"fake-audio-bytes"


def _spotify_block() -> dict[str, Any]:
    return {
        "album": {
            "id": "spot-album-1",
            "name": "Kind of Blue",
            "release_date": "1959-08-17",
            "images": [{"url": "https://i.scdn.co/image/kob.jpg", "width": 640}],
        },
        "artists": [
            {
                "id": "art-miles",
                "name": "Miles Davis",
                "images": [{"url": "https://i.scdn.co/image/miles.jpg", "width": 640}],
            }
        ],
    }


def _success(result: dict[str, Any] | None) -> dict[str, Any]:
    return {"status": "success", "result": result}


def test_normalizes_match_with_spotify(httpx_mock: HTTPXMock) -> None:
    result = {
        "title": "So What",
        "artist": "Miles Davis",
        "album": "Kind of Blue (LP)",
        "release_date": "1959",
        "spotify": _spotify_block(),
    }
    httpx_mock.add_response(url=AUDD_URL, method="POST", json=_success(result))

    out = RecognitionService("tok").recognize(_AUDIO, "audio/webm")

    assert out.matched is True
    assert out.title == "So What"
    assert out.artist_name == "Miles Davis"
    # Spotify の album が基本 album を上書きする
    assert out.album == "Kind of Blue"
    assert out.spotify_album_id == "spot-album-1"
    assert out.image_url == "https://i.scdn.co/image/kob.jpg"
    assert out.original_release_date == "1959-08-17"
    assert out.spotify_artist_id == "art-miles"
    assert out.artist_image_url == "https://i.scdn.co/image/miles.jpg"


def test_normalizes_match_without_spotify(httpx_mock: HTTPXMock) -> None:
    result = {
        "title": "Naima",
        "artist": "John Coltrane",
        "album": "Giant Steps",
        "release_date": "1960-01-27",
    }
    httpx_mock.add_response(url=AUDD_URL, method="POST", json=_success(result))

    out = RecognitionService("tok").recognize(_AUDIO)

    assert out.matched is True
    assert out.title == "Naima"
    assert out.artist_name == "John Coltrane"
    assert out.album == "Giant Steps"
    assert out.original_release_date == "1960-01-27"
    assert out.spotify_album_id is None
    assert out.spotify_artist_id is None


def test_no_match_returns_unmatched(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=AUDD_URL, method="POST", json=_success(None))

    out = RecognitionService("tok").recognize(_AUDIO)

    assert out.matched is False
    assert out.title is None
    assert out.spotify_album_id is None


def test_missing_token_raises_503() -> None:
    with pytest.raises(RecognitionError) as exc:
        RecognitionService("").recognize(_AUDIO)
    assert exc.value.status_code == 503


def test_audd_body_failure_raises_502(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url=AUDD_URL,
        method="POST",
        json={"status": "error", "error": {"error_message": "wrong token"}},
    )

    with pytest.raises(RecognitionError) as exc:
        RecognitionService("tok").recognize(_AUDIO)
    assert exc.value.status_code == 502


def test_http_error_raises_502(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=AUDD_URL, method="POST", status_code=500, text="boom")

    with pytest.raises(RecognitionError) as exc:
        RecognitionService("tok").recognize(_AUDIO)
    assert exc.value.status_code == 502


def test_network_error_raises_502(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_exception(httpx.ConnectError("no route"))

    with pytest.raises(RecognitionError) as exc:
        RecognitionService("tok").recognize(_AUDIO)
    assert exc.value.status_code == 502
