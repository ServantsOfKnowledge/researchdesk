# Permanent links, preservation and OCR quality

Three things that keep a digital library trustworthy over decades: every book has a link that
never breaks, the library keeps its own checked copy of its books, and it knows which books have
text too poor to search.

> **Other kinds of material.** A photograph carries a SHA-256 of its original taken when it comes
> in ([Photographs](photographs.md)), a deposit has a checksum for each file
> ([Repository deposit](deposit.md)), and an offline copy lists what it holds
> ([Offline copies](offline.md)). The library's own checked copies (below) apply to books and any
> item with a PDF; a Calibre library or a folder is read where it is and is never changed.

## Permanent links (ARKs)

Once switched on, every book has an **ARK** (Archival Resource Key), such as
`ark:/12345/b1x7k2m9q`. It is shown on the book's portal page as **Permanent link**, on the
book in the Desk as **Permanent ARK**, and it is what citations, exports, OAI-PMH records and
pushes to Koha, Wikidata and the Internet Archive use as the book's address.

- The portal resolves ARKs itself: `https://<your portal>/ark:/12345/b1x7k2m9q` opens the book.
- Add `/n42` for a page: `…/ark:/12345/b1x7k2m9q/n42` opens the book at leaf 42 (the 43rd page
  image, counted from 0 as archive.org does; printed page numbers repeat, leaves never do).
- Add `?info` to get a short metadata record instead (who, what, when, where), as the ARK
  standard asks.
- The name says nothing about the book, on purpose: it never has to change when a title or
  date is corrected. The last character is a check character that catches a mistyped one.

Libraries that are DataCite members can give chosen collections **DOIs** as well (see the staff
guide, *DOIs*): a DOI points at the book's ARK, and both keep working when a book is deleted.

### Switching ARKs on

ARKs are **off** until the library has its own **NAAN**, the number after `ark:/`, given free
by the ARK Alliance (arks.org → *Request a NAAN*). Until then nothing is minted and nothing
shows, so no temporary identifier can end up in someone's citation.

When the Alliance replies: **Settings → Persistent Identifiers**, enter the **ARK NAAN**, tick
**Give Books ARKs** and save. New books get their ARK as they are catalogued, and the books
already in the catalogue get theirs in the background (about a minute per 50,000 books). The
Alliance's test number (99999) is not accepted.

Once on, the NAAN and the shoulder can't be changed in Settings: ARKs under them are promises to
everyone who cited them. Switching ARKs off again stops new ones and hides them from pages and
citations, but ARKs already given out keep working. The resolver address in every ARK is your
portal's address, so choose a domain you expect to keep.

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
Checked On*, so the list stays readable. Second copies (*Replication*), repairs (*Repair*),
books served from our copy (*Access from copy*) and BagIt exports (*Export*) are recorded too.

## A second copy

One copy on one disk is one fault away from loss. Settings → Preservation → **Second Copy**
keeps a second copy of every preserved book somewhere else:

| Second copy | Where | How it is checked |
|---|---|---|
| **Folder** | another disk, a NAS, or a partner's storage mounted on this server (NFS, SMB, `rclone mount`) | like the first: every file's sha512 against the inventory |
| **S3-compatible** | a bucket on Amazon S3, Wasabi, Backblaze B2, a partner's MinIO or Ceph… (endpoint, region, bucket, an optional folder, access and secret keys) | every file's MD5, which the service checked when the file arrived and keeps (as its ETag), against the MD5 the inventory records, without downloading the files |

The second copy holds the same OCFL objects at the same paths, so each copy can be read on its
own, by any OCFL tool, and each can rebuild the other.

- It is **made right after the first copy**, and every night for books whose second copy is
  missing or behind (Settings → **Preservation → Make Every Second Copy Now** for all at once).
  Only new files travel: a corrected book sends its new version, not the scans again.
- A book's **Copies** field says how many copies it has and how many passed their last check:
  *2 of 2 verified*.
- **Repair.** The nightly checks look at both copies. When one fails (a changed or missing file)
  and the other is good, the bad one is rebuilt from the good one: copied whole into a temporary
  place, checked against its inventory, and only then put in place of the bad one. The repair is
  recorded on the book. When both fail, both are marked and the Server page alerts.
- On the book form, **Preservation → Make Second Copy** and **Check Copy** do the same for one
  book at once.

For S3 the server uses the `boto3` package, installed with Research Desk. Files are uploaded whole, with
their MD5, so the service refuses a damaged upload; a file uploaded to the bucket in parts by
another tool can't be checked this way and is reported.

## Serving a book from our copy

When archive.org stops serving a book (it was taken down, or *darkened*), the daily sync takes it
off the portal. For a book we hold a copy of, the library can keep it instead:

- **Book by book** (the default): Preservation → **Serve From Our Copy** on the book form. The
  portal then shows the book with its PDF from our copy, through Research Desk (archive.org's page
  images aren't in the copy unless *Include Page Images* was on, so *Page & text* shows the text
  and a link to the PDF). **Stop Serving From Our Copy** undoes it.
- **Always**: Settings → **Keep Dropped Books on the Portal**: the sync keeps every dropped book we
  hold a PDF of, served from our copy, and lists them in the profile's log.

archive.org often darkens books for rights reasons, so decide before serving a book again. Each
change is recorded as an *Access from copy* event.

## Handing books to another archive (BagIt)

**Export BagIt** makes [BagIt](https://www.rfc-editor.org/rfc/rfc8493) bags (the packaging
libraries and archives exchange collections in) of the newest preserved version of books:

- on a **book** form (Preservation → Export BagIt): downloads at once;
- on a **collection** form (**Export BagIt**): all its preserved books, bagged in the background,
  with a notification when the file is ready.

One zip file holds one bag per book: `bagit.txt`, `bag-info.txt` (the library, the book's ARK or
identifier, its title, the date), `data/` with the book's files, and SHA-512 manifests. Any BagIt
tool validates it (the Library of Congress's `bagit-python`, Archivematica, DSpace). Exports are
written to `exports/` in the first copy's folder, listed in Settings → **Preservation → BagIt
Exports** for download, and removed after two weeks (make them again any time).

## OCR quality

Each book has an **OCR Quality** from 1 (garbage) to 100 (clean; 0 means not scored yet), and the number of
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

OCR Quality is a column of the Items list, and **Background Jobs → Machine** shows how many books
are scored, with **Score now** and **Worst first** (the Items list, lowest score first).

Books are scored as they are indexed. Books already in the catalogue are scored in the
background from the page text kept on this server (no archive.org requests), one job working
through them all: the upgrade starts it, a daily job picks up what is left, and **Score now**
(or **Items → ⋯ → Score OCR quality**) starts it at once. A book whose page text isn't kept on
this server shows *Low-Quality Pages* −1 and is scored the next time it is indexed. Sort the
Items list by **OCR Quality** (lowest first, with a filter *OCR Quality > 0*) to see the worst books.
