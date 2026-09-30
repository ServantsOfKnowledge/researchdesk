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

## Background jobs: see, pause and stop what is running

Desk → Research Desk → **Background Jobs** (`/app/resdesk-jobs`) shows everything Research Desk
is doing in the background and refreshes every 5 seconds:

| Section | Shows | Controls |
|---|---|---|
| Summary | active ingest and push runs, running, waiting and held jobs, workers, search-engine tasks, schedules on/paused | **Pause All / Resume All**, **Pause / Resume Schedules**, **Stop Everything** |
| Ingest runs in progress | profile, progress bar, new/updated/failed counts, last progress | **Pause / Resume** · **Stop** (after the current book) · **Stop now** |
| Metadata pushes in progress | target, progress, sent/unchanged/failed, dry run or not | **Pause / Resume** · **Stop** |
| Background jobs | every queued or running ingest batch, re-index batch, bulk visibility or collection change, export, spreadsheet import and push run | **Hold** (waiting jobs) · **Cancel** / **Stop** |
| Held jobs | jobs kept aside by Hold or Pause All | **Release** · **Discard** (one or all) |
| Scheduled ingests | profiles set to Hourly, Daily or Weekly, with their last run | pause them all, or set a profile's Schedule to Manual |
| Search engine | indexing work Meilisearch still has to do (this is what uses CPU after a big ingest or an upgrade) | **Cancel pending indexing** |
| Recent runs | the last ten runs and how they ended | |

### Pause: stop for now, carry on later

Pausing never throws work away.

