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

## v0.12 – v0.19: easier to install, run and grow (done)

- [x] A portal page for every archive.org collection; the library at `/`; an About page
- [x] HTTPS from Let's Encrypt, the portal's address in one command, Coolify
- [x] Big ingests that don't stall or do work twice; failed books retried by themselves
- [x] Worker priority from the Desk; the portal's book count kept up with the catalogue

## v0.20 – v0.31: a research library (done)

- [x] Permanent links: ARKs for every book and page (switched on once the NAAN is assigned), tombstones
- [x] Preservation: OCFL copies with SHA-256 fixity checks and PREMIS-style events; a second copy
      (folder or S3-compatible) with automatic repair; books kept on the portal from our copy;
      BagIt exports
- [x] OCR quality scores for every page and book; the search queue under control
- [x] *Page & text*: each page image beside its text, page links, page-level citations; one Cite
      window for the book or the page
- [x] Notes on pages (W3C Web Annotation): private, research groups, public with review; My notes
      with exports
- [x] Proofreading with validation by a second person; re-OCR with Tesseract's Indic models, a
      page part by part or whole books worst first, in several languages at once; a proofreaders'
      work list
- [x] Search in Latin letters for every Indic script (`vachana` finds ವಚನ), phrases, OR and
      words left out
- [x] People & Roles in the Desk, the library at a glance on login, private usage statistics
- [x] Server → Requirements: what the server has and lacks, installing it from the Desk (native)
      or with the upgrade (Docker, OCR languages chosen in `.env`)

- [x] Sharing the loop: corrected pages as open OCR ground truth (once a licence is chosen); notes
      linked to Wikidata people, places and works, with a page for each; the W3C Annotation
      Protocol for other tools; optional DOIs (DataCite) for chosen collections
- [x] A collection on the portal within minutes: catalogue from archive.org's search records in
      bulk, page text in the background; every collection on one page
- [x] Accessibility, first pass (WCAG 2.2 AA, GIGW 3.0): skip link, focus, landmarks, labels,
      Indic text marked with its language for screen readers, read aloud, notes and proofreading
      zones without a mouse, schema.org accessibility metadata, an accessibility statement

## Next

- [ ] **Accessibility** (details and the full plan: [Accessibility](accessibility.md)): testing with
      blind and low-vision readers using NVDA and TalkBack with Indic voices; axe-core checks in
      CI; reader settings (text size, spacing, dyslexia-friendly font, high contrast); an audit of
      our Desk pages against WCAG 2.2 AA; later EPUB 3 / DAISY downloads of proofread books and
      sharing with Sugamya Pustakalaya under the Marrakesh Treaty and Copyright Act 52(1)(zb)
- [ ] Portal UI in Kannada and other languages (Frappe translations)
- [ ] Authority control: reconcile creators with VIAF/Wikidata; subjects with LCSH/Sears
- [ ] Cataloguer review queue for flagged records (no year, unknown language, duplicate titles)
- [ ] More sources: Wikisource, DSpace/OAI-PMH repositories, bare PDFs with no OCR (OCR on ingest)
- [ ] Offline collections (Kiwix packages) for schools and places with poor connections

## v1.0: library-grade

- [ ] OpenSearch adapter for very large page indexes
- [ ] IIIF manifests and an image service for books held locally
- [ ] Holdings, patrons and circulation stay with Koha: Research Desk works alongside it
- [ ] SRU/Z39.50 target for older ILS integrations
- [ ] Usage statistics in COUNTER form, for libraries that report them

Ideas and priorities welcome: open an issue.
