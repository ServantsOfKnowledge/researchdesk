#!/usr/bin/env bash
# Put a release on GitHub: the newest release tag becomes the `main` branch there, so anyone who
# runs `git clone` gets the current version, and every tag goes up with it.
#
#   scripts/publish.sh                    publish the newest release tag in this folder
#   scripts/publish.sh FILE.bundle        first bring in a release bundle, then publish it
#   scripts/publish.sh --check            only show what GitHub has and what would change
#
# Works whatever this folder has checked out (a branch, or a release tag after ./upgrade.sh).
# main only ever moves forward: if GitHub's main has commits this folder doesn't, it stops.
set -euo pipefail
cd "$(dirname "$0")/.."

CHECK=0
BUNDLE=""
for a in "$@"; do
  case "$a" in
    --check) CHECK=1 ;;
    -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
    *) BUNDLE="$a" ;;
  esac
done
REMOTE="${PUBLISH_REMOTE:-origin}"
die() { echo "✗ $*" >&2; exit 1; }

if [ -n "$BUNDLE" ]; then
  [ -f "$BUNDLE" ] || die "No such bundle: $BUNDLE"
  git bundle verify -q "$BUNDLE" >/dev/null 2>&1 || die "$BUNDLE doesn't fit this folder (git bundle verify $BUNDLE says why)"
  git fetch -q "$BUNDLE" '+refs/tags/*:refs/tags/*' 'refs/heads/main:refs/remotes/bundle/main'
  echo "✓ Brought in $BUNDLE"
fi

LATEST=$(git tag -l 'v[0-9]*' --sort=-v:refname | head -1)
[ -n "$LATEST" ] || die "No release tags here (make one with scripts/release.sh X.Y.Z)"
TARGET=$(git rev-parse "$LATEST^{commit}")
VERSION=$(git show "$TARGET:sok_resdesk/__init__.py" | sed -n 's/^__version__ = "\(.*\)"/\1/p')

git fetch -q "$REMOTE" main 2>/dev/null || die "Can't reach $REMOTE (git remote -v)"
REMOTE_MAIN=$(git rev-parse "$REMOTE/main")
REMOTE_VERSION=$(git show "$REMOTE_MAIN:sok_resdesk/__init__.py" | sed -n 's/^__version__ = "\(.*\)"/\1/p')
echo "GitHub's main: $REMOTE_VERSION ($(git log -1 --format=%h "$REMOTE_MAIN"))"
echo "Newest release here: $LATEST ($VERSION, $(git log -1 --format=%h "$TARGET"))"

if [ "$REMOTE_MAIN" = "$TARGET" ]; then
  echo "✓ GitHub's main is already $LATEST."
elif git merge-base --is-ancestor "$TARGET" "$REMOTE_MAIN"; then
  echo "✓ GitHub's main is already past $LATEST."
  TARGET="$REMOTE_MAIN"
else
  git merge-base --is-ancestor "$REMOTE_MAIN" "$TARGET" \
    || die "GitHub's main has commits that $LATEST doesn't (someone pushed elsewhere). Merge them first: git log $TARGET..$REMOTE/main"
  [ "$CHECK" = 1 ] && { echo "Would move GitHub's main to $LATEST and push the tags. Run without --check."; exit 0; }
  git push "$REMOTE" "$TARGET:refs/heads/main"
  echo "✓ GitHub's main is now $LATEST: a fresh git clone gets $VERSION"
fi
[ "$CHECK" = 1 ] && exit 0
git push -q "$REMOTE" --tags && echo "✓ Tags pushed"

# keep this folder's own main branch in step (without touching what is checked out)
if [ "$(git symbolic-ref -q --short HEAD || true)" = main ]; then
  git merge -q --ff-only "$TARGET" 2>/dev/null || echo "! This folder's main has its own commits: not moved"
else
  git branch -f main "$TARGET" >/dev/null && echo "✓ This folder's main branch now points at $LATEST too"
fi
