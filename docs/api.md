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

`sok_resdesk.server.ping` is for uptime monitors (Uptime Kuma, a load balancer, a cron job):
`{"status": "ok"}`, or HTTP 503 with `"degraded"` when the workers, scheduler, cache or search
engine are down. It says nothing more, so it is safe to leave open.

`sok_resdesk.server.agent_sync` is only for the updater helper (it needs the helper's token);
see [Server](server.md#how-the-updater-helper-works).

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
| `sok_resdesk.ia_sync.sync_now` (`profile`) | bring in what changed on archive.org since the profile's last run; returns the run name |
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
| `sok_resdesk.jobs.retry_run` (`run`) | try a finished run's failures again in the same run: failed books, batches that failed as a whole, or the whole listing for a run that failed or was interrupted |
| `sok_resdesk.jobs.retry_failed_jobs` (`job_id`, optional) | retry one failed background job, or all of them; ingest batches go back into their run |
| `sok_resdesk.jobs.clear_failed_jobs` | forget every failed background job (System Manager) |
| `sok_resdesk.jobs.stop_all` (`force`, `pause`, `search`) | stop all Research Desk background work |
| `sok_resdesk.jobs.cancel_job` (`job_id`) · `set_paused` (`paused`) · `cancel_search_tasks` | single job, schedules, cancel what waits in the search engine (keeping track of it: page text is sent again, book records count as not sent) |
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
| `sok_resdesk.guide.checklist` · `checklist_mark` (`key`, `what`=`done`/`skipped`/`hide`/`show`) · `restart_checklist` | the getting-started checklist on the workspace (`show` brings a hidden one back, keeping its ticks; `restart_checklist` starts it afresh) |
| `sok_resdesk.priority.set_worker_priority` (`nice`=`19`/`10`/`5`/`0`/`-5`) | choose the background workers' priority live; each worker applies it between two books (Background Jobs → Machine → Worker priority) |
| `sok_resdesk.search.enqueue_index_missing` (`with_pages`) | queue the books that never reached the search engine; returns how many |
| `sok_resdesk.preservation.preserve_now` (`item`) · `check_now` (`item`) · `enqueue_preservation` | make or update a book's preservation copy now; check a copy against its checksums; copy every book waiting for one (docs/preservation.md) |
| `sok_resdesk.ocr.enqueue_scoring` (`limit`) · `sok_resdesk.jobs.score_ocr_now` | score the OCR quality of books not scored yet, in one background job; returns how many |
| `sok_resdesk.search_queue.get_overview` | the search engine's queue: book records and page text waiting, tasks a minute, time to go, failures, page text held or pending, task history |
| `sok_resdesk.search_queue.books_first` · `hold_page_text` (`hold`=1/0) · `clear_history` (`days`) | cancel the waiting page text so books are listed next (it is sent again later); hold or resume page text; forget finished tasks older than `days` (7) |
| `sok_resdesk.api.page` (`item_id`, `leaf`) | one page for the page reader: image address, text, printed number, last leaf (text needs read access) |
| `sok_resdesk.api.cite_page` (`item_id`, `leaf`, `label`) | one page's citation in every format, and its link |
| `sok_resdesk.annotations.page_notes` (`item_id`, `leaf`) | the notes on one page this visitor may see (anchored in the page text as it is now), and what they may do |
| `sok_resdesk.annotations.add` (`item_id`, `leaf`, `kind`, `body`, `tags`, `link`, `start`+`end` or `region`=`x,y,w,h` in percent, `visibility`=`Private`/`Group`/`Public`, `research_group`, `page_label`) · `edit` (`name`, fields) · `remove` (`name`) | add, change or delete a note (logged in; only its author changes it) |
| `sok_resdesk.annotations.mine` (`q`, `kind`, `item`, `mine_only`) · `export` (`format`=`markdown`/`csv`/`jsonld`, same filters) | My notes, and my groups'; exported with page citations |
| `sok_resdesk.annotations.review` (`name`, `decision`=`Approved`/`Rejected`) | managers: approve or reject a public note |
| `sok_resdesk.annotations.collection` (`item_id`, `leaf`) · `get` (`name`) | a book's approved public notes as a W3C AnnotationPage; one note as a W3C Web Annotation |
| `sok_resdesk.pagetext.history` (`item_id`, `leaf`) | proofreaders: a page's text versions, newest first, and the zone layouts |
| `sok_resdesk.pagetext.save_page` (`item_id`, `leaf`, `text`, `zones`, `page_label`, `validate`=1/0) · `restore` (`name`) | proofreaders: save a corrected page (Proofread), validate one proofread by someone else (unchanged text), or make an earlier version current again |
| `sok_resdesk.reocr.ocr_page` (`item_id`, `leaf`, `zones`=`[{x,y,w,h,kind}]` in percent, in reading order) · `ocr_result` (`key`) | proofreaders: read one page again, zone by zone, in the background; `ocr_result` returns its text when done (to the same person) |
| `sok_resdesk.reocr.enqueue_book` (`item_id`, `preset`) · `enqueue_worst` (`count`, `preset`) · `engine_status` | managers: re-OCR a book, or the books with the poorest OCR, keeping the better text; whether Tesseract is installed and with which models |
| `sok_resdesk.people.overview` · `users` (`role`, `q`, `show_disabled`) | managers: each role with its count and sign-ups waiting; people with their Research Desk roles |
| `sok_resdesk.people.set_role` (`user`, `role`, `on`) · `set_enabled` (`user`, `enabled`) · `invite` (`emails`, `roles`, `full_name`, `send_welcome`) · `decide` (`names`, `status`) | managers: give or take a role, switch an account off or on, invite people, approve or reject sign-ups |
| `sok_resdesk.dashboard.numbers` (`refresh`) | managers: the workspace numbers (cached five minutes) |
| `sok_resdesk.analytics.config` | the usage statistics service portal pages load (public) |
| `GET /ark:/<naan>/<name>[/n<leaf>]` | a permanent ARK: redirects to the book (with a leaf: that page in the page reader); `?info` returns its who/what/when/where record as text; a deleted book's ARK leads to its tombstone |
| `sok_resdesk.capacity.get_status` | the book limit: books and pages in the catalogue, the limit, room left, and what the machine's CPUs, memory and disk can each hold |
| `sok_resdesk.server.status` | everything on the Server page: versions, updates, health, backups, helper, recent tasks |
| `sok_resdesk.server.check_updates` | look for a newer release and Frappe patch now (also daily) |
| `sok_resdesk.server.request_task` (`action`, `args` JSON) | ask the updater helper to `upgrade` (`target`=`latest`/`vX.Y.Z`, `backup`, `frappe`), `restart` (`service`=`web`/`workers`/`scheduler`/`search`/`all`), `apply_resources` (`preset`), `server_backup`, `check_updates` or `logs` (`service`, `lines`); returns the task name. Changes to the installation need the System Manager role |
| `sok_resdesk.server.get_task` (`name`) · `cancel_task` (`name`) | a task's status and log; cancel one still waiting |
| `sok_resdesk.server.take_backup` (`with_files`) · `delete_backup` (`name`) | back up now in the background; delete a backup (System Manager). Download: `/backups/<file>` (System Manager) |
| `sok_resdesk.server.logs` (`source`=`errors`/`failed_jobs`/`files`, `name`, `lines`) | recent errors, failed jobs, or the end of a log file |
| `sok_resdesk.server.test_alert` | send a test alert to the Desk, email and webhook |

See [Collections, metadata & pushing](collections-and-metadata.md) for what these do.

Frappe's standard REST API also works for staff: `/api/resource/RD Item`,
`/api/resource/RD Ingest Profile`, … with token or session authentication.
