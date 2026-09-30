# Research Desk documentation

- [Using the library](reader-guide.md): for readers: finding, reading and citing books, My list, members-only books
- [Staff guide: a tour of the Desk](staff-guide.md): for library staff: the workspace, help and tours, the getting-started checklist, every part of the Desk

The same pages are inside the app: **Help** on the portal (for readers) and **Help** in the Desk (everything).

1. [Getting started](getting-started.md): install, load sample books, search and cite (for everyone)
2. [Installation](installation.md): Docker or native install (macOS, Ubuntu/Debian), prebuilt images, a server with a domain and HTTPS, Coolify, developer mode, upgrading
3. [Choosing & ingesting books](ingesting.md): profiles, archive.org search syntax, the Servants of Knowledge sub-collections, keeping in step with archive.org (new, changed and removed books; mirrored collections), schedules
   - [Books from your own folders or servers](local-folders.md): IA-style item folders on disk, NAS or a web server; drop-folder mode
4. [Searching](searching.md): books vs. inside-the-text search, filters, Kannada and other scripts
5. [Citations & reading lists](citations.md): formats, Zotero, sharing a bibliography
6. [Who can see what](access.md): members-only books, public catalogue or internal library, reader sign-up and approval, bulk changes
7. [Collections, metadata & pushing](collections-and-metadata.md): curated collections, editing details, exports (spreadsheet, MARCXML, MODS, Dublin Core, JSON-LD, IA), spreadsheet imports, pushing to Internet Archive, Koha, Wikidata or a webhook
8. [Koha & interoperability](koha.md): OAI-PMH harvesting, MARCXML import, standalone mode
9. [API](api.md): public HTTP endpoints
10. [Server: updates, health & backups](server.md): the Server page in the Desk: new releases, health of every part, the book limit, backups, logs, alerts; upgrading and restarting from the Desk with the updater helper
11. [Operations](operations.md): upgrading and rolling back, backups, workers, background jobs (see, pause, resume and stop), resources (presets, quiet hours), re-indexing, logo & branding, troubleshooting
   - [Moving to another server](moving.md): one-file export and import, `move-to` over SSH, Docker ↔ native
12. [Scaling to 50,000 books](scaling.md): measured numbers, server sizing, running a large ingest
13. [Architecture](architecture.md): components, data model, scaling from a laptop to a national library
14. [Development](development.md): code layout, tests, adding a new source
15. [Roadmap](roadmap.md)
