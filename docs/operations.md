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
| ResDesk Cataloguer | edit catalogue records, re-index items, read runs |
| (public) | search, read, cite; no login |

Add staff in Desk → *User* → give them one of these roles. They land on the Research Desk
workspace after login.

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

Errors from background jobs also appear in Desk → *Error Log*.
