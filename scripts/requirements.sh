#!/usr/bin/env bash
# ---------------------------------------------------------------------------
#  SOK Research Desk: install the tools Research Desk uses (native installs)
#
#    ./resdesk.sh requirements install python   Python packages of Research Desk (boto3…)
#    ./resdesk.sh requirements install ocr      Tesseract and its Indic language models
#
#  The Server page's Requirements card runs the same through the updater helper. On Docker
#  everything comes with the image: upgrade (./upgrade.sh, or Server → Upgrade) instead.
#  Exit 3: it needs an administrator (sudo with a password): the command to run is printed.
# ---------------------------------------------------------------------------
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; [ -f .env ] && . ./.env; set +a
BENCH_DIR="${BENCH_DIR:-$HOME/researchdesk-bench}"
OCR_LANGS="${OCR_LANGS:-kan hin mar san tam tel mal ben guj pan ori eng}"
ok()  { printf "  \033[32m✓\033[0m %s\n" "$*"; }
die() { printf "  \033[31m✗\033[0m %s\n" "$*"; exit "${2:-1}"; }
have() { command -v "$1" >/dev/null 2>&1; }

if [ "${INSTALL_MODE:-docker}" != native ]; then
  echo "This is a Docker install: the tools come with the Research Desk image."
  echo "Upgrade to bring the image up to date:  ./upgrade.sh   (or Server → Upgrade in the Desk)"
  exit 0
fi

as_admin() {
  # root, or sudo that needs no password (the updater helper can't type one)
  if [ "$(id -u)" -eq 0 ]; then "$@"
  elif have sudo && sudo -n true 2>/dev/null; then sudo -n "$@"
  else
    echo "This needs an administrator. Run on the server:"
    echo "    sudo $*"
    exit 3
  fi
}

part="${2:-}"
[ "${1:-}" = install ] || die "Usage: $0 install python|ocr"
case "$part" in
  python)
    have uv || die "uv is missing: run ./install.sh --native again"
    (cd "$BENCH_DIR" && uv pip install --python env/bin/python -e apps/sok_resdesk)
    ok "Research Desk's Python packages"
    ;;
  ocr)
    if [ "$(uname -s)" = Darwin ]; then
      have brew || die "Homebrew is required on macOS: https://brew.sh"
      brew list --versions tesseract >/dev/null 2>&1 || brew install tesseract
      brew list --versions tesseract-lang >/dev/null 2>&1 || brew install tesseract-lang
    elif [ -f /etc/debian_version ]; then
      pkgs="tesseract-ocr"
      for l in $OCR_LANGS; do pkgs="$pkgs tesseract-ocr-$l"; done
      as_admin env DEBIAN_FRONTEND=noninteractive apt-get install -y -q $pkgs
    else
      die "Install Tesseract and its language models with this system's package manager."
    fi
    ok "Tesseract $(tesseract --version 2>&1 | head -1 | awk '{print $2}') with $(tesseract --list-langs 2>/dev/null | tail -n +2 | tr '\n' ' ')"
    ;;
  *) die "Usage: $0 install python|ocr" ;;
esac
