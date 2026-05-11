"""Spotify Authorization Code Flow に対する HTTP クライアント。

このクラスは外部システム (Spotify Web API) のアダプタであり、`services/` 配下に
置くのは clean architecture 派生の既存配置に揃えるため。`core/` は DB アクセス層で
あり、HTTP I/O はそこに混ぜない。

呼び出しは同期 (`httpx.Client`) でまとめる。FastAPI は sync / async どちらでも捌けるが
既存 routers が sync (`def`) で揃っており、本クライアントも sync にすることで
スタックを単純に保つ。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from app.core.exceptions import SpotifyAuthError
from app.core.settings import Settings

# uvicorn のデフォルト logger 設定下では `uvicorn.error` が stdout に流れるため、
# それに乗せる (アプリ独自 logger だと basicConfig 未呼び出しで黙ることがある)。
logger = logging.getLogger("uvicorn.error")

SPOTIFY_AUTHORIZE_URL = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_ME_URL = "https://api.spotify.com/v1/me"

# user-follow-read を最初から要求しておくことで、後続の followed-artists 同期 PR で
# 再認可ダイアログを出さずに済む。user-read-email は profile 取得の慣例的最低限。
DEFAULT_SCOPES = ("user-read-private", "user-read-email", "user-follow-read")


@dataclass(frozen=True)
class SpotifyTokenResponse:
    access_token: str
    refresh_token: str | None
    expires_in: int


@dataclass(frozen=True)
class SpotifyUserProfile:
    id: str
    display_name: str
    image_url: str | None


class SpotifyOAuthClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def build_authorize_url(self, state: str, scopes: tuple[str, ...] = DEFAULT_SCOPES) -> str:
        params = {
            "client_id": self._settings.spotify_client_id,
            "response_type": "code",
            "redirect_uri": self._settings.spotify_redirect_uri,
            "scope": " ".join(scopes),
            "state": state,
        }
        return f"{SPOTIFY_AUTHORIZE_URL}?{urlencode(params)}"

    def exchange_code(self, code: str) -> SpotifyTokenResponse:
        body = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self._settings.spotify_redirect_uri,
        }
        return self._post_token(body)

    def refresh_access_token(self, refresh_token: str) -> SpotifyTokenResponse:
        body = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
        return self._post_token(body)

    def get_me(self, access_token: str) -> SpotifyUserProfile:
        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.get(
                    SPOTIFY_ME_URL,
                    headers={"Authorization": f"Bearer {access_token}"},
                )
        except httpx.HTTPError as exc:
            raise SpotifyAuthError("failed to reach Spotify") from exc
        if res.status_code != 200:
            raise SpotifyAuthError(f"spotify /v1/me returned {res.status_code}")
        payload = res.json()
        spotify_id = payload.get("id")
        display_name = payload.get("display_name") or spotify_id
        if not spotify_id:
            raise SpotifyAuthError("spotify /v1/me missing id")
        images = payload.get("images") or []
        image_url = images[0].get("url") if images else None
        return SpotifyUserProfile(
            id=spotify_id,
            display_name=display_name,
            image_url=image_url,
        )

    def _post_token(self, body: dict[str, str]) -> SpotifyTokenResponse:
        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.post(
                    SPOTIFY_TOKEN_URL,
                    data=body,
                    auth=(
                        self._settings.spotify_client_id,
                        self._settings.spotify_client_secret,
                    ),
                )
        except httpx.HTTPError as exc:
            raise SpotifyAuthError("failed to reach Spotify token endpoint") from exc
        if res.status_code != 200:
            # 4xx 時は Spotify の error / error_description だけログに残す
            # (logging policy §設計詳細 8 で公開情報として許可)。
            # access_token / refresh_token はそもそも 4xx レスポンスに含まれないが
            # res.text 全体を載せない設計を貫く。
            try:
                err_body = res.json()
                err_code = err_body.get("error")
                err_desc = err_body.get("error_description")
            except ValueError:
                err_code = None
                err_desc = None
            logger.warning(
                "spotify token endpoint returned %s error=%s description=%s",
                res.status_code,
                err_code,
                err_desc,
            )
            raise SpotifyAuthError(f"spotify token endpoint returned {res.status_code}")
        payload = res.json()
        access_token = payload.get("access_token")
        if not access_token:
            raise SpotifyAuthError("spotify token response missing access_token")
        return SpotifyTokenResponse(
            access_token=access_token,
            refresh_token=payload.get("refresh_token"),
            expires_in=int(payload.get("expires_in", 0)),
        )
