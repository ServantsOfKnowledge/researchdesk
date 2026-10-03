# Changelog

## 0.24.0 (2026-10-05): proofreading and re-OCR, part by part

- **Proofread** in Page & text: the page text becomes an editor beside its image; **Save as
  proofread**, **Validate** (a second person, text unchanged), and a **History** of every version
  with **Make current**. Corrected pages are what readers see, search finds and citations quote,
  and re-ingesting a book never undoes them
- **Read a page again, part by part**: draw as many zones as the page has (columns, headings,
  side notes, footnotes), order them, skip pictures, or start from a layout (*Two columns*,
  *Three columns*, *Heading and two columns*). Each zone is read on its own with Tesseract and the
  book's language model, so columns no longer run into each other
- **Re-OCR whole books** in the background (book form, or Items → *Re-OCR the worst books*): the
  new text is kept only where it scores clearly better, and pages people proofread are never
  replaced
- **Proofreading work list** (`/library/proofread`): OCR error reports to correct, pages to
  validate, the books with the poorest OCR; by language
- New **ResDesk Proofreader** role (portal only), **Page Texts** in the Desk, and Tesseract with
  Indic language models in the Docker image (and the native installer)
- Every pure test file now runs in CI

## 0.23.0 (2026-10-05): notes on the pages

- **Notes in Page & text** for logged-in readers: select words to **Highlight**, **Comment**,
  **Tag**, ask a **Question**, **Link** (e.g. to Wikidata) or report an **OCR error**; or **Mark a
  region** of the page image. Shown as coloured marks and boxes, listed under the page, hidden
  with *Show notes*
- **Who can see a note**: only its author, a **research group** (made by staff in the Desk, with
  its members), or everyone after a manager **approves** it (Annotations → Review)
- **Notes stay with their words**: kept by position and by quote (W3C), so a note finds its words
  again after the page text is corrected; one whose words are gone says so
- **My notes** (`/library/notes`): search your notes and your groups', open them at their page,
  and **export** them with page citations as Markdown, a spreadsheet or W3C Web Annotations
- **OCR error** reports always reach the managers: the start of proofreading (0.24)
- A book's approved public notes are published as a W3C AnnotationPage for other tools
- Fixed on the portal: the `hidden` attribute could be overridden by other styles

## 0.22.0 (2026-10-05): Page & text, next to the book reader

- **Page & text**, a second reader on every book page beside the book reader (archive.org's,
  unchanged and still the first one shown): each page image next to the text read from it,
  with its printed page number. Arrows, ← → keys or a page number to move; search inside the
  book opens its hits here, with the words marked, while it is showing
- **Copy page link**: a link that opens the book at that page in Page & text (`?page=…&view=text`;
  a page's ARK `…/n41` leads there too once ARKs are on)
- **Cite this page** in APA, MLA, Chicago, BibTeX, RIS and CSL-JSON: *p. 42*, or *leaf 7* when no
  number is printed, linking to the page (BibTeX `pages`, RIS `SP`, CSL-JSON `page`)
- **Open in book reader** switches back at the same page
- It is the ground the next releases build on: annotations (0.23) and proofreading (0.24)

## 0.21.2 (2026-10-05): OCR quality you can see

- **OCR Quality is a column of the Items list**, and Background Jobs → Machine shows how many books
  are scored, with *Score now* and *Worst first*
- **Fixed: scoring the books already in the catalogue stalled.** It queued a job per 200 books at
  once (about 440 for 88,000 books), which the job queue refuses past its limit. It is now one job
  that works through them all and queues itself again. It starts with this upgrade
- Books whose page text isn't kept on the server are marked (−1 low-quality pages) instead of
  being tried again every day; they are scored when next indexed

## 0.21.1 (2026-10-05): Books first by itself

- **Books first happens by itself** when a new book has waited more than 15 minutes in the search
  engine behind page text (at most every 30 minutes): the page text is moved back and sent again
  later, and new books reach the portal first. Settings → Machine Resources → *Books First
  Automatically* (on by default); the Search queue card shows when it last did

## 0.21.0 (2026-10-05): the search queue, under control

- **Background Jobs → Search queue** shows what waits in the search engine (book records and page
  text separately), how many tasks a minute it gets through, how long it has to go, failures,
  page text held back and the size of its task history
- **Books first**: cancels the page text waiting in the search engine, so the book records queued
  behind it are listed next: new books reach the portal within minutes instead of after hours of
  page text. The page text is sent again in the background, from the text kept on the server, at
  the pace the engine keeps up with. Nothing is lost
- **Hold page text / Resume page text**: books keep being catalogued and listed while their page
  text waits; resuming sends it
- **Clear finished tasks**, and weekly by itself: the search engine's record of finished tasks no
  longer grows without end
- **Fixed: cancelling search-engine work lost books.** *Cancel pending indexing* (and *Stop
  everything* with search) cancelled every waiting task outright, book records included, leaving
  books in the catalogue that never reached the portal. Cancelling now keeps track of what it
  cancels: page text is sent again, book records count as not sent (*Send them*)
- **Fixed: books already in the catalogue were never given an OCR quality** (0.20 looked for
  empty scores, but the database keeps them at 0). They are scored after this upgrade; 0 now
  means *not scored yet*

## 0.20.0 (2026-10-05): permanent links, preservation copies, OCR quality, search indexing that moves

- **A permanent link for every book (ARK), switched on when the library is ready.** Settings →
  Persistent Identifiers: enter the NAAN the ARK Alliance gives the library and tick *Give Books
  ARKs*. Every book then gets an ARK (those already here in the background), shown as *Permanent
  link* on its page and used by citations, exports, OAI-PMH and pushes. The portal resolves ARKs
  itself (`/ark:/<naan>/<name>`, `/n42` for a page, `?info` for a short record). Until it is on,
  nothing is minted or shown. Once on, the NAAN can't be changed, and a deleted book leaves a
  **tombstone**, so its link never ends in "page not found"
- **The library's own copies of its books.** Settings → Preservation: a folder, which books (by
  collection or all), page images or not, a size budget. Each book is kept as an **OCFL** object
  (an open standard: plain files and a checksum inventory, readable without Research Desk), each
  file checked against archive.org's md5 as it arrives, a new version only when a file changed.
  Every night a share of the copies is **checked against their checksums**; a failure marks the
  book, is recorded as a **Preservation Event** and alerts on the Server page. In Docker the
  folder is `/preservation` (a volume, or `PRESERVATION_DIR` for a disk or NAS)
