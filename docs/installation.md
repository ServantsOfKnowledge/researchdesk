# Installation

There are three ways to run Research Desk:

| Setup | Use it for | How |
|---|---|---|
| **Docker, one command** | Laptops, a library PC, trying it out | `./install.sh` |
| **Docker on a server** | A public portal with a domain name | `./install.sh` + a reverse proxy (below) |
| **bench (native)** | Developing Research Desk itself | `scripts/dev-setup.sh` |

## What gets installed

`compose.yaml` runs these containers:

| Service | What it does |
|---|---|
| `frontend` | nginx, the only service with a port open (`HTTP_PORT`, default 8080) |
| `backend` | Frappe web application (gunicorn) |
| `websocket` | real-time updates in the Desk |
| `queue` | background workers (`QUEUE_WORKERS`, default 2): run ingest batches and re-indexing in parallel |
| `scheduler` | runs scheduled (Daily/Weekly) ingest profiles |
| `db` | MariaDB 11.8: the catalogue |
| `redis-cache`, `redis-queue` | cache and job queue |
| `meilisearch` | the search engine: book records and the text of every page |
| `configurator`, `create-site` | one-off setup steps that run and exit |

Data lives in Docker volumes (`db-data`, `meili-data`, `sites`, …), so stopping or updating
containers never deletes it. Only `./resdesk.sh uninstall` removes volumes.

## Requirements

| | Minimum | Comfortable for 100k books |
|---|---|---|
| Memory | 4 GB for Docker | 8 to 16 GB |
| Disk | 10 GB | 60 to 120 GB (page text index) |
| CPU | 2 cores | 4+ cores |

Apple Silicon (M1/M2/M3/M4) and Intel/AMD both work: the Frappe base images are
multi-architecture.

## Docker: one command

```bash
./install.sh            # interactive
./install.sh --yes      # accept all defaults (for scripts/CI)
./install.sh --sample   # also ingest 20 sample books
```

The installer writes `.env` with random passwords (keep it private). You can re-run
`./install.sh` safely at any time. It keeps `.env` and your data, rebuilds if needed and
migrates the site.

Settings you can change in `.env` before (re)running the installer:

| Variable | Default | Meaning |
|---|---|---|
| `PORTAL_TITLE` | SoK Research Desk | shown on the portal |
| `HTTP_PORT` | 8080 | port on your computer |
| `BASE_URL` | http://localhost:8080 | public address. Used in citations, OAI-PMH, MARC 856 and realtime. **Change this on a server.** |
| `CONTACT_EMAIL` | (empty) | sent to archive.org in the User-Agent; also the OAI-PMH admin email |
| `TIMEZONE` / `COUNTRY` / `CURRENCY` | Asia/Kolkata / India / INR | Frappe system defaults |
| `GUNICORN_WORKERS` | 2 | web workers; raise on bigger servers |
| `QUEUE_WORKERS` | 2 | parallel ingest workers; 4 to 6 for large collections (see [Scaling](scaling.md)) |
| `DEV_MODE` | 0 | `1` runs the code from this folder live (see below) |
| `RESDESK_IMAGE`, `RESDESK_TAG` | (build locally) | use a prebuilt image instead of building |

### Using a prebuilt image (skip the 15-minute build)

The GitHub Actions workflow `docker-image.yml` publishes multi-arch images to GitHub
Container Registry. Add to `.env`:

```
RESDESK_IMAGE=ghcr.io/servantsofknowledge/researchdesk
RESDESK_TAG=latest
```

then run `./install.sh`.

## Docker on a server with a domain name and HTTPS

1. Point a DNS name (e.g. `library.example.org`) at the server.
2. In `.env`, set `BASE_URL=https://library.example.org` and keep `HTTP_PORT=8080`.
3. Run `./install.sh`.
4. Put a TLS-terminating reverse proxy in front of port 8080. With **Caddy**:

   ```
   library.example.org {
       reverse_proxy 127.0.0.1:8080
   }
   ```

   With **nginx**, proxy to `http://127.0.0.1:8080` and pass `Host`, `X-Forwarded-For`
   and `X-Forwarded-Proto`. Include the websocket upgrade headers for `/socket.io`.

If you changed `BASE_URL` after the first install, apply it with:

```bash
./resdesk.sh bench set-config host_name https://library.example.org
./resdesk.sh configure --base-url https://library.example.org
```

### Coolify

Research Desk is a standard Docker Compose app:

1. In Coolify: *New Resource → Docker Compose*, from this Git repository (`compose.yaml`).
2. Add the variables from `.env.example` as environment variables. Generate
   `ADMIN_PASSWORD`, `DB_ROOT_PASSWORD` and `MEILI_MASTER_KEY` with long random strings.
3. Assign your domain to the **frontend** service on port 8080, and set `BASE_URL` to it.
4. Deploy. The `create-site` container creates the site on the first deploy and migrates on
   later ones.

## Developer mode (Docker, code from this folder)

The easiest way to keep developing: no Python, MariaDB or Node needed on your computer.

```bash
./resdesk.sh dev on     # once; remembered in .env as DEV_MODE=1
```

- Python files, templates, JS and CSS are read **live from this folder**. The web server
  reloads by itself when you save a `.py` file.
- Background workers need `./resdesk.sh restart` to pick up Python changes.
- `developer_mode` is on, so DocTypes you edit in the Desk are written back into
  `sok_resdesk/resdesk/doctype/` for you to commit.
- After changing a DocType's JSON by hand, run `./resdesk.sh migrate`.

`./resdesk.sh dev off` rebuilds the image with the current code and goes back to normal mode.
Dev mode uses a development web server with a debugger, so **don't use it on a public server**.

## Developer setup (bench)

For working on the code with live reload. You need Python 3.14, Node 24 with yarn,
MariaDB 11.x, Redis, `pip install frappe-bench`, and Meilisearch
(`brew install meilisearch`, or `docker run -p 7700:7700 getmeili/meilisearch:v1.54`).

```bash
scripts/dev-setup.sh ~/frappe-bench resdesk.localhost
cd ~/frappe-bench && bench start
```

The script creates a bench (Frappe `version-16`), links this repository into `apps/`,
creates a site with `developer_mode`, and prints next steps. See [Development](development.md).

## Uninstall

```bash
./resdesk.sh uninstall     # removes containers and ALL data (asks first)
```
