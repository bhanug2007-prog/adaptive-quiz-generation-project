#!/usr/bin/env bash
# DEVELOPMENT / TEST ONLY. Runs the backend on a throwaway SQLite file with the fake model server
# (tests/fake_model_server.py) so the UI can be worked on without the real Qwen model, then fills it
# with test data. Questions it produces are canned test strings, not model output.
#
#   scripts/dev_fake_stack.sh [BACKEND_PORT] [MODEL_PORT] [FRONTEND_ORIGIN]
#   SEED=0 scripts/dev_fake_stack.sh ...   starts with an empty database (used by the Playwright test)
#   then: cd ../frontend && VITE_BACKEND_URL=http://127.0.0.1:BACKEND_PORT npx vite --port N
set -euo pipefail
cd "$(dirname "$0")/.."
BPORT="${1:-8000}"
MPORT="${2:-8081}"
ORIGIN="${3:-http://localhost:5173}"
DB="$(mktemp -d)/dev.db"
export ENVIRONMENT=development DATABASE_URL="sqlite:///$DB" MODEL_BASE_URL="http://127.0.0.1:$MPORT" \
  LECTURER_INVITE_CODE=dev-invite REQUIRE_EMAIL_VERIFICATION=false FRONTEND_URL="$ORIGIN" \
  ALLOWED_ORIGINS="$ORIGIN,http://localhost:5173,http://127.0.0.1:5173"
python3 -m tests.fake_model_server --port "$MPORT" --delay 0.2 &
MPID=$!
trap 'kill $MPID $BPID 2>/dev/null || true' EXIT
python3 -m alembic upgrade head >/dev/null 2>&1
python3 -m uvicorn app.main:app --host 127.0.0.1 --port "$BPORT" --log-level warning &
BPID=$!
for _ in $(seq 60); do curl -sf "http://127.0.0.1:$BPORT/api/health" >/dev/null && break; sleep 0.5; done
if [ "${SEED:-1}" != "0" ]; then
  python3 -m scripts.dump_api_samples --live "http://127.0.0.1:$BPORT" --invite dev-invite 2>&1 | grep -v " INFO "
fi
echo "Backend on http://127.0.0.1:$BPORT (fake model on $MPORT, database $DB). Lecturer invite code: dev-invite"
wait $BPID
