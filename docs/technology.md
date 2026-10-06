# Technology map: what runs, and what each part is for

Every piece of software Research Desk uses, what it is configured to do, where that is set, and
which features need it. Nothing here is a bespoke integration: each part is a standard
open-source tool or service used for one job.

```
 READERS · STAFF · APPS ─────────────▶ nginx (frontend)  ·  HTTPS: nginx + certbot (Let's Encrypt)
 browser, KOReader, Mirador, Kiwix                        │
                                                          ▼
   ┌───────────────────────────  Frappe v16 app "sok_resdesk"  (Python 3.14) ──────────────────────┐
   │  gunicorn: portal (Jinja + vanilla JS) · Desk · APIs · OAI-PMH · IIIF · OPDS                  │
   │  Socket.IO (Node 24): live Desk updates          scheduler: nightly and daily jobs            │
   │  workers (RQ on Redis): ingest · re-OCR · drafts · exports · preservation                     │
   └───────┬───────────────┬──────────────────┬───────────────────┬──────────────┬────────────────┘
           ▼               ▼                  ▼                   ▼              ▼
       MariaDB 11.8   Redis (cache, queue)  Meilisearch v1.54   Files on disk:  Tools run by workers:
       catalogue,     sessions, queues,     books + pages index  preservation,   Tesseract · poppler ·
       notes,         caches                                      private/,       pypdf · Pillow ·
       page versions                                              library (ro)    mutagen/ffprobe ·
                                                                                  Whisper · Kraken ·
                                                                                  zimwriterfs (optional)
   Outside: archive.org · Wikidata · Wikisource · Commons · VIAF · id.loc.gov · DataCite · Koha ·
            S3-compatible storage · PostHog/Plausible/Umami   (each optional, each switched on by the library)
```

## 1. Runtime services

In Docker these are the services of `compose.yaml`; a native install runs the same processes from
a Procfile (`bench start`), with MariaDB, Redis and Meilisearch installed by Homebrew or apt.

| Component | What it is for | How it is configured | Needed by |
|---|---|---|---|
| **Frappe v16** (Python 3.14, uv) | the framework: DocTypes (the catalogue), permissions and roles, the Desk, background jobs, the web server's request handling, translations | `FRAPPE_BRANCH` and `FRAPPE_COMMIT` build arguments; the app is `sok_resdesk` (`hooks.py`) | everything |
| **gunicorn** (`backend`) | serves the portal pages, the Desk and every API; also answers `/iiif/…` and `/opds` before routing | `GUNICORN_WORKERS`, `GUNICORN_THREADS` in `.env`; resource presets (Settings → Server) | the portal and the Desk |
| **nginx** (`frontend`) | the front door on port 8080: static files and proxying to gunicorn and Socket.IO | the Frappe image's nginx; `HTTP_PORT` | the portal |
| **Socket.IO** (`websocket`, Node 24) | live progress on Desk pages (runs, jobs, the Server page) | `socketio_port` in the common site config | the Desk |
| **Queue workers** (`queue`) | ingest runs, re-OCR, machine drafts, exports, ground-truth sets, preservation, search indexing: all slow work, on the `short`, `default` and `long` queues | `WORKERS_PER_CONTAINER`, `WORKER_NICE` (low priority by default), quiet hours and Pause All (Settings → Server) | ingest, OCR, drafts, exports, preservation |
| **Scheduler** | daily archive.org sync, nightly review checks and fixity audits, second copies, alerts, backups | `bench schedule`; per-feature switches under Settings → Features | scheduled work |
| **MariaDB 11.8** | the catalogue and everything people make: items, creators, collections, notes, proofread page versions, archival units, deposits, settings | `utf8mb4`; `DB_BUFFER_POOL`, `DB_CPUS`, `DB_MEMORY` | everything |
| **Redis** (two instances) | `redis-cache`: sessions and caches; `redis-queue`: the job queues and Socket.IO messages | host names set by the `configurator` service | workers, the Desk |
| **Meilisearch v1.54** | the search index: one document per book (`{prefix}_books`) and per page (`{prefix}_pages`), with filters, facets and highlighted snippets | `MEILI_MASTER_KEY`, `MEILI_VERSION`, `MEILI_CPUS`, `MEILI_MAX_INDEXING_THREADS`; Settings → Search | search, facets, page hits |
| **nginx + certbot** (`proxy`, optional) | HTTPS with a free Let's Encrypt certificate, renewed twice a day; HTTP redirects to it | `./resdesk.sh https on DOMAIN` | a server with its own name |
| **Updater helper** (`updater`, optional) | upgrades, restarts and resource presets from the Server page, run by the same scripts a person would run | `./resdesk.sh updater on`; `scripts/agent.py` | Server page buttons |
| **Docker socket proxy** (`monitor`, optional) | read-only view of the containers, so the Server page can show their health | `monitor` profile | Server page |
| **Docker Compose / bench** | how it is all started: containers, or native processes | `install.sh`, `resdesk.sh`, `upgrade.sh` | installation |

