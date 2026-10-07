#!/usr/bin/env bash
# ---------------------------------------------------------------------------
#  SOK Research Desk — upgrade an existing install (Docker or native)
#
#  ./upgrade.sh              upgrade to the latest release (asks before starting)
#  ./upgrade.sh v0.4.0       upgrade (or roll back) to a specific release
#  ./upgrade.sh --main       upgrade to the newest code on the main branch
#  ./upgrade.sh --check      only report whether an update is available
#  options: --yes (don't ask)  --no-backup  --no-frappe (keep Frappe as it is)
#           --gentle (Docker: restart only what the release needs, and the background
#           workers one at a time, each finishing its job first; UPGRADE_GENTLE=1 in .env
#           makes it the default)
#
#  What it does: backup → fetch new code → update Frappe (patch releases
#  within v16) → rebuild → database migrations → search-index settings →
#  restart → health check. Logs go to logs/upgrade-<date>.log.
#  The Server page in the Desk runs this too, through the updater helper.
# ---------------------------------------------------------------------------
set -euo pipefail
# Run from a copy: the upgrade replaces this very file, and bash reads scripts as it goes.
if [ -z "${RESDESK_UPGRADE_DIR:-}" ]; then
  RESDESK_UPGRADE_DIR="$(cd "$(dirname "$0")" && pwd)"; export RESDESK_UPGRADE_DIR
  COPY="$(mktemp "${TMPDIR:-/tmp}/resdesk-upgrade.XXXXXX")"
  cp "$0" "$COPY"
  exec bash "$COPY" "$@"
fi
cd "$RESDESK_UPGRADE_DIR"
case "$0" in */resdesk-upgrade.*) trap 'rm -f "$0"' EXIT ;; esac
APP_DIR="$(pwd)"

YES=0; CHECK=0; BACKUP=1; FRAPPE=1; TARGET=""; USE_MAIN=0; GENTLE=0
for arg in "$@"; do
  case "$arg" in
    -y|--yes) YES=1 ;;
    --check) CHECK=1 ;;
    --no-backup) BACKUP=0 ;;
    --no-frappe) FRAPPE=0 ;;
    --gentle) GENTLE=1 ;;
    --main) USE_MAIN=1 ;;
    -h|--help) sed -n '2,19p' "$0"; exit 0 ;;
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
[ "${UPGRADE_GENTLE:-0}" = 1 ] && GENTLE=1
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
bold "SOK Research Desk upgrade ($MODE install)"
echo "  Installed:  v$CURRENT_VER ($CURRENT_REF)"
echo "  Target:     $TARGET_LABEL"
if [ "$(git rev-parse HEAD)" = "$TARGET_SHA" ]; then
  ok "Already up to date."
  [ "$CHECK" = 1 ] && exit 0
  [ "$YES" = 1 ] || { read -r -p "  Re-run migrations and a health check anyway? [y/N]: " a || true; [[ "${a:-N}" =~ ^[Yy] ]] || exit 0; }
  export FORCE_MIGRATE=1   # asked for: migrate even though the code is the same
else
  echo
  if git merge-base --is-ancestor "$TARGET_SHA" HEAD 2>/dev/null; then
    echo "  Going back to an earlier release. Only the code goes back: if that release can't read"
    echo "  the database as it is now, restore the backup made before the upgrade you are undoing."
  else
    echo "  What's new:"
    git log --no-merges --format='    • %s' "HEAD..$TARGET_SHA" 2>/dev/null | head -20 || true
  fi
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
  BACKUP_FILE="$(ls -t site-backups/*-database.sql.gz 2>/dev/null | head -1 || true)"
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

