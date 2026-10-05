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

## Making a small Calibre collection

For a small collection to take away (a branch library, a colleague, a reading device), Desk →
Exports → New, **Format: Calibre library (zip)**, and choose the books as for any export: a
collection, a search, selected books, an ingest profile. **Estimate Size** says how many of the
chosen books have files held here, how many files and how many megabytes, before anything is
made; the zip is then built in the background and appears on the Export when done.

The zip holds a folder `Author/Title (n)/` for every book with its files (every format together),
`metadata.opf` (its details in Calibre's own sidecar format: title, authors, date, publisher,
language, tags, series, ISBN and a link back to the book here) and `cover.jpg` when it has one.
Unzip it and, in Calibre, **Add books → Add books from directories, including sub-directories
(Assume each directory has a single logical book)**, or on a command line
`calibredb add --recurse --one-book-per-directory <folder>`. Calibre reads each folder's files
and `metadata.opf`.

- **Only files held here go in**: a Calibre or other folder source's own files and a book's copy
  in the preservation store. A book that is not open to read is never written out.
- **Books held elsewhere** (on archive.org, in a repository, on Wikisource or a book server) are
  not copied. They are listed in `not-included.csv` with the reason and a link to where they
  are, so each person can fetch the ones they want there. Calibre has no way to keep a link to a
  file elsewhere and download it when clicked: a Calibre book is its files.
- The same book always gets the same Calibre id, so an export made again can be told from
  the first.
