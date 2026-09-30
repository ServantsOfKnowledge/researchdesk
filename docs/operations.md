# Operations

All commands below run from the Research Desk folder. `./resdesk.sh help` lists them.

## Start, stop, status

```bash
./resdesk.sh start | stop | restart
./resdesk.sh status          # containers + catalogue counts + search health
./resdesk.sh logs            # backend log; or: logs queue | create-site | meilisearch
```

Docker Desktop's *restart policy* brings Research Desk back after a reboot as long as Docker
itself starts.

## Backups

```bash
./resdesk.sh backup
```

This writes a database dump plus uploaded files into `./site-backups/`. Copy that folder somewhere
safe (Nextcloud, Synology, an external disk). The **search index is not backed up**, because
it can always be rebuilt from the catalogue:

```bash
./resdesk.sh reindex --background   # all workers; page text comes from the local cache
./resdesk.sh reindex --no-pages     # books only, fast
./resdesk.sh reindex --reset --background   # drop and rebuild the page index (some upgrades need this)
```

To restore (onto the same or a fresh install):

```bash
./resdesk.sh restore site-backups/<date>-<site>-database.sql.gz
```

It asks for confirmation, restores the database, migrates, and rebuilds the search index.

## Ingest workers

```bash
./resdesk.sh workers 4      # run four ingest workers (saved in .env as QUEUE_WORKERS)
./resdesk.sh progress       # watch the latest ingest run
```

Restarting workers (`./resdesk.sh restart`, `update`, a reboot) stops batches that were in
progress. The run is marked *Interrupted* within a couple of hours. Run the profile again and
already-ingested books are skipped.

## Background jobs: see and stop what is running

Desk → Research Desk → **Background Jobs** (`/app/resdesk-jobs`) shows everything Research Desk
is doing in the background and refreshes every 5 seconds:

| Section | Shows | Controls |
|---|---|---|
| Summary | active runs, running and waiting jobs, workers, search-engine tasks, schedules on/paused | **Stop Everything**, **Pause / Resume Schedules** |
| Ingest runs in progress | profile, progress bar, new/updated/failed counts, last progress | **Stop** (after the current book) · **Stop now** |
| Background jobs | every queued or running ingest batch, re-index batch, bulk visibility or collection change, export, spreadsheet import and push run | **Cancel** / **Stop** per job |
| Scheduled ingests | profiles set to Hourly, Daily or Weekly, with their last run | pause them all, or set a profile's Schedule to Manual |
| Search engine | indexing work Meilisearch still has to do (this is what uses CPU after a big ingest or an upgrade) | **Cancel pending indexing** |
| Recent runs | the last ten runs and how they ended | |

**Stop Everything** cancels every active ingest and push run and removes every queued Research Desk job. By
default it also pauses schedules. Tick *immediately* to kill running jobs as well. Books already
ingested stay in the catalogue, and running a profile again skips them. A job stopped
immediately may leave the book it was on half-indexed; *Rebuild Search Index* (Settings) fixes that.

**Pause Schedules** stops Hourly/Daily/Weekly profiles from starting new runs (also a checkbox in
Settings, *Pause Scheduled Ingests*). Manual runs still work.

From the terminal:

```bash
./resdesk.sh jobs                    # what is running and waiting
./resdesk.sh jobs --stop RUN-00042   # stop one run (add --now to kill its running batches)
./resdesk.sh jobs --stop-all --now   # stop everything at once and pause schedules
./resdesk.sh jobs --pause            # or --resume
```

Emergency brake that works on any version: `docker compose stop queue scheduler` stops all
workers and the scheduler; queued jobs wait in Redis until `./resdesk.sh start`.

## Upgrading

```bash
./upgrade.sh --check      # is there a newer release? shows what changed
./upgrade.sh              # upgrade to the latest release (asks first)
./upgrade.sh v0.4.0       # a specific release, forwards or backwards
./upgrade.sh --main       # follow the main branch instead of releases
./upgrade.sh --yes        # no questions, e.g. from cron
```

(`./resdesk.sh update` does the same.) Each upgrade:

1. **backs up** the database and files into `site-backups/` (skip with `--no-backup`),
2. **fetches** the new Research Desk code from GitHub,
3. **updates Frappe** to the newest patch release of v16. Docker rebuilds the image; native
   updates the bench (skip with `--no-frappe`),
4. runs **database migrations** and re-applies the search-index settings,
5. **restarts** and runs a **health check** (portal and search engine).

