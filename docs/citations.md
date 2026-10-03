# Citations & reading lists

## On every book page

The **Cite this book** box offers:

| Format | Use it with |
|---|---|
| BibTeX / BibLaTeX | LaTeX, Overleaf, JabRef |
| RIS | Zotero, Mendeley, EndNote, RefWorks |
| CSL-JSON | Zotero, Pandoc, any CSL processor |
| APA 7, MLA 9, Chicago 17 | paste straight into a paper |

**Copy** puts the current tab on the clipboard; **Download** saves a file; **MARCXML** gives
a library catalogue record (see [Koha](koha.md)).

### Citing a page

In **Page & text** on a book page, **Cite this page** gives the same formats for the page you
are on: *p. 42* when a number is printed on it, or *leaf 7* (the page image, counted from 0)
when none is; roman numbers in front matter stay as printed (*xii*). The link in the reference
opens that page in Page & text; once the library gives its books permanent ARKs it is the page's
own ARK (`…/ark:/…/n41`). BibTeX gets `pages`, RIS `SP`, CSL-JSON `page`.

### Books in Kannada and other scripts

Titles and names are kept in the original script. When the record has a romanised form, it
is added in square brackets, which is how most style guides want it:

```
Shenoy, K. S. (1955). ೧೮೫೭ರ "ಸಿಪಾಯಿ ದಂಗೆ" ೪೬ [1857 Ra "Sipayi Dhangye" 46]. ಒಂದಾಣೆ ಮಾಲೆ, ಮಂಗಳೂರು. https://…
```

Honorifics (Sri, Shri, Dr., Prof., Smt., Pandit …) are dropped from the name used for
sorting and initials. Single-name authors (common in Indian bibliography) are cited under
that name.

BibTeX entries carry the Internet Archive identifier and ARK in `note`, plus `url`,
`urldate`, `language` and `pagetotal`.

## Zotero, Google Scholar and friends

Each book page embeds:

- `citation_*` meta tags (Highwire Press), read by Zotero and Google Scholar
- schema.org `Book` JSON-LD, read by search engines
- a COinS span (OpenURL), read by older reference-manager plugins
- `<link rel="alternate">` to the BibTeX and RIS files

With the Zotero Connector installed, clicking its button on a book page saves a complete
record, including a link to the PDF when the book is openly available.

## My list: reading lists and shared bibliographies

- Click **＋** on any search result, or **Add to my list** on a book page.
- **My list** (top right of the search page) exports the whole list as BibTeX, RIS, CSL-JSON,
  APA or MARCXML.
- **Copy share link** makes a URL like `/?list=id1,id2,id3`. Anyone who opens it gets
  those books added to their own list, which is handy for course readings or a research group.

The list is stored in your browser; nobody needs an account. (Accounts and saved, shared
lists on the server are on the [roadmap](roadmap.md).)

## For developers

```
GET /api/method/sok_resdesk.api.cite?item_id=<id>&format=bibtex|biblatex|ris|csl-json|apa|mla|chicago[&download=1]
GET /api/method/sok_resdesk.api.cite_many?item_ids=["id1","id2"]&format=ris
```

See [API](api.md).
