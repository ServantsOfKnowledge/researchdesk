# Development

## Repository layout

```
researchdesk/
├── install.sh              one-command installer (asks: Docker or native)
├── upgrade.sh              backup → new code → migrate → restart → health check
├── resdesk.sh              everyday commands (docker compose or the native bench)
├── compose.yaml            full stack
├── compose.dev.yaml        developer mode: mounts this folder into the containers
├── docker/                 Dockerfile, entrypoint, gunicorn start, create-site
├── scripts/
│   ├── upgrade-plan.sh     what a release changed → restart the web part, roll the workers, or everything (gentle upgrades)
│   ├── install-native.sh   native install: packages, Python 3.14 (uv), Node 24 (nvm), bench, site
│   ├── native-procfile.sh  Procfile for native runs (gunicorn, Meilisearch, extra workers)
│   ├── dev-setup.sh        bench setup for developers
│   ├── gen_docs.py         the generated parts of docs/ (./resdesk.sh docs)
│   ├── screenshots.py      retake the pictures in docs/ (./resdesk.sh screenshots)
│   ├── release.sh          check docs + changelog, set the version, tag
│   └── publish.sh          put the newest release on GitHub's main (and push the tags)
├── docs/                   this documentation
├── .github/workflows/      CI (lint, unit, Docker install + integration) and image publishing
└── sok_resdesk/            the Frappe app
    ├── hooks.py            routes, doc events, scheduler, install hooks
    ├── core/               pure Python, no Frappe:  ia.py  folder.py  normalize.py  citations.py  marc.py  oai.py  access.py
    │                                           mail.py (outgoing email presets, plain-words errors)  known_errors.py (Log QA: which release fixed which error)
    │                                           helpdocs.py (docs as help pages)  collections.py (rules, slugs)  metaio.py (export formats, spreadsheet)  push.py (IA, Koha, Wikidata, webhook clients)
    │                                           ark.py (ARKs, check character)  ocfl.py (preservation copies)  replica.py (second copy: folder, S3)  bagit.py (BagIt bags)
    │                                           ocrquality.py (OCR scores)  ocr_engine.py (Tesseract by zone, several languages)  zones.py (page zones)  scandata.py (OCR page ↔ page image)
    │                                           translit.py (romanised words → Indic spellings)  groundtruth.py (OCR training sets)  wikidata.py  datacite.py (DOI records)  annotations.py (W3C anchoring)  capacity.py  quiet.py  schema.py  updates.py  equipment.py (programs, packages, versions)
    ├── catalogue.py        settings, upsert RD Item, record <-> dict
    ├── ingest.py           ingest jobs, scheduler, whitelisted actions
    ├── ia_sync.py          keeping profiles in step with archive.org (new, changed, removed books)
    ├── local_source.py     IA-style item folders on disk / NAS / web server
    ├── search.py           Meilisearch adapter, indexing, search (romanised words, OR, federated)
    ├── search_queue.py     the search engine's queue: books first, page text held or paced
    ├── access.py           who can see what: members, bulk visibility, reader sign-up
    ├── people.py           People & Roles page: roles, invitations, accounts, sign-ups
    ├── identifiers.py      ARKs: minting, resolver, tombstones
    ├── preservation.py     preservation copies, fixity, second copy, repair, serving from copy, BagIt
    ├── ocr.py              OCR quality of the catalogue
    ├── pagetext.py         page text versions: proofreading, validation, history
    ├── reocr.py            re-OCR of a page (zones) or of whole books
    ├── page_order.py       putting each page's text with its own image (books from before 0.24.1)
    ├── annotations.py      readers' notes on pages, research groups, exports, Wikidata items and tags
    ├── annotation_protocol.py  the W3C Web Annotation Protocol for other annotation tools
    ├── groundtruth.py      ground-truth sets: proofread pages with their images, licence-gated
    ├── datacite.py         DOIs from DataCite for chosen collections
    ├── dashboard.py        the numbers on the Research Desk workspace
    ├── analytics.py        usage statistics (built-in, PostHog, Plausible, Umami)
    ├── counter.py          COUNTER style usage reports from the built-in page views (core/counter.py has the format)
    ├── sru.py              SRU 1.2 at /sru for older library systems (core/sru.py has CQL and the XML)
    ├── curation.py         curated collections: membership, rules, counts
    ├── transfer.py         metadata exports and spreadsheet imports
    ├── outbound.py         push runs to other systems, automatic pushes
    ├── jobs.py             Background Jobs page: see, pause, resume and stop runs and queued jobs
    ├── holding.py          held jobs (Pause All / Hold) and the @hold_when_paused job decorator
    ├── priority.py         worker CPU priority (renice) from the Desk
    ├── server.py           the Server page: versions, health, backups, the updater helper
    ├── requirements.py     Server → Requirements: what the server has, installing what is missing
    ├── help.py             in-app help pages and each screen's Help link (from docs/*.md)
    ├── guide.py            form tours and the getting-started checklist
    ├── portal.py           helpers for portal pages (collection cards, facet labels)
    ├── api.py              public API
    ├── oai.py              OAI-PMH endpoint (Frappe store for core/oai.py)
    ├── about.py            the About page (/about), edited in the Desk
    ├── authority.py        authority control: authors matched to Wikidata and VIAF, subjects to LCSH
    ├── contribute.py       giving back to Wikidata (names in their scripts, author links)
    ├── review.py           the cataloguer's review queue
    ├── features.py         features and institution profiles (Settings → Features)
    ├── deskscope.py        the Desk shows Research Desk only (trimmed boot, redirects)
    ├── sidebar.py          the Desk's one sidebar: every screen in sections, plus Administration
    ├── seo.py  security.py robots.txt, sitemap and link previews; secure-by-default headers and lock-out
    ├── translations.py     the portal in Kannada and other languages
    ├── collectioncovers.py collection pictures from archive.org
    ├── librarysystems.py   a library system's catalogue (Koha, MARC) matched and linked back
    ├── iiif.py  opds.py    /iiif/… manifests and image service; /opds catalogue for e-reader apps (answered before routing)
    ├── pdfs.py             pages of books not on archive.org drawn as images, OCR of scans, leaf images
    ├── wikimedia.py        each person's own Wikimedia account (OAuth 2.0 token, encrypted)
    ├── wikisource.py       Wikisource as a source, and sending proofread pages back
    ├── commons.py          sending a photograph to Wikimedia Commons (review, licence check, depicts)
    ├── calibre_export.py   exporting a collection as a Calibre library
    ├── deposit.py          repository deposit: people give their work, a reviewer accepts it
    ├── manuscripts.py      manuscripts and palm leaves: labelling leaves, transcription from blank
    ├── media.py            audio and video: lengths, transcript segments
    ├── commands.py         `bench … resdesk` CLI
    ├── setup.py            roles, defaults, sample profiles, setup wizard, branding
    ├── native_wsgi.py      gunicorn entry point for native installs (static files, default site)
    ├── patches/            data migrations between versions (listed in patches.txt)
    ├── resdesk/workspace/  the Research Desk workspace (shipped as a file so migrate keeps it)
    ├── resdesk/doctype/    DocTypes (JSON + controllers + form scripts)
    ├── resdesk/page/       Desk pages: Background Jobs, Server, Help, People & Roles
    ├── www/library/        portal pages (index = search, item = book page, collections, collection, help, notes, proofread)
    ├── public/             css/resdesk.css, js/library.js, js/item.js (Cite window), js/reader.js (Page & text),
    │                       js/annotate.js (notes), js/proofread.js (proofreading, zones), js/analytics.js,
    │                       js/basket.js, js/tips.js, js/desk_help.js (help, checklist, numbers), images/guide/
    └── tests/              unit_*.py, test_core.py, test_push.py, test_docs.py (pytest, no Frappe);
                            test_integration.py, test_operations.py, test_server.py, test_mail.py, test_profile.py,
                            test_log_qa.py … (Frappe, in CI's Docker job); unit_mail.py, unit_profile_clean.py,
                            unit_known_errors.py, unit_upgrade_plan.py (pure)
```

