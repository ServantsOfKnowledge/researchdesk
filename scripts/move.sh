# Moving an installation to another server, or between Docker and native.
# Sourced by resdesk.sh (it provides MODE, SITE, BENCH_DIR, bench, set_env and .env):
#   ./resdesk.sh export [FILE]                   one archive with everything needed
#   ./resdesk.sh import FILE [--base-url URL] [--yes]
#   ./resdesk.sh move-to USER@HOST[:DIR] [--base-url URL] [--with-library] [--port N]
# See docs/moving.md.

move_tmp() { mktemp -d "${TMPDIR:-/tmp}/resdesk-move.XXXXXX"; }

# Run a command where the site lives, and copy files in and out of it.
site_run() {
  if [ "$MODE" = native ]; then (cd "$BENCH_DIR" && "$@"); else docker compose exec -T backend "$@"; fi
}
site_path() { # path of the site folder, as seen by site_run
  if [ "$MODE" = native ]; then echo "$BENCH_DIR/sites/$SITE"; else echo "sites/$SITE"; fi
}
copy_out() { # copy_out <path in site_run's world> <local file>
  if [ "$MODE" = native ]; then cp -p "$1" "$2"; else docker compose exec -T backend cat "$1" > "$2"; fi
}
copy_in() { # copy_in <local file> <name>  → prints the path the site can read it from
  if [ "$MODE" = native ]; then
    (cd "$(dirname "$1")" && echo "$(pwd)/$(basename "$1")")
  else
    docker compose cp "$1" "backend:/tmp/$2" >/dev/null 2>&1
    docker compose exec -T -u root backend chown frappe "/tmp/$2"
    echo "/tmp/$2"
  fi
}

rd_export() {
  OUT="${1:-site-backups/resdesk-move-$(date +%Y%m%d-%H%M).tar.gz}"
  mkdir -p "$(dirname "$OUT")"
  if [ "$MODE" != native ] && [ -z "$(docker compose ps -q --status running backend 2>/dev/null)" ]; then
    echo "Start Research Desk first (./resdesk.sh start): the export reads the running site."; exit 1
  fi
  T=$(move_tmp); trap 'rm -rf "$T"' EXIT
  echo "1/4 Backing up the database and files…"
  site_run bench --site "$SITE" backup --with-files >/dev/null
  DIR="$(site_path)/private/backups"
  PREFIX=$(site_run bash -c "cd '$DIR' && ls -t *-database.sql.gz | head -1" | tr -d '\r' | sed 's/-database\.sql\.gz$//')
  [ -n "$PREFIX" ] || { echo "No backup was made; see ./resdesk.sh logs."; exit 1; }
  copy_out "$DIR/$PREFIX-database.sql.gz" "$T/database.sql.gz"
  copy_out "$DIR/$PREFIX-files.tar" "$T/public-files.tar"
  copy_out "$DIR/$PREFIX-private-files.tar" "$T/private-files.tar"

  echo "2/4 Page text (so the new server can rebuild search without downloading)…"
  site_run bash -c "cd '$(site_path)/private' && [ -d resdesk-pages ] && tar -czf - resdesk-pages || true" > "$T/page-text.tar.gz"

  echo "3/4 Keys and settings…"
  site_run cat "$(site_path)/site_config.json" > "$T/site_config.json.full"
  python3 - "$T" "$MODE" "$SITE" <<'PY'
import json, sys, os, datetime, re
t, mode, site = sys.argv[1:4]
conf = json.load(open(os.path.join(t, "site_config.json.full")))
os.remove(os.path.join(t, "site_config.json.full"))
# only what the new site needs: the key that unlocks saved passwords (push targets, search key…)
json.dump({"encryption_key": conf.get("encryption_key")}, open(os.path.join(t, "keys.json"), "w"))
env = {}
for line in open(".env"):
    m = re.match(r"^([A-Z_]+)=(.*)$", line.strip())
    if m and m.group(1) in ("PORTAL_TITLE", "CONTACT_EMAIL", "BASE_URL", "TIMEZONE", "COUNTRY", "CURRENCY"):
        env[m.group(1)] = m.group(2).strip('"')
version = re.search(r'__version__ = "([^"]+)"', open("sok_resdesk/__init__.py").read()).group(1)
# where the book folders were (native installs keep real paths): the import relinks them
library_dir = conf.get("resdesk_library_dir") or "/library-source"
json.dump({"format": 1, "version": version, "made": datetime.datetime.now().isoformat(timespec="seconds"),
           "from_mode": mode, "site": site, "library_dir": library_dir, "settings": env},
          open(os.path.join(t, "manifest.json"), "w"), indent=1)
PY
  echo "4/4 Packing…"
  tar -czf "$OUT" -C "$T" .
  chmod 600 "$OUT"
  SIZE=$(du -h "$OUT" | cut -f1)
  echo
  echo "Exported to $OUT ($SIZE)."
  echo "It holds the catalogue, readers and staff, settings, uploaded files, page text and the key that"
  echo "unlocks saved passwords: keep it private. Your book folders (LIBRARY_DIR) are not in it."
  echo "On the new server: ./resdesk.sh import $(basename "$OUT")"
}