The portal is offline for a few minutes. Everything is written to `logs/upgrade-<date>.log`. If
a step fails, the script stops and prints the two commands that put you back where you were:
checking out the previous version, and restoring the backup it just made.

Local code changes block an upgrade (so nothing is overwritten). Commit or `git stash` them
first. Releases that change the search index say so at the end. Then run
`./resdesk.sh reindex --reset --background`.

**Automatic upgrades:** add a weekly cron job, for example Sunday 3 a.m.:

```
0 3 * * 0  cd /path/to/researchdesk && ./upgrade.sh --yes >> logs/cron-upgrade.log 2>&1
```

## Changing settings

Desk → Research Desk → **Settings**:

- Portal title and tagline, **Public Base URL**, OAI repository identifier, admin email
- **Logo & Branding**: upload a **Logo** (shown on the home page, in the top bar of every
  portal page and in the Desk), an optional browser-tab icon and an optional home-page
  background image. Changes apply as soon as you save.
- Meilisearch URL and key, index prefix, page-level indexing on/off, max characters per page
- Internet Archive contact and request delay

**Test Search Engine** checks the connection and (re)applies index settings. **Rebuild
Search Index** queues a full rebuild.

## Users and roles

| Role | Can |
|---|---|
| ResDesk Manager | everything in Research Desk: settings, profiles, ingests, catalogue |
| ResDesk Cataloguer | edit catalogue records, re-index items, read runs, change who can see books |
| ResDesk Reader | log in on the portal and read members-only books; no Desk access |
| (visitors) | search, read and cite what the site allows without a login |

Add staff in Desk → *User* → give them one of these roles. They land on the Research Desk
workspace after login. Readers can also sign up themselves, or be added with
`./resdesk.sh add-reader EMAIL`: see [Who can see what](access.md#reader-accounts).

## Troubleshooting

| Symptom | Fix |
|---|---|
| `install.sh` says Docker isn't running | start Docker Desktop and wait for "Engine running" |
| Build fails with network errors | check your internet connection and re-run `./install.sh`; it resumes |
| Port 8080 already in use | set `HTTP_PORT=8090` in `.env`, re-run `./install.sh` |
| Portal shows "Search is temporarily unavailable" | `./resdesk.sh logs meilisearch`; then Desk → Settings → **Test Search Engine** |
| An ingest run stays *Queued* | the worker isn't running: `./resdesk.sh restart`, check `./resdesk.sh logs queue` |
| A run is *Interrupted* | workers restarted mid-run: run the profile again (existing books are skipped) |
| Page search slow or disk full on a big collection | see [Scaling](scaling.md) for sizing |
| Some items *FAIL* in a run log | usually a temporary IA error: re-run the profile (existing items are skipped) |
| Book has no "search inside" | IA has no page-level OCR for it yet, or it's access-restricted |
| Citations show `localhost` links on a server | set `BASE_URL` (see [Installation](installation.md#docker-on-a-server-with-a-domain-name-and-https)) |
| Forgot the admin password | `./resdesk.sh password` |
| Desk looks broken after an update | `./resdesk.sh bench clear-cache`, then hard-refresh the browser |
| `upgrade.sh` stops at the backup | it prints why (usually Docker, or the database not starting). With a recent backup already in `site-backups/`, run `./upgrade.sh --no-backup` |
| Containers won't start after an upgrade | `docker compose ps -a` and `docker compose logs --tail 50 create-site backend`. Common causes: Docker Desktop out of disk (*Settings → Resources*, or `docker system prune`), `LIBRARY_DIR` pointing at a folder Docker Desktop can't share (*Settings → Resources → File sharing*), or another program using `HTTP_PORT` |
| `upgrade.sh` stopped half way | read the log it names (`logs/upgrade-*.log`); run the rollback commands it printed, or fix the cause and run `./upgrade.sh` again (it is safe to repeat) |
| `upgrade.sh` says there are local code changes | `git stash`, upgrade, then `git stash pop` (or discard them) |
| Native: `./resdesk.sh start` returns but the portal doesn't answer | `./resdesk.sh logs` (bench and web logs are in the bench folder, `~/researchdesk-bench/logs`) |
| Native: port 8080, 7700 or a Redis port is taken | another service is using it; stop it, or change `HTTP_PORT`/`MEILI_PORT` in `.env` and run `./install.sh --native` again |
| Native: MariaDB refuses the root password | re-run `./install.sh --native`; it resets the MariaDB root password to the one in `.env` |
| Native: "Research Desk" workspace missing from the Desk | `./resdesk.sh migrate` |

Errors from background jobs also appear in Desk → *Error Log*.
