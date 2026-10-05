# Books from Wikisource

[Wikisource](https://wikisource.org) volunteers type in scanned books and proofread them page by
page. Research Desk can bring those books in: each becomes a book in the catalogue with its
**page text** (searchable inside the text, readable page by page beside the page image), its
details, and a link to its Index page and its scan on Wikisource. Wikisource keeps the scan and
the editing; the library keeps a searchable, citable copy of the text.

Works with any language's Wikisource: `kn.wikisource.org` (Kannada), `sa.wikisource.org`
(Sanskrit), `ta.`, `te.`, `ml.`, `hi.`, `bn.`, or the multilingual `wikisource.org`.

## Bringing a Wikisource's books in

Desk → Ingest Profiles → New, **Source: Wikisource**:

| Field | Meaning |
|---|---|
| **Wikisource Address** | `kn.wikisource.org`, for example |
| **Category of Index Pages** | a category whose Index pages are the books (`Category:Books`) |
| **Index Pages** | Index pages to take, one per line (`Index:Name.pdf`; the `Index:` can be left out). Used with, or instead of, a category |
| **Pages to Take** | which pages' text comes in: *Any text* (every page that has text), *Proofread* (a person has checked it; the default) or *Validated* (checked by a second person too) |

**Check Wikisource** says how many Index pages it finds and shows the first book's details before
anything runs. **Run Ingest** then catalogues each book (an *Index page* is a book) and reads its
pages in the background, like any other run.

## What a book gets

- **Details** from its Index page: title, author(s), year, publisher, language, remarks. A book
  with no title there is named after its scan's file.
- **Page text** of the pages at the level you chose, from the transcription, as plain text
  (formatting templates are unwrapped, the others dropped, links give their words). The book's
  *Text source* says *Wikisource (proofread)* when every page taken was proofread, else *Wikisource*.
- **Page images**: drawn by Wikisource from the scan (Wikimedia Commons), in *Page & text* and in
  the book's [IIIF manifest](iiif.md). The book's page links to its Index page and the scan.
- **Identifier**: `ws-<language>-<scan name>`, such as `ws-kn-Kanaka.pdf`.
- **Rights**: the text is CC BY-SA 4.0 (Wikisource contributors); the scan has its own rights, which
  its file page on Commons states. The book's record says both. Keep the licence if you share
  the text (exports, [ground truth](staff-guide.md#sharing-ground-truth)).

A run reads each book again (the wiki's pages are fetched in bulk); a book whose text and Index
page have not changed is left as it is. **Refresh** on a book (or *Refresh Items Already in
Catalogue* on the profile) reads it again regardless.

## Good to know

- Pages that are not on Wikisource yet (not created, or blank) have no text here; the page image
  still shows. A book is catalogued with the number of pages its scan has.
- This is Wikisource's own transcription: corrections made here (proofreading in Research Desk)
  stay here and are not sent back to Wikisource. Re-reading a book from Wikisource does not undo
  a correction made here: corrected pages are laid over the source text, as for any book.
- Requests are polite: one at a time, with a pause, and a User-Agent that names Research Desk.
- Switched off with *Books from repositories* in [Settings → Features](staff-guide.md#features-and-your-institution).
