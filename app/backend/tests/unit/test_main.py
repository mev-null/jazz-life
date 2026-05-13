"""`app/main.py` の env 直読みヘルパの挙動テスト。

CORS / docs の露出制御は Settings 経由ではなく env を直接読む方式に倒している
(test 環境で Settings の必須項目が無くても app を構築できるようにするため)。
ヘルパ関数を単体で叩いて挙動を確認する。
"""

from __future__ import annotations

import pytest

from app.main import _resolve_cors_allow_origins, _resolve_docs_kwargs


@pytest.mark.parametrize(
    "value,expected",
    [
        ("true", {}),
        ("True", {}),
        ("1", {}),
        ("yes", {}),
        ("false", {"docs_url": None, "redoc_url": None, "openapi_url": None}),
        ("False", {"docs_url": None, "redoc_url": None, "openapi_url": None}),
        ("0", {"docs_url": None, "redoc_url": None, "openapi_url": None}),
        ("no", {"docs_url": None, "redoc_url": None, "openapi_url": None}),
        ("", {"docs_url": None, "redoc_url": None, "openapi_url": None}),
    ],
)
def test_resolve_docs_kwargs(
    monkeypatch: pytest.MonkeyPatch, value: str, expected: dict[str, str | None]
) -> None:
    monkeypatch.setenv("EXPOSE_OPENAPI_DOCS", value)
    assert _resolve_docs_kwargs() == expected


def test_resolve_docs_kwargs_defaults_to_exposed(monkeypatch: pytest.MonkeyPatch) -> None:
    """env 未設定なら docs を露出する (ローカル / CI の利便を優先)。"""
    monkeypatch.delenv("EXPOSE_OPENAPI_DOCS", raising=False)
    assert _resolve_docs_kwargs() == {}


def test_resolve_cors_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CORS_ALLOW_ORIGINS", raising=False)
    assert _resolve_cors_allow_origins() == [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]


def test_resolve_cors_from_csv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "https://a.example.com, https://b.example.com")
    assert _resolve_cors_allow_origins() == [
        "https://a.example.com",
        "https://b.example.com",
    ]
