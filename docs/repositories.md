# Books from repositories (DSpace, EPrints, OAI-PMH)

University and institutional repositories, national digital libraries and journal systems
publish their catalogue over **OAI-PMH**, the harvesting protocol libraries have shared for
twenty years: DSpace, EPrints, Islandora, Fedora, OJS, Koha, Greenstone and most others.
Research Desk can harvest one, so its theses, rare books and reports sit in the same portal
as your archive.org books, searchable inside their text, in Kannada and every other script.

The repository stays the **store of record**: each book's page on the portal links to its
record and its PDF there. Research Desk keeps the catalogue entry and the text.

## Setting it up

Desk → Research Desk → **Ingest Profiles** → New, and choose **Source: Repository (OAI-PMH)**.

| Field | Meaning |
|---|---|
| **Repository's OAI-PMH Address** | the repository's OAI-PMH base address. DSpace 7 and later: `https://<host>/server/oai/request`; DSpace 6: `https://<host>/oai/request`; EPrints: `https://<host>/cgi/oai2`; OJS: `https://<host>/index.php/<journal>/oai`. The repository's help pages or its *About* page usually say |
| **Set (optional)** | only this set's records: in DSpace a community (`com_…`) or collection (`col_…`). Empty: the whole repository |
| **Identifier Prefix** | starts each book's catalogue identifier, e.g. `kud` → `kud-123456789-42` (from the record `oai:…:123456789/42`). Made from the repository's address when left empty. Keep it once books are in: it is part of their addresses |
| **Metadata Format** | `oai_dc` (simple Dublin Core), which every repository offers. Leave it |
| **Find Each Record's PDF** | when a record doesn't name its PDF, look on its web page for it: repositories mark it for Google Scholar (`citation_pdf_url`). On by default |
| **Fetch Full Text** | read each PDF's text, page by page, for search inside the book |
| **Maximum Items** | stop after this many records (`0` = all). Try 20 first |
| **Refresh Items Already in Catalogue** | harvest every record again, not just the changed ones |
| **Schedule** | *Daily* or *Weekly* keeps the portal in step with the repository |

**Check Repository** asks the repository for its name, its sets (so you can pick one), and one
record, showing how it will be catalogued, its web page and its PDF. **Check Count** shows how
many records the repository has, when it says. Then **Run Ingest**.

## What happens

1. **Harvesting**: the run asks the repository for its records (`ListRecords`, page after page),
   politely: one request at a time, a pause between them, and waiting when the repository asks
   (`503 Retry-After`).
2. **Cataloguing**: each record's Dublin Core is cleaned up like an archive.org record:
   languages to ISO codes, the year of publication picked out of the record's dates (not the
   day it was deposited), authors, subjects, the licence when it is a Creative Commons address.
   A second title becomes the other-script title. The repository's name becomes the book's
   collection, so readers can filter by it. Theses, reports and periodicals get their item type.
3. **The PDF**: the record's own PDF link, or the one on its web page. With *Fetch Full Text*
   the PDF is read once: its text layer becomes the book's page text, page by page, so search
   finds the page and **Page & text** shows it. The PDF itself is not kept here.
4. **Later runs** ask only for records changed since the last harvest (*Harvested Up To* on the
   profile). Changed records are catalogued again; records the repository deleted are taken off
   the portal (*Removed from Its Source*), and put back if they return.

A record whose datestamp hasn't changed is skipped without asking for its PDF again.

## What readers see

The book's page has its catalogue entry, citations in every format and, under **Book reader**,
buttons for **Open the PDF** and **The record in its repository** (other sites' PDFs usually
can't be shown inside this portal's page). **Page & text** shows the PDF's text page by page,
with page links and page citations, notes and proofreading as for any book.

## Scans without text

Many older theses and books in repositories are scans whose PDF has no text layer. Those are
catalogued (they appear in searches by title, author and subject) with *Text Taken From: PDF
without text (scan)*. Reading their text with OCR as they come in is the next release.

## Things to know

- **Restricted records**: a record whose PDF the repository doesn't give out (embargoed, members
  only) is catalogued without text. Set the profile's **Access for Its Books** if the catalogue
  entries themselves should be for members only.
- **Very large PDFs** (over 300 MB) are linked but not read.
- **Your own repository**: harvesting your own DSpace into Research Desk adds search inside the
  text in Indic scripts, page citations, notes and the reader's other tools to it; the records
  stay managed in DSpace.
- Research Desk also **publishes** its own catalogue over OAI-PMH, for repositories and
  aggregators to harvest: see [Koha & interoperability](koha.md).