- **OCR quality for every book**, 0 to 100 with its low-quality pages, from the text itself
  (broken Indic words, mixed scripts, stray symbols): sort the Items list by it to find the books
  that most need better OCR. Books are scored as they are indexed, and those already here in the
  background from the page text kept on the server
- **When search indexing doesn't move.** The search engine takes at most 50 waiting tasks per
  batch (`MEILI_MAX_BATCHED_TASKS`): before, it could take on a batch too big for its memory,
  run out, restart and start the same batch again, so the queue never moved. Workers hold back
  while more than 300 tasks wait, so ingesting goes at the pace indexing can keep up with.
  Background Jobs → Machine shows what the engine is working on (since when, how far), the oldest
  waiting task and the last failure, with *Restart search engine* when it is stuck; the Server
  page turns *Search indexing* red (and alerts) when tasks wait and nothing is worked on
- New help page: *Permanent links, preservation & OCR quality*; Operations → *Search indexing is stuck*

## 0.19.1 (2026-10-05): Pause, Stop and the jobs list work again; failed runs retry by themselves

- **Fixed: Pause (and Stop, and the jobs list) failed with "signal only works in main thread of
  the main interpreter".** Listing the running jobs made RQ clean up its started registry, which
  runs the failure callbacks of dead jobs with a SIGALRM timer, and that only works in a main
  thread, not in a web request. Listing now only reads; the 10-minute watcher (a worker's main
  thread) does the clean-up
- **Failed work is tried again by itself.** A run that ends *Completed with Errors* or *Failed*
  retries 15 minutes later, up to twice, taking only the books that failed; after that it waits
  for **Retry**. (Runs that lose their workers already carried on by themselves since 0.19.0)

## 0.19.0 (2026-10-05): the portal book count, worker priority, the guide

- **The portal's book total no longer stops at 10,000.** The count under the search box comes
  from the search engine, which only counted that far, so with more than 10,000 books it stayed at
  10,000 however many were ingested. The books index now counts them all (an upgrade patch applies
  it); page-text searches show *10,000+ matching pages*
- **New books reach the search sooner.** Each book used to send its own few small tasks, and the
  page text of earlier books queued in front of the next book itself. A batch now sends all its
  books in one task first, then the page text in a few big ones; Kannada, Hindi and Tamil text is
  sent as itself instead of `\uXXXX` escapes. Books that never got there are listed on
  Background Jobs → Machine with a **Send them** button
- **Worker priority can be changed live** by an admin (Background Jobs → Machine → Worker
  priority, or Settings): each worker applies it between books, no restart. Docker workers may
  also be made *less* nice (`ulimits: nice`). Quick jobs are now taken before long ingest batches
