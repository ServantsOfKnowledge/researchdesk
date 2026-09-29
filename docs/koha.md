# Koha & interoperability

Research Desk can run **on its own** as a discovery portal and digital library, or
**alongside** an integrated library system (ILS) such as Koha. In the second case, Koha keeps
print holdings, patrons and circulation, while Research Desk provides full text, reading and
citation for digitised books. Records flow between them through standards, not custom code.

## Option A: Koha harvests Research Desk over OAI-PMH

Research Desk is an **OAI-PMH 2.0 data provider**:

```
<BASE_URL>/api/method/sok_resdesk.oai.endpoint
```

| | |
|---|---|
| Metadata formats | `oai_dc` (Dublin Core), `marc21` (MARCXML) |
| Sets | source collections (e.g. `ServantsOfKnowledge`, `KannadaUniversity`, `JaiGyan`) |
| Identifiers | `oai:<repository-id>:<IA identifier>` |
| Selective harvesting | `from` / `until` (UTC), `set` |
| Page size | 100 records with resumption tokens |

Try it:

```
…/sok_resdesk.oai.endpoint?verb=Identify
…/sok_resdesk.oai.endpoint?verb=ListSets
…/sok_resdesk.oai.endpoint?verb=ListRecords&metadataPrefix=marc21&set=KannadaUniversity
```

**In Koha versions with the built-in OAI-PMH harvester** ([Koha bug 35659](https://bugs.koha-community.org/bugzilla3/show_bug.cgi?id=35659);
look for *Administration → OAI repositories* in your Koha), add Research Desk as a repository:

1. New repository, with the endpoint above as the URL.
2. Metadata prefix `marc21`; optionally a set.
3. Pick a MARC framework and the item type for e-books, then enable the harvester's
   scheduled job.
4. Koha imports bibliographic records with an **856** link to the Research Desk page and one
   to the Internet Archive, so OPAC users click straight through to read.

Menu names and scheduling differ between Koha versions, so check your version's manual. If
your Koha has no harvester yet, use Option B, or run any external harvester that writes
MARCXML files for Koha's import tools.

Any other harvester works the same way: VuFind, DSpace, BASE, CORE, OCLC WorldCat Digital
Collection Gateway, or your own scripts.

## Option B: import MARCXML files

For a one-off load, or when harvesting isn't set up:

- One book: **MARCXML** on its page.
- A reading list: **My list → MARCXML (Koha)**.
- A whole ingest profile or the whole catalogue (staff only):
  `GET /api/method/sok_resdesk.api.marcxml_all?profile=<profile name>` (logged in).

In Koha: *Cataloguing → Stage MARC records for import* → upload the file, record type
*Bibliographic*, format **MARCXML**, then *Manage staged records → Import*.

### What's in the MARC record

| Tag | Content |
|---|---|
| 001 / 003 | IA identifier / `SoK-ResDesk` |
| 007, 008 | online text resource; date, language (MARC code), place `ii` |
| 020 | ISBN when known |
| 035 | `(IA)<identifier>` |
| 041 | language |
| 100 / 700 | first author / further authors and romanised forms |
| 245 / 246 | title / romanised or alternate title |
| 264 | place, publisher, year |
| 300 | `1 online resource (N pages)` |
| 336 / 337 / 338 | RDA content, media and carrier types |
| 490 | series |
| 520 | description |
| 533 | electronic reproduction note (Servants of Knowledge / Internet Archive) |
| 540 | licence / rights |
| 653 | subjects (uncontrolled) |
| 856 40 / 856 41 | Research Desk page / Internet Archive |

Records validate against the Library of Congress MARC21 slim schema. Subjects are
uncontrolled (653) because IA subject data is free text; mapping to LCSH or other schemes is on
the [roadmap](roadmap.md).

## Option C: Research Desk on its own

Everything a reader needs (discovery, faceted search, full text, reading, citation) works
without any other system. The Frappe data model can be extended with holdings, patrons and
loans for a complete library system. See [Architecture](architecture.md#towards-a-full-library-system).

## Other standards

| Need | Use |
|---|---|
| Reference managers | citation meta tags, RIS, BibTeX, CSL-JSON (see [Citations](citations.md)) |
| Search engines | schema.org JSON-LD on each book page |
| Page images and the reader | Internet Archive BookReader and IIIF (`iiif.archive.org`) |
| Your own software | [HTTP API](api.md) |
