# Server: updates, health & backups

The **Server** page in the Desk (Research Desk → *Server*, or `/app/resdesk-server`) shows
the state of the whole installation in one place and, if you allow it, lets a System Manager
look after it without opening a terminal:

- which version of Research Desk and Frappe is running, and whether a newer one is out;
- whether every part is working: database, cache, background workers, scheduler, search
  engine, disk space, backups;
- backups: make one, download one, and when they are made automatically;
- recent errors, failed jobs and log files;
- alerts by Desk notification, email and webhook when something goes wrong;
- with the **updater helper** on: **upgrade**, go back to an earlier release, **restart** a
  part, apply a **resource preset**, and read each part's logs, all from the Desk.

![The Server page](../sok_resdesk/public/images/guide/desk-server.png)

ResDesk Managers can see the page, make and list backups, and read logs. Changing the
installation (upgrading, restarting, applying a preset, deleting a backup) and downloading
backups needs the **System Manager** role.

## The Server page

| Part of the page | What it shows |
|---|---|
| Summary | Research Desk and Frappe versions (with *available* when a newer one is out), Docker or native install, health, disk space, the updater helper |
| Health | each part, with **OK**, **Check** (worth a look) or **Problem**, and a sentence saying why |
| Updates | the newest release, *What's new* from its release notes, and either the **Upgrade** button or the command to run on the server |
| Services | with the helper: every container (Docker) or process (native) and its state, **Logs** for each, and **Restart** buttons |
| Backups | the automatic schedule, **Back up now**, the list of backups with download links |
| Logs | recent errors, failed background jobs, and the end of any log file |
| Book limit | how many books the catalogue holds, the limit, and what this machine's CPUs, memory and disk can each take ([below](#book-limit)) |
| Resources | the resource preset in use, and **Apply a preset now** with the helper ([Resources](operations.md#resources-how-much-of-the-machine-research-desk-may-use)) |
| Alerts | where alerts go, and a test button |
| Updater helper | whether it is on and connected, and how to turn it on or off |

What each health line means:

| Line | Problem means |
|---|---|
| Background workers | none is running: ingests, exports and pushes wait. *Check* while Pause All is on |
| Scheduler | it hasn't run for 20 minutes: scheduled ingests, backups, quiet hours and alerts stop. *Check* when it has been switched off on purpose |
| Search engine | Meilisearch doesn't answer: the portal can't search |
| Disk | fuller than the alert level (Settings, 90% by default); *Check* 10% before |
| Backups | the last backup failed, or the newest is older than the schedule promises |
| Book limit | the catalogue is at its limit: no new books are added. *Check* from 90% |
| Errors | *Check* when errors were logged or background jobs failed in the last day: open them under Logs |
| Updater helper | it is on but hasn't reported for a minute and a half |

The page refreshes itself every 15 seconds.

## Security

Research Desk is secure by default; the Server page's health list says what is left to do,
under the same alerts as everything else (one alert when a check turns red, one when it is
fine again):

| Check | What it wants | Fix |
|---|---|---|
| **HTTPS** | the portal's address starts with `https://` | `./resdesk.sh https on <domain>` gets a Let's Encrypt certificate ([Installation](installation.md)) |
| **Administrator password** | not the default `admin` | `./resdesk.sh password`, or Desk → avatar → *My Settings* → Change Password |
| **Developer mode** | off on a public server | `./resdesk.sh dev off` |
| **Password strength** | strong passwords required | System Settings → Password |
| **Wrong passwords** | an account locked for a while after a few wrong tries (5 tries, 5 minutes since 0.41) | System Settings → Login |
| **Two-factor login** | worth turning on for staff | System Settings → Login → Two Factor Authentication |
| **Search engine key** | Meilisearch needs a key | set by the installer; Settings → Search |

What it does on its own:

- **Security headers** on every page and answer: content types are never guessed
  (`nosniff`), other sites can't frame the portal or the Desk (`frame-ancestors`,
  `X-Frame-Options`), no plugins, forms post only to the portal, a strict referrer, and HSTS
  over HTTPS.
- **Rate limits** on every public endpoint, per visitor (searches, pages, citations, downloads,
  sign-up), so a scraper or a script gets *429 Too Many Requests* instead of slowing the portal.
- **Fetching only public addresses**: links that come from outside (a repository record's PDF,
  its web page) are fetched only when they point at the public internet, never at this
  server's own network or a cloud's metadata service (the repositories you set up yourself
  may be on your network).
- **Members-only portals stay out of search engines**: with *Login required*, robots.txt
  turns every crawler away and the sitemap is empty.

## Search engines

Every published public book is in the **sitemap** (`/sitemap.xml`, an index of parts of 40,000
books, with the collections and the About page), and **robots.txt** points to it while keeping
crawlers out of the Desk, the API, proofreading, notes and searches. Submit
`https://<your portal>/sitemap.xml` in Google Search Console and Bing Webmaster Tools once; they
read it again by themselves. Lines you add in *Website Settings → Robots.txt* are kept.

Each page tells search engines and link previews what it is: a **description** (a book's own,
or one made from the catalogue: *A book by Kanakadasa from 1931 in Kannada. Read it and search
inside its text…*), its cover as the **image** (Open Graph and Twitter cards), its **canonical
address**, and the same page in each portal language (`hreflang`, `?_lang=kn`). Book pages also
carry schema.org JSON-LD, Highwire and COinS tags for Google Scholar and Zotero; the home page
says it is a library with a search box. Searches and filtered lists are followed but not indexed,
so search engines list books rather than endless result pages.

## Book limit

A machine can only hold so many books before searching slows down or the disk fills up.
Research Desk works out how many from the machine's **CPUs, memory and free disk**, using sizes
measured on real books ([Scaling](scaling.md)): about 27 KB of disk and 1.5 KB of memory per
page of text, and about 2.3 million pages per CPU, with 3 GB of memory for everything else and
some disk kept free for upgrades and backups (5% of the disk, 10 to 50 GB). The smallest of the
three is the limit.

Size is counted in **pages**, so a 600-page book uses three times the room of a 200-page one;
the limit is shown in books at your library's own average. The Server page shows how many books
each resource could hold, which one sets the limit, and how much room is left.

Settings → *Machine Resources* → **Book Limit**:

| Choice | |
|---|---|
| Automatic (the default) | what this machine can hold; it grows when you add memory, CPUs or disk |
| A number I choose | *Books at Most*, e.g. to keep room for something else on the same machine. More than the machine can take is allowed, at your own risk |
| No limit | never stop; the Server page still shows what the machine can hold |

At the limit, **ingests keep updating the books already in the catalogue but add no new ones**:
they are counted as skipped, and the run's log says *book limit reached*. **Check Count** on an
ingest profile says when a profile matches more books than there is room for. Managers get an
alert at 90% and again at the limit. To make room: add disk, memory or CPUs (Docker Desktop:
Settings → Resources), raise the limit in Settings, or remove books you don't need.

## Requirements

The **Requirements** card lists every tool Research Desk uses and how well this server has it:
what it is for, what was found (and its version), what is needed, and how to put it right.
**Check again** looks afresh; otherwise the list is worked out at most every ten minutes.

| Group | Checked |
|---|---|
| Core | Python (3.11+), Frappe (16), MariaDB (10.6+), Redis, the updater helper; on native installs `git` and `uv` |
| Search | Meilisearch, and its version: search in Latin letters and `OR` need 1.11 or newer |
| OCR and proofreading | Pillow, Tesseract (4+), and a Tesseract language model for each language the catalogue is OCR'd in (books' languages, languages named in their language labels, their *OCR Languages*), with how many books it covers |
| Preservation | the preservation folder (writable, free space), `boto3` for an S3 second copy, the second copy's folder or bucket (reachable) |
| Network and disk | archive.org reachable; free disk space |

