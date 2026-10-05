# Books from a Calibre library

A [Calibre](https://calibre-ebook.com) library is a folder with a `metadata.db` and, for every
book, a folder `Author/Title (id)/` with its files (EPUB, MOBI, PDF…), `cover.jpg` and
`metadata.opf`. Research Desk can bring a whole library in, so a collection kept in Calibre can
move to Research Desk, or be searched and shared from it, without retyping a record.

## Bringing a library in

Put (or mount) the Calibre library folder under the library folder (`/library-source`, or a
folder listed in `resdesk_library_roots`) and make an Ingest Profile like any folder source:
Desk → Ingest Profiles → New, **Source: Folder or Server**, **Location** the library folder (the
one containing `metadata.db`). Research Desk notices the `metadata.db` and reads the library as
Calibre does. **Run Ingest** catalogues every book.

The library is **only read, never changed**: its database is opened read-only and no file in it
is written, so it can stay in use in Calibre while Research Desk reads it. Run the profile
again whenever you like: only books Calibre records as changed are updated.

## What comes across

| In Calibre | In Research Desk |
|---|---|
| Title, authors (as Calibre keeps them) | title, authors |
| Publication date | year (Calibre's "no date" is left empty) |
| Publisher, language(s) | publisher, language (several: *multiple*) |
| Tags | subjects |
| Series and series number | series (*Name #3*) |
| Comments | description |
| ISBN | ISBN |
| Cover | the book's cover |
| Identifiers, rating, custom columns | kept with the book's source record for cataloguers |
| The files | the book's files, for download |

A book's identifier here is made from Calibre's own id of the book (`calibre-` and the start of
its uuid), so it stays the same if the library is rebuilt or moved.

## Files and text

- **PDF**: read like any PDF: its text layer is the book's page text, a scan without text is read
  with OCR, and the book can be read page by page.
- **EPUB, MOBI, AZW3 and other formats**: catalogued and **downloadable** from the book's page
  (*Download EPUB*, *Download MOBI*…), by the book's usual access. Their text is not read yet,
  so these books are found by their details, not by words inside them.
- Files a Calibre record names but that are missing on disk are not offered.
- Calibre books are never looked up on archive.org.

## Access

As for every book: set **Access** on the profile (open, login to read, login to find). Only
books readers may read can be downloaded, and only the files listed on the book (never
`metadata.opf` or anything else in the folder).
