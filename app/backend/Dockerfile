FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/usr/local

WORKDIR /app

RUN pip install --no-cache-dir uv

# Resolve dependencies first: copy pyproject.toml and uv.lock before the source so the layer cache is reused
COPY pyproject.toml ./
COPY uv.lock* ./
RUN uv sync --no-dev --frozen 2>/dev/null || uv sync --no-dev

# Application code
COPY app ./app
COPY alembic.ini ./
COPY migrations ./migrations
COPY entrypoint.sh ./
RUN chmod +x ./entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
# Start uvicorn through a launcher that listens dual-stack (IPv4 + IPv6).
# On Railway, edge -> container traffic arrives over IPv4 while service-to-service
# private networking arrives over IPv6, so both must be accepted. `uvicorn --host ::`
# alone depends on the kernel's `bindv6only` setting; in Railway containers that left
# IPv4 unreachable and produced 502s, so the socket is pre-bound with `IPV6_V6ONLY=0`
# and handed over by fd. See the docstring in app/server.py for details.
#
# Locally / under docker-compose the override replaces CMD entirely (exec form), so
# this launcher is not used there (existing behaviour is unchanged).
CMD ["python", "-m", "app.server"]
