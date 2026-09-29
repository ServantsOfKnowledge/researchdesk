#!/usr/bin/env bash
# (Re)writes a native bench's Procfile: Frappe's standard processes, gunicorn as the web
# server (or `bench serve` with auto-reload when NATIVE_DEV=1), Meilisearch and extra
# ingest workers.
#   native-procfile.sh <bench-dir> <workers> <meili-port> <meili-key>
set -euo pipefail
BENCH_DIR="$1"; WORKERS="${2:-2}"; MEILI_PORT="${3:-7700}"; MEILI_KEY="$4"
PORT="${HTTP_PORT:-8000}"
BIND="${BIND_ADDRESS:-0.0.0.0}"
cd "$BENCH_DIR"
rm -f Procfile && bench setup procfile >/dev/null   # regenerates web/socketio/watch/schedule/worker/redis
mkdir -p meili-data logs

# Production-style web server unless developer mode is asked for
if [ "${NATIVE_DEV:-0}" != 1 ]; then
  sed -i.bak '/^web:/d' Procfile && rm -f Procfile.bak
  echo "web: ./env/bin/gunicorn --chdir sites --bind $BIND:$PORT --workers ${GUNICORN_WORKERS:-2} --threads 4 --worker-class gthread --timeout 120 --preload sok_resdesk.native_wsgi:application 1>> logs/web.log 2>> logs/web.error.log" >> Procfile
fi
# The asset watcher is only useful while editing Frappe's JS bundles
sed -i.bak '/^watch:/d' Procfile && rm -f Procfile.bak
{
  echo "meilisearch: meilisearch --db-path $BENCH_DIR/meili-data --http-addr 127.0.0.1:$MEILI_PORT --master-key $MEILI_KEY --no-analytics --env production 1>> logs/meilisearch.log 2>&1"
  for i in $(seq 2 "$WORKERS"); do
    echo "worker_rd$i: bench worker 1>> logs/worker.log 2>> logs/worker.error.log"
  done
} >> Procfile