- **The getting-started guide can be brought back**: hiding it leaves a *Show the guide again*
  line on the workspace, keeping what was ticked
- **Fixed: runs that lost their workers never carried on.** Two schedules shared the same
  `*/10 * * * *` key in `hooks.py`, so the Server page's watcher replaced the job that carries
  interrupted runs on (a check now guards against it)
- **Releases tag themselves**: a `release.yml` workflow tags and publishes the version on `main`
  when it has no `v*` tag yet (installs find releases by tag), and starts the image build
- Faster: the home page's book and collection counts are worked out once a minute rather than on
  every view; the page-text cache is compressed at a lighter level (3x quicker to write)

## 0.18.0 (2026-10-04): big ingests that don't stall or do work twice

- **A big run no longer stalls.** Every batch of a run used to go into the queue at once; a
  run of 35,000 books (700 batches) hit Frappe's limit of queued jobs ("Too many queued
  background jobs"), so the batches past the limit were never queued: the run sat at the
  same count with nothing left to do it, and the other runs' jobs waited behind hundreds of
  batches. Batches now wait on the run and go into the queue a few at a time (twice the
  number of workers), one more each time one finishes
- **Books already done aren't fetched again.** A batch skips a book that any run brought in
  since this run started, and a run that only takes new books skips those another run added
  meanwhile. *Carry On* and *Try Again* list the books again and take only those not done yet
- **One run per profile at a time.** Starting a profile that already has a run going (or
  paused) is refused, with the run's name: two would fetch the same books twice
- **Runs that lose their workers carry on by themselves.** Every 10 minutes, a run none of
  whose batches is queued, running or held any more (after an upgrade, a restart or not
  enough memory) is marked *Interrupted* and carried on, skipping what is done (up to three
  times; after that it waits for *Carry On*). Runs with no progress for two hours are still
  marked *Interrupted*
- **Books left out at the book limit are shown on the run** (*New Books Left Out*), with a
  red note and the way out: raise the limit in Settings → Machine Resources, then *Carry On*
  brings them in
- Parallel workers that bump into each other on the same author, subject or collection try a
  book up to five times (was three), waiting a little longer each time

## 0.17.1 (2026-10-03): trying failed ingests again

- **Failed ingest work can be tried again, in the same run.** On the run: **Retry Failed
  Books** (Completed with Errors: exactly the books that failed), **Carry On** (Interrupted:
  batches cut off by a restart go back in the queue, failed books are taken again; Cancelled:
  the books are listed again) and **Try Again** (Failed while listing the books). The same
  next to each recent run on Background Jobs. Runs now remember which books failed; older
  runs are read back from their logs
- **The Server page's Failed jobs list works**: it looked for failed jobs under the wrong queue
  names, so it was always empty (and the health check never counted them). Each failed job
  has **Retry**, with **Retry all** and **Clear the list**; ingest batches go back into their
  run
- Runs marked *Interrupted* or *Cancelled* show those words properly in the Desk (they were
  missing from the status list)

## 0.17.0 (2026-10-02): advice before installing

- **`./install.sh --check`** (`scripts/preflight.sh`) looks at the machine and advises how best
  to install, changing nothing: memory, disk and CPUs; whether Docker is installed, running and
  usable, with Compose v2 and enough memory; Coolify; what has ports 80 and 443 (nginx,
  Apache, Caddy, Traefik, a container, Research Desk's own proxy) and so how HTTPS will work;
  the portal's port; an existing MySQL/MariaDB (prefer Docker then); the network to GitHub,
  archive.org and Docker Hub; with `--domain`, whether the name points at the machine; an
  earlier install. The installer runs it first on a new install and shows what needs
  attention, and asks before going ahead on a Coolify server

## 0.16.1 (2026-10-02): the logo on the help pages, and SOK

- **The help pages carry the library's logo**, on the portal (for readers) and in the Desk (for
  staff): the one set in Settings → Logo & Branding, or else the Servants of Knowledge logo
  (Ganesha reading), which now ships with Research Desk (`public/images/sok-logo.png`). The
  documentation on GitHub carries it too, and every picture in the guides was taken again with
  it, showing the About page and the library at `/`
- **SOK, not SoK**, everywhere: the default portal name *SOK Research Desk*, the starter
  profiles (*SOK Kannada sample*, *SOK English sample*), the guides, and the name Research
  Desk gives itself to archive.org and in MARC records (`SOK-ResDesk`). Upgrades rename the
  portal and the starter profiles where they still have the old spelling
- **`scripts/publish.sh`** puts the newest release on GitHub's `main` branch, so a fresh
  `git clone` always gets the current version (`main` had stayed at 0.4.0 while only the tags
  were pushed, because the folder was on a release tag rather than on `main`)
