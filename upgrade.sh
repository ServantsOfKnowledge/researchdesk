#!/usr/bin/env bash
# ---------------------------------------------------------------------------
#  SoK Research Desk — upgrade an existing install (Docker or native)
#
#  ./upgrade.sh              upgrade to the latest release (asks before starting)
#  ./upgrade.sh v0.4.0       upgrade (or roll back) to a specific release
#  ./upgrade.sh --main       upgrade to the newest code on the main branch
#  ./upgrade.sh --check      only report whether an update is available
#  options: --yes (don't ask)  --no-backup  --no-frappe (native: keep Frappe as is)
#
#  What it does: backup → fetch new code → update Frappe (patch releases
#  within v16) → rebuild → database migrations → search-index settings →
#  restart → health check. Logs go to logs/upgrade-<date>.log.
# ---------------------------------------------------------------------------
set -euo pipefail
cd "$(dirname "$0")"
APP_DIR="$(pwd)"

YES=0; CHECK=0; BACKUP=1; FRAPPE=1; TARGET=""; USE_MAIN=0
for arg in "$@"; do
  case "$arg" in
    -y|--yes) YES=1 ;;
    --check) CHECK=1 ;;
    --no-backup) BACKUP=0 ;;
    --no-frappe) FRAPPE=0 ;;
    --main) USE_MAIN=1 ;;
    -h|--help) sed -n '2,15p' "$0"; exit 0 ;;
    v*|[0-9]*) TARGET="$arg" ;;
    *) echo "Unknown option: $arg"; exit 1 ;;
  esac
done

bold() { printf "\033[1m%s\033[0m\n" "$*"; }
ok()   { printf "  \033[32m✓\033[0m %s\n" "$*"; }
warn() { printf "  \033[33m!\033[0m %s\n" "$*"; }
die()  { printf "\n  \033[31m✗ %s\033[0m\n\n" "$*"; exit 1; }

[ -f .env ] || die "No .env here. Run ./install.sh first."
set -a; . ./.env; set +a
MODE="${INSTALL_MODE:-docker}"
SITE="${SITE_NAME:-resdesk.localhost}"
version_here() { sed -n 's/^__version__ = "\(.*\)"/\1/p' sok_resdesk/__init__.py; }

# -- what is available ---------------------------------------------------------------
[ -d .git ] || die "This folder is not a git checkout, so it can't be upgraded in place. Download the new release and copy your .env into it."
git fetch --quiet --tags origin 2>/dev/null || warn "Could not reach the git remote; using what is already downloaded"
CURRENT_REF="$(git rev-parse --short HEAD)"
CURRENT_VER="$(version_here)"
LATEST_TAG="$(git tag -l 'v*' | sort -V | tail -1)"
if [ "$USE_MAIN" = 1 ]; then TARGET_REF="origin/main"; TARGET_LABEL="main ($(git rev-parse --short origin/main 2>/dev/null || echo '?'))"
elif [ -n "$TARGET" ]; then
  git rev-parse -q --verify "refs/tags/$TARGET" >/dev/null || die "No release called $TARGET. Available: $(git tag -l 'v*' | sort -V | tr '\n' ' ')"
  TARGET_REF="$TARGET"; TARGET_LABEL="$TARGET"
else
  [ -n "$LATEST_TAG" ] || die "No releases (tags) found. Use ./upgrade.sh --main to follow the main branch."
  TARGET_REF="$LATEST_TAG"; TARGET_LABEL="$LATEST_TAG"
fi
TARGET_SHA="$(git rev-parse "$TARGET_REF^{commit}")"

echo
bold "SoK Research Desk upgrade ($MODE install)"
echo "  Installed:  v$CURRENT_VER ($CURRENT_REF)"
echo "  Target:     $TARGET_LABEL"
if [ "$(git rev-parse HEAD)" = "$TARGET_SHA" ]; then
  ok "Already up to date."
  [ "$CHECK" = 1 ] && exit 0
  [ "$YES" = 1 ] || { read -r -p "  Re-run migrations and a health check anyway? [y/N]: " a || true; [[ "${a:-N}" =~ ^[Yy] ]] || exit 0; }
else
  echo
  echo "  What's new:"
  git log --no-merges --format='    • %s' "HEAD..$TARGET_SHA" 2>/dev/null | head -20 || true
  [ "$CHECK" = 1 ] && { echo; echo "  Run ./upgrade.sh to install it."; exit 0; }
