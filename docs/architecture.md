# Architecture

## Principles

1. **The Internet Archive is the store of record for scans.** Research Desk does not copy
   images or PDFs. It links to them and embeds IA's reader. That's what lets a laptop host a
   portal for 88,000 books.
2. **Frappe is the catalogue and the control plane**: records, people, roles, workflows,
   ingest jobs, APIs and the Desk UI.
3. **The search engine holds the text.** Page-level OCR lives in Meilisearch only, never in
   MariaDB, so the database stays small and fast.
4. **Standards at every edge**: OAI-PMH, MARCXML, Dublin Core, schema.org, Highwire tags,
   COinS, BibTeX/RIS/CSL. There are no bespoke integrations.
5. **Pure-Python core.** Normalisation, citations, MARC and OAI-PMH live in
   `sok_resdesk/core/` with no Frappe imports, so they are unit-tested in milliseconds and
   reusable elsewhere.

## Components

```
┌──────────────── Docker Compose (or bench) ────────────────────────────────────────┐
│                                                                                   │
│  frontend (nginx) :8080 ──▶ backend (gunicorn · Frappe)                          │
│                              │  www/library      public portal (Jinja + vanilla JS)│
│                              │  api.py           search · cite · marc · stats      │
│                              │  oai.py           OAI-PMH endpoint                  │
│                              │  Desk             DocTypes, forms, workspace        │
│                              ▼                                                    │
│   MariaDB  ◀── catalogue ── Frappe ORM ──▶ search.py ──▶ Meilisearch              │
│                                              ▲            rd_books · rd_pages      │
│   redis-queue ──▶ queue worker ── ingest.py ─┘                                    │
│   scheduler (Daily/Weekly profiles)          │                                    │
└──────────────────────────────────────────────┼────────────────────────────────────┘
                                               ▼
                         archive.org: scrape API · metadata API · hOCR search text
                         your folders / web server: meta.xml · OCR text · PDF
```

**Native installs** run the same processes without containers: `bench start` (honcho) runs
gunicorn (`sok_resdesk.native_wsgi`, which also serves `/assets` and picks the default site),
Socket.IO, the scheduler, the queue workers and Meilisearch from a Procfile in
`~/researchdesk-bench`; MariaDB and Redis come from Homebrew or apt. The app folder is
symlinked into the bench, so `./upgrade.sh` updates code in one place for both modes.

