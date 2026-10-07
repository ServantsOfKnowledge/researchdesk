#!/usr/bin/env bash
# PostToolUse hook (Edit|Write): keep Python files formatted the way CI checks them
# (ruff format; tabs, 110 columns). Python only: documentation and everything else is never touched.
f=$(jq -r '.tool_input.file_path // empty' 2>/dev/null)
case "$f" in
  *.py) command -v ruff >/dev/null 2>&1 && ruff format -q "$f" >/dev/null 2>&1 ;;
esac
exit 0