fi

if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  git status --short --untracked-files=no | sed 's/^/    /'
  die "This folder has local code changes (listed above). Commit or stash them first (git stash), then re-run."
fi

if [ "$YES" != 1 ]; then
  read -r -p "  Upgrade now? The portal is offline for a few minutes. [Y/n]: " a || true
  [[ "${a:-Y}" =~ ^[Nn] ]] && exit 0
fi

mkdir -p logs
LOG="logs/upgrade-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee -a "$LOG") 2>&1
PREV_SHA="$(git rev-parse HEAD)"
BACKUP_FILE=""
rollback_hint() {
  echo
  warn "The upgrade did not finish. To go back to the previous version:"
  echo "      git checkout $PREV_SHA && ./install.sh $( [ "$MODE" = native ] && echo --native )"
  [ -n "$BACKUP_FILE" ] && echo "      ./resdesk.sh restore $BACKUP_FILE     # only if the database was changed"
  echo "  Full log: $LOG"
}
trap 'rollback_hint' ERR

# -- 1. backup -----------------------------------------------------------------------------
bold "1/5  Backup"
if [ "$BACKUP" = 1 ]; then
  if [ "$MODE" = native ]; then ./resdesk.sh start || true; fi
  trap - ERR; set +e
  ./resdesk.sh backup 2>&1 | sed 's/^/    /'
  rc=${PIPESTATUS[0]}
  set -e; trap 'rollback_hint' ERR
  if [ "$rc" != 0 ]; then
    trap - ERR
    warn "The backup failed (details above), so nothing was changed."
    echo "      Fix the problem shown, or if you already have a recent backup in site-backups/,"
    echo "      run again without one:  ./upgrade.sh --no-backup"
    exit 1
  fi
  BACKUP_FILE="$(ls -t site-backups/*-database.sql.gz 2>/dev/null | head -1)"
  ok "Saved ${BACKUP_FILE:-site-backups/}"
else
  warn "Skipped (--no-backup)"
fi

# -- 2. code ---------------------------------------------------------------------------------
bold "2/5  Research Desk code → $TARGET_LABEL"
BRANCH="$(git symbolic-ref --quiet --short HEAD || true)"
if [ -n "$BRANCH" ] && git merge-base --is-ancestor HEAD "$TARGET_SHA"; then
  git merge --quiet --ff-only "$TARGET_SHA"     # stay on the branch
else
  git checkout --quiet "$TARGET_SHA"            # rollback or a release off the branch
fi
ok "Now at v$(version_here) ($(git rev-parse --short HEAD))"

# -- 3–4. apply ------------------------------------------------------------------------------
if [ "$MODE" = native ]; then
  BENCH_DIR="${BENCH_DIR:-$HOME/researchdesk-bench}"
  export PATH="$HOME/.local/bin:$PATH"
  if [ -s "$HOME/.nvm/nvm.sh" ]; then set +u; . "$HOME/.nvm/nvm.sh" >/dev/null; nvm use 24 >/dev/null 2>&1 || true; set -u; fi
  bold "3/5  Frappe and dependencies"
  ./resdesk.sh stop >/dev/null || true
  cd "$BENCH_DIR"
  if [ "$FRAPPE" = 1 ]; then
    BR="$(cd apps/frappe && git rev-parse --abbrev-ref HEAD)"
    REMOTE="$(cd apps/frappe && git remote | head -1)"
    (cd apps/frappe && git fetch --quiet "$REMOTE" "$BR" && git merge --quiet --ff-only FETCH_HEAD) \
      && ok "Frappe $(cd apps/frappe && git describe --tags --abbrev=0 2>/dev/null) ($BR)" \
      || warn "Frappe not updated (local changes or no network); continuing with the current version"
  fi
  bench setup requirements frappe >/dev/null   # frappe only: our app has no extra requirements and may have any git remote
  uv pip install --python env/bin/python -e apps/sok_resdesk >/dev/null
  ok "Python and Node packages"
  bold "4/5  Database migrations and assets"
  # migrations need Redis and Meilisearch up
  redis-server config/redis_cache.conf --daemonize yes >/dev/null
  redis-server config/redis_queue.conf --daemonize yes >/dev/null
  meilisearch --db-path "$BENCH_DIR/meili-data" --http-addr "127.0.0.1:${MEILI_PORT:-7700}" --master-key "$MEILI_MASTER_KEY" \
    --no-analytics --env production >> logs/meilisearch.log 2>&1 &
  MEILI_PID=$!; sleep 2
  bench --site "$SITE" migrate
  bench --site "$SITE" execute sok_resdesk.search.setup_indexes >/dev/null || warn "Search index settings will be applied on the next ingest"
  bench build >/dev/null
  redis-cli -p "$(awk '/^port/{print $2}' config/redis_cache.conf)" shutdown nosave >/dev/null 2>&1 || true
  redis-cli -p "$(awk '/^port/{print $2}' config/redis_queue.conf)" shutdown nosave >/dev/null 2>&1 || true
  kill "$MEILI_PID" 2>/dev/null || true
  cd "$APP_DIR"
  bash scripts/native-procfile.sh "$BENCH_DIR" "${QUEUE_WORKERS:-2}" "${MEILI_PORT:-7700}" "$MEILI_MASTER_KEY"
  ok "Migrated and rebuilt"
  ./resdesk.sh start
