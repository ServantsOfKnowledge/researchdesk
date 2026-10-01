#!/usr/bin/env bash
# Looks at this machine before installing Research Desk and advises the best way to do it:
# Docker, native, or Coolify; how to get HTTPS; what could get in the way. Changes nothing.
#
#   ./install.sh --check [--domain library.example.org]     (the installer also runs it first)
#   bash scripts/preflight.sh [--domain NAME] [--port 8080] [--brief]
#
# --brief prints only the findings that need attention and the advice (the installer uses it).
# Exit code: 0 always (advice, not a gate). RESDESK_PREFLIGHT_OUT=FILE also writes KEY=value
# lines (RECOMMENDED_MODE, COOLIFY, …) for install.sh.
set -uo pipefail
cd "$(dirname "$0")/.."

DOMAIN=""
PORT=""
BRIEF=0
while [ $# -gt 0 ]; do
  case "$1" in
    --domain) DOMAIN="${2:-}"; shift ;;
    --port) PORT="${2:-}"; shift ;;
    --brief) BRIEF=1 ;;
    -h|--help) sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
  esac
  shift
done
DOMAIN="${DOMAIN#http://}"; DOMAIN="${DOMAIN#https://}"; DOMAIN="${DOMAIN%%/*}"
if [ -z "$PORT" ] && [ -f .env ]; then PORT=$(sed -n 's/^HTTP_PORT=//p' .env | tr -d '"' | head -1); fi
PORT="${PORT:-8080}"

if [ -t 1 ]; then B=$'\033[1m'; G=$'\033[32m'; Y=$'\033[33m'; R=$'\033[31m'; D=$'\033[2m'; N=$'\033[0m'; else B=""; G=""; Y=""; R=""; D=""; N=""; fi
WARNINGS=0
section() { [ "$BRIEF" = 1 ] || printf "\n%s%s%s\n" "$B" "$1" "$N"; }
good()  { [ "$BRIEF" = 1 ] || printf "  %s✓%s %s\n" "$G" "$N" "$1"; }
note()  { [ "$BRIEF" = 1 ] || printf "  %s·%s %s\n" "$D" "$N" "$1"; }
heads() { WARNINGS=$((WARNINGS + 1)); printf "  %s!%s %s\n" "$Y" "$N" "$1"; }
bad()   { WARNINGS=$((WARNINGS + 1)); printf "  %s✗%s %s\n" "$R" "$N" "$1"; }
have()  { command -v "$1" >/dev/null 2>&1; }

listening() { # listening PORT: something on this machine listens on it
  if have ss; then ss -ltnH "sport = :$1" 2>/dev/null | grep -q .
  elif have lsof; then lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
  elif have netstat; then netstat -an 2>/dev/null | grep -E "[.:]$1[[:space:]].*LISTEN" -q
  else (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; fi
}
running() { pgrep -x "$1" >/dev/null 2>&1; }
reach() { # reach URL: any HTTP answer at all (even 401) means the network gets there
  local code; code=$(curl -s -o /dev/null -m 8 -w '%{http_code}' "$1" 2>/dev/null || true)
  [ -n "$code" ] && [ "$code" != 000 ]
}

# -- the machine ----------------------------------------------------------------------------
OS="$(uname -s)"; ARCH="$(uname -m)"; OS_NAME="$OS"; DEBIAN=0; WSL=0
case "$OS" in
  Darwin) OS_NAME="macOS $(sw_vers -productVersion 2>/dev/null)" ;;
  Linux)
    if [ -f /etc/os-release ]; then OS_NAME="$(. /etc/os-release && echo "${PRETTY_NAME:-Linux}")"; fi
    [ -f /etc/debian_version ] && DEBIAN=1
    grep -qi microsoft /proc/version 2>/dev/null && WSL=1 ;;
