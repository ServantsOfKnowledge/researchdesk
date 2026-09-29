#!/usr/bin/env bash
# Everyday commands for a Docker install of SoK Research Desk.  ./resdesk.sh help
set -euo pipefail
cd "$(dirname "$0")"
[ -f .env ] || { echo "No .env found. Run ./install.sh first."; exit 1; }
set -a; . ./.env; set +a
SITE="${SITE_NAME:-resdesk.localhost}"

bench() { docker compose exec -T backend bench --site "$SITE" "$@"; }
bench_tty() { docker compose exec backend bench --site "$SITE" "$@"; }

cmd="${1:-help}"; shift || true
case "$cmd" in
  start)    docker compose up -d ;;
  stop)     docker compose stop ;;
  restart)  docker compose restart ;;
  status)   docker compose ps; echo; bench resdesk status ;;
  logs)     docker compose logs -f --tail 100 "${@:-backend}" ;;
  url)      echo "http://localhost:${HTTP_PORT:-8080}/library" ;;

  count)    bench resdesk count "$@" ;;
  ingest)   bench resdesk ingest "$@" ;;
  reindex)  bench resdesk reindex "$@" ;;
  configure) bench resdesk configure "$@" ;;

  console)  bench_tty console ;;
  shell)    docker compose exec backend bash ;;
  bench)    bench_tty "$@" ;;
  migrate)  bench migrate ;;

  backup)
    bench backup --with-files
    mkdir -p site-backups
    CID=$(docker compose ps -q backend)
    docker cp "$CID:/home/frappe/frappe-bench/sites/$SITE/private/backups/." site-backups/
    echo "Backups copied to ./site-backups (search index is rebuilt with: ./resdesk.sh reindex)" ;;

  restore)
    F="${1:-}"; [ -f "$F" ] || { echo "Usage: ./resdesk.sh restore site-backups/<...>-database.sql.gz"; exit 1; }
    read -r -p "Replace the current catalogue with $F? [y/N]: " a; [[ "$a" =~ ^[Yy] ]] || exit 0
    docker compose cp "$F" backend:/tmp/restore.sql.gz
    docker compose exec -T -u root backend chown frappe /tmp/restore.sql.gz
    bench --force restore /tmp/restore.sql.gz --db-root-password "$DB_ROOT_PASSWORD"
    bench migrate
    echo "Restored. Rebuilding the search index in the foreground (Ctrl+C to skip; run ./resdesk.sh reindex later)…"
    bench resdesk reindex ;;

  update)
    git pull --ff-only
    if [ -n "${RESDESK_IMAGE:-}" ]; then docker compose pull; else docker compose build; fi
    docker compose up -d
    echo "Migrations run automatically in the create-site container:"; docker compose logs --tail 5 create-site ;;

  password)
    NEW="${1:-}"; [ -n "$NEW" ] || { read -r -s -p "New Administrator password: " NEW; echo; }
    bench set-admin-password "$NEW" && echo "Updated. (Remember to update ADMIN_PASSWORD in .env if you rely on it.)" ;;

  uninstall)
    read -r -p "Delete ALL Research Desk containers AND data (catalogue, search index)? Type 'delete': " a
    [ "$a" = "delete" ] && docker compose down -v && echo "Removed." || echo "Cancelled." ;;

  help|*)
    cat <<EOF
SoK Research Desk — everyday commands

  ./resdesk.sh start | stop | restart | status
  ./resdesk.sh logs [service]           follow logs (backend, queue, create-site, meilisearch…)
  ./resdesk.sh url                      print the portal address

Choosing and ingesting books from the Internet Archive
  ./resdesk.sh count  --collection ServantsOfKnowledge --filter "language:kan"
  ./resdesk.sh ingest --collection ServantsOfKnowledge --filter "language:kan" --limit 100
  ./resdesk.sh ingest --query 'creator:(Kuvempu) AND mediatype:texts' --limit 50 --name "Kuvempu"
  ./resdesk.sh ingest --ids "id1,id2,id3"
  ./resdesk.sh ingest --profile "SoK Kannada sample"
      options: --no-fulltext  --update  --limit 0 (= everything)

Maintenance
  ./resdesk.sh reindex [--no-pages]     rebuild the search index
  ./resdesk.sh backup                   database + files into ./site-backups
  ./resdesk.sh restore <file.sql.gz>    restore a database backup, then re-index
  ./resdesk.sh update                   pull new code and upgrade
  ./resdesk.sh password [new]           reset the Administrator password
  ./resdesk.sh console | shell | bench …  for developers
  ./resdesk.sh uninstall                remove everything (asks first)
EOF
    ;;
esac
