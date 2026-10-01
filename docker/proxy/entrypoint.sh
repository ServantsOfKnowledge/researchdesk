#!/bin/sh
# nginx in front of Research Desk (the "proxy" service, ./resdesk.sh https on).
# Before there is a certificate: plain HTTP, and the files Let's Encrypt checks. With one:
# HTTPS, and HTTP redirects to it. Checks for a new or renewed certificate every 6 hours;
# `sh /resdesk-proxy/entrypoint.sh reload` does it straight away.
set -eu

render() {
  live="/etc/letsencrypt/live/${DOMAIN}"
  if [ -s "$live/fullchain.pem" ] && [ -s "$live/privkey.pem" ]; then mode=https; else mode=http; fi
  sed "s#__DOMAIN__#${DOMAIN}#g" "/resdesk-proxy/${mode}.conf" > /etc/nginx/conf.d/default.conf
  echo "$mode"
}

if [ "${1:-}" = reload ]; then
  mode=$(render)
  nginx -t -q && nginx -s reload
  echo "proxy: serving ${DOMAIN} over ${mode}"
  exit 0
fi

echo "proxy: serving ${DOMAIN} over $(render)"
(
  while :; do
    sleep 21600
    render >/dev/null && nginx -t -q && nginx -s reload
  done
) &
exec nginx -g 'daemon off;'
