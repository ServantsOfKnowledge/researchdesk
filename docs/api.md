# HTTP API

All public endpoints are `GET` requests (some also accept `POST`), need no login, and only
return published records. Responses are JSON inside a `message` key unless noted. Guest
endpoints are rate-limited per IP.

What an anonymous caller gets also depends on [who can see what](access.md): books set to
*Login to find* are left out, *Login to read* books appear but without page text or PDF, and
with *Login required* guests get nothing. Send a logged-in reader's session cookie or an API
token (`Authorization: token <key>:<secret>`) to see everything that reader can.

Base: `<BASE_URL>/api/method/`

## Search

`sok_resdesk.api.search`

| Param | Default | |
|---|---|---|
| `q` | `""` | query text (any script) |
| `mode` | `books` | `books` or `pages` (full text inside books) |
| `filters` | `{}` | JSON, e.g. `{"language_label":["Kannada"],"decade":["1950s"],"year_from":1900,"year_to":1950}`. Facet keys: `curated` (your collections, by web address), `item_type` (Book, Periodical, Thesis…), `language_label`, `decade`, `subjects`, `creators`, `collections` (source collections on archive.org) |
| `page`, `per_page` | 1, 20 | `per_page` ≤ 100 |
| `sort` | relevance | `year:asc`, `year:desc`, `title_sort:asc` (books mode) |

```bash
curl -G "$BASE/api/method/sok_resdesk.api.search" \
  --data-urlencode 'q=ವಿಜಯನಗರ' -d mode=pages \
  --data-urlencode 'filters={"language_label":["Kannada"]}'
```

```json
{"message": {"query": "ವಿಜಯನಗರ", "mode": "pages", "page": 1, "total_pages": 12, "total": 232, "took_ms": 11,
  "facets": {"language_label": {"Kannada": 20}, "decade": {"1990s": 2, "2010s": 11}},
  "hits": [{"item_id": "damh.ivarukandavijaya0000msna", "title": "Ivaru Kanda Vijayanagara",
            "leaf": 13, "page_label": "10", "snippet": "<mark>ವಿಜಯನಗರ</mark>ವು ಭಾರತದ …",
            "url": "/library/item/damh.ivarukandavijaya0000msna?page=13"}]}}
```

Snippets contain `<mark>` tags only; escape everything else before inserting into HTML.

Each hit has `visibility` (`Public`, `Login to read` or `Login to find`). When the caller
may not search this way (inside the text, for a guest on a *Records only* site) the response
has `"login_needed": true` and no hits.

## Search inside one book

`sok_resdesk.api.search_inside?item_id=<id>&q=<text>[&limit=50]` returns
`{"total", "hits": [{"leaf", "page_label", "snippet"}]}`, sorted by page.
`leaf` is the 0-based page index used by the Internet Archive reader (`…/page/n<leaf>`).
For a book the caller may find but not read, it returns `{"login_needed": true, "hits": []}`.

## Records

`sok_resdesk.api.item?item_id=<id>` returns the full catalogue record (title, alt_title,
creators, alt_creators, year, language, publisher, subjects, collections, licence,
page_count, ark, source_url, portal_url, visibility, …). `can_read` says whether the caller
may read it; when false, `pdf_url` is empty.

`sok_resdesk.api.stats` returns counts of items, creators, full-text items, languages,
indexed pages and search-engine health.

`sok_resdesk.api.file?item_id=<id>&name=<file name>` streams the PDF or cover of a book that
lives in your own folders or on your book server (HTTP range requests supported). Only those
two files are ever served, and the PDF only when the caller may read the book.

## Citations (plain-text responses)

| Endpoint | Returns |
|---|---|
| `sok_resdesk.api.cite?item_id=<id>&format=<fmt>[&download=1]` | one record |
| `sok_resdesk.api.cite_many?item_ids=["a","b"]&format=<fmt>` | many records in one file (≤ 500) |

`fmt`: `bibtex`, `biblatex`, `ris`, `csl-json`, `apa`, `mla`, `chicago`.

## Library records

| Endpoint | Returns |
|---|---|
| `sok_resdesk.api.marcxml?item_ids=["a","b"]` | MARCXML collection (≤ 500) |
| `sok_resdesk.api.marcxml_all[?profile=<name>]` | whole catalogue or one profile (**login required**) |
| `sok_resdesk.oai.endpoint?verb=…` | OAI-PMH 2.0 (see [Koha](koha.md)) |