rd_import() {
  F=""; BASE=""; YES=0
  while [ $# -gt 0 ]; do
    case "$1" in
      --base-url) BASE="$2"; shift 2 ;;
      --yes|-y) YES=1; shift ;;
      *) F="$1"; shift ;;
    esac
  done
  [ -f "$F" ] || { echo "Usage: ./resdesk.sh import FILE.tar.gz [--base-url https://new.address] [--yes]"; exit 1; }
  if [ "$MODE" != native ] && [ -z "$(docker compose ps -q --status running backend 2>/dev/null)" ]; then
    echo "Start Research Desk first (./resdesk.sh start). Install it with ./install.sh if this is a new server."; exit 1
  fi
  T=$(move_tmp); trap 'rm -rf "$T"' EXIT
  tar -xzf "$F" -C "$T"
  [ -f "$T/manifest.json" ] && [ -f "$T/database.sql.gz" ] || { echo "$F is not a Research Desk export."; exit 1; }
  read -r FROM_VERSION FROM_SITE <<< "$(python3 -c "import json;m=json.load(open('$T/manifest.json'));print(m['version'], m.get('site',''))")"
  HERE=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' sok_resdesk/__init__.py)
  if ! python3 -c "import sys;v=lambda s:[int(x) for x in s.split('.')];sys.exit(0 if v('$HERE')>=v('$FROM_VERSION') else 1)"; then
    echo "The export comes from Research Desk $FROM_VERSION; this install is $HERE. Upgrade first: ./upgrade.sh"; exit 1
  fi
  echo "Importing $FROM_SITE (Research Desk $FROM_VERSION) into $SITE ($MODE)."
  if [ "$YES" != 1 ]; then
    read -r -p "This replaces everything in this install's catalogue. Continue? [y/N]: " a; [[ "$a" =~ ^[Yy] ]] || exit 0
  fi

  echo "1/5 Restoring the database and files…"
  DB=$(copy_in "$T/database.sql.gz" rd-move-db.sql.gz)
  PUB=$(copy_in "$T/public-files.tar" rd-move-public.tar)
  PRIV=$(copy_in "$T/private-files.tar" rd-move-private.tar)
  bench --force restore "$DB" --with-public-files "$PUB" --with-private-files "$PRIV" --db-root-password "$DB_ROOT_PASSWORD"

  echo "2/5 Keys…"
  KEY=$(python3 -c "import json;print(json.load(open('$T/keys.json')).get('encryption_key') or '')")
  [ -n "$KEY" ] && bench set-config -- encryption_key "$KEY" >/dev/null   # "--": keys can start with "-"

  echo "3/5 Page text…"
  if [ -s "$T/page-text.tar.gz" ]; then
    PT=$(copy_in "$T/page-text.tar.gz" rd-move-pages.tar.gz)
    site_run bash -c "mkdir -p '$(site_path)/private' && tar -xzf '$PT' -C '$(site_path)/private'"
  fi
  [ "$MODE" = native ] || docker compose exec -T -u root backend bash -c "rm -f /tmp/rd-move-*"

  echo "4/5 Updating to this install…"
  bench migrate >/dev/null
  if [ "$MODE" = native ]; then MURL="http://127.0.0.1:${MEILI_PORT:-7700}"; else MURL="http://meilisearch:7700"; fi
  ARGS=(--meili-url "$MURL" --meili-key "$MEILI_MASTER_KEY")
  [ -n "$BASE" ] && ARGS+=(--base-url "$BASE")
  bench resdesk configure "${ARGS[@]}" >/dev/null
  [ -n "$BASE" ] && set_env BASE_URL "$BASE"
  # book folders: point books and profiles at /library-source, which is this install's LIBRARY_DIR
  OLD_LIB=$(python3 -c "import json;print(json.load(open('$T/manifest.json')).get('library_dir') or '/library-source')")
  [ "$OLD_LIB" != "/library-source" ] && bench resdesk relink-folders --from "$OLD_LIB" | tail -1
  bench clear-cache >/dev/null

  echo "5/5 Rebuilding the search index in the background (from the page text: no downloads)…"
  bench resdesk reindex --background >/dev/null || echo "  (run ./resdesk.sh reindex --background once it's up)"
  [ "$MODE" = native ] || docker compose restart backend queue scheduler frontend >/dev/null
  echo
  echo "Imported. Search fills up over the next minutes (Background Jobs shows progress)."
  echo "- Log in with the Administrator password of the OLD server (change it: ./resdesk.sh password)."
  [ -z "$BASE" ] && echo "- If the address changed, set Settings → Public Base URL (or re-run with --base-url)."
  echo "- Copy your book folders (LIBRARY_DIR) separately if you ingest from folders; see docs/moving.md."
}