esac
CPUS=$( (getconf _NPROCESSORS_ONLN || sysctl -n hw.ncpu) 2>/dev/null | head -1 )
if [ "$OS" = Darwin ]; then MEM_GB=$(( $(sysctl -n hw.memsize 2>/dev/null || echo 0) / 1073741824 ))
else MEM_GB=$(( $(awk '/MemTotal/ {print $2}' /proc/meminfo 2>/dev/null || echo 0) / 1048576 )); fi
DISK_GB=$(df -Pk . 2>/dev/null | awk 'NR==2 {print int($4/1048576)}')
SERVER=0  # looks like a server: Linux, no desktop session
[ "$OS" = Linux ] && [ -z "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ] && [ "$WSL" = 0 ] && SERVER=1

section "This machine"
good "$OS_NAME ($ARCH), ${CPUS:-?} CPUs, ${MEM_GB:-?} GB memory, ${DISK_GB:-?} GB free here"
[ "$WSL" = 1 ] && note "Windows (WSL): use Docker Desktop for Windows with WSL integration"
if [ "${MEM_GB:-0}" -lt 4 ]; then bad "Less than 4 GB of memory: Research Desk needs 4 GB (use the light preset: ./resdesk.sh resources light)"
elif [ "${MEM_GB:-0}" -lt 8 ]; then note "Fine for a few thousand books; 8 GB or more for large collections"; fi
if [ "${DISK_GB:-0}" -lt 10 ]; then bad "Less than 10 GB of disk free: the install alone needs about 10 GB"
elif [ "${DISK_GB:-0}" -lt 40 ]; then note "Room for the install and some thousands of books; the page-text index grows with the library"; fi
SUDO_OK=0
if [ "$(id -u)" -eq 0 ]; then SUDO_OK=1; note "Running as root"
elif have sudo; then SUDO_OK=1; fi

# -- Docker ---------------------------------------------------------------------------------
section "Docker"
DOCKER=missing; DOCKER_MEM_GB=""
if have docker; then
  if docker info >/dev/null 2>&1; then
    DOCKER=running
    if docker compose version >/dev/null 2>&1; then
      good "Docker $(docker version --format '{{.Server.Version}}' 2>/dev/null) running, Compose $(docker compose version --short 2>/dev/null)"
    else
      DOCKER=no-compose; bad "Docker runs but Compose v2 is missing (install the docker-compose-plugin package, or update Docker Desktop)"
    fi
    DOCKER_MEM_GB=$(( $(docker info --format '{{.MemTotal}}' 2>/dev/null || echo 0) / 1073741824 ))
    if [ "$OS" = Darwin ] && [ "${DOCKER_MEM_GB:-0}" -lt 4 ]; then
      heads "Docker Desktop has ${DOCKER_MEM_GB} GB of memory: give it 4 GB or more (Settings → Resources)"
    fi
  elif docker info 2>&1 | grep -qi "permission denied"; then
    DOCKER=no-permission; heads "Docker is installed, but this user may not use it: sudo usermod -aG docker \"\$USER\", then log in again"
  else
    DOCKER=stopped; heads "Docker is installed but not running: start Docker Desktop, or sudo systemctl start docker"
  fi
else
  note "Docker is not installed"
fi

# -- what already runs here -------------------------------------------------------------------
section "Already on this machine"
COOLIFY=0
if [ -d "${COOLIFY_DATA:-/data/coolify}" ] || { [ "$DOCKER" = running ] && docker ps --format '{{.Names}}' 2>/dev/null | grep -Eqx 'coolify|coolify-proxy'; }; then
  COOLIFY=1; heads "Coolify manages this server (it owns ports 80 and 443 through its proxy)"
fi
HTTP80=0; HTTP443=0
listening 80 && HTTP80=1
listening 443 && HTTP443=1
WEB=""
if [ "$HTTP80$HTTP443" != 00 ]; then
  # a container publishing the ports first (its nginx would also look like the host's), then
  # web servers running on the machine itself
  PUBLISHER=""
  [ "$DOCKER" = running ] && PUBLISHER=$(docker ps --format '{{.Names}} {{.Ports}}' 2>/dev/null \
    | grep -E '(0\.0\.0\.0|\[::\]|:::):(80|443)->' | awk '{print $1}' | head -1)
  if [ -n "$PUBLISHER" ]; then
    case "$PUBLISHER" in sok-resdesk-proxy*) WEB=resdesk ;; *) WEB=container ;; esac
  elif running nginx; then WEB=nginx
  elif running apache2 || running httpd; then WEB=apache
  elif running caddy; then WEB=caddy
  elif running traefik; then WEB=traefik; fi
fi
if [ "$HTTP80$HTTP443" != 00 ]; then
  case "$WEB" in
    nginx) good "nginx answers on port 80/443: Research Desk can get a site in it, next to your other sites" ;;
    resdesk) good "Research Desk's own HTTPS proxy has port 80/443 (./resdesk.sh https status)" ;;
    apache) heads "Apache has port 80/443: Research Desk can sit behind it (proxy the name to 127.0.0.1:$PORT)" ;;
    caddy) heads "Caddy has port 80/443: add the name to your Caddyfile with reverse_proxy 127.0.0.1:$PORT" ;;
    traefik|container) [ "$COOLIFY" = 1 ] || heads "A container (Traefik or another proxy) has port 80/443: route the name to port $PORT through it" ;;
    *) heads "Something has port 80/443 (sudo ss -ltnp 'sport = :80' shows what)" ;;
  esac