# -- Frappe goes with the app when the release needs a newer one ------------------------------
# Each release says which Frappe it needs (__frappe_min__ in sok_resdesk/__init__.py). When the
# installed Frappe is older, Frappe is updated together with the app, whatever --no-frappe says.
frappe_min() { sed -n 's/^__frappe_min__ = "\(.*\)"/\1/p' sok_resdesk/__init__.py; }
frappe_have() {
  if [ "$MODE" = native ]; then
    sed -n 's/^__version__ = "\(.*\)"/\1/p' "${BENCH_DIR:-$HOME/researchdesk-bench}/apps/frappe/frappe/__init__.py" 2>/dev/null
  else
    docker run --rm --entrypoint cat "${RESDESK_IMAGE:-sok-resdesk}:${RESDESK_TAG:-local}" \
      apps/frappe/frappe/__init__.py 2>/dev/null | sed -n 's/^__version__ = "\(.*\)"/\1/p'
  fi
}
NEED_MIN="$(frappe_min || true)"
if [ -n "$NEED_MIN" ]; then
  HAVE_NOW="$(frappe_have || true)"
  if [ -n "$HAVE_NOW" ] && [ "$(printf '%s\n%s\n' "$NEED_MIN" "$HAVE_NOW" | sort -V | head -1)" != "$NEED_MIN" ]; then
    [ "$FRAPPE" = 0 ] && warn "Not keeping Frappe as it is: this release needs Frappe $NEED_MIN or newer"
    FRAPPE=1
    ok "This release needs Frappe $NEED_MIN or newer (here: $HAVE_NOW): Frappe is updated with it"
  fi
fi

# -- what needs restarting (--gentle, Docker) -----------------------------------------------------
# The database, Redis and the search engine are never restarted by an upgrade unless their image
# changes. --gentle also spares the background workers (running ingests and page-text sending)
# when nothing they run has changed, and otherwise restarts them one at a time.
PLAN=full
if [ "$GENTLE" = 1 ]; then
  if [ "$MODE" = native ]; then
    warn "--gentle is for Docker installs; a native install is restarted as a whole"
  elif [ -f scripts/upgrade-plan.sh ]; then
    . scripts/upgrade-plan.sh
    PLAN_LINE="$(git diff --name-only "$PREV_SHA" HEAD | upgrade_plan)"
    PLAN="${PLAN_LINE%%:*}"
    ok "Gentle upgrade, ${PLAN_LINE}"
  else
    warn "--gentle needs scripts/upgrade-plan.sh, which this release does not have: restarting everything"
  fi
fi

