# Repository deposit

People can give the library their own work: a paper, a thesis, a report, a dataset description.
They describe it, choose a licence and who may read it, add the files and submit it. A librarian
who is not the depositor reviews it and accepts it, asks for changes or rejects it. An accepted
deposit becomes a book in the catalogue, with its text searchable, downloads, a collection and
the access the depositor chose.

## Setting it up

1. Settings → Features → **Repository deposit** is on by default; switch it off if the library
   does not take deposits (the pages and the review screen then go).
2. Give each person who may deposit the role **ResDesk Depositor** (Desk → People & Roles). Library
   staff (managers and cataloguers) can deposit too, for someone else.
3. Optional: `resdesk_deposit_max_mb` in the site config sets the size limit of one file
   (default 1024 MB).

Accepted works are kept in the site's `private/deposits` folder (not in the read-only library
folder). Put that folder in the library's backups and preservation plan like the rest of the library.

## Depositing

Depositors open **/library/deposit** on the portal (they log in first):

- **Details**: title, authors (one per line, *Surname, Given*), abstract, subjects, kind of work,
  year, language code and the collection to list it in.
- **Licence**: CC0, CC-BY, CC-BY-SA, CC-BY-NC or All rights reserved.
- **Who may read the files**: anyone, or logged-in readers only. An **embargo date** keeps the files
  for logged-in readers until that date; the details stay visible, and on the date the files open
  as chosen, by themselves.
- **Files**: PDF, EPUB, MOBI, AZW3, DOCX, ODT, RTF, TXT, CSV, XLSX or ZIP; a SHA-256 is taken of
  each on arrival, to show later that the file is the one deposited.
- **The declaration** that they may deposit the work and share it on those terms.

*Save draft* keeps it; *Submit for review* sends it. Before submitting, a title, authors, a
licence, at least one file and the declaration are needed. Until it is decided, a deposit can be
withdrawn; after *Ask for changes* it can be changed and submitted again.

## Reviewing

Reviewers (managers and cataloguers) are mailed when a deposit is submitted. In the Desk:
Research Desk → **Deposits**, open one with status *Submitted*. The *Checks made on submission*
box says if a file is the same as one already deposited, or the catalogue already has a book with
that title. Then **Review**:

- **Accept**: the work is written to the deposit folder as a book, catalogued (a PDF's text read,
  or OCR for a scan), listed in the collection chosen, and mailed to the depositor. Its details are
  locked so a later ingest never undoes the reviewed record, and the book notes who deposited and
  who accepted it.
- **Ask for Changes** / **Reject**: a note is required and goes to the depositor by mail.

Nobody reviews their own deposit (only a System Manager can, so a one-person library can still
use it).

## What an accepted deposit is

An ordinary book from a folder source: a PDF is searchable page by page and readable in the
reader, other formats are downloadable, access follows the book's visibility, and ARKs, DOIs,
preservation copies and OAI-PMH, IIIF and exports apply as for any book. Its identifier is
`dep-` and the deposit's number.
