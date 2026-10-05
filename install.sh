#!/usr/bin/env bash
# ---------------------------------------------------------------------------
#  SOK Research Desk — one-command installer
#
#  ./install.sh              interactive install (asks: Docker or native)
#  ./install.sh --docker     run everything in Docker containers (recommended)
#  ./install.sh --native     install directly on this computer (macOS / Ubuntu / Debian)
#  ./install.sh --yes        accept all defaults (unattended; Docker unless --native)
#  ./install.sh --sample     also ingest a small sample from Servants of Knowledge
#  ./install.sh --check      look at this machine and advise how to install (changes nothing)
#  ./install.sh --profile portal,archive [--languages "kan eng"] [--books 20000]
#                            what kind of institution (they combine): small, portal, members,
#                            archive, repository, langtech; the books' languages for OCR (or
#                            all); about how many books. Settings → Features can change it later
#  ./install.sh --domain library.example.org [--email you@example.org]
#                            a server with a DNS name: the portal's address, with HTTPS from
#                            Let's Encrypt (Docker; --no-https if you have your own proxy)
#
#  Docker: Docker Desktop (Mac/Windows) or Docker Engine + Compose v2 (Linux).
#  Native: Homebrew (macOS) or apt + sudo (Ubuntu 22.04+/Debian 12+).
#  Either way: 4 GB of free RAM, ~10 GB of disk. Re-running is safe.
# ---------------------------------------------------------------------------
set -euo pipefail
cd "$(dirname "$0")"

YES=0
SAMPLE=""
MODE=""
DOMAIN=""
EMAIL=""
WANT_HTTPS=""   # not HTTPS: that one, in .env, says whether it is on
CHECK_ONLY=0
PROFILES=""
LANGUAGES=""
BOOKS=""
while [ $# -gt 0 ]; do
  case "$1" in
    -y|--yes) YES=1 ;;
    --docker) MODE=docker ;;
    --native) MODE=native ;;
    --sample) SAMPLE=1 ;;
    --no-sample) SAMPLE=0 ;;
    --domain) DOMAIN="${2:-}"; shift ;;
    --email) EMAIL="${2:-}"; shift ;;
    --https) WANT_HTTPS=1 ;;
    --no-https) WANT_HTTPS=0 ;;
    --check) CHECK_ONLY=1 ;;
    --profile|--profiles) PROFILES="${2:-}"; shift ;;
    --languages) LANGUAGES="${2:-}"; shift ;;
    --books) BOOKS="${2:-}"; shift ;;
    -h|--help) sed -n '2,18p' "$0"; exit 0 ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
  shift
done
DOMAIN="${DOMAIN#http://}"; DOMAIN="${DOMAIN#https://}"; DOMAIN="${DOMAIN%%/*}"

bold() { printf "\033[1m%s\033[0m\n" "$*"; }
ok()   { printf "  \033[32m✓\033[0m %s\n" "$*"; }
warn() { printf "  \033[33m!\033[0m %s\n" "$*"; }
die()  { printf "\n  \033[31m✗ %s\033[0m\n\n" "$*"; exit 1; }

ask() { # ask VAR "Question" "default"
  local __var=$1 __q=$2 __def=$3 __ans
  if [ "$YES" = 1 ]; then printf -v "$__var" '%s' "$__def"; return; fi
  read -r -p "  $__q [$__def]: " __ans || true
  printf -v "$__var" '%s' "${__ans:-$__def}"
}

secret() { # random URL-safe string
  if command -v openssl >/dev/null 2>&1; then openssl rand -hex 16
  else LC_ALL=C tr -dc 'a-zA-Z0-9' </dev/urandom | head -c 32; fi
}

echo
bold "SOK Research Desk installer"
echo

# Look at the machine first: Docker, Coolify, a web server on 80/443, ports, memory, network
if [ "$CHECK_ONLY" = 1 ]; then
  bash scripts/preflight.sh ${DOMAIN:+--domain "$DOMAIN"}
  exit 0
fi
if [ ! -f .env ]; then
  PREFLIGHT_OUT=$(mktemp)
  RESDESK_PREFLIGHT_OUT="$PREFLIGHT_OUT" bash scripts/preflight.sh --brief ${DOMAIN:+--domain "$DOMAIN"} || true
  COOLIFY_HERE=$(sed -n 's/^COOLIFY=//p' "$PREFLIGHT_OUT"); DOCKER_STATE=$(sed -n 's/^DOCKER=//p' "$PREFLIGHT_OUT")
  rm -f "$PREFLIGHT_OUT"
  echo "  (./install.sh --check shows everything it looked at.)"
  echo
  if [ "${COOLIFY_HERE:-0}" = 1 ] && [ "$YES" != 1 ]; then
    read -r -p "  Coolify runs this server. Install here with ./install.sh anyway? [y/N]: " a || true
    [[ "${a:-N}" =~ ^[Yy] ]] || exit 0
  fi
  if [ -z "$MODE" ] && [ "$YES" != 1 ] && [ "${DOCKER_STATE:-}" != running ]; then
    warn "Docker isn't ready on this machine: choose 2 below, or set Docker up first (see the advice above)."
  fi
