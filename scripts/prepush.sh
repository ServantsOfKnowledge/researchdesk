#!/usr/bin/env bash
# The checks every push must pass (the same ones CI runs first), in one place.
#
#   scripts/prepush.sh              check this folder
#   scripts/prepush.sh --dir PATH   check another copy (a commit exported with git archive)
#   scripts/prepush.sh --full       also run every pure test (pytest -q)
#
# Used by the push guard (.claude/hooks/guard.py), the /release skill and pre-commit.
set -u
DIR="."
FULL=0
while [ $# -gt 0 ]; do
  case "$1" in
    --dir) DIR="$2"; shift 2 ;;
    --full) FULL=1; shift ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done
cd "$DIR" || exit 2
fail=0
step() { printf '\n== %s\n' "$1"; }

step "ruff check"
ruff check sok_resdesk scripts || fail=1
step "ruff format --check"
ruff format --check sok_resdesk scripts || fail=1
step "docs match the code (test_docs: pages, anchors, API, doctypes, changelog = version)"
python3 -m pytest -q sok_resdesk/tests/test_docs.py || fail=1
step "shell scripts parse"
bash -n install.sh resdesk.sh upgrade.sh scripts/*.sh docker/create-site.sh || fail=1
if [ "$FULL" = 1 ]; then
  step "every pure test"
  python3 -m pytest -q || fail=1
fi

# information, never a failure: which documentation files this push changes, so none changes unasked
if git rev-parse --git-dir >/dev/null 2>&1 && git rev-parse -q --verify origin/main >/dev/null 2>&1; then
  step "documentation files that differ from origin/main"
  git diff --stat origin/main -- docs README.md CHANGELOG.md 2>/dev/null | tail -20 || true
fi

if [ "$fail" = 0 ]; then echo; echo "prepush: all checks passed"; else echo; echo "prepush: FAILED" >&2; fi
exit "$fail"