**Server management.** The Server page (`server.py`) reads everything it can from inside the
app: versions, the health of each part, backups, logs. Changing the installation (upgrading,
restarting, applying a resource preset) has to happen outside it, so the page records an
**RD Server Task** and the optional *updater helper* (`scripts/agent.py`: a small container
with the Docker socket, or a Procfile process on native installs) picks it up, runs the same
`./upgrade.sh` or `./resdesk.sh` command a person would, and reports back. Long tasks run in a
separate short-lived container (or a detached process), so they outlive the restarts they
cause. Details: [Server](server.md#how-the-updater-helper-works).

## Data model (DocTypes, module *ResDesk*)

| DocType | Purpose | Key fields |
|---|---|---|
| **RD Item** | one book/document | `item_id` (= IA identifier, the document name), title, alt_title, creators (table), year, language (ISO 639-3), publisher, subjects (multi-select), collections (source), curated_collections, item_type, lock_metadata ("Keep My Edits"), removed_from_source, licence, access, visibility (Public / Login to read / Login to find) and visibility_set_by, page_count, has_page_text, ark, raw_metadata (JSON) |
| RD Item Creator | child table | creator → RD Creator, role, name_as_given |
| RD Item Subject | child table | subject → RD Subject |
| **RD Creator** | authority-lite person record | full_name, alt_name (romanised), VIAF, Wikidata |
| **RD Subject** | keyword / heading | subject_name, scheme |
| **RD Ingest Profile** | *what* to ingest | scope (collection / query / identifiers), filter, max items, full text, schedule, keeping in step with archive.org (new, changed, removed; `synced_on`), portal collection |
| **RD Ingest Run** | one execution | status, counts, log |
| **RD Settings** | single | portal, branding, OAI, Meilisearch, IA politeness, machine resources, server & updates (update checks, backups, alerts), guest access, reader sign-up, access rules |
| RD Access Rule | child table of settings | match_on (collection, subject, language, creator, source, profile), value, visibility |
| **RD Collection** | a curated collection | title, slug (the name and web address), published, featured, cover, curator, description, rules, item_count |
| RD Collection Rule | child table | match_on (source collection, subject, language, creator, source, profile, document type), how (is exactly / contains), value |
| RD Item Collection | child table of RD Item (`curated_collections`) | collection |
| **RD Export** | one metadata export | format, which books, status, file |
| **RD Metadata Import** | one spreadsheet import | file, preview, counts, status |
| **RD Push Target** | where to send metadata | type (Internet Archive / Koha / Wikidata / Webhook), dry run, scope, auto push, credentials (Password fields) |
| **RD Push Run** | one push | status, counts, log |
| **RD External Record** | what was sent where | item, target, external id (Koha biblionumber, Wikidata QID), url, last hash |
| **RD Reader Request** | a sign-up waiting for approval | user, status (Pending / Approved / Rejected); approving adds the ResDesk Reader role |
| **RD Server Task** | an upgrade, restart, resource preset, server backup, update check or log request from the Server page, carried out by the updater helper | action, arguments (checked), status (Queued / Running / Succeeded / Failed / Cancelled), requested by, log, summary |

`raw_metadata` keeps the untouched source record, so re-normalising later never needs a
re-download.

## Search index

| Index | One document per | Searchable | Filters / facets |
|---|---|---|---|
| `{prefix}_books` | RD Item | title, alt_title, creators, alt_creators, subjects, series, publisher, description, text excerpt | language, decade, year, creators, subjects, collections, access |
| `{prefix}_pages` | OCR'd page | text, title | item_id, language, decade, year, collections |

Page documents carry `leaf` (IA's 0-based page index), so hits deep-link into the reader.
`search.py` wraps Meilisearch behind a small client, so another engine can replace it
without touching the portal or API.

## Ingest pipeline

`profile → IA query → scrape (cursor) → per item: metadata → normalise → upsert → page text → index`

- **Plan** job lists identifiers and skips what's already catalogued; **batch** jobs (default 50
  books) run in parallel, one per queue worker. Counters use atomic SQL increments; the last
  batch closes the run; an hourly check marks runs with dead workers *Interrupted*.
- Each book commits on its own and is retried on lock/duplicate conflicts between workers, so a
  failure only loses that book.
- Page text is cached compressed on disk, so re-indexing never needs archive.org.
- Politeness: fixed delay, back-off on 429/5xx, identifying User-Agent.
- Idempotent: re-running a profile skips items already present (unless *Refresh* is set).

## Scaling path

| Stage | Size | Setup |
|---|---|---|
| **Single server** (this release) | up to ~50k books / ~9M pages | one server (8 vCPU, 32 GB, 500 GB NVMe), Docker Compose, Meilisearch, 4 to 6 workers. Measured numbers: [Scaling](scaling.md) |
| Institutional | 100k to 500k books | 16 to 32 GB RAM; several `queue` workers (`docker compose up --scale queue=4`); Meilisearch on its own host with SSD; MariaDB tuned |
| National / consortium | millions of books, 100M+ pages | swap the page index to **OpenSearch** (ICU analysers for Indic scripts, sharding) behind the same `search.py` interface; Frappe web tier behind a load balancer; read replicas; IIIF image server for locally held scans |

Things that don't change as you scale: the DocTypes, the API contract, OAI-PMH/MARC output
and the portal.

## Towards a full library system

Frappe makes it cheap to add the rest of an ILS alongside the digital library:

- **Holdings & items**: physical copies with barcodes and locations, linked to RD Item
- **Patrons & circulation**: members, loans, returns, fines (Frappe ships Contacts, Users,
  Web Forms, Payments)
- **Acquisitions**: Frappe/ERPNext purchasing if needed
- **Authority control**: VIAF/Wikidata reconciliation for RD Creator; LCSH/Sears for RD Subject

Until then, Koha (or any ILS) can do those jobs, and Research Desk integrates through
OAI-PMH and MARC (see [Koha](koha.md)).

## Adding another source

Sources are pluggable at two points: a client that lists and fetches items (like
`core/ia.py`) and a normaliser that returns the RD Item record shape (like
`core/normalize.normalize_ia_item`). See [Development → Adding a source](development.md#adding-a-new-source).

## Access control

`core/access.py` holds the rules (who may find or read a book, given its visibility, the
site's guest mode and whether the visitor is a reader) as pure functions with unit tests.
`access.py` applies them: portal pages and API endpoints check `can_find` / `can_read`;
searches add a Meilisearch filter for guests (`NOT visibility = "Login to find"` for books,
`NOT visibility IN [...]` for pages, so documents indexed before v0.5 count as Public); SQL
counts and OAI-PMH add the matching `WHERE` condition. Book and page documents carry
`visibility`, and bulk changes rewrite just that attribute with partial document updates,
so switching thousands of books never re-indexes their text.

