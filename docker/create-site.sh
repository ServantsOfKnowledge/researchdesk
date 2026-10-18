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

# Classified mode (docs/governance.md#classified-mode): RESDESK_CLASSIFIED=1 in .env turns it on, for a
# new site or an existing one, once; nothing here turns it off (that is `bench set-config` on the host)
if [ "${RESDESK_CLASSIFIED:-}" = 1 ] && ! env/bin/python -c 'import json,sys; sys.exit(0 if json.load(open(sys.argv[1])).get("resdesk_classified") else 1)' "sites/${SITE_NAME}/site_config.json" 2>/dev/null; then
  bench --site "${SITE_NAME}" set-config resdesk_classified 1
  bench --site "${SITE_NAME}" execute sok_resdesk.classified.apply
fi

# Public mirror (docs/governance.md#the-public-mirror): a token in .env makes this site the read-only
# copy the main system feeds; it is written to the site configuration, outside the Desk's reach
if [ -n "${RESDESK_MIRROR_TOKEN:-}" ] && ! env/bin/python -c 'import json,sys; sys.exit(0 if json.load(open(sys.argv[1])).get("resdesk_mirror_token") == sys.argv[2] else 1)' "sites/${SITE_NAME}/site_config.json" "${RESDESK_MIRROR_TOKEN}" 2>/dev/null; then
  bench --site "${SITE_NAME}" set-config resdesk_mirror 1
  bench --site "${SITE_NAME}" set-config resdesk_mirror_token "${RESDESK_MIRROR_TOKEN}"
fi

# The updater helper's token (./resdesk.sh updater on): .env is where it is kept, the site configuration is
# where the Desk reads it. A restored backup or a recreated site loses the second copy, and then the
# Server page says the helper is off while the helper is refused; put it back whenever the stack comes up
if [ -n "${RESDESK_AGENT_TOKEN:-}" ] && ! env/bin/python -c 'import json,sys; sys.exit(0 if json.load(open(sys.argv[1])).get("resdesk_agent_token") == sys.argv[2] else 1)' "sites/${SITE_NAME}/site_config.json" "${RESDESK_AGENT_TOKEN}" 2>/dev/null; then
  echo ">> Putting the updater helper's token back in the site configuration"
  bench --site "${SITE_NAME}" set-config resdesk_agent_token "${RESDESK_AGENT_TOKEN}"
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
