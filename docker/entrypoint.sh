#!/bin/bash
# Link the assets baked into the image into the (shared) sites volume.
set -e
ASSETS_PATH="/home/frappe/frappe-bench/sites/assets"
BAKED_PATH="/home/frappe/frappe-bench/assets"
if [ -d "$BAKED_PATH" ]; then
  rm -rf "$ASSETS_PATH"
  ln -s "$BAKED_PATH" "$ASSETS_PATH"
fi
exec "$@"