- The *About Page* link in the workspace and *Open Portal* going to `/` now reach existing
  installs (the workspace file's date had gone backwards in 0.15.0, so upgrades skipped it)

## 0.16.0 (2026-10-02): the library at /

- **The library's search page is the site's front page, `/`**, for everyone, logged-in staff
  included (Frappe used to show them their role's home page there). Every link to it (the top
  bar, crumbs, author, language and subject links, reading-list share links, the About page's
  button, Open Portal in the Desk) now says `/`, and searches are `/?q=…`. `/library` and
  `/library?q=…` lead to `/`, so links already shared keep working. Book pages stay at
  `/library/item/…`, the addresses in citations
- With the About page as the front page (Website Settings → Home Page = `about`), the search
  page moves to `/library` and all links follow

## 0.15.0 (2026-10-01): an About page

- **An introduction to the library at `/about`**, edited in the Desk (Research Desk → About
  Page): a headline and introduction, live numbers (books, pages of searchable text,
  collections, languages), a button to `/library`, numbered steps on how to use it, highlight
  cards, featured collections and a free-form part for anything else. It has a link in the
  portal's top bar (with your label), and switching it off hides both. New installs and
  upgrades start with a ready-made page to change

## 0.14.0 (2026-10-01): HTTPS from Let's Encrypt, and the portal's address

- **HTTPS is part of the installation**: `./install.sh --domain library.example.org` (or giving
  the name when the installer asks for the web address) sets the portal's address and gets a
  free Let's Encrypt certificate. `./resdesk.sh https on DOMAIN` does it later: nginx on ports
  80 and 443 in front of the portal, certbot renewing the certificate by itself, HTTP
  redirected to HTTPS, and the portal's own port kept to the server. `https status`, `renew`,
  `off`. The containers live in `compose.https.yaml`, added only when HTTPS is on, so Coolify
  never starts them
- **Works with the server's own nginx**: when nginx already has ports 80 and 443 (other sites
  on the server), and on every native install on Linux, `https on` adds a site for Research
  Desk to that nginx and uses the server's certbot (`--nginx`), leaving the other sites alone.
  Before, native installs ignored nginx entirely, and realtime updates (progress bars, live
  lists) didn't reach browsers; the nginx site now routes them to Frappe's socket.io server
- **`./resdesk.sh url`** shows the portal's address everywhere it is kept, and
  `./resdesk.sh url https://NEW` changes it in one go (`.env`, the site's `host_name`, Settings
  → Public Base URL), with no restart. With HTTPS on, a new name gets its own certificate
  while the old one keeps working until it does
- Changing the address no longer waits for the search engine (it could take a minute while
  books were being indexed)

## 0.13.0 (2026-10-01): Coolify

- **Deploys on Coolify**: `WORKERS_PER_CONTAINER` runs several background workers inside one
  container (a Frappe worker pool). Coolify names every container, so it can't run copies of
  the worker container and stopped with *container name must be unique*; set
  `QUEUE_WORKERS=1` and `WORKERS_PER_CONTAINER` to the workers you want
