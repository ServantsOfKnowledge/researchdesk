# Roadmap

## v0.1: proof of concept (done)

- [x] Ingest from the Internet Archive by collection, query or identifier list
- [x] Metadata normalisation (languages, years, creators, subjects, romanised forms)
- [x] Book-level and page-level full-text search with facets (Meilisearch)
- [x] Public portal: search, filters, book page with IA reader, search inside a book
- [x] Citations: BibTeX, BibLaTeX, RIS, CSL-JSON, APA, MLA, Chicago; Zotero/Scholar metadata
- [x] Reading lists: export and share by link
- [x] OAI-PMH 2.0 provider (oai_dc, marc21) and MARCXML export for Koha
- [x] One-command Docker installer, CLI, scheduled ingests, CI running the installer

## v0.2 – v0.4: scale, your own books, easier running (done)

- [x] Parallel ingest across workers, page-text cache, measured to 50,000 books on one server
- [x] Docker developer mode (run code from your checkout)
- [x] Ingest IA-style item folders from disk, NAS or a web server; drop-folder mode with change detection
- [x] Stream local PDFs; check whether each local item already exists on archive.org
- [x] Library logo, favicon and home-page banner from the admin Settings
- [x] Native install (macOS/Homebrew, Ubuntu/Debian) without Docker
- [x] `upgrade.sh`: backup, upgrade to a release or main, migrate, health check, rollback hints

## v0.5: access control (done)

- [x] Public / Login to read / Login to find per book; public catalogue or internal-library modes
- [x] Reader accounts: staff-added, open sign-up or sign-up with approval
- [x] Bulk visibility by selection, filter, portal search, profile, rules and CLI

## v0.6 – v0.7: control, collections and metadata (done)

- [x] Background Jobs page: see, pause, resume and stop ingest and push runs, queued jobs and schedules
- [x] Curated collections (by hand, in bulk, by rules) with portal pages and OAI-PMH sets
- [x] Document types; staff edits kept on re-ingest ("Keep My Edits")
- [x] Metadata exports: spreadsheet, JSON, Dublin Core, MODS, MARCXML, JSON-LD, CSL-JSON, BibTeX, RIS, IA upload files
- [x] Bulk editing by spreadsheet import with preview
- [x] Push metadata to Internet Archive, Koha (REST), Wikidata and webhooks

## v0.8 – v0.11: running a library day to day (done)

- [x] Pause and resume runs, single jobs or everything; quiet hours
- [x] Help on every screen: in-app docs, form tours, a getting-started checklist, reader tips; docs checked against the code in CI
- [x] Resource presets, low-priority workers, one-file moves to another server or between Docker and native
- [x] Server page: versions and new releases, health of every part, nightly backups, logs, alerts (Desk, email, webhook)
- [x] Upgrades, rollbacks and restarts from the Desk through an optional updater helper
- [x] Book limit from the machine's CPUs, memory and disk
- [x] Profiles kept in step with archive.org (new, changed, removed books) and collections that mirror it

## Where we are going

Research Desk already searches inside every page of tens of thousands of books, handles Indic
scripts, and runs itself. Next it becomes a library that **keeps** its books, **names** them for
good, lets researchers **work with** them, and **improves** their text over time. Four pillars,
in this order:

1. **Preservation**: our own verified copies, so a book outlives any one website.
2. **Persistent identifiers**: a name for every book and page that never breaks.
3. **The OCR and correction loop**: better text for Indic books, from machines and from people.
4. **Annotation**: researchers highlight, comment, tag and link, alone or together.

Preservation, annotation and correction all need the **page images in our own reader**, not only
inside the archive.org reader. That shared foundation (IIIF) comes first.

### Foundation: our own reader (IIIF)

- [ ] IIIF Presentation manifests for every book, from archive.org's images or our own copies
- [ ] A IIIF image service for books we hold locally
- [x] A reader on the book page (page image + its text side by side), with the archive.org reader
      still one click away
- [x] Page-level links: `…/item/<id>/page/42` opens that page, and the citations can name it

### 1. Preservation

