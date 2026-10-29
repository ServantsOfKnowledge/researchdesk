# What Research Desk does

The short version is on the project's front page. This is the whole list. It is written for libraries,
archives, schools and colleges, and **universities and research institutions** (their repositories, theses,
publications, datasets' catalogue records, archives and special collections).

Choose a collection, a search or a list of items on archive.org, or point it at your own
folders, and Research Desk will:

- ingest from **archive.org** (a whole collection is listed on the portal within minutes, from
  archive.org's search records in bulk, or from a **metadata file** made with the `ia` tool;
  page text follows in the background) *or* from
  **IA-style item folders** on your own disk, NAS or web
  server, with a drop folder that picks up new and changed books automatically, *or* from
  **institutional repositories** (DSpace, EPrints and any other that offers OAI-PMH), their
  PDFs' text read page by page
- bring in **your own material**: books and loose PDFs from folders, **manuscripts and palm
  leaves** (a folder of leaf photographs, with leaf labels such as 1a, 1b and transcription from
  blank), **photographs** (EXIF, who and where, tagged with Wikidata, a checksum of the original),
  **audio and video** (a player with a time-coded transcript), a **Calibre library** read in
  place, **Wikisource** books with their proofread pages, and **deposits** that people make
  themselves and a reviewer accepts (licence and embargo included)
- **serve a government or institution** (the optional *governance edition*, [installed only when asked for](installation.md#editions)): records with a level and a department, a clearance per person, offices that see downward, a tamper-evident audit log of who viewed, downloaded and changed what, a Classified mode for Secret and Top Secret records, a read-only public mirror on another server, retention rules with legal holds, a file register, requests to see records with redaction, and LDAP and single sign-on ([Government and institutional use](governance.md))
- **describe archives** as archivists do: fonds, series, file and item (ISAD(G)), browsable on
  the portal, exported as **EAD3**, with digitised items placed in the hierarchy
- **stay in step with archive.org** by itself: every day, books added to a collection come in,
  changed ones are refreshed and removed ones are unpublished, and every archive.org collection
  the books belong to (sub-collections too) gets a portal page that keeps itself up to date
- **catalogue** the books, cleaning up messy metadata (languages, dates, authors, subjects), with a
  **review queue** of records that need a cataloguer's eye (no year, a language that doesn't
  match the title's script, possible duplicates…) and **authority control**: authors matched to
  Wikidata and VIAF, subjects to Library of Congress Subject Headings
- **index the full OCR text page by page**, so people can search *inside* 88,000+ books,
  in Kannada, Hindi, Konkani, Tamil, English and more, typing in the script or **in Latin
  letters** (`kanakadasa` finds ಕನಕದಾಸ), with "phrases", `OR` and `-words`
- give each book a **public page** with two readers (archive.org's book reader, and **Page &
  text**: each page image beside its text), search inside the book, and **one Cite window** for
  the book or the page: BibTeX, BibLaTeX, RIS, CSL-JSON, APA, MLA and Chicago, with a link
- let readers keep **notes on pages** (highlights, comments, tags, questions, links, OCR error
  reports; private, shared with a research group, or public after review), following the W3C Web
  Annotation model, exported with page citations, linked to **Wikidata** (pages about a person,
  place or work gathered on one page), and open to other annotation tools through the **W3C Web
  Annotation Protocol**
- **improve the text over time**: an OCR quality score for every page and book; proofreading
  beside the page image, validated by a second person, every version kept; **re-OCR** with
  Tesseract's Indic models, **several languages at once** (the book's languages and English, or a
  language of its own for a verse or footnote), a page part by part (columns, headings) or whole
  books worst first; **machine drafts** (speech to text for recordings, handwriting recognition
  for manuscripts) for people to correct; and share the corrected pages as **open OCR ground
  truth**, each page only if its proofreaders released it under an open licence of their own
  choosing, after a person has reviewed the set
- **link the library's own catalogue**: Koha's (or any library system's) records matched to the
  books here, and *Read online* links sent back into them
- give books **DOIs** from DataCite for chosen collections (optional, for DataCite members)
- give every book and page a **permanent ARK** (on once the library's NAAN is assigned), with
  tombstones so no link ever dies
- **keep its own checked copies** of the books (OCFL, SHA-256, nightly fixity checks, PREMIS-style
  events), a **second copy** in another folder or an S3-compatible bucket with **automatic
  repair** from the good one, books kept on the portal **from our copy** when archive.org drops
  them, and **BagIt** exports for handing books to another archive
- show every book, photograph, manuscript and recording in any **IIIF** viewer (manifests and an
  image service with deep zoom), and offer the library in **e-reader apps** over **OPDS**
- **give back to Wikimedia** under each person's own account: names and author links to
  Wikidata, corrected pages to Wikisource, photographs to Commons, each reviewed before it is sent
- **take the library away**: an offline copy of a collection for USB sticks, phones and **Kiwix**
  (ZIM), a small **Calibre** collection, and this documentation as one EPUB
- fit the institution: tell the installer what kind it is (a small library, a research portal, an
  archive, a manuscript library, a photograph archive…; they combine) and switch any of **nineteen
  features** off, so what is off is not collected
- work with **Zotero, Google Scholar and reference managers** (embedded citation metadata)
- work **alongside Koha** and other library systems (OAI-PMH harvesting and MARCXML import),
  or on its own
- **give a book to archive.org** from the portal or the Desk, under the sender's own archive.org
  account (always public, reviewed before it goes), and see every outside connection (Internet
  Archive, Wikimedia, library systems, repositories, e-readers, open standards, imports and
  exports) by kind, with its status and who may use it, on one **Connections** screen
- answer **SRU** for Z39.50 gateways and older library systems, and give funders a **COUNTER**
  style usage report; keep **Page & text** and the text downloads for logged-in members, to look
  after bandwidth and make scraping harder
- keep the installation safe in a librarian's hands: a **super admin** role for Servants of
  Knowledge holds the installation's own settings, the Server page, security setup and
  credentials, while librarians keep the manager role
- let readers **create an account on one short page** (name, email, password: signed in at once, no email
  to wait for), and **send sign-in and password email** from a mailbox set on one screen (Resend, Gmail, Microsoft 365
  and more, with a test), let readers fill in an optional **About me** (volunteer to review or
  proofread; private support needs for blind, low-vision or other readers), and keep the server
  tidy with **Log QA**, folding Server sections and **gentle upgrades** that restart only what a
  release needs
- take **messages from visitors** on a Contact us page into a Desk inbox, with an optional private
  Telegram alert that says a message came (never what it says) and a *Message us on Telegram* button
- let readers keep a **reading list**, export it as a bibliography, and share it as a link
- keep some books (or everything) **for logged-in readers**: members-only books, a public
  catalogue with reading for members, or an internal library; readers sign up, are approved,
  or are added by staff, and books can be switched in bulk by collection, filter or search
- carry **your library's logo and name** on the portal, the admin bar and the browser tab, with
  an **About page** introducing the library and how to use it, edited in the Desk, and **pages of your own** (`/p/…`) so the portal can serve as an organisation's website too
- for a school or small library with no library system, **lend books**: members with printable ID cards (and
  sign-up with the ID number), a circulation desk with barcode scanners, holds, fines and acquisitions,
  switched off unless the library asks ([Members, lending and acquisitions](lending.md))
- let staff build **curated collections** (by hand, in bulk or by rules), each with its own
  portal page and OAI-PMH set, and **correct catalogue details** that survive re-ingest
- **export metadata** as a spreadsheet, JSON, Dublin Core, MODS, MARCXML, JSON-LD, BibTeX/RIS or
  Internet Archive upload files, and **edit many books at once** by importing an edited spreadsheet
- **push metadata** to the Internet Archive, Koha, Wikidata or any web service (webhook), with a
  dry run first and automatic updates when a book is edited
- be **accessible**: keyboard and screen readers throughout, Kannada and other Indian-language
  text marked so screen readers use the right voice, pages read aloud, notes and proofreading
  without a mouse (WCAG 2.2 AA and GIGW 3.0; see [Accessibility](accessibility.md))
- offer the portal **in Kannada and other languages**: a language switch for readers, and every
  portal phrase (and the library's own words: its name, About page, collections) translated on
  one Desk page or in a spreadsheet
- let readers **type in Kannada, Hindi, Tamil and 20 more languages on any keyboard** in search
  boxes and proofreading (jquery.ime), and pick languages in proofreading by typing a code
- **help on every screen**: the documentation is built into the portal (for readers) and the
  Desk (for staff), with step-by-step tours of the main forms, a getting-started checklist for
  a new library, and first-visit tips for readers
- manage **people and roles** on one Desk page (give or take a role with a tick, invite by
  email, approve sign-ups), see **the library at a glance** on the Desk (books, readers, logins,
  notes, proofreading, preservation, portal use), and count **portal use** privately (built in,
  or PostHog, Plausible or Umami; no cookies)
- **keep the machine usable**: resource presets for a laptop, desktop or server, low-priority
  background work, quiet hours that pause heavy work during the day, and a **book limit** worked
  out from the machine's CPUs, memory and disk, so it never takes on more than it can hold
- **move in one file** to another server, or between Docker and a native install
- **see, pause and stop background work** from the Desk: every ingest run, metadata push, queued
  job and schedule on one page; pause a run or everything and carry on later, hold single jobs,
  or stop them
- **look after the server from the Desk**: versions and new releases with their notes, the
  health of every part, **what the server has** (every library and native tool it needs, with
  versions, and installing what is missing from the Desk), nightly backups to download, errors and logs, and alerts by Desk
  notification, email or webhook. With the optional updater helper, upgrade (or go back),
  restart parts and apply resource presets from the Desk too
- go on a server with its own name and **HTTPS from Let's Encrypt** set up by the installer, and
  change the portal's address with one command
- run **in Docker or directly on the computer** (macOS or Ubuntu/Debian), and **upgrade with one
  command** (or one button) that backs up first and tells you how to roll back

It's built to install with one command, for librarians, educators, archivists and
anyone else who can open a terminal. It scales to tens of thousands of books on one server
([measured](scaling.md)). Books can go to archive.org, to Research Desk, or to both: Research Desk is the last link of a scan-to-reader chain Servants of Knowledge builds in the open (TTScribe scanning hardware; [Repub](https://github.com/servantsofknowledge/repub), which crops, straightens, flattens and reads each scan and exports a searchable PDF, text and the images; Research Desk), with OpenScribe still to come.
