#!/usr/bin/env bash
# What an upgrade needs to restart, from the files it changes (sourced by upgrade.sh).
#
#   git diff --name-only OLD NEW | upgrade_plan
#
# prints one line, "<plan>: <why>", where plan is
#   web    the web part only: nothing the background workers run has changed
#   roll   the workers too, one at a time (each finishes its job first)
#   full   everything: the images, services or Frappe itself changed
# Kept apart from upgrade.sh so it can be tested (sok_resdesk/tests/unit_upgrade_plan.py).
upgrade_plan() {
  local f full="" workers=""
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    case "$f" in
      compose*.yaml | Dockerfile | docker/* | pyproject.toml | install.sh)
        [ -n "$full" ] || full="$f" ;;
      sok_resdesk/tests/* | sok_resdesk/__init__.py) ;; # the version number alone changes every release
      sok_resdesk/*.py)
        [ -n "$workers" ] || workers="$f" ;;
    esac
  done
  if [ -n "$full" ]; then
    echo "full: $full changed (images or services)"
  elif [ -n "$workers" ]; then
    echo "roll: Python the workers run changed (for example $workers)"
  else
    echo "web: only documents, screens or data definitions changed; nothing the workers run"
  fi
}
