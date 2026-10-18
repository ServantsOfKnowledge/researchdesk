<img src="sok_resdesk/public/images/sok-logo.png" alt="Servants of Knowledge" height="64">

# SOK Research Desk

**An open-source digital library, archive and research platform for books, manuscripts,
photographs and recordings: made for Indian languages, open to every language.**

Bring in material from the Internet Archive, your own folders, Calibre, institutional
repositories, Wikisource and people's deposits. Research Desk makes it **searchable down to the
page** (in the script or in Latin letters), **readable and citable**, **correctable** by
proofreading, and **kept safe** with checked copies and permanent links. It shares what it holds
through open standards and gives back to Wikidata, Wikisource and Commons. It runs on
[Frappe](https://frappe.io) and is free software (MIT).

It is built for institutions: roles and members-only access, reviewed deposits, archival
description, accessibility checked in every release (WCAG 2.2 AA), a Server page with health
checks, backups and upgrades, and an optional **governance edition** for government records
(classification, audit log, retention, disclosure and redaction) that is installed only when
asked for. [Everything it does](docs/features.md).

> Status: before 1.0. It works end to end and is tested against live Servants of Knowledge data.
> What changed: [CHANGELOG](CHANGELOG.md). What comes next: [roadmap](docs/roadmap.md).

## Install

About 20 minutes, mostly waiting. Needs 4 GB of free memory and 10 GB of disk, and
[Docker](https://www.docker.com/products/docker-desktop/) (or macOS/Ubuntu for a native install).

```bash
git clone https://github.com/ServantsOfKnowledge/researchdesk.git
cd researchdesk
./install.sh                                 # asks a few questions; press Enter for the defaults
./install.sh --domain library.example.org    # on a server: its address, with HTTPS
./install.sh --edition governance            # also the records-office app
```

It prints the portal and Desk addresses and the administrator's password. Then choose what to
ingest (Desk → Ingest Profiles, or `./resdesk.sh ingest`), and keep it current with
`./upgrade.sh`. [Installation](docs/installation.md) · [Getting started](docs/getting-started.md) ·
[Choosing & ingesting books](docs/ingesting.md)

## Documentation

| For | Read |
|---|---|
| Readers | [Using the library](docs/reader-guide.md) · [Searching](docs/searching.md) · [Citations](docs/citations.md) |
| Library staff | [Staff guide](docs/staff-guide.md) · [Ingesting](docs/ingesting.md) · [Collections & metadata](docs/collections-and-metadata.md) |
| Archives | [Archival description](docs/archival-description.md) · [Manuscripts](docs/manuscripts.md) · [Photographs](docs/photographs.md) · [Audio & video](docs/audio-video.md) |
| Government & institutions | [Governance](docs/governance.md) · [Who can see what](docs/access.md) |
| Administrators | [Installation](docs/installation.md) · [Server](docs/server.md) · [Operations](docs/operations.md) · [Scaling](docs/scaling.md) |
| Developers | [Architecture](docs/architecture.md) · [Technology map](docs/technology.md) · [Development](docs/development.md) · [API](docs/api.md) |

All pages: [docs index](docs/README.md). They are also inside the app, under **Help**.

## Part of a chain

Servants of Knowledge builds the path from scanner to reader in the open: **TTScribe**, open
book-scanning hardware; [**Repub**](https://github.com/servantsofknowledge/repub), which crops,
straightens and reads each scan and exports a searchable PDF, text and the images; and Research Desk, which makes the
books searchable, citable, correctable and kept safe. **OpenScribe**, the last step, is in
progress.

## Licence

MIT. See [LICENSE](LICENSE). Book content belongs to its rights holders; each record shows its
licence as published on the Internet Archive.