fi

# 0. Docker or native? ------------------------------------------------------------
if [ -z "$MODE" ] && [ -f .env ] && grep -q '^INSTALL_MODE=native' .env; then MODE=native; fi
if [ -z "$MODE" ]; then
  if [ "$YES" = 1 ]; then MODE=docker
  else
    echo "  How should Research Desk run?"
    echo "    1) In Docker containers  (recommended: isolated, easy to update and remove)"
    echo "    2) Directly on this computer  (native: Homebrew on macOS, apt on Ubuntu/Debian)"
    read -r -p "  Choose 1 or 2 [1]: " a || true
    case "${a:-1}" in 2) MODE=native ;; *) MODE=docker ;; esac
  fi
fi
ok "Install mode: $MODE"

# 1. Prerequisites ------------------------------------------------------------
bold "1/5  Checking your computer"
if [ "$MODE" = native ]; then
  case "$(uname -s)" in
    Darwin) command -v brew >/dev/null 2>&1 || die "Native install on macOS needs Homebrew: https://brew.sh (or use ./install.sh --docker)"
            ok "macOS with Homebrew" ;;
    Linux)  [ -f /etc/debian_version ] || die "Native install supports Ubuntu/Debian. Use ./install.sh --docker on other Linux systems."
            ok "$(. /etc/os-release && echo "$PRETTY_NAME") with apt" ;;
    *)      die "Native install supports macOS and Ubuntu/Debian. Use Docker here: ./install.sh --docker" ;;
  esac
else
  command -v docker >/dev/null 2>&1 || die "Docker is not installed. Get Docker Desktop from https://www.docker.com/products/docker-desktop/ and run this again (or use ./install.sh --native)."
  docker info >/dev/null 2>&1 || die "Docker is installed but not running. Start Docker Desktop (or 'sudo systemctl start docker') and run this again."
  docker compose version >/dev/null 2>&1 || die "Docker Compose v2 is missing. Update Docker Desktop, or install the docker-compose-plugin package."
  ok "Docker $(docker version --format '{{.Server.Version}}' 2>/dev/null) with Compose $(docker compose version --short)"
  MEM_BYTES=$(docker info --format '{{.MemTotal}}' 2>/dev/null || echo 0)
  if [ "${MEM_BYTES:-0}" -gt 0 ] && [ "$MEM_BYTES" -lt 3500000000 ]; then
    warn "Docker has less than 4 GB of memory. In Docker Desktop: Settings → Resources → Memory → 4 GB or more."
  else
    ok "Memory looks fine"
  fi
fi

# 2. Configuration --------------------------------------------------------------
echo
bold "2/5  Settings"
if [ -f .env ]; then
  ok "Found existing .env — keeping your settings and passwords"
  # shellcheck disable=SC1091
  set -a; . ./.env; set +a
else
  DEFAULT_PORT=8080; [ "$MODE" = native ] && DEFAULT_PORT=8000
  ask PORTAL_TITLE  "Portal name"                                        "SOK Research Desk"
  ask CONTACT_EMAIL "Your email (sent politely to the Internet Archive)" "$EMAIL"
  if [ -z "$DOMAIN" ] && [ "$YES" != 1 ]; then
    echo "  On a server with a DNS name (e.g. library.example.org) pointing at it, give the name for"
    echo "  its address and HTTPS. Leave it empty to use Research Desk on this computer only."
  fi
  ask DOMAIN        "Web address (domain name), or empty"                "$DOMAIN"
  DOMAIN="${DOMAIN#http://}"; DOMAIN="${DOMAIN#https://}"; DOMAIN="${DOMAIN%%/*}"
  ask HTTP_PORT     "Port to open in your browser"                       "$DEFAULT_PORT"
  ask SITE_NAME     "Internal site name"                                 "resdesk.localhost"
  ask LIBRARY_DIR   "Folder of IA-style book folders (optional)"         "./library"
  # what this library is (docs/staff-guide.md#features-and-your-institution): it decides which
  # features start on and how much of the machine they get; Settings → Features changes it later
  if [ -z "$PROFILES" ] && [ "$YES" != 1 ]; then
    echo
    echo "  What kind of institution is this? Give every number that fits (they combine), e.g. 2,4."
    echo "  Leave it empty to start with every feature on."
    echo "    1  Small library or school        4  Archive keeping its own copies"
    echo "    2  Public research portal          5  University or repository front"
    echo "    3  Members-only institution        6  Language-technology partner"
    echo "    7  Manuscript or palm-leaf library 8  Photograph archive"
  fi
  ask PROFILES      "Kinds of institution"                               "$PROFILES"
  PROFILES=$(echo "$PROFILES" | tr ' ' ',' \
    | sed 's/1/small/g;s/2/portal/g;s/3/members/g;s/4/archive/g;s/5/repository/g;s/6/langtech/g;s/7/manuscripts/g;s/8/photos/g')
  ask LANGUAGES     "Languages of the books, for OCR (codes like kan hin, or all)" "${LANGUAGES:-all}"
  # English too: Indic books carry English titles, names and numbers
  case " $LANGUAGES " in *" eng "*|" all ") ;; *) LANGUAGES="$LANGUAGES eng" ;; esac
  ask BOOKS         "About how many books will the library hold"         "${BOOKS:-1000}"
  ADMIN_PASSWORD=$(secret | cut -c1-16)
  cat > .env <<EOF