Today most books exist only on archive.org; if an item is darkened or removed there, we have its
catalogue record and page text but not the book. Preservation keeps master copies we control and
proves, on a schedule, that they are unchanged.

- [x] **Storage locations** (Settings): local disk or NAS first, then S3-compatible storage, each
      with a size budget that the book limit takes into account
- [x] **Preservation copies**, chosen by collection, profile or rule: the original files (PDF, page
      images, OCR, metadata) fetched once and stored as **OCFL** objects (a plain, versioned
      folder layout any future system can read without Research Desk)
- [x] **Fixity**: a SHA-256 checksum on arrival, compared with archive.org's, and a scheduled
      audit that re-checks a sample every night and every file over a cycle; failures alert on
      the Server page
- [x] **Preservation events** (PREMIS) on every book: fetched, checked, repaired, migrated, by whom
      and when, shown on the book and exportable
- [x] **Reading from our copy** when archive.org no longer serves a book (the sync already notices
      removals): the portal keeps working from the local files
- [x] **A second copy** elsewhere (another disk, a partner library, S3), with each book showing
      *copies: 2 of 2 verified*, and repair from the good copy when one fails its check
- [x] **BagIt** export of a book or a collection, for handing over to another archive
- [ ] File-format identification (PRONOM) and a report of formats at risk

### 2. Persistent identifiers

- [x] **ARK identifiers** for every book (`ark:/<NAAN>/…`; the ARK Alliance assigns the number for
      free), minted on ingest, with a check character, and resolved by the portal itself
- [x] **Page-level identifiers** (`ark:/…/p42`): a citation points at the page, not just the book
- [x] Identifiers carried everywhere a book goes: citations, OAI-PMH, exports, and pushes to Koha,
      Wikidata and the Internet Archive
- [x] **Never a dead link**: a book that is withdrawn or merged leaves a tombstone page saying what
      happened and where to go
- [ ] Optional **DOIs** (DataCite) for chosen collections, and Handles for libraries that use them

### 3. The OCR and correction loop

Much of the Indic text from archive.org is poor, and poor text cannot be searched. The loop
measures the text, replaces the worst of it with better machine OCR, lets people correct what
is left, and puts every improvement straight into search.

- [x] **OCR quality** for every page and book, from the text we already hold (share of real words
      for its language and script, broken characters, OCR confidence): a list of the worst books,
      and a quality filter for staff
- [x] **Text versions with provenance**: each page keeps archive.org's text, each re-OCR and each
      human correction, saying who or what made it; search uses the best version
