<img src="../sok_resdesk/public/images/sok-logo.png" alt="Servants of Knowledge" height="64">

# Research Desk documentation

- [Using the library](reader-guide.md): for readers: finding, reading and citing books, My list, members-only books
- [Accessibility](accessibility.md): keyboard, screen readers and Indian-language voices, read aloud; the standards followed and the plan
- [Staff guide: a tour of the Desk](staff-guide.md): for library staff: the workspace, help and tours, the getting-started checklist, every part of the Desk

The same pages are inside the app: **Help** on the portal (for readers) and **Help** in the Desk (everything).

1. [Getting started](getting-started.md): install, load sample books, search and cite (for everyone)
2. [Installation](installation.md): Docker or native install (macOS, Ubuntu/Debian), prebuilt images, a server with a domain and HTTPS from Let's Encrypt (also [step by step on a server that already runs nginx](installation.md#step-by-step-a-new-linux-server-that-already-runs-nginx)), changing the portal's address, Coolify, developer mode, upgrading
3. [Choosing & ingesting books](ingesting.md): profiles, archive.org search syntax, the Servants of Knowledge sub-collections, keeping in step with archive.org (new, changed and removed books; mirrored collections), schedules
   - [Books from your own folders or servers](local-folders.md): IA-style item folders on disk, NAS or a web server; drop-folder mode
   - [Photographs](photographs.md): photographs as items with their EXIF, who and where, a SHA-256 of the original and a zoom viewer
   - [Audio and video](audio-video.md): recordings in folders and from archive.org, with a player, a time-coded transcript, captions and IIIF
   - [Manuscripts and palm leaves](manuscripts.md): describing them, labelling leaves (1a, 1b…), transcribing leaves nobody has read
   - [Repository deposit](deposit.md): people deposit their own work (files, licence, embargo); a librarian reviews and accepts it
   - [Books from a Calibre library](calibre.md): a whole Calibre library, with its details, covers and files, read without changing it
   - [Books from repositories](repositories.md): DSpace, EPrints and any OAI-PMH repository; their PDFs' text page by page; kept in step
   - [Books from Wikisource](wikisource.md): scanned books transcribed and proofread on any language's Wikisource, with their page text and page images
   - [Giving back to Wikimedia](wikimedia.md): connect your own Wikimedia account; what you send to Wikidata is sent as you
4. [Searching](searching.md): books vs. inside-the-text search, filters, Kannada and other scripts
5. [Citations & reading lists](citations.md): formats, Zotero, sharing a bibliography
6. [Who can see what](access.md): members-only books, public catalogue or internal library, reader sign-up and approval, bulk changes
7. [Collections, metadata & pushing](collections-and-metadata.md): curated collections, editing details, exports (spreadsheet, MARCXML, MODS, Dublin Core, JSON-LD, IA), spreadsheet imports, pushing to Internet Archive, Koha, Wikidata or a webhook
   - [Permanent links, preservation & OCR quality](preservation.md): ARKs for every book and page, tombstones, the library's own checked copies (OCFL), a second copy (folder or S3) with automatic repair, serving books from our copy, BagIt exports, preservation events, OCR quality scores
8. [Koha & interoperability](koha.md): OAI-PMH harvesting, MARCXML import, standalone mode
   - [IIIF](iiif.md): every book as a manifest for Mirador, Universal Viewer and other viewers; collections; an image service for books drawn from PDFs
   - [Offline copies and Kiwix](offline.md): a collection as a folder of web pages for USB sticks, phones and Kiwix (ZIM)
   - [OPDS](opds.md): the library as a catalogue for e-reader apps: newest books, collections, search and downloads
9. [API](api.md): public HTTP endpoints
10. [Server: updates, health & backups](server.md): the Server page in the Desk: new releases, health of every part, the book limit, backups, logs, alerts; upgrading and restarting from the Desk with the updater helper
11. [Operations](operations.md): upgrading and rolling back, backups, workers, background jobs (see, pause, resume and stop), resources (presets, quiet hours), re-indexing, logo & branding, troubleshooting
   - [Moving to another server](moving.md): one-file export and import, `move-to` over SSH, Docker ↔ native
12. [Scaling to 50,000 books](scaling.md): measured numbers, server sizing, running a large ingest
13. [Architecture](architecture.md): components, data model, scaling from a laptop to a national library
14. [Development](development.md): code layout, tests, adding a new source
15. [Roadmap](roadmap.md)
