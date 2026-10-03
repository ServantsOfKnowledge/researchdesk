#!/usr/bin/env bash
# Everyday commands for SOK Research Desk (Docker or native install).  ./resdesk.sh help
set -euo pipefail
cd "$(dirname "$0")"
# Coolify and similar hosts: no .env here, the containers have their own names
[ "${1:-}" = coolify ] && { shift; exec bash scripts/coolify.sh "$@"; }
[ -f .env ] || { echo "No .env found. Run ./install.sh first."; exit 1; }
set -a; . ./.env; set +a
SITE="${SITE_NAME:-resdesk.localhost}"
MODE="${INSTALL_MODE:-docker}"
compose_files() { # compose_files DEV_MODE HTTPS → the Compose files for this install
  local f=compose.yaml
  [ "$1" = 1 ] && f="$f:compose.dev.yaml"
  [ "$2" = 1 ] && f="$f:compose.https.yaml"
  echo "$f"
}

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
  # and HTTPS (./resdesk.sh https on): the Let's Encrypt proxy
  if [ -z "${COMPOSE_FILE:-}" ]; then export COMPOSE_FILE; COMPOSE_FILE=$(compose_files "${DEV_MODE:-0}" "${HTTPS:-0}")
  elif [ "${HTTPS:-0}" = 1 ]; then
    case ":$COMPOSE_FILE:" in *:compose.https.yaml:*) ;; *) export COMPOSE_FILE="$COMPOSE_FILE:compose.https.yaml" ;; esac
  fi
  bench() { docker compose exec -T backend bench --site "$SITE" "$@"; }
  bench_tty() { docker compose exec backend bench --site "$SITE" "$@"; }
fi

