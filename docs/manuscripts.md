# Manuscripts and palm leaves

Manuscripts, palm-leaf bundles and other handwritten material are catalogued like any book, with
what is special about them kept alongside: a description of the object, leaf labels like *12a* and
*12b*, and a way to transcribe the leaves by hand, with a second person validating each one.

## Describing the manuscript

On a book (Desk → Item), set **Kind of Work** to *Manuscript*. A **Manuscript** section opens:

| Field | Holds |
|---|---|
| Holding Institution, Shelfmark / Accession No. | where it is kept, and its number there |
| Material | palm leaf, paper, birch bark, copper plate, cloth, parchment, other |
| Script | Kannada, Grantha, Telugu, Nandinagari, Tigalari, Devanagari… |
| Leaves, Dimensions (cm) | the count, and the height × width of a leaf |
| Condition | good, fair, poor, fragile |
| Scribe, Date Copied | as the colophon or the cataloguer gives them (*Śaka 1745 (1823 CE)*) |
| Work(s) Contained, Colophon, Provenance | free text |

These show on the book's page under *Details*, and in its IIIF manifest. Books already on archive.org
are described the same way: they stay on archive.org; the description lives here.

## Labelling the leaves

Photographs of a bundle are numbered 1, 2, 3… in the order they were taken, but leaves are cited
by folio. **Actions → Label the Leaves** (on a manuscript) asks:

- **Sides**: *a/b* (1a, 1b, 2a…), *r/v* (1r, 1v…) or *none* (1, 2, 3…);
- **First image of the first leaf**: images before it (a cover, a ruler and colour card) are labelled
  *front 1*, *front 2*;
- **Images that are leaves**: how many from there (0 = all the rest); images after them are *end 1…*;
- **Number of the first leaf**.

The first labels are shown before anything is saved. Once saved, the labels appear in the reader,
in the text that search is given, in citations of a page, and as the canvas names in the IIIF
manifest. **Back to the Source's Numbers** removes them.

## Transcribing

A manuscript has no OCR text to correct, so its leaves are transcribed from nothing: open the book,
**Page & text**, choose a leaf and use **Proofread** to type what it says beside its image. A
proofreader's save is a new version, every version is kept with who made it, and a second person
validates the leaf (as for any page). The first transcribed leaf makes the book searchable as text,
and the book's *Pages proofread* count follows. **Proofreading** on the portal (/library/proofread)
lists manuscripts to transcribe, those with the fewest leaves done first.

## Photographs that are not on archive.org

A folder of photographs of the leaves is a book in a folder source (see
[folders of photographs](local-folders.md#folders-of-photographs-manuscripts-palm-leaves-bound-volumes)):
the leaves are the images in order, the details can come from a `bundle.json`, and the photographs
stay where they are.

## Looking closely

Beside every page image, **Zoom** opens it whole and full screen: the wheel or two fingers zoom,
dragging moves it, double-click zooms in, **↻** turns it a quarter, and `+` `−` `0` and the arrow
keys work from the keyboard. Other viewers (Mirador, Universal Viewer) open the book's IIIF
manifest, and its [image service](iiif.md) serves regions and tiles for deep zoom.

## What is not here yet

Reading handwriting automatically (handwritten-text recognition) is planned. Until then
transcription is by people, and a library can share the corrected leaves as ground truth
(Settings → Proofreading) to train a recogniser.
