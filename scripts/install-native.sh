#!/usr/bin/env bash
# ---------------------------------------------------------------------------
#  SOK Research Desk: native install (no Docker)
#
#  Installs everything directly on this computer:
#    MariaDB, Redis, Meilisearch, Python 3.14 (via uv), Node 24 (via nvm),
#    frappe-bench, then a Frappe v16 "bench" with Research Desk in it.
#
#  Supported: macOS (Homebrew) and Ubuntu 22.04+/Debian 12+ (apt).
#  Normally run through:   ./install.sh --native
#
#  Re-running is safe: finished steps are skipped.
# ---------------------------------------------------------------------------
set -euo pipefail
APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$APP_DIR"

YES=${YES:-0}
bold() { printf "\033[1m%s\033[0m\n" "$*"; }
ok()   { printf "  \033[32m✓\033[0m %s\n" "$*"; }
warn() { printf "  \033[33m!\033[0m %s\n" "$*"; }
die()  { printf "\n  \033[31m✗ %s\033[0m\n\n" "$*"; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

set -a; . ./.env; set +a
BENCH_DIR="${BENCH_DIR:-$HOME/researchdesk-bench}"
SITE="${SITE_NAME:-resdesk.localhost}"
HTTP_PORT="${HTTP_PORT:-8000}"
FRAPPE_BRANCH="${FRAPPE_BRANCH:-version-16}"
MEILI_PORT="${MEILI_PORT:-7700}"
LIBRARY_DIR="${LIBRARY_DIR:-$APP_DIR/library}"
case "$LIBRARY_DIR" in /*) ;; *) LIBRARY_DIR="$APP_DIR/${LIBRARY_DIR#./}";; esac

OS="$(uname -s)"
SUDO=""; [ "$(id -u)" -ne 0 ] && SUDO="sudo"

# 1. System packages ------------------------------------------------------------
bold "1/6  System packages"
if [ "$OS" = "Darwin" ]; then
  have brew || die "Homebrew is required on macOS. Install it from https://brew.sh and run this again."
  brew list --versions mariadb >/dev/null 2>&1 || brew install mariadb
  for p in redis meilisearch pkg-config git tesseract tesseract-lang poppler; do brew list --versions "$p" >/dev/null 2>&1 || brew install "$p"; done
  MYSQL_CNF_DIR="$(brew --prefix)/etc/my.cnf.d"
  ok "Homebrew packages: mariadb, redis, meilisearch, pkg-config, tesseract, poppler"
elif [ -f /etc/debian_version ]; then
  $SUDO apt-get update -qq
  $SUDO env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    git curl ca-certificates build-essential pkg-config libmariadb-dev mariadb-server mariadb-client \
    redis-server xvfb libfontconfig1 cron tesseract-ocr poppler-utils \
    $(if [ "${OCR_LANGS:-all}" = all ]; then echo tesseract-ocr-all; else for l in $OCR_LANGS; do echo "tesseract-ocr-$l"; done; fi) \
    >/dev/null   # OCR models: every language (OCR_LANGS=all), or the books' languages
  MYSQL_CNF_DIR=/etc/mysql/mariadb.conf.d
  if ! have meilisearch; then
    ARCH="$(uname -m)"; case "$ARCH" in x86_64) M=amd64;; aarch64|arm64) M=aarch64;; *) die "Unsupported CPU $ARCH";; esac
    curl -fsSL -o /tmp/meilisearch "https://github.com/meilisearch/meilisearch/releases/download/v1.54.1/meilisearch-linux-$M"
    $SUDO install -m 755 /tmp/meilisearch /usr/local/bin/meilisearch
  fi
  ok "apt packages + Meilisearch $(meilisearch --version 2>/dev/null | awk '{print $2}')"
else
  die "Native install supports macOS and Ubuntu/Debian. On other systems use Docker: ./install.sh"
fi

# 2. Python 3.14 (uv), Node 24 (nvm), bench ----------------------------------------------
bold "2/6  Python, Node and bench"
if ! have uv; then
  curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null
  export PATH="$HOME/.local/bin:$PATH"
fi
uv python install 3.14 >/dev/null
PY314="$(uv python find 3.14)"
ok "Python $("$PY314" --version | awk '{print $2}') ($PY314)"

export NVM_DIR="$HOME/.nvm"
if [ ! -s "$NVM_DIR/nvm.sh" ]; then
  curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | PROFILE=/dev/null bash >/dev/null
fi
set +u  # nvm reads unset variables
# shellcheck disable=SC1091
. "$NVM_DIR/nvm.sh"
nvm install 24 >/dev/null && nvm alias default 24 >/dev/null && nvm use 24 >/dev/null
set -u
have yarn || npm install -g yarn >/dev/null
ok "Node $(node --version), yarn $(yarn --version)"

have bench || uv tool install frappe-bench >/dev/null
export PATH="$HOME/.local/bin:$PATH"
ok "bench $(bench --version 2>/dev/null)"

# 3. MariaDB ---------------------------------------------------------------------------
bold "3/6  Database (MariaDB)"
$SUDO mkdir -p "$MYSQL_CNF_DIR"
cat <<EOF | $SUDO tee "$MYSQL_CNF_DIR/99-researchdesk.cnf" >/dev/null
[mysqld]
character-set-client-handshake = FALSE
character-set-server = utf8mb4
collation-server = utf8mb4_unicode_ci

[mysql]
default-character-set = utf8mb4
EOF
if [ "$OS" = "Darwin" ]; then
  brew services restart mariadb >/dev/null
else
  $SUDO systemctl enable --now mariadb >/dev/null 2>&1 || $SUDO service mariadb restart
  $SUDO systemctl restart mariadb >/dev/null 2>&1 || true
fi
for _ in $(seq 1 30); do $SUDO mariadb -e "select 1" >/dev/null 2>&1 && break; sleep 1; done
# Frappe logs in as root with a password; keep socket login for the admin too.
if ! mariadb -uroot -p"$DB_ROOT_PASSWORD" -e "select 1" >/dev/null 2>&1; then
  $SUDO mariadb -e "ALTER USER 'root'@'localhost' IDENTIFIED VIA unix_socket OR mysql_native_password USING PASSWORD('$DB_ROOT_PASSWORD'); FLUSH PRIVILEGES;" \
    || die "Could not set the MariaDB root password. If MariaDB already had one, put it in .env as DB_ROOT_PASSWORD and re-run."
fi
ok "MariaDB ready (utf8mb4, root password from .env)"

# 4. Bench ------------------------------------------------------------------------------
bold "4/6  Frappe bench at $BENCH_DIR (first time: 5–15 minutes)"
if [ ! -d "$BENCH_DIR/apps/frappe" ]; then
  [ -e "$BENCH_DIR" ] && die "$BENCH_DIR exists but is not a Frappe bench. Move it away or set BENCH_DIR in .env."
  bench init --frappe-branch "$FRAPPE_BRANCH" --python "$PY314" "$BENCH_DIR"
fi
cd "$BENCH_DIR"
if [ ! -e apps/sok_resdesk ]; then
  ln -s "$APP_DIR" apps/sok_resdesk
  uv pip install --python env/bin/python -e apps/sok_resdesk >/dev/null
fi
if ! grep -qx sok_resdesk sites/apps.txt; then
  [ -n "$(tail -c1 sites/apps.txt)" ] && echo >> sites/apps.txt
  echo sok_resdesk >> sites/apps.txt
fi
ok "Frappe $(cd apps/frappe && git describe --tags --abbrev=0 2>/dev/null || echo "$FRAPPE_BRANCH") + Research Desk"

# Procfile = what `bench start` runs: web, workers, scheduler, redis, and here also Meilisearch
bench set-config -gp webserver_port "$HTTP_PORT" >/dev/null
bench set-config -gp serve_default_site True >/dev/null
bash "$APP_DIR/scripts/native-procfile.sh" "$BENCH_DIR" "${QUEUE_WORKERS:-2}" "$MEILI_PORT" "$MEILI_MASTER_KEY"
ok "Procfile: web on port $HTTP_PORT, ${QUEUE_WORKERS:-2} worker(s), scheduler, redis, meilisearch"

# 5. Site ---------------------------------------------------------------------------------
bold "5/6  Site $SITE"
# Site setup needs the bench's Redis and Meilisearch; run them just for this step.
redis-server config/redis_cache.conf --daemonize yes >/dev/null
redis-server config/redis_queue.conf --daemonize yes >/dev/null
mkdir -p meili-data logs
meilisearch --db-path "$BENCH_DIR/meili-data" --http-addr "127.0.0.1:$MEILI_PORT" --master-key "$MEILI_MASTER_KEY" \
  --no-analytics --env production >> logs/meilisearch.log 2>&1 &
MEILI_PID=$!
cleanup_services() {
  redis-cli -p "$(awk '/^port/{print $2}' config/redis_cache.conf)" shutdown nosave >/dev/null 2>&1 || true
  redis-cli -p "$(awk '/^port/{print $2}' config/redis_queue.conf)" shutdown nosave >/dev/null 2>&1 || true
  kill "$MEILI_PID" 2>/dev/null || true
}
trap cleanup_services EXIT
sleep 2

site_apps() { bench --site "$SITE" list-apps 2>/dev/null || true; }
if [ -d "sites/$SITE" ] && ! site_apps | grep -q '^frappe'; then
  warn "Found an unfinished site from an earlier attempt; creating it again"
  NEW_SITE_FORCE="--force"
fi
if ! site_apps | grep -q '^frappe'; then
  bench new-site "$SITE" --db-root-username root --db-root-password "$DB_ROOT_PASSWORD" \
    --admin-password "$ADMIN_PASSWORD" --set-default ${NEW_SITE_FORCE:-}
fi
bench --site "$SITE" set-config resdesk_meili_url "http://127.0.0.1:$MEILI_PORT" >/dev/null
bench --site "$SITE" set-config resdesk_meili_key "$MEILI_MASTER_KEY" >/dev/null
bench --site "$SITE" set-config resdesk_portal_title "${PORTAL_TITLE:-SOK Research Desk}" >/dev/null
bench --site "$SITE" set-config resdesk_contact "${CONTACT_EMAIL:-}" >/dev/null
bench --site "$SITE" set-config resdesk_profiles "${RESDESK_PROFILES:-}" >/dev/null
bench --site "$SITE" set-config resdesk_books "${RESDESK_BOOKS:-0}" >/dev/null
bench --site "$SITE" set-config resdesk_repository_id "$SITE" >/dev/null
mkdir -p "$LIBRARY_DIR"
# Profiles keep using /library-source; natively it points at LIBRARY_DIR.
bench --site "$SITE" set-config resdesk_library_dir "$LIBRARY_DIR" >/dev/null
bench --site "$SITE" set-config host_name "${BASE_URL:-http://localhost:$HTTP_PORT}" >/dev/null
if site_apps | grep -q '^sok_resdesk'; then
  bench --site "$SITE" migrate
else
  bench --site "$SITE" install-app sok_resdesk
fi
bench --site "$SITE" execute sok_resdesk.setup.complete_setup_wizard \
  --kwargs "{'timezone': '${TIMEZONE:-Asia/Kolkata}', 'country': '${COUNTRY:-India}', 'currency': '${CURRENCY:-INR}'}" >/dev/null
bench --site "$SITE" enable-scheduler >/dev/null
bench use "$SITE" >/dev/null
bench build --app sok_resdesk >/dev/null
cleanup_services; trap - EXIT
ok "Site ready; library folder: $LIBRARY_DIR"

# 6. Remember the mode for ./resdesk.sh -------------------------------------------------
bold "6/6  Finishing"
cd "$APP_DIR"
for kv in "INSTALL_MODE=native" "BENCH_DIR=$BENCH_DIR"; do
  k="${kv%%=*}"
  if grep -q "^$k=" .env; then sed -i.bak "s#^$k=.*#$kv#" .env && rm -f .env.bak; else echo "$kv" >> .env; fi
done
ok "Saved INSTALL_MODE=native in .env"
./resdesk.sh start
