# Permanent links, preservation and OCR quality

Three things that keep a digital library trustworthy over decades: every book has a link that
never breaks, the library keeps its own checked copy of its books, and it knows which books have
text too poor to search.

## Permanent links (ARKs)

Every book gets an **ARK** (Archival Resource Key) when it is first catalogued, such as
`ark:/99999/b1x7k2m9q`. It is shown on the book's portal page as **Permanent link**, on the
book in the Desk as **Permanent ARK**, and it is what citations, exports, OAI-PMH records and
pushes to Koha, Wikidata and the Internet Archive use as the book's address.

- The portal resolves ARKs itself: `https://<your portal>/ark:/99999/b1x7k2m9q` opens the book.
- Add `/n42` for a page: `…/ark:/99999/b1x7k2m9q/n42` opens the book at leaf 42 (the 43rd page
  image, counted from 0 as archive.org does; printed page numbers repeat, leaves never do).
- Add `?info` to get a short metadata record instead (who, what, when, where), as the ARK
  standard asks.
- The name says nothing about the book, on purpose: it never has to change when a title or
  date is corrected. The last character is a check character that catches a mistyped one.

### Your NAAN

The number after `ark:/` is the library's **NAAN**, given free by the ARK Alliance
(arks.org → *Request a NAAN*). Until you have one, books get ARKs under `99999`, the Alliance's
test number. When yours arrives, enter it in **Settings → Persistent Identifiers → ARK NAAN**:
every book's ARK is made again under it, keeping its name (only the number and the check
character change). After that the NAAN can't be changed in Settings: ARKs under it are
promises to everyone who cited them.

The resolver address in every ARK is your portal's address, so choose a domain you expect to
keep.

### Tombstones

A book that is deleted leaves a **tombstone** (Research Desk → *Tombstones*): its ARK then
opens a page saying what the book was, what happened to it and, for a merged record, where to go
instead (set **Replaced By** and a **Note for Readers** on the tombstone). A book that is only
unpublished says so, and its ARK leads to it again when it comes back. A permanent link never
ends in "page not found".

## Preservation copies

Most books exist only on archive.org. If an item is removed there, the catalogue record and the
page text remain, but not the book. Preservation keeps the library's **own copy** of each book
and proves, on a schedule, that it is unchanged.

Set it up in **Settings → Preservation**:

| Setting | |
|---|---|
| Preservation Folder | where the copies go. In Docker it is `/preservation` (a Docker volume; set `PRESERVATION_DIR` in `.env` to a disk or NAS folder instead, writable by uid 1000). On a native install, any folder |
| Preserve | *Off*, *Books in collections marked Preserve* (tick **Preserve** on a collection), or *Every book* |
| Include Page Images | also the original scans, not only the PDF, OCR and metadata: often 10 to 50 times larger, but enough to make new OCR from |
| Space for Copies (GB) | the most the copies may take (0: what the disk allows; the last 5% is never used) |
| Check Every (days) | every copy is checked at least this often |

Every night (after the backup) the books waiting for a copy are copied, a few hundred at a
time, and a share of the copies is checked. A book's copy holds its files as archive.org
publishes them, each compared with archive.org's md5 as it arrives; a book from your own
folders is copied from its folder.

On the book in the Desk, **Preservation** shows the state (*Preserved*, *Failed check* or
*Missing*), the version, the size and when it was last checked, with **Preserve Now**, **Check
Copy** and **History**.

### What a copy looks like

Copies follow **OCFL** (the Oxford Common File Layout), an open standard: each book is a folder
of its plain files plus an `inventory.json` listing every file with its checksums (SHA-512,
SHA-256 and MD5) and every version of the book. Nothing in it needs Research Desk to be read:
any OCFL tool, or a person with a file browser, can find a book (its folder is named after its
identifier) and check it.

- A book ingested again becomes a new **version** only if one of its files changed, and the
  new version stores only the changed files.
- Versions are never rewritten: an earlier state of a book can always be recovered.

### Checks and alerts

A check reads every file of the copy and compares it with the inventory: a file changed (bit
rot, a disk fault, tampering), missing, or not listed is a **failure**. The book is marked
*Failed check*, the failure is recorded with what was wrong, and the Server page shows
*Preservation copies* in red and sends an alert (by Desk notification, email or webhook, as set
in Settings → Server & Updates).

### Preservation events

**Preservation Events** (Research Desk → *Preservation Events*, or **History** on a book) is the
book's preservation history, in the spirit of PREMIS: each copy made (with its version, the
files and bytes added), each failed check (with what was wrong), and a copy that checks out
again, with when, by whom and the outcome. Checks that pass only update the book's *Fixity
Checked On*, so the list stays readable.

Coming next: a second copy in another place with automatic repair from the good one, and BagIt
packages for handing a collection to another archive ([roadmap](roadmap.md)).

## OCR quality

Each book has an **OCR Quality** from 0 (garbage) to 100 (clean), and the number of
**Low-Quality Pages** (below 50). They are worked out from the page text itself, in Kannada,
Devanagari, Tamil, Telugu, Malayalam, Bengali, Gujarati, Gurmukhi, Oriya and Latin script, by
looking at what broken OCR leaves behind:

- words mixing two scripts (a Latin letter inside a Kannada word);
- Indic words that can't be written: starting with a vowel sign or a virama, two vowel signs in
  a row, a vowel sign straight after a virama;
- words of an impossible length, consonant piles with no vowels, stray symbols and replacement
  characters.

It is a **ranking**, not an accuracy figure: it finds the books and pages that most need better
OCR or proofreading. English with plausible-looking errors ("tbe" for "the") still scores
fairly high, since it uses no dictionary.

Books are scored as they are indexed. Books already in the catalogue are scored in the
background from the page text kept on this server (no archive.org requests): the upgrade starts
it, a daily job continues it, and **Items → ⋯ → Score OCR quality** starts it at once. Sort the
Items list by **OCR Quality** (lowest first) to see the worst books.
