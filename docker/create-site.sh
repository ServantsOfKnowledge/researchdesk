#!/bin/bash
# Creates the Research Desk site on first run; migrates it on later runs.
# Runs inside the "create-site" one-shot container (see compose.yaml).
set -euo pipefail
cd /home/frappe/frappe-bench

SITE_NAME="${SITE_NAME:-resdesk.localhost}"

wait-for-it -t 180 db:3306
wait-for-it -t 120 redis-cache:6379
wait-for-it -t 120 redis-queue:6379

if [ -d "sites/${SITE_NAME}" ]; then
  echo ">> Site ${SITE_NAME} exists: running migrate"
  bench --site "${SITE_NAME}" migrate
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
  bench --site "${SITE_NAME}" set-config resdesk_portal_title "${PORTAL_TITLE:-SoK Research Desk}"
  bench --site "${SITE_NAME}" set-config resdesk_contact "${CONTACT_EMAIL:-}"
  bench --site "${SITE_NAME}" set-config resdesk_repository_id "${SITE_NAME}"
  echo ">> Installing Research Desk"
  bench --site "${SITE_NAME}" install-app sok_resdesk
  bench --site "${SITE_NAME}" execute sok_resdesk.setup.complete_setup_wizard \
    --kwargs "{'timezone': '${TIMEZONE:-Asia/Kolkata}', 'country': '${COUNTRY:-India}', 'currency': '${CURRENCY:-INR}'}"
  bench --site "${SITE_NAME}" enable-scheduler
fi

if [ -n "${BASE_URL:-}" ]; then
  # host_name: used by Frappe for absolute URLs and the realtime (socket.io) origin check
  bench --site "${SITE_NAME}" set-config host_name "${BASE_URL}"
  # not worth failing an upgrade over: it only records the address (Settings can set it too)
  bench --site "${SITE_NAME}" resdesk configure --base-url "${BASE_URL}" \
    || echo ">> WARNING: could not save the public address in Settings; set it there (Public Base URL)"
fi
echo ">> create-site finished"