# Generated by install.sh on $(date). Keep this file private: it holds passwords.
PORTAL_TITLE="${PORTAL_TITLE}"
CONTACT_EMAIL="${CONTACT_EMAIL}"
HTTP_PORT=${HTTP_PORT}
SITE_NAME=${SITE_NAME}
BASE_URL=$([ -n "$DOMAIN" ] && echo "https://${DOMAIN}" || echo "http://localhost:${HTTP_PORT}")
LIBRARY_DIR=${LIBRARY_DIR}
# what kind of institution (Settings → Features), the books' languages for OCR, about how many books
RESDESK_PROFILES="${PROFILES}"
OCR_LANGS="${LANGUAGES:-all}"
RESDESK_BOOKS=${BOOKS:-1000}
ADMIN_PASSWORD=${ADMIN_PASSWORD}
DB_ROOT_PASSWORD=$(secret)
MEILI_MASTER_KEY=$(secret)$(secret)
# Use a prebuilt image instead of building locally (Docker mode), e.g.
# RESDESK_IMAGE=ghcr.io/servantsofknowledge/researchdesk
# RESDESK_TAG=latest
EOF
  chmod 600 .env
  ok "Wrote .env (passwords generated)"
  set -a; . ./.env; set +a
fi
HTTP_PORT=${HTTP_PORT:-8080}

if [ "$MODE" = native ]; then
  # 3–4. Native: system packages, bench, site (see scripts/install-native.sh) -------------
  echo
  bold "3–4/5  Installing on this computer (first time: 15–30 minutes)"
  YES=$YES bash scripts/install-native.sh || die "Native install failed (see messages above). Fix the problem and run ./install.sh --native again; it resumes."
  set -a; . ./.env; set +a
else
  if [ -z "${COMPOSE_FILE:-}" ]; then
    COMPOSE_FILE=compose.yaml
    if [ "${DEV_MODE:-0}" = 1 ]; then
      COMPOSE_FILE="$COMPOSE_FILE:compose.dev.yaml"
      ok "Developer mode is on (code runs live from this folder)"
    fi
    [ "${HTTPS:-0}" = 1 ] && COMPOSE_FILE="$COMPOSE_FILE:compose.https.yaml"
    export COMPOSE_FILE
  fi

  # 3. Build / pull ------------------------------------------------------------------
  echo
  bold "3/5  Preparing the software (first time: 10–20 minutes)"
  if [ -n "${RESDESK_IMAGE:-}" ]; then
    docker compose pull || die "Could not download ${RESDESK_IMAGE}:${RESDESK_TAG:-latest}"
  else
    docker compose build || die "Build failed. Check your internet connection and run ./install.sh again."
  fi
  docker compose pull db redis-cache redis-queue meilisearch --quiet 2>/dev/null || true
  ok "Images ready"

  # 4. Start ---------------------------------------------------------------------------
  echo
  bold "4/5  Starting services and creating the site"
  docker compose up -d
  printf "  waiting for site setup"
  for _ in $(seq 1 180); do
    CID=$(docker compose ps -a -q create-site 2>/dev/null || true)
    STATE=$( [ -n "$CID" ] && docker inspect -f '{{.State.Status}} {{.State.ExitCode}}' "$CID" 2>/dev/null || echo "none")
    case "$STATE" in
      "exited 0") echo; ok "Site ready"; break ;;
      exited*)    echo; docker compose logs --tail 40 create-site; die "Site setup failed (see log above)." ;;
    esac
    printf "."; sleep 5
  done
fi