set_env() { # set_env KEY VALUE  (in .env)
  if grep -q "^$1=" .env; then sed -i.bak "s#^$1=.*#$1=$2#" .env && rm -f .env.bak; else echo "$1=$2" >> .env; fi
}
profile_on() {  # add a Docker Compose profile (monitor, updater) to COMPOSE_PROFILES in .env
  local now=",${COMPOSE_PROFILES:-},"
  case "$now" in *",$1,"*) ;; *) now="$now$1," ;; esac
  now="$(echo "$now" | sed 's/^,*//; s/,*$//; s/,,*/,/g')"
  set_env COMPOSE_PROFILES "$now"; export COMPOSE_PROFILES="$now"
}
profile_off() {
  local now=",${COMPOSE_PROFILES:-},"
  now="$(echo "${now//,$1,/,}" | sed 's/^,*//; s/,*$//; s/,,*/,/g')"
  set_env COMPOSE_PROFILES "$now"; export COMPOSE_PROFILES="$now"
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

  count)    bench resdesk count "$@" ;;
  ingest)   bench resdesk ingest "$@" ;;
  progress) bench resdesk progress "$@" ;;
  reindex)  bench resdesk reindex "$@" ;;
  configure) bench resdesk configure "$@" ;;
  access)   bench resdesk access "$@" ;;
  add-reader) bench resdesk add-reader "$@" ;;
  jobs)     bench resdesk jobs "$@" ;;
  screenshots) python3 scripts/screenshots.py --url "http://localhost:${HTTP_PORT:-8080}" "$@" ;;
  docs)     python3 scripts/gen_docs.py "$@" ;;
  requirements)
    # what the server has and what is missing; install tools on native installs (docs/server.md#requirements)
    if [ "${1:-}" = install ]; then bash scripts/requirements.sh "$@"; else bench resdesk requirements; fi ;;

  resources)
    # Caps for the background workers, search engine and database (docs/operations.md#resources)
    RES_KEYS="QUEUE_WORKERS WORKERS_PER_CONTAINER QUEUE_CPUS QUEUE_MEMORY WORKER_NICE MEILI_CPUS MEILI_MEMORY MEILI_MAX_INDEXING_THREADS MEILI_MAX_INDEXING_MEMORY MEILI_MAX_BATCHED_TASKS DB_CPUS DB_MEMORY DB_BUFFER_POOL GUNICORN_WORKERS"
    preset_values() {
      case "$1" in
        light)    echo "QUEUE_WORKERS=1 QUEUE_CPUS=1 QUEUE_MEMORY=1g MEILI_CPUS=1 MEILI_MEMORY=1g MEILI_MAX_INDEXING_THREADS=1 MEILI_MAX_INDEXING_MEMORY=256Mb DB_CPUS=1 DB_MEMORY=1g DB_BUFFER_POOL=256M GUNICORN_WORKERS=2" ;;
        standard) echo "QUEUE_WORKERS=2 QUEUE_CPUS=1 QUEUE_MEMORY=1536m MEILI_CPUS=2 MEILI_MEMORY=2g MEILI_MAX_INDEXING_THREADS=2 MEILI_MAX_INDEXING_MEMORY=1Gb DB_CPUS=1 DB_MEMORY=1536m DB_BUFFER_POOL=512M GUNICORN_WORKERS=2" ;;
        server)   echo "QUEUE_WORKERS=4 QUEUE_CPUS=2 QUEUE_MEMORY=2g MEILI_CPUS=0 MEILI_MEMORY=0 MEILI_MAX_INDEXING_THREADS= MEILI_MAX_INDEXING_MEMORY= DB_CPUS=0 DB_MEMORY=0 DB_BUFFER_POOL=2G GUNICORN_WORKERS=4" ;;
        *) return 1 ;;
      esac
    }
    show_resources() {
      set -a; . ./.env; set +a
      echo "Preset: ${RESOURCES_PRESET:-standard (default)}"
      printf "  %-28s %s\n" "Background workers" "${QUEUE_WORKERS:-2}$([ "${WORKERS_PER_CONTAINER:-1}" -gt 1 ] 2>/dev/null && echo " containers × ${WORKERS_PER_CONTAINER} workers") (each container up to ${QUEUE_CPUS:-0} CPU, ${QUEUE_MEMORY:-0} memory; priority nice ${WORKER_NICE:-19})"
      printf "  %-28s %s\n" "Search engine (Meilisearch)" "${MEILI_CPUS:-0} CPU, ${MEILI_MEMORY:-0} memory; indexing threads ${MEILI_MAX_INDEXING_THREADS:-auto}, indexing memory ${MEILI_MAX_INDEXING_MEMORY:-auto}"
      printf "  %-28s %s\n" "Database (MariaDB)" "${DB_CPUS:-0} CPU, ${DB_MEMORY:-0} memory; buffer pool ${DB_BUFFER_POOL:-256M}"
      printf "  %-28s %s\n" "Web server" "${GUNICORN_WORKERS:-2} gunicorn workers"
      echo "  (0 = no limit)"
      if [ "$MODE" = native ]; then
        echo; echo "Native install: CPU and memory caps don't apply; workers, priority and search-indexing limits do."
        echo; ps -eo pcpu,pmem,rss,comm --sort=-pcpu 2>/dev/null | head -8 || ps -Ao pcpu,pmem,rss,comm | head -8
      else
        echo; echo "This machine (as Docker sees it): $(docker info --format '{{.NCPU}} {{.MemTotal}}' 2>/dev/null | awk '{printf "%s CPUs, %.1f GB memory", $1, $2/1073741824}')"
        echo
        # shellcheck disable=SC2046 # one argument per container id
        docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" $(docker compose ps -q 2>/dev/null) 2>/dev/null || true
      fi
      REQ=$(bench resdesk resource-preset 2>/dev/null | tail -1 || true)
      if [ -n "$REQ" ] && [ "$REQ" != "${RESOURCES_PRESET:-}" ]; then
        echo; echo "Chosen in the Desk: $REQ. Apply it with: ./resdesk.sh resources apply"
      fi
    }
    check_fit() { # warn when the caps add up to more than the machine has
      [ "$MODE" = native ] && return 0
      set -a; . ./.env; set +a
      NCPU=$(docker info --format '{{.NCPU}}' 2>/dev/null || echo 0)
      python3 - "$NCPU" "${QUEUE_WORKERS:-2}" "${QUEUE_CPUS:-0}" "${MEILI_CPUS:-0}" "${DB_CPUS:-0}" <<'PY' || true
import sys
n, workers, qc, mc, dc = int(sys.argv[1] or 0), int(sys.argv[2]), float(sys.argv[3] or 0), float(sys.argv[4] or 0), float(sys.argv[5] or 0)
total = workers * qc + mc + dc
if n and qc and mc and dc and total > n:
    print(f"Note: the caps add up to {total:g} CPUs and Docker has {n}. That's allowed (they rarely all peak at once),")
    print("but if the machine feels slow, lower QUEUE_WORKERS or QUEUE_CPUS.")
PY
    }
    apply_resources() {
      set -a; . ./.env; set +a
      if [ "$MODE" = native ]; then
        bash scripts/native-procfile.sh "$BENCH_DIR" "${QUEUE_WORKERS:-2}" "${MEILI_PORT:-7700}" "$MEILI_MASTER_KEY"
        native_stop; native_start
      else
        docker compose up -d --scale queue="${QUEUE_WORKERS:-2}" configurator db meilisearch backend queue scheduler websocket
        docker compose restart frontend >/dev/null   # it looks the web server up again
      fi
      check_fit
      echo "Applied. ./resdesk.sh resources shows the result."
    }
    SUB="${1:-show}"; shift || true
    case "$SUB" in
      show) show_resources ;;
      light|standard|server)
        for kv in $(preset_values "$SUB"); do set_env "${kv%%=*}" "${kv#*=}"; done
        set_env RESOURCES_PRESET "$SUB"
        bench resdesk resource-preset --set "$SUB" >/dev/null 2>&1 || true
        apply_resources ;;
      set)
        [ $# -gt 0 ] || { echo "Usage: ./resdesk.sh resources set KEY=VALUE …   keys: $RES_KEYS"; exit 1; }
        for kv in "$@"; do
          k="${kv%%=*}"; case " $RES_KEYS " in *" $k "*) set_env "$k" "${kv#*=}" ;; *) echo "Unknown setting $k (one of: $RES_KEYS)"; exit 1 ;; esac
        done
        set_env RESOURCES_PRESET custom
        apply_resources ;;
      apply)
        REQ=$(bench resdesk resource-preset 2>/dev/null | tail -1 || true)
        if [ -n "$REQ" ] && preset_values "$REQ" >/dev/null && [ "$REQ" != "${RESOURCES_PRESET:-}" ]; then
          echo "Using the preset chosen in the Desk: $REQ"
          for kv in $(preset_values "$REQ"); do set_env "${kv%%=*}" "${kv#*=}"; done
          set_env RESOURCES_PRESET "$REQ"
        fi
        apply_resources ;;
      monitor)
        [ "$MODE" = native ] && { echo "Only for Docker installs."; exit 1; }
        case "${1:-}" in
          on)  profile_on monitor
               docker compose up -d --no-recreate monitor && echo "Background Jobs → Machine now shows CPU and memory per part." ;;
          off) profile_off monitor; docker compose rm -sf monitor >/dev/null 2>&1 || true; echo "Monitor stopped." ;;
          *)   echo "Usage: ./resdesk.sh resources monitor on|off   (now: ${COMPOSE_PROFILES:-off})"; exit 1 ;;
        esac ;;
      *) echo "Usage: ./resdesk.sh resources [light|standard|server|set KEY=VALUE…|apply|monitor on|off]"; exit 1 ;;
    esac ;;

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
           export COMPOSE_FILE; COMPOSE_FILE=$(compose_files 1 "${HTTPS:-0}")
           docker compose up -d
           docker compose exec -T backend bench --site "$SITE" set-config developer_mode 1
           docker compose restart backend queue scheduler && docker compose restart frontend
           echo "Developer mode ON: code is read live from $(pwd)" ;;
      off) set_env DEV_MODE 0
           docker compose exec -T backend bench --site "$SITE" set-config developer_mode 0 || true
           export COMPOSE_FILE; COMPOSE_FILE=$(compose_files 0 "${HTTPS:-0}")
           docker compose build
           docker compose up -d
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

  url)      . scripts/https.sh; rd_url "$@" ;;
  https)    . scripts/https.sh; rd_https "$@" ;;
  export)   . scripts/move.sh; rd_export "$@" ;;
  import)   . scripts/move.sh; rd_import "$@" ;;
  move-to)  . scripts/move.sh; rd_move_to "$@" ;;

  update|upgrade)
    exec ./upgrade.sh "$@" ;;

  updater)
    # The updater helper: lets the Server page in the Desk upgrade, restart and back up (docs/server.md)
    case "${1:-status}" in
      on)
        TOKEN="$(python3 -c 'import secrets; print(secrets.token_hex(32))' 2>/dev/null || openssl rand -hex 32)"
        set_env RESDESK_AGENT_TOKEN "$TOKEN"
        bench set-config resdesk_agent_token "$TOKEN" >/dev/null
        if [ "$MODE" = native ]; then
          set_env UPDATER 1; export UPDATER=1
          bash scripts/native-procfile.sh "$BENCH_DIR" "${QUEUE_WORKERS:-2}" "${MEILI_PORT:-7700}" "$MEILI_MASTER_KEY"
          native_stop; native_start
        else
          RESDESK_DIR="$(pwd)"; export RESDESK_DIR; set_env RESDESK_DIR "$RESDESK_DIR"
          if [ "$(uname -s)" = Linux ]; then  # write files in this folder as you, not as root
            SOCK="${DOCKER_SOCKET:-/var/run/docker.sock}"
            set_env RESDESK_UID "$(id -u)"; set_env RESDESK_GID "$(id -g)"
            set_env DOCKER_GID "$(stat -c %g "$SOCK" 2>/dev/null || echo 0)"
            set -a; . ./.env; set +a
          fi
          profile_on updater
          docker compose build updater
          docker compose up -d --no-deps updater
        fi
        echo "Updater helper on. The Server page in the Desk (/app/resdesk-server) can now upgrade,"
        echo "restart and back up this install. Turn it off with: ./resdesk.sh updater off" ;;
      off)
        set_env RESDESK_AGENT_TOKEN ""
        bench set-config resdesk_agent_token "" >/dev/null || true
        if [ "$MODE" = native ]; then
          set_env UPDATER 0; export UPDATER=0
          bash scripts/native-procfile.sh "$BENCH_DIR" "${QUEUE_WORKERS:-2}" "${MEILI_PORT:-7700}" "$MEILI_MASTER_KEY"
          native_stop; native_start
        else
          profile_off updater
          docker compose rm -sf updater >/dev/null 2>&1 || true
        fi
        echo "Updater helper off. The Server page still shows everything; upgrades are done here with ./upgrade.sh." ;;
      status)
        if [ -z "${RESDESK_AGENT_TOKEN:-}" ]; then echo "Updater helper: off (turn on: ./resdesk.sh updater on)"; exit 0; fi
        if [ "$MODE" = native ]; then pgrep -f "scripts/agent.py" >/dev/null && echo "Updater helper: running" || echo "Updater helper: on, but not running (./resdesk.sh restart)"
        else docker compose ps updater; echo; docker compose logs --tail 10 updater; fi ;;
      *) echo "Usage: ./resdesk.sh updater on|off|status"; exit 1 ;;
    esac ;;

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
SOK Research Desk — everyday commands  (this install: $MODE)

  ./resdesk.sh start | stop | restart | status
  ./resdesk.sh logs [name]              follow logs (Docker: backend, queue…; native: bench-start, worker, web…)