A line is **ok**, **missing**, **too old**, **check** (works, but worth a look) or **not needed
now** (for a feature that is off, such as boto3 without an S3 second copy). The **Health** list
sums it up in one *Requirements* line, which also feeds the [alerts](#alerts).

**Installing what is missing:**

- **Docker**: everything comes with the Research Desk image, so every upgrade installs it: the
  fix is to [upgrade](#upgrading-from-the-desk). The image carries Tesseract with **every language model** it has
  (Debian's `tesseract-ocr-all`: the Indic languages, Urdu, Nepali, Assamese, English and the
  rest), so no book's language is missing a model. A library that wants a smaller image can set a
  list instead, such as `OCR_LANGS="kan hin eng"` in `.env`; the next upgrade rebuilds that layer
  (a few minutes), and a model missing from the list then shows here with the value to set.
- **Native**, with the [updater helper](#the-updater-helper) on: **Install** on a missing line
  installs Research Desk's Python packages, or Tesseract with its language models (Homebrew on
  macOS; apt on Ubuntu/Debian). The task's progress shows on the page like an upgrade's.
  apt needs administrator rights: the helper can use them only when `sudo` asks no password for
  its user; otherwise the task stops and shows the command to run.
- **Native, by hand**: each line shows its command (with **Copy**), e.g.
  `./resdesk.sh requirements install ocr`, `sudo apt-get install tesseract-ocr tesseract-ocr-all`
  or `brew install tesseract tesseract-lang`.

On the server, `./resdesk.sh requirements` prints the same list.

## Checking for updates

Once a day Research Desk looks on GitHub for a newer release and for Frappe patch releases, and
tells managers when one is out (Settings → *Server & Updates* → *Check for New Releases*).
**Check for Updates** on the Server page looks straight away. With the updater helper on, the
server also asks its own git remote, which is what an upgrade installs from.

*What's new* shows the release notes of every release between yours and the newest one. If a
release needs the search index rebuilt, the page says so.

## Upgrading from the Desk

With the updater helper on and the System Manager role, press **Upgrade to vX.Y.Z**:

- **Release**: the latest, or an older one to go back to. Going back only changes the code:
  if that release can't read the database as it is now, restore the backup made before the
  upgrade you are undoing.
- **Back up first** (recommended) makes a backup into `site-backups/` on the server.
- **Also update Frappe** brings Frappe to its newest v16 patch release. When the release you are installing needs a newer Frappe than this server has (each release names the Frappe it needs), the box is ticked and locked, and Frappe is updated with it, because the two must move together. On Docker this rebuilds
  the Frappe part of the image when a newer patch is out, which takes 10 minutes or more.

The upgrade is exactly `./upgrade.sh` ([Upgrading](operations.md#upgrading)), run on the server
by the helper: backup, new code, Frappe, migrations, restart, health check. The page shows its
output as it runs. The portal and the Desk go offline for a few minutes; the page says so and
reconnects by itself. When it finishes, managers get an alert with the result, and the task
stays in the list with its full log (Research Desk → *Server Tasks*).

If an upgrade fails, nothing is lost. The log ends with what went wrong and the two commands
that put things back (the previous version, and the backup it just made). Running ingests and
pushes are interrupted by the restart; resume them on Background Jobs.

Without the helper, the Updates box shows the command to run on the server instead:
`./upgrade.sh`. Settings → *Server & Updates* → *Allow Upgrades and Restarts from the Desk*
switches the buttons off (for everyone) without touching the server.

## Restarting and reading logs

With the helper, **Services** lists every part with its state. **Restart** the portal and Desk,
the background workers, the scheduler, the search engine, or everything (native installs can
only restart everything). **Logs** shows the last few hundred lines of that part.

Without the helper, the health list still shows whether each part answers, and **Logs** shows
errors, failed jobs and the log files the app can read. On the server:
`./resdesk.sh status`, `./resdesk.sh logs queue`, `./resdesk.sh restart`.

## Backups

Research Desk backs up its database every night at 02:30 (server time) by itself: Settings →
*Server & Updates*:

| Setting | |
|---|---|
| Automatic Backups | Daily (the default), Weekly (Sunday night) or Off |
| Include Uploaded Files | also back up logos, pictures and attachments. Books themselves are never in a backup: they stay on archive.org or in your folders |
| Backups to Keep | older ones are deleted after each new backup (7 by default) |

**Back up now** and **Back up with files** make one straight away (it takes a moment to appear).
A System Manager can download each part of a backup and delete old ones. With the helper,
**Back up on the server** runs `./resdesk.sh backup`, which also copies the backup into
`site-backups/` in the Research Desk folder.

These backups stay on the same disk as Research Desk. **Download one now and then** (or copy
`site-backups/`) and keep it somewhere else: another disk, Nextcloud, a NAS. Restoring is done
on the server: `./resdesk.sh restore FILE` ([Backups](operations.md#backups)). The search index
is never in a backup; it is rebuilt from the catalogue.

A backup that fails raises an alert and shows as a **Problem**.

## Help pictures

The help pages show screenshots of Research Desk. **Retake help pictures** (Server page, under
Backups; needs the [updater helper](#the-updater-helper)) takes them again from **this
library**, with its own name, logo, books and collections, and the help shows them as soon as
they are ready (a few minutes). They are kept in the site's files, so upgrades keep them and
backups with files include them. When an upgrade changes a screen, its picture goes back to the
one that comes with Research Desk (which shows the new screen) until you retake them; the Server
page says how many are out of date.

On the server the same is `./resdesk.sh screenshots --site`. Nothing needs installing: when the
server has no Playwright (the browser the pictures are taken with), it runs in Playwright's own
Docker image (`mcr.microsoft.com/playwright/python`, with the Playwright package fetched into
it from PyPI; `PLAYWRIGHT_VERSION` in `.env` picks another version). Without `--site`, the pictures go into the code (`sok_resdesk/public/images/guide/`),
for changes to the project's own documentation. Pictures of the Desk show what staff see: with
Administrator's password (in `.env`) they are taken as a staff account, *Help Pictures*
(`help-pictures@example.org`), switched on for the pictures and off again afterwards. A
library whose portal is members-only shows visitors only its login page, so its portal pictures
are taken as a reader account too (*Help Pictures Reader*, `help-pictures-reader@example.org`); `--query WORDS` chooses the search shown in the results
pictures (default: `history`, so pick words your catalogue finds).

## Alerts

Managers (ResDesk Manager and System Manager) are told when:

- a part stops working (workers, scheduler, cache, search engine, the helper), and again when
  it is fine;
- the disk is fuller than the alert level;
- a backup fails;
- an upgrade from the Desk finishes or fails;
- a new release is out (once per release).

Checks run every 10 minutes. Alerts go to:

| Where | How |
|---|---|
| Desk notifications | always (the bell at the top of the Desk) |
| Outgoing email | sign-in links, sign-up confirmations, password resets and alerts all need it: **Connections → Outgoing email** sets it up and sends a test (presets for Gmail, Microsoft 365, Zoho, SES, Brevo and Resend: for Resend the login is `resend`, the password is the API key, and the sender must be on a domain verified in Resend) |
| Email | to every manager, and the *Also Email* addresses, when *Email Alerts to Managers* is on. Needs an outgoing email account: Desk → Email Account |
| Webhook | *Alert Webhook URL*: a JSON post with the message in `text`, which Slack, Mattermost and Discord (add `/slack` to a Discord webhook address) show as a message. Other fields: `event`, `severity` (`bad`, `ok`, `info`), `message`, `site`, `link`, `at` |

**Send a test alert** (Server page, Alerts) checks all three.

For an outside uptime monitor (Uptime Kuma, a hosting provider's check, a load balancer), use
`https://your-library/api/method/sok_resdesk.server.ping`: it answers `{"status": "ok"}`, or
HTTP 503 when a part is down, and says nothing else.

## The updater helper

The app can't replace or restart itself from inside its own container, so upgrades and restarts
from the Desk need something next to it: the **updater helper**. It is off until you turn it
on, because it can control Docker and change the Research Desk folder.

```bash
./resdesk.sh updater on        # turn it on (once)
./resdesk.sh updater status    # is it running? its last lines
./resdesk.sh updater off       # turn it off again
```

- **Docker**: a small container, `updater`, with the Docker command line, git and Python. It
  sees the Research Desk folder and the Docker socket. On Linux it runs as your user, so files
  it writes in the folder stay yours.
- **Native**: a process in the bench's Procfile (`updater`), started with the others.

`updater on` makes a new secret token each time and restarts nothing else (native installs
restart once to add the process).

### How the updater helper works

Every five seconds the helper tells Research Desk what it sees (version, git state, which parts
run, disk space) and asks whether there is work. When a System Manager presses a button, the
page records an **RD Server Task**; the helper picks it up, runs the matching command and sends
back the output:

| Task | Command |
|---|---|
| Upgrade | `./upgrade.sh --yes [vX.Y.Z] [--no-backup] [--no-frappe]` |
| Restart | `docker compose restart …` (native: `./resdesk.sh restart`) |
| Apply a preset | `./resdesk.sh resources light\|standard\|server` |
| Server backup | `./resdesk.sh backup` |
| Check for updates | `git fetch --tags` |
| Logs | `docker compose logs --tail N part` (native: the part's log file) |

That list is all it does: nothing else can be asked of it, and every argument is checked twice,
by the site and by the helper. It talks only to your own Research Desk, with a secret token
kept in `.env` and the site config. Long tasks run apart from the helper (in a short-lived
container on Docker, a detached process on native), so they carry on while the restart they
cause replaces the helper itself.

### Troubleshooting the helper

| Problem | Try |
|---|---|
| *Not reporting* on the Server page | `./resdesk.sh updater status`; `./resdesk.sh updater on` again |
| "The site refused the token" in its log | `./resdesk.sh updater on` (makes a new token for both sides) |
| An upgrade says there are local code changes | someone edited files in the Research Desk folder: `git status`, then commit or `git stash` them |
| A task stays *Running* | the helper stopped reporting; after three hours the task is marked failed. Its log is in `logs/upgrade-<date>.log` on the server |