rd_move_to() {
  DEST=""; BASE=""; LIB=0; PORT=22
  while [ $# -gt 0 ]; do
    case "$1" in
      --base-url) BASE="$2"; shift 2 ;;
      --with-library) LIB=1; shift ;;
      --port) PORT="$2"; shift 2 ;;
      *) DEST="$1"; shift ;;
    esac
  done
  [ -n "$DEST" ] || { echo "Usage: ./resdesk.sh move-to USER@HOST[:DIR] [--base-url URL] [--with-library] [--port N]"; exit 1; }
  HOST="${DEST%%:*}"; RDIR="researchdesk"; [[ "$DEST" == *:* ]] && RDIR="${DEST#*:}"
  SSH=(ssh -p "$PORT" -o BatchMode=yes "$HOST")
  echo "Checking $HOST…"
  "${SSH[@]}" "test -x '$RDIR/resdesk.sh' && test -f '$RDIR/.env'" 2>/dev/null || {
    echo "Research Desk isn't installed in ~/$RDIR on $HOST (or SSH needs a key: ssh-copy-id $HOST)."
    echo "Install it there first:  git clone https://github.com/ServantsOfKnowledge/researchdesk.git $RDIR && cd $RDIR && ./install.sh"
    exit 1
  }
  FILE="site-backups/resdesk-move-$(date +%Y%m%d-%H%M).tar.gz"
  rd_export "$FILE"
  echo "Copying $(du -h "$FILE" | cut -f1) to $HOST…"
  scp -P "$PORT" -q "$FILE" "$HOST:$RDIR/$(basename "$FILE")"
  if [ "$LIB" = 1 ] && [ -n "${LIBRARY_DIR:-}" ] && [ -d "$LIBRARY_DIR" ]; then
    RLIB=$("${SSH[@]}" "cd '$RDIR' && sed -n 's/^LIBRARY_DIR=//p' .env | tr -d '\"'")
    [ -n "$RLIB" ] || RLIB="$RDIR/library"
    echo "Copying book folders $LIBRARY_DIR → $HOST:$RLIB (only what's new or changed)…"
    rsync -a --info=progress2 -e "ssh -p $PORT" "$LIBRARY_DIR/" "$HOST:$RLIB/"
  fi
  ARGS="--yes"; [ -n "$BASE" ] && ARGS="$ARGS --base-url '$BASE'"
  "${SSH[@]}" "cd '$RDIR' && ./resdesk.sh import '$(basename "$FILE")' $ARGS && rm -f '$(basename "$FILE")'"
  echo
  echo "Moved to $HOST. This install still runs; stop it with ./resdesk.sh stop once the new one looks right."
  echo "A copy of the export stays in $FILE (it holds the key to saved passwords: delete it when done)."
}
