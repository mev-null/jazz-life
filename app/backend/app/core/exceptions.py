class DomainError(Exception):
    """Base for errors raised by the service layer."""


class NotFoundError(DomainError):
    """Raised when a referenced entity does not exist."""


class SpotifyAuthError(DomainError):
    """Spotify OAuth フロー中の失敗を表す。

    `__str__` には secret (code / access_token / refresh_token / Spotify レスポンス全文)
    を含めない。コンストラクタは `safe_message` のみを受け取る設計とし、外部に流れる
    情報を絞り込む (§設計詳細 8 のログ出力ポリシー)。
    """

    def __init__(self, safe_message: str) -> None:
        super().__init__(safe_message)
        self.safe_message = safe_message

    def __str__(self) -> str:
        return self.safe_message


class AuthError(DomainError):
    """セッション検証 / OAuth state 検証で発生するエラー。

    SpotifyAuthError と同様、`safe_message` のみ外部に出る。
    """

    def __init__(self, safe_message: str) -> None:
        super().__init__(safe_message)
        self.safe_message = safe_message

    def __str__(self) -> str:
        return self.safe_message


class ForbiddenError(DomainError):
    """Allowlist 等によるアクセス拒否。"""

    def __init__(self, safe_message: str) -> None:
        super().__init__(safe_message)
        self.safe_message = safe_message

    def __str__(self) -> str:
        return self.safe_message


class SpotifyApiError(DomainError):
    """Spotify Web API (user 認証不要の参照系) 呼び出しで発生したエラー。

    `status_code` には Spotify 側ステータスを格納し、router で 429 / 502 へ分岐させる。
    `__str__` は `safe_message` のみ (auth 系と同方針)。
    """

    def __init__(self, safe_message: str, *, status_code: int | None = None) -> None:
        super().__init__(safe_message)
        self.safe_message = safe_message
        self.status_code = status_code

    def __str__(self) -> str:
        return self.safe_message
