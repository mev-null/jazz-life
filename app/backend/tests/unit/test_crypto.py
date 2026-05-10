import pytest
from cryptography.fernet import Fernet, InvalidToken

from app.core.crypto import TokenCipher


def _key() -> str:
    return Fernet.generate_key().decode()


def test_roundtrip_returns_original_plaintext() -> None:
    cipher = TokenCipher(_key())
    plaintext = "AQB-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    token = cipher.encrypt(plaintext)
    assert token != plaintext
    assert cipher.decrypt(token) == plaintext


def test_decrypt_with_different_key_raises() -> None:
    sealed = TokenCipher(_key()).encrypt("secret")
    with pytest.raises(InvalidToken):
        TokenCipher(_key()).decrypt(sealed)


def test_invalid_key_raises_on_construction() -> None:
    with pytest.raises(ValueError):
        TokenCipher("not-a-real-fernet-key")
