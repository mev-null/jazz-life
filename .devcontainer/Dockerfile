# Devcontainer workspace image.
# - base: Debian bookworm + Python 3.11 + 一般的な dev tools (git/sudo/zsh/vscode user)
# - 追加: Node.js + uv + make
# Docker CLI は docker-outside-of-docker feature が入れる (ホスト daemon と通信)。
FROM mcr.microsoft.com/devcontainers/python:3.11-bookworm

ARG NODE_VERSION=20

RUN curl -fsSL https://deb.nodesource.com/setup_${NODE_VERSION}.x | bash - \
 && apt-get install -y --no-install-recommends nodejs make \
 && rm -rf /var/lib/apt/lists/*

# uv: /usr/local/bin に置いて全ユーザから使えるようにする
RUN curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh
