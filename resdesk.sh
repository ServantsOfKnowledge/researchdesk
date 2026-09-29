#!/usr/bin/env bash
# Everyday commands for SoK Research Desk (Docker or native install).  ./resdesk.sh help
set -euo pipefail
cd "$(dirname "$0")"
[ -f .env ] || { echo "No .env found. Run ./install.sh first."; exit 1; }
set -a; . ./.env; set +a
SITE="${SITE_NAME:-resdesk.localhost}"
APP_DIR="$(pwd)"
MODE="${INSTALL_MODE:-docker}"

if [ "$MODE" = native ]; then
  BENCH_DIR="${BENCH_DIR:-$HOME/researchdesk-bench}"
  export PATH="$HOME/.local/bin:$PATH"
  if [ -s "$HOME/.nvm/nvm.sh" ]; then set +u; . "$HOME/.nvm/nvm.sh" >/dev/null; nvm use 24 >/dev/null 2>&1 || true; set -u; fi
  [ -d "$BENCH_DIR/apps/frappe" ] || { echo "Bench not found at $BENCH_DIR. Run ./install.sh --native."; exit 1; }
  PIDFILE="$BENCH_DIR/resdesk.pid"
  bench() { (cd "$BENCH_DIR" && command bench --site "$SITE" "$@"); }
  bench_tty() { bench "$@"; }
  running() { [ -f "$PIDFILE" ] && ps -p "$(cat "$PIDFILE")" -o command= 2>/dev/null | grep -Eq "(bench|honcho) start"; }
  native_start() {
    if running; then echo "Already running (pid $(cat "$PIDFILE"))."; return; fi
    BENCH_BIN="$(command -v bench)"
    (cd "$BENCH_DIR" || exit 1; nohup "$BENCH_BIN" start < /dev/null > logs/bench-start.log 2>&1 & echo $! > "$PIDFILE")
    printf "Starting"
    for _ in $(seq 1 60); do
      curl -fs -o /dev/null "http://localhost:${HTTP_PORT:-8000}/library" 2>/dev/null && { echo " up: http://localhost:${HTTP_PORT:-8000}/library"; return; }
      printf "."; sleep 2
    done
    echo; echo "Still starting. Check: ./resdesk.sh logs"
  }
  kill_tree() { # stop a process and everything it started (works on macOS and Linux)
    local child
    for child in $(pgrep -P "$1" 2>/dev/null); do kill_tree "$child"; done
    kill -TERM "$1" 2>/dev/null || true
  }
  native_stop() {
    if running; then
      PID="$(cat "$PIDFILE")"
      kill_tree "$PID"
      for _ in $(seq 1 20); do kill -0 "$PID" 2>/dev/null || break; sleep 1; done
      echo "Stopped."
    else
      echo "Not running."
    fi
    rm -f "$PIDFILE"
  }
else
  # Developer mode (./resdesk.sh dev on): use this folder's code live inside the containers
  if [ "${DEV_MODE:-0}" = 1 ] && [ -z "${COMPOSE_FILE:-}" ]; then export COMPOSE_FILE=compose.yaml:compose.dev.yaml; fi
  bench() { docker compose exec -T backend bench --site "$SITE" "$@"; }
  bench_tty() { docker compose exec backend bench --site "$SITE" "$@"; }
fi

set_env() { # set_env KEY VALUE  (in .env)
  if grep -q "^$1=" .env; then sed -i.bak "s#^$1=.*#$1=$2#" .env && rm -f .env.bak; else echo "$1=$2" >> .env; fi
}

