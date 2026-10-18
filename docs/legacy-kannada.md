# Old Kannada font text

Before Unicode, Kannada was typed in fonts (Nudi, Baraha, ShreeLipi, Akruti and others) that put Kannada
letters on the Latin keys. A PDF made with such a font keeps those characters as its text: the book
reads as `PÀ£ÀßqÀ` instead of `ಕನ್ನಡ`, and no search finds anything in it. Research Desk converts such
text to Unicode with the Sanchaya **Kannada Font Converter** (<https://converter.sanchaya.net>), so the
book can be searched.

## While books are read in

Settings → **Convert Old Kannada Fonts in PDF Text**: choose the font the books were made in (or *Off*, the
default). From then on, when Research Desk reads a PDF's text layer (books from folders and from
repositories), every page that looks like old-font text is converted to Unicode before it is shown and
searched. Pages already in Unicode, and English pages, are left alone.

- **One font at a time.** The setting names one font; a library with books in several fonts changes it
  between ingests, or converts the odd page by hand (below).
- **Books already in the library** are converted when they are ingested again,
  because the text comes from the PDF each time.
- **Scans read with OCR** are not affected: OCR already writes Unicode.
- **A page is judged by its characters**: full of accented Latin characters and nearly without Kannada.
  A page of French or of English with an accent or two is not touched.
- **It is not fast.** The engine converts about five thousand characters a second at worst, so a
  400-page book takes some minutes; it runs in the background with the ingest, in batches.
- **It never stops an ingest.** If the converter cannot run (Node.js missing, an error), the text is kept
  as it was and the failure is written to the Error Log.

## Converting text by hand

Desk → Running the Library → **Convert Old Kannada Text**: pick the font and the direction (old font to
Unicode, or back), paste the text, **Convert**. Up to 50,000 characters at a time (about ten calls a minute); nothing is saved.
Managers and cataloguers can use it. The same is available as `sok_resdesk.legacy_kannada.convert_text`
([API](api.md)).

## The fonts

Nudi / Baraha, ShreeLipi (KAN-850), Prakashak (Praja), Akruti (Mono and Bi), Surabhi (KND-series and KN),
ISM (KNTT-Nandi and KNB TT-Nandi), Dharma ILs, Janna Mono, SriLipi 850, Shree Deccan, Suchi Kan and WinKey
KanEng.

**How accurate it is depends on the font.** Nudi/Baraha is the most thoroughly tested; the other fonts
have known gaps (conjunct letters especially), listed per font on the converter's own
[status page](https://converter.sanchaya.net/status.html). Check a sample of each book, and keep the
original PDF: the converted text is for searching and reading, and a proofreader can correct it as any page
text.

## How it works, and its licence

The engine is the converter's own `js/app.js`, copied **unmodified** into
`sok_resdesk/vendor/kannada_font_converter`, and run on the server as a separate `node convert.js`
program that takes text as JSON and gives text back. Frappe's build already needs Node.js, so nothing
more is installed.

That code is licensed **GPL-3.0-or-later** (the converter's licence); the rest of Research Desk is MIT. They
stay separate works: this directory keeps its own licence and notice, and Research Desk only runs it as a
program. If you redistribute Research Desk, keep that directory, its `LICENSE` and the notice in `app.js`
together. To take a newer converter, copy `js/app.js` and `LICENSE` from
<https://github.com/sanchaya/kannada-font-converter> and run `pytest sok_resdesk/tests/unit_legacy_kannada.py`.

## What it does not do yet

- It does not find a PDF's font by itself: the setting names it.
- It does not convert books that are already indexed without re-ingesting them.
- It has not been tried on a real old-font PDF in this repository's tests: the tests use text the
  converter itself produces. Try one book first.