- [x] **Re-OCR pipeline** on its own queue and workers, with pluggable engines (Tesseract with
      Indic models first; newer engines added as they prove better on our pages), run on the
      worst books first and kept only where the score improves; several languages at once (the
      book's languages and English, or a language per page part)
- [x] **Proofreading**: page image and text side by side, line by line; pages move from *not
      proofread* to *proofread* to *validated* (checked by a second person), as on Wikisource
- [x] **Proofreaders**: a reader role and sign-up, work lists by collection and language, credit on
      every page a person corrected, and review by staff
- [x] Corrections re-index the page at once and show on the portal as *proofread text*
- [x] **Ground truth**: corrected pages exported with their images as an open training set, so
      the community can build better Kannada, Konkani, Tamil and Hindi OCR, and the loop
      retrains our own engines

### 4. Annotation

- [x] **Annotations** following the W3C Web Annotation model: on a passage of page text, a region
      of a page image, a whole book or a collection; as a highlight, comment, tag, question or link
- [x] **Private, group or public**: private by default; research groups share theirs; public ones
      are reviewed by staff before they show
- [ ] **Annotations in search**: find your notes and your group's, and books by their tags
- [ ] **Links to people, places and works** (Wikidata) from an annotation, so notes build a map of
      who and what the books talk about
- [ ] **Export** with citations (to Zotero, as JSON-LD, Markdown or a spreadsheet), and the W3C
      Annotation Protocol so other tools (Mirador and others) can read and write them
- [x] Corrections and annotations meet: a reader who spots an OCR error annotates it, and it lands in
      the proofreading list

### Release plan (as shipped)

| Release | Brought |
|---|---|
| 0.20 | ARK identifiers and the resolver, tombstones; OCR quality scores; preservation copies on local disk with fixity and events |
| 0.21 | The search engine's queue under control; OCR quality visible |
| 0.22 | Our own reader (*Page & text*: page image beside its text), page links and page-level citations |
| 0.23 | Annotations: private, group and public with review, on text and images; My notes; exports; W3C AnnotationPage |
| 0.24 | Text versions, proofreading with validation, proofreaders and their work list; re-OCR by zone and of whole books |
| 0.24.1 | Each page's text with its own image (scan data); one Cite window |
| 0.25 | People & Roles, the library at a glance, private usage statistics |
| 0.26 | A second copy (folder or S3) with automatic repair; serving books from our copy; BagIt |
| 0.27 | Search in Latin letters for every Indic script; phrases, OR and exclusions |
| 0.28 | Server → Requirements: what the server has and lacks, installs from the Desk or with the upgrade |
| 0.29 | OCR in several languages at once; a language per page part |
| 0.30 | Sharing the loop: ground-truth sets (licence-gated), notes linked to Wikidata, the W3C Annotation Protocol, optional DOIs; a collection on the portal in minutes (bulk catalogue first) |
| 0.31 | Accessibility, first pass: Indic text marked for screen readers, read aloud, notes and zones without a mouse, WCAG 2.2 AA fixes, an accessibility statement |

Still open from the four pillars: IIIF manifests and an image service, PRONOM format
identification. (DOIs, the ground-truth export, Wikidata links from notes, the W3C Annotation
Protocol and finding books by their notes' tags shipped in 0.30.)

## Accessibility for every reader

The library's readers include blind and low-vision people, people with print disabilities, and
people who cannot use a mouse. Target: WCAG 2.2 AA and GIGW 3.0 (IS 17802) for the portal and our
Desk pages, and accessible copies under the Marrakesh Treaty and Copyright Act 52(1)(zb). The full
study and plan: docs/accessibility.md on main.

- [x] First pass (0.31): language of Indic text for screen readers, read aloud, keyboard paths for
      notes and proofreading, landmarks, labels, focus, an accessibility statement
- [ ] Testing with blind and low-vision readers (NVDA, TalkBack, Indic voices) with a partner
- [ ] axe-core checks in CI; reader settings (text size, spacing, dyslexia font, contrast)
- [ ] Our Desk pages audited; fixes for Frappe's Desk contributed upstream
- [ ] EPUB 3 / DAISY downloads of proofread books; sharing with Sugamya Pustakalaya

## Later: better search and data

- [x] Romanised ↔ Kannada query transliteration (type `vachana`, match ವಚನ) for all Indic scripts
- [x] Phrase search and boolean operators (OR, -word) in the portal; "near" still to come
- [ ] Search by meaning across languages, and answers to questions that cite the pages they come from
- [ ] Cataloguing help: titles, dates and subjects read from title pages, in a review queue for
      cataloguers (with records flagged for no year, unknown language or duplicate titles)
- [ ] Authority control: reconcile creators with VIAF/Wikidata; subjects with LCSH/Sears
- [ ] Collections as data: bulk text downloads and an API for text mining
- [ ] Saved, shared reading lists for logged-in readers
- [ ] Portal UI in Kannada and other languages (Frappe translations)
- [ ] More sources: Wikisource, DSpace/OAI-PMH repositories, bare PDFs with no OCR (run OCR on ingest)
- [ ] Offline collections (Kiwix packages) for schools and places with poor connections
- [ ] Federated search across several Research Desk libraries

## v1.0: library-grade

- [ ] OpenSearch adapter for very large page indexes
- [ ] SRU/Z39.50 target for older library systems
- [ ] Usage statistics (COUNTER-style), privacy-respecting
- [ ] Holdings, patrons and circulation stay with Koha: Research Desk works alongside it rather
      than replacing it

Ideas and priorities welcome: open an issue.