printf "  waiting for the web server"
for _ in $(seq 1 60); do
  if curl -fs -o /dev/null "http://localhost:${HTTP_PORT}/library"; then echo; ok "Web server is up"; break; fi
  printf "."; sleep 3
done

# The public address, and HTTPS -------------------------------------------------------
if [ -n "$DOMAIN" ]; then
  echo
  bold "     Address: https://${DOMAIN}"
  ON_ALREADY=0
  { [ "${HTTPS:-0}" = 1 ] || [ "${HTTPS_NGINX:-0}" = 1 ]; } && [ "${HTTPS_DOMAIN:-}" = "$DOMAIN" ] && ON_ALREADY=1
  if [ "$MODE" = native ] && [ "$(uname -s)" != Linux ]; then
    ./resdesk.sh url "https://${DOMAIN}" >/dev/null && ok "The portal's address is https://${DOMAIN}"
    warn "HTTPS on macOS: put nginx or Caddy in front of port ${HTTP_PORT} (docs/installation.md#https-with-lets-encrypt)"
  else
    # Docker: its own nginx, or a site in the server's nginx if that already has ports 80/443.
    # Native (Linux): always the server's nginx (installed if missing), with socket.io routed.
    if [ "$ON_ALREADY" = 1 ] && [ "$WANT_HTTPS" != 1 ]; then
      WANT_HTTPS=0   # already on for this name (a re-run): nothing to do
      ok "HTTPS is already on for ${DOMAIN} (./resdesk.sh https status)"
    elif [ -z "$WANT_HTTPS" ]; then
      if [ "$YES" = 1 ]; then WANT_HTTPS=1; else
        echo "  A free certificate from Let's Encrypt needs ${DOMAIN} to point at this server and ports"
        echo "  80 and 443 open to the internet. Say no if another proxy (Caddy, Cloudflare…) handles HTTPS."
        read -r -p "  Get a certificate for ${DOMAIN} now? [Y/n]: " a || true
        case "${a:-Y}" in [Nn]*) WANT_HTTPS=0 ;; *) WANT_HTTPS=1 ;; esac
      fi
    fi
    if [ "$ON_ALREADY" = 1 ] && [ "$WANT_HTTPS" = 0 ]; then
      :
    elif [ "$WANT_HTTPS" = 1 ]; then
      ./resdesk.sh https on "$DOMAIN" ${EMAIL:+--email "$EMAIL"} \
        || warn "No certificate yet. When DNS and ports are ready: ./resdesk.sh https on ${DOMAIN}"
    else
      ./resdesk.sh url "https://${DOMAIN}" >/dev/null && ok "The portal's address is https://${DOMAIN} (HTTPS from your own proxy, to port ${HTTP_PORT})"
    fi
  fi
  set -a; . ./.env; set +a
fi

# 5. Sample data -------------------------------------------------------------------
echo
bold "5/5  Sample books"
if [ -z "$SAMPLE" ]; then
  if [ "$YES" = 1 ]; then SAMPLE=0; else
    read -r -p "  Ingest 20 Kannada books from Servants of Knowledge now to try it out? [Y/n]: " a || true
    case "${a:-Y}" in [Nn]*) SAMPLE=0 ;; *) SAMPLE=1 ;; esac
  fi
fi
if [ "$SAMPLE" = 1 ]; then
  ./resdesk.sh ingest --profile "SOK Kannada sample" --limit 20 || warn "Sample ingest had problems; you can retry with ./resdesk.sh ingest --profile \"SOK Kannada sample\""
else
  ok "Skipped. Later: ./resdesk.sh ingest --profile \"SOK Kannada sample\""
fi

echo
bold "All done 🎉"
cat <<EOF

  Portal (public):   ${BASE_URL%/}/
  Admin (Desk):      ${BASE_URL%/}/app/research-desk$( [ "${BASE_URL%/}" != "http://localhost:${HTTP_PORT}" ] && printf "\n  On this server:    http://localhost:%s/" "${HTTP_PORT}")
  Login:             Administrator
  Password:          ${ADMIN_PASSWORD}      (also in the .env file)
  Running as:        ${MODE}$( [ "$MODE" = native ] && echo " (bench at ${BENCH_DIR:-~/researchdesk-bench})" )

  Next steps:
    • Add your logo:          Desk → Research Desk → Settings → Logo & Branding
    • Choose what to ingest:  Desk → Research Desk → Ingest Profiles
    • Or from the terminal:   ./resdesk.sh count  --collection ServantsOfKnowledge --filter "language:kan"
                              ./resdesk.sh ingest --collection ServantsOfKnowledge --filter "language:kan" --limit 100
    • Change the address:     ./resdesk.sh url https://library.example.org
    • Everyday commands:      ./resdesk.sh help
    • Documentation:          docs/README.md

EOF
