# Scaling to 50,000 books

Short answer: **yes, on one well-sized server.** The catalogue is small. The heavy parts are
the page-level search index (about 9 million pages for 50k books) and the time it takes to
fetch everything politely from the Internet Archive. Both scale predictably. The numbers
below are measured, not guessed.

## What we measured

Test: 300 books from the Servants of Knowledge collection (about half Kannada, half English),
ingested with full page text on a small 2-vCPU / 8 GB machine, Research Desk v0.2, Meilisearch 1.54.

| Measure | Result |
|---|---|
| Pages per book (average) | **184** (55,115 pages for 300 books) |
| Ingest speed, 1 worker | ~800 to 900 books/hour (4 to 5 s per book, mostly waiting on archive.org) |
| Ingest speed, 4 workers | **~3,000 books/hour** while all four were busy; 0 failures |
| Page index on disk (Meilisearch, used) | **~16 KB per page** |
| Book index on disk | ~95 KB per book |
| Local page-text cache | ~75 KB per book (compressed) |
| MariaDB catalogue | ~10 KB per book |
| Search latency at 55k pages | 7 to 32 ms (page search), <10 ms (book search) |
| Meilisearch memory at 55k pages | ~600 MB |

Page text is OCR, so it contains a lot of noise words (about 19% of tokens were unique in the
sample). That's why the page index is several times larger than the raw text. Tuning
(`proximityPrecision: byAttribute`, slim page documents, no facet search on pages) is already
applied. Prefix search is deliberately kept on: Kannada words carry suffixes, so `ಕನಕ` must
find `ಕನಕದಾಸರ`. Turning it off saved only about 7%. Further tricks, such as grouping pages or dropping filters, saved under 10% in tests,
so they aren't worth losing features for.

## Projection for 50,000 books

| | Estimate |
|---|---|
| Pages | ~9.2 million |
| Page index | **~150 GB** (allow 250 GB: the index file grows beyond its used size during indexing) |
| Book index | ~5 GB |
| Page-text cache | ~4 GB |
| MariaDB | <1 GB |
| First full ingest, 4 workers | **~17 to 23 hours** of wall-clock time |
| First full ingest, 6 workers | ~12 to 16 hours (the most we'd suggest against archive.org) |
| Rebuilding the index from the cache (no archive.org calls) | a few hours, limited by CPU |

Search latency will be higher than at 55k pages. Very broad queries are capped at 1.5 s
(`searchCutoffMs`) and return their best matches. Typical specific queries should stay well
under a second on the hardware below. Measure on your own server before a public launch.

## Recommended server for 50k books

| | Minimum | Comfortable |
|---|---|---|
| CPU | 4 vCPU | 8 vCPU |
| Memory | 16 GB | 32 GB |
| Disk | 300 GB SSD | 500 GB NVMe |
| Workers | `QUEUE_WORKERS=4` | `QUEUE_WORKERS=6` |

Research Desk applies these numbers itself: the **book limit** (Settings → Machine Resources)
stops adding new books when the machine is full, and the Server page shows how many books its
CPUs, memory and disk can each hold ([Book limit](server.md#book-limit)).

A laptop is fine for a few thousand books; for 50k use a server (or at least an external SSD
for Docker's data). Meilisearch reads its index through memory-mapped files, so more RAM means
more of the index stays in memory and search is faster.

## How to run a 50k ingest

1. **Size the machine** (above) and set in `.env`:

   ```
   QUEUE_WORKERS=4
   ```

   then `./install.sh` (or `./resdesk.sh workers 4`).

2. **Check what you're about to ingest:**

   ```bash
   ./resdesk.sh count --collection ServantsOfKnowledge --filter "language:(kan OR Kannada OR Kan)"
   ```

3. **Start it in the background**, split across the workers:

   ```bash
   ./resdesk.sh ingest --collection ServantsOfKnowledge --limit 50000 --background --name "SOK 50k"
   ```

   Or in the Desk: an Ingest Profile with *Maximum Items* 50000 → **Run Ingest**. Large runs
   are always split into batches (RD Settings → *Books per Background Batch*, default 50).

4. **Watch progress** from anywhere: `./resdesk.sh progress`, or the RD Ingest Run page (with a
   progress bar and a **Cancel Run** button). The portal is usable throughout; books appear
   as they're indexed.

5. **If something stops** (a reboot, a Docker restart, an upgrade), the run is marked
   *Interrupted* within about 15 minutes and carries on by itself, skipping the books already
   done. **Carry On** on the run does the same at once. Batches go into the queue a few at a
   time, so even a 50,000-book run never fills the queue.

Tip: ingest in slices you can reason about (for example by language or partner collection:
`KannadaUniversity`, `Vishwakonkani`, …). Each slice becomes its own profile you can re-run or
schedule.

## Re-indexing without archive.org

Every book's page text is kept in a compressed local cache (`sites/<site>/private/resdesk-pages/`,
included in `./resdesk.sh backup --with-files`). Rebuilding the search index uses it:

```bash
./resdesk.sh reindex --background          # all workers, cache first
./resdesk.sh reindex --reset --background  # drop and rebuild the page index (after upgrades)
```

## Beyond 50k

The code doesn't assume a size; these are the next levers, in order:

1. **Put Meilisearch on its own machine**: set *Meilisearch URL* in RD Settings.
2. **More web capacity**: raise `GUNICORN_WORKERS`, or run several `backend` containers
   behind a load balancer.
3. **Switch the page index to OpenSearch** (on the roadmap). Its compressed inverted
   indexes and sharding across nodes are the usual choice at hundreds of millions of pages.
   The search adapter (`sok_resdesk/search.py`) is the only code that changes; the portal,
   API, OAI-PMH and citations stay the same.
