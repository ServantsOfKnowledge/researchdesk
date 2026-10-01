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
| `scheduler` | runs scheduled ingest profiles, the daily sync with archive.org, nightly backups, quiet hours and alerts |
| `db` | MariaDB 11.8: the catalogue |
| `redis-cache`, `redis-queue` | cache and job queue |
| `meilisearch` | the search engine: book records and the text of every page |
| `configurator`, `create-site` | one-off setup steps that run and exit |
| `monitor` (optional) | read-only view of container CPU and memory for Background Jobs (`./resdesk.sh resources monitor on`) |
| `updater` (optional) | the updater helper: upgrades, restarts and server backups started from the Server page (`./resdesk.sh updater on`, [Server](server.md#the-updater-helper)) |

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
./install.sh --domain library.example.org   # a server with a DNS name: HTTPS from Let's Encrypt
```

The installer writes `.env` with random passwords (keep it private). You can re-run
`./install.sh` safely at any time. It keeps `.env` and your data, rebuilds if needed and
migrates the site if the code needs it ([Database migrations](operations.md#database-migrations)).

Settings you can change in `.env` before (re)running the installer:

| Variable | Default | Meaning |
|---|---|---|
| `PORTAL_TITLE` | SoK Research Desk | shown on the portal |
| `HTTP_PORT` | 8080 | port on your computer |
| `BASE_URL` | http://localhost:8080 | public address. Used in citations, OAI-PMH, MARC 856 and realtime. Set with `./install.sh --domain` or `./resdesk.sh url` ([Changing the portal's address](#changing-the-portals-address)) |
| `HTTPS`, `HTTPS_DOMAIN` | 0 | set by `./resdesk.sh https on DOMAIN`: nginx + Let's Encrypt on ports 80 and 443 |
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

1. Point a DNS name (e.g. `library.example.org`) at the server: an **A** record with its public
   address (and **AAAA** for IPv6). Open ports **80** and **443** to the internet (firewall,
   cloud security group, or port forwarding on your router).
2. Install with the name:

   ```bash
   ./install.sh --domain library.example.org --email you@example.org
   ```

   Or run `./install.sh` and give the name when it asks for the *web address*. The installer
   sets the portal's address to `https://library.example.org` and, after the site is up, gets
   a free certificate from Let's Encrypt ([below](#https-with-lets-encrypt)). Say no to the
   certificate (or use `--no-https`) if HTTPS is handled elsewhere: Cloudflare, Caddy, or a
   proxy of your own in front of port 8080.

### HTTPS with Let's Encrypt

`./resdesk.sh https on DOMAIN` (which the installer runs for you) works one of two ways,
chosen by itself:

| | How |
|---|---|
| **Docker, nothing on ports 80/443** | two small containers: **nginx** on ports 80 and 443 in front of the portal, and **certbot**, which gets the certificate and renews it (`compose.https.yaml`) |
| **The server already runs nginx** (other sites on it), and **every native install** on Linux | a site for Research Desk in *that* nginx (`/etc/nginx/sites-available/researchdesk-DOMAIN.conf`), and the certificate from the server's certbot (`certbot --nginx`, renewed by its timer). Your other sites are not touched. nginx and certbot are installed with apt if missing; it asks for your `sudo` password |

Force one or the other with `--nginx` or `--docker-proxy`. If something other than nginx has
port 80 or 443 (Apache, Caddy…), it stops and says so: pass the name on from that server to
`http://127.0.0.1:8080` (Docker) or `:8000` (native), and set the address with
`./resdesk.sh url`.

On a native install the nginx site also carries **realtime updates** (progress bars, live
lists): Frappe's socket.io server listens on its own port, which browsers can't reach without
nginx in front. The portal's own port (8000) is then kept to the server itself.

```bash
./resdesk.sh https on library.example.org [--email you@example.org]   # turn on, or add later
./resdesk.sh https status     # the name, the containers, when the certificate expires
./resdesk.sh https renew      # renew now (it renews by itself)
./resdesk.sh https off        # back to plain HTTP on port 8080 (the certificate is kept)
```

What `https on` does with its own containers (the server's nginx: the same steps, with a site
in that nginx instead of the containers):

1. starts nginx on ports 80 and 443, and keeps the portal's own port (8080) to the server
   itself, so visitors only come in through HTTPS;
2. checks that the name reaches this server;
3. asks Let's Encrypt for a certificate (the *webroot* check on port 80);
4. switches nginx to HTTPS (HTTP redirects to it) and sets the portal's address to
   `https://DOMAIN`.

Certificates last 90 days. certbot checks twice a day and renews a month before they expire;
nginx picks up the new one within 6 hours. Let's Encrypt emails the address you give
(`--email`, or *CONTACT_EMAIL* in `.env`) if a renewal keeps failing. `--staging` uses Let's
Encrypt's test service (certificates browsers don't trust) while you try things out, without
running into its limits.

If it fails, the message says why. Usually the DNS name doesn't point at the server yet, or
port 80 is closed: fix it and run `./resdesk.sh https on DOMAIN` again. The portal keeps
answering on `http://DOMAIN` meanwhile. If another web server already uses port 80 or 443 on
the machine, stop it, or leave HTTPS to it (proxy to `http://127.0.0.1:8080` with `Host`,
`X-Forwarded-For`, `X-Forwarded-Proto` and the websocket upgrade headers for `/socket.io`).

On **macOS** (native), put Caddy (`reverse_proxy 127.0.0.1:8000`, plus `/socket.io*` to
`127.0.0.1:9000`) or nginx in front by hand. On **Coolify**, Coolify does HTTPS itself.

### Changing the portal's address

The address goes into citations, OAI-PMH, MARC 856 links, emails and the realtime connection.
Set it when installing (`--domain`, or the *web address* question), or at any time after:

```bash
./resdesk.sh url                                  # what it is now, everywhere it's kept
./resdesk.sh url https://library.example.org      # change it
./resdesk.sh url http://192.168.1.20:8080         # e.g. a machine on your own network
```

`url` sets `BASE_URL` in `.env`, the site's `host_name` and Settings → *Public Base URL* in one
go, with no restart. With HTTPS on, a new name also gets its own certificate; the old one keeps
working until the new one is in. Links people already copied (citations, OAI-PMH records
harvested elsewhere) keep the old address, so keep the old name pointing here for a while, or
redirect it.

You can also change *Public Base URL* in Settings in the Desk (or with
`./resdesk.sh configure --base-url URL`), but that changes only the links; `./resdesk.sh url`
changes all three.

### Coolify

Research Desk runs as a Docker Compose resource in Coolify, built from this repository.

1. *New Resource → Docker Compose*, from this Git repository, branch `main`, file `compose.yaml`.
2. **Environment Variables** tab (Developer view takes a whole `.env` at once):

   ```
   BASE_URL=https://library.example.org
   ADMIN_PASSWORD=...          # long random strings
   DB_ROOT_PASSWORD=...
   MEILI_MASTER_KEY=...
   QUEUE_WORKERS=1             # required: see below
   WORKERS_PER_CONTAINER=3     # how many ingest workers
   HTTP_PORT=18080             # any free port: Coolify's proxy doesn't use it
   ```

   Coolify gives every container a fixed name, so it can't run several copies of the worker
   container (Docker stops with *can't set container_name and queue as container name must be
   unique*). `QUEUE_WORKERS=1` runs one worker container and `WORKERS_PER_CONTAINER` the
   workers inside it. `LIBRARY_DIR`, if you ingest from folders, must be an absolute path on
   the server.
3. **Configuration → Services → frontend → Domains**: `https://library.example.org:8080` (the
   `:8080` is the port inside the container; visitors use the plain address, and Coolify gets
   the certificate).
4. **Deploy.** The first build takes 10 minutes or more (it builds Frappe). The `create-site`
   container creates the site, and on later deploys migrates when the new code needs it.

Changed a variable? **Redeploy** (a restart keeps the old values). To upgrade, redeploy the
latest code. The updater helper and the Background Jobs container monitor don't work under
Coolify (they need a Research Desk folder and Compose project of their own), so the Server
page's Upgrade and Restart buttons stay off; health, backups, logs and alerts work.

**Moving an existing install to Coolify**: make an export on the old install
(`./resdesk.sh export`), copy it to the Coolify server, clone this repository there and load it
into the containers Coolify made:

```bash
git clone https://github.com/ServantsOfKnowledge/researchdesk.git && cd researchdesk
./resdesk.sh coolify list                                # finds Research Desk's containers
./resdesk.sh coolify import ~/resdesk-move-20261001-0930.tar.gz
```

It restores the export into the Coolify site, sets the address from `BASE_URL` and starts
rebuilding search. `./resdesk.sh coolify bench ...` runs any bench command on that site (e.g.
`bench set-admin-password NEW`), and `./resdesk.sh coolify export` makes an export from it. With
more than one Research Desk on the server, add `--project ID` (from `list`). See
[Moving](moving.md).

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
- After changing a DocType's JSON by hand, run `./resdesk.sh migrate` (a restart also migrates,
  because the JSON changed).

