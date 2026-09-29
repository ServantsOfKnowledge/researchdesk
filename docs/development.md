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
│   └── dev-setup.sh        bench setup for developers
├── docs/                   this documentation
├── .github/workflows/      CI (lint, unit, Docker install + integration) and image publishing
└── sok_resdesk/            the Frappe app
    ├── hooks.py            routes, doc events, scheduler, install hooks
    ├── core/               pure Python, no Frappe:  ia.py  folder.py  normalize.py  citations.py  marc.py  oai.py
    ├── catalogue.py        settings, upsert RD Item, record <-> dict
    ├── ingest.py           ingest jobs, scheduler, whitelisted actions
    ├── local_source.py     IA-style item folders on disk / NAS / web server
    ├── search.py           Meilisearch adapter, indexing, search
    ├── api.py              public API
    ├── oai.py              OAI-PMH endpoint (Frappe store for core/oai.py)
    ├── commands.py         `bench … resdesk` CLI
    ├── setup.py            roles, defaults, sample profiles, setup wizard, branding
    ├── native_wsgi.py      gunicorn entry point for native installs (static files, default site)
    ├── patches/            data migrations between versions (listed in patches.txt)
    ├── resdesk/workspace/  the Research Desk workspace (shipped as a file so migrate keeps it)
    ├── resdesk/doctype/    DocTypes (JSON + controllers + form scripts)
    ├── www/library/        portal pages (index = search, item = book page)
    ├── public/             css/resdesk.css, js/library.js, js/item.js, js/basket.js
    └── tests/              test_core.py + unit_folder.py (pytest), test_integration.py (Frappe)
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
# fast, no Frappe needed (normalisation, citations, MARC, OAI-PMH protocol)
pip install pytest requests && pytest      # test_core.py + unit_folder.py

# integration, inside a site
bench --site resdesk.localhost set-config allow_tests true
bench --site resdesk.localhost run-tests --app sok_resdesk
#   Docker: docker compose exec backend bench --site resdesk.localhost run-tests --app sok_resdesk

# lint
ruff check sok_resdesk
```

CI (`.github/workflows/ci.yml`) runs lint and unit tests, then a **real Docker install using
`install.sh`**, the integration tests, a 3-book live ingest and endpoint smoke tests. If the
installer breaks for librarians, CI breaks too.

## Conventions

- Python formatted with tabs (Frappe style); `ruff` config in `pyproject.toml`.
- Keep protocol and format logic in `core/` with unit tests; keep Frappe glue thin.
- Public endpoints: `allow_guest=True`, published records only, rate-limited.
- No new Python dependencies without a good reason (the app currently needs none beyond Frappe).
- Every user-visible change: update `docs/` and `CHANGELOG.md`.
- Data changes between versions go in a patch (`patches/vX_Y/…`, added to `patches.txt`), so
  `./upgrade.sh` applies them. If a release needs the search index rebuilt, put
  `NEEDS-REINDEX` in the commit message and `upgrade.sh` tells the admin.

## Releasing

1. Bump `__version__` in `sok_resdesk/__init__.py`; add a `CHANGELOG.md` entry.
2. Commit, tag and push: `git tag v0.4.1 && git push origin main --tags`.
3. Installs pick it up with `./upgrade.sh` (latest tag). The Docker image workflow publishes
   `ghcr.io/servantsofknowledge/researchdesk:<tag>` for prebuilt-image installs.

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

## Releasing

1. Update `CHANGELOG.md` and `__version__` in `sok_resdesk/__init__.py`.
2. Tag `vX.Y.Z` and push. The `docker-image.yml` workflow publishes
   `ghcr.io/servantsofknowledge/researchdesk:X.Y.Z` and `:latest` for amd64 and arm64.
