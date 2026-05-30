"""音声認識 (AudD) クライアント / 正規化サービス (ADR-016)。

録音した短いクリップ (webm/opus, mp4/aac 等) を AudD の `POST https://api.audd.io/`
に multipart で投げ、返ってきた 1 件のマッチを `RecognitionResult` に正規化する。

`return=spotify` を付けることで、その曲に対応する Spotify トラック情報
(album.id / images / release_date, artists[].id) まで取得し、曲 → アルバム +
Spotify アーティスト ID を解決する。frontend はこれを Record 追加フォームに prefill する。

外部 API クライアントの作法 (httpx 同期 + DomainError 変換) は SpotifyAppClient
(`spotify_app_client.py`) に倣う。
"""

from __future__ import annotations

import httpx

from app.core.exceptions import RecognitionError
from app.schemas.recognition import RecognitionResult

# テストが mock 登録に使えるよう module-level の定数として公開する
# (spotify_app_client の SPOTIFY_TOKEN_URL と同方針)。
AUDD_URL = "https://api.audd.io/"
# 録音は最大 ~15 秒。AudD 側の指紋照合に余裕を見て長めに取る。
_HTTP_TIMEOUT = 30.0


class RecognitionService:
    def __init__(self, api_token: str) -> None:
        self._api_token = api_token

    def recognize(self, audio: bytes, content_type: str | None = None) -> RecognitionResult:
        """音声バイト列を AudD に送って認識結果を返す。

        - トークン未設定 → RecognitionError(503)
        - 通信失敗 / 上流エラー → RecognitionError(502)
        - マッチ無し (`result` が null) → `RecognitionResult(matched=False)`
        """
        if not self._api_token:
            raise RecognitionError(
                "audio recognition is not configured (AUDD_API_TOKEN missing)",
                status_code=503,
            )

        filename = "clip"
        try:
            resp = httpx.post(
                AUDD_URL,
                data={"api_token": self._api_token, "return": "spotify"},
                files={"file": (filename, audio, content_type or "application/octet-stream")},
                timeout=_HTTP_TIMEOUT,
            )
        except httpx.HTTPError as exc:
            raise RecognitionError(f"audd request failed: {exc}", status_code=502) from exc

        if resp.status_code >= 400:
            raise RecognitionError(
                f"audd api error {resp.status_code}: {resp.text}", status_code=502
            )

        payload = resp.json()
        # AudD は HTTP 200 でも本体 status で失敗を返すことがある (例: 認証エラー)。
        if payload.get("status") != "success":
            detail = payload.get("error", {}).get("error_message") or payload.get("status")
            raise RecognitionError(f"audd recognition failed: {detail}", status_code=502)

        return self._normalize(payload.get("result"))

    @staticmethod
    def _normalize(result: dict | None) -> RecognitionResult:
        if not result:
            return RecognitionResult(matched=False)

        out = RecognitionResult(
            matched=True,
            title=result.get("title"),
            artist_name=result.get("artist"),
            album=result.get("album"),
            original_release_date=result.get("release_date"),
        )

        # `return=spotify` で付く Spotify トラックメタを使ってアルバム / アーティストを補完。
        spotify = result.get("spotify") or {}
        album = spotify.get("album") or {}
        if album:
            out.spotify_album_id = album.get("id")
            out.album = album.get("name") or out.album
            images = album.get("images") or []
            if images:
                out.image_url = images[0].get("url")
            out.original_release_date = album.get("release_date") or out.original_release_date

        artists = spotify.get("artists") or []
        if artists:
            first = artists[0]
            out.spotify_artist_id = first.get("id")
            out.artist_name = out.artist_name or first.get("name")
            images = first.get("images") or []
            if images:
                out.artist_image_url = images[0].get("url")

        return out
