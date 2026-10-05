# Archival description

For archives, manuscript libraries and repositories that keep papers: describe them as the archivist
does, as a hierarchy, and show it to readers. The hierarchy follows **ISAD(G)**, the international
standard, and a fonds or collection can be taken out as an **EAD3** finding aid. Books, photographs,
manuscripts and recordings stay items; description is how they are arranged and understood.

The feature is **Archival description** (Settings → Features), on for archives, university
repositories and manuscript libraries and archives.

## Describing

Research Desk → **Archival Description** (the list, or **Hierarchy** for the tree). Each *unit* has:

- the essentials (ISAD(G) area 3.1 and 3.2): **reference code**, **title**, **level** (fonds,
  sub-fonds, collection, series, sub-series, file, item), **dates** (as written, with first and last
  year for sorting), **extent** and **creator**;
- as far as you have them: administrative or biographical history, custodial history, scope and
  content, system of arrangement, conditions of access and of reproduction, language, physical
  characteristics, finding aids, related units and notes (paragraphs are separated by a blank line).

The **reference code** is the unit's permanent name and is in its web address: letters, digits and
`. _ -` only (for example `UAS-1-2-14`). Units nest by **Part of**. The rules follow the standard: a
fonds or collection is the top and has no parent, a series sits under a fonds (or sub-fonds), a file
under a series, an item under a file; a collection holds anything below it; nothing sits under an
item. **Add a Part** on a unit makes a child.

To place a digitised book, photograph, manuscript or recording in the hierarchy, set **Part of
(Archival Description)** on the item. The unit's page then lists it, and the item's page shows where
it sits.

## On the portal

Tick **On the Portal** on the units to show. The archive is at `/library/archive`: the fonds and
collections, and a page for each unit with its description, its parts and its digitised items. A unit
is shown only when it and **every unit above it** are published, and by *Who can see it* as for books
(public, or only logged-in readers): hiding a series hides what is under it.

## EAD3

On a fonds, sub-fonds or collection, **Actions → Download EAD3 (XML)** (and the link on its portal
page) gives the finding aid: the unit and everything under it the reader may see, with levels,
dates, extent, creator and every description field, as EAD3 for archive portals and aggregators.
