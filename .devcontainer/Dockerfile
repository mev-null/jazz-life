# Devcontainer workspace image.
# - base: Debian bookworm + Python 3.11 + common dev tools (git/sudo/zsh/vscode user)
# - added: Node.js + uv + make
# The Docker CLI is provided by the docker-in-docker feature declared in devcontainer.json.
FROM mcr.microsoft.com/devcontainers/python:3.11-bookworm

ARG NODE_VERSION=20

RUN curl -fsSL https://deb.nodesource.com/setup_${NODE_VERSION}.x | bash - \
 && apt-get install -y --no-install-recommends nodejs make \
 && rm -rf /var/lib/apt/lists/*

# uv: install to /usr/local/bin so every user can run it
RUN curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh
