class DomainError(Exception):
    """Base for errors raised by the service layer."""


class NotFoundError(DomainError):
    """Raised when a referenced entity does not exist."""


class ConflictError(DomainError):
    """Raised when an operation conflicts with current state (e.g. UNIQUE 違反).

    Router 側で 409 にマップする。`safe_message` 相当のシンプルな文字列を
    コンストラクタに渡す。
    """


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


class RecognitionError(DomainError):
    """音声認識 (AudD) 呼び出しで発生したエラー (ADR-016)。

    `status_code` には router がそのまま返す HTTP status を格納する。
    - トークン未設定 → 503 (Service Unavailable)
    - 上流 AudD のエラー / 通信失敗 → 502 (Bad Gateway)
    `__str__` は `safe_message` のみ (auth / spotify 系と同方針)。
    """

    def __init__(self, safe_message: str, *, status_code: int = 502) -> None:
        super().__init__(safe_message)
        self.safe_message = safe_message
        self.status_code = status_code

    def __str__(self) -> str:
        return self.safe_message
