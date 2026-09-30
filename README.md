# SoK Research Desk

An open research portal and digital library for the books digitised by
[Servants of Knowledge](https://archive.org/details/ServantsOfKnowledge), and for any other
Internet Archive collection. It is built on the [Frappe](https://frappe.io) framework.

Choose a collection, a search or a list of items on archive.org, and Research Desk will:

- ingest from **archive.org** *or* from **IA-style item folders** on your own disk, NAS or web
  server, with a drop folder that picks up new and changed books automatically
- **catalogue** the books, cleaning up messy metadata (languages, dates, authors, subjects)
- **index the full OCR text page by page**, so people can search *inside* 88,000+ books,
  in Kannada, Hindi, Konkani, Tamil, English and more
- give each book a **public page** with a reader, search inside the book, and
  **ready-made citations**: BibTeX, BibLaTeX, RIS, CSL-JSON, APA, MLA and Chicago
- work with **Zotero, Google Scholar and reference managers** (embedded citation metadata)
- work **alongside Koha** and other library systems (OAI-PMH harvesting and MARCXML import),
  or on its own
- let readers keep a **reading list**, export it as a bibliography, and share it as a link
- keep some books (or everything) **for logged-in readers**: members-only books, a public
  catalogue with reading for members, or an internal library; readers sign up, are approved,
  or are added by staff, and books can be switched in bulk by collection, filter or search
- carry **your library's logo and name** on the portal, the admin bar and the browser tab
- let staff build **curated collections** (by hand, in bulk or by rules), each with its own
  portal page and OAI-PMH set, and **correct catalogue details** that survive re-ingest
- **export metadata** as a spreadsheet, JSON, Dublin Core, MODS, MARCXML, JSON-LD, BibTeX/RIS or
  Internet Archive upload files, and **edit many books at once** by importing an edited spreadsheet
- **push metadata** to the Internet Archive, Koha, Wikidata or any web service (webhook), with a
  dry run first and automatic updates when a book is edited
- **see and stop background work** from the Desk: every ingest run, queued job and schedule on one
  page, with Stop, Stop now and Stop Everything
- run **in Docker or directly on the computer** (macOS or Ubuntu/Debian), and **upgrade with one
  command** that backs up first and tells you how to roll back

It's built to install with one command, for librarians, educators, archivists and
anyone else who can open a terminal. It scales to tens of thousands of books on one server
([measured](docs/scaling.md)).

> Status: **proof of concept (v0.7)**. It works end to end and is tested against live
> Servants of Knowledge data, but expect changes before 1.0. See [the roadmap](docs/roadmap.md).

---

## Quick start (about 20 minutes, mostly waiting)

```bash
git clone https://github.com/ServantsOfKnowledge/researchdesk.git
cd researchdesk
./install.sh              # asks: Docker (recommended) or directly on this computer
./install.sh --native     # no Docker: macOS (Homebrew) or Ubuntu/Debian (apt)
```

Docker needs [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Mac or Windows)
or Docker Engine (Linux). Native needs Homebrew or apt. Either way: 4 GB of free memory and 10 GB of disk.

The installer checks your computer and asks a few questions (you can press Enter to accept
each default). It then builds everything, creates the site and offers to load 20 sample
Kannada books. When it finishes it prints:

```
Portal (public):   http://localhost:8080/library
Admin (Desk):      http://localhost:8080/app/research-desk
Login:             Administrator
Password:          ••••••••    (also in the .env file)
```

Keep it up to date with one command. It backs up first and rolls back cleanly:

```bash
./upgrade.sh --check      # anything new?
./upgrade.sh              # upgrade to the latest release
```

## Choose what to ingest

**In the browser:** Desk → Research Desk → **Ingest Profiles** → New:

| Choose by | Example |
|---|---|
| Collection | `ServantsOfKnowledge`, narrowed with `language:(kan OR Kannada)` |
| Search query | `collection:ServantsOfKnowledge AND subject:vachana` |
| Identifier list | one archive.org identifier per line |

Click **Check Count** to see how many items match, set **Maximum Items**, then **Run Ingest**.

**From the terminal:**

```bash
./resdesk.sh count  --collection ServantsOfKnowledge --filter "language:kan"
./resdesk.sh ingest --collection ServantsOfKnowledge --filter "language:kan" --limit 100
./resdesk.sh ingest --collection KannadaUniversity --limit 50
./resdesk.sh help
```

## Documentation

| For | Read |
|---|---|
| Librarians & educators | [Getting started](docs/getting-started.md) · [Choosing & ingesting books](docs/ingesting.md) · [Your own folders & servers](docs/local-folders.md) |
| Researchers | [Searching](docs/searching.md) · [Citations & reading lists](docs/citations.md) |
| Library managers | [Who can see what: members-only books & reader accounts](docs/access.md) · [Collections, metadata, exports & pushing](docs/collections-and-metadata.md) |
| Library systems staff | [Koha & interoperability](docs/koha.md) · [API](docs/api.md) |
| System administrators | [Installation](docs/installation.md) · [Operations](docs/operations.md) · [Scaling to 50k books](docs/scaling.md) |
| Developers | [Architecture](docs/architecture.md) · [Development](docs/development.md) · [Roadmap](docs/roadmap.md) |

## How it fits together

```
 archive.org / your folders ──(metadata + OCR text)──▶ Ingest jobs ──▶ Frappe / MariaDB  (catalogue)
                                                        │
                                                        └──────▶ Meilisearch       (books + pages)
                                                                        │
  Readers ◀── /library  (search, read, cite) ◀── Frappe web + API ◀─────┘
  Koha, VuFind, aggregators ◀── OAI-PMH / MARCXML / exports (MODS, Dublin Core, JSON-LD)
  archive.org, Koha, Wikidata, webhooks ◀── push targets
  Zotero, Google Scholar ◀── citation_* meta tags, JSON-LD, COinS
```

Books from your own folders or web server (`meta.xml` + OCR text + PDF) go through the same
pipeline; their PDFs are streamed from your disk.

Scans stay on the Internet Archive and are shown through its reader. Research Desk keeps the
catalogue and the search index, so a laptop can hold tens of thousands of books.

## Licence

MIT. See [LICENSE](LICENSE). Book content belongs to its rights holders; each record shows
its licence as published on the Internet Archive.
