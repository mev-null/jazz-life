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
- `.env` ファイルは廃止 (詳細: README / docs/DEVELOPMENT.md)

起動時に Fernet 鍵 / JWT_SECRET / allowlist の妥当性を `model_validator` で検証し、
誤った設定で起動して最初の callback 時に初めて気付く事故を防ぐ。
"""

from __future__ import annotations

from functools import lru_cache

from cryptography.fernet import Fernet
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# JWT の iss / aud は環境変数化せずコード内定数として保持する。
# 同じ JWT_SECRET を別 backend と共有した場合に token を物理的に隔離するための識別子。
JWT_ISSUER = "jazz-life-api"
JWT_AUDIENCE = "jazz-life-web"

# OAuth state を保護する cookie 名。callback パスに限定して送る。
OAUTH_STATE_COOKIE_NAME = "oauth_state"

_ALLOWED_SAMESITE = {"lax", "strict", "none"}


def normalize_database_url(url: str) -> str:
    """Railway などの managed PG が渡してくる `postgres://` を SQLAlchemy 2.x が
    解釈できる `postgresql+psycopg://` に揃える。

    - `postgres://...`        → `postgresql+psycopg://...`
    - `postgresql://...`      → `postgresql+psycopg://...` (driver 未指定の場合のみ)
    - `postgresql+psycopg://` → そのまま

    `migrations/env.py` からも参照するため module-level に置く (Settings の
    field_validator は副作用 env を要求するため alembic offline mode で使い辛い)。
    """
    if not isinstance(url, str):
        return url
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    if url.startswith("postgresql://") and "+" not in url.split("://", 1)[0]:
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


class Settings(BaseSettings):
    # ---- DB ----
    database_url: str = Field(min_length=1)

    # ---- Spotify ----
    spotify_client_id: str = Field(min_length=1)
    spotify_client_secret: str = Field(min_length=1)
    spotify_redirect_uri: str = Field(min_length=1)

    # invite 制御は Spotify Developer Dashboard の Users and Access に集約する
    # (ADR-005)。アプリ側で重ねて allowlist を持たない。

    # ---- AudD (音声認識 / ADR-016) ----
    # 未設定 ("") の場合は recognize エンドポイントが 503 を返す (RecognitionService 側で判定)。
    audd_api_token: str = ""

    # ---- Auth ----
    jwt_secret: str
    refresh_token_key: str

    # ---- Cookie / frontend ----
    frontend_base_url: str = "http://127.0.0.1:5173"
    cookie_name: str = "jl_session"
    cookie_secure: bool = False
    cookie_samesite: str = "lax"
    session_ttl_seconds: int = 60 * 60 * 24 * 7  # 7 日
    state_ttl_seconds: int = 60 * 5  # 5 分

    # CORS_ALLOW_ORIGINS は CORSMiddleware 登録時 (main.py) に env を直読みする。
    # Settings に持たせると app 初期化時に Settings() の評価が要り、test 環境
    # (env 未設定) で起動できなくなるため意図的にここでは持たない。

    model_config = SettingsConfigDict(extra="ignore")

    @field_validator("database_url", mode="before")
    @classmethod
    def _normalize_database_url(cls, v: object) -> object:
        if not isinstance(v, str):
            return v
        return normalize_database_url(v)

    @field_validator("cookie_samesite", mode="before")
    @classmethod
    def _validate_samesite(cls, v: object) -> object:
        if v is None:
            return "lax"
        s = str(v).lower()
        if s not in _ALLOWED_SAMESITE:
            raise ValueError(f"COOKIE_SAMESITE must be one of {sorted(_ALLOWED_SAMESITE)}")
        return s

    @model_validator(mode="after")
    def _validate_secrets(self) -> Settings:
        if len(self.jwt_secret) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters")
        try:
            Fernet(self.refresh_token_key.encode())
        except (ValueError, TypeError) as exc:
            raise ValueError(
                "REFRESH_TOKEN_KEY must be a 32-byte url-safe base64 string "
                "(e.g. cryptography.fernet.Fernet.generate_key())"
            ) from exc
        # SameSite=None はブラウザ仕様で Secure=true が必須
        if self.cookie_samesite == "none" and not self.cookie_secure:
            raise ValueError("COOKIE_SAMESITE=none requires COOKIE_SECURE=true")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
