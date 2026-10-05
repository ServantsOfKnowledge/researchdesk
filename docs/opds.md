# OPDS: the library in an e-reader app

OPDS is the catalogue format e-reader apps understand. Point KOReader, Thorium, Moon+ Reader,
Aldiko, Librera or any other OPDS reader at the library and browse and download books on a phone,
tablet or e-ink reader, with no browser.

The address is `/opds` on the portal, for example `https://library.example.org/opds`.

| Address | What it lists |
|---|---|
| `/opds` | the start: newest books and collections |
| `/opds/new` | the newest books (50 a page, with a *next* link) |
| `/opds/collections` | the published collections |
| `/opds/collection/<name>` | one collection's books |
| `/opds/search?q=` | books whose title, author or description match |
| `/opds/opensearch.xml` | tells apps how to search |

Each book carries its title, authors, language, summary, cover and a download link for every file
the library holds (PDF, EPUB, MOBI…).

**Who sees what** is the portal's rule: a book guests cannot find is not listed. A book they can
find but may not read is listed without its downloads. A book held on archive.org or another
repository is listed with a link to its page. To read members-only books an app needs the reader's
login, which most apps do not offer yet, so such books stay out of public feeds.

Switch it off with Settings → Features → *Sharing metadata*, which also controls
[IIIF](iiif.md).
