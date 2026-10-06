# SRU: the catalogue for older library systems

SRU (Search/Retrieve via URL) is how many library systems, union catalogues and Z39.50 gateways
search another catalogue over the web. Research Desk answers SRU 1.2 at `/sru` on the portal, for
example `https://library.example.org/sru`, with MARCXML or Dublin Core records.

Visit the address with no arguments and the server describes itself (an *explain* record: where
it is, which indexes and record formats it offers).

## Searching

    /sru?operation=searchRetrieve&query=title%3D%22red%20fort%22&maximumRecords=10&recordSchema=marcxml

| Parameter | What it does |
|---|---|
| `query` | a CQL query (below), required |
| `startRecord` | the first record to return, from 1 (default 1) |
| `maximumRecords` | how many records (default 10, at most 50) |
| `recordSchema` | `marcxml` (default) or `dc` (Dublin Core) |

**CQL**, the query language, as catalogues use it:

| Write | Meaning |
|---|---|
| `kanakadasa` | the word in a title, author or description |
| `title = "red fort"` | a title containing the phrase |
| `author = basava` | an author (`creator` and `dc.creator` mean the same) |
| `subject = "vachana literature"` | a subject |
| `identifier = ark:/…` | an item id, ARK, DOI, ISBN or other identifier |
| `date = 1880` | the year |
| `language = kan` | the language |
| `title all "red fort"` | every word, in any order |
| `title any "red fort"` | at least one word |
| `title exact "Vachanas"` | the whole title |
| `a and b`, `a or b`, `a not b` | combine; read left to right, brackets group |

Mistakes come back as SRU *diagnostics* (a normal answer that names the problem: an unknown
index, a query that does not parse, a record position past the end), never as a web error.

## What it shows

The same records OAI-PMH shares, under the same rule: Settings → Sharing & Identifiers →
*OAI-PMH Scope* (by default records a guest can find). SRU is switched off with Settings →
Features → *Sharing metadata*, which also controls OAI-PMH, [OPDS](opds.md) and [IIIF](iiif.md).

## Using it

* **Koha** (copy cataloguing): add it under Administration → Z39.50/SRU servers as an SRU server,
  with the portal's host and port, the database `sru` and MARCXML records.
* **Z39.50 only**: Z39.50 is a separate binary protocol that Research Desk does not speak. A
  Z39.50 client reaches this catalogue through a Z39.50-to-SRU gateway (for example one built on
  YAZ), which turns its searches into the requests above.
* Anything else that harvests whole catalogues should use [OAI-PMH](koha.md#other-standards).
