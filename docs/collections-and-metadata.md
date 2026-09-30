# Collections, metadata, exports and pushing to other systems

This page is for library staff (the *ResDesk Manager* role or a System Manager). It covers:

- [Curated collections](#curated-collections): your own groupings of books, with their own portal pages
- [Editing catalogue details](#editing-catalogue-details): document types and **Keep My Edits**
- [Exporting metadata](#exporting-metadata): spreadsheets, library and linked-data formats, IA-ready files
- [Editing many books with a spreadsheet](#editing-many-books-with-a-spreadsheet)
- [Pushing metadata to other systems](#pushing-metadata-to-other-systems): Internet Archive, Koha, Wikidata, any web service

## Curated collections

Books arrive with the **Source Collections** they have on archive.org (or in `meta.xml`), such as
`ServantsOfKnowledge` or `KannadaUniversity`. **Collections** are yours: *Vachana literature*,
*Epigraphy*, *Books for the Class 10 syllabus*. A book can be in any number of them.

Create one at **Research Desk → Collections → + Add**. Give it a title; the web address
(`/library/collection/<address>`) is filled in from the title and keeps Kannada and other scripts.

| Field | What it does |
|---|---|
| Show on Portal | Lists it on `/library/collections` and gives it a page. Untick for a staff-only working set |
| Featured on the Home Page | Shows it as a card on the portal home page |
| Cover Image, Description, Curator | Shown on the collection page |
| Order on the Collections Page | Lower numbers first |
| Rules | Optional. Books that match are added automatically (see below) |

### Adding books

- **From the Items list** (Desk): tick books → **Actions → Add to / Remove from Collection**, or
  filter the list and use **menu → Add All Matching Books to a Collection** (works for thousands
  of books; large changes run in the background).
- **From the portal**: logged in as staff, search, then use the staff bar above the results to
  add everything matching the search to a collection.
- **On a book's form**: the *Collections* field.
- **With a spreadsheet**: the `collections` column (see below). New collection names are created.
- **With rules**: in the collection, add rows like *Subject contains Vachana* or *Source Collection
  is exactly KannadaUniversity*. Rules can match on Source Collection, Subject, Language, Creator,
  Source, Ingest Profile and Document Type; matching ignores case. A book that matches **any** rule
  is added. Press **Apply Rules** to add existing books; newly ingested books are added as they arrive.
  Rules only add books, they never remove one you added by hand.

### On the portal

- `/library/collections` lists published collections with how many books *the viewer* can find
  (members-only books aren't counted for guests).
- Each collection page has the full search: filters, search inside the text, sorting.
- Search results everywhere have a **Collection** filter, and book pages show their collections.
- OAI-PMH offers each collection as a set, `rd:<address>`, so Koha or another harvester can take
  just one collection.

## Editing catalogue details

Open a book (**Research Desk → Items**) and edit the title, creators, subjects, date, document
type and so on. Changes reach the portal and search within seconds.

**Document Type** (Book, Periodical, Article, Thesis, Report, Manuscript, Map, Other) is guessed
at ingest from the archive.org metadata and can be corrected. It is a search filter and decides the
citation type: a Thesis becomes `@phdthesis` in BibTeX and `THES` in RIS, a Periodical `@periodical`.

**Keep My Edits.** When you edit a book's details (on the form or with a spreadsheet), *Keep My
Edits* is ticked for you. Re-ingesting that book later still updates its OCR text, page count and
files, but won't overwrite the details you corrected. Untick it to let the source win again.

## Exporting metadata

**Research Desk → Exports → + Add**, choose a **Format** and **Which Books**, and save. Small
exports finish at once; big ones run in the background (watch them on **Background Jobs**). The
file is attached to the export (**Download**) and kept private to staff. **Export Again** rebuilds it
with current data.

Shortcuts: **Export Metadata** on a collection, and **menu → Export Metadata of Matching Books**
on the Items list (exports exactly what the list is filtered to).

| Which Books | |
|---|---|
| Everything | All published books (tick *Include Unpublished Books* for the rest) |
| Collection / Ingest Profile / Source Collection | As named |
| Search | The same words you would type on the portal |
| Filters / Selected Books | Set by the Items list shortcuts |

| Format | For |
|---|---|
| Spreadsheet (CSV), Spreadsheet (Excel) | Checking and correcting in bulk, then importing back |
| JSON (everything), JSON Lines | A full dump for backups, scripts and other software |
| Dublin Core XML | Repositories and aggregators (`oai_dc` records) |
| MODS XML | Libraries and digital repositories (MODS 3.7, validated against the schema) |
| MARCXML (Koha) | Importing into Koha or any MARC21 system (*Tools → Stage MARC records*) |
| JSON-LD (schema.org) | Linked data and search engines |
| CSL-JSON, BibTeX, RIS | Zotero, Mendeley, EndNote, JabRef, LaTeX |
| Internet Archive bulk-upload CSV | The `ia upload --spreadsheet` tool, for uploading or updating many items |
| Internet Archive meta.xml files (zip) | One `<identifier>_meta.xml` per book, for IA-style item folders |

## Editing many books with a spreadsheet

1. Export as **Spreadsheet (CSV)** or **(Excel)**. Each row is a book; lists (creators, subjects,
   collections) are separated with `; `.
2. Edit it in Excel, LibreOffice or Google Sheets. You can delete columns you aren't changing.
   Columns on the right (`source_collections`, `source`, `page_count`, `portal_url`,
   `source_url`) are for reference and are ignored on import.
3. **Research Desk → Spreadsheet Imports → + Add**, attach the file, save, and press **Preview Changes**.
   The preview lists every book that will change and which columns, plus any problems (a year
   that isn't a number, an unknown visibility). Nothing is changed yet.
4. Press **Apply Changes**. Changed books get *Keep My Edits* ticked.

Rules: only columns present in the file are touched; an **empty cell clears** that field (delete
the column if you don't mean to change it); rows are matched by `item_id`. Tick **Create Records
for New IDs** to add books that aren't in the catalogue yet (for example a manuscript you are
describing before it is digitised); otherwise such rows are skipped.

## Pushing metadata to other systems

A **Push Target** (**Research Desk → Push Targets**) sends book metadata to another system.
Every target starts with **Dry Run** on: runs work out and log exactly what would change without
sending anything. Read the log, then untick Dry Run.

On a target: **Test Connection** checks the address and login. **Push → Dry Run / Push Now**
starts a run; **View → Runs** shows past runs with a line per book. What was sent is remembered per
book (**Pushed Records**, with a link to the book in the other system), so the next run skips books
that haven't changed and updates rather than duplicates. Tick *Send unchanged books again too* to
resend everything.

**Send Changes Automatically**: when a book in scope is edited (form, bulk change, spreadsheet
import), it is pushed within a minute. Books updated by ingest are not pushed automatically;
run the target after a big ingest instead.

A run stops by itself if 10 books in a row fail (the other system is probably down). **Pause** a
run from its form or from Background Jobs (for example while the other system is being upgraded)
and **Resume** it later: it carries on with the books it hadn't sent. **Cancel** gives up on the
rest; books already sent stay sent.

### Internet Archive

Updates the metadata of **your own items on archive.org** (books whose source is archive.org)
with your corrected catalogue details, using the IA Metadata Write API.

- Keys: log in to archive.org as an account that can edit the items, and get the **Access Key**
  and **Secret Key** from <https://archive.org/account/s3.php>.
- **Fields to Update**: by default `title, alt_title, creator, alt_creator, date, publisher,
  language, subject, description, volume, isbn, licenseurl, rights`. List fewer to be careful,
  e.g. just `subject, language`.
- Fields are only added or replaced, **never deleted** on archive.org, and a field is only written
  when your value differs. The dry run shows each book's changed fields.
- archive.org queues each change as a task; it appears on the item after a few minutes.

### Koha

Creates or updates bibliographic records in Koha through its REST API (**Koha 23.11 or later**).

- In Koha: turn on the system preference **RESTBasicAuth** (for *User and Password*) or
  **RESTOAuth2ClientCredentials** (for *OAuth2 Client Credentials*, with an API key made under
  the patron's *More → Manage API keys*). The staff user needs the `editcatalogue` permission.
- **Koha Staff URL** is the staff interface address, e.g. `https://library-intra.example.org`.
- The first push creates a biblio for each book and remembers its biblionumber; later pushes
  update that biblio. If someone deleted it in Koha, a new one is created.
- The record is the same MARC21 as the MARCXML export (with the 856 link back to the portal). Items
  (barcodes, shelving) are left to Koha. For harvesting instead of pushing, see [Koha](koha.md).

### Wikidata

Adds your books to Wikidata as editions (*instance of: version, edition or translation*), with
title, authors (as names), publication date, language, Internet Archive ID, ARK, page count and
a link to the portal. Statements carry the archive.org page as their reference.

- Make a bot password at <https://www.wikidata.org/wiki/Special:BotPasswords> (grants: *Edit
  existing pages*, *Create, edit, and move pages*). Enter the bot username (`YourName@BotName`)
  and password.
- For each book it first looks for an existing item with the same **Internet Archive ID (P724)**
  and **only adds statements that item doesn't have**; existing statements are never changed.
- **Create New Items** is off by default. Creating items in bulk needs community approval: read
  [Wikidata:Bots](https://www.wikidata.org/wiki/Wikidata:Bots) and request a bot flag before
  switching it on for more than a handful of books. Test on
  `https://test.wikidata.org/w/api.php` (set **API URL**) first.
- Edits are paced at one a second and wait when Wikidata is busy (`maxlag`).

### Webhook (any web service)

POSTs each book as JSON to a URL you give: your own discovery system, a data lake, Zapier/n8n,
a university repository.

```json
{"event": "record.updated", "sent_at": 1790000000, "data": { "item_id": "...", "title": "...", ... }}
```

`data` is the same record as the JSON export. **Test Connection** sends `{"event": "ping", ...}`.
With a **Secret**, each request has the header `X-ResDesk-Signature: sha256=<hex>`, the
HMAC-SHA256 of the raw body with the secret; check it on your side:

```python
import hmac, hashlib
expected = "sha256=" + hmac.new(secret.encode(), request_body, hashlib.sha256).hexdigest()
assert hmac.compare_digest(expected, request.headers["X-ResDesk-Signature"])
```

Any 2xx answer counts as delivered; anything else is logged as a failure and retried on the next run.
