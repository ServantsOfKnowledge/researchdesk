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

- [x] Background Jobs page: see and stop ingest runs, queued jobs and schedules
- [x] Curated collections (by hand, in bulk, by rules) with portal pages and OAI-PMH sets
- [x] Document types; staff edits kept on re-ingest ("Keep My Edits")
- [x] Metadata exports: spreadsheet, JSON, Dublin Core, MODS, MARCXML, JSON-LD, CSL-JSON, BibTeX, RIS, IA upload files
- [x] Bulk editing by spreadsheet import with preview
- [x] Push metadata to Internet Archive, Koha (REST), Wikidata and webhooks

## Next: better for researchers

- [ ] Romanised ↔ Kannada query transliteration (type `vachana`, match ವಚನ) for all Indic scripts
- [ ] Phrase search, boolean operators and "near" in the portal
- [ ] Saved, shared, collaborative reading lists and notes for logged-in readers
- [ ] Page-level citations (cite p. 42 with a stable link)
- [ ] Persistent identifiers (ARK/Handle/DOI) for portal records
- [ ] Portal UI in Kannada and other languages (Frappe translations)

## Then: better data

- [ ] Re-OCR pipeline for poor scans (Tesseract/other engines with trained Kannada models), replacing IA text in the index
- [ ] Authority control: reconcile creators with VIAF/Wikidata; subjects with LCSH/Sears
- [ ] Cataloguer review queue for flagged records (no year, unknown language, duplicate titles)
- [ ] More sources: Wikisource, DSpace/OAI-PMH repositories, bare PDFs with no OCR (run OCR on ingest)

## v1.0: library-grade

- [ ] OpenSearch adapter for very large page indexes
- [ ] IIIF manifests and a self-hosted viewer (Mirador) as an alternative to the IA embed
- [ ] Holdings, patrons and circulation, for standalone use as a library system
- [ ] SRU/Z39.50 target for older ILS integrations
- [ ] Usage statistics (COUNTER-style), privacy-respecting

Ideas and priorities welcome: open an issue.