else
  good "Ports 80 and 443 are free (Research Desk can bring its own HTTPS)"
fi
if listening "$PORT"; then
  if [ "$DOCKER" = running ] && docker ps --format '{{.Names}}' 2>/dev/null | grep -q '^sok-resdesk-frontend'; then
    note "Port $PORT is Research Desk's own (already installed here)"
  else heads "Port $PORT is in use: choose another when the installer asks (or HTTP_PORT in .env)"; fi
else good "Port $PORT is free for the portal"; fi

EXISTING=""
[ -f .env ] && EXISTING="this folder has a .env (re-running the installer keeps it)"
if [ "$DOCKER" = running ] && docker ps -a --format '{{.Names}}' 2>/dev/null | grep -q '^sok-resdesk-'; then
  EXISTING="Research Desk's containers are on this machine"
fi
[ -d "${BENCH_DIR:-$HOME/researchdesk-bench}/apps/sok_resdesk" ] && EXISTING="a native Research Desk bench is at ${BENCH_DIR:-~/researchdesk-bench}"
[ -n "$EXISTING" ] && note "Research Desk: $EXISTING (./upgrade.sh brings it up to date)"

DB_OTHER=0
if listening 3306; then
  if [ "$DOCKER" = running ] && docker ps --format '{{.Names}} {{.Ports}}' 2>/dev/null | grep -q ':3306->'; then
    note "A database container publishes port 3306 (Docker installs don't need it)"
  else
    DB_OTHER=1; heads "MySQL/MariaDB already runs here: a native install would change its settings and root password. Prefer Docker"
  fi
fi
listening 6379 && note "Redis already runs on port 6379 (Docker installs use their own; native ones their own ports)"
if [ "$OS" = Darwin ]; then
  have brew && good "Homebrew is installed (needed for a native install on macOS)" || note "No Homebrew (only needed for a native install)"
fi
have git && good "git $(git --version | awk '{print $3}')" || heads "git is missing (needed for ./upgrade.sh): sudo apt install git / xcode-select --install"
have curl || heads "curl is missing: sudo apt install curl"

# -- network ----------------------------------------------------------------------------------
section "Network"
NET_OK=1
for target in "https://github.com GitHub (code and upgrades)" "https://archive.org Internet Archive (the books)" "https://registry-1.docker.io/v2/ Docker Hub (images)"; do
  url="${target%% *}"; name="${target#* }"
  if reach "$url"; then good "$name"; else NET_OK=0; heads "Can't reach $name: check the firewall or proxy"; fi
done

DNS_OK=""
if [ -n "$DOMAIN" ]; then
  section "The name $DOMAIN"
  IPS=""
  if have getent; then IPS=$(getent ahostsv4 "$DOMAIN" 2>/dev/null | awk '{print $1}' | sort -u | tr '\n' ' ')
  elif have dscacheutil; then IPS=$(dscacheutil -q host -a name "$DOMAIN" 2>/dev/null | awk '/ip_address/ {print $2}' | sort -u | tr '\n' ' '); fi
  if [ -z "$IPS" ]; then
    DNS_OK=0; bad "$DOMAIN doesn't resolve: add an A record pointing at this server's public address"
  else
    MINE=$( (hostname -I 2>/dev/null || ifconfig 2>/dev/null | awk '/inet / {print $2}') | tr '\n' ' ')
    PUBLIC=$(curl -s -m 6 https://api.ipify.org 2>/dev/null || true)
    match=0
    for ip in $IPS; do
      case " $MINE $PUBLIC " in *" $ip "*) match=1 ;; esac
    done
    if [ "$match" = 1 ]; then DNS_OK=1; good "$DOMAIN → ${IPS% }: this machine"
    else DNS_OK=0; heads "$DOMAIN → ${IPS% }, but this machine is ${PUBLIC:-${MINE% }}: point the A record here before asking for a certificate"; fi
  fi
fi

# -- advice ---------------------------------------------------------------------------------
NAME_ARG=""; [ -n "$DOMAIN" ] && NAME_ARG=" --domain $DOMAIN"
NATIVE_OK=0
{ [ "$OS" = Darwin ] && have brew; } && NATIVE_OK=1
{ [ "$OS" = Linux ] && [ "$DEBIAN" = 1 ] && [ "$SUDO_OK" = 1 ]; } && NATIVE_OK=1