# -- 3–4. apply ------------------------------------------------------------------------------
if [ "$MODE" = native ]; then
  BENCH_DIR="${BENCH_DIR:-$HOME/researchdesk-bench}"
  export PATH="$HOME/.local/bin:$PATH"
  if [ -s "$HOME/.nvm/nvm.sh" ]; then set +u; . "$HOME/.nvm/nvm.sh" >/dev/null; nvm use 24 >/dev/null 2>&1 || true; set -u; fi
  bold "3/5  Frappe and dependencies"
  ./resdesk.sh stop >/dev/null || true
  cd "$BENCH_DIR"
  FRAPPE_BEFORE="$(cd apps/frappe && git rev-parse HEAD 2>/dev/null || true)"
  if [ "$FRAPPE" = 1 ]; then
    BR="$(cd apps/frappe && git rev-parse --abbrev-ref HEAD)"
    REMOTE="$(cd apps/frappe && git remote | head -1 || true)"
    (cd apps/frappe && git fetch --quiet "$REMOTE" "$BR" && git merge --quiet --ff-only FETCH_HEAD) \
      && ok "Frappe $(cd apps/frappe && git describe --tags --abbrev=0 2>/dev/null) ($BR)" \
      || warn "Frappe not updated (local changes or no network); continuing with the current version"
  fi
  # Only what changed: Frappe's Python and Node packages when Frappe moved, this app's when its
  # pyproject.toml did (boto3, for S3 second copies)
  FRAPPE_CHANGED=0
  [ "$(cd apps/frappe && git rev-parse HEAD 2>/dev/null || true)" != "$FRAPPE_BEFORE" ] && FRAPPE_CHANGED=1
  if [ "$FRAPPE_CHANGED" = 1 ]; then
    bench setup requirements frappe >/dev/null   # frappe only: our app (any git remote) is installed below
    ok "Frappe's Python and Node packages"
  else
    ok "Frappe unchanged: its packages are already installed"
  fi
  if ! (cd "$APP_DIR" && git diff --quiet "$PREV_SHA" HEAD -- pyproject.toml) || [ ! -e env/bin/python ]; then
    uv pip install --python env/bin/python -e apps/sok_resdesk >/dev/null
    ok "Research Desk's Python package"
  fi
  bold "4/5  Database migrations and assets"
  # migrations need Redis and Meilisearch up
  redis-server config/redis_cache.conf --daemonize yes >/dev/null
  redis-server config/redis_queue.conf --daemonize yes >/dev/null
  meilisearch --db-path "$BENCH_DIR/meili-data" --http-addr "127.0.0.1:${MEILI_PORT:-7700}" --master-key "$MEILI_MASTER_KEY" \
    --no-analytics --env production >> logs/meilisearch.log 2>&1 &
  MEILI_PID=$!; sleep 2
  if [ "${FORCE_MIGRATE:-0}" != 1 ] && WHY="$(BENCH_DIR="$BENCH_DIR" env/bin/python -m sok_resdesk.core.schema check "$SITE")"; then
    ok "No migrate needed: $WHY"
  else
    bench --site "$SITE" migrate --skip-search-index
  fi
  bench --site "$SITE" execute sok_resdesk.search.setup_indexes >/dev/null || warn "Search index settings will be applied on the next ingest"
  if [ "$FRAPPE_CHANGED" = 1 ]; then bench build >/dev/null; else bench build --app sok_resdesk >/dev/null; fi
  redis-cli -p "$(awk '/^port/{print $2}' config/redis_cache.conf)" shutdown nosave >/dev/null 2>&1 || true
  redis-cli -p "$(awk '/^port/{print $2}' config/redis_queue.conf)" shutdown nosave >/dev/null 2>&1 || true
  kill "$MEILI_PID" 2>/dev/null || true
  cd "$APP_DIR"
  bash scripts/native-procfile.sh "$BENCH_DIR" "${QUEUE_WORKERS:-2}" "${MEILI_PORT:-7700}" "$MEILI_MASTER_KEY"
  ok "Migrated and rebuilt"
  ./resdesk.sh start
