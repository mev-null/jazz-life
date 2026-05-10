#!/bin/sh
set -e

# Apply DB migrations on every container start. Idempotent.
alembic upgrade head

# Hand off to whatever command was passed (dev: uvicorn --reload via override,
# prod: the Dockerfile CMD without --reload).
exec "$@"