printf "\n%sRecommended%s\n" "$B" "$N"
MODE_REC=docker
if [ "$COOLIFY" = 1 ]; then
  MODE_REC=coolify
  echo "  Deploy it as a Docker Compose resource in Coolify rather than with ./install.sh: Coolify"
  echo "  already has ports 80/443 and does HTTPS. Set QUEUE_WORKERS=1, WORKERS_PER_CONTAINER=3 and"
  echo "  BASE_URL there. Moving an existing install in: ./resdesk.sh coolify import FILE."
  echo "  Step by step: docs/installation.md#coolify"
elif [ "$DOCKER" = running ]; then
  echo "  Docker (it's ready):  ./install.sh --docker${NAME_ARG}"
elif [ "$DOCKER" = stopped ] || [ "$DOCKER" = no-permission ] || [ "$DOCKER" = no-compose ]; then
  echo "  Docker, once it works (see above), then:  ./install.sh --docker${NAME_ARG}"
elif [ "$OS" = Linux ] && [ "$SUDO_OK" = 1 ] && [ "$WSL" = 0 ]; then
  echo "  Install Docker first (two minutes), then Research Desk in Docker:"
  echo "    curl -fsSL https://get.docker.com | sudo sh && sudo usermod -aG docker \"\$USER\" && newgrp docker"
  echo "    ./install.sh --docker${NAME_ARG}"
  if [ "$NATIVE_OK" = 1 ] && [ "$DB_OTHER" = 0 ]; then
    echo "  Or without Docker:  ./install.sh --native${NAME_ARG}"
  fi
elif [ "$OS" = Darwin ]; then
  echo "  Docker Desktop (https://www.docker.com/products/docker-desktop/), give it 4 GB of memory, then:"
  echo "    ./install.sh --docker"
  if [ "$NATIVE_OK" = 1 ]; then MODE_REC=docker; echo "  Or without Docker, with Homebrew:  ./install.sh --native"; fi
else
  echo "  Install Docker (https://docs.docker.com/engine/install/), then ./install.sh --docker${NAME_ARG}"
fi

if [ "$MODE_REC" != coolify ]; then
  if [ -n "$DOMAIN" ] || [ "$SERVER" = 1 ]; then
    NAME="${DOMAIN:-library.example.org}"
    case "$WEB" in
      nginx) echo "  HTTPS: the installer adds a site for $NAME to your nginx and gets a Let's Encrypt certificate" ;;
      resdesk) echo "  HTTPS: already on, through Research Desk's own proxy (./resdesk.sh https status)" ;;
      apache|caddy|traefik|container)
        echo "  HTTPS: let your existing web server pass $NAME on to http://127.0.0.1:$PORT, and install with"
        echo "         --no-https (then: ./resdesk.sh url https://$NAME)" ;;
      *) if [ "$HTTP80$HTTP443" = 00 ]; then
           if [ "$DOCKER" = running ]; then echo "  HTTPS: Research Desk brings its own nginx and Let's Encrypt certificate (ports 80/443)"
           else echo "  HTTPS: in Docker, its own nginx and certificate; native, nginx is installed and set up for it"; fi
         fi ;;
    esac
    [ -z "$DOMAIN" ] && echo "  On a server, give its name: --domain library.example.org (the DNS name must point here)"
    [ "$DNS_OK" = 0 ] && echo "  Fix the DNS record first, or install now and get the certificate later: ./resdesk.sh https on $DOMAIN"
  fi
  [ "${MEM_GB:-0}" -lt 6 ] && echo "  Small machine: after installing, ./resdesk.sh resources light"
  [ "$NET_OK" = 0 ] && echo "  The network blocks something above: the install downloads from GitHub and Docker Hub"
fi
echo "  Guide: docs/installation.md"
[ "$BRIEF" = 1 ] || { [ "$WARNINGS" = 0 ] && printf "\n%sNothing in the way.%s\n" "$G" "$N" || printf "\n%s%s thing(s) to look at above.%s\n" "$Y" "$WARNINGS" "$N"; }

if [ -n "${RESDESK_PREFLIGHT_OUT:-}" ]; then
  {
    echo "RECOMMENDED_MODE=$MODE_REC"; echo "COOLIFY=$COOLIFY"; echo "DOCKER=$DOCKER"; echo "WEB_SERVER=$WEB"
    echo "PORTS_80_443_BUSY=$([ "$HTTP80$HTTP443" != 00 ] && echo 1 || echo 0)"; echo "NATIVE_OK=$NATIVE_OK"
    echo "DB_OTHER=$DB_OTHER"; echo "WARNINGS=$WARNINGS"
  } > "$RESDESK_PREFLIGHT_OUT"
fi
exit 0