else
  if [ -z "${COMPOSE_FILE:-}" ]; then
    COMPOSE_FILE=compose.yaml
    [ "${DEV_MODE:-0}" = 1 ] && COMPOSE_FILE="$COMPOSE_FILE:compose.dev.yaml"
    [ "${HTTPS:-0}" = 1 ] && COMPOSE_FILE="$COMPOSE_FILE:compose.https.yaml"
    export COMPOSE_FILE
  elif [ "${HTTPS:-0}" = 1 ]; then
    case ":$COMPOSE_FILE:" in *:compose.https.yaml:*) ;; *) export COMPOSE_FILE="$COMPOSE_FILE:compose.https.yaml" ;; esac
  fi
  bold "3/5  Container image"
  # A build needs several GB; a full Docker disk corrupts config files and stops containers.
  FREE_KB=$(docker run --rm --entrypoint df "${RESDESK_IMAGE:-sok-resdesk}:${RESDESK_TAG:-local}" -Pk / 2>/dev/null | awk 'NR==2{print $4}' || true)
  if [ -n "$FREE_KB" ] && [ "$FREE_KB" -lt 6000000 ]; then
    warn "Docker has only $((FREE_KB / 1024 / 1024)) GB free; an upgrade needs about 6 GB."
    echo "      Free space (your data is not touched):  docker builder prune -af ; docker image prune -f"
    echo "      Docker Desktop: Settings → Resources → Disk usage limit can also be raised."
    false
  fi
  if [ -n "${RESDESK_IMAGE:-}" ]; then
    docker compose pull
  else
    # Frappe: rebuild it (10 minutes or more) only when a newer v16 *release* is out than the one
    # in the image; otherwise the cached build is used and only Research Desk itself is rebuilt
    if [ "$FRAPPE" = 1 ]; then
      MAJOR="${FRAPPE_BRANCH:-version-16}"; MAJOR="${MAJOR#version-}"
      LATEST="$( (git ls-remote --tags --refs https://github.com/frappe/frappe "refs/tags/v${MAJOR}.*" 2>/dev/null || true) \
        | sed 's#.*refs/tags/##' | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' | sort -V | tail -1)"
      HAVE="$(docker run --rm --entrypoint cat "${RESDESK_IMAGE:-sok-resdesk}:${RESDESK_TAG:-local}" \
        apps/frappe/frappe/__init__.py 2>/dev/null | sed -n 's/^__version__ = "\(.*\)"/v\1/p' || true)"
      if [ -z "$LATEST" ]; then
        warn "Could not ask GitHub for Frappe's newest release; keeping Frappe ${HAVE:-as it is}"
      elif [ -n "$HAVE" ] && [ "$(printf '%s\n%s\n' "$LATEST" "$HAVE" | sort -V | tail -1)" = "$HAVE" ]; then
        ok "Frappe $HAVE is the newest release: no rebuild needed"
      else
        if grep -q '^FRAPPE_COMMIT=' .env; then sed -i.bak "s#^FRAPPE_COMMIT=.*#FRAPPE_COMMIT=$LATEST#" .env && rm -f .env.bak
        else echo "FRAPPE_COMMIT=$LATEST" >> .env; fi
        export FRAPPE_COMMIT="$LATEST"
        [ "$PLAN" = full ] || { PLAN=full; warn "Frappe is rebuilt, so everything is restarted"; }
        ok "Frappe ${HAVE:-?} → $LATEST: rebuilding Frappe (10 minutes or more, only for a new Frappe release)"
      fi
    else
      ok "Frappe kept as it is (--no-frappe)"
    fi
    docker compose build
  fi
  docker compose pull db redis-cache redis-queue meilisearch --quiet 2>/dev/null || true
  docker image prune -f >/dev/null 2>&1 || true   # drop the previous build's layers (never touches your data)
  ok "Images ready"
  bold "4/5  Restart and migrate"
  show_containers() {
    echo; docker compose ps -a --format 'table {{.Service}}\t{{.State}}\t{{.Status}}' || true
    for s in configurator create-site backend; do
      echo "  --- last lines from $s:"; docker compose logs --no-color --tail 25 "$s" 2>&1 | sed 's/^/    /' || true
    done
  }
  # `docker compose up` waits for the one-shot configurator to succeed; if it keeps failing
  # (restart: on-failure) compose would wait forever, so watch it and give up with details.
  UP_SERVICES=""
  if [ "$PLAN" != full ]; then
    # everything except the workers, which are dealt with after the web part answers
    UP_SERVICES="$(docker compose config --services 2>/dev/null | grep -vx queue | tr '\n' ' ')"
    ok "Restarting the web part only; the workers keep running for now"
  fi
  # shellcheck disable=SC2086
  docker compose up -d --remove-orphans $UP_SERVICES &
  UP_PID=$!
  UP_OK=0
  for i in $(seq 1 120); do
    if ! kill -0 "$UP_PID" 2>/dev/null; then
      if wait "$UP_PID"; then UP_OK=1; fi
      break
    fi
    CFG=$(docker compose ps -a -q configurator 2>/dev/null || true)
    RESTARTS=$( [ -n "$CFG" ] && docker inspect -f '{{.RestartCount}}' "$CFG" 2>/dev/null || echo 0)
    if [ "${RESTARTS:-0}" -ge 3 ]; then
      kill "$UP_PID" 2>/dev/null || true
      echo; warn "The configurator container keeps failing (it has restarted $RESTARTS times)."
      break
    fi
    sleep 5
  done
  if [ "$UP_OK" != 1 ]; then
    kill "$UP_PID" 2>/dev/null || true
    [ "$i" -ge 120 ] && { echo; warn "Docker has not finished starting the containers after 10 minutes."; }
    warn "Docker could not start the containers."
    show_containers
    echo "  Free Docker disk space if it is full: docker system df ; docker image prune -f ; docker builder prune -f"
    false
  fi
  printf "  waiting for migrations"
  MIGRATED=0
  for i in $(seq 1 180); do
    CID=$(docker compose ps -a -q create-site 2>/dev/null || true)
    STATE=$( [ -n "$CID" ] && docker inspect -f '{{.State.Status}} {{.State.ExitCode}}' "$CID" 2>/dev/null || echo none)
    case "$STATE" in
      "exited 0") echo
        if docker compose logs --no-color --tail 30 create-site 2>/dev/null | grep "exists:" | tail -1 | grep -q "no migrate needed"; then
          ok "Database already up to date: no migrate needed"
        else ok "Database migrated"; fi
        MIGRATED=1; break ;;
      exited*) echo; docker compose logs --tail 40 create-site; false ;;
      created*|none) [ "$i" -gt 24 ] && { echo; warn "The migration container never started."; show_containers; false; } ;;
    esac
    printf "."; sleep 5
  done
  [ "$MIGRATED" = 1 ] || { echo; warn "Migrations are still running after 15 minutes."; show_containers; false; }
  docker compose exec -T backend bench --site "$SITE" execute sok_resdesk.search.setup_indexes >/dev/null || warn "Search index settings will be applied on the next ingest"
