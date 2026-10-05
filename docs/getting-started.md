# Getting started

This guide takes you from nothing to a working research portal with real books. No
programming is needed; you type a few commands into a terminal.

## 1. Install Docker (or skip it)

Research Desk can run in Docker (recommended: everything is kept in one box, easy to remove)
or **directly on your computer** (macOS with Homebrew, or Ubuntu/Debian). For the native way,
skip this step and run `./install.sh --native` in step 2; the installer sets up Python,
Node, MariaDB, Redis and Meilisearch for you. See
[Installation → Native install](installation.md#native-install-no-docker).

- **Mac / Windows:** install [Docker Desktop](https://www.docker.com/products/docker-desktop/)
  and open it once. In *Settings → Resources*, give it at least **4 GB of memory**.
- **Linux:** install Docker Engine and the Compose plugin
  (`sudo apt install docker.io docker-compose-plugin` on Ubuntu/Debian).

Check it works: `docker compose version`

## 2. Download and install Research Desk

```bash
git clone https://github.com/ServantsOfKnowledge/researchdesk.git
cd researchdesk
./install.sh
```

No git? Download the ZIP from the GitHub page, unzip it, open a terminal in that folder and
run `./install.sh`.

The installer asks:

| Question | What to enter |
|---|---|
| Portal name | What visitors see, e.g. *Sanchaya Research Desk* |
| Your email | Sent (politely) to the Internet Archive with each request so they can contact you. Optional. |
| Web address | On your own computer: leave it empty. On a server with a DNS name pointing at it: the name, e.g. `research.example.org`. The installer then gets an HTTPS certificate from Let's Encrypt, through the server's nginx if it has one ([step by step](installation.md#step-by-step-a-new-linux-server-that-already-runs-nginx)) |
| Port | `8080` unless something else already uses it |
| Internal site name | Keep the default |

Change the address later with `./resdesk.sh url https://new.address`
([Changing the portal's address](installation.md#changing-the-portals-address)).

The first install downloads and builds the software, which takes 10 to 20 minutes. Later starts
take seconds. At the end, answer **Y** to load 20 sample Kannada books.

## 3. Look around

(On a server with a name, use `https://your.name` instead of `http://localhost:8080`.)

- **Public portal:** <http://localhost:8080/>. Try searching `ವಿಜಯನಗರ` or `hampi`,
  then switch to **Inside the text** to search the OCR of every page.
- **Admin (the Desk):** <http://localhost:8080/app/research-desk>. Log in as `Administrator`
  with the password the installer printed (it's also in the `.env` file).

## 4. Add your logo

Desk → Research Desk → **Settings** → *Logo & Branding* → **Logo** → upload a PNG or SVG
(a wide logo about 400×120 px works well) → **Save**. It appears on the portal home page and top
bar, on the login page, and in the Desk. Add a square **Icon** too (e.g. just the emblem of your
logo): it is used for the browser tab and the Research Desk icon in the Desk, where a wide logo
would be too small to read. You can also set the portal name, tagline and a background photo for
the home page there.

## 5. Add your own selection of books

1. Desk → **Ingest Profiles** → **+ Add**.
2. Give it a name, for example *Kannada University books*.
3. **Choose By:** *Collection*. **IA Collection:** `KannadaUniversity`.
4. Optional **Narrow With:** `date:[1900-01-01 TO 1960-12-31]`
5. **Maximum Items:** start with `50`.
6. **Save** → **Check Count** → **Run Ingest**.

The run page shows progress. Each book takes a few seconds: metadata, then the OCR text of
every page. See [Choosing & ingesting books](ingesting.md) for more ideas.

From then on the profile **keeps itself in step** with archive.org: every day new books added to
the collection come in, changed ones are refreshed and removed ones are unpublished, and a
collection page named after it appears on the portal. Check Count also tells you when a
profile matches more books than this machine has room for (the
[book limit](server.md#book-limit)).

Books in your own folders (scans not yet on archive.org, a NAS, another server)? See
[Books from your own folders or servers](local-folders.md). From a DSpace, EPrints or other
repository? See [Books from repositories](repositories.md).

## 6. Cite a book

Open any book page. The **Cite this book** box has tabs for BibTeX, RIS, APA, MLA, Chicago
and more. Copy the text or download the file. Zotero users can click the Zotero browser button
on the book page and it picks up the record automatically.

To build a bibliography, click **＋** next to search results to add books to **My list**,
then export the whole list, or copy a share link and send it to your students.

## 7. Keep some books for members (optional)

Everything is public to start with. To keep some books for logged-in readers, open
Desk → *Items*, tick them → **Actions → Set Who Can See Them**, or make the whole portal an
internal library in **Settings → Access & Sign-up**. Readers can sign up themselves or be added
by you. See [Who can see what](access.md).

## 8. Everyday commands

```bash
./resdesk.sh stop        # stop (your data is kept)
./resdesk.sh start       # start again
./resdesk.sh status      # what's running, how many books
./resdesk.sh backup      # save a backup into ./site-backups
./resdesk.sh help        # everything else
```

Research Desk also backs itself up every night. **Research Desk → Server** in the Desk shows the
backups (download one now and then, and keep it somewhere else), whether every part is working,
and alerts you when something isn't.

## 9. Keep it up to date

```bash
./upgrade.sh --check     # is there a new release?
./upgrade.sh             # back up, upgrade, migrate, restart and check it all works
```

If anything goes wrong, the script prints the two commands that take you back to the
previous version. See [Operations → Upgrading](operations.md#upgrading).

Rather do it from the browser? Run `./resdesk.sh updater on` once; after that a System Manager
can upgrade (and restart parts) from **Research Desk → Server**, and watch it happen
([Server](server.md#upgrading-from-the-desk)).

Having trouble? See [Operations → Troubleshooting](operations.md#troubleshooting).
