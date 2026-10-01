#!/usr/bin/env bash
# Make a release: checks the docs and changelog, sets the version, commits and tags.
#   scripts/release.sh 0.9.0
# Then push:  git push origin main --tags
set -euo pipefail
cd "$(dirname "$0")/.."

V="${1:-}"
[[ "$V" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "Usage: scripts/release.sh X.Y.Z"; exit 1; }
git rev-parse "v$V" >/dev/null 2>&1 && { echo "v$V already exists."; exit 1; }

top=$(grep -m1 '^## ' CHANGELOG.md | awk '{print $2}')
[ "$top" = "$V" ] || { echo "CHANGELOG.md must start with a '## $V (date): …' entry (it starts with $top)."; exit 1; }

sed -i.bak "s/^__version__ = \".*\"/__version__ = \"$V\"/" sok_resdesk/__init__.py && rm -f sok_resdesk/__init__.py.bak
python3 scripts/gen_docs.py
if command -v pytest >/dev/null 2>&1; then
  pytest -q sok_resdesk/tests/test_docs.py sok_resdesk/tests/test_core.py sok_resdesk/tests/test_push.py
else
  echo "(pytest not installed: skipping the doc and unit checks; CI runs them)"
fi

git add -A
git diff --cached --quiet || git commit -q -m "Release v$V"
git tag -a "v$V" -m "v$V"
echo "Tagged v$V. Publish it: scripts/publish.sh (GitHub main + tags; or bring a bundle to the publishing machine: scripts/publish.sh FILE.bundle)"
