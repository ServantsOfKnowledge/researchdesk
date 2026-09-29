#!/usr/bin/env bash
# ---------------------------------------------------------------------------
#  Developer setup with bench (no Docker for the app itself).
#
#  Prerequisites (see docs/installation.md#developer-setup-bench):
#    Python 3.14, Node 24 + yarn, MariaDB 11.x, Redis, wkhtmltopdf (optional),
#    frappe-bench (pip install frappe-bench), and Meilisearch
#    (brew install meilisearch  |  or: docker run -p 7700:7700 getmeili/meilisearch:v1.54)
#
#  Usage:
#    scripts/dev-setup.sh [bench-dir] [site-name]
#    defaults:           ~/frappe-bench  resdesk.localhost
# ---------------------------------------------------------------------------
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BENCH_DIR="${1:-$HOME/frappe-bench}"
SITE="${2:-resdesk.localhost}"
FRAPPE_BRANCH="${FRAPPE_BRANCH:-version-16}"
MEILI_URL="${MEILI_URL:-http://127.0.0.1:7700}"
MEILI_KEY="${MEILI_KEY:-}"
DB_ROOT_PASSWORD="${DB_ROOT_PASSWORD:-}"

need() { command -v "$1" >/dev/null 2>&1 || { echo "Missing: $1. $2"; exit 1; }; }
need bench "pip install frappe-bench"
need node "Install Node 24 (nvm install 24)"
need yarn "npm install -g yarn"
command -v mariadb >/dev/null 2>&1 || echo "Note: MariaDB client not found; make sure a MariaDB 11.x server is running."
command -v redis-server >/dev/null 2>&1 || echo "Note: redis-server not found; bench start needs Redis."

if [ ! -d "$BENCH_DIR" ]; then
  echo ">> Creating bench at $BENCH_DIR (Frappe $FRAPPE_BRANCH)"
  bench init --frappe-branch "$FRAPPE_BRANCH" "$BENCH_DIR"
fi
cd "$BENCH_DIR"

if [ ! -e "apps/sok_resdesk" ]; then
  echo ">> Linking the app from $APP_DIR"
  ln -s "$APP_DIR" apps/sok_resdesk
  ./env/bin/python -m pip install -e apps/sok_resdesk 2>/dev/null || uv pip install --python env/bin/python -e apps/sok_resdesk
  grep -qx sok_resdesk sites/apps.txt || { sed -i.bak -e '$a\' sites/apps.txt; echo sok_resdesk >> sites/apps.txt; rm -f sites/apps.txt.bak; }
fi

if [ ! -d "sites/$SITE" ]; then
  echo ">> Creating site $SITE"
  ROOT_ARGS=()
  [ -n "$DB_ROOT_PASSWORD" ] && ROOT_ARGS=(--db-root-password "$DB_ROOT_PASSWORD")
  bench new-site "$SITE" --admin-password admin "${ROOT_ARGS[@]}"
  bench --site "$SITE" set-config resdesk_meili_url "$MEILI_URL"
  [ -n "$MEILI_KEY" ] && bench --site "$SITE" set-config resdesk_meili_key "$MEILI_KEY"
  bench --site "$SITE" install-app sok_resdesk
  bench --site "$SITE" execute sok_resdesk.setup.complete_setup_wizard
  bench --site "$SITE" set-config developer_mode 1
  bench --site "$SITE" set-config allow_tests true
fi
bench use "$SITE"
bench build --app sok_resdesk

cat <<EOF

Ready. Start everything with:
  cd $BENCH_DIR && bench start

Then open http://$SITE:8000/library  (add "127.0.0.1 $SITE" to /etc/hosts if needed)
Login: Administrator / admin

Try an ingest:
  bench --site $SITE resdesk ingest --collection ServantsOfKnowledge --filter "language:kan" --limit 20
Run tests:
  bench --site $SITE run-tests --app sok_resdesk
  (cd $APP_DIR && pytest)
EOF
