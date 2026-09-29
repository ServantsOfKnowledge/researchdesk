# Roadmap

## v0.1: proof of concept (this release)

- [x] Ingest from the Internet Archive by collection, query or identifier list
- [x] Metadata normalisation (languages, years, creators, subjects, romanised forms)
- [x] Book-level and page-level full-text search with facets (Meilisearch)
- [x] Public portal: search, filters, book page with IA reader, search inside a book
- [x] Citations: BibTeX, BibLaTeX, RIS, CSL-JSON, APA, MLA, Chicago; Zotero/Scholar metadata
- [x] Reading lists: export and share by link
- [x] OAI-PMH 2.0 provider (oai_dc, marc21) and MARCXML export for Koha
- [x] One-command Docker installer, CLI, scheduled ingests, CI running the installer

## v0.2: better for researchers

- [ ] Romanised ↔ Kannada query transliteration (type `vachana`, match ವಚನ) for all Indic scripts
- [ ] Phrase search, boolean operators and "near" in the portal
- [ ] Accounts with saved, shared, collaborative reading lists and notes
- [ ] Page-level citations (cite p. 42 with a stable link)
- [ ] Persistent identifiers (ARK/Handle/DOI) for portal records
- [ ] Portal UI in Kannada and other languages (Frappe translations)

## v0.3: better data

- [ ] Re-OCR pipeline for poor scans (Tesseract/other engines with trained Kannada models), replacing IA text in the index
- [ ] Authority control: reconcile creators with VIAF/Wikidata; subjects with LCSH/Sears
- [ ] Cataloguer review queue for flagged records (no year, unknown language, duplicate titles)
- [ ] More sources: Wikisource, DSpace/OAI-PMH repositories, local PDF uploads with OCR

## v1.0: library-grade

- [ ] OpenSearch adapter for very large page indexes
- [ ] IIIF manifests and a self-hosted viewer (Mirador) as an alternative to the IA embed
- [ ] Holdings, patrons and circulation, for standalone use as a library system
- [ ] SRU/Z39.50 target for older ILS integrations
- [ ] Usage statistics (COUNTER-style), privacy-respecting

Ideas and priorities welcome: open an issue.