- **`./resdesk.sh coolify`** moves an install into Coolify: `list` finds Research Desk's
  containers on the server, `import FILE` loads an export into them (the address comes from
  Coolify's `BASE_URL`), `export` makes one, `bench ...` runs a bench command on the site. No
  `.env` needed: it reads the settings from the containers
- Installation guide: Coolify step by step (variables, domain and port, redeploying, what
  doesn't apply there)

## 0.12.1 (2026-10-01): no migrate when nothing needs it

- **Starts, restarts and upgrades skip the database migrate when the code hasn't changed what
  it acts on** (Frappe or Research Desk version, DocTypes and other definitions, patches,
  `hooks.py`, the setup code). Before, every start ran a full `bench migrate` next to the
  running portal and workers. A fingerprint of that code is recorded in the database by each
  migrate; the check takes a fraction of a second. `./resdesk.sh migrate` or
  `FORCE_MIGRATE=1` still migrate on demand
- Migrates no longer queue Frappe's website search index (the portal uses Meilisearch)
- Start-up saves the public address to Settings only when `BASE_URL` changed, instead of on
  every start

## 0.12.0 (2026-10-01): a portal page for every archive.org collection

- **Every archive.org collection your books belong to gets a portal collection**, sub-collections
  included (for Servants of Knowledge: *Karnataka Archaeology*, *Karnataka Tulu Sahitya
  Academy* and the rest), named and described as on archive.org and kept in step as books come
  and go. Sub-collections are shown on their parent's page; the Collections page lists the top
  level. Settings → Collections from archive.org: on by default, a smallest size, and
  collections to skip; archive.org's general groupings never get a page

## 0.11.2 (2026-10-01): quicker upgrades

- **Upgrades reuse Frappe** when it hasn't changed: Frappe and its Python and Node packages are
  built again only when a newer Frappe v16 *release* is out (before, any new commit on Frappe's
  branch did it, 10 minutes or more). On Docker the image is split so that an upgrade of
  Research Desk alone rebuilds a few MB instead of copying the whole 1 GB Frappe bench again
  (about a minute instead of several, and 1 GB less disk each time). Native upgrades skip
  reinstalling packages and rebuild only Research Desk's assets when Frappe didn't change
- **Portal collections for archive.org profiles** appear straight after upgrading and as soon
  as *Portal Collection for It* is ticked, instead of only after the profile's next run

## 0.11.1 (2026-10-01): moving from a Mac

- `./resdesk.sh move-to` works with the bash that comes with macOS (it stopped with
  "HOST…: unbound variable"); a test keeps the scripts that way
- README and guides cover keeping in step with archive.org, the book limit and the Server page

## 0.11.0 (2026-10-02): look after the server from the Desk

- **Server page** in the Desk (Research Desk → Server): Research Desk and Frappe versions and
  whether a newer release is out, with its release notes; the health of every part (database,
  cache, workers, scheduler, search engine, disk, backups, errors); backups; recent errors,
  failed jobs and log files; alerts; resources
- **Upgrade from the Desk** with the optional **updater helper** (`./resdesk.sh updater on`):
  a System Manager upgrades to the latest release or goes back to an earlier one, restarts a
  part (portal, workers, scheduler, search engine or everything), applies a resource preset,
  backs up on the server and reads each part's logs, and watches the output live. The helper
  runs only those commands (`./upgrade.sh`, `./resdesk.sh`, `docker compose restart/logs`),
  with checked arguments and a secret token; it is off unless turned on, and Settings can
  switch the Desk buttons off. Every request is kept as an RD Server Task with its log
- **Automatic backups**: every night by default (Settings → Server & Updates: daily, weekly or
  off, how many to keep, with or without uploaded files); make, list, download and delete
  backups on the Server page
- **Alerts** to managers when a part stops working (and when it recovers), the disk is nearly
  full, a backup or upgrade fails, or a new release is out: Desk notifications, email and a
  webhook (Slack, Mattermost, Discord). `sok_resdesk.server.ping` for uptime monitors
- **Book limit**: how many books this machine can hold, worked out from its CPUs, memory and
  free disk (counted in pages, so thick books use more), or a number chosen in Settings, or no
  limit. At the limit, ingests keep updating existing books but add no new ones; managers get an
  alert at 90% and at 100%; the Server page and Check Count show the room left
- **Keep in step with archive.org**: after its first run, a profile brings in the books added
  to its archive.org collection (or search) since the last run, refreshes the ones that changed
  and unpublishes the ones taken out or made dark (they come back if they return), daily or on
  its schedule. It asks archive.org only for what changed. If many books seem to vanish at once,
  nothing is unpublished and managers are alerted. On by default; existing profiles start from
  their last completed run. **Sync with archive.org** on the profile does it now
- **Portal collections that mirror archive.org**: a profile for an archive.org collection keeps a
  portal collection of the same name (title and description from archive.org) with exactly its
  books
- Daily **update check** for new Research Desk releases and Frappe patches
- Upgrades on Docker now really bring Frappe's newest v16 patch release (the Frappe part of the
  image is rebuilt when a new patch is out; `--no-frappe` keeps it). The first upgrade to
  0.11 rebuilds it, which takes 10 minutes or more
- `./upgrade.sh` runs from a copy of itself (it replaces its own file), keeps going when
  GitHub can't be reached, and says so when going back to an earlier release
- Upgrades no longer fail when the workers write to Settings at the moment the search-engine
  status is saved (MariaDB "Record has changed", error 1020): it retries, and saving the public
  address after migrating can't stop an upgrade any more
- Collection rules left behind by a deleted collection no longer stop new books from coming in
- Book folders and logs are no longer sent to Docker when the image is built
- `COMPOSE_PROFILES` keeps both the monitor and the updater when either is turned on or off

## 0.10.1 (2026-09-30): gentler workers by default, more tests, formatted code

- Background workers now run at the **lowest priority (nice 19) by default** on every preset, and
  that is the level they really get: Frappe's own +10 for workers no longer adds on top. To let
  them work harder, `./resdesk.sh resources set WORKER_NICE=10` (0 = normal). `WORKER_NICE`
  replaces `QUEUE_NICE`, which is no longer used
- More integration tests (`tests/test_operations.py`): pushing, dry runs, pause and resume,
  cancel, Pause All, quiet hours, the getting-started checklist, resource presets and portable
  folder paths. CI also checks the worker priority and moves the install (export, import back)
- Code formatted with `ruff format`, checked in CI
- Errors while pausing or cancelling a queued push are written to the Error Log instead of being
  hidden

## 0.10.0 (2026-09-30): keep the machine usable, move in one file, logo in the Desk

- **Resource presets**: `./resdesk.sh resources light|standard|server` caps the background
  workers, the search engine and the database (CPU, memory, number of parallel jobs,
  search-indexing threads and memory, database cache); `./resdesk.sh resources set KEY=VALUE`
  fine-tunes one cap; `./resdesk.sh resources` shows the caps and what each part uses now
- Background workers run at **low CPU and disk priority**, so the portal and Desk stay quick
- **Quiet hours** (Settings → Machine Resources): pause all background work between set times
  (optionally weekdays only) and carry on afterwards
- **Background Jobs → Machine**: CPU load, memory, disk, search-index size, the caps in force,
  quiet hours, and choosing a preset; CPU and memory per part with the optional read-only
  monitor (`./resdesk.sh resources monitor on`)
- **Moving**: `./resdesk.sh export` makes one file with the catalogue, users, settings, files,
  page text and the key to saved passwords; `./resdesk.sh import FILE` loads it into a new
  install, Docker or native, and rebuilds search without downloading; `./resdesk.sh move-to
  user@host --with-library` does it all over SSH. Guide: [Moving to another server](docs/moving.md)
- Book folders are stored as `/library-source/…` on every install (a patch converts native
  installs), so catalogues move between servers and between Docker and native;
  `bench resdesk relink-folders` points books at a new folder
- **Logo in the Desk**: the library's icon (or logo) in the Desk sidebar and on the apps screen,
  with a Research Desk mark as the default; a new square **Icon** setting for small places

## 0.9.0 (2026-09-30): help on every screen, and docs that keep up

- **Help inside the app**, made from the same `docs/*.md` files as on GitHub, with pictures:
  - Portal: **Help** in the top bar (`/library/help`) with a new reader guide, searching and citing
  - Desk: **Help** page (`/app/resdesk-help`) with every guide, and a **Help** menu on every
    Research Desk screen that opens the right section
- **Take the tour** on the main forms (ingest profile, collection, book, settings, export,
  spreadsheet import, push target): Frappe form tours, one field at a time
- **Getting-started checklist** at the top of the Research Desk workspace for managers: six steps
  from an empty install to a working portal; steps tick themselves as the library does them
- **First-visit tips** for readers on the portal home page
- New guides: [Using the library](docs/reader-guide.md) and
  [Staff guide: a tour of the Desk](docs/staff-guide.md); every setting and command now has a
  reference in [Operations](docs/operations.md)
- Docs are checked on every change (`sok_resdesk/tests/test_docs.py`, in CI): APIs, DocTypes,
  settings, commands, links, help buttons, tours and pictures must all match the code
- `./resdesk.sh docs` refreshes the generated settings and command reference;
  `./resdesk.sh screenshots` retakes the pictures; `scripts/release.sh X.Y.Z` refuses to tag
  without a changelog entry

## 0.8.0 (2026-09-30): pause and resume background work

- **Pause / Resume** for ingest runs and metadata push runs, on Background Jobs and on each run's
  form. Waiting batches leave the queue, running ones stop after the current book, and the books
  not yet done are kept on the run; Resume carries on with exactly those (nothing twice, nothing
  skipped). A paused scheduled profile doesn't start a second run
- **Pause All / Resume All**: pauses every run, holds every waiting job, pauses schedules and
  makes new jobs wait; Resume All puts everything back, schedules as they were
- **Hold** a single waiting job (re-index batch, export, bulk change) and **Release** or
  **Discard** it later from the new *Held jobs* section
- Background Jobs also lists **metadata pushes in progress** with progress and controls
- Stop Everything now also cancels paused runs and discards held jobs
- `./resdesk.sh jobs --pause-run RUN | --resume-run RUN | --pause-all | --resume-all`

## 0.7.0 (2026-09-30): collections, metadata exports and pushing to other systems

After upgrading, run `./resdesk.sh reindex --background` once so the new Collection and
Document Type filters work in search (the portal keeps working while it runs).

- **Curated collections** (Research Desk → Collections): your own groupings of books, with a
  portal page each (`/library/collection/<address>`), a `/library/collections` listing,
  featured collections on the home page, and an OAI-PMH set `rd:<address>`. Add books from the
  Items list (selected or all matching), from a portal search, on the book form, by spreadsheet,
  or with **rules** (source collection, subject, language, creator, source, profile or document
  type; "is exactly" or "contains") that also catch newly ingested books
- The archive.org collections field is now called **Source Collections**
- **Document Type** per book (Book, Periodical, Article, Thesis, Report, Manuscript, Map,
  Other), guessed at ingest; a search filter, and used for BibTeX/RIS/CSL citation types
- **Keep My Edits**: details corrected by staff (form or spreadsheet) are no longer overwritten
  when a book is re-ingested
- **Metadata exports** (Research Desk → Exports): Spreadsheet (CSV/Excel), JSON, JSON Lines,
  Dublin Core, MODS 3.7, MARCXML, JSON-LD, CSL-JSON, BibTeX, RIS, Internet Archive bulk-upload
  CSV and IA `meta.xml` files; for everything, a collection, a profile, a source collection, a
  search, the Items list filter or selected books; big exports run in the background
- **Spreadsheet import** (Research Desk → Spreadsheet Imports): edit an exported spreadsheet and
  import it back, with a preview of every change and problem before anything is applied; can
  create records for new IDs
- **Push Targets** (Research Desk → Push Targets): send metadata to the **Internet Archive**
  (update your items' metadata), **Koha** (create/update biblios over the REST API, Koha 23.11+),
  **Wikidata** (complete or create edition items, paced for bot rules) or any **webhook**
  (signed JSON). Dry run by default, per-run logs, only changed books are sent, and optional
  automatic pushes when a book is edited
- Background Jobs lists export, import, collection and push jobs; Stop Everything also stops push runs
- New docs page: [Collections, metadata & pushing](docs/collections-and-metadata.md)

## 0.6.0 (2026-09-30): take control of background work

- New Desk page **Background Jobs** (`/app/resdesk-jobs`, on the Research Desk workspace):
  active ingest runs with progress, every queued or running Research Desk job (ingest batches,
  re-index batches, visibility changes), scheduled profiles, search-engine indexing tasks and
  recent runs; refreshes every 5 seconds
- Controls: **Stop** a run (after the current book) or **Stop now**, cancel single jobs,
  **Pause / Resume Schedules**, cancel pending search indexing, and **Stop Everything**
- Stopping a run now also removes its queued batches (before, they still started and exited)
- Re-index batches stop when "Stop Everything" is used; a new rebuild clears that
- *Pause Scheduled Ingests* setting; scheduled profiles don't start while it is on
- `./resdesk.sh jobs` (`--stop RUN`, `--stop-all`, `--now`, `--pause`, `--resume`)

## 0.5.3 (2026-09-30): recover from a full Docker disk

- The configurator recreates `common_site_config.json` when it is empty or damaged (a full
  Docker disk can truncate it, after which every bench command fails)
- Meilisearch upgrades its index files in place (`MEILI_UPGRADE_DB`) when a newer patch
  release of the image is pulled, instead of refusing to start
- `./upgrade.sh` checks Docker's free disk space before building and stops with instructions
  when less than about 6 GB is left

## 0.5.2 (2026-09-30): upgrade fixes

- `./upgrade.sh` no longer waits forever at "Restart and migrate" when the configurator
  container keeps failing (usually Docker out of disk space): it stops after three restarts, or
  after 10 minutes, and shows each container's state, its last log lines and how to free space
- Old image layers from previous builds are removed after each upgrade build, so repeated
  upgrades don't fill Docker's disk. Data volumes are never touched

## 0.5.1 (2026-09-30): upgrade fixes

- `./upgrade.sh` no longer hangs silently at the backup step: the backup needs only the
  database, so it works even when the web containers won't start (it uses a one-off container),
  shows its progress, and stops with the reason and a `--no-backup` hint if it can't finish
- When Docker can't start the containers, or the migration container never starts, the upgrade
  stops within two minutes and prints each container's state and last log lines, instead of
  waiting 15 minutes
- `./resdesk.sh backup` uses the same approach

## 0.5.0 (2026-09-30): members-only books and reader accounts

- Each book has **Who can see it**: *Public*, *Login to read* (find and cite openly; reading,
  search inside and the PDF need a login) or *Login to find* (only logged-in readers know it
  exists). Enforced in portal search, book pages, page search, search inside, local PDFs,
  citations, MARCXML, stats and OAI-PMH
- Site setting for visitors who are not logged in: *Each item's setting*, *Records only*
  (a public catalogue) or *Login required* (an internal library)
- Reader accounts: *Admins add readers*, *Anyone can sign up* or *Sign up, admin approves*
  with a **Reader Requests** queue, bulk approve/reject, manager notifications and emails.
  New role **ResDesk Reader** (portal only); `./resdesk.sh add-reader EMAIL`
- Bulk changes: ticked rows or everything matching a filter in the Desk Items list, every
  result of a portal search (staff bar), a whole ingest profile, or
  `./resdesk.sh access <visibility> --collection/--profile/--language/--ids/--all`.
  Updates the search index in place, no re-index; big batches run in the background
- **Access rules** by collection, subject, language, author, source or profile set the
  visibility of new books; an ingest profile's own setting comes first; **Apply Access Rules**
  updates existing books without touching manual choices. `ingest --visibility` on the CLI
- OAI-PMH shares what guests can find by default, or all published records, or is off
- Upgrade note: existing books become *Public*; nothing needs re-indexing

## 0.4.0 (2026-09-29): native install and upgrades

- `./install.sh --native` (or choose at the prompt): installs MariaDB, Redis, Meilisearch,
  Python 3.14 (uv), Node 24 (nvm) and a Frappe v16 bench linked to the checkout, on macOS
  (Homebrew) or Ubuntu/Debian (apt). Idempotent; tested on a clean Ubuntu 24.04
- Native runtime: gunicorn with static files and default-site routing
  (`sok_resdesk.native_wsgi`), Meilisearch and extra workers in the bench Procfile;
  `./resdesk.sh` start/stop/status/logs/workers/backup/restore/dev/uninstall work natively
- `./upgrade.sh`: check, backup, fetch a release/tag/main, update Frappe patch releases,
  migrate, re-apply index settings, restart, health check, rollback instructions, logs
- The installer asks for the book folder (`LIBRARY_DIR`); `/library-source` maps to it natively
- The Research Desk workspace ships as an app file, so migrations no longer recreate it

## 0.3.0 (2026-09-29): your own folders and servers, logo

- New ingest source **Folder or Server**: IA-style item folders on a local disk, USB/NAS mount
  (`LIBRARY_DIR` → `/library-source`, read-only) or a web server (directory listing or an
  item-list file)
- Page text from `_hocr_searchtext` + page index, `_hocr.html`, `_chocr.html.gz`, `_djvu.xml`,
  or `_djvu.txt` (as numbered sections)
- Each book checked against archive.org: IA reader when it's there, otherwise the book's own PDF
  (streamed with range requests; only PDF and cover are ever served)
- Drop-folder mode: Hourly schedule; new and changed items (by file signature) are ingested,
  unchanged ones skipped
- CLI: `count/ingest --folder`, `--server`, `--manifest`
- **Logo & Branding** in RD Settings: logo on the home page, the portal top bar and the Desk;
  favicon; home-page background image
- Prefix search kept on for page text (Kannada suffixes), more language codes

## 0.2.0 (2026-09-29): scaling and developer mode

- Parallel ingest: runs are planned, split into batches and processed by several queue workers
  (`QUEUE_WORKERS`, `./resdesk.sh workers N`); atomic progress counters; conflict retries;
  Cancel Run; hourly detection of interrupted runs
- `resdesk ingest --background`, `resdesk progress`, `resdesk reindex --background --reset`
- Local compressed page-text cache: re-indexing no longer downloads from archive.org
- Page index tuned for millions of pages (slim documents, byAttribute proximity, no prefix
  search, search cutoff); titles joined from the books index at query time
- Measured scaling guide for 50,000 books (docs/scaling.md)
- Docker developer mode (`./resdesk.sh dev on`): code runs live from the checkout
- Compose project name pinned (`sok-resdesk`), so data volumes are kept whatever the folder is called

## 0.1.0 (2026-09-29): proof of concept

- Frappe v16 app `sok_resdesk` with DocTypes RD Item, RD Creator, RD Subject,
  RD Ingest Profile, RD Ingest Run, RD Settings
- Internet Archive ingest by collection / query / identifier list, with counting, limits,
  scheduling and a command-line interface
- Metadata normalisation for IA records (languages, years, creators, subjects, romanised forms)
- Meilisearch indexes for books and for the OCR text of every page
- Public portal `/library`: faceted search, full-text page search, book pages with the IA reader,
  search inside a book, reading lists
- Citations: BibTeX, BibLaTeX, RIS, CSL-JSON, APA, MLA, Chicago; Highwire tags, JSON-LD, COinS
- OAI-PMH 2.0 provider (oai_dc, marc21) and MARCXML export for Koha
- `install.sh` one-command Docker install, `resdesk.sh` operations CLI, bench dev setup,
  CI running the real installer, multi-arch image publishing
