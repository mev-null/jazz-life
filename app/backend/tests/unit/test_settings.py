import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError

from app.core.settings import Settings


def _valid_kwargs(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "database_url": "postgresql+psycopg://jazz:jazz@db:5432/jazz",
        "spotify_client_id": "cid",
        "spotify_client_secret": "secret",
        "spotify_redirect_uri": "http://localhost:8000/api/auth/callback",
        "allowed_spotify_user_id": "owner",
        "jwt_secret": "x" * 32,
        "refresh_token_key": Fernet.generate_key().decode(),
    }
    base.update(overrides)
    return base


def test_settings_accepts_valid_values() -> None:
    settings = Settings(**_valid_kwargs())  # type: ignore[arg-type]
    assert settings.spotify_client_id == "cid"


def test_short_jwt_secret_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(**_valid_kwargs(jwt_secret="x" * 31))  # type: ignore[arg-type]


def test_invalid_fernet_key_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(**_valid_kwargs(refresh_token_key="not-a-real-fernet-key"))  # type: ignore[arg-type]


def test_empty_allowlist_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(**_valid_kwargs(allowed_spotify_user_id=""))  # type: ignore[arg-type]
