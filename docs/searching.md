# Searching

The portal's search page, the site's front page (`/`), has two search modes.

## Books

Searches each book's **title, romanised title, authors (both scripts), subjects, series,
publisher, description** and the first few pages of text. Results show cover, author, year,
language and page count, with matches highlighted.

- **Filters (left):** Collection (the library's own collections), Type (book, periodical,
  thesis…), Language, Decade, Subject, Author and Source collection (the archive.org
  collection), plus a Year range.
  Filters combine: pick *Kannada* and *1950s* to get Kannada books from the 1950s.
- **Sort:** relevance, oldest, newest, title A–Z. Until a reader chooses, books are listed in
  the library's **Default Order** (Settings → Portal; oldest first unless changed) and a search
  with words shows the best matches first (**Best Matches First When Searching**). Books without
  a year come last.
- **Empty search** lists everything, which is useful for browsing by filter.

## Inside the text

Searches the OCR text of **every page of every book**. Each result is a page, with a
highlighted snippet. Clicking it opens the book at that page, with the same words searched
inside the book.

For a recording the "pages" are the **segments of its transcript**, and a hit says the minute
where the words are spoken. For a manuscript they are its leaves (1a, 1b…). Text a machine has
drafted and nobody has checked is searched too, and marked as a draft.

On a book's page, **Search inside this book** lists every matching page. Click one to jump
the reader there.

## Kannada and other Indian scripts

- Type in the script (ಕನ್ನಡ, हिन्दी, …), or in **Latin letters, as you would write it**:
  `kanakadasa`, `vachana`, `karnataka sangeeta`, `dharma`. Research Desk works out the likely
  spellings in the scripts of the library's languages (long or short vowels, ತ or ಟ, ನ or ಣ, ಂ
  before a consonant…), keeps the ones its books really contain, and searches those too.
  **Also searched: ಕನಕದಾಸ** under the result count says what it found. It works the same in
  *Inside the text* and in *Search inside this book* (in the book's own script).
- Exact spellings in IAST are read as written: `ṭīkā`, `śāstra`.
- A romanised title on record is found as before: `hampi` finds *ಹಂಪಿ…*.
- Settings → Search Engine → **Find Indic Spellings** switches this off.
- The search engine tolerates small typos. That helps with OCR noise, but very short words and
  heavily damaged scans will still miss.
- OCR quality varies with the age and print of the original. Research Desk shows what the
  Internet Archive's OCR produced; better OCR (see the [roadmap](roadmap.md)) will improve
  results without changing anything here.

## Phrases, OR and leaving words out

| Type | Finds |
|---|---|
| `karnataka sangeeta` | books (or pages) with both words |
| `"karnataka sangeeta"` | the words together, in that order |
| `purandara OR vachana` | either word |
| `vachana -basavanna` | *vachana*, but not where *basavanna* is |
| `ಕನಕ` (the last word) | also words that begin with it: ಕನಕದಾಸರ |

They combine, and work with romanised words: `"purandara dasa" OR kanakadasa`.

## Links you can share

The address bar always reflects the current search, so you can bookmark or share it:

```
/?q=ವಚನ&mode=pages&language_label=Kannada&decade=1950s
/?creators=Kuvempu
/library/item/<identifier>?page=12&q=ಹಂಪಿ
```

## Limits in this proof of concept

- A search returns at most 10,000 hits (paged 20 at a time). Narrow with filters beyond that.
- Meilisearch holds the page index in memory-mapped files. For collections beyond a few hundred
  thousand books, see [Architecture → Scaling](architecture.md#scaling-path).
