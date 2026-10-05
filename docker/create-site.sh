#!/bin/bash
# Creates the Research Desk site on first run; on later runs migrates it when the code has
# changed since the last migrate (sok_resdesk/core/schema.py), or always with FORCE_MIGRATE=1.
# Runs inside the "create-site" one-shot container (see compose.yaml).
set -euo pipefail
cd /home/frappe/frappe-bench

SITE_NAME="${SITE_NAME:-resdesk.localhost}"

wait-for-it -t 180 db:3306
wait-for-it -t 120 redis-cache:6379
wait-for-it -t 120 redis-queue:6379

if [ -d "sites/${SITE_NAME}" ]; then
  if [ "${FORCE_MIGRATE:-0}" != 1 ] && WHY="$(env/bin/python -m sok_resdesk.core.schema check "${SITE_NAME}")"; then
    echo ">> Site ${SITE_NAME} exists: ${WHY}, no migrate needed"
  else
    echo ">> Site ${SITE_NAME} exists: ${WHY:-migrate asked for}, running migrate"
    # --skip-search-index: Frappe's own website search isn't used (the portal searches with Meilisearch)
    bench --site "${SITE_NAME}" migrate --skip-search-index
  fi
else
  echo ">> Creating site ${SITE_NAME}"
  bench new-site "${SITE_NAME}" \
    --mariadb-user-host-login-scope='%' \
    --db-root-username=root \
    --db-root-password="${DB_ROOT_PASSWORD}" \
    --admin-password="${ADMIN_PASSWORD}" \
    --set-default
  bench --site "${SITE_NAME}" set-config resdesk_meili_url "http://meilisearch:7700"
  bench --site "${SITE_NAME}" set-config resdesk_meili_key "${MEILI_MASTER_KEY}"
  bench --site "${SITE_NAME}" set-config resdesk_portal_title "${PORTAL_TITLE:-SOK Research Desk}"
  bench --site "${SITE_NAME}" set-config resdesk_contact "${CONTACT_EMAIL:-}"
  bench --site "${SITE_NAME}" set-config resdesk_profiles "${RESDESK_PROFILES:-}"
  bench --site "${SITE_NAME}" set-config resdesk_books "${RESDESK_BOOKS:-0}"
  bench --site "${SITE_NAME}" set-config resdesk_repository_id "${SITE_NAME}"
  echo ">> Installing Research Desk"
  bench --site "${SITE_NAME}" install-app sok_resdesk
  bench --site "${SITE_NAME}" execute sok_resdesk.setup.complete_setup_wizard \
    --kwargs "{'timezone': '${TIMEZONE:-Asia/Kolkata}', 'country': '${COUNTRY:-India}', 'currency': '${CURRENCY:-INR}'}"
  bench --site "${SITE_NAME}" enable-scheduler
  bench --site "${SITE_NAME}" execute sok_resdesk.search.setup_indexes \
    || echo ">> WARNING: search indexes will be set up by the first ingest"
fi

stored_host() {
  env/bin/python -c 'import json,sys; print(json.load(open(sys.argv[1])).get("host_name") or "")' \
    "sites/${SITE_NAME}/site_config.json" 2>/dev/null || true
}
# only when the address changed: saving Settings on every start competes with running jobs
if [ -n "${BASE_URL:-}" ] && [ "$(stored_host)" != "${BASE_URL}" ]; then
  # host_name: used by Frappe for absolute URLs and the realtime (socket.io) origin check
  bench --site "${SITE_NAME}" set-config host_name "${BASE_URL}"
  # not worth failing an upgrade over: it only records the address (Settings can set it too)
  bench --site "${SITE_NAME}" execute sok_resdesk.setup.set_base_url --kwargs "{'url': '${BASE_URL}'}" \
    || echo ">> WARNING: could not save the public address in Settings; set it there (Public Base URL)"
fi
echo ">> create-site finished"
