#!/usr/bin/env bash
# Browser tests of the portal (sok_resdesk/tests/ui): fetch axe-core and jquery once, then run them.
#   scripts/ui-tests.sh            needs: pip install pytest playwright jinja2; playwright install chromium
# Without a browser or the files the tests skip, they do not fail.
set -eu
cd "$(dirname "$0")/.."
CACHE="${RD_UI_CACHE:-.cache/ui}"
mkdir -p "$CACHE/axe" "$CACHE/jquery"
fetch() { # name spec dir
  [ -d "$CACHE/$1/package" ] && return 0
  (cd "$CACHE/$1" && npm pack -s "$2" >/dev/null && tar xzf ./*.tgz)
}
fetch axe 'axe-core@4'
fetch jquery 'jquery@3'
export RD_UI_CACHE="$PWD/$CACHE"
exec python3 -m pytest -q -p no:cacheprovider -o python_files='ui_*.py' sok_resdesk/tests/ui "$@"
