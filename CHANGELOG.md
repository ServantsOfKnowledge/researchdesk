# Changelog

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
