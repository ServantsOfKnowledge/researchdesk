# Books from your own folders or servers

Research Desk can ingest books that sit in **Internet-Archive-style item folders** as well as
books on archive.org. That includes scanning-centre output (Scribe, Repub), local copies of IA
items, and material that is not, or not yet, on archive.org. It works with:

| Where the books are | Set the profile's *Folder Path or Server URL* to |
|---|---|
| A folder on the Research Desk computer | `/library-source` (the folder set as `LIBRARY_DIR` in `.env`) |
| A USB disk or NAS share | mount it on the computer, point `LIBRARY_DIR` at it, use `/library-source` |
| A sub-folder of either | `/library-source/2026/september` |
| A web server with the same layout | `https://books.example.org/items/` |

Mixed collections are normal. Each book is checked against archive.org: books that are there
use the Internet Archive reader and links. The rest are served from **your** files, with the
PDF opening at the right page from search results.

## The item folder layout

Each book is a folder containing `<identifier>_meta.xml`, at any depth:

```
books/
  2026/september/
    mybook0001/
      mybook0001_meta.xml                    required: IA metadata (title, creator, date, language…)
      mybook0001_hocr_searchtext.txt.gz      ┐ best: page-level text
      mybook0001_hocr_pageindex.json.gz      ┘
      mybook0001_page_numbers.json           optional: printed page numbers
      mybook0001.pdf                         the PDF readers see (local-only books)
      __ia_thumb.jpg                         optional: cover (also cover.jpg / thumbnail.jpg)
      mybook0001_jp2.zip, _scandata.xml …    ignored
```

The identifier is taken from the `_meta.xml` file name, which normally matches the folder name.
If two folders use the same identifier, the first one wins and the run log names the duplicate.

**Page text is taken from the best file available**, in this order:

1. `_hocr_searchtext.txt.gz` + `_hocr_pageindex.json.gz` (what archive.org produces)
2. `_hocr.html` / `_hocr.html.gz`
3. `_chocr.html.gz` (character-level hOCR)
4. `_djvu.xml`
5. `_djvu.txt`: no page breaks, so it is indexed in numbered **sections** (§1, §2 …).
   Search finds the passage, but can't jump the reader to a page.

The file used is shown on each item (Desk → RD Item → *Local Copy → Text Taken From*).

## Setting it up (Docker)

1. In `.env`, point at the folder:

   ```
   LIBRARY_DIR=/Volumes/Books          # macOS external disk or mounted share
   # LIBRARY_DIR=/mnt/nas/sok-books    # Linux NAS mount
   ```

2. `./install.sh` (or `./resdesk.sh restart`). The folder is mounted **read-only**:
   Research Desk never changes your files.

3. Desk → **Ingest Profiles** → *Library folder* (created on install), or a new profile with
   **Source: Folder or Server**. **Check Count** → **Run Ingest**.

From the terminal:

```bash
./resdesk.sh count  --folder /library-source
./resdesk.sh ingest --folder /library-source --limit 0 --background --name "Library folder"
./resdesk.sh ingest --folder /library-source/2026/september
```

### NAS shares

Mount the share on the host (Finder → *Connect to Server* on a Mac, `/etc/fstab` on Linux) and
set `LIBRARY_DIR` to the mount point. Alternatively, let Docker mount it directly with a
`compose.override.yaml`:

```yaml
volumes:
  books:
    driver_opts: { type: nfs, o: "addr=nas.local,ro,nfsvers=4", device: ":/volume1/books" }
services:
  backend:   { volumes: [ "books:/library-source:ro" ] }
  queue:     { volumes: [ "books:/library-source:ro" ] }
  scheduler: { volumes: [ "books:/library-source:ro" ] }
```

(For SMB/CIFS use `type: cifs` with `o: "addr=nas.local,username=…,password=…,ro"`.) Docker Compose
reads `compose.override.yaml` automatically, except in developer mode. There, add it to
`COMPOSE_FILE` yourself.

## Books on a web server

Any server that exposes the item folders works:

- **With directory listings** (nginx `autoindex on;`, Apache `Options +Indexes`, `python3 -m http.server`):
  Research Desk walks the folders itself.
- **Without listings**: publish a plain-text list of item folders, one relative path per line,
  and put its URL in *Item List URL*:

  ```
  # identifiers.txt
  mybook0001
  2026/september/mybook0002
  ```

```bash
./resdesk.sh ingest --server https://books.example.org/items/ --manifest https://books.example.org/items/identifiers.txt
```

Readers never talk to the book server directly: PDFs and covers are streamed through Research
Desk, so the server can stay on a private network (it only has to be reachable from the
Research Desk machine).

## New and changed books: drop-folder mode

Set the profile's **Schedule** to *Hourly* (or *Daily* for big web servers). On each run:

- **new** item folders are ingested,
- **changed** ones (a newer `_meta.xml`, new OCR, a replaced PDF) are re-ingested,
- **unchanged** ones are skipped in a fraction of a second.

So people can copy, rsync or upload item folders into the library folder at any time. They
appear on the portal within the hour. To force a full refresh, tick *Refresh Items Already in
Catalogue* for one run, or use **Refresh from Source** on a single item.

## Security

- Only folders under the library root (`/library-source`) can be used. For native (bench)
  installs, list allowed folders in the site config:
  `bench --site <site> set-config -p resdesk_library_roots '["/srv/books"]'`.
- Readers can download only each book's **PDF** (for items marked *Open*) and its **cover
  image**. Metadata files, OCR files and anything else in the folders are never served.
- Items marked *Restricted* in `_meta.xml` (`access-restricted-item: true`) are catalogued,
  but their text is not indexed and their PDF is not served.
