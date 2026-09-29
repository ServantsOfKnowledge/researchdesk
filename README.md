# SoK Research Desk

An open research portal and digital library for the books digitised by
[Servants of Knowledge](https://archive.org/details/ServantsOfKnowledge), and for any other
Internet Archive collection. It is built on the [Frappe](https://frappe.io) framework.

Choose a collection, a search or a list of items on archive.org, and Research Desk will:

- **catalogue** the books, cleaning up messy metadata (languages, dates, authors, subjects)
- **index the full OCR text page by page**, so people can search *inside* 88,000+ books,
  in Kannada, Hindi, Konkani, Tamil, English and more
- give each book a **public page** with a reader, search inside the book, and
  **ready-made citations**: BibTeX, BibLaTeX, RIS, CSL-JSON, APA, MLA and Chicago
- work with **Zotero, Google Scholar and reference managers** (embedded citation metadata)
- work **alongside Koha** and other library systems (OAI-PMH harvesting and MARCXML import),
  or on its own
- let readers keep a **reading list**, export it as a bibliography, and share it as a link

It's built to install with one command, for librarians, educators, archivists and
anyone else who can open a terminal.

> Status: **proof of concept (v0.1)**. It works end to end and is tested against live
> Servants of Knowledge data, but expect changes before 1.0. See [the roadmap](docs/roadmap.md).

---

## Quick start (about 20 minutes, mostly waiting)

You need [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Mac or Windows)
or Docker Engine (Linux), 4 GB of free memory and 10 GB of disk.

```bash
git clone https://github.com/omshivaprakash/sok-resdesk.git
cd sok-resdesk
./install.sh
```

The installer checks your computer and asks four questions (you can press Enter to accept
each default). It then builds everything, creates the site and offers to load 20 sample
Kannada books. When it finishes it prints:

```
Portal (public):   http://localhost:8080/library
Admin (Desk):      http://localhost:8080/app/research-desk
Login:             Administrator
Password:          ••••••••    (also in the .env file)
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
| Librarians & educators | [Getting started](docs/getting-started.md) · [Choosing & ingesting books](docs/ingesting.md) |
| Researchers | [Searching](docs/searching.md) · [Citations & reading lists](docs/citations.md) |
| Library systems staff | [Koha & interoperability](docs/koha.md) · [API](docs/api.md) |
| System administrators | [Installation](docs/installation.md) · [Operations](docs/operations.md) |
| Developers | [Architecture](docs/architecture.md) · [Development](docs/development.md) · [Roadmap](docs/roadmap.md) |

## How it fits together

```
 archive.org ──(scrape + metadata + OCR text)──▶ Ingest jobs ──▶ Frappe / MariaDB  (catalogue)
                                                        │
                                                        └──────▶ Meilisearch       (books + pages)
                                                                        │
  Readers ◀── /library  (search, read, cite) ◀── Frappe web + API ◀─────┘
  Koha, VuFind, aggregators ◀── OAI-PMH / MARCXML
  Zotero, Google Scholar ◀── citation_* meta tags, JSON-LD, COinS
```

Scans stay on the Internet Archive and are shown through its reader. Research Desk keeps the
catalogue and the search index, so a laptop can hold tens of thousands of books.

## Licence

MIT. See [LICENSE](LICENSE). Book content belongs to its rights holders; each record shows
its licence as published on the Internet Archive.
