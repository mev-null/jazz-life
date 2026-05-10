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

EXPOSE 8000

# dev では docker-compose.override.yml で --reload を付与する
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