fi

# -- 5. health check -------------------------------------------------------------------------
bold "5/5  Health check"
PORT="${HTTP_PORT:-8080}"
# the updater helper runs this inside Docker, where the portal is at http://frontend:8080
BASE="${RESDESK_HEALTH_URL:-http://localhost:$PORT}"
for _ in $(seq 1 40); do curl -fs -o /dev/null "$BASE/library" && break; sleep 3; done
curl -fs -o /dev/null "$BASE/library" && ok "Portal answers on http://localhost:$PORT/library" || { warn "Portal is not answering"; false; }
STATS="$(curl -fs "$BASE/api/method/sok_resdesk.api.stats" || true)"
echo "$STATS" | grep -q '"search":"ok"' && ok "Search engine OK" || warn "Search engine not answering yet: check ./resdesk.sh logs"
# -- the workers (--gentle) -----------------------------------------------------------------------
if [ "$MODE" != native ] && [ "$PLAN" = web ]; then
  ok "Workers left running: nothing they run has changed"
elif [ "$MODE" != native ] && [ "$PLAN" = roll ]; then
  bold "Workers, one at a time"
  GRACE="${UPGRADE_WORKER_GRACE:-1200}"   # seconds a worker may take to finish its job
  trap - ERR; set +e
  NQ="$(docker compose ps -q queue 2>/dev/null | wc -l | tr -d ' ')"
  if [ "${NQ:-0}" -lt 1 ]; then
    docker compose up -d --no-deps queue >/dev/null 2>&1 && ok "Workers started"
  else
    for CID in $(docker compose ps -q queue 2>/dev/null); do
      WNAME="$(docker inspect -f '{{.Name}}' "$CID" 2>/dev/null | sed 's#^/##')"
      echo "  stopping $WNAME (it finishes the job it is on, up to $((GRACE / 60)) minutes)"
      docker stop -t "$GRACE" "$CID" >/dev/null 2>&1
      docker rm "$CID" >/dev/null 2>&1
      if docker compose up -d --no-deps --no-recreate --scale queue="$NQ" queue >/dev/null 2>&1; then
        ok "$WNAME replaced by one running the new version"
      else
        warn "Could not start a replacement worker: run  docker compose up -d queue"
        break
      fi
    done
  fi
  set -e; trap 'rollback_hint' ERR
fi
trap - ERR
echo
bold "Upgraded to v$(version_here) 🎉"
echo "  Previous version: $PREV_SHA   Backup: ${BACKUP_FILE:-none}   Log: $LOG"
if git log --format=%B "$PREV_SHA..HEAD" 2>/dev/null | grep -q "NEEDS-REINDEX"; then
  warn "This release changes the search index: run ./resdesk.sh reindex --reset --background"
fi
exit 0
