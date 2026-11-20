#!/bin/sh
set -eu

# Render supplies a driverless PostgreSQL URL. The project uses psycopg 3.
case "$DATABASE_URL" in
    postgresql://*) export DATABASE_URL="postgresql+psycopg://${DATABASE_URL#postgresql://}" ;;
esac

export FRONTEND_URL="${FRONTEND_URL:-$RENDER_EXTERNAL_URL}"
export ALLOWED_ORIGINS="${ALLOWED_ORIGINS:-$FRONTEND_URL}"

python -m alembic upgrade head
exec python -m uvicorn serve:app --host 0.0.0.0 --port "${PORT:-10000}"