## 2. Tools the workers run, and libraries

| Component | What it is for | Configured by | Needed by |
|---|---|---|---|
| **Tesseract** (+ language models) | reading page images: OCR of scans, re-OCR by zone, handwriting drafts with the OCR models | `OCR_LANGS` (all models, or a list) in `.env`; Server → Requirements says which are missing | OCR, re-OCR, draft leaves |
| **poppler** (`pdftoppm`) | drawing PDF pages as images for *Page & text*, proofreading and OCR | in the image; Server → Requirements | books with a PDF and no archive.org scan |
| **pypdf** | the text layer of a PDF, page by page; the embedded image of a scanned page when poppler is absent | part of Frappe's environment | PDFs, repositories, deposits |
| **Pillow** | page and photograph images: scaling, tiles, regions and rotation for IIIF level 2, EXIF | part of Frappe's environment | the reader, IIIF, photographs |
| **mutagen** / **ffprobe** | the length of an audio or video file (mutagen first, ffprobe as the fallback) | `pyproject.toml`; ffprobe optional | recordings |
| **boto3** | the second preservation copy on S3-compatible storage | Settings → Preservation | the second copy |
| **requests** | every call to an outside service, with polite pacing and back-off | part of Frappe's environment | all integrations |
| **faster-whisper** or the **whisper** command (optional) | speech to text: machine drafts of a recording's transcript | installed by the library; model size in Settings → Machine Drafts | draft transcripts |
| **Kraken** (optional) | handwriting recognition with a recognition model file | installed by the library; Settings → Machine Drafts | draft leaves |
| **zimwriterfs** (optional, `zim-tools`) | packaging an offline copy as a ZIM file for Kiwix | found on the server's path | offline copies |
| **Meilisearch client** (`search.py`) | a small wrapper, so another engine can replace Meilisearch | Settings → Search | search |
| **Portal front end** | Jinja templates with vanilla JavaScript and CSS (no framework, no build step): the readers, notes, proofreading, zoom viewer, media player | `public/js`, `public/css`, `www/library` | the portal |

## 3. Files and where they live

| Place | Holds | Kept by |
|---|---|---|
| `db-data` volume | MariaDB's files | Docker volume (backed up nightly by Frappe) |
| `meili-data` volume | the search index (it can be rebuilt from the catalogue and the page-text cache) | Docker volume |
| `redis-queue-data` volume | the job queue | Docker volume |
| `sites` volume | site config, public and private files: uploaded pictures, deposits (`private/deposits`), exports, ground-truth sets, the page-text cache, OCR'd text, page images | Docker volume |
| `/preservation` | the library's own checked copies (OCFL); an optional second copy elsewhere (folder or S3) | `PRESERVATION_DIR` |
| `/library-source` (read-only) | your folders of books, leaf images, photographs, recordings, and a Calibre library, read where they are and never changed | `LIBRARY_DIR` |
| `logs` volume | application and worker logs, shown on the Server page | Docker volume |

## 4. Outside services and standards

