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
| Port | `8080` unless something else already uses it |
| Internal site name | Keep the default |

The first install downloads and builds the software, which takes 10 to 20 minutes. Later starts
take seconds. At the end, answer **Y** to load 20 sample Kannada books.

## 3. Look around

- **Public portal:** <http://localhost:8080/library>. Try searching `ವಿಜಯನಗರ` or `hampi`,
  then switch to **Inside the text** to search the OCR of every page.
- **Admin (the Desk):** <http://localhost:8080/app/research-desk>. Log in as `Administrator`
  with the password the installer printed (it's also in the `.env` file).

## 4. Add your logo

Desk → Research Desk → **Settings** → *Logo & Branding* → **Logo** → upload a PNG or SVG
(a wide logo about 400×120 px works well) → **Save**. It appears on the home page, in the top
bar and as the browser-tab icon. You can also set the portal name, tagline and a background photo
for the home page there.

## 5. Add your own selection of books

1. Desk → **Ingest Profiles** → **+ Add**.
2. Give it a name, for example *Kannada University books*.
3. **Choose By:** *Collection*. **IA Collection:** `KannadaUniversity`.
4. Optional **Narrow With:** `date:[1900-01-01 TO 1960-12-31]`
5. **Maximum Items:** start with `50`.
6. **Save** → **Check Count** → **Run Ingest**.

The run page shows progress. Each book takes a few seconds: metadata, then the OCR text of
every page. See [Choosing & ingesting books](ingesting.md) for more ideas.

Books in your own folders (scans not yet on archive.org, a NAS, another server)? See
[Books from your own folders or servers](local-folders.md).

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

## 9. Keep it up to date

```bash
./upgrade.sh --check     # is there a new release?
./upgrade.sh             # back up, upgrade, migrate, restart and check it all works
```

If anything goes wrong, the script prints the two commands that take you back to the
previous version. See [Operations → Upgrading](operations.md#upgrading).

Having trouble? See [Operations → Troubleshooting](operations.md#troubleshooting).
