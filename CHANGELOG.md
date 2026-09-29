# Changelog

## 0.5.3 (2026-09-30): recover from a full Docker disk

- The configurator recreates `common_site_config.json` when it is empty or damaged (a full
  Docker disk can truncate it, after which every bench command fails)
- Meilisearch upgrades its index files in place (`MEILI_UPGRADE_DB`) when a newer patch
  release of the image is pulled, instead of refusing to start
- `./upgrade.sh` checks Docker's free disk space before building and stops with instructions
  when less than about 6 GB is left

## 0.5.2 (2026-09-30): upgrade fixes

- `./upgrade.sh` no longer waits forever at "Restart and migrate" when the configurator
  container keeps failing (usually Docker out of disk space): it stops after three restarts, or
  after 10 minutes, and shows each container's state, its last log lines and how to free space
- Old image layers from previous builds are removed after each upgrade build, so repeated
  upgrades don't fill Docker's disk. Data volumes are never touched

## 0.5.1 (2026-09-30): upgrade fixes

- `./upgrade.sh` no longer hangs silently at the backup step: the backup needs only the
  database, so it works even when the web containers won't start (it uses a one-off container),
  shows its progress, and stops with the reason and a `--no-backup` hint if it can't finish
- When Docker can't start the containers, or the migration container never starts, the upgrade
  stops within two minutes and prints each container's state and last log lines, instead of
  waiting 15 minutes
- `./resdesk.sh backup` uses the same approach

## 0.5.0 (2026-09-30): members-only books and reader accounts

- Each book has **Who can see it**: *Public*, *Login to read* (find and cite openly; reading,
  search inside and the PDF need a login) or *Login to find* (only logged-in readers know it
  exists). Enforced in portal search, book pages, page search, search inside, local PDFs,
  citations, MARCXML, stats and OAI-PMH
- Site setting for visitors who are not logged in: *Each item's setting*, *Records only*
  (a public catalogue) or *Login required* (an internal library)
- Reader accounts: *Admins add readers*, *Anyone can sign up* or *Sign up, admin approves*
  with a **Reader Requests** queue, bulk approve/reject, manager notifications and emails.
  New role **ResDesk Reader** (portal only); `./resdesk.sh add-reader EMAIL`
- Bulk changes: ticked rows or everything matching a filter in the Desk Items list, every
  result of a portal search (staff bar), a whole ingest profile, or
  `./resdesk.sh access <visibility> --collection/--profile/--language/--ids/--all`.
  Updates the search index in place, no re-index; big batches run in the background
- **Access rules** by collection, subject, language, author, source or profile set the
  visibility of new books; an ingest profile's own setting comes first; **Apply Access Rules**
  updates existing books without touching manual choices. `ingest --visibility` on the CLI
- OAI-PMH shares what guests can find by default, or all published records, or is off
- Upgrade note: existing books become *Public*; nothing needs re-indexing

## 0.4.0 (2026-09-29): native install and upgrades

- `./install.sh --native` (or choose at the prompt): installs MariaDB, Redis, Meilisearch,
  Python 3.14 (uv), Node 24 (nvm) and a Frappe v16 bench linked to the checkout, on macOS
  (Homebrew) or Ubuntu/Debian (apt). Idempotent; tested on a clean Ubuntu 24.04
- Native runtime: gunicorn with static files and default-site routing
  (`sok_resdesk.native_wsgi`), Meilisearch and extra workers in the bench Procfile;
  `./resdesk.sh` start/stop/status/logs/workers/backup/restore/dev/uninstall work natively
- `./upgrade.sh`: check, backup, fetch a release/tag/main, update Frappe patch releases,
  migrate, re-apply index settings, restart, health check, rollback instructions, logs
- The installer asks for the book folder (`LIBRARY_DIR`); `/library-source` maps to it natively
- The Research Desk workspace ships as an app file, so migrations no longer recreate it

## 0.3.0 (2026-09-29): your own folders and servers, logo

- New ingest source **Folder or Server**: IA-style item folders on a local disk, USB/NAS mount
  (`LIBRARY_DIR` → `/library-source`, read-only) or a web server (directory listing or an
  item-list file)
- Page text from `_hocr_searchtext` + page index, `_hocr.html`, `_chocr.html.gz`, `_djvu.xml`,
  or `_djvu.txt` (as numbered sections)
- Each book checked against archive.org: IA reader when it's there, otherwise the book's own PDF
  (streamed with range requests; only PDF and cover are ever served)
- Drop-folder mode: Hourly schedule; new and changed items (by file signature) are ingested,
  unchanged ones skipped
- CLI: `count/ingest --folder`, `--server`, `--manifest`
- **Logo & Branding** in RD Settings: logo on the home page, the portal top bar and the Desk;
  favicon; home-page background image
- Prefix search kept on for page text (Kannada suffixes), more language codes

## 0.2.0 (2026-09-29): scaling and developer mode

- Parallel ingest: runs are planned, split into batches and processed by several queue workers
  (`QUEUE_WORKERS`, `./resdesk.sh workers N`); atomic progress counters; conflict retries;
  Cancel Run; hourly detection of interrupted runs
- `resdesk ingest --background`, `resdesk progress`, `resdesk reindex --background --reset`
- Local compressed page-text cache: re-indexing no longer downloads from archive.org
- Page index tuned for millions of pages (slim documents, byAttribute proximity, no prefix
  search, search cutoff); titles joined from the books index at query time
- Measured scaling guide for 50,000 books (docs/scaling.md)
- Docker developer mode (`./resdesk.sh dev on`): code runs live from the checkout
- Compose project name pinned (`sok-resdesk`), so data volumes are kept whatever the folder is called

## 0.1.0 (2026-09-29): proof of concept

- Frappe v16 app `sok_resdesk` with DocTypes RD Item, RD Creator, RD Subject,
  RD Ingest Profile, RD Ingest Run, RD Settings
- Internet Archive ingest by collection / query / identifier list, with counting, limits,
  scheduling and a command-line interface
- Metadata normalisation for IA records (languages, years, creators, subjects, romanised forms)
- Meilisearch indexes for books and for the OCR text of every page
- Public portal `/library`: faceted search, full-text page search, book pages with the IA reader,
  search inside a book, reading lists
- Citations: BibTeX, BibLaTeX, RIS, CSL-JSON, APA, MLA, Chicago; Highwire tags, JSON-LD, COinS
- OAI-PMH 2.0 provider (oai_dc, marc21) and MARCXML export for Koha
- `install.sh` one-command Docker install, `resdesk.sh` operations CLI, bench dev setup,
  CI running the real installer, multi-arch image publishing