| Service or standard | Used for | In the library's hands |
|---|---|---|
| **archive.org** (scrape, metadata and search APIs, S3 writes) | books: details, page text, images, PDFs; pushing corrected metadata | Ingest Profiles; Push Targets |
| **Wikidata** (MediaWiki and Wikibase APIs) | authority matching, giving back names and author links, what notes are about, *depicts* on photographs | Settings → Catalogue; each person's own Wikimedia account |
| **Wikisource** | books with their proofread pages; corrected pages sent back | Ingest Profiles; My Wikimedia Account |
| **Wikimedia Commons** | photographs, uploaded under the sender's own account | Item → Send to Wikimedia Commons |
| **VIAF**, **Library of Congress (id.loc.gov)** | authors' VIAF numbers (through Wikidata); subject headings | Settings → Catalogue → Authorities |
| **DataCite** | DOIs for chosen collections | Settings → Sharing |
| **ARK / N2T** | permanent identifiers under the library's own NAAN | Settings → Sharing |
| **Koha** and other library systems | records matched to books; links sent back | Library Systems; Push Targets |
| **OAI-PMH** | the portal's catalogue for harvesters; DSpace, EPrints and others harvested in | always on; Ingest Profiles |
| **IIIF** (Presentation 3.0, Image API 3.0 level 2) | manifests and an image service for Mirador, Universal Viewer | Settings → Features → Sharing metadata |
| **OPDS 1.2** | the library in e-reader apps (KOReader, Thorium, Moon+ Reader) | Settings → Features → Sharing metadata |
| **W3C Web Annotation** | readers' notes, and the Annotation Protocol for other tools | always on |
| **EAD3**, **ISAD(G)** | archival description and finding aids | Archival Description |
| **OCFL**, **BagIt**, **PREMIS-style events** | preservation copies, exports for other archives | Settings → Preservation |
| **Frictionless Data Package** | ground-truth sets | Ground Truth |
| **Zotero, Google Scholar** (Highwire tags, COinS, JSON-LD) | citations from every book page | always on |
| **Let's Encrypt** | the HTTPS certificate | `./resdesk.sh https on` |
| **S3-compatible storage** | the second preservation copy | Settings → Preservation |
| **PostHog, Plausible, Umami** | portal use, without cookies (or the built-in counter) | Settings → Readers & Access |
| **Kiwix** | offline use of an offline copy (a ZIM file) | Exports |
| **Calibre** | libraries read in place; a small collection written out | Ingest Profiles; Exports |

## 5. Building, testing and shipping

| Component | What it is for |
|---|---|
| **GitHub Actions** | on every push: ruff (lint and format), the pure-Python tests, the docs-match-code checks, a Docker install with the Frappe integration tests; on a green main with a new version: a tag and a GitHub release |
| **GitHub Container Registry** | the prebuilt image for each tagged version (`ghcr.io/servantsofknowledge/researchdesk`) |
| **ruff**, **pytest** | the code's style and its tests (`unit_*.py` need no Frappe; `test_*.py` run on a site) |
| **Playwright** (Chromium) | retaking the help pictures (`scripts/screenshots.py`) and the accessibility checks (axe-core) |
| **Documentation tools** | `scripts/gen_docs.py` (the settings tables), `scripts/docs_pdf.py` (the architecture PDF), `scripts/docs_epub.py` (the whole guide as an EPUB), `scripts/setup-signing.sh` (Verified commits) |

## 6. Which components each feature needs

| You want to… | You need running |
|---|---|
| search books and inside books | Meilisearch, the workers, MariaDB |
| read scans without a PDF, or proofread | archive.org images (or poppler + a PDF), the workers |
| OCR scans or re-OCR pages | Tesseract and its language models, the workers |
| draft transcripts by machine | faster-whisper or whisper (speech); Tesseract or Kraken (handwriting) |
| keep your own checked copies | the preservation folder, the scheduler (fixity), optionally S3 and boto3 |
| show books in Mirador or Universal Viewer | nothing extra: the app answers `/iiif` (poppler for PDF pages) |
| offer the library to e-readers | nothing extra: `/opds` |
| make an offline copy or a ZIM for Kiwix | the workers; zimwriterfs for the ZIM |
| use a Calibre library | the library folder mounted read-only; no Calibre program needed |
| put the portal on a server with HTTPS | the proxy (nginx and certbot), a DNS name |
| upgrade and restart from the browser | the updater helper |
| give back to Wikimedia | each person's own OAuth token; nothing installed |
