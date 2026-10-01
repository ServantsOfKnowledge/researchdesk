# shellcheck shell=bash
# The portal's address, and HTTPS with a free Let's Encrypt certificate (Docker installs).
# Sourced by resdesk.sh (it provides MODE, SITE, bench, set_env and .env). HTTPS=1 in .env adds
# compose.https.yaml (nginx + certbot) to the Compose files:
#   ./resdesk.sh url                                 show the address the portal uses
#   ./resdesk.sh url https://library.example.org     change it (links, citations, OAI-PMH, emails)
#   ./resdesk.sh https on DOMAIN [--email you@example.org] [--staging] [--nginx|--docker-proxy]
#     Docker: Research Desk's own nginx + certbot (compose.https.yaml), or, when the server's
#     nginx already has ports 80/443 (and always on native installs), a site in that nginx.
#   ./resdesk.sh https status | renew | off
# See docs/installation.md#https-with-lets-encrypt.

https_is_on() { [ "${HTTPS:-0}" = 1 ] || [ "${HTTPS_NGINX:-0}" = 1 ]; }

https_files() { # https_files on|off: add or drop compose.https.yaml in COMPOSE_FILE
  local f=":${COMPOSE_FILE:-compose.yaml}:"
  f="${f//:compose.https.yaml:/:}"
  [ "$1" = on ] && f="${f}compose.https.yaml:"
  f="${f#:}"; f="${f%:}"
  export COMPOSE_FILE="$f"
}

proxy_running() { [ -n "$(docker compose ps -q --status running proxy 2>/dev/null)" ]; }

acme_run() { # certbot with the certificate volumes: acme_run ARGS...
  docker compose run --rm --no-deps --entrypoint certbot certbot "$@"
}

quiet_up() { # docker compose up -d SERVICES, showing only problems
  docker compose up -d "$@" 2>&1 | grep -iv "running\|start\|recreate\|creat\|waiting\|healthy\|exited" || true
}

host_of() { # host_of URL → the host name
  python3 -c 'import sys,urllib.parse as u; print(u.urlsplit(sys.argv[1]).hostname or "")' "$1"
}

public_ip_warning() { # warn when DOMAIN doesn't resolve, or resolves to a private address
  python3 - "$1" <<'PY' || true
import ipaddress, socket, sys
d = sys.argv[1]
try:
    ips = sorted({a[4][0] for a in socket.getaddrinfo(d, 80, proto=socket.IPPROTO_TCP)})
except OSError:
    print(f"  ! {d} doesn't resolve yet. Add a DNS record (A, and AAAA for IPv6) pointing at this server,")
    print("    wait for it to spread (minutes to an hour), and run this again.")
    sys.exit(1)
private = [i for i in ips if not ipaddress.ip_address(i).is_global]
print(f"  {d} → {', '.join(ips)}")
if private:
    print("  ! That is a private address: Let's Encrypt must reach this server from the internet on port 80.")
    print("    Point the DNS name at the public address, and forward ports 80 and 443 on your router.")
PY
}

docker_subnet() { # the Compose network's subnet (for trusting the proxy's X-Forwarded-For)
  local project net
  project=$(docker compose config --format json 2>/dev/null | python3 -c 'import json,sys;print(json.load(sys.stdin)["name"])' 2>/dev/null || echo sok-resdesk)
  net=$(docker network ls -q --filter "label=com.docker.compose.project=$project" | head -1)
  [ -n "$net" ] && docker network inspect -f '{{range .IPAM.Config}}{{.Subnet}} {{end}}' "$net" 2>/dev/null | awk '{print $1}'
}

apply_url() { # apply_url URL: everywhere the address is kept
  local url="$1"
  set_env BASE_URL "$url"
  bench set-config host_name "$url" >/dev/null
  bench execute sok_resdesk.setup.set_base_url --kwargs "{'url': '$url'}" >/dev/null
}

