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
│   ├── install-native.sh   native install: packages, Python 3.14 (uv), Node 24 (nvm), bench, site
│   ├── native-procfile.sh  Procfile for native runs (gunicorn, Meilisearch, extra workers)
│   ├── dev-setup.sh        bench setup for developers
│   ├── gen_docs.py         the generated parts of docs/ (./resdesk.sh docs)
│   ├── screenshots.py      retake the pictures in docs/ (./resdesk.sh screenshots)
│   └── release.sh          check docs + changelog, set the version, tag
├── docs/                   this documentation
├── .github/workflows/      CI (lint, unit, Docker install + integration) and image publishing
└── sok_resdesk/            the Frappe app
    ├── hooks.py            routes, doc events, scheduler, install hooks
    ├── core/               pure Python, no Frappe:  ia.py  folder.py  normalize.py  citations.py  marc.py  oai.py  access.py
    │                                           helpdocs.py (docs as help pages)  collections.py (rules, slugs)  metaio.py (export formats, spreadsheet)  push.py (IA, Koha, Wikidata, webhook clients)
    ├── catalogue.py        settings, upsert RD Item, record <-> dict
    ├── ingest.py           ingest jobs, scheduler, whitelisted actions
    ├── local_source.py     IA-style item folders on disk / NAS / web server
    ├── search.py           Meilisearch adapter, indexing, search
    ├── access.py           who can see what: members, bulk visibility, reader sign-up
    ├── curation.py         curated collections: membership, rules, counts
    ├── transfer.py         metadata exports and spreadsheet imports
    ├── outbound.py         push runs to other systems, automatic pushes
    ├── jobs.py             Background Jobs page: see, pause, resume and stop runs and queued jobs
    ├── holding.py          held jobs (Pause All / Hold) and the @hold_when_paused job decorator
    ├── help.py             in-app help pages and each screen's Help link (from docs/*.md)
    ├── guide.py            form tours and the getting-started checklist
    ├── portal.py           helpers for portal pages (collection cards, facet labels)
    ├── api.py              public API
    ├── oai.py              OAI-PMH endpoint (Frappe store for core/oai.py)
    ├── commands.py         `bench … resdesk` CLI
    ├── setup.py            roles, defaults, sample profiles, setup wizard, branding
    ├── native_wsgi.py      gunicorn entry point for native installs (static files, default site)
    ├── patches/            data migrations between versions (listed in patches.txt)
    ├── resdesk/workspace/  the Research Desk workspace (shipped as a file so migrate keeps it)
    ├── resdesk/doctype/    DocTypes (JSON + controllers + form scripts)
    ├── www/library/        portal pages (index = search, item = book page, collections, collection, help)
    ├── public/             css/resdesk.css, js/library.js, js/item.js, js/basket.js, js/tips.js,
    │                       js/desk_help.js, images/guide/ (screenshots used in docs/)
    └── tests/              test_core.py, test_push.py, test_docs.py, unit_folder.py (pytest), test_integration.py, test_operations.py (Frappe)
```

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
# resume, Pause All, quiet hours, the checklist, portable folders (test_operations.py)
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

Good next candidates: Wikisource, Digital Library of India mirrors, DSpace repositories (via
OAI-PMH, reusing `core/oai.py` concepts), and local uploads (PDF + OCR).

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
   (needs `pip install playwright pillow && python3 -m playwright install chromium`). Use a site
   with some books, a collection and a profile, and `--query` for a search that finds books.
   Check `git diff --stat sok_resdesk/public/images/guide`, look at the changed pictures, commit.

The in-app help, tours and checklist:

| What | Where |
|---|---|
| Help pages (portal `/library/help`, Desk `/app/resdesk-help`) | `help.py`, `core/helpdocs.py`, `www/library/help.*`, `resdesk/page/resdesk_help/` |
| **Help** / **Take the tour** buttons on forms | `public/js/desk_help.js`, `help.py` `SCREEN_HELP` |
| Form tours | `guide.py` `TOURS` (Frappe Form Tours, written on every migrate) |
| Getting-started checklist | `guide.py` `STEPS`, drawn by `desk_help.js` in the workspace block *Research Desk Checklist* |
| Reader tips on the portal | `templates/includes/rd_tips.html`, `public/js/tips.js` |

## Releasing

1. Write the `CHANGELOG.md` entry (`## X.Y.Z (date): what it brings`).
2. `scripts/release.sh X.Y.Z` sets `__version__`, refreshes the generated docs, runs the doc and
   unit checks, commits and tags. It stops if the changelog has no entry for that version.
3. `git push origin main --tags`. Installs pick it up with `./upgrade.sh` (latest tag), and the
   `docker-image.yml` workflow publishes `ghcr.io/servantsofknowledge/researchdesk:X.Y.Z` and
   `:latest` for amd64 and arm64.