Choosing and ingesting books
  ./resdesk.sh count  --collection ServantsOfKnowledge --filter "language:kan"
  ./resdesk.sh ingest --collection ServantsOfKnowledge --filter "language:kan" --limit 100
  ./resdesk.sh ingest --query 'creator:(Kuvempu) AND mediatype:texts' --limit 50 --name "Kuvempu"
  ./resdesk.sh ingest --ids "id1,id2,id3"
  ./resdesk.sh ingest --folder /library-source            (IA-style item folders in LIBRARY_DIR)
  ./resdesk.sh ingest --server https://books.example.org/items/
  ./resdesk.sh ingest --metadata-file /library-source/sok.jsonl.gz --limit 0 --background
                                                         (a metadata export put in LIBRARY_DIR: fastest)
  ./resdesk.sh ingest --profile "SOK Kannada sample"
  ./resdesk.sh ingest --folder /library-source/staff --visibility members   (who can see the new books)
      options: --no-fulltext  --update  --limit 0 (= everything)  --background

Who can see what (details: docs/access.md)
  ./resdesk.sh access                   who can see what (settings + counts)
  ./resdesk.sh access login-to-read --collection X
        (visibility: public | login-to-read | members; --profile, --language, --ids, --all)
  ./resdesk.sh access --guests "Login required"      (or "Records only", "Each item's setting")
  ./resdesk.sh add-reader EMAIL [--name "Full Name"]  create a reader account