rd_url() {
  local url="${1:-}"
  if [ -z "$url" ]; then
    local cfg settings
    cfg=$(bench execute frappe.get_site_config 2>/dev/null | python3 -c 'import json,sys
try: print(json.loads(sys.stdin.read().strip().splitlines()[-1]).get("host_name") or "")
except Exception: print("")' 2>/dev/null || true)
    settings=$(bench execute frappe.db.get_single_value --args "['RD Settings','base_url']" 2>/dev/null | tail -1 | tr -d '"\r' || true)
    echo "Portal address (BASE_URL in .env):   ${BASE_URL:-not set}"
    echo "Site config (host_name):             ${cfg:-not set}"
    echo "Settings → Public Base URL:          ${settings:-not set}"
    if https_is_on; then
      echo "HTTPS (Let's Encrypt):               on for ${HTTPS_DOMAIN:-?}"
    else
      echo "HTTPS (Let's Encrypt):               off (./resdesk.sh https on DOMAIN)"
    fi
    echo
    echo "Change it: ./resdesk.sh url https://library.example.org"
    return
  fi
  url="${url%/}"
  [[ "$url" =~ ^https?://[A-Za-z0-9.-]+(:[0-9]+)?$ ]] || {
    echo "Give the full address, e.g. https://library.example.org (http:// or https://, no path)."; exit 1; }
  local host; host=$(host_of "$url")
  echo "Setting the portal's address to $url"
  apply_url "$url"
  echo "  ✓ links, citations, OAI-PMH and emails now use $url"
  if [ "$MODE" != native ] && [[ "$url" == https://* ]] && [ "$host" != localhost ] && [[ ! "$host" =~ ^[0-9.]+$ ]]; then
    if https_is_on; then
      if [ "$host" != "${HTTPS_DOMAIN:-}" ]; then
        echo "  HTTPS is on for ${HTTPS_DOMAIN:-another name}: getting a certificate for ${host}…"
        rd_https on "$host"
      fi
    else
      echo "  For HTTPS on $host: ./resdesk.sh https on $host (free Let's Encrypt certificate),"
      echo "  or put your own reverse proxy in front of port ${HTTP_PORT:-8080}."
    fi
  fi
  echo "  Links already shared (citations, OAI-PMH identifiers harvested elsewhere) keep the old address."
}

# -- HTTPS through the server's own nginx ------------------------------------------------
# Native installs, and Docker installs on a server whose nginx already has ports 80 and 443:
# a site for Research Desk in that nginx, and certbot's nginx plugin for the certificate
# (renewed by the certbot package's timer).

port_in_use() { # port_in_use PORT: something on this machine listens on it
  if command -v ss >/dev/null 2>&1; then ss -ltnH "sport = :$1" 2>/dev/null | grep -q .
  else (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; fi
}

use_host_nginx() { # use_host_nginx CMD ARGS...: 0 when HTTPS goes through the server's nginx
  [ "$MODE" = native ] && return 0
  [ "${HTTPS_NGINX:-0}" = 1 ] && return 0
  https_is_on && return 1
  local a; for a in "$@"; do
    case "$a" in --nginx) return 0 ;; --docker-proxy) return 1 ;; esac
  done
  [ "$1" = on ] || return 1
  if port_in_use "${HTTPS_HTTP_PORT:-80}" || port_in_use "${HTTPS_PORT:-443}"; then
    if pgrep -x nginx >/dev/null 2>&1; then
      echo "nginx already answers on this server: Research Desk gets a site in it."
      return 0
    fi
    echo "Something on this server already uses port 80 or 443, and it isn't nginx."
    echo "  sudo ss -ltnp 'sport = :80 or sport = :443'    shows what. Then either:"
    echo "  - stop it and run this again (Research Desk brings its own nginx), or"
    echo "  - let it pass https://DOMAIN on to http://127.0.0.1:${HTTP_PORT:-8080}, and set the address:"
    echo "    ./resdesk.sh url https://DOMAIN"
    exit 1
  fi
  return 1
}

nginx_site_file() { # nginx_site_file DOMAIN: one file per name, so a new name never touches the old
  local slug; slug="researchdesk-$(echo "${1:-${HTTPS_DOMAIN:-resdesk}}" | tr -c 'A-Za-z0-9\n' '-')"
  if [ -d /etc/nginx/sites-available ]; then echo "/etc/nginx/sites-available/$slug.conf"
  else echo "/etc/nginx/conf.d/$slug.conf"; fi
}

nginx_socketio_port() { # native: Frappe's socket.io server (Docker: the portal container has it)
  python3 -c 'import json,sys
try: print(json.load(open(sys.argv[1])).get("socketio_port") or 9000)
except Exception: print(9000)' "${BENCH_DIR:-}/sites/common_site_config.json"
}

write_nginx_site() { # write_nginx_site DOMAIN: a plain-HTTP site; certbot adds HTTPS to it
  local domain="$1" file port slug sio_block=""
  file=$(nginx_site_file "$domain"); port="${HTTP_PORT:-8000}"
  slug=$(basename "$file" .conf | tr '-' '_')
  if [ "$MODE" = native ]; then
    sio_block="
    # realtime updates: Frappe's socket.io server
    location /socket.io {
        proxy_pass http://127.0.0.1:$(nginx_socketio_port);
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection \$${slug}_connection;
        proxy_set_header X-Frappe-Site-Name ${SITE};
        proxy_set_header Origin \$scheme://\$http_host;
        proxy_set_header Host \$host;
    }
"
  fi
  local tmp; tmp=$(mktemp)
  cat > "$tmp" <<NGINX
# SoK Research Desk at ${domain}: written by ./resdesk.sh https on (rewritten when the name
# changes; certbot adds the HTTPS lines). Remove with ./resdesk.sh https off.
map \$http_upgrade \$${slug}_connection { default upgrade; '' close; }

server {
    listen 80;
    server_name ${domain};
    client_max_body_size 50m;
${sio_block}
    location / {
        proxy_pass http://127.0.0.1:${port};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection \$${slug}_connection;
        proxy_read_timeout 120s;
        proxy_send_timeout 120s;
    }
}
NGINX
  $SUDO_CMD install -m 644 "$tmp" "$file"; rm -f "$tmp"
  if [ -d /etc/nginx/sites-enabled ]; then $SUDO_CMD ln -sf "$file" "/etc/nginx/sites-enabled/$(basename "$file")"; fi
}

nginx_reload() {
  $SUDO_CMD nginx -t -q || { echo "  ✗ nginx doesn't accept the configuration (above); nothing was reloaded."; exit 1; }
  if command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet nginx 2>/dev/null; then $SUDO_CMD systemctl reload nginx
  else $SUDO_CMD nginx -s reload; fi
}

native_rebind() { # native_rebind ADDRESS: gunicorn's address, then restart
  set_env BIND_ADDRESS "$1"; export BIND_ADDRESS="$1"
  bash scripts/native-procfile.sh "$BENCH_DIR" "${QUEUE_WORKERS:-2}" "${MEILI_PORT:-7700}" "$MEILI_MASTER_KEY"
  if running; then native_stop >/dev/null; native_start >/dev/null; fi
}

nginx_https() {
  local cmd="$1"; shift
  SUDO_CMD=""; [ "$(id -u)" -ne 0 ] && SUDO_CMD="sudo"
  if [ "$(uname -s)" != Linux ]; then
    echo "HTTPS through nginx is set up for Linux servers. On this computer, put nginx or Caddy in"
    echo "front of port ${HTTP_PORT:-8000} by hand (docs/installation.md#https-with-lets-encrypt)."
    exit 1
  fi
  case "$cmd" in
    on)
      local domain="" email="${CONTACT_EMAIL:-}" staging=0
      while [ $# -gt 0 ]; do
        case "$1" in
          --email) email="${2:-}"; shift 2 ;;
          --staging) staging=1; shift ;;
          --nginx|--docker-proxy) shift ;;
          *) domain="$1"; shift ;;
        esac
      done
      domain="${domain#http://}"; domain="${domain#https://}"; domain="${domain%%/*}"
      [ -n "$domain" ] || domain="${HTTPS_DOMAIN:-}"
      [[ "$domain" =~ ^[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?(\.[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?)+$ ]] || {
        echo "Usage: ./resdesk.sh https on library.example.org [--email you@example.org]"; exit 1; }
      echo "HTTPS for $domain through this server's nginx, with a Let's Encrypt certificate"
      public_ip_warning "$domain"

      echo "1/4 nginx and certbot…"
      if ! command -v nginx >/dev/null 2>&1 || ! command -v certbot >/dev/null 2>&1 \
         || ! { $SUDO_CMD certbot plugins 2>/dev/null | grep -q '^\* nginx'; }; then
        if [ -f /etc/debian_version ]; then
          $SUDO_CMD apt-get update -qq
          $SUDO_CMD env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq nginx certbot python3-certbot-nginx >/dev/null
        else
          echo "  ✗ Install nginx, certbot and certbot's nginx plugin, then run this again."; exit 1
        fi
      fi
      if ! pgrep -x nginx >/dev/null 2>&1; then
        if port_in_use 80 || port_in_use 443; then
          echo "  ✗ Port 80 or 443 is taken by something other than nginx: sudo ss -ltnp 'sport = :80'"; exit 1
        fi
        $SUDO_CMD systemctl enable --now nginx >/dev/null 2>&1 || $SUDO_CMD nginx
      fi
      echo "  ✓ nginx $(nginx -v 2>&1 | sed 's#.*/##'), certbot $(certbot --version 2>&1 | awk '{print $2}')"

      echo "2/4 A site for $domain in nginx…"
      write_nginx_site "$domain"
      nginx_reload
      echo "  ✓ $(nginx_site_file "$domain") → port ${HTTP_PORT:-8000}"
      # only nginx should answer from outside; the portal's own port stays on this machine
      if [ "$MODE" = native ]; then
        [ "${BIND_ADDRESS:-0.0.0.0}" = 127.0.0.1 ] || native_rebind 127.0.0.1
      else
        set_env HTTP_BIND "127.0.0.1:"; export HTTP_BIND="127.0.0.1:"
        local subnet; subnet=$(docker_subnet || true)
        set_env UPSTREAM_REAL_IP_ADDRESS "${subnet:-172.16.0.0/12}"; export UPSTREAM_REAL_IP_ADDRESS="${subnet:-172.16.0.0/12}"
        quiet_up frontend
      fi

      echo "3/4 Asking Let's Encrypt for a certificate…"
      local args=(--nginx -d "$domain" --cert-name "$domain" --agree-tos --non-interactive --redirect --keep-until-expiring)
      if [ -n "$email" ]; then args+=(--email "$email"); else args+=(--register-unsafely-without-email); fi
      [ "$staging" = 1 ] && args+=(--staging)
      # shellcheck disable=SC2206
      [ -n "${ACME_ARGS:-}" ] && args+=(${ACME_ARGS})
      if ! $SUDO_CMD ${ACME_CA_BUNDLE:+env REQUESTS_CA_BUNDLE=$ACME_CA_BUNDLE} certbot "${args[@]}"; then
        echo
        echo "  ✗ No certificate. The portal answers on http://$domain meanwhile."
        echo "    Usual causes: the DNS name doesn't point here yet, or port 80 is closed to the internet."
        echo "    Fix it and run: ./resdesk.sh https on $domain"
        # keep the earlier name (if any) as the one HTTPS is on for; this name's site stays,
        # so the retry finds it
        if [ -z "${HTTPS_DOMAIN:-}" ]; then set_env HTTPS_NGINX 1; set_env HTTPS_DOMAIN "$domain"; fi
        exit 1
      fi

      echo "4/4 Switching to HTTPS…"
      if [ -n "${HTTPS_DOMAIN:-}" ] && [ "${HTTPS_DOMAIN}" != "$domain" ]; then
        local old; old=$(nginx_site_file "$HTTPS_DOMAIN")   # the previous name's site
        $SUDO_CMD rm -f "/etc/nginx/sites-enabled/$(basename "$old")" "$old"
        nginx_reload
      fi
      set_env HTTPS_NGINX 1; export HTTPS_NGINX=1
      set_env HTTPS_DOMAIN "$domain"; export HTTPS_DOMAIN="$domain"
      apply_url "https://$domain"
      echo
      echo "HTTPS is on: https://$domain/library"
      echo "certbot renews the certificate by itself (its systemd timer). ./resdesk.sh https status"
      ;;
    status)
      if [ "${HTTPS_NGINX:-0}" != 1 ]; then
        echo "HTTPS is off. Turn it on: ./resdesk.sh https on library.example.org"; return
      fi
      echo "HTTPS is on for ${HTTPS_DOMAIN:-?}, through this server's nginx ($(nginx_site_file "${HTTPS_DOMAIN:-}"))"
      $SUDO_CMD certbot certificates --cert-name "${HTTPS_DOMAIN:-x}" 2>/dev/null | grep -E "Domains|Expiry" | sed 's/^ */  /' || true
      systemctl list-timers certbot.timer --no-pager 2>/dev/null | sed -n 2p | sed 's/^/  renewal timer: /' || true
      ;;
    renew)
      $SUDO_CMD certbot renew
      nginx_reload
      ;;
    off)
      local file; file=$(nginx_site_file "${HTTPS_DOMAIN:-}")
      $SUDO_CMD rm -f "/etc/nginx/sites-enabled/$(basename "$file")" "$file"
      nginx_reload
      set_env HTTPS_NGINX 0; export HTTPS_NGINX=0
      if [ "$MODE" = native ]; then native_rebind 0.0.0.0
      else
        set_env HTTP_BIND ""; export HTTP_BIND=""
        set_env UPSTREAM_REAL_IP_ADDRESS "127.0.0.1"; export UPSTREAM_REAL_IP_ADDRESS=127.0.0.1
        quiet_up frontend
      fi
      echo "Removed Research Desk's site from nginx (the certificate is kept: sudo certbot delete to remove it)."
      echo "The portal answers on port ${HTTP_PORT:-8000} again. Set the address: ./resdesk.sh url http://SERVER:${HTTP_PORT:-8000}"
      ;;
    *) echo "Usage: ./resdesk.sh https on DOMAIN [--email ADDRESS] [--staging] | status | renew | off"; exit 1 ;;
  esac
}

