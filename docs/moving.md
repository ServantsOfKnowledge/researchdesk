# Moving to another server, or between Docker and native

Research Desk can move in any direction: to a bigger server, from a laptop to a server, from
Docker to a native install or back. Everything that matters travels in **one file**: the
catalogue, collections, readers and staff with their passwords, settings, uploaded files (logo,
covers, exports), the page text of every book, and the key that unlocks saved passwords (push
targets, the search-engine key).

What doesn't travel, because the new server makes its own:

- **the search index**: rebuilt on the new server from the page text in the file, without
  downloading anything from archive.org (minutes for thousands of books);
- **passwords in `.env`** (database, search engine): the new install has its own;
- **resource settings** (`./resdesk.sh resources`): each machine gets what suits it;
- **your book folders** (`LIBRARY_DIR`), if you ingest from folders: copy them yourself, or use
  `move-to --with-library` (below).

## The short way: `move-to` (over SSH)

On the new server, install Research Desk as usual (Docker or native), with the new address if
it has one ([Installation](installation.md)):

```bash
git clone https://github.com/ServantsOfKnowledge/researchdesk.git researchdesk
cd researchdesk && ./install.sh --no-sample
```

Then, on the **old** server, one command does the rest:

```bash
./resdesk.sh move-to user@new-server --base-url https://library.example.org --with-library
```

It exports, copies the file over SSH, imports it on the new server and starts rebuilding search.
Options:

| Option | |
|---|---|
| `user@host:DIR` | where Research Desk is installed on the new server (default `~/researchdesk`) |
| `--base-url URL` | the new public address (Settings → Public Base URL); leave out if it stays the same |
| `--with-library` | also copy your book folders (`LIBRARY_DIR`) with `rsync`, into the new server's `LIBRARY_DIR` |
| `--port N` | SSH port, if not 22 |

It needs SSH login with a key (`ssh-copy-id user@new-server` sets that up). The old install keeps
running: check the new one, point your domain at it, then `./resdesk.sh stop` on the old one.

## The step-by-step way: export and import

Use this when the servers can't reach each other, or you'd rather copy the file yourself (a USB
disk, `scp`, a shared drive).

**1. On the old server**, make the file:

```bash
./resdesk.sh export
# → site-backups/resdesk-move-20261001-0930.tar.gz
```

It takes a minute or two. The file holds the key that unlocks saved passwords, so treat it like
a password: keep it private and delete it when you're done.

**2. Copy the file** to the new server, into its Research Desk folder.

**3. On the new server**, install Research Desk if you haven't, then:

```bash
./resdesk.sh import resdesk-move-20261001-0930.tar.gz --base-url https://library.example.org
```

It asks before replacing anything (`--yes` skips the question). The new server must run the same
or a newer version of Research Desk (`./upgrade.sh` first if not).

**4. Book folders**: if you ingest from folders, copy them to the new server's `LIBRARY_DIR`
(for example `rsync -a /old/library/ new-server:/srv/library/`). Paths inside the catalogue are
relative to the folder, so a different location is fine.

**5. Check**: open the portal and the Desk. Search fills up over a few minutes (Background Jobs
shows the re-index). Then point your domain at the new server.

## After the move

- **Log in with the old Administrator password**: the users came along. Change it with
  `./resdesk.sh password` if you like (and update `ADMIN_PASSWORD` in `.env` for your notes).
- **The address**: if you didn't use `--base-url`, set Settings → **Public Base URL** when the
  address changes, so citations and OAI-PMH links point to the right place.
- **Scheduled ingests** carry on on the new server. Stop the old server (`./resdesk.sh stop`) so
  both don't ingest the same books.
- **Resources**: pick what suits the new machine: `./resdesk.sh resources server`
  ([Operations → Resources](operations.md#resources-how-much-of-the-machine-research-desk-may-use)).
- **Koha and other harvesters** only need the new OAI-PMH address if the address changed.

## To or from Coolify

Coolify runs the same containers under its own names, so use `./resdesk.sh coolify import`
there instead of `import` ([Installation → Coolify](installation.md#coolify)). Leaving Coolify:
`./resdesk.sh coolify export` on its server, then `./resdesk.sh import` on the new one.

## Between Docker and native

The same commands work in every direction: the file doesn't depend on how Research Desk runs.
Install the new side with `./install.sh` (Docker) or `./install.sh --native`, then import.
Docker keeps its data in Docker volumes and a native install in `~/researchdesk-bench`; the
import puts everything in the right place for the new side.

To switch on **the same machine**: export, stop the old side (`./resdesk.sh stop`), install the
other side in a **new folder** (a second clone), import there, and when it looks right remove
the old one (`./resdesk.sh uninstall` in the old folder). Both use port 8080 by default, so stop
the old one first, or give the new one another `HTTP_PORT` in its `.env`.

## By hand (what the commands do)

For administrators who want to do it themselves, or move to a setup the scripts don't know:

1. `bench --site SITE backup --with-files`: the database and the public and private files.
2. Copy `sites/SITE/private/resdesk-pages/` (page text; saves re-downloading).
3. Note `encryption_key` from `sites/SITE/site_config.json`.
4. On the new install: `bench --site SITE --force restore DB.sql.gz --with-public-files FILES.tar
   --with-private-files PRIVATE.tar`, then `bench --site SITE set-config -- encryption_key KEY`,
   put the page text back under `sites/SITE/private/`, and `bench --site SITE migrate`.
5. Point the catalogue at the new search engine: `bench --site SITE resdesk configure --meili-url
   URL --meili-key KEY` (and `--base-url` if the address changed).
6. `bench --site SITE resdesk reindex --background`.