cmd="${1:-help}"; shift || true
case "$cmd" in
  start)    if [ "$MODE" = native ]; then native_start; else docker compose up -d; fi ;;
  stop)     if [ "$MODE" = native ]; then native_stop; else docker compose stop; fi ;;
  restart)  if [ "$MODE" = native ]; then native_stop; native_start; else docker compose restart; fi ;;
  status)
    if [ "$MODE" = native ]; then
      running && echo "Running natively (pid $(cat "$PIDFILE")), bench at $BENCH_DIR" || echo "Not running (./resdesk.sh start)"
    else docker compose ps; fi
    echo; bench resdesk status ;;
  logs)
    if [ "$MODE" = native ]; then tail -n 100 -f "$BENCH_DIR/logs/${1:-bench-start}.log"
    else docker compose logs -f --tail 100 "${@:-backend}"; fi ;;
  url)      echo "http://localhost:${HTTP_PORT:-8080}/library" ;;

  count)    bench resdesk count "$@" ;;
  ingest)   bench resdesk ingest "$@" ;;
  progress) bench resdesk progress "$@" ;;
  reindex)  bench resdesk reindex "$@" ;;
  configure) bench resdesk configure "$@" ;;
  access)   bench resdesk access "$@" ;;
  add-reader) bench resdesk add-reader "$@" ;;

  workers)
    N="${1:-}"; [[ "$N" =~ ^[0-9]+$ ]] && [ "$N" -ge 1 ] || { echo "Usage: ./resdesk.sh workers <number>   (now: ${QUEUE_WORKERS:-2})"; exit 1; }
    set_env QUEUE_WORKERS "$N"
    if [ "$MODE" = native ]; then
      bash scripts/native-procfile.sh "$BENCH_DIR" "$N" "${MEILI_PORT:-7700}" "$MEILI_MASTER_KEY"
      native_stop; native_start
    else
      QUEUE_WORKERS=$N docker compose up -d --no-recreate --scale queue="$N" queue
    fi
    echo "Now running $N ingest worker(s)." ;;

  dev)
    if [ "$MODE" = native ]; then
      # Native installs always run this folder's code (it is linked into the bench).
      # dev on = auto-reloading web server + developer_mode; off = gunicorn.
      case "${1:-}" in
        on)  set_env NATIVE_DEV 1; export NATIVE_DEV=1; bench set-config developer_mode 1 >/dev/null ;;
        off) set_env NATIVE_DEV 0; export NATIVE_DEV=0; bench set-config developer_mode 0 >/dev/null ;;
        *)   echo "Developer mode is $([ "${NATIVE_DEV:-0}" = 1 ] && echo ON || echo OFF). Usage: ./resdesk.sh dev on|off"; exit 0 ;;
      esac
      bash scripts/native-procfile.sh "$BENCH_DIR" "${QUEUE_WORKERS:-2}" "${MEILI_PORT:-7700}" "$MEILI_MASTER_KEY"
      native_stop; native_start
      echo "Developer mode $1 (code is always read from $(pwd); Python changes need ./resdesk.sh restart unless dev is on)."
      exit 0
    fi
    case "${1:-}" in
      on)  set_env DEV_MODE 1
           COMPOSE_FILE=compose.yaml:compose.dev.yaml docker compose up -d
           COMPOSE_FILE=compose.yaml:compose.dev.yaml docker compose exec -T backend bench --site "$SITE" set-config developer_mode 1
           COMPOSE_FILE=compose.yaml:compose.dev.yaml docker compose restart backend queue scheduler && COMPOSE_FILE=compose.yaml:compose.dev.yaml docker compose restart frontend
           echo "Developer mode ON: code is read live from $(pwd)" ;;
      off) set_env DEV_MODE 0
           docker compose exec -T backend bench --site "$SITE" set-config developer_mode 0 || true
           COMPOSE_FILE=compose.yaml docker compose build
           COMPOSE_FILE=compose.yaml docker compose up -d
           echo "Developer mode OFF: running the code baked into the image" ;;
      *)   echo "Developer mode is $([ "${DEV_MODE:-0}" = 1 ] && echo ON || echo OFF). Usage: ./resdesk.sh dev on|off" ;;
    esac ;;

  console)  bench_tty console ;;
  shell)    if [ "$MODE" = native ]; then cd "$BENCH_DIR" && exec "${SHELL:-bash}"; else docker compose exec backend bash; fi ;;
  bench)    bench_tty "$@" ;;
  migrate)  bench migrate ;;

  backup)
    mkdir -p site-backups
    if [ "$MODE" = native ]; then
      bench backup --with-files
      cp -p "$BENCH_DIR/sites/$SITE/private/backups/"* site-backups/
    else
      # Only the database is needed, so this works even when the web containers won't start.
      docker compose up -d db redis-cache redis-queue
      printf "Waiting for the database"
      for _ in $(seq 1 60); do
        DB_CID=$(docker compose ps -q db 2>/dev/null || true)
        [ -n "$DB_CID" ] && [ "$(docker inspect -f '{{.State.Health.Status}}' "$DB_CID" 2>/dev/null)" = healthy ] && break
        printf "."; sleep 3
      done
      echo
      [ "$(docker inspect -f '{{.State.Health.Status}}' "${DB_CID:-none}" 2>/dev/null)" = healthy ] \
        || { docker compose logs --tail 30 db; echo "The database container is not healthy (see above), so no backup was made."; exit 1; }
      if [ -n "$(docker compose ps -q --status running backend 2>/dev/null)" ]; then
        run_in() { docker compose exec -T backend "$@"; }
      else
        echo "The backend container isn't running; making the backup with a one-off container."
        run_in() { docker compose run --rm --no-deps -T backend "$@"; }
      fi
      run_in bench --site "$SITE" backup --with-files
      DIR="sites/$SITE/private/backups"
      for f in $(run_in bash -c "cd $DIR && ls -t | head -4"); do
        run_in cat "$DIR/$f" > "site-backups/$f"
      done
    fi
    echo "Backups copied to ./site-backups (search index is rebuilt with: ./resdesk.sh reindex)" ;;

  restore)
    F="${1:-}"; [ -f "$F" ] || { echo "Usage: ./resdesk.sh restore site-backups/<...>-database.sql.gz"; exit 1; }
    read -r -p "Replace the current catalogue with $F? [y/N]: " a; [[ "$a" =~ ^[Yy] ]] || exit 0
    if [ "$MODE" = native ]; then
      TARGET="$(cd "$(dirname "$F")" && pwd)/$(basename "$F")"
    else
      docker compose cp "$F" backend:/tmp/restore.sql.gz
      docker compose exec -T -u root backend chown frappe /tmp/restore.sql.gz
      TARGET=/tmp/restore.sql.gz
    fi
    bench --force restore "$TARGET" --db-root-password "$DB_ROOT_PASSWORD"
    bench migrate
    echo "Restored. Rebuilding the search index in the foreground (Ctrl+C to skip; run ./resdesk.sh reindex later)…"
    bench resdesk reindex ;;

  update|upgrade)
    exec ./upgrade.sh "$@" ;;

  password)
    NEW="${1:-}"; [ -n "$NEW" ] || { read -r -s -p "New Administrator password: " NEW; echo; }
    bench set-admin-password "$NEW" && echo "Updated. (Remember to update ADMIN_PASSWORD in .env if you rely on it.)" ;;

  uninstall)
    if [ "$MODE" = native ]; then
      read -r -p "Delete the site, its database and $BENCH_DIR? Your book folders are not touched. Type 'delete': " a
      [ "$a" = "delete" ] || { echo "Cancelled."; exit 0; }
      native_stop
      (cd "$BENCH_DIR" && command bench drop-site "$SITE" --db-root-password "$DB_ROOT_PASSWORD" --force --no-backup) || true
      rm -rf "$BENCH_DIR" && sed -i.bak '/^INSTALL_MODE=/d;/^BENCH_DIR=/d' .env && rm -f .env.bak
      echo "Removed. (MariaDB, Redis and Meilisearch themselves stay installed.)"
    else
      read -r -p "Delete ALL Research Desk containers AND data (catalogue, search index)? Type 'delete': " a
      [ "$a" = "delete" ] && docker compose down -v && echo "Removed." || echo "Cancelled."
    fi ;;

  help|*)
    cat <<EOF