# -- dispatch: the server's nginx, or Research Desk's own (Docker) ------------------------

rd_https() {
  local cmd="${1:-status}"; [ $# -gt 0 ] && shift
  if use_host_nginx "$cmd" "$@"; then nginx_https "$cmd" "$@"; return; fi
  docker_https "$cmd" "$@"
}

docker_https() {
  local cmd="$1"; shift
  case "$cmd" in
    on)
      local domain="" email="${CONTACT_EMAIL:-}" staging=0
      while [ $# -gt 0 ]; do
        case "$1" in
          --email) email="${2:-}"; shift 2 ;;
          --staging) staging=1; shift ;;
          --nginx|--docker-proxy) shift ;;
          *) domain="$1"; shift ;;
        esac
      done
      domain="${domain#http://}"; domain="${domain#https://}"; domain="${domain%%/*}"
      [ -n "$domain" ] || domain="${HTTPS_DOMAIN:-}"
      [[ "$domain" =~ ^[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?(\.[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?)+$ ]] || {
        echo "Usage: ./resdesk.sh https on library.example.org [--email you@example.org]"; exit 1; }
      echo "HTTPS for $domain with a Let's Encrypt certificate"
      public_ip_warning "$domain"

      echo "1/4 The HTTPS proxy on ports ${HTTPS_HTTP_PORT:-80} and ${HTTPS_PORT:-443}…"
      https_files on
      if proxy_running; then
        # already running (for this or another name): it answers Let's Encrypt's checks for any
        # name, and keeps serving the current certificate until the new one is in
        echo "  ✓ running"
      else
        set_env HTTPS_DOMAIN "$domain"; export HTTPS_DOMAIN="$domain"
        # only the proxy should answer from outside; the portal's own port stays on this machine
        set_env HTTP_BIND "127.0.0.1:"; export HTTP_BIND="127.0.0.1:"
        local subnet; subnet=$(docker_subnet || true)
        set_env UPSTREAM_REAL_IP_ADDRESS "${subnet:-172.16.0.0/12}"; export UPSTREAM_REAL_IP_ADDRESS="${subnet:-172.16.0.0/12}"
        set_env HTTPS 1; export HTTPS=1
        quiet_up frontend proxy
        if ! proxy_running; then
          echo "  ✗ The proxy didn't start. Is something else using port 80 or 443 (another web server)?"
          echo "    sudo ss -ltnp 'sport = :80 or sport = :443'   Stop it, or see the docs for using your own."
          exit 1
        fi
        echo "  ✓ started"
      fi

      echo "2/4 Checking that $domain reaches this server…"
      local probe; probe="resdesk-$(date +%s)"
      docker compose run --rm --no-deps --entrypoint sh certbot -c \
        "mkdir -p /var/www/certbot/.well-known/acme-challenge && echo $probe > /var/www/certbot/.well-known/acme-challenge/$probe" >/dev/null 2>&1 || true
      if [ "$(curl -fsS -m 10 "http://$domain:${HTTPS_HTTP_PORT:-80}/.well-known/acme-challenge/$probe" 2>/dev/null)" = "$probe" ]; then
        echo "  ✓ http://$domain answers from this server"
      else
        echo "  ! Couldn't reach http://$domain from here. That's fine if your router doesn't loop back;"
        echo "    otherwise check DNS and that ports 80 and 443 are open to the internet. Trying anyway."
      fi
      docker compose run --rm --no-deps --entrypoint rm certbot -f "/var/www/certbot/.well-known/acme-challenge/$probe" >/dev/null 2>&1 || true

      echo "3/4 Asking Let's Encrypt for a certificate…"
      local args=(certonly --webroot -w /var/www/certbot --cert-name "$domain" -d "$domain"
                  --agree-tos --non-interactive --keep-until-expiring)
      if [ -n "$email" ]; then args+=(--email "$email"); else args+=(--register-unsafely-without-email); fi
      [ "$staging" = 1 ] && args+=(--staging)
      # ACME_ARGS: another ACME certificate authority, e.g. --server https://acme.example/directory
      # shellcheck disable=SC2206
      [ -n "${ACME_ARGS:-}" ] && args+=(${ACME_ARGS})
      if ! acme_run "${args[@]}"; then
        echo
        if [ -n "${HTTPS_DOMAIN:-}" ] && [ "${HTTPS_DOMAIN}" != "$domain" ]; then
          echo "  ✗ No certificate for $domain. HTTPS stays as it was, for ${HTTPS_DOMAIN}."
        else
          echo "  ✗ No certificate. The portal still answers on http://$domain."
        fi
        echo "    Usual causes: the DNS name doesn't point here yet, or port 80 is closed to the internet."
        echo "    Fix it and run: ./resdesk.sh https on $domain"
        exit 1
      fi

      echo "4/4 Switching to HTTPS…"
      set_env HTTPS_DOMAIN "$domain"; export HTTPS_DOMAIN="$domain"
      quiet_up proxy
      sleep 1
      docker compose exec -T proxy sh /resdesk-proxy/entrypoint.sh reload
      quiet_up certbot
      apply_url "https://$domain"
      echo
      echo "HTTPS is on: https://$domain/library"
      echo "The certificate renews by itself (certbot checks twice a day). ./resdesk.sh https status"
      ;;
    status)
      if ! https_is_on; then
        echo "HTTPS (Let's Encrypt) is off. Turn it on: ./resdesk.sh https on library.example.org"; return
      fi
      https_files on
      echo "HTTPS is on for ${HTTPS_DOMAIN:-?}"
      docker compose ps proxy certbot --format '  {{.Service}}: {{.Status}}' 2>/dev/null || true
      acme_run certificates --cert-name "${HTTPS_DOMAIN:-x}" 2>/dev/null | grep -E "Domains|Expiry|Certificate Path" | sed 's/^ */  /' || true
      ;;
    renew)
      https_is_on || { echo "HTTPS is off."; exit 1; }
      https_files on
      # shellcheck disable=SC2086
      acme_run renew --webroot -w /var/www/certbot ${ACME_ARGS:-}
      docker compose exec -T proxy sh /resdesk-proxy/entrypoint.sh reload
      ;;
    off)
      https_files on
      docker compose rm -sf proxy certbot >/dev/null 2>&1 || true
      set_env HTTPS 0; export HTTPS=0
      https_files off
      set_env HTTP_BIND ""; export HTTP_BIND=""
      set_env UPSTREAM_REAL_IP_ADDRESS "127.0.0.1"; export UPSTREAM_REAL_IP_ADDRESS=127.0.0.1
      quiet_up frontend
      echo "HTTPS is off; the portal answers on port ${HTTP_PORT:-8080} again (the certificate is kept)."
      echo "Set the address people use: ./resdesk.sh url http://SERVER:${HTTP_PORT:-8080}"
      ;;
    *) echo "Usage: ./resdesk.sh https on DOMAIN [--email ADDRESS] [--staging] | status | renew | off"; exit 1 ;;
  esac
}
