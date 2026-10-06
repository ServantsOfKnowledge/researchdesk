# Architecture

A PDF of this page and the [scaling guide](scaling.md) comes with every
[release](https://github.com/ServantsOfKnowledge/researchdesk/releases/latest), for reading
offline or sending to partners; `python3 scripts/docs_pdf.py` makes one from the current docs.

## Principles

1. **The Internet Archive is the store of record for scans.** Research Desk links to images and
   PDFs and embeds IA's reader, so a laptop can host a portal for 88,000 books. The library keeps
   **its own copies** only of the books it chooses to preserve ([OCFL](preservation.md)), and can keep a second
   copy elsewhere.
2. **Frappe is the catalogue and the control plane**: records, people, roles, workflows,
   ingest jobs, APIs and the Desk UI.
3. **The search engine holds the text.** Page-level OCR lives in Meilisearch and a compressed
   cache on disk, never in MariaDB, so the database stays small and fast. Only the pages people
   corrected or re-read (RD Page Text) are in the database, laid over the source text wherever a
   page is read.
4. **Standards at every edge**: OAI-PMH, MARCXML, Dublin Core, schema.org, Highwire tags,
   COinS, BibTeX/RIS/CSL, W3C Web Annotation, ARK, OCFL, BagIt. There are no bespoke integrations.
5. **Secure and findable by default**: security headers, rate limits, login lock-out and
   strong passwords, outside addresses fetched only on the public internet, staff shown only
   Research Desk in the Desk (Administrator keeps Frappe's tools; `deskscope.py`); a sitemap of every
   book, descriptions, canonical addresses and language alternates (`security.py`, `seo.py`,
   `core/seo.py`, `core/netguard.py`; [Server → Security](server.md#security)).
6. **Only what the library uses.** Institutions differ, so what Research Desk does is chosen, not
   assumed: the installer asks what kind of institution this is (profiles that combine), and
   Settings → Features switches nineteen features on and off. A feature that is off is not
   collected: its scheduled work stops, its Desk screens go and calls that would make new data of
   its kind are refused, while what exists stays and who sees it is still decided by access
   (`features.py`; [Staff guide → Features](staff-guide.md#features-and-your-institution)).
7. **Every kind of material is an item.** A book, a manuscript or palm-leaf bundle, a photograph, a
   recording and a deposited paper are all RD Items with the same catalogue, access rules, search,
   citations, IIIF manifest and permanent links; each kind only adds what it needs (leaf labels,
   EXIF, time-coded transcripts). Items come from interchangeable *stores* (archive.org, IA-style
   folders, loose PDFs, image folders, recordings, a Calibre library read in place, repository
   deposits, OAI-PMH repositories, Wikisource) behind one small interface (`core/folder.py`).
8. **People do the proofreading; machines only draft.** Everything a machine produces (OCR,
   speech to text, handwriting recognition) is a *Machine* page version that a person corrects;
   machine text is never shared as ground truth and never replaces a person's work.
9. **Pure-Python core.** Normalisation, citations, MARC, OAI-PMH, ARKs, OCFL, the second copy,
   BagIt, OCR quality, page zones, OCR languages, transliteration, annotation anchoring and server
   equipment checks live in
   `sok_resdesk/core/` with no Frappe imports, so they are unit-tested in milliseconds and
   reusable elsewhere.

## Components

The full list of software, what each part is configured for and which features need it is the [Technology map](technology.md).

```
┌──────────────── Docker Compose (or bench) ────────────────────────────────────────────┐
│                                                                                       │
│  frontend (nginx) :8080 ──▶ backend (gunicorn · Frappe)                               │
│                             │  www/library      public portal (Jinja + vanilla JS):   │
│                             │                   search · book · archive · deposit     │
│                             │  api.py           search · cite · marc · stats · media  │
│                             │  oai.py  iiif.py  OAI-PMH · IIIF manifests + image      │
│                             │  opds.py          e-reader catalogue (OPDS 1.2)         │
│                             │  Desk             one sidebar: DocTypes, forms, pages   │
│                             ▼                                                         │
│  MariaDB  ◀── catalogue ── Frappe ORM ──▶ search.py ──▶ Meilisearch                   │
│                                             ▲            rd_books · rd_pages          │
│  redis-queue ──▶ queue worker ── ingest.py ─┘                                         │
│                  │ re-OCR (Tesseract) · machine drafts (Whisper, Kraken)              │
│                  │ preservation copies (OCFL) · exports (offline copy, Calibre)       │
│  scheduler (profiles, archive.org sync, fixity checks, second copies)                 │
└──────────────────────────────────────────────┼────────────────────────────────────────┘
                                               ▼
                         archive.org: scrape API · metadata API · hOCR search text · page images
                         your folders / web server: books, leaf-image bundles, photographs,
                                                    recordings · meta.xml / sidecar JSON · text
                         a Calibre library (read in place) · repository deposits (private files)
                         repositories (DSpace, EPrints…): OAI-PMH records · PDFs and their text
                         Wikisource: Index and Page pages · Wikimedia Commons, Wikidata (give back)
                         preservation folder · second copy (folder or S3-compatible bucket)
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
| **RD Item** | one book/document | `item_id` (= IA identifier, the document name; for a repository's record, the profile's prefix and the record's own identifier), source (Internet Archive / Local / Repository / Wikisource / Library System), oai_identifier and remote_pdf (a repository's record and PDF), title, alt_title, creators (table), year, language (ISO 639-3), publisher, subjects (multi-select), collections (source), curated_collections, item_type (Book, Periodical, Article, Thesis, Report, Manuscript, Map, Audio, Video, Photograph, Other), lock_metadata ("Keep My Edits"), removed_from_source, licence, access, visibility (Public / Login to read / Login to find) and visibility_set_by, page_count, has_page_text, ark (archive.org's), persistent_id (this library's permanent ARK), ocr_quality and ocr_low_pages, ocr_languages (the languages to OCR it in), doi / doi_state (DataCite), details_pending (catalogued from its search record, full record and text still coming), reocr_state and pages_proofread (re-OCR and proofreading), page_order (page text matched to the page images by the scan data), preservation_status / preserved_on / preserved_version / preserved_bytes / fixity_checked_on, copies ("2 of 2 verified"), second_copy_status / second_copy_version / second_copy_on / second_copy_checked_on, served_from_copy, raw_metadata (JSON); for local material local_store, local_path, local_pdf, local_files, local_images (leaf images of a manuscript or photograph), local_thumb; manuscripts: ms_* (repository, shelfmark, material, script, leaves, dimensions, condition, scribe, date copied, contents, colophon, provenance) and leaf_labels; recordings: media_files, duration, leaf_times (the start and end seconds of each transcript segment); photographs: ph_* (taken on, place, event, people, depicts as Wikidata Q numbers, camera, GPS, dimensions, SHA-256 of the original) and commons_file / commons_sent_by / commons_sent_on; wiki_site and wiki_index (a Wikisource book); archival_unit (its place in the archival description) |
| RD Item Creator | child table | creator → RD Creator, role, name_as_given |
| RD Item Subject | child table | subject → RD Subject |
| **RD Creator** | a person the books name | full_name, alt_name (romanised), sort name; matched on Desk → Authorities: Wikidata, VIAF, born, died, description, match (Proposed / Confirmed / No match), candidates |
| **RD Review Flag** | a question about a record for a cataloguer (Desk → Review Queue) | book, check (no year, wrong-looking year, language, script, author, title, subjects, duplicate), detail, weight, status (Open / Fixed / Ignored), who answered and when |
| **RD Subject** | keyword / heading | subject_name, scheme; matched to LCSH: lcsh_id, heading, match, candidates |
| **RD Ingest Profile** | *what* to ingest | source (archive.org, a folder or server, an OAI-PMH repository, Wikisource), include_media (recordings from archive.org), images_as_photographs (a folder of images is photographs, not a manuscript), scope (collection / query / identifiers), filter, max items, full text, schedule, keeping in step with archive.org (new, changed, removed; `synced_on`), portal collection; for a repository its address, set, identifier prefix and `harvested_until` |
| **RD Wikimedia Account** | one person's own connection to Wikimedia | the person (record name), their Wikimedia username, when connected, the OAuth 2.0 access token (an encrypted Password field only that person can read or use), when last used |
| **RD Archival Unit** | one unit of archival description (fonds, series, file, item) | reference code (the record name), title, level, parent (a tree), dates, extent, creator, the other ISAD(G) fields, published, visibility; digitised **RD Item**s point at their unit |
| **RD Contributor Release** | one person's open licence for the pages they proofread | the person (record name), the licence (CC0, CC BY, CC BY-SA), when agreed, whether they may be named; ground-truth sets carry only pages whose proofreaders released them under a licence the set can carry |
| **RD Deposit** (with its **RD Deposit File** rows) | a person's own work waiting for or past review | the depositor, status (Draft, Submitted, Needs Changes, Accepted, Rejected, Withdrawn), the work's details, licence, who may read it and an embargo date, the files with a SHA-256 each, the reviewer's notes, checks made on submission and the book it became |
| **RD Ingest Run** | one execution | status, counts, log |
| **RD Settings** | single | portal, branding, OAI, Meilisearch, IA politeness, machine resources, server & updates (update checks, backups, alerts), guest access, reader sign-up, access rules, institution kinds and the nineteen feature switches, ground-truth licence and release rule, machine-draft engines |
| RD Access Rule | child table of settings | match_on (collection, subject, language, creator, source, profile), value, visibility |
| **RD Collection** | a curated collection | title, slug (the name and web address), published, featured, preserve, cover, curator, description, rules, item_count, mirror_of (the archive.org collection it follows), part_of (the collection it belongs to) |
| RD Collection Rule | child table | match_on (source collection, subject, language, creator, source, profile, document type), how (is exactly / contains), value |
| RD Item Collection | child table of RD Item (`curated_collections`) | collection |
| **RD Export** | one export | format (metadata formats, a Calibre library, an offline copy for Kiwix), which books, status, file |
| **RD Metadata Import** | one spreadsheet import | file, preview, counts, status |
| **RD Push Target** | where to send metadata | type (Internet Archive / Koha / Wikidata / Webhook), dry run, scope, auto push, credentials (Password fields) |
| **RD Push Run** | one push | status, counts, log |
| **RD External Record** | what was sent where | item, target, external id (Koha biblionumber, Wikidata QID), url, last hash |
| **RD Library System** | a library system whose catalogue is matched to the books here | system type, records from a MARC file or OAI-PMH, OPAC record address (`{id}`), a Koha Push Target for sending links back, link text, cataloguing unmatched records; counts and progress |
| RD Library Record | one record from a library system | record number, title, other title, authors, year, ISBN, status (New / Linked / To Review / No Match / Not This Book / Catalogued), the book here, score and why, candidates, who decided, links sent on, the MARCXML as received |
| **RD Reader Request** | a sign-up waiting for approval | user, status (Pending / Approved / Rejected); approving adds the ResDesk Reader role |
| **RD About Page** | single | the introduction page at `/about`: on/off and its top-bar label, page title and search description, headline, tagline, introduction (rich text), image, live numbers, two buttons, steps, highlight cards, featured collections, a free-form part |
| RD About Item | child table of RD About Page (`steps`, `highlights`) | title, text (plain, `**bold**`), link, link text |
| **RD Tombstone** | what is left of a deleted or merged book, so its ARK still answers | ark, item_id, title, authors, year, reason (Deleted / Withdrawn / Merged), replaced_by, note for readers |
| **RD Preservation Event** | a book's preservation history (PREMIS-style) | item, event (Ingestion / Fixity check / Replication / Repair / Deletion / Access from copy / Export), outcome, when, copy version, by, detail |
| **RD Annotation** | a reader's note on a page | item, leaf, printed page, kind (Highlight / Comment / Tag / Question / Link / OCR error), who can see it (Private / Group / Public), research group, review (Pending / Approved / Rejected), note, tags, link, what it is about (a Wikidata item, with its name and description); on a passage: quoted text with the text before and after it, and its character positions; on the page image: a region in percent |
| **RD Ground Truth** | a set of proofread pages with their images, shared for training and testing OCR | title, which pages (proofread or validated, validated only), collection, language, book, only books anyone can read, page parts, at most; status, on the portal, licence, pages, page parts, books, languages, file, size, SHA-256, log; pages left out for want of a contributor release, who reviewed it and when (a set goes on the portal only after review) |
| **RD Page Text** | a version of one page's text (re-OCR or proofreading); the current one overlays archive.org's text wherever the page is read | item, leaf, printed page, current (yes/no), source (Re-OCR / Proofreading / Machine draft), status (Machine / Proofread / Validated), OCR quality, proofread by/on, validated by/on, text, OCR engine, zones (JSON, in reading order) |
| **RD Research Group** | readers who share notes | group name, description, members (RD Research Group Member: user) |
| RD Research Group Member | child table | user, name |
| **RD Server Task** | an upgrade, restart, resource preset, server backup, update check, log request or requirements install from the Server page, carried out by the updater helper | action, arguments (checked), status (Queued / Running / Succeeded / Failed / Cancelled), requested by, log, summary |

The portal's translations are Frappe's own **Translation** records (language, phrase,
translation), edited on Desk → Portal Translations (`translations.py`), so Frappe serves them to
templates and Python, and `website_context` sends the scripts' share to the browser
(`window.RD_I18N`, used as `__()` by the portal scripts).

`raw_metadata` keeps the untouched source record, so re-normalising later never needs a
re-download.

## Kinds of material

All of these are RD Items; the store an item comes from decides where its files are read.

| Kind | Comes from | What it adds | Pages |
|---|---|---|---|
| Book | archive.org, folders, loose PDFs, a Calibre library, repositories, Wikisource | the catalogue record; OCR text, page by page | page images from the scan or the PDF |
| Manuscript or palm leaf | a folder of leaf images, or a PDF | `ms_*` description, leaf labels (1a, 1b, r/v), transcription from blank (`core/leaves.py`, `core/leafimages.py`, `manuscripts.py`) | one image per leaf, served at IIIF level 2 with deep zoom |
| Photograph | a folder of images (`images_as_photographs`) | EXIF, who and where, depicts (Wikidata), SHA-256 of the original (`core/photo.py`) | the photograph itself |
| Recording | a folder (media file, WebVTT/SRT, poster, sidecar JSON) or archive.org | duration, a player, a transcript kept as segments (pages with `leaf_times`) for search, proofreading and citations (`core/media.py`, `media.py`) | segments |
| Deposit | the portal's deposit form (`deposit.py`) | licence, embargo, files with checksums, a reviewer's decision; accepting makes an item | by the file |

Manuscripts, photographs and recordings reuse the page-text machinery: a leaf or a segment is a
page, so search, proofreading, validation and citation need nothing new. IIIF
(`iiif.py`, `core/iiif.py`) serves a Presentation 3.0 manifest for each (A/V manifests carry the
transcript as supplementing annotations) and an Image API 3.0 level 2 service with tiles.

## Archival description

`RD Archival Unit` is a Frappe tree (`lft`/`rgt`): fonds, sub-fonds, collection, series,
sub-series, file and item, with the ISAD(G) fields (`core/archival.py`; rules for what may sit
under what). Digitised items point at their unit (`RD Item.archival_unit`). The portal shows
`/library/archive` and a page per unit, hiding a unit whose parent is hidden (`archival.shown`),
and a fonds or collection is exported as EAD3 (`archival.ead`).

## Machine drafts

`drafts.py` and `core/draft.py` run optional engines on the library's server in background jobs:
speech to text (`faster-whisper`, or the `whisper` command) fills a recording's transcript
segments, and handwriting recognition (Tesseract through re-OCR, or Kraken with a model file)
reads manuscript leaves. Results are saved as *Machine* page versions with source *Machine draft*
and the engine named; `drafts._save` never writes over a proofread or validated page, and
ground-truth sets only ever contain human pages.

## Giving back to Wikimedia

Each person connects their own Wikimedia account (`wikimedia.py`, `RD Wikimedia Account`): an
owner-only OAuth 2.0 token, kept encrypted, readable and usable only by its owner. Under that
account the library gives back to Wikidata (names in their scripts, author links), sends
proofread and validated Wikisource pages back after a diff review with revision-based conflict
and licence checks (`wikisource.py`), and contributes photographs to Wikimedia Commons
(`commons.py`, `core/commons.py`): a reviewed file name, description page and categories, free
licences only, duplicate and name checks, and *depicts* statements from the photograph's Wikidata
items.

## Taking the library away

- **Offline copy** (`offline_export.py`, `core/offline.py`): a collection as a folder of web pages
  with a search box (a script over one data file, so it works from `file://`), a page per book
  and the text where held; a ZIM file for Kiwix when `zimwriterfs` is installed.
- **OPDS** (`opds.py`, `core/opds.py`): `/opds` is an OPDS 1.2 catalogue for e-reader apps,
  answered before routing like IIIF, under the portal's access rules.
- **Calibre** (`calibre_export.py`): a small collection as a Calibre library.
- **The guide**: `scripts/docs_epub.py` makes one EPUB of every help page; each release carries it.

## Search index

| Index | One document per | Searchable | Filters / facets |
|---|---|---|---|
| `{prefix}_books` | RD Item | title, alt_title, creators, alt_creators, subjects, series, publisher, description, item_id, readers' public note tags and Wikidata names, text excerpt | language, decade, year, creators, subjects, collections, curated collections, item type, access, visibility, source, note tags and entities |
| `{prefix}_pages` | OCR'd page | text | item_id, language, decade, year, creators, subjects, collections, curated collections, item type, visibility |

Page documents carry `leaf` (IA's 0-based page index), so hits deep-link into the reader, and
copies of the book fields they are filtered by (titles and authors for the hits on screen come
from the books index). `search.py` wraps Meilisearch behind a small client, so another engine
can replace it without touching the portal or API.

**Only real work goes to the engine** (0.38.1). Meilisearch runs its tasks one after another
and merges neighbouring tasks of the same kind, and indexing page text is the heaviest thing it
does, so `search.py` sends as little, and in as few tasks, as it can:

| What | How |
|---|---|
| Index settings | `MeiliClient.setup()` creates a missing index and sends only the settings that differ from the engine's (`settings_diff`); a fingerprint in Redis spares even the comparison for a day. Every ingest run, re-index and migration used to send them all again |
| Catalogue edits | `update_item_fields` compares each book's record with the engine's copy: unchanged books send nothing, and a book's pages are rewritten only when a field they carry changed |
| Books fetched again | RD Item keeps a fingerprint of the page text sent (`page_text_hash`). An update or sync with the same text sends the book record only, and its pages get just the changed fields; new text replaces the old pages |
| Batching | `IndexBuffer` sends 25 books at a time: one task for the books, one to remove replaced pages, page text in tasks of 2,000 pages. Workers wait while more than 300 tasks are waiting (`wait_for_room`) |
| Watching it | the Desk's queue figures are cached 15 seconds; finished tasks are forgotten nightly, a week after they finish |

How much of the machine the engine may use is set outside the app
(`MEILI_CPUS`, `MEILI_MAX_INDEXING_THREADS`: [Operations → Resources](operations.md#resources-how-much-of-the-machine-research-desk-may-use)).

## Ingest pipeline

`profile → IA query → scrape with catalogue fields (5,000 a request) → catalogue + index every new book → per item, in batches: metadata → normalise → upsert → page text → index`

- **Catalogue first**: the planner asks the scrape API for each book's catalogue fields (as
  `ia search -f` does) and catalogues and indexes all new books at once, marked
  `details_pending`; the batches then fetch each book's full record, files and page text and
  clear the mark. Refused fields fall back to a core set, then to identifiers only.

- **Plan** job lists identifiers and skips what's already catalogued; **batch** jobs (default 50
  books) run in parallel, one per queue worker. Counters use atomic SQL increments; the last
  batch closes the run; an hourly check marks runs with dead workers *Interrupted*.
- Each book commits on its own and is retried on lock/duplicate conflicts between workers, so a
  failure only loses that book.
- Page text is cached compressed on disk, so re-indexing never needs archive.org.
- Page text is matched to the page images with the book's scan data (`core/scandata.py`): archive.org's OCR counts every leaf scanned, its page images (`…/page/n<leaf>.jpg`) and PDF only the pages the book shows. `leaf` everywhere (search, notes, page links, citations, proofreading) counts the pages shown.
- Politeness: fixed delay, back-off on 429/5xx, identifying User-Agent.
- Idempotent: re-running a profile skips items already present (unless *Refresh* is set).

## Re-OCR

`core/ocr_engine.py` reads a page image with Tesseract, one zone at a time in reading order
(`core/zones.py`). A book is read with several language models at once (`kan+san+eng`, the
main one first): the book's language, the languages named in its language label, then English,
or the list in its *OCR Languages* field; a zone can carry its own. Only installed models are
used, and Server → Requirements (`requirements.py`, `core/equipment.py`) says which the
catalogue needs. Results become RD Page Text versions; people's proofread pages are never
replaced.

## Sharing

- **Ground truth** (`groundtruth.py`, `core/groundtruth.py`): RD Ground Truth sets of current
  proofread/validated RD Page Text versions with their page images, written as a zip (page and
  zone pairs, manifest, Frictionless Data Package) in the site's private files. A page goes in
  only if everyone who proofread or validated it released it (RD Contributor Release: CC0, CC BY
  or CC BY-SA, chosen by each person) under a licence the set's licence can carry; a person
  reviews the set before it can go on the portal (a licence chosen in Settings is also needed);
  served by `groundtruth.download`.
- **Notes as data** (`core/wikidata.py`): a note's `entity` is a Wikidata Q-number (search proxied
  and cached by `annotations.wikidata_search`); approved public notes' tags and items are copied
  into the book's search document (`note_tags`, `note_entities`, `note_entity_names`) and listed
  on `/library/entity/Q…` and `/library/tag/…`.
- **W3C Web Annotation Protocol** (`annotation_protocol.py`): one whitelisted endpoint whose path
  names the container (`…/annotations/<book>/`) or the note (`…/<book>/<note>`); GET/HEAD/OPTIONS,
  POST, PUT and DELETE with ETags; the same visibility rules as the page reader.
- **DOIs** (`datacite.py`, `core/datacite.py`): DataCite REST API (JSON:API, schema 4.5), PUT to
  create or update, sent again only when the metadata fingerprint changes; test system first.

## Integrations with external authorities and services

Research Desk keeps its own catalogue and leans on the shared registries libraries already
trust. Each integration is optional, works through an open standard or a documented API, and
is switched on in Settings (or by a Push Target) by the library. Where a service takes
contributions, Research Desk can give back what the library knows.

| Authority or service | What Research Desk takes | What it gives back | How (code) | Switched on in |
|---|---|---|---|---|
| **Internet Archive** | books: metadata, page text, page images, PDFs | corrected metadata to the library's own items | scrape, metadata and search APIs; IA S3 metadata writes (`core/ia.py`, `core/push.py` IAWriter) | Ingest Profiles; Push Targets |
| **Library systems** (Koha, Evergreen, SOUL, e-Granthalaya…) | their catalogue records (MARC file or OAI-PMH `marc21`), matched to the books here | 856 links to the digital copies in their own records (Koha REST), or their records with links as MARCXML | `core/marcin.py`, `core/libmatch.py`, `librarysystems.py`, `core/push.py` KohaClient | Library Systems |
| **Institutional repositories** (DSpace, EPrints, Islandora, OJS…) | records (Dublin Core), their PDFs' text page by page; deleted records | the portal's own catalogue over OAI-PMH, for them to harvest back | OAI-PMH 2.0 harvesting with resumption tokens and `from` (`core/harvest.py`), `citation_pdf_url` on the record's page, the PDF's text layer (`core/pdftext.py`) | Ingest Profiles (Repository) |
| **Wikisource** | Index pages as books, their Page texts at a chosen proofreading level, page images | proofread and validated pages, under each person's own account, after a diff review (`wikisource.py`) | MediaWiki API (`core/wikisource.py`, `core/wikimedia.py`) | Ingest Profiles (Wikisource); My Wikimedia Account |
| **Wikimedia Commons** | | photographs with a description page, licence, categories and *depicts*, under each person's own account (`commons.py`) | MediaWiki upload and Wikibase APIs (`core/commons.py`) | Item → Send to Wikimedia Commons; My Wikimedia Account |
| **Calibre** | a library read in place: metadata, covers, formats, EPUB text | a small collection as a Calibre library (`calibre_export.py`) | read-only SQLite (`core/calibre.py`, `core/calibre_export.py`) | Ingest Profiles (folder with a Calibre library); Exports |
| **IIIF viewers** (Mirador, Universal Viewer) | | a manifest for every item and an image service at level 2 | `iiif.py`, `core/iiif.py` | Settings → Features → Sharing metadata |
| **E-reader apps** (KOReader, Thorium…) | | the library as an OPDS 1.2 catalogue | `opds.py`, `core/opds.py` | Settings → Features → Sharing metadata |
| **Kiwix** | | an offline copy as a ZIM file | `offline_export.py` (zimwriterfs) | Exports |
| **Speech and handwriting engines** (Whisper, Kraken) | drafts of transcripts, on the library's own server | | `drafts.py`, `core/draft.py` | Settings → Machine Drafts |
| **Wikidata** | people for authors (names, dates, VIAF), things notes are about | book editions with their authors linked (P50, *stated as* the printed name), people's names in the books' scripts, as QuickStatements or sent directly (`contribute.py`) | MediaWiki API: `wbsearchentities`, `wbgetentities`, `wbeditentity` (`core/authority.py`, `core/wikidata.py`, `core/push.py`) | Settings → Catalogue → Authorities; Push Targets (Wikidata) |
| **VIAF** (OCLC) | authors' VIAF numbers, through Wikidata | the numbers in MARC `$0`, JSON-LD and DOIs, so other catalogues can link | read through Wikidata P214 | with Wikidata matching |
| **Library of Congress Subject Headings** (id.loc.gov) | headings and identifiers for subjects | MARC 650 with `$0`; headings LCSH lacks, listed for SACO proposals (`contribute.saco`) | `suggest2` API (`core/authority.py`) | Settings → Catalogue → Authorities |
| **DataCite** | DOIs for chosen collections | each book's metadata (schema 4.5), authors with VIAF and Wikidata identifiers | REST API, JSON:API (`core/datacite.py`) | Settings → Sharing → DOIs |
| **ARK** (N2T / the library's NAAN) | the library's ARK prefix | permanent ARKs for every book and page, tombstones for withdrawn books | resolver at `/ark:/…` (`core/ark.py`, `identifiers.py`) | Settings → Sharing → Persistent Identifiers |
| **Koha** and other library systems | | MARCXML records, collections as sets; records pushed into Koha | OAI-PMH 2.0 (`core/oai.py`), MARCXML (`core/marc.py`), Koha REST (`core/push.py`) | always on (OAI); Push Targets (Koha) |
| **Annotation tools** (Hypothesis-style clients) | readers' notes | public notes as W3C Web Annotations | W3C Web Annotation Protocol (`annotation_protocol.py`) | always on |
| **OCR research** | | proofread pages with their images as open ground truth | zip with a Frictionless Data Package (`core/groundtruth.py`) | Settings → Sharing → Ground Truth |
| **Zotero, Google Scholar, reference managers** | | citation metadata on every book page | Highwire tags, COinS, JSON-LD, BibTeX/RIS/CSL (`core/citations.py`) | always on |
| **Usage statistics** (PostHog, Plausible, Umami) | | page views without cookies | their scripts and APIs (`analytics.py`) | Settings → Readers & Access |
| **Storage** (S3-compatible) | | the second preservation copy | S3 API (`core/replica.py`) | Settings → Preservation |

Requests to outside services are made by background jobs or on a cataloguer's request, never
while a reader waits (except Wikidata search when a reader picks what a note is about, cached a
day). Each identifies itself (`SOK-ResearchDesk (+repository URL)`), keeps to the service's pace
(a pause between requests, `maxlag` for Wikidata) and fails soft: a service that can't be
reached leaves the catalogue as it was.

## Scaling path

| Stage | Size | Setup |
|---|---|---|
| **Single server** (this release) | up to ~50k books / ~9M pages | one server (8 vCPU, 32 GB, 500 GB NVMe), Docker Compose, Meilisearch, 4 to 6 workers. Measured numbers: [Scaling](scaling.md) |
| Institutional | 100k to 500k books | 16 to 32 GB RAM; several `queue` workers (`docker compose up --scale queue=4`); Meilisearch on its own host with SSD; MariaDB tuned |
| National / consortium | millions of books, 100M+ pages | swap the page index to **OpenSearch** (ICU analysers for Indic scripts, sharding) behind the same `search.py` interface; Frappe web tier behind a load balancer; read replicas; a dedicated IIIF image server (tiling) in front of the built-in level 2 service |

Things that don't change as you scale: the DocTypes, the API contract, OAI-PMH/MARC output
and the portal.

## Where it fits in the library and archive ecosystem

For most libraries and archives, Research Desk replaces the four or five separate systems a
digital library needs: repository, discovery, reader, OCR and proofreading, and basic
preservation, and, for archives, the description of papers as a hierarchy (ISAD(G), EAD3). It works
alongside the library system (circulation, acquisitions, patrons).

| Layer | Typical tools | Research Desk | Why |
|---|---|---|---|
| Digital library / repository | Greenstone, Omeka, CONTENTdm, DSpace or EPrints used for digitised collections, one-off portals | **Replaces** | Catalogue, portal, collections and OAI-PMH in one install; strongest for Greenstone sites |
| Search and discovery (digital holdings) | VuFind, Blacklight | **Replaces** | Full-text search in Indic scripts, search in Latin letters, facets. Licensed e-resources stay with their discovery layer |
| Reader | Internet Archive BookReader, Mirador, Universal Viewer | **Includes** | Page images and text side by side, citations, notes; every book is also a [IIIF](iiif.md) manifest, so Mirador and Universal Viewer open it |
| OCR and proofreading | Tesseract scripts, FromThePage, Wikisource-style projects | **Replaces** | OCR on ingest, re-OCR by zones, proofreading, ground truth. eScriptorium and Transkribus stay for training handwriting models |
| Preservation | Archivematica, Preservica, LOCKSS | **Replaces for small institutions** | Fixity, OCFL, BagIt, a second copy, ARKs. Not a full OAIS: no format migration |
| Library system (ILS) | Koha, Evergreen, SOUL, e-Granthalaya | **Complements** | Links the catalogue to the digital copies and sends the links back ([Koha](koha.md)) |
| Aggregators | NDLI, Europeana, DPLA, Wikidata, Wikimedia Commons, Wikisource, Internet Archive, e-reader apps | **Feeds** | OAI-PMH, OPDS, IIIF, Wikidata links, archive.org, and photographs and corrections given to Wikimedia under each person's own account |
| Digitisation workflow | Goobi, Kitodo, Scribe | Not covered | Starts after scanning |
| Archival description | AtoM, ArchivesSpace | **Includes the essentials** | Fonds to item (ISAD(G)), a hierarchy on the portal, EAD3 export, digitised items attached to units. Not authority records for creators and repositories (ISAAR(CPF)), accessions, or finding-aid import |
| Institutional repository | DSpace or EPrints for theses and papers | **Includes the essentials** | Deposit with review, licences and embargoes ([Deposit](deposit.md)); harvests DSpace and EPrints too. Not workflows with several reviewers, versioning of deposits or DOIs at deposit |

**Where the impact is largest:** small and mid-size libraries with Indic collections, which
cannot staff four systems; every install as a ready node for aggregators such as NDLI; a digital
layer for Koha libraries with no migration; and proofread Indic text and OCR ground truth.

**Gaps that would widen it**, in order: digitisation tracking for small projects (a book's way
through scanning, QA and ingest); archival authority records and accessions; a machine-draft
engine bundled in the image (today the engines are installed by the library); and, at national
scale, an OpenSearch adapter. Circulation, acquisitions and patrons stay with the library
system.

## Towards a full library system

Frappe makes it cheap to add the rest of an ILS alongside the digital library:

- **Holdings & items**: physical copies with barcodes and locations, linked to RD Item
- **Patrons & circulation**: members, loans, returns, fines (Frappe ships Contacts, Users,
  Web Forms, Payments)
- **Acquisitions**: Frappe/ERPNext purchasing if needed

Until then, Koha (or any ILS) can do those jobs, and Research Desk integrates through
OAI-PMH and MARC (see [Koha](koha.md)).

## Adding another source

Material from files is pluggable through *stores* (`core/folder.py`: an `ItemStore` lists items,
reads files, loads an item's metadata and its pages; the folder, Calibre, deposit, leaf-image,
recording and photograph stores are all one interface). Sources that are services are pluggable at two points: a client that lists and fetches items (like
`core/ia.py`) and a normaliser that returns the RD Item record shape (like
`core/normalize.normalize_ia_item`). The OAI-PMH source shows the pattern end to end:
`core/harvest.py` (the protocol client, Dublin Core to the record shape, finding the PDF),
`core/pdftext.py` (a PDF's text layer page by page) and `repository.py` (planning a run,
one record in a batch, the book's text when the cache doesn't have it).

**Books with a PDF and no archive.org scan** (repositories, folders, loose PDFs): `pdfs.py`
finds the book's PDF (its own file, our preservation copy, or a copy fetched and kept within a
size limit), draws its pages with poppler's `pdftoppm` (`core/pdfrender.py`, or the page's
embedded image without poppler) for *Page & text*, proofreading and re-OCR, and reads a scan
without text with Tesseract in a background job. OCR'd text is kept in `private/resdesk-ocr`
(it can't be fetched again) and comes before every other source in `ingest.fetch_pages`. See [Development → Adding a source](development.md#adding-a-new-source).

## Access control

`core/access.py` holds the rules (who may find or read a book, given its visibility, the
site's guest mode and whether the visitor is a reader) as pure functions with unit tests.
`access.py` applies them: portal pages and API endpoints check `can_find` / `can_read`;
searches add a Meilisearch filter for guests (`NOT visibility = "Login to find"` for books,
`NOT visibility IN [...]` for pages, so documents indexed before v0.5 count as Public); SQL
counts and OAI-PMH add the matching `WHERE` condition. Book and page documents carry
`visibility`, and bulk changes rewrite just that attribute with partial document updates,
so switching thousands of books never re-indexes their text.

