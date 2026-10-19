#!/usr/bin/env bash
# ---------------------------------------------------------------------------
#  Make an offline install bundle: Research Desk and every image it runs, in one archive, for a
#  machine with no internet (a locked-down network, a records office).
#
#    scripts/make-bundle.sh [--edition standard|governance] [--out DIR]
#
#  Run it on a machine that has Docker, the internet and this checkout. It builds the image of the
#  edition, pulls the database, cache and search images, and writes
#  DIR/resdesk-bundle-<version>-<edition>-<arch>.tar (default DIR: dist/). On the other machine:
#
#    tar -xf resdesk-bundle-….tar && cd researchdesk && ./install.sh --offline
#
#  The bundle is for the machine type it was made on (amd64 or arm64). It holds no .env and no
#  data. To update an offline install, unpack a newer bundle over the folder and run
#  ./install.sh --offline again. See docs/installation.md#offline-install-bundle.
# ---------------------------------------------------------------------------
set -euo pipefail
cd "$(dirname "$0")/.."

EDITION=standard; OUT=dist
while [ $# -gt 0 ]; do
  case "$1" in
    --edition) EDITION="${2:-}"; shift ;;
    --out) OUT="${2:-}"; shift ;;
    -h|--help) sed -n '2,17p' "$0"; exit 0 ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
  shift
done
case "$EDITION" in standard|governance) ;; *) echo "--edition is standard or governance"; exit 1 ;; esac
die() { printf "\n  ✗ %s\n\n" "$*"; exit 1; }
command -v docker >/dev/null 2>&1 || die "Docker is needed to make a bundle."
git rev-parse --git-dir >/dev/null 2>&1 || die "Run this in a git checkout of Research Desk."
[ -z "$(git status --porcelain --untracked-files=no)" ] || die "This checkout has uncommitted changes; the bundle holds what is committed. Commit or stash them first."

VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' sok_resdesk/__init__.py)"
ARCH="$(docker version --format '{{.Server.Arch}}')"
NAME="resdesk-bundle-${VERSION}-${EDITION}-${ARCH}"
mkdir -p "$OUT"
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT

# The image is built here, never pulled: the edition decides what is in it
unset RESDESK_IMAGE RESDESK_TAG COMPOSE_FILE
export RESDESK_EDITION="$EDITION"
# compose wants these set to read the file; they are not baked into any image (install.sh makes real ones)
export DB_ROOT_PASSWORD=bundle MEILI_MASTER_KEY=bundle ADMIN_PASSWORD=bundle
echo ">> building the ${EDITION} image"
docker compose build
docker compose pull db redis-cache redis-queue meilisearch --quiet
IMAGES="$(docker compose config --images | sort -u)"
echo ">> images: $(echo $IMAGES | tr '\n' ' ')"

mkdir -p "$WORK/researchdesk/bundle"
git archive HEAD | tar -x -C "$WORK/researchdesk"
# shellcheck disable=SC2086
docker save $IMAGES | gzip > "$WORK/researchdesk/bundle/images.tar.gz"
{
  echo "version=$VERSION"
  echo "edition=$EDITION"
  echo "arch=$ARCH"
  echo "images=$(echo $IMAGES | tr '\n' ' ')"
  echo "made=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} > "$WORK/researchdesk/bundle/MANIFEST"
if command -v sha256sum >/dev/null 2>&1; then SUM="sha256sum"; else SUM="shasum -a 256"; fi
(cd "$WORK/researchdesk/bundle" && $SUM images.tar.gz MANIFEST > SHA256SUMS)
tar -C "$WORK" -cf "$OUT/$NAME.tar" researchdesk
echo ">> $OUT/$NAME.tar ($(du -h "$OUT/$NAME.tar" | cut -f1))"