## Keeping the search engine pluggable

Meilisearch is the default search engine, and OpenSearch is planned as a second one for very large
page indexes. To keep that a small change later: code that searches or indexes goes through
`search.py` (`MeiliClient`, `IndexBuffer`, `index_record`) and `search_queue.py`, never straight to
Meilisearch's API from elsewhere, and the settings it needs live in Settings → Search. A new
engine means a client with the same methods (set up indexes, add and delete documents, search with
facets, report its queue), a choice in Settings → Search, and tests that run the same cases on both.

## The Desk's sidebar across Frappe releases

The Research Desk sidebar is one list (`sok_resdesk/core/sidebar.py`). From Frappe 16.50 a module's
sidebar is a `Sidebar` document an app ships as a file and no longer edits on a site, so
`python scripts/make_sidebar_json.py` writes `resdesk/sidebar/research_desk/research_desk.json` from
the list (a unit test fails if they differ); before 16.50 `sidebar.refresh()` rewrites the Workspace
Sidebar. Switched-off features' screens are taken out of what the Desk is sent (`features.trim_boot`),
and the Desk-only scope trims it too (`deskscope.trim_boot`); both handle either payload. When Frappe
changes how the Desk is built, CI (which installs the newest Frappe 16) is where it shows first.

## Workflow

