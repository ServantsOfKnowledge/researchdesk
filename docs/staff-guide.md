# Staff guide: a tour of the Desk

This page is for library staff who look after Research Desk: bringing books in, correcting the
catalogue, building collections and deciding who can read what. Installing and running the
server is covered in [Getting started](getting-started.md) and [Operations](operations.md).

Log in, and you land on the **Research Desk** workspace (also at `/app/research-desk`). Readers
never see the Desk; they use the portal at `/library`.

## The Research Desk workspace

![The Research Desk workspace with the getting-started checklist](../sok_resdesk/public/images/guide/desk-workspace.png)

- **Get started with Research Desk**, at the top, is a checklist for a new library (see
  [below](#the-getting-started-checklist)). Hide it when you're done.
- **Shortcuts**: Ingest Profiles, Items, Collections, Background Jobs, Open Portal, Settings and
  Help.
- **Cards** list everything else: the catalogue (items, collections, authors, subjects), ingest
  (profiles, runs, background jobs), setup, readers (sign-up requests, users) and metadata
  (exports, spreadsheet imports, push targets).

## Help, tours and the checklist

### Help on every screen

Every Research Desk screen has a **Help** menu at the top:

- **Help for this screen** opens this documentation at the right section, inside the Desk.
- **Take the tour** (on the main forms) walks through the important fields one at a time. Press
  **Next** to move on, or **Close** to stop.
- **All help pages** lists everything, for staff and for readers.

![Take the tour: an ingest profile, one field at a time](../sok_resdesk/public/images/guide/desk-tour.png)

![Help inside the Desk](../sok_resdesk/public/images/guide/desk-help.png)

The same pages are on GitHub, and readers have their own help on the portal at `/library/help`.

### The getting-started checklist

Six steps take a new library from an empty install to a working portal: name and logo, a first
selection of books, watching the ingest, access, a first collection, and this guide. Each step's
button opens the right screen, often with its tour. Steps tick themselves when the library has
done them some other way (a logo is set, an ingest has finished, a collection exists). **Skip**
sets a step aside; **Hide checklist** removes the whole block once you don't need it.

To see the checklist again: Help → menu (⋯) → **Restart the getting-started checklist**. Only
managers see it.

## Bringing books in

An **ingest profile** says which books to bring in and how often: an archive.org collection or
search, a list of identifiers, or IA-style folders on your own disk or server. Press **Check
Count** to see how many books match, then **Run Ingest**.

![An ingest profile](../sok_resdesk/public/images/guide/desk-profile.png)

Books arrive in batches in the background. Only the details and the text of each page are
downloaded; scans stay on archive.org (or your server) and are shown from there. Details:
[Choosing & ingesting books](ingesting.md) and [Your own folders & servers](local-folders.md).

**Background Jobs** shows every run, queued job and schedule, with progress, and lets you
**Pause** and **Resume** a run, **Pause All** background work, or stop it
([more](operations.md#background-jobs-see-pause-and-stop-what-is-running)).

![Background Jobs](../sok_resdesk/public/images/guide/desk-jobs.png)

## The catalogue

**Items** lists every book. Filter the list like any Desk list (by language, collection, type,
who can see it…), tick books to act on many at once (**Actions → Add to / Remove from Collection** or **Set
Who Can See Them**), or open one to edit it. The menu (⋯) does the same for every book matching
the filters, and exports their metadata.

![The Items list](../sok_resdesk/public/images/guide/desk-items.png)

On a book's form you can correct the title (and add a romanised title), authors, date,
publisher, language, subjects, document type, collections and rights. Your changes reach the
portal and search within seconds, and **Keep My Edits** is ticked so that bringing the book in
again doesn't overwrite them. See [Editing catalogue details](collections-and-metadata.md#editing-catalogue-details).

To change many books at once, export a spreadsheet, edit it and import it back
([how](collections-and-metadata.md#editing-many-books-with-a-spreadsheet)).

### Authors and subjects

**Creators** and **Subjects** are made automatically from the books' details, one record per
person or heading, so the portal can filter by them. Open a creator to add a romanised name,
a sort name (Family, Given), or its VIAF and Wikidata identifiers.

## Collections

A **collection** is your own group of books with its own page on the portal: a subject, an
author, a course, an exhibition. Add books by hand, in bulk from the Items list or a portal
search, with a spreadsheet, or with rules that also catch new books as they arrive.

![A collection with rules](../sok_resdesk/public/images/guide/desk-collection.png)

Details: [Curated collections](collections-and-metadata.md#curated-collections).

## Who can see what

Each book is **Public**, **Login to read** (anyone finds and cites it; members read it) or
**Login to find** (members only). A site-wide setting decides what visitors who aren't logged in
can do, and another how readers get accounts: added by staff, open sign-up, or sign-up with
approval (requests wait under **Reader Requests**). Details: [Who can see what](access.md).

## Metadata out

- **Exports**: the catalogue, or part of it, as a spreadsheet, MARCXML for Koha, MODS or Dublin
  Core, JSON-LD, BibTeX/RIS, or files for archive.org.
- **Push Targets**: send details straight to the Internet Archive, Koha, Wikidata or another web
  service. Start with a dry run.
- **OAI-PMH**: Koha and other systems can harvest the catalogue, or a single collection.

See [Collections, metadata & pushing](collections-and-metadata.md) and [Koha](koha.md).

## Settings

**Settings** (RD Settings) holds everything that applies to the whole library:

| Section | What you set there |
|---|---|
| Portal | the library's name, tagline, public web address, OAI identifier and admin email |
| Logo & Branding | logo, browser-tab icon and a picture for the home page |
| Search Engine | the Meilisearch address and whether page text is indexed; **Rebuild Search Index** |
| Internet Archive | contact sent with requests, delay between requests, books per batch, page-text cache, pausing schedules |
| Access & Sign-up | what visitors can do, the default for new books, reader accounts, what OAI-PMH shares, access rules |

![Settings](../sok_resdesk/public/images/guide/desk-settings.png)

Take the tour on the Settings form for the fields most libraries change first.

## Roles

| Role | Can |
|---|---|
| ResDesk Manager | everything: settings, ingests, background jobs, access, pushes, readers |
| ResDesk Cataloguer | edit books, authors, subjects and collections; exports and spreadsheet imports; read ingest runs |
| ResDesk Reader | the portal only: read members-only books |

Give staff a role under **Users** in the Desk ([more](operations.md#users-and-roles)).