- **Pause a run** (ingest or push; also on the run's own form): waiting batches are taken out of
  the queue and running batches stop after the book they are on. The books not yet done are kept
  on the run, which shows *Paused*. **Resume** queues exactly those books again, so nothing is
  processed twice and nothing is skipped. A paused ingest counts as running for its schedule, so
  the scheduler won't start a second one.
- **Hold a job**: takes one waiting job (a re-index batch, an export, a bulk change) out of the
  queue and keeps it under *Held jobs* until you **Release** it (or **Discard** it).
- **Pause All**: pauses every run, holds every waiting job, pauses schedules, and makes any new
  job wait too (an export or bulk change started while paused is held as soon as it reaches a
  worker). Jobs already running finish their current step, a few seconds. The page shows a
  yellow banner until you press **Resume All**, which resumes the runs, releases the held jobs
  and puts schedules back the way they were. Use it before a backup, an upgrade, or when the
  computer is needed for something else.

Held jobs and paused runs are stored in the database, so they survive restarts and upgrades.
The search engine's own indexing (Meilisearch tasks) can't be paused, only cancelled.

### Stop: give up on the work

**Stop Everything** cancels every active or paused ingest and push run, removes every queued
Research Desk job and discards held ones. By default it also pauses schedules. Tick
*immediately* to kill running jobs as well. Books already ingested stay in the catalogue, and
running a profile again skips them. A job stopped immediately may leave the book it was on
half-indexed; *Rebuild Search Index* (Settings) fixes that.

**Pause Schedules** stops Hourly/Daily/Weekly profiles from starting new runs (also a checkbox in
Settings, *Pause Scheduled Ingests*). Manual runs still work.

From the terminal:

```bash
./resdesk.sh jobs                        # what is running, waiting, paused and held
./resdesk.sh jobs --pause-run RUN-00042  # pause a run where it is (ingest or PUSH-…)
./resdesk.sh jobs --resume-run RUN-00042 # carry on
./resdesk.sh jobs --pause-all            # pause everything; --resume-all to carry on
./resdesk.sh jobs --stop RUN-00042       # stop one run (add --now to kill its running batches)
./resdesk.sh jobs --stop-all --now       # stop everything at once and pause schedules
./resdesk.sh jobs --pause                # pause schedules only; --resume to turn them back on
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

Desk → Research Desk → **Settings**. Changes apply as soon as you save. **Test Search Engine**
checks the connection and (re)applies index settings; **Rebuild Search Index** queues a full
rebuild; **Apply Access Rules** re-applies the access rules to books already in the catalogue.

Every setting:

<!-- generated:settings -->
<!-- made by scripts/gen_docs.py from the code: edit the code, then run ./resdesk.sh docs -->
**Portal**

| Setting | What it does |
|---|---|
| Portal Title | The library's name on the portal, in the browser tab, in the Desk and in citations. |
| Tagline | One line under the name on the portal home page. |
| Public Base URL | e.g. https://library.example.org. Used in citations, OAI-PMH and MARC 856 links. Leave empty to use this site's URL. |
| OAI Repository Identifier | Domain-style identifier used in OAI identifiers, e.g. library.example.org |
| Admin Email | Shown to OAI-PMH harvesters. |

**Logo & Branding**

| Setting | What it does |
|---|---|
| Logo | PNG, SVG or JPG. Shown on the portal home page, in the top bar of every portal page and in the Desk. A wide logo about 400×120 px works well. |
| Show Logo on the Home Page | Show the logo above the name on the portal home page. |
| Show Portal Name Next to the Logo in the Top Bar | Turn off when the logo already contains the library's name. |
| Browser Tab Icon (optional) | Square image (PNG/ICO, 64×64 or larger). Leave empty to use the logo. |
| Home Page Background Image (optional) | A wide photo behind the search box on the home page, e.g. a manuscript or library shelf. |

**Search Engine (Meilisearch)**

| Setting | What it does |
|---|---|
| Meilisearch URL | Where the search engine runs. The installer sets this; change it only if you move Meilisearch. |
| Meilisearch API Key | The key the installer created for the search engine. Keep it secret. |
| Index Prefix | Lets several sites share one Meilisearch. |
| Index Page-Level Full Text | Enables deep search inside books. Uses more disk. |
| Max Characters per Page | Longer pages are cut to this length in the index, which keeps it smaller. |
| Search Status | Filled in by Test Search Engine: whether it connected and how many books and pages the index holds. |

**Internet Archive**

| Setting | What it does |
|---|---|
| Contact (sent in User-Agent) | An email or URL so IA can reach you if your harvesting causes problems. |
| Delay Between Requests (seconds) | Pause between requests to archive.org. Raise it if archive.org asks you to slow down. |
| Books per Background Batch | Large ingests are split into batches that run in parallel, one per queue worker. Add workers with QUEUE_WORKERS in .env. |
| Keep a Local Copy of Page Text | Stores compressed OCR text on disk (about 20–60 KB per book) so re-indexing never needs to download from archive.org again. |
| Pause Scheduled Ingests | Stops Hourly/Daily/Weekly profiles from starting new runs. Manual runs still work. Also on the Background Jobs page. |
| Pause All Background Work | Set from the Background Jobs page: runs are paused and queued jobs held until you press Resume All there. |

**Access & Sign-up**

| Setting | What it does |
|---|---|
| Visitors Who Are Not Logged In | Each item's setting: follow each book's “Who can see it”. Records only: visitors can search the catalogue and cite, but reading and search inside the text need a login. Login required: the whole portal is for logged-in readers (an internal library). Choices: *Each item's setting*, *Records only*, *Login required*. |
| Default for New Books | Used when neither the ingest profile nor a rule below decides. Choices: *Public*, *Login to read*, *Login to find*. |
| Reader Accounts | Admins add readers: no sign-up page; add people in User with the ResDesk Reader role, or ./resdesk.sh add-reader. Anyone can sign up: every account can read. Sign up, admin approves: new accounts wait in Reader Requests. Choices: *Admins add readers*, *Anyone can sign up*, *Sign up, admin approves*. |
| OAI-PMH Shares | What harvesters such as Koha receive. “All published records” suits a library system on an internal network. Choices: *Records guests can find*, *All published records*, *Off*. |

**Access Rules**

| Setting | What it does |
|---|---|
| Rules | Give books a visibility by collection, subject, language, creator, source or profile. Press Apply Access Rules to use them on books already in the catalogue. |
<!-- /generated:settings -->

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

## Command reference

<!-- generated:commands -->
<!-- made by scripts/gen_docs.py from the code: edit the code, then run ./resdesk.sh docs -->
`./resdesk.sh help` prints:

```text
SoK Research Desk — everyday commands

  ./resdesk.sh start | stop | restart | status
  ./resdesk.sh logs [name]              follow logs (Docker: backend, queue…; native: bench-start, worker, web…)
  ./resdesk.sh url                      print the portal address

Choosing and ingesting books
  ./resdesk.sh count  --collection ServantsOfKnowledge --filter "language:kan"
  ./resdesk.sh ingest --collection ServantsOfKnowledge --filter "language:kan" --limit 100
  ./resdesk.sh ingest --query 'creator:(Kuvempu) AND mediatype:texts' --limit 50 --name "Kuvempu"
  ./resdesk.sh ingest --ids "id1,id2,id3"
  ./resdesk.sh ingest --folder /library-source            (IA-style item folders in LIBRARY_DIR)
  ./resdesk.sh ingest --server https://books.example.org/items/
  ./resdesk.sh ingest --profile "SoK Kannada sample"
  ./resdesk.sh ingest --folder /library-source/staff --visibility members   (who can see the new books)
      options: --no-fulltext  --update  --limit 0 (= everything)  --background

Who can see what (details: docs/access.md)
  ./resdesk.sh access                   who can see what (settings + counts)
  ./resdesk.sh access login-to-read --collection X
        (visibility: public | login-to-read | members; --profile, --language, --ids, --all)
  ./resdesk.sh access --guests "Login required"      (or "Records only", "Each item's setting")
  ./resdesk.sh add-reader EMAIL [--name "Full Name"]  create a reader account

Maintenance
  ./resdesk.sh jobs                     what is running in the background (Desk: /app/resdesk-jobs)
  ./resdesk.sh jobs --stop-all [--now]  stop all ingests and queued jobs, pause schedules
  ./resdesk.sh jobs --stop RUN | --pause | --resume      (schedules)
  ./resdesk.sh jobs --pause-run RUN | --resume-run RUN  pause a run where it is, carry on later
  ./resdesk.sh jobs --pause-all | --resume-all          pause everything, then carry on
  ./resdesk.sh screenshots [--query WORDS]  retake the pictures used in the guides (needs Playwright)
  ./resdesk.sh docs [--check]           refresh the settings and command reference in docs/
  ./resdesk.sh progress [RUN]           watch an ingest run
  ./resdesk.sh workers <n>              number of parallel ingest workers (default 2)
  ./resdesk.sh reindex [--background] [--no-pages] [--reset]
  ./resdesk.sh backup                   database + files into ./site-backups
  ./resdesk.sh restore <file.sql.gz>    restore a database backup, then re-index
  ./resdesk.sh update [v0.4.0]          upgrade (same as ./upgrade.sh; --check to just look)
  ./resdesk.sh password [new]           reset the Administrator password
  ./resdesk.sh dev on|off               developer mode (Docker); native is always live
  ./resdesk.sh console | shell | bench …  for developers
  ./resdesk.sh uninstall                remove everything (asks first)
```

The Research Desk commands behind it (`./resdesk.sh <command>` runs `bench --site <site> resdesk <command>`):

| Command | What it does | Options |
|---|---|---|
| `count` | How many IA items match (before you ingest). | `--collection` IA collection id, e.g. ServantsOfKnowledge<br>`--filter` Extra IA query to narrow a collection, e.g. "language:kan"<br>`--query` A full IA advanced-search query instead of a collection<br>`--ids` Comma-separated IA identifiers<br>`--ids-file` File with one IA identifier per line<br>`--folder` Folder of IA-style item folders, e.g. /library-source or /library-source/2026<br>`--server` Web server with IA-style item folders, e.g. https://books.example.org/items/<br>`--manifest` With --server: URL of a list of item folders (one per line) |
| `ingest` | Bring books in from the Internet Archive or from IA-style item folders. | `--profile` Run an existing RD Ingest Profile by name<br>`--collection` IA collection id, e.g. ServantsOfKnowledge<br>`--filter` Extra IA query to narrow a collection, e.g. "language:kan"<br>`--query` A full IA advanced-search query instead of a collection<br>`--ids` Comma-separated IA identifiers<br>`--ids-file` File with one IA identifier per line<br>`--folder` Folder of IA-style item folders, e.g. /library-source or /library-source/2026<br>`--server` Web server with IA-style item folders, e.g. https://books.example.org/items/<br>`--manifest` With --server: URL of a list of item folders (one per line)<br>`--limit` Max items (0 = all). Default 50, or the profile's own limit<br>`--no-fulltext` Metadata only; skip OCR text<br>`--update` Refresh items already in the catalogue<br>`--name` Save the scope as a profile with this name<br>`--visibility` Who can see the new books: public, login-to-read or members (default: rules in Settings)<br>`--background` Hand the work to the queue workers (parallel; best for large runs) and watch progress |
| `progress` | Watch an ingest run (default: the latest). | `RUN` |
| `reindex` | Rebuild the search index from the catalogue (page text comes from the local cache when present). | `--no-pages` Only book-level records (fast)<br>`--background` Split across the queue workers (parallel)<br>`--reset` Drop and recreate the page index first |
| `configure` | Set Research Desk settings from the command line. | `--meili-url` Search engine address, e.g. http://127.0.0.1:7700<br>`--meili-key` Search engine API key<br>`--title` Portal title<br>`--base-url` Public URL, e.g. https://library.example.org<br>`--contact` Email/URL sent to the Internet Archive in the User-Agent |
| `status` | Catalogue and search-engine health. |  |
| `access` | Who can see what: public, login-to-read or login-to-find (members only). | `VISIBILITY`<br>`--collection` Books in this collection, e.g. ServantsOfKnowledge<br>`--profile` Books ingested by this RD Ingest Profile<br>`--language` Books in this language, e.g. Kannada or kan<br>`--ids` Comma-separated item identifiers<br>`--ids-file` File with one identifier per line<br>`--all` Every book in the catalogue<br>`--apply-rules` Re-apply profiles, rules and the default (Settings → Access)<br>`--include-manual` With --apply-rules: also change books set by hand or in bulk<br>`--guests` What visitors who are not logged in may do<br>`--signup` How people get reader accounts<br>`--default` Visibility for new books when no profile or rule decides |
| `add-reader` | Create a reader account (or give an existing account the Reader role). | `EMAIL`<br>`--name` Full name<br>`--no-email` Don't send the welcome email (set a password in the Desk instead) |
| `jobs` | What is running in the background; pause, resume or stop it. | `--stop` Stop this ingest run (e.g. RUN-00042)<br>`--stop-all` Cancel all runs and queued Research Desk jobs, pause schedules<br>`--now` With --stop/--stop-all: kill running jobs instead of letting them finish the current book<br>`--pause` Pause scheduled ingests<br>`--resume` Resume scheduled ingests<br>`--pause-run` Pause this ingest or push run (it keeps its place)<br>`--resume-run` Resume a paused run<br>`--pause-all` Pause all runs, hold waiting jobs, pause schedules<br>`--resume-all` Undo --pause-all: everything carries on |
<!-- /generated:commands -->
