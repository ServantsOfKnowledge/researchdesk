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
| `q` | `""` | query text (any script): `"a phrase"`, `a OR b`, `-word`; words in Latin letters also search their Indic spellings (the response's `also` lists them) |
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

`sok_resdesk.api.book_text?item_id=<id>&format=epub|txt` downloads the book's text: an
accessible EPUB 3 (language, printed page numbers as a page list, EPUB Accessibility metadata)
or plain text, with proofread pages in their corrected form. Readers who may read the book
only; 10 a minute.

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
| `sok_resdesk.ingest.count_profile` (`profile`) | count matching IA items (folder items, repository records, Wikisource Index pages) |
| `sok_resdesk.repository.check` (`profile`) | a repository profile: the repository's name, its sets and one record as it would be catalogued |
| `sok_resdesk.wikisource.check` (`profile`) | a Wikisource profile: how many Index pages (books) it names and the first one's details |
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
| `sok_resdesk.collectioncovers.get_image` (`collection`, `identifier` optional) | take the collection's picture from archive.org now (its mirrored collection, or any identifier), replacing the cover |
| `sok_resdesk.collectioncovers.get_missing` | pictures from archive.org for every collection without a cover (background) |
| `sok_resdesk.features.overview` | Settings → Features: every feature and whether it is on, the institution profiles, and suggestions from the data here (managers) |
| `sok_resdesk.features.switch_on` (`feature`) | switch a feature on (a suggestion's Turn on; managers) |
| `sok_resdesk.transfer.quick_export` (`export_format`, and `search`, `collection` or `filters`) | download an export straight away (≤ 2,000 books); bigger ones: `POST /api/resource/RD Export` |
| `sok_resdesk.transfer.preview_import` · `apply_import` (`name` of an RD Metadata Import) | check, then apply, an edited spreadsheet |
| `sok_resdesk.outbound.test_connection` (`target`) | check a push target's address and login |
| `sok_resdesk.librarysystems.start` (`system`, `action`: import / match / send) | a library system: import its records and match them, match again, or send links back (background) |
| `sok_resdesk.librarysystems.decide` (`record`, `item` or `not_a_match`) | a cataloguer's decision on a library record |
| `sok_resdesk.librarysystems.download_with_links` (`system`) | the linked records with their 856 links, MARCXML to import into the library system |
| `sok_resdesk.outbound.start` (`target`, `dry_run`, `force`, `items`) | start a push run, returns its name |
| `sok_resdesk.outbound.cancel` (`run_name`) | stop a push run |
| `sok_resdesk.ingest.cancel_run` (`run`) | same as `jobs.stop_run` (kept for older scripts) |
| `sok_resdesk.transfer.rerun_export` (`name`) | rebuild an export's file with current data |
| `sok_resdesk.calibre_export.estimate` (`values`: an Export's fields) | Staff: how many of the chosen books have files held here, how many files and megabytes, and what is left out, before a *Calibre library (zip)* export is made |
| `sok_resdesk.help.get_page` (`slug`) | a help page (docs/*.md) as HTML with its table of contents, for the Desk |
| `sok_resdesk.guide.checklist` · `checklist_mark` (`key`, `what`=`done`/`skipped`/`hide`/`show`) · `restart_checklist` | the getting-started checklist on the workspace (`show` brings a hidden one back, keeping its ticks; `restart_checklist` starts it afresh) |
| `sok_resdesk.priority.set_worker_priority` (`nice`=`19`/`10`/`5`/`0`/`-5`) | choose the background workers' priority live; each worker applies it between two books (Background Jobs → Machine → Worker priority) |
| `sok_resdesk.search.enqueue_index_missing` (`with_pages`) | queue the books that never reached the search engine; returns how many |
| `sok_resdesk.preservation.preserve_now` (`item`) · `check_now` (`item`) · `enqueue_preservation` | make or update a book's preservation copy now; check a copy against its checksums; copy every book waiting for one (docs/preservation.md) |
| `sok_resdesk.preservation.second_copy_now` (`item`) · `enqueue_second_copies` | make or update a book's second copy now; queue every book whose second copy is missing or behind |
| `sok_resdesk.preservation.serve_from_copy` (`item`, `on`=1/0) | serve a book's PDF from our copy (archive.org no longer serves it), or stop |
| `sok_resdesk.preservation.export_book` (`item`) · `export_collection` (`collection`) · `exports` · `download_export` (`file`) | BagIt bags of a book (at once) or a collection's preserved books (in the background); the exports made; download one |
| `sok_resdesk.ocr.enqueue_scoring` (`limit`) · `sok_resdesk.jobs.score_ocr_now` | score the OCR quality of books not scored yet, in one background job; returns how many |
| `sok_resdesk.search_queue.get_overview` | the search engine's queue: book records and page text waiting, tasks a minute, time to go, failures, page text held or pending, task history |
| `sok_resdesk.search_queue.send_now` | start sending waiting page text now (managers; not while held) |
| `sok_resdesk.search_queue.books_first` · `hold_page_text` (`hold`=1/0) · `clear_history` (`days`) | cancel the waiting page text so books are listed next (it is sent again later); hold or resume page text; forget finished tasks older than `days` (7) |
| `sok_resdesk.api.page` (`item_id`, `leaf`) | one page for the page reader: image address, text, printed number, last leaf (text needs read access) |
| `sok_resdesk.api.page_image` (`item_id`, `leaf`) | a page of a book not on archive.org, drawn from its PDF (JPEG; read access, open books) |
| `sok_resdesk.pdfs.ocr_now` (`item_id`) | staff: read a book's PDF with OCR, every page, in the background |
| `sok_resdesk.api.cite_page` (`item_id`, `leaf`, `label`) | one page's citation in every format, and its link |
| `sok_resdesk.annotations.page_notes` (`item_id`, `leaf`) | the notes on one page this visitor may see (anchored in the page text as it is now), and what they may do |
| `sok_resdesk.annotations.add` (`item_id`, `leaf`, `kind`, `body`, `tags`, `link`, `entity` (a Wikidata Q-number), `start`+`end` or `region`=`x,y,w,h` in percent, `visibility`=`Private`/`Group`/`Public`, `research_group`, `page_label`) · `edit` (`name`, fields) · `remove` (`name`) | add, change or delete a note (logged in; only its author changes it) |
| `sok_resdesk.annotations.mine` (`q`, `kind`, `item`, `mine_only`) · `export` (`format`=`markdown`/`csv`/`jsonld`, same filters) | My notes, and my groups'; exported with page citations |
| `sok_resdesk.annotations.review` (`name`, `decision`=`Approved`/`Rejected`) | managers: approve or reject a public note |
| `sok_resdesk.annotations.collection` (`item_id`, `leaf`) · `get` (`name`) | a book's approved public notes as a W3C AnnotationPage; one note as a W3C Web Annotation |
| `sok_resdesk.pagetext.history` (`item_id`, `leaf`) | proofreaders: a page's text versions, newest first, and the zone layouts |
| `sok_resdesk.pagetext.save_page` (`item_id`, `leaf`, `text`, `zones`, `page_label`, `validate`=1/0) · `restore` (`name`) | proofreaders: save a corrected page (Proofread), validate one proofread by someone else (unchanged text), or make an earlier version current again |
| `sok_resdesk.reocr.ocr_page` (`item_id`, `leaf`, `zones`=`[{x,y,w,h,kind,langs?}]` in percent, in reading order, `languages`=`["kan","san"]`) · `ocr_result` (`key`) | proofreaders: read one page again, zone by zone (a zone may have its own languages), in the languages chosen (default: the book's; English always added), in the background; `ocr_result` returns its text when done (to the same person) |
| `sok_resdesk.reocr.languages` (`item_id`) | proofreaders: the book's OCR languages and the language models installed on the server |
| `sok_resdesk.annotations.wikidata_search` (`q`, `language`) | logged-in readers: Wikidata items matching what was typed (a name in any script, or a Q-number), for a note's **About** |
| `sok_resdesk.annotation_protocol.annotations/<book>/` · `…/<book>/<note>` | the W3C Web Annotation Protocol: GET the book's notes (an AnnotationCollection in pages of 100, `?page=0`, `?iris=1`), POST a Web Annotation to add one (private to its author); GET, PUT (If-Match) or DELETE one note. Reading public notes needs no login; writing needs a reader's session or API key |
| `sok_resdesk.groundtruth.preview` (`name`) · `build` (`name`) · `publish` (`name`, `on`) · `download` (`name`) | a ground-truth set: how many pages match now; make its zip in the background; put it on the portal (needs a licence) or take it off; download it (anyone for a set on the portal, staff for any) |
| `sok_resdesk.datacite.register_collection` (`collection`) · `register_book` (`name`) | send a collection's public books to DataCite in the background, or one book now (Settings → DOIs) |
| `sok_resdesk.reocr.enqueue_book` (`item_id`, `preset`, `languages`) · `enqueue_worst` (`count`, `preset`) · `engine_status` | managers: re-OCR a book (in the languages chosen, default the book's), or the books with the poorest OCR, keeping the better text; whether Tesseract is installed and with which models |
| `sok_resdesk.people.overview` · `users` (`role`, `q`, `show_disabled`) | managers: each role with its count and sign-ups waiting; people with their Research Desk roles |
| `sok_resdesk.people.set_role` (`user`, `role`, `on`) · `set_enabled` (`user`, `enabled`) · `invite` (`emails`, `roles`, `full_name`, `send_welcome`) · `decide` (`names`, `status`) | managers: give or take a role, switch an account off or on, invite people, approve or reject sign-ups |
| `sok_resdesk.review.overview` (`check`, `q`, `start`) · `save` (`item`, `values`) · `ignore` (`name`) · `hide_duplicate` (`item`) · `scan_now` | Cataloguers and managers: Desk → Review Queue: books whose records need a look, corrections kept through re-ingest, answers, duplicates taken off the portal |
| `sok_resdesk.contribute.plan` · `refresh` · `quickstatements` · `send` (`target`) · `send_mine` · `saco` | Cataloguers (sending: managers): Authorities → Give back: names and author links for Wikidata worked out from the library's matches, as QuickStatements or sent through a Wikidata Push Target; subjects LCSH lacks as a CSV for SACO |
| `sok_resdesk.wikimedia.status` · `connect` (`token`) · `disconnect` | Cataloguers, proofreaders, managers: My Wikimedia Account: whether and as whom I am connected; check an OAuth 2.0 access token with Wikimedia and keep it encrypted for me alone; forget it. The token never leaves the server |
| `sok_resdesk.wikisource.send_plan` (`item`) · `send_pages` (`item`, `pages`) | Cataloguers, proofreaders, managers: Item → Send to Wikisource: what my own corrections would change on the wiki (with diffs), then sending the reviewed pages (up to 25, each against the revision reviewed) under my Wikimedia account |
| `sok_resdesk.deposit.options` · `mine` · `get` (`name`) · `save` (`values`, `name`) · `attach_file` (`name`, `file_url`) · `remove_file` (`name`, `idx`) · `submit` (`name`) · `withdraw` (`name`) | Depositors (and staff): the deposit form's choices, my deposits, one deposit, and making, filling, submitting and withdrawing a draft; a person reads and changes only their own |
| `sok_resdesk.deposit.accept` (`name`, `notes`, `collection`) · `request_changes` (`name`, `notes`) · `reject` (`name`, `notes`) | Staff: review a submitted deposit (not one's own, unless a System Manager); accepting writes the work as a book and lists it in the collection |
| `sok_resdesk.manuscripts.label_leaves` (`item`, `sides`, `start_image`, `leaves`, `start_folio`, `preview`) · `clear_labels` (`item`) | Cataloguers: Item → Label the Leaves: give a manuscript's images their folio labels (1a, 1b…), shown first with `preview=1`; or take them off |
| `sok_resdesk.authority.overview` (`kind`, `status`, `q`, `start`) · `find` (`kind`, `limit`) · `accept` (`kind`, `name`, `choice`) · `reject` · `undo` (`kind`, `name`) · `search_again` (`kind`, `name`, `q`) · `merge` (`name`, `into`) | Cataloguers and managers: Desk → Authorities: authors matched to Wikidata/VIAF and subjects to LCSH; candidates, decisions, merging two names for one person |
| `sok_resdesk.translations.overview` · `save` (`lang`, `source`, `text`) · `download` · `upload` (`content`) | Cataloguers and managers: Portal Translations, every portal phrase with its translations; save one (empty text removes it); the CSV spreadsheet out and back |
| `sok_resdesk.translations.set_language` (`lang`) | anyone, POST: the portal's language switch (a cookie; a logged-in reader's account language too) |
| `sok_resdesk.requirements.report` (`refresh`) · `install` (`part`=`python`/`ocr`) | admins: every tool Research Desk uses, found or missing, with what it is for and how to fix it; install Python packages or Tesseract with its models through the updater helper (native installs) |
| `sok_resdesk.dashboard.numbers` (`refresh`) | managers: the workspace numbers (cached five minutes) |
| `sok_resdesk.analytics.config` | the usage statistics service portal pages load (public) |
| `GET /ark:/<naan>/<name>[/n<leaf>]` | a permanent ARK: redirects to the book (with a leaf: that page in the page reader); `?info` returns its who/what/when/where record as text; a deleted book's ARK leads to its tombstone |
| `sok_resdesk.capacity.get_status` | the book limit: books and pages in the catalogue, the limit, room left, and what the machine's CPUs, memory and disk can each hold |
| `sok_resdesk.server.status` | everything on the Server page: versions, updates, health, backups, helper, recent tasks |
| `sok_resdesk.server.check_updates` | look for a newer release and Frappe patch now (also daily) |
| `sok_resdesk.server.request_task` (`action`, `args` JSON) | ask the updater helper to `upgrade` (`target`=`latest`/`vX.Y.Z`, `backup`, `frappe`), `restart` (`service`=`web`/`workers`/`scheduler`/`search`/`all`), `apply_resources` (`preset`), `server_backup`, `help_pictures` (new screenshots of this library for its help), `check_updates` or `logs` (`service`, `lines`); returns the task name. Changes to the installation need the System Manager role |
| `sok_resdesk.server.get_task` (`name`) · `cancel_task` (`name`) | a task's status and log; cancel one still waiting |
| `sok_resdesk.server.take_backup` (`with_files`) · `delete_backup` (`name`) | back up now in the background; delete a backup (System Manager). Download: `/backups/<file>` (System Manager) |
| `sok_resdesk.server.logs` (`source`=`errors`/`failed_jobs`/`files`, `name`, `lines`) | recent errors, failed jobs, or the end of a log file |
| `sok_resdesk.server.test_alert` | send a test alert to the Desk, email and webhook |

See [Collections, metadata & pushing](collections-and-metadata.md) for what these do.

Frappe's standard REST API also works for staff: `/api/resource/RD Item`,
`/api/resource/RD Ingest Profile`, … with token or session authentication.
