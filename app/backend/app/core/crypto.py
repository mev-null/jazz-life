"""Fernet を使った対称暗号ラッパ。

Spotify の refresh_token を DB に保存する際の暗号化に使う。鍵は
`Settings.refresh_token_key` (url-safe base64 32 バイト) を取り、`Fernet` の
コンストラクタはモジュール初期化時ではなくインスタンス化時に検証される。

設計上の注意:
- 復号した平文はローカル変数のみで扱い、ログ・例外メッセージに露出させない
  (§設計詳細 8 のログ出力ポリシー)。
- 暗号鍵を変更すると既存暗号文は全て読めなくなる。鍵ローテーションは MultiFernet
  を使った別 PR で整備する。
"""

from __future__ import annotations

from cryptography.fernet import Fernet


class TokenCipher:
    def __init__(self, key: str) -> None:
        self._fernet = Fernet(key.encode())

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, token: str) -> str:
        return self._fernet.decrypt(token.encode()).decode()
