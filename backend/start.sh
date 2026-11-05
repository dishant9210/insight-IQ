#!/usr/bin/env bash
# Migrate, then serve. With RUN_WORKER=true and a REDIS_URL, the ingest worker
# runs in the same container: it reads uploads from the api's disk, so on Fly
# (one machine, one volume) it has to sit beside the api. In compose the
# worker is its own service and this just starts the api.
set -euo pipefail

alembic upgrade head

if [[ "${RUN_WORKER:-false}" != "true" || -z "${REDIS_URL:-}" ]]; then
  exec uvicorn app.main:app --host 0.0.0.0 --port 8000
fi

# the worker forks per job, so its metrics go through files, on their own port
PROMETHEUS_MULTIPROC_DIR=/tmp/worker-metrics METRICS_PORT="${WORKER_METRICS_PORT:-9092}" \
  python -m app.worker &
uvicorn app.main:app --host 0.0.0.0 --port 8000 &

stopping=0
trap 'stopping=1; kill -TERM $(jobs -p) 2>/dev/null || true' TERM INT

# whichever exits first takes the other down, so the platform restarts both
wait -n || true
kill -TERM $(jobs -p) 2>/dev/null || true
wait || true
if [[ $stopping -eq 0 ]]; then
  echo "start.sh: a process exited on its own; stopping" >&2
  exit 1
fi