## Staff actions (login required)

| Endpoint | |
|---|---|
| `sok_resdesk.ingest.count_profile` (`profile`) | count matching IA items |
| `sok_resdesk.ingest.start_ingest` (`profile`) | queue a run, returns the run name |
| `sok_resdesk.ingest.refresh_item` (`item_id`) | re-fetch one item from IA |
| `sok_resdesk.search.reindex_item` (`item_id`) | re-index one item |
| `sok_resdesk.search.enqueue_rebuild` | rebuild the whole index in the background |
| `sok_resdesk.search.setup_indexes` | test the search engine and apply index settings |
| `sok_resdesk.access.bulk_set_visibility` (`visibility` and one of `names`, `filters`, `collection`, `profile`, `language`, `search`, `everything=1`) | set who can see many books; over 200 run in the background |
| `sok_resdesk.access.apply_rules` (`include_manual`) | re-apply profiles, access rules and the default |
| `sok_resdesk.access.apply_profile` (`profile`) | give a profile's books its visibility |
| `sok_resdesk.access.decide_requests` (`names`, `status`) | approve or reject reader requests |
| `sok_resdesk.jobs.overview` | active and paused runs (ingest and push), queued/running and held jobs, Pause All state, schedules, search-engine tasks |
| `sok_resdesk.jobs.pause_run` · `resume_run` (`run`: an ingest run or `PUSH-…`) | pause a run keeping its unfinished books; resume carries on with them |
| `sok_resdesk.jobs.pause_all` · `resume_all` | pause every run, hold waiting and new jobs, pause schedules; and undo it |
| `sok_resdesk.jobs.hold_job` (`job_id`) · `release_held` (`keys` JSON list or empty for all, `discard`) | keep one waiting job aside; put held jobs back or drop them |
| `sok_resdesk.jobs.choose_preset` (`preset`=`light`/`standard`/`server`) | record the resource preset; `./resdesk.sh resources apply` puts it into effect |
| `sok_resdesk.jobs.stop_run` (`run`, `force`) | stop one run and drop its queued batches |
| `sok_resdesk.jobs.stop_all` (`force`, `pause`, `search`) | stop all Research Desk background work |
| `sok_resdesk.jobs.cancel_job` (`job_id`) · `set_paused` (`paused`) · `cancel_search_tasks` | single job, schedules, search indexing |
| `sok_resdesk.curation.create` (`title`, `description`) | make a collection, returns its name (web address) |
| `sok_resdesk.curation.bulk` (`action`=`add`/`remove`, `collection`, and one of `names`, `filters`, `profile`, `language`, `search`, `source_collection`, `everything=1`) | add or remove many books; over 200 run in the background |
| `sok_resdesk.curation.apply_rules` (`collection`) | add every book matching the collection's rules |
| `sok_resdesk.transfer.quick_export` (`export_format`, and `search`, `collection` or `filters`) | download an export straight away (≤ 2,000 books); bigger ones: `POST /api/resource/RD Export` |
| `sok_resdesk.transfer.preview_import` · `apply_import` (`name` of an RD Metadata Import) | check, then apply, an edited spreadsheet |
| `sok_resdesk.outbound.test_connection` (`target`) | check a push target's address and login |
| `sok_resdesk.outbound.start` (`target`, `dry_run`, `force`, `items`) | start a push run, returns its name |
| `sok_resdesk.outbound.cancel` (`run_name`) | stop a push run |
| `sok_resdesk.ingest.cancel_run` (`run`) | same as `jobs.stop_run` (kept for older scripts) |
| `sok_resdesk.transfer.rerun_export` (`name`) | rebuild an export's file with current data |
| `sok_resdesk.help.get_page` (`slug`) | a help page (docs/*.md) as HTML with its table of contents, for the Desk |
| `sok_resdesk.guide.checklist` · `checklist_mark` (`key`, `what`=`done`/`skipped`/`hide`) · `restart_checklist` | the getting-started checklist on the workspace |

See [Collections, metadata & pushing](collections-and-metadata.md) for what these do.

Frappe's standard REST API also works for staff: `/api/resource/RD Item`,
`/api/resource/RD Ingest Profile`, … with token or session authentication.
