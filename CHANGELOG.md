# Changelog

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
