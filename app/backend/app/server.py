"""Dual-stack (IPv4 + IPv6) uvicorn launcher for Railway.

Railway edge は IPv4 経由でコンテナに到達する一方、private networking
(`<service>.railway.internal`) は IPv6 でのみ解決される。両方を 1 プロセスで
受けるには、IPv6 wildcard socket を `IPV6_V6ONLY=0` で bind して dual-stack
にする必要がある。

`uvicorn --host ::` だけでは kernel の `bindv6only` 設定次第になり、Railway の
コンテナ環境では IPv4 側が受けられず public edge から 502 が返るケースが
あったため、socket を事前に明示生成して uvicorn には `fd` 経由で渡す。

ローカル / docker-compose 開発では docker-compose.override.yml の command が
`uvicorn ... --host 0.0.0.0` で CMD を完全置換するため、この launcher は
触られない (= 既存挙動を壊さない)。
"""

from __future__ import annotations

import os
import socket

import uvicorn


def _build_dual_stack_socket(port: int) -> socket.socket:
    sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    # IPV6_V6ONLY=0 で IPv4-mapped IPv6 (::ffff:0.0.0.0/96) も受ける。
    # kernel default は 0 のはずだが、コンテナ環境では 1 で来るケースが
    # あるため明示的に 0 を強制する。
    sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
    sock.bind(("::", port))
    sock.listen(socket.SOMAXCONN)
    return sock


def main() -> None:
    port = int(os.environ.get("PORT", "8000"))
    sock = _build_dual_stack_socket(port)
    uvicorn.run(
        "app.main:app",
        fd=sock.fileno(),
        log_level="info",
        access_log=True,
    )


if __name__ == "__main__":
    main()