SoK Research Desk — everyday commands  (this install: $MODE)

  ./resdesk.sh start | stop | restart | status
  ./resdesk.sh logs [name]              follow logs (Docker: backend, queue…; native: bench-start, worker, web…)
  ./resdesk.sh url                      print the portal address

Choosing and ingesting books
  ./resdesk.sh count  --collection ServantsOfKnowledge --filter "language:kan"
  ./resdesk.sh ingest --collection ServantsOfKnowledge --filter "language:kan" --limit 100
  ./resdesk.sh ingest --query 'creator:(Kuvempu) AND mediatype:texts' --limit 50 --name "Kuvempu"
  ./resdesk.sh ingest --ids "id1,id2,id3"
  ./resdesk.sh ingest --folder /library-source            (IA-style item folders in LIBRARY_DIR)
  ./resdesk.sh ingest --server https://books.example.org/items/
  ./resdesk.sh ingest --profile "SoK Kannada sample"
  ./resdesk.sh ingest --folder /library-source/staff --visibility members   (who can see the new books)
      options: --no-fulltext  --update  --limit 0 (= everything)  --background

Who can see what (details: docs/access.md)
  ./resdesk.sh access                   who can see what (settings + counts)
  ./resdesk.sh access login-to-read --collection X
        (visibility: public | login-to-read | members; --profile, --language, --ids, --all)
  ./resdesk.sh access --guests "Login required"      (or "Records only", "Each item's setting")
  ./resdesk.sh add-reader EMAIL [--name "Full Name"]  create a reader account

Maintenance
  ./resdesk.sh progress [RUN]           watch an ingest run
  ./resdesk.sh workers <n>              number of parallel ingest workers (default 2)
  ./resdesk.sh reindex [--background] [--no-pages] [--reset]
  ./resdesk.sh backup                   database + files into ./site-backups
  ./resdesk.sh restore <file.sql.gz>    restore a database backup, then re-index
  ./resdesk.sh update [v0.4.0]          upgrade (same as ./upgrade.sh; --check to just look)
  ./resdesk.sh password [new]           reset the Administrator password
  ./resdesk.sh dev on|off               developer mode (Docker); native is always live
  ./resdesk.sh console | shell | bench …  for developers
  ./resdesk.sh uninstall                remove everything (asks first)
EOF
    ;;
esac
