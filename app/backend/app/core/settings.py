"""アプリ設定を pydantic-settings で 1 つのクラスに集約する。

`get_settings()` は `@lru_cache` 経由でシングルトンを返し、`Depends(get_settings)`
パターンで service / dependency に注入する。テストでは `app.dependency_overrides` で
差し替える。

env の出所:
- Codespaces user secrets → `.devcontainer/devcontainer.json` の `secrets` 経由で
  container shell に注入される
- 公開デフォルト → `.devcontainer/devcontainer.json` の `containerEnv`
- docker-compose は host shell env を `environment:` substitution で container に
  forward する
- `.env` ファイルは廃止 (詳細: README / CLAUDE.md)

起動時に Fernet 鍵 / JWT_SECRET / allowlist の妥当性を `model_validator` で検証し、
誤った設定で起動して最初の callback 時に初めて気付く事故を防ぐ。
"""

from __future__ import annotations

from functools import lru_cache
from typing import Self

from cryptography.fernet import Fernet
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# JWT の iss / aud は環境変数化せずコード内定数として保持する。
# 同じ JWT_SECRET を別 backend と共有した場合に token を物理的に隔離するための識別子。
JWT_ISSUER = "jazz-life-api"
JWT_AUDIENCE = "jazz-life-web"

# OAuth state を保護する cookie 名。callback パスに限定して送る。
OAUTH_STATE_COOKIE_NAME = "oauth_state"


class Settings(BaseSettings):
    # ---- DB ----
    database_url: str = Field(min_length=1)

    # ---- Spotify ----
    spotify_client_id: str = Field(min_length=1)
    spotify_client_secret: str = Field(min_length=1)
    spotify_redirect_uri: str = Field(min_length=1)

    allowed_spotify_user_id: str = Field(min_length=1)

    # ---- Auth ----
    jwt_secret: str
    refresh_token_key: str

    # ---- Cookie / frontend ----
    frontend_base_url: str = "http://127.0.0.1:5173"
    cookie_name: str = "jl_session"
    cookie_secure: bool = False
    session_ttl_seconds: int = 60 * 60 * 24 * 7  # 7 日
    state_ttl_seconds: int = 60 * 5  # 5 分

    model_config = SettingsConfigDict(extra="ignore")

    @model_validator(mode="after")
    def _validate_secrets(self) -> Self:
        if len(self.jwt_secret) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters")
        try:
            Fernet(self.refresh_token_key.encode())
        except (ValueError, TypeError) as exc:
            raise ValueError(
                "REFRESH_TOKEN_KEY must be a 32-byte url-safe base64 string "
                "(e.g. cryptography.fernet.Fernet.generate_key())"
            ) from exc
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
