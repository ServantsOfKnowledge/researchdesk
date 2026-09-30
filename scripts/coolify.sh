#!/usr/bin/env bash
# Research Desk deployed by Coolify (or any tool that runs compose.yaml under its own project
# name and container names): finds its containers and runs export, import and bench against
# them. Run it on the server, from a clone of the Research Desk repository (no .env needed):
#
#   ./resdesk.sh coolify list                                  Research Desk installs on this server
#   ./resdesk.sh coolify import FILE [--base-url URL] [--yes]  load an export (./resdesk.sh export)
#   ./resdesk.sh coolify export [FILE]                         make one, e.g. to move away again
#   ./resdesk.sh coolify bench ARGS...                         a bench command on the site
#
# With more than one install on the server, add --project ID (from `list`).
# See docs/installation.md#coolify and docs/moving.md.
set -euo pipefail
cd "$(dirname "$0")/.."

PROJECT=""
REST=()
while [ $# -gt 0 ]; do
  case "$1" in
    --project) PROJECT="${2:-}"; shift 2 ;;
    *) REST+=("$1"); shift ;;
  esac
done
set -- ${REST[@]+"${REST[@]}"}
CMD="${1:-help}"; [ $# -gt 0 ] && shift

usage() { sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; }
command -v docker >/dev/null || { echo "Docker isn't installed here: run this on the server Coolify deploys to."; exit 1; }

projects() { # Compose projects that have a Research Desk backend
  docker ps -a --filter label=com.docker.compose.service=backend \
    --format '{{.Label "com.docker.compose.project"}} {{.Names}}' 2>/dev/null |
    while read -r p name; do
      docker exec "$name" test -d apps/sok_resdesk 2>/dev/null && echo "$p" || true
    done | sort -u
}
ctr() { # ctr SERVICE → the container's name in $PROJECT
  docker ps -a --filter "label=com.docker.compose.project=$PROJECT" \
    --filter "label=com.docker.compose.service=$1" --format '{{.Names}}' | head -1
}
ctr_env() { # ctr_env CONTAINER KEY
  [ -n "$1" ] || return 0
  docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$1" 2>/dev/null | sed -n "s/^$2=//p" | head -1
}

if [ "$CMD" = help ] || [ "$CMD" = -h ] || [ "$CMD" = --help ]; then usage; exit 0; fi

if [ "$CMD" = list ]; then
  found=0
  for p in $(projects); do
    found=1; PROJECT="$p"; b=$(ctr backend)
    printf "%-28s backend %-40s %-9s %s\n" "$p" "$b" "$(docker inspect -f '{{.State.Status}}' "$b")" \
      "$(ctr_env "$(ctr create-site)" BASE_URL)"
  done
  [ "$found" = 1 ] || echo "No Research Desk containers on this server. Deploy it in Coolify first."
  exit 0
fi

if [ -z "$PROJECT" ]; then
  ALL=()
  while read -r p; do [ -n "$p" ] && ALL+=("$p"); done < <(projects)
  case "${#ALL[@]}" in
    0) echo "No Research Desk containers on this server. Deploy it in Coolify first (and wait for it to start)."; exit 1 ;;
    1) PROJECT="${ALL[0]}" ;;
    *) echo "More than one Research Desk here; choose one with --project:"; printf "  %s\n" "${ALL[@]}"; exit 1 ;;
  esac
fi
BACKEND_CTR=$(ctr backend)
[ -n "$BACKEND_CTR" ] || { echo "No backend container in project $PROJECT."; exit 1; }

# the settings live in the containers' environment (Coolify's Environment Variables)
SITE=$(docker exec "$BACKEND_CTR" cat sites/currentsite.txt 2>/dev/null | tr -d '\r\n' || true)
[ -n "$SITE" ] || SITE=$(ctr_env "$(ctr create-site)" SITE_NAME)
SITE="${SITE:-resdesk.localhost}"
DB_ROOT_PASSWORD=$(ctr_env "$(ctr db)" MARIADB_ROOT_PASSWORD)
MEILI_MASTER_KEY=$(ctr_env "$(ctr meilisearch)" MEILI_MASTER_KEY)
BASE_URL=$(ctr_env "$(ctr create-site)" BASE_URL)
MODE=container
UPGRADE_HINT="redeploy the latest release in Coolify"
PASSWORD_HINT="./resdesk.sh coolify bench set-admin-password NEW-PASSWORD"
export MODE SITE BACKEND_CTR

bench() { docker exec $([ -t 0 ] && [ -t 1 ] && echo -it) "$BACKEND_CTR" bench --site "$SITE" "$@"; }
set_env() { :; }   # no .env here: settings are Coolify's Environment Variables
restart_containers() {
  local s c
  for s in backend queue scheduler websocket frontend; do
    for c in $(docker ps -q --filter "label=com.docker.compose.project=$PROJECT" --filter "label=com.docker.compose.service=$s"); do
      docker restart "$c" >/dev/null
    done
  done
}

echo "Research Desk in $PROJECT (site $SITE, container $BACKEND_CTR)"
case "$CMD" in
  bench) bench "$@" ;;
  export) . scripts/move.sh; rd_export "$@" ;;
  import)
    [ -n "$DB_ROOT_PASSWORD" ] || { echo "Can't read the database password from the db container."; exit 1; }
    # the address set in Coolify, unless given
    case " $* " in *" --base-url "*) ;; *) [ -n "$BASE_URL" ] && set -- "$@" --base-url "$BASE_URL" ;; esac
    . scripts/move.sh; rd_import "$@" ;;
  *) usage; exit 1 ;;
esac
