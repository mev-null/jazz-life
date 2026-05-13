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
# CMD は shell 形式にして ${PORT} を取り込む。Railway は app に PORT env を
# 注入してくる仕様で、これを無視するとルーティング不整合になりうる。
# ローカル / docker-compose では override が exec 形式 (port 8000 固定) で
# CMD を完全置換するため、この shell 形式は触られない。
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
