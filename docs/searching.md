# Searching

The portal at `/library` has two search modes.

## Books

Searches each book's **title, romanised title, authors (both scripts), subjects, series,
publisher, description** and the first few pages of text. Results show cover, author, year,
language and page count, with matches highlighted.

- **Filters (left):** Language, Decade, Subject, Author, Collection, plus a Year range.
  Filters combine: pick *Kannada* and *1950s* to get Kannada books from the 1950s.
- **Sort:** relevance, oldest, newest, title A–Z.
- **Empty search** lists everything, which is useful for browsing by filter.

## Inside the text

Searches the OCR text of **every page of every book**. Each result is a page, with a
highlighted snippet. Clicking it opens the book at that page, with the same words searched
inside the book.

On a book's page, **Search inside this book** lists every matching page. Click one to jump
the reader there.

## Kannada and other Indian scripts

- Type in the script (ಕನ್ನಡ, हिन्दी, …) or in the romanised form when the record has one:
  `hampi` finds *ಹಂಪಿ…* books whose romanised title is on record.
- The search engine tolerates small typos. That helps with OCR noise, but very short words and
  heavily damaged scans will still miss.
- OCR quality varies with the age and print of the original. Research Desk shows what the
  Internet Archive's OCR produced; better OCR (see the [roadmap](roadmap.md)) will improve
  results without changing anything here.

## Links you can share

The address bar always reflects the current search, so you can bookmark or share it:

```
/library?q=ವಚನ&mode=pages&language_label=Kannada&decade=1950s
/library?creators=Kuvempu
/library/item/<identifier>?page=12&q=ಹಂಪಿ
```

## Limits in this proof of concept

- A search returns at most 10,000 hits (paged 20 at a time). Narrow with filters beyond that.
- Phrase search ("exact words") and boolean operators in the portal are not exposed yet.
- Meilisearch holds the page index in memory-mapped files. For collections beyond a few hundred
  thousand books, see [Architecture → Scaling](architecture.md#scaling-path).