else
  [ "${DEV_MODE:-0}" = 1 ] && [ -z "${COMPOSE_FILE:-}" ] && export COMPOSE_FILE=compose.yaml:compose.dev.yaml
  bold "3/5  Container image"
  if [ -n "${RESDESK_IMAGE:-}" ]; then
    docker compose pull
  else
    docker compose build     # also picks up Frappe patch releases from the version-16 base images
  fi
  docker compose pull db redis-cache redis-queue meilisearch --quiet 2>/dev/null || true
  ok "Images ready"
  bold "4/5  Restart and migrate"
  show_containers() {
    echo; docker compose ps -a --format 'table {{.Service}}\t{{.State}}\t{{.Status}}' || true
    for s in configurator create-site backend; do
      echo "  --- last lines from $s:"; docker compose logs --no-color --tail 25 "$s" 2>&1 | sed 's/^/    /' || true
    done
  }
  docker compose up -d --remove-orphans || { warn "Docker could not start the containers (the error is above)."; show_containers; false; }
  printf "  waiting for migrations"
  MIGRATED=0
  for i in $(seq 1 180); do
    CID=$(docker compose ps -a -q create-site 2>/dev/null || true)
    STATE=$( [ -n "$CID" ] && docker inspect -f '{{.State.Status}} {{.State.ExitCode}}' "$CID" 2>/dev/null || echo none)
    case "$STATE" in
      "exited 0") echo; ok "Database migrated"; MIGRATED=1; break ;;
      exited*) echo; docker compose logs --tail 40 create-site; false ;;
      created*|none) [ "$i" -gt 24 ] && { echo; warn "The migration container never started."; show_containers; false; } ;;
    esac
    printf "."; sleep 5
  done
  [ "$MIGRATED" = 1 ] || { echo; warn "Migrations are still running after 15 minutes."; show_containers; false; }
  ./resdesk.sh bench execute sok_resdesk.search.setup_indexes >/dev/null || warn "Search index settings will be applied on the next ingest"
fi

# -- 5. health check -------------------------------------------------------------------------
bold "5/5  Health check"
PORT="${HTTP_PORT:-8080}"
for _ in $(seq 1 40); do curl -fs -o /dev/null "http://localhost:$PORT/library" && break; sleep 3; done
curl -fs -o /dev/null "http://localhost:$PORT/library" && ok "Portal answers on http://localhost:$PORT/library" || { warn "Portal is not answering"; false; }
STATS="$(curl -fs "http://localhost:$PORT/api/method/sok_resdesk.api.stats" || true)"
echo "$STATS" | grep -q '"search":"ok"' && ok "Search engine OK" || warn "Search engine not answering yet: check ./resdesk.sh logs"
trap - ERR
echo
bold "Upgraded to v$(version_here) 🎉"
echo "  Previous version: $PREV_SHA   Backup: ${BACKUP_FILE:-none}   Log: $LOG"
if git log --format=%B "$PREV_SHA..HEAD" 2>/dev/null | grep -q "NEEDS-REINDEX"; then
  warn "This release changes the search index: run ./resdesk.sh reindex --reset --background"
fi
exit 0
