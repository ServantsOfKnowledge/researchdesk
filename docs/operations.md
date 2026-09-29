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
./resdesk.sh reindex             # books + page text (re-downloads page text from IA)
./resdesk.sh reindex --no-pages  # books only, fast
```

To restore (onto the same or a fresh install):

```bash
./resdesk.sh restore site-backups/<date>-<site>-database.sql.gz
```

It asks for confirmation, restores the database, migrates, and rebuilds the search index.

## Updating

```bash
./resdesk.sh update
```

This pulls the latest code, rebuilds (or pulls) the image, restarts, and runs database migrations
automatically through the `create-site` container.

## Changing settings

Desk → Research Desk → **Settings**:

- Portal title and tagline, **Public Base URL**, OAI repository identifier, admin email
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
| Some items *FAIL* in a run log | usually a temporary IA error: re-run the profile (existing items are skipped) |
| Book has no "search inside" | IA has no page-level OCR for it yet, or it's access-restricted |
| Citations show `localhost` links on a server | set `BASE_URL` (see [Installation](installation.md#docker-on-a-server-with-a-domain-name-and-https)) |
| Forgot the admin password | `./resdesk.sh password` |
| Desk looks broken after an update | `./resdesk.sh bench clear-cache`, then hard-refresh the browser |

Errors from background jobs also appear in Desk → *Error Log*.
