# Choosing & ingesting books

> Books in IA-style folders on your own disk, NAS or web server? See
> [Books from your own folders or servers](local-folders.md). This page covers archive.org.

Research Desk never tries to copy "everything". You decide what comes in, using an
**Ingest Profile**: a saved description of a set of items on archive.org. That keeps a
proof of concept small and lets a large library grow its collection step by step.

## Ingest profiles

Desk → Research Desk → **Ingest Profiles**.

| Field | Meaning |
|---|---|
| **Choose By** | *Collection*, *Search Query* or *Identifier List* |
| **IA Collection** | the collection's identifier: the part after `archive.org/details/` |
| **Narrow With** | optional archive.org search terms added to the collection |
| **IA Search Query** | any archive.org advanced-search query |
| **Identifiers** | one archive.org identifier per line |
| **Maximum Items** | stop after this many items (`0` = no limit). Start with 50 to 500. |
| **Fetch Full Text** | download page-level OCR text for full-text search (recommended) |
| **Refresh Items Already in Catalogue** | re-fetch items you already have (to pick up corrected metadata) |
| **Schedule** | *Manual*, *Daily* or *Weekly*. Scheduled runs only fetch items that are new. |

Buttons: **Check Count** (how many items match right now), **Run Ingest** (starts a
background job and opens its progress page), **Items from this Profile**, **Run History**.

Research Desk only asks for `mediatype:texts`, so audio, video and collection records are skipped.

Two starter profiles are created on install: *SoK Kannada sample* and *SoK English sample*.

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
./resdesk.sh ingest --profile "SoK Kannada sample" --limit 20

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

Every ingest is planned first: the list of identifiers is fetched, books already in the
catalogue are skipped, and the rest are split into batches (**RD Settings → Books per
Background Batch**, default 50). Each batch is a background job. With `QUEUE_WORKERS=4`, four
batches run at once. The RD Ingest Run page shows batches remaining and has a **Cancel Run**
button. A run whose workers disappear (reboot, restart) is marked **Interrupted** after two
hours without progress; run the profile again and it picks up where it stopped.

For tens of thousands of books, read [Scaling to 50,000 books](scaling.md).

## Watching and stopping runs

Each run's page shows progress and has **Stop** / **Stop Now**. Desk → Research Desk →
**Background Jobs** shows every run, queued batch and scheduled profile in one place, with a
**Stop Everything** button. See [Operations → Background jobs](operations.md#background-jobs-see-and-stop-what-is-running).

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

## Scheduling

Set a profile's **Schedule** to *Daily* or *Weekly*. The scheduler container then queues a
run that only picks up items not yet in the catalogue. That keeps a portal in step with
ongoing digitisation automatically.
