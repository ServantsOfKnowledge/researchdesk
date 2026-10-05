#!/usr/bin/env bash
# Make your commits show as "Verified" on GitHub: sign them with an SSH key.
#
#   scripts/setup-signing.sh you@example.org [--global]
#
# Run it on the machine where you commit. It makes an ed25519 signing key (or uses the one
# there), points git at it, and prints the public key to add on GitHub as a *Signing Key*:
# Settings → SSH and GPG keys → New SSH key → Key type: Signing Key. The email must be a
# verified address of your GitHub account (or your ...@users.noreply.github.com address).
set -euo pipefail

EMAIL="${1:-}"
SCOPE="--local"
[ "${2:-}" = "--global" ] && SCOPE="--global"
if [ -z "$EMAIL" ]; then
  echo "usage: $0 you@example.org [--global]" >&2
  exit 2
fi

KEY="${SIGNING_KEY:-$HOME/.ssh/github-signing}"
if [ ! -f "$KEY" ]; then
  mkdir -p "$(dirname "$KEY")"
  ssh-keygen -t ed25519 -f "$KEY" -C "$EMAIL" -N ""
  echo "Made $KEY (no passphrase: add one with  ssh-keygen -p -f $KEY  if you like)."
fi

git config $SCOPE user.email "$EMAIL"
git config $SCOPE gpg.format ssh
git config $SCOPE user.signingkey "$KEY.pub"
# so that `git log --show-signature` can check your own signatures locally
ALLOWED="$(dirname "$KEY")/allowed_signers"
grep -qF "$(cut -d' ' -f1-2 "$KEY.pub")" "$ALLOWED" 2>/dev/null \
  || echo "$EMAIL $(cut -d' ' -f1-2 "$KEY.pub")" >> "$ALLOWED"
git config $SCOPE gpg.ssh.allowedSignersFile "$ALLOWED"
git config $SCOPE commit.gpgsign true
git config $SCOPE tag.gpgsign true

echo
echo "Git now signs every commit${SCOPE:+ ($SCOPE)} with $KEY.pub."
echo
echo "Last step, once: add this public key on GitHub as a SIGNING key"
echo "(github.com → Settings → SSH and GPG keys → New SSH key → Key type: Signing Key):"
echo
cat "$KEY.pub"
echo
echo "Then check:  git commit --allow-empty -m test && git log --show-signature -1"
echo "(new commits only: earlier ones stay unsigned; rewriting pushed history would break the release tags)."