Maintenance
  ./resdesk.sh jobs                     what is running in the background (Desk: /app/resdesk-jobs)
  ./resdesk.sh jobs --stop-all [--now]  stop all ingests and queued jobs, pause schedules
  ./resdesk.sh jobs --stop RUN | --pause | --resume      (schedules)
  ./resdesk.sh jobs --pause-run RUN | --resume-run RUN  pause a run where it is, carry on later
  ./resdesk.sh jobs --pause-all | --resume-all          pause everything, then carry on
  ./resdesk.sh screenshots [--query WORDS]  retake the pictures used in the guides (needs Playwright)
  ./resdesk.sh docs [--check]           refresh the settings and command reference in docs/
  ./resdesk.sh progress [RUN]           watch an ingest run
  ./resdesk.sh resources [light|standard|server]  how much of the machine Research Desk may use
  ./resdesk.sh resources set QUEUE_CPUS=1.5 …     fine-tune one cap (see docs/operations.md)
  ./resdesk.sh resources monitor on|off            CPU/memory per part on Background Jobs (Docker)
  ./resdesk.sh workers <n>              number of parallel ingest workers (default 2)
  ./resdesk.sh reindex [--background] [--no-pages] [--reset]
  ./resdesk.sh backup                   database + files into ./site-backups
  ./resdesk.sh restore <file.sql.gz>    restore a database backup, then re-index
  ./resdesk.sh url [https://NEW.ADDRESS]      show or change the address the portal uses
  ./resdesk.sh https on DOMAIN [--email E]    HTTPS with a free Let's Encrypt certificate (also: status, renew, off)
  ./resdesk.sh export [FILE]            everything needed to move this install, in one file
  ./resdesk.sh import FILE [--base-url URL]   load an export into this (new) install
  ./resdesk.sh move-to USER@HOST [--with-library]   export, copy over SSH and import in one go
  ./resdesk.sh coolify import FILE          on a Coolify server: load an export (also: list, export, bench)
  ./resdesk.sh update [v0.4.0]          upgrade (same as ./upgrade.sh; --check to just look)
  ./resdesk.sh updater on|off|status    let the Server page in the Desk upgrade, restart and back up
  ./resdesk.sh requirements             how well this server is equipped: every tool, found or missing
  ./resdesk.sh requirements install python|ocr   install Python packages, or Tesseract + models (native)
  ./resdesk.sh password [new]           reset the Administrator password
  ./resdesk.sh dev on|off               developer mode (Docker); native is always live
  ./resdesk.sh console | shell | bench …  for developers
  ./resdesk.sh uninstall                remove everything (asks first)
EOF
    ;;
esac
