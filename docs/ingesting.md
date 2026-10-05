# Choosing & ingesting books

> Books in IA-style folders on your own disk, NAS or web server? See
> [Books from your own folders or servers](local-folders.md). From a DSpace, EPrints or other
> OAI-PMH repository? See [Books from repositories](repositories.md). This page covers archive.org.

Research Desk never tries to copy "everything". You decide what comes in, using an
**Ingest Profile**: a saved description of a set of items on archive.org. That keeps a
proof of concept small and lets a large library grow its collection step by step.

## Ingest profiles

Desk → Research Desk → **Ingest Profiles**.

| Field | Meaning |
|---|---|
| **Choose By** | *Collection*, *Search Query*, *Identifier List* or *Metadata File* ([below](#importing-a-metadata-file-the-fastest-way)) |
| **IA Collection** | the collection's identifier: the part after `archive.org/details/` |
| **Narrow With** | optional archive.org search terms added to the collection |
| **IA Search Query** | any archive.org advanced-search query |
| **Identifiers** | one archive.org identifier per line (or separated by commas or spaces); any number: a list of 80,000 is taken as the run's books, its catalogue records fetched 100 at a time. A list is never kept in step with archive.org |
| **Maximum Items** | stop after this many items (`0` = no limit). Start with 50 to 500. |
| **Fetch Full Text** | download page-level OCR text for full-text search (recommended) |
| **Refresh Items Already in Catalogue** | re-fetch items you already have (to pick up corrected metadata) |
| **Schedule** | *Manual*, *Hourly*, *Daily* or *Weekly*. Scheduled runs only fetch what changed ([below](#keeping-in-step-with-archiveorg)). |
| **Keep in Step with archive.org** | after the first run, bring in new books, update changed ones and unpublish removed ones, every day or on the schedule (on by default) |
| **Portal Collection for It** | keep a portal collection page with this archive.org collection's books (on by default for *Collection*) |

Buttons: **Check Count** (how many items match right now, and whether they fit under the
[book limit](server.md#book-limit)), **Run Ingest** (starts a background job and opens its
progress page), **Sync with archive.org** (bring in what changed since the last run),
**Portal Collection**, **Items from this Profile**, **Run History**.

Research Desk only asks for `mediatype:texts`, so audio, video and collection records are skipped.

Two starter profiles are created on install: *SOK Kannada sample* and *SOK English sample*.

## Servants of Knowledge sub-collections

The [ServantsOfKnowledge](https://archive.org/details/ServantsOfKnowledge) collection had
about 88,000 items in September 2026. Many items also belong to partner collections, which
make natural ingest profiles:

| Collection id | Items (approx.) | Collection id | Items (approx.) |
|---|---|---|---|
| `Vishwakonkani` | 4,700 | `MalayalamHeritage` | 280 |
| `Sochara` | 4,600 | `TuluSahityaAcademy` | 270 |
| `KannadaUniversity` | 4,200 | `ArebhasheSamskruthiSahityaAcademy` | 260 |
| `AzimPremjiUniversity` | 3,700 | `Ramakrishna` | 240 |
| `karnatakasanskrituniversity` | 1,400 | `GandhiBhavan` | 230 |
| `bmshri` | 1,350 | `KarnatakaArchaeology` | 190 |
| `RojaMuthiah` | 1,300 | `IndiaHistory` | 140 |
| `LalbaghBotanicalGarden` | 800 | `IndiaScience` | 110 |
| `digitallibraryindia` | 690 | `IndiaTribal` | 110 |
| `RBANMS` | 600 | `kerala-archives` | 115 |

Counts change as digitisation continues. Use **Check Count** for the current number.

## archive.org search syntax (for "Narrow With" and "Search Query")

| You want | Write |
|---|---|
| Kannada books (IA spells the language several ways) | `language:(kan OR Kannada OR Kan)` |
| English books | `language:(eng OR English)` |
| Published 1900 to 1950 | `date:[1900-01-01 TO 1950-12-31]` |
| A subject word | `subject:vachana` |
| A word in the title | `title:(ramayana)` |
| An author | `creator:(Kuvempu)` |
| Two collections | `collection:(KannadaUniversity OR bmshri)` |
| Exclude something | `-subject:magazine` |
| Added to IA recently | `addeddate:[2026-01-01 TO null]` |

Combine with `AND` / `OR` and brackets. Try the same query on
<https://archive.org/advancedsearch.php> to preview results.

## From the terminal

```bash
# how many?
./resdesk.sh count --collection ServantsOfKnowledge --filter "language:kan AND date:[1900-01-01 TO 1950-12-31]"

# ingest (saves a profile called "Command line ingest" unless you pass --name)
./resdesk.sh ingest --collection ServantsOfKnowledge --filter "language:kan" --limit 200 --name "Kannada 200"
./resdesk.sh ingest --query 'collection:ServantsOfKnowledge AND subject:vachana' --limit 100
./resdesk.sh ingest --ids "1857rasipayidhan0000srik,1909kannadaeleme0000kran"
./resdesk.sh ingest --ids-file my-list.txt          # the file must be inside the container; see below
./resdesk.sh ingest --profile "SOK Kannada sample" --limit 20

# options
--no-fulltext   metadata only (much faster; no search inside books)
--update        refresh items you already have
--limit 0       everything that matches
```

Terminal ingests run in the foreground and print one line per book. Add `--background` to
split a large run across the queue workers instead, and follow it with
`./resdesk.sh progress`. Ingests started from the Desk always run in the background. On a developer
(bench) setup, the same commands are `bench --site <site> resdesk ingest ...`.

> For `--ids-file` with Docker, copy the file in first:
> `docker compose cp my-list.txt backend:/tmp/` then `--ids-file /tmp/my-list.txt`.

## Catalogue first, details later

A big collection is on the portal within minutes, not days. When a run starts, it asks
archive.org's search for every matching book **with its catalogue fields** (title, authors,
date, language, subjects, description, collections, page count, formats), up to 5,000 books per
request, as the `ia search -f …` command-line tool does: 88,000 books take about 18 requests
instead of 88,000. Every new book is catalogued from that record and sent to search straight
away, 500 at a time (the run's log counts them), marked **Details Still Coming**.

In the background (the Desk's **Run Ingest**, or `--background`), the first pass itself is split
into parts of 500 books that run on **every queue worker at once**, queued ahead of the batches:
with four workers, four parts are catalogued together. Each part logs one line ("first pass part
12: 500 books catalogued"). Paused or stopped, the parts still waiting are dropped: their books
come in through their own batches.

Then the batches do the slow part in the background, book by book as below: the full record and
file list from the metadata API, the page text, page images matched by scan data. As each book
is done its mark goes and its text becomes searchable. A run stopped in between carries on
where it was: books still marked are fetched again, never skipped.

It is on for every archive.org profile (**Catalogue First, Details Later**); untick it to go
book by book as before. If archive.org refuses some of the fields, the run asks for the core
ones; if that fails too, it lists identifiers only and works book by book.

## Importing a metadata file (the fastest way)

When the metadata of a whole collection is already in a file, nothing needs to be asked of
archive.org to build the catalogue. Make the file with the `ia` command-line tool (`pip install
internetarchive`), on any computer:

```bash
# search records: quick to make (thousands of books a request), enough to catalogue
ia search "collection:ServantsOfKnowledge" \
   -f title -f creator -f date -f language -f subject -f description -f collection \
   -f publisher -f imagecount -f format -f licenseurl -f rights -f volume > sok.jsonl

# or full records, with each book's file list: slower to make, but complete
ia search "collection:ServantsOfKnowledge" --itemlist | xargs -n1 ia metadata > sok-full.jsonl

gzip sok.jsonl          # optional: files may be gzip-compressed
```

Then an ingest profile with **Choose By** = *Metadata File*: upload the file (up to 100 MB; raise it in **Settings → Machine Resources → Largest
Upload**) under **Metadata File**, or, for a big one, put it in the library folder (`LIBRARY_DIR` in `.env`) and give its
path under **Or a File on the Server** (`/library-source/sok.jsonl.gz`). **Count** says how many
records it holds; **Start** catalogues them all and sends them to search, 500 at a time, without
a single request to archive.org. From the terminal:

```bash
./resdesk.sh count  --metadata-file /library-source/sok.jsonl.gz
./resdesk.sh ingest --metadata-file /library-source/sok.jsonl.gz --limit 0 --background
```

Files it reads: JSON Lines from `ia search` or `ia metadata` (or a JSON array of them), a CSV or
TSV with an `identifier` column (IA's `subject[0]`, `subject[1]` columns are joined; several
values in a cell split on `;` or `|`), or a plain list of identifiers. Lines it can't read are
counted in the run's log and left out.

What happens next depends on the records and on **Fetch Full Text**:

| Records | Fetch Full Text off | Fetch Full Text on |
|---|---|---|
| full (`ia metadata`, with file lists) | done: no request at all | page text fetched in the background |
| search records (`ia search`) | full record fetched in the background (one request a book) | full record and page text in the background |
| identifiers only | each book fetched as usual | each book fetched as usual |

A file doesn't change on archive.org, so such profiles are not kept in step with it (use a
collection profile for that).

## What happens to each book

1. **Metadata** from `archive.org/metadata/<id>` is normalised:
   - languages to ISO 639-3 (`Kan`, `kan`, `Kannada`, `KAN` → `kan` / Kannada)
   - dates to a year, authors and subjects split on `;`
   - IA's per-user "favourites" collections (`fav-*`) dropped
   - romanised titles and author names (`alt_title`, `alt_creator`) kept alongside the
     original script
2. An **RD Item** is created or updated, with linked **RD Creator** and **RD Subject** records.
3. **Page text** comes from IA's OCR files (`_hocr_searchtext.txt.gz` and
   `_hocr_pageindex.json.gz`): one searchable document per page. It is stored in the
   search index only, not in the database.
4. The book and its pages are **indexed** in Meilisearch.

Access-restricted (lending-library) items are catalogued, but their text is not fetched.

## Large ingests run in parallel

**More books at once: more workers.** Batches and first-pass parts run one per queue worker, so the
number of workers is how many books come in together. Set it in the Desk: **Settings → Machine
Resources → Parallel Workers** (1 to 16). Saving applies it through the updater helper (Server →
Tasks shows it); without the helper the Desk shows the command to run on the server,
`./resdesk.sh resources set QUEUE_WORKERS=6`. Cataloguing from a metadata file asks nothing of archive.org, so more workers only cost
this machine; page text does ask archive.org, and 4 to 6 workers stay polite.

Every ingest is planned first: the list of identifiers is fetched, books already in the
catalogue are skipped, and the rest are split into batches (**RD Settings → Books per
Background Batch**, default 50). Each batch is a background job. With `QUEUE_WORKERS=4`, four
batches run at once. The batches wait on the run and go into the queue a few at a time (twice
the number of workers), one more each time one finishes, so a run of 35,000 books doesn't fill
the queue or hold up other work. The RD Ingest Run page shows batches remaining.

Nothing is fetched twice:

- a profile has **one run at a time**: starting it again while a run is going (or paused) is
  refused and names that run
- a batch skips a book that any run has brought in since this run started, and a run that only
  takes new books skips those another run added meanwhile (*Skipped* on the run, and a line in
  its log)

**When the workers disappear** (an upgrade, a restart, a reboot, not enough memory), Research
Desk notices within about 15 minutes that none of the run's batches is queued or running any
more: the run is marked **Interrupted** and carries on by itself, listing its books again and
taking only those not done yet. It does that up to three times; after that it waits for
**Carry On**. A run with no progress for two hours is marked Interrupted too.
A run that ends *Completed with Errors* or *Failed* tries again by itself, 15 minutes after it
ended and up to twice (most failures are a busy moment at archive.org or a clash between two
workers), taking only the books that failed; after that it waits for **Retry**.

## When books or batches fail

Nothing is lost when something fails: try it again from the run, in the same run.

| The run says | What went wrong | Button on the run |
|---|---|---|
| **Completed with Errors** | some books failed one by one (the log says why: `FAIL <identifier>: …`); often archive.org was busy, or a book is dark or withdrawn | **Retry Failed Books**: takes exactly those books again |
| **Interrupted** | the workers stopped in the middle (an upgrade, a restart, a reboot, not enough memory); it usually carries on by itself | **Carry On**: lists the books again and takes those not done yet |
| **Failed** | it couldn't list the books (archive.org didn't answer, a folder was missing) | **Try Again**: lists the books again; those already done are skipped |
| **Cancelled** | someone stopped it | **Carry On**: lists the books again; those already done are skipped |
| *New Books Left Out* shown in red | the [book limit](server.md#book-limit) was reached, so new books were skipped | raise the limit in Settings → Machine Resources (or free disk space, or give Docker more), then **Carry On** |

The same is on **Background Jobs** (*Retry failed* / *Carry on* next to each recent run) and on
the **Server** page → Logs → **Failed jobs**, which lists every background job that failed
with its error: **Retry** one, **Retry all**, or **Clear the list**. Ingest batches retried there
go back into their run, which then finishes as usual. A book that still fails after a retry is
counted as failed again, with the new reason in the log.

For tens of thousands of books, read [Scaling to 50,000 books](scaling.md).

## Watching, pausing and stopping runs

Each run's page shows progress and has **Pause** and **Stop** / **Stop Now**. A paused run keeps
the books it hasn't done yet; **Resume** carries on with exactly those. Desk → Research Desk →
**Background Jobs** shows every run, queued batch and scheduled profile in one place, with
**Pause All** (carry on later with Resume All) and **Stop Everything**. See
[Operations → Background jobs](operations.md#background-jobs-see-pause-and-stop-what-is-running).

## Page-text cache

Each book's page text is also saved, compressed (about 75 KB per book), under
`sites/<site>/private/resdesk-pages/`. Re-indexing reads it instead of downloading from
archive.org again. Turn it off in RD Settings if disk is tight.

## Being polite to the Internet Archive

Requests go one at a time with a delay (**RD Settings → Delay Between Requests**, default
0.5 s), carry a User-Agent with your contact address, and back off automatically when IA is
busy. A book with page text takes 3 to 10 seconds per worker. We measured about **900 books/hour
with one worker and 3,000 books/hour with four**. Keep it to 4 to 6 workers. For the full 88k
collection, plan on a day or two, or ask the Internet Archive about bulk access.

## Keeping in step with archive.org

Collections on archive.org keep growing, and books in them get corrected, moved or taken down.
With **Keep in Step with archive.org** ticked (the default), a profile that has run once is kept
up to date by itself. Each day (or on the profile's *Schedule*, if it has one) Research Desk asks
archive.org only what changed since the last run ("In Step Up To" on the profile):

| On archive.org | In Research Desk |
|---|---|
| a book was **added** to the collection (or now matches the search) | it comes in, with its page text: all new books, whatever *Maximum Items* says (that limits the first run only), within the [book limit](server.md#book-limit) |
| a book's details or files **changed** (*Update Changed Books*) | it is refreshed; books with *Keep My Edits* keep your corrections |
| a book was **taken out** of the collection, or made dark (*Unpublish Removed Books*) | it is unpublished and marked *Removed from Its Source*; nothing is deleted, and it is published again if it comes back |

Removals are checked carefully: a book counts as gone only when archive.org confirms it (dark,
or no longer in the collection; for a *Search Query* profile, only dark books). If many of a
profile's books seem to vanish at once (more than 20, and more than a tenth), that looks like a
problem on archive.org's side: nothing is unpublished and managers get an alert.

**Portal collections.** Every archive.org collection your books belong to gets its own
collection page on the portal, named after it and with its description from archive.org: for
Servants of Knowledge books that is *Servants Of Knowledge* and its sub-collections such as
*Karnataka Archaeology* or *Karnataka Tulu Sahitya Academy*. Sub-collections are shown on the
page of the collection they belong to on archive.org, and the Collections page lists only the
top level. The pages appear as soon as there are books (after a run, after an upgrade, or when
the setting is switched on) and stay exactly in step: books join and leave with archive.org.

Settings → *Collections from archive.org*:

| Setting | |
|---|---|
| A Portal Collection for Every archive.org Collection | on by default. Off: only the collection of each profile that has *Portal Collection for It* ticked |
| Smallest Collection to Show | leave out archive.org collections with fewer of your books than this |
| Skip These archive.org Collections | identifiers that should not get a page, one per line |

archive.org's general groupings (such as *printdisabled*, *inlibrary* or *opensource*) and
people's favourites lists never get a page. Rename a page or give it a cover as you like; its
books follow archive.org, so for a hand-picked set make your own collection (books added by
hand to a mirrored one are removed at the next update). A page whose archive.org collection is
later skipped stays as it is: unpublish or delete it in the Desk.

**Sync with archive.org** on the profile does the same straight away. The run's log lists what
was new, changed, removed or back.

## Scheduling

Set a profile's **Schedule** to *Hourly*, *Daily* or *Weekly* to choose when it is kept in step;
profiles left on *Manual* are kept in step daily (untick *Keep in Step with archive.org* to only
run them by hand). Scheduled runs of a profile that isn't kept in step only pick up items not yet
in the catalogue.