`./resdesk.sh dev off` rebuilds the image with the current code and goes back to normal mode.
Dev mode uses a development web server with a debugger, so **don't use it on a public server**.

## Native install (no Docker)

```bash
./install.sh --native
```

For computers where Docker isn't wanted or available. Supported: **macOS** with
[Homebrew](https://brew.sh), and **Ubuntu 22.04+ / Debian 12+** (needs `sudo`). The installer:

1. installs MariaDB, Redis and Meilisearch (Homebrew or apt; Meilisearch from its GitHub release on Linux),
2. installs Python 3.14 with [uv](https://docs.astral.sh/uv/), Node 24 with nvm, and `frappe-bench`,
3. configures MariaDB for Frappe (utf8mb4) and sets its root password from `.env`,
4. creates a Frappe v16 bench in `~/researchdesk-bench` (change with `BENCH_DIR` in `.env`),
   **linked to this folder**, so the code you edit here is the code that runs,
5. creates the site, installs Research Desk and finishes Frappe's setup wizard,
6. records `INSTALL_MODE=native` in `.env` and starts everything.

Everything then runs from the bench's `Procfile`: gunicorn (the web server, on `HTTP_PORT`,
default 8000), background workers, the scheduler, Redis and Meilisearch. The same
`./resdesk.sh` commands work (`start`, `stop`, `status`, `ingest`, `backup`, `workers`, …) and so
does `./upgrade.sh`. Your book folder (`LIBRARY_DIR`) is read directly; ingest profiles still call
it `/library-source`.

| | Docker | Native |
|---|---|---|
| Isolation | everything in containers | installs system packages |
| Remove cleanly | `./resdesk.sh uninstall` | `./resdesk.sh uninstall` (MariaDB/Redis/Meilisearch stay installed) |
| Start on boot | automatic (Docker restart policy) | run `./resdesk.sh start` at login, or see below |
| Best for | most people, servers | machines without Docker, developers who prefer bench |

**Starting on boot (native):** on Linux, add `@reboot cd /path/to/researchdesk && ./resdesk.sh start`
with `crontab -e`. On macOS, add `resdesk.sh start` to *System Settings → General → Login Items*
through a small Automator app or a LaunchAgent. For a public Linux server, prefer Docker, or Frappe's
own `sudo bench setup production` (nginx + supervisor).

`./resdesk.sh dev on` switches the native web server to Frappe's auto-reloading development
server (with `developer_mode`); `dev off` goes back to gunicorn. Never leave dev mode on for a
machine others can reach: it includes an interactive debugger.

> Tested on a clean Ubuntu 24.04. The macOS path uses the same steps through Homebrew. If a
> step fails, the installer stops with the reason; fix it and run `./install.sh --native` again.
> Finished steps are skipped.

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

## Upgrading

```bash
./upgrade.sh --check      # is there a newer release? shows what changed
./upgrade.sh              # latest release
./upgrade.sh v0.4.0       # a specific release (also how you roll back)
./upgrade.sh --main       # newest code on the main branch
```

Or from the Desk (Research Desk → Server) with the updater helper on. See
[Operations → Upgrading](operations.md#upgrading) and [Server](server.md#upgrading-from-the-desk).

## Uninstall

```bash
./resdesk.sh uninstall     # removes containers and ALL data (asks first)
```
