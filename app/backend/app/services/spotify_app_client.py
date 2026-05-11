"""Spotify Web API を app token (Client Credentials Flow) で叩くクライアント。

`spotify_oauth_client.SpotifyOAuthClient` は user OAuth (Authorization Code Flow)
専用で、ユーザのプロフィールやフォロー情報など user-scoped なエンドポイントに使う。
一方アルバム検索など public な参照系は user token を使う必要がなく、app token
(Client Credentials) で十分。クライアントを分けることで、user scope の access_token を
処理する DB ロジック (refresh / 暗号化) を public 参照経路に持ち込まないようにする。

設計詳細:
- access_token は in-memory にキャッシュし、`expires_in` から margin (60s) を引いた
  時刻で再取得する。Web API の rate limit / latency 両方を削るための定石。
- sync (`httpx.Client`) で揃える (`spotify_oauth_client` と同じ理由)。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import httpx

from app.core.exceptions import SpotifyApiError
from app.core.settings import Settings
from app.schemas.spotify import SpotifyAlbumSummary

logger = logging.getLogger("uvicorn.error")

SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_SEARCH_URL = "https://api.spotify.com/v1/search"
SPOTIFY_ARTISTS_URL = "https://api.spotify.com/v1/artists"

_TOKEN_EXPIRY_MARGIN_SECONDS = 60
# GET /v1/artists?ids=... の上限。Spotify 公式仕様。
_ARTISTS_BATCH_LIMIT = 50


@dataclass
class _CachedToken:
    access_token: str
    expires_at: float  # epoch seconds


class SpotifyAppClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._cached: _CachedToken | None = None

    def search_albums(
        self,
        query: str,
        artist: str | None = None,
        limit: int = 20,
    ) -> list[SpotifyAlbumSummary]:
        if not query.strip():
            return []
        token = self._get_app_token()
        # type=album で既に album 種別に絞っているので、追加で `album:` field-filter を
        # 重ねると Spotify が 400 を返すことがある。クエリ本体はそのまま渡し、artist
        # のみ field filter で絞り込む。
        q = query.strip()
        if artist:
            q += f' artist:"{artist}"'
        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.get(
                    SPOTIFY_SEARCH_URL,
                    headers={"Authorization": f"Bearer {token}"},
                    params={"q": q, "type": "album", "limit": limit},
                )
        except httpx.HTTPError as exc:
            raise SpotifyApiError("failed to reach Spotify search endpoint") from exc
        if res.status_code == 429:
            raise SpotifyApiError("spotify rate limit exceeded", status_code=429)
        if res.status_code != 200:
            try:
                err_body = res.json()
                err_detail = err_body.get("error")
            except ValueError:
                err_detail = None
            logger.warning(
                "spotify search returned %s q=%r error=%s",
                res.status_code,
                q,
                err_detail,
            )
            raise SpotifyApiError(
                f"spotify search returned {res.status_code}",
                status_code=res.status_code,
            )
        payload = res.json()
        items = (payload.get("albums") or {}).get("items") or []
        return [_to_summary(item) for item in items]

    def get_artists_images(self, ids: list[str]) -> dict[str, str | None]:
        """`GET /v1/artists?ids=...` で複数アーティストの画像 URL をまとめて取る。

        Spotify は一度に 50 件まで受け付けるので超える場合はチャンク分割する。
        戻り値は `{ spotify_id: image_url or None }`。Spotify から `null`
        (ID 不正) が返ったエントリや、`images` が空のアーティストは `None`
        を入れて返し、呼び出し側で「未取得」と「画像なし」を区別する必要は
        生じないようにする (どちらも DB 上は image_url=None のまま据え置きで
        良い)。
        """
        deduped = [i for i in dict.fromkeys(ids) if i]
        if not deduped:
            return {}
        token = self._get_app_token()
        result: dict[str, str | None] = {}
        for start in range(0, len(deduped), _ARTISTS_BATCH_LIMIT):
            chunk = deduped[start : start + _ARTISTS_BATCH_LIMIT]
            try:
                with httpx.Client(timeout=10.0) as client:
                    res = client.get(
                        SPOTIFY_ARTISTS_URL,
                        headers={"Authorization": f"Bearer {token}"},
                        params={"ids": ",".join(chunk)},
                    )
            except httpx.HTTPError as exc:
                raise SpotifyApiError("failed to reach Spotify artists endpoint") from exc
            if res.status_code == 429:
                raise SpotifyApiError("spotify rate limit exceeded", status_code=429)
            if res.status_code != 200:
                try:
                    err_body = res.json()
                    err_detail = err_body.get("error")
                except ValueError:
                    err_detail = None
                logger.warning(
                    "spotify artists endpoint returned %s ids=%d error=%s",
                    res.status_code,
                    len(chunk),
                    err_detail,
                )
                raise SpotifyApiError(
                    f"spotify artists endpoint returned {res.status_code}",
                    status_code=res.status_code,
                )
            payload = res.json()
            entries = payload.get("artists") or []
            for entry in entries:
                if not entry:
                    # Spotify は ID 不正時に null を返す。呼び出し側がチャンクに
                    # 入れた順序は保てないので、id 取り出しは entry["id"] に頼る。
                    continue
                artist_id = entry.get("id")
                if not artist_id:
                    continue
                images = entry.get("images") or []
                image_url = images[0].get("url") if images else None
                result[artist_id] = image_url
        return result

    def _get_app_token(self) -> str:
        cached = self._cached
        if cached is not None and cached.expires_at > time.time():
            return cached.access_token
        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.post(
                    SPOTIFY_TOKEN_URL,
                    data={"grant_type": "client_credentials"},
                    auth=(
                        self._settings.spotify_client_id,
                        self._settings.spotify_client_secret,
                    ),
                )
        except httpx.HTTPError as exc:
            raise SpotifyApiError("failed to reach Spotify token endpoint") from exc
        if res.status_code != 200:
            try:
                err_body = res.json()
                err_code = err_body.get("error")
            except ValueError:
                err_code = None
            logger.warning(
                "spotify app-token endpoint returned %s error=%s",
                res.status_code,
                err_code,
            )
            raise SpotifyApiError(
                f"spotify app-token endpoint returned {res.status_code}",
                status_code=res.status_code,
            )
        payload = res.json()
        access_token = payload.get("access_token")
        expires_in = int(payload.get("expires_in", 0))
        if not access_token or expires_in <= 0:
            raise SpotifyApiError("spotify app-token response missing fields")
        self._cached = _CachedToken(
            access_token=access_token,
            expires_at=time.time() + expires_in - _TOKEN_EXPIRY_MARGIN_SECONDS,
        )
        return access_token


def _to_summary(item: dict) -> SpotifyAlbumSummary:
    images = item.get("images") or []
    image_url = images[0].get("url") if images else None
    artists = item.get("artists") or []
    primary_artist_id = artists[0].get("id") if artists else None
    return SpotifyAlbumSummary(
        id=item.get("id") or "",
        name=item.get("name") or "",
        release_date=item.get("release_date"),
        image_url=image_url,
        artist_names=[a.get("name") for a in artists if a.get("name")],
        primary_artist_id=primary_artist_id,
    )
