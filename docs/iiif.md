# IIIF: the library's books in any viewer

The books can be opened in **Mirador**, **Universal Viewer**, Annona and other viewers that
speak [IIIF](https://iiif.io) (the International Image Interoperability Framework). Each book
has a **manifest**: its title, author, date, language and subjects, one canvas for every page with
the page's image, the PDF, MARCXML and archive.org's own manifest as links, and the text of each
page as an annotation. A scholar can put the library's books next to other libraries' in one
viewer, compare pages, and annotate them with their own tools.

Nothing to set up: a book's **IIIF** button (under *About this book*) is its manifest. Paste that
address into a viewer, or drag it in. IIIF is part of **Sharing metadata** in
[Settings → Features](staff-guide.md#features-and-your-institution): switched off, the addresses
answer *not found*.

## The addresses

All under the portal's address (`https://library.example.org` below):

| Address | What it is |
|---|---|
| `/iiif/<book>/manifest` | the book as a IIIF Presentation 3.0 manifest |
| `/iiif/<book>/text/<page>` | one page's text, as an annotation page that supplements its canvas (the first page is `0`) |
| `/iiif/collection` | every published top-level collection |
| `/iiif/collection/<collection>` | the books of a collection and its sub-collections; a big collection comes in pages of 200 (`?page=2`) |
| `/iiif/image/<book>/<page>/info.json` | the image service of a book whose pages are drawn here (below) |
| `/iiif/image/<book>/<page>/full/800,/0/default.jpg` | a page image from that service |

`<book>` is the book's identifier, as in `/library/item/<book>`.

## Whose images

- **Books on archive.org**: the manifest paints archive.org's page images (the same ones the
  *Page & text* reader shows) and links to archive.org's own IIIF manifest for those who want its
  deep-zoom image service.
- **Books from repositories and the library's own folders**: their pages are drawn here from the
  PDF (or are the book's own photographs), so this library serves them through a **IIIF Image API
  3.0 service at level 2**: any region (`x,y,w,h`, `pct:`, `square`), any size (`w,`, `,h`, `w,h`,
  `!w,h`, `pct:n`, `max`; larger than the page only with `^`), turned in quarters (and mirrored with
  `!`), in colour, grey or black and white, as JPEG or PNG. `info.json` lists 512-pixel tiles at
  every scale, so deep-zoom viewers (Mirador, Universal Viewer, OpenSeadragon) load only what they
  show. One request makes an image of at most 25 million pixels.

Page sizes on a canvas are the first page's (or a standard size for archive.org's books); viewers
read the real size from the image.

## Who may see what

The same as on the portal:

- a book guests cannot find is *not found*; one they can find but not read asks for a login
  (`401`);
- a **members-only** book's manifest and images are served only to logged-in readers, are not
  cached by shared caches, and carry no cross-site permission, so a viewer on another site cannot
  open them with a reader's login;
- public books are open to viewers on any site and cached for five minutes (images for a week).

## Using it

1. Open a book's page and press **IIIF**, or take `…/iiif/<book>/manifest`.
2. In Mirador, *Add resource*; in Universal Viewer, `?manifest=<address>`.
3. For a whole collection, add `…/iiif/collection/<collection>`.

Aggregators and other libraries can harvest `/iiif/collection` the same way as the
[OAI-PMH set](koha.md) lists.