**Easiest: Docker developer mode.** `./resdesk.sh dev on` runs the code from your checkout
live inside the containers (see [Installation → Developer mode](installation.md#developer-mode-docker-code-from-this-folder)).
Edit, save, reload the page; `./resdesk.sh restart` for worker code; `./resdesk.sh migrate`
after DocType changes; run tests with the commands below.

**Or native bench** (see [Installation → Developer setup](installation.md#developer-setup-bench)):

```bash
bench start                                        # web + workers + watcher
bench --site resdesk.localhost migrate             # after changing DocType JSON
bench --site resdesk.localhost resdesk ingest --collection ServantsOfKnowledge --limit 5
```

Edit DocTypes in the Desk with `developer_mode` on: Frappe writes the JSON back into
`sok_resdesk/resdesk/doctype/`. Commit those files.

Portal JS/CSS are plain files served from `/assets/sok_resdesk/…`, with no build step.

Without dev mode, the Docker setup needs a rebuild after code changes: `docker compose build && docker compose up -d`.

## Tests

```bash
# fast, no Frappe needed (normalisation, citations, MARC, OAI-PMH, push clients, docs checks)
pip install pytest requests && pytest      # test_core.py, test_push.py, test_docs.py, unit_folder.py

# integration, inside a site: catalogue and access (test_integration.py); pushing, pause and
# resume, Pause All, quiet hours, the checklist, portable folders (test_operations.py); the
# Server page: the updater helper's protocol, tasks and permissions, updates, alerts, backups (test_server.py)
bench --site resdesk.localhost set-config allow_tests true
bench --site resdesk.localhost run-tests --app sok_resdesk
#   Docker: docker compose exec backend bench --site resdesk.localhost run-tests --app sok_resdesk

# lint and formatting
ruff check sok_resdesk scripts
ruff format sok_resdesk scripts          # CI checks this with --check
```

CI (`.github/workflows/ci.yml`) runs lint and unit tests, then a **real Docker install using
`install.sh`**, the integration tests, a check that the workers run at low priority, a 3-book
live ingest, endpoint smoke tests, and a move (export, then import the archive back). If the
installer breaks for librarians, CI breaks too.

## Conventions

- Python formatted with `ruff format` (tabs, Frappe style); config in `pyproject.toml`.
- Keep protocol and format logic in `core/` with unit tests; keep Frappe glue thin.
- Public endpoints: `allow_guest=True`, published records only, rate-limited.
- No new Python dependencies without a good reason (the app currently needs none beyond Frappe).
- Every user-visible change: update `docs/` and `CHANGELOG.md` ([how](#keeping-the-docs-current)).
- Data changes between versions go in a patch (`patches/vX_Y/…`, added to `patches.txt`), so
  `./upgrade.sh` applies them. If a release needs the search index rebuilt, put
  `NEEDS-REINDEX` in the commit message and `upgrade.sh` tells the admin.

## Adding a new source

1. **Client** in `core/<source>.py`: list identifiers for a query, fetch metadata, fetch page
   texts as `[{leaf, label, text}]`.
2. **Normaliser** returning the same dict shape as `normalize_ia_item` (with `source` set).
3. Add the source to the `source` options of RD Item and RD Ingest Profile, plus any
   source-specific profile fields.
4. Branch on `profile.source` in `ingest.run_ingest`/`_ingest_one`.
5. Unit tests with recorded fixtures (no network in `test_core.py` / `unit_*.py`).

The OAI-PMH repository source (0.39) is a worked example: `core/harvest.py` (client and
normaliser), `repository.py` (`plan` for listing a run's records, `ingest_one` for one record in
a batch, `source_pages` for the text when the cache lacks it), the `is_repository` branches in
`ingest.py`, and `tests/unit_harvest.py` / `tests/test_repository.py` with recorded answers.

Good next candidates: Wikisource, Digital Library of India mirrors, and local uploads (PDF +
OCR).

## Keeping the docs current

The documentation is part of the product: the same `docs/*.md` files are the Help inside the
app (portal and Desk), and the pictures in them are real screens. Four things keep them true:

1. **Write the docs with the change.** Anything a reader, librarian or admin will notice goes into
   `docs/` and `CHANGELOG.md` in the same commit. Reader-facing pages are `reader-guide.md`,
   `searching.md` and `citations.md`; which pages the portal and Desk show is set in
   `sok_resdesk/core/helpdocs.py` (`PAGES`).
2. **Checks that fail when something is missing** (`sok_resdesk/tests/test_docs.py`, run in CI):
   - every `@frappe.whitelist()` function is in `docs/api.md`;
   - every DocType is in the data model in `docs/architecture.md`;
   - every Settings field has a description, and every `./resdesk.sh` command is documented;
   - every link, heading anchor and picture in the docs exists;
   - every doc is a help page and listed in `docs/README.md`;
   - every screen's **Help** button (`help.py` `SCREEN_HELP`) opens a real section, and every
     DocType has one;
   - every field a form tour (`guide.py` `TOURS`) points at still exists;
   - the pictures the docs use are exactly those `scripts/screenshots.py` takes;
   - the top `CHANGELOG.md` entry is the current version.
3. **Generated reference.** The Settings table and the command reference in `docs/operations.md`
   are made from `rd_settings.json`, `commands.py` and `resdesk.sh`. After changing those, run
   `./resdesk.sh docs` (the check fails until you do).
4. **Fresh pictures.** `./resdesk.sh screenshots` retakes every picture from a running site
   (with `pip install playwright pillow && python3 -m playwright install chromium`, or with
   nothing installed on a machine with Docker: it uses Playwright's image). Use a site
   with some books, a collection and a profile, and `--query` for a search that finds books.
   Check `git diff --stat sok_resdesk/public/images/guide`, look at the changed pictures, commit.

The in-app help, tours and checklist:

| What | Where |
|---|---|
| Help pages (portal `/library/help`, Desk `/app/resdesk-help`) | `help.py`, `core/helpdocs.py`, `www/library/help.*`, `resdesk/page/resdesk_help/` |
| **Help** / **Take the tour** buttons on forms | `public/js/desk_help.js`, `help.py` `SCREEN_HELP` |
| Form tours | `guide.py` `TOURS` (Frappe Form Tours, written on every migrate) |
| When start-up migrates | `core/schema.py`: the files whose change needs a migrate. Code that `after_migrate` runs goes in `AFTER_MIGRATE_FILES` |
| Getting-started checklist | `guide.py` `STEPS`, drawn by `desk_help.js` in the workspace block *Research Desk Checklist* |
| Reader tips on the portal | `templates/includes/rd_tips.html`, `public/js/tips.js` |

## Releasing

A release that needs a newer Frappe than earlier ones raises `__frappe_min__` in
`sok_resdesk/__init__.py`. `upgrade.sh` (and so the Server page) then updates Frappe together with the
app whenever the installed Frappe is older, even with `--no-frappe`, and the Server page's upgrade
box says so.


1. Write the `CHANGELOG.md` entry (`## X.Y.Z (date): what it brings`).
2. `scripts/release.sh X.Y.Z` sets `__version__`, refreshes the generated docs, runs the doc and
   unit checks, commits and tags. It stops if the changelog has no entry for that version.
3. `scripts/publish.sh` (or `scripts/publish.sh FILE.bundle` for a release made elsewhere)
   moves GitHub's **`main`** to the new release tag and pushes the tags. Do this, not only
   `git push --tags`: a fresh `git clone` gets whatever `main` is, so `main` must always be
   the newest release. It works whatever the folder has checked out (after `./upgrade.sh` it's
   a release tag, not a branch, so `git push origin main` would push an old `main`), only ever
   moves `main` forward, and `--check` shows what it would do. Installs pick it up with
   `./upgrade.sh` (latest tag), and the
   `docker-image.yml` workflow publishes `ghcr.io/servantsofknowledge/researchdesk:X.Y.Z` and
   `:latest` for amd64 and arm64.

If a version reaches `main` without its tag (a merge on GitHub, a push that couldn't carry tags),
the `release.yml` workflow tags it: when CI passes on `main` and `__version__` has no `v*` tag (a version whose tests fail is never released; if CI failed for a reason outside the code, such as archive.org being down during its live ingest, **Actions → Release → Run workflow** releases it by hand)
it creates the tag and a GitHub release (notes from the changelog entry) and starts the image
build. **Actions → Release → Run workflow** does the same by hand. Installs only see releases
by their tag, so an untagged version is invisible to the Server page and `./upgrade.sh`.

## Signed commits (Verified on GitHub)

GitHub shows a commit as **Verified** only if it is signed with a key registered on the author's
account, with an email that account has verified. `scripts/setup-signing.sh you@example.org` sets
that up on the machine where you commit: it makes (or reuses) an SSH signing key, points git at it
and prints the public key to add on GitHub under Settings → SSH and GPG keys → *Signing Key*. Only
new commits are signed; do not rewrite pushed history to sign old ones (it would change the hashes
the release tags point at).
