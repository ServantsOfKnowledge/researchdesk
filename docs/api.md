# HTTP API

All public endpoints are `GET` requests (some also accept `POST`), need no login, and only
return published records. Responses are JSON inside a `message` key unless noted. Guest
endpoints are rate-limited per IP.

Base: `<BASE_URL>/api/method/`

## Search

`sok_resdesk.api.search`

| Param | Default | |
|---|---|---|
| `q` | `""` | query text (any script) |
| `mode` | `books` | `books` or `pages` (full text inside books) |
| `filters` | `{}` | JSON, e.g. `{"language_label":["Kannada"],"decade":["1950s"],"year_from":1900,"year_to":1950}`. Facet keys: `language_label`, `decade`, `subjects`, `creators`, `collections` |
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

## Search inside one book

`sok_resdesk.api.search_inside?item_id=<id>&q=<text>[&limit=50]` returns
`{"total", "hits": [{"leaf", "page_label", "snippet"}]}`, sorted by page.
`leaf` is the 0-based page index used by the Internet Archive reader (`…/page/n<leaf>`).

## Records

`sok_resdesk.api.item?item_id=<id>` returns the full catalogue record (title, alt_title,
creators, alt_creators, year, language, publisher, subjects, collections, licence,
page_count, ark, source_url, portal_url, …).

`sok_resdesk.api.stats` returns counts of items, creators, full-text items, languages,
indexed pages and search-engine health.

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

Frappe's standard REST API also works for staff: `/api/resource/RD Item`,
`/api/resource/RD Ingest Profile`, … with token or session authentication.
