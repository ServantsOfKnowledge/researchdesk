<img src="sok_resdesk/public/images/sok-logo.png" alt="Servants of Knowledge" height="64">

# SOK Research Desk

An open research portal and digital library for the books digitised by
[Servants of Knowledge](https://archive.org/details/ServantsOfKnowledge), and for any other
Internet Archive collection. It is built on the [Frappe](https://frappe.io) framework.

Choose a collection, a search or a list of items on archive.org, and Research Desk will:

- ingest from **archive.org** (a whole collection is listed on the portal within minutes, from
  archive.org's search records in bulk; page text follows in the background) *or* from
  **IA-style item folders** on your own disk, NAS or web
  server, with a drop folder that picks up new and changed books automatically
- **stay in step with archive.org** by itself: every day, books added to a collection come in,
  changed ones are refreshed and removed ones are unpublished, and every archive.org collection
  the books belong to (sub-collections too) gets a portal page that keeps itself up to date
- **catalogue** the books, cleaning up messy metadata (languages, dates, authors, subjects)
- **index the full OCR text page by page**, so people can search *inside* 88,000+ books,
  in Kannada, Hindi, Konkani, Tamil, English and more, typing in the script or **in Latin
  letters** (`kanakadasa` finds ಕನಕದಾಸ), with "phrases", `OR` and `-words`
- give each book a **public page** with two readers (archive.org's book reader, and **Page &
  text**: each page image beside its text), search inside the book, and **one Cite window** for
  the book or the page: BibTeX, BibLaTeX, RIS, CSL-JSON, APA, MLA and Chicago, with a link
- let readers keep **notes on pages** (highlights, comments, tags, questions, links, OCR error
  reports; private, shared with a research group, or public after review), following the W3C Web
  Annotation model, exported with page citations, linked to **Wikidata** (pages about a person,
  place or work gathered on one page), and open to other annotation tools through the **W3C Web
  Annotation Protocol**
- **improve the text over time**: an OCR quality score for every page and book; proofreading
  beside the page image, validated by a second person, every version kept; **re-OCR** with
  Tesseract's Indic models, **several languages at once** (the book's languages and English, or a
  language of its own for a verse or footnote), a page part by part (columns, headings) or whole
  books worst first; and share the corrected pages as **open OCR ground truth** under the
  library's chosen licence
- give books **DOIs** from DataCite for chosen collections (optional, for DataCite members)
- give every book and page a **permanent ARK** (on once the library's NAAN is assigned), with
  tombstones so no link ever dies
- **keep its own checked copies** of the books (OCFL, SHA-256, nightly fixity checks, PREMIS-style
  events), a **second copy** in another folder or an S3-compatible bucket with **automatic
  repair** from the good one, books kept on the portal **from our copy** when archive.org drops
  them, and **BagIt** exports for handing books to another archive
- work with **Zotero, Google Scholar and reference managers** (embedded citation metadata)
- work **alongside Koha** and other library systems (OAI-PMH harvesting and MARCXML import),
  or on its own
- let readers keep a **reading list**, export it as a bibliography, and share it as a link
- keep some books (or everything) **for logged-in readers**: members-only books, a public
  catalogue with reading for members, or an internal library; readers sign up, are approved,
  or are added by staff, and books can be switched in bulk by collection, filter or search
- carry **your library's logo and name** on the portal, the admin bar and the browser tab, with
  an **About page** introducing the library and how to use it, edited in the Desk
- let staff build **curated collections** (by hand, in bulk or by rules), each with its own
  portal page and OAI-PMH set, and **correct catalogue details** that survive re-ingest
- **export metadata** as a spreadsheet, JSON, Dublin Core, MODS, MARCXML, JSON-LD, BibTeX/RIS or
  Internet Archive upload files, and **edit many books at once** by importing an edited spreadsheet
- **push metadata** to the Internet Archive, Koha, Wikidata or any web service (webhook), with a
  dry run first and automatic updates when a book is edited
- **help on every screen**: the documentation is built into the portal (for readers) and the
  Desk (for staff), with step-by-step tours of the main forms, a getting-started checklist for
  a new library, and first-visit tips for readers
- manage **people and roles** on one Desk page (give or take a role with a tick, invite by
  email, approve sign-ups), see **the library at a glance** on the Desk (books, readers, logins,
  notes, proofreading, preservation, portal use), and count **portal use** privately (built in,
  or PostHog, Plausible or Umami; no cookies)
- **keep the machine usable**: resource presets for a laptop, desktop or server, low-priority
  background work, quiet hours that pause heavy work during the day, and a **book limit** worked
  out from the machine's CPUs, memory and disk, so it never takes on more than it can hold
- **move in one file** to another server, or between Docker and a native install
- **see, pause and stop background work** from the Desk: every ingest run, metadata push, queued
  job and schedule on one page; pause a run or everything and carry on later, hold single jobs,
  or stop them
- **look after the server from the Desk**: versions and new releases with their notes, the
  health of every part, **what the server has** (every library and native tool it needs, with
  versions, and installing what is missing from the Desk), nightly backups to download, errors and logs, and alerts by Desk
  notification, email or webhook. With the optional updater helper, upgrade (or go back),
  restart parts and apply resource presets from the Desk too
- go on a server with its own name and **HTTPS from Let's Encrypt** set up by the installer, and
  change the portal's address with one command
- run **in Docker or directly on the computer** (macOS or Ubuntu/Debian), and **upgrade with one
  command** (or one button) that backs up first and tells you how to roll back

It's built to install with one command, for librarians, educators, archivists and
anyone else who can open a terminal. It scales to tens of thousands of books on one server
([measured](docs/scaling.md)).

> Status: **v0.30**, before 1.0. It works end to end and is tested against live Servants of
> Knowledge data, but expect changes before 1.0. What changed: [CHANGELOG](CHANGELOG.md); what
> comes next: [the roadmap](docs/roadmap.md).

---

## Quick start (about 20 minutes, mostly waiting)

```bash
git clone https://github.com/ServantsOfKnowledge/researchdesk.git
cd researchdesk
./install.sh --check      # optional: looks at this machine and advises how to install
./install.sh              # asks: Docker (recommended) or directly on this computer
./install.sh --native     # no Docker: macOS (Homebrew) or Ubuntu/Debian (apt)
./install.sh --domain library.example.org   # on a server: its address, with HTTPS from Let's Encrypt
```

Docker needs [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Mac or Windows)
or Docker Engine (Linux). Native needs Homebrew or apt. Either way: 4 GB of free memory and 10 GB of disk.

The installer checks your computer and asks a few questions (you can press Enter to accept
each default). It then builds everything, creates the site and offers to load 20 sample
Kannada books. When it finishes it prints:

```
Portal (public):   http://localhost:8080/
Admin (Desk):      http://localhost:8080/app/research-desk
Login:             Administrator
Password:          ••••••••    (also in the .env file)
```

Moving it to a server with a DNS name later, or changing its address:

```bash
./resdesk.sh url https://library.example.org     # the address used in links and citations
./resdesk.sh https on library.example.org        # a free Let's Encrypt certificate, renewed by itself
```

Keep it up to date with one command. It backs up first and rolls back cleanly:

```bash
./upgrade.sh --check      # anything new?
./upgrade.sh              # upgrade to the latest release
```

Or from the browser: **Research Desk → Server** shows when a new release is out, the health of
every part and the backups. Turn on the updater helper once and upgrades, restarts and resource
presets are a button there too ([Server](docs/server.md)):

```bash
./resdesk.sh updater on
```

## Choose what to ingest

**In the browser:** Desk → Research Desk → **Ingest Profiles** → New:

| Choose by | Example |
|---|---|
| Collection | `ServantsOfKnowledge`, narrowed with `language:(kan OR Kannada)` |
| Search query | `collection:ServantsOfKnowledge AND subject:vachana` |
| Identifier list | one archive.org identifier per line |

Click **Check Count** to see how many items match, set **Maximum Items**, then **Run Ingest**.
After that first run the profile keeps itself in step with archive.org: new books come in each
day, changed ones are refreshed, removed ones are unpublished
([more](docs/ingesting.md#keeping-in-step-with-archiveorg)).

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
| Readers | [Using the library](docs/reader-guide.md) · [Searching](docs/searching.md) · [Citations & reading lists](docs/citations.md) |
| Library staff | [Staff guide: a tour of the Desk](docs/staff-guide.md) |
| Librarians & educators | [Getting started](docs/getting-started.md) · [Choosing & ingesting books](docs/ingesting.md) · [Your own folders & servers](docs/local-folders.md) |
| Library managers | [Who can see what: members-only books & reader accounts](docs/access.md) · [Collections, metadata, exports & pushing](docs/collections-and-metadata.md) · [Permanent links, preservation & OCR quality](docs/preservation.md) |
| Library systems staff | [Koha & interoperability](docs/koha.md) · [API](docs/api.md) |
| System administrators | [Installation](docs/installation.md) · [Server: updates, health & backups](docs/server.md) · [Operations](docs/operations.md) · [Moving to another server](docs/moving.md) · [Scaling to 50k books](docs/scaling.md) |
| Developers | [Architecture](docs/architecture.md) · [Development](docs/development.md) · [Roadmap](docs/roadmap.md) |

## How it fits together

```
 archive.org / your folders ──(metadata + OCR text)──▶ Ingest jobs ──▶ Frappe / MariaDB  (catalogue,
                                                        │                            notes, page texts)
                                                        └──────▶ Meilisearch       (books + pages)
  Proofreaders ──▶ corrections, re-OCR (Tesseract) ──▶ page text versions ──▶ search, reader, citations
  Preservation ──▶ OCFL copies + fixity ──▶ second copy (folder or S3) ⇄ repair · BagIt exports
                                                                        │
  Readers ◀── /        (search, read, cite) ◀── Frappe web + API ◀─────┘
  Koha, VuFind, aggregators ◀── OAI-PMH / MARCXML / exports (MODS, Dublin Core, JSON-LD)
  archive.org, Koha, Wikidata, webhooks ◀── push targets
  daily: new / changed / removed books from archive.org ──▶ Ingest jobs ──▶ mirrored collections
  Desk → Server ◀── health, backups, alerts ──▶ updater helper (optional): upgrade, restart
  Zotero, Google Scholar ◀── citation_* meta tags, JSON-LD, COinS
```

Books from your own folders or web server (`meta.xml` + OCR text + PDF) go through the same
pipeline; their PDFs are streamed from your disk.

Scans stay on the Internet Archive and are shown through its reader. Research Desk keeps the
catalogue and the search index, so a laptop can hold tens of thousands of books; preservation
copies of the books the library chooses are kept on its own storage.

## Licence

MIT. See [LICENSE](LICENSE). Book content belongs to its rights holders; each record shows
its licence as published on the Internet Archive.
