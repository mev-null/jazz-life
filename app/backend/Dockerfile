FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/usr/local

WORKDIR /app

RUN pip install --no-cache-dir uv

# 依存解決を先に：pyproject.toml と uv.lock を先にコピーしてレイヤキャッシュを効かせる
COPY pyproject.toml ./
COPY uv.lock* ./
RUN uv sync --no-dev --frozen 2>/dev/null || uv sync --no-dev

# アプリ本体
COPY app ./app
COPY alembic.ini ./
COPY migrations ./migrations
COPY entrypoint.sh ./
RUN chmod +x ./entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
# dual-stack (IPv4 + IPv6) で listen する launcher を経由して uvicorn を起動。
# Railway は edge → container を IPv4 で、service-to-service の private network
# を IPv6 で来るため、両方受ける必要がある。`uvicorn --host ::` だけでは kernel の
# `bindv6only` 設定次第になり、Railway コンテナでは IPv4 が受けられず 502 になる
# 事例があったため、socket を `IPV6_V6ONLY=0` で事前 bind して fd 経由で渡す。
# 詳細は app/server.py の docstring 参照。
#
# ローカル / docker-compose では override が exec 形式で CMD を完全置換するため、
# この launcher は触られない (=既存挙動を維持)。
CMD ["python", "-m", "app.server"]
