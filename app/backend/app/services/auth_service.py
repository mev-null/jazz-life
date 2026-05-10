"""Spotify OAuth Authorization Code Flow と JWT セッションの統合サービス層。

責務:
- OAuth state の発行 / 検証 (`oauth_state` cookie とサーバ dict の二重防御)
- Spotify との code 交換 / プロフィール取得
- ALLOWED_SPOTIFY_USER_ID allowlist による 403 判定 (timing-safe 比較)
- refresh_token の Fernet 暗号化 → users upsert
- JWT (HS256, iss/aud 検証あり) の発行 / 復号

設計上の注意:
- 復号した平文 refresh_token / access_token / OAuth code はローカル変数に閉じ、
  ログ・例外メッセージに露出させない (§設計詳細 8)。
- state 用の in-memory dict は単一プロセス前提。redis 移行時は GETDEL / Lua で
  TOCTOU を避ける必要がある旨をコードコメントに残す。
"""

from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt

from app.core.crypto import TokenCipher
from app.core.exceptions import AuthError, ForbiddenError, SpotifyAuthError
from app.core.repositories.user_repository import UserRepository
from app.core.settings import (
    JWT_AUDIENCE,
    JWT_ISSUER,
    Settings,
)
from app.models.user import User
from app.services.spotify_oauth_client import SpotifyOAuthClient

# AuthService は per-request で生成されるため、state は process 内で共有する
# モジュール変数に置く必要がある (login と callback で別インスタンスになるため)。
# 単一プロセス前提。マルチプロセス化する場合は redis 等に置き換える
# (GETDEL や Lua で取得 + 削除を atomic にする必要あり、TOCTOU 防止)。
_state_store: dict[str, datetime] = {}


@dataclass(frozen=True)
class CallbackResult:
    user: User
    session_token: str


class AuthService:
    def __init__(
        self,
        user_repo: UserRepository,
        spotify: SpotifyOAuthClient,
        settings: Settings,
    ) -> None:
        self._user_repo = user_repo
        self._spotify = spotify
        self._settings = settings
        self._cipher = TokenCipher(settings.refresh_token_key)

    # ---- state 管理 ----

    def issue_state(self) -> str:
        state = secrets.token_urlsafe(32)
        _state_store[state] = datetime.now(UTC)
        self._evict_expired_states()
        return state

    def verify_state(self, url_state: str | None, cookie_state: str | None) -> None:
        if not url_state or not cookie_state:
            raise AuthError("missing state")
        if not secrets.compare_digest(url_state, cookie_state):
            raise AuthError("state mismatch")
        issued_at = _state_store.pop(url_state, None)
        if issued_at is None:
            raise AuthError("unknown or already used state")
        ttl = timedelta(seconds=self._settings.state_ttl_seconds)
        if datetime.now(UTC) - issued_at > ttl:
            raise AuthError("expired state")

    def _evict_expired_states(self) -> None:
        now = datetime.now(UTC)
        ttl = timedelta(seconds=self._settings.state_ttl_seconds)
        expired = [s for s, t in _state_store.items() if now - t > ttl]
        for s in expired:
            _state_store.pop(s, None)

    # ---- callback フロー ----

    def build_authorize_url(self, state: str) -> str:
        return self._spotify.build_authorize_url(state)

    def complete_callback(self, code: str) -> CallbackResult:
        token = self._spotify.exchange_code(code)
        if not token.refresh_token:
            # Spotify は code 交換時に必ず refresh_token を返す仕様。返らないのは異常。
            raise SpotifyAuthError("spotify did not return refresh_token")
        profile = self._spotify.get_me(token.access_token)
        self._enforce_allowlist(profile.id)
        encrypted = self._cipher.encrypt(token.refresh_token)
        user = self._user_repo.upsert_from_spotify(
            spotify_id=profile.id,
            display_name=profile.display_name,
            image_url=profile.image_url,
            encrypted_refresh_token=encrypted,
        )
        session_token = self._issue_session_token(user.id)
        return CallbackResult(user=user, session_token=session_token)

    def _enforce_allowlist(self, spotify_id: str) -> None:
        if not secrets.compare_digest(spotify_id, self._settings.allowed_spotify_user_id):
            raise ForbiddenError("user not in allowlist")

    # ---- JWT セッション ----

    def _issue_session_token(self, user_id: uuid.UUID) -> str:
        now = datetime.now(UTC)
        payload = {
            "sub": str(user_id),
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(seconds=self._settings.session_ttl_seconds)).timestamp()),
            "type": "session",
            "iss": JWT_ISSUER,
            "aud": JWT_AUDIENCE,
        }
        return jwt.encode(payload, self._settings.jwt_secret, algorithm="HS256")

    def decode_session_token(self, token: str) -> uuid.UUID:
        try:
            payload = jwt.decode(
                token,
                self._settings.jwt_secret,
                algorithms=["HS256"],
                issuer=JWT_ISSUER,
                audience=JWT_AUDIENCE,
            )
        except jwt.PyJWTError as exc:
            raise AuthError("invalid session token") from exc
        if payload.get("type") != "session":
            raise AuthError("wrong token type")
        sub = payload.get("sub")
        if not isinstance(sub, str):
            raise AuthError("malformed sub")
        try:
            return uuid.UUID(sub)
        except ValueError as exc:
            raise AuthError("malformed sub") from exc

    # ---- refresh_token の復号 (後続 PR の同期処理用に公開) ----

    def decrypt_refresh_token(self, encrypted: str) -> str:
        return self._cipher.decrypt(encrypted)
