# Photographs

A photograph is an item of its own: one picture with its details, kept as it came. Libraries and archives
that hold photographs (a family's, a temple's, a newspaper's, a field worker's) switch on **Photographs**
in Settings → Features. Libraries and archives of every kind include it, and the *Manuscript library or
archive* and *Photograph archive* kinds are for those that mostly hold such material; only the
*Language-technology partner* kind leaves it out.

## Bringing photographs in

In a Folder or Server profile tick **Each Image Is a Photograph**. Every JPEG, PNG or TIFF under the
folder becomes a photograph. (Without the option a folder of images is one book: the leaves of a
manuscript, see [Manuscripts and palm leaves](manuscripts.md).) The pictures stay where they are.

Details come from two places, a person's words winning over the camera's:

- **The camera's EXIF**: when it was taken (which also gives the year), the camera, who took it, a description and
  the copyright when the camera has them, where it was taken (latitude and longitude), and the size.
- **A `<name>.json` beside the picture** (`Ratha at dusk.jpg` and `Ratha at dusk.json`):

```json
{
  "title": "The ratha at dusk",
  "creator": ["K. Ramesh"],
  "date": "1987-03-14",
  "description": "The car festival at the Udupi Krishna temple.",
  "subject": ["festivals", "Udupi"],
  "licenseurl": "https://creativecommons.org/licenses/by-sa/4.0/",
  "photo": {
    "people": ["A priest"],
    "place": "Udupi",
    "event": "Paryaya 1987",
    "depicts": ["Q1234", "Q99 Udupi Krishna Temple"]
  }
}
```

Without a `.json` the file's name is the title. What is read from the files fills the *Photograph*
section on the item while it is empty and is never put back over a person's edit.

## What is kept

- **The original, untouched**, with a **SHA-256 taken when it was brought in**, shown on the photograph's
  page. If the file changes, the next run notices and takes a new one.
- **Access copies** are drawn from it as needed (a screen-size picture, a small thumbnail, any region at any
  size for deep zoom), and the original can be downloaded where access allows. The originals are what
  *Preservation* keeps when it is on.
- **Tags**: subjects like any book's, and who is shown, where, the event, and the **Wikidata items** it
  depicts (`Q` numbers), ready for sharing with Wikimedia Commons.

## Looking at a photograph

The photograph's page shows the picture with **Zoom** (the wheel, dragging, a quarter turn), details
beneath it, citations, and it is a **IIIF** manifest with an image service for Mirador and other viewers
([IIIF](iiif.md)). It is found by its title, subjects, place and people.
