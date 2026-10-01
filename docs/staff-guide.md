# Staff guide: a tour of the Desk

This page is for library staff who look after Research Desk: bringing books in, correcting the
catalogue, building collections and deciding who can read what. Installing and running the
server is covered in [Getting started](getting-started.md) and [Operations](operations.md).

Log in, and you land on the **Research Desk** workspace (also at `/app/research-desk`). Readers
never see the Desk; they use the portal at `/`, the site's front page (book pages are at `/library/item/…`).

## The Research Desk workspace

![The Research Desk workspace with the getting-started checklist](../sok_resdesk/public/images/guide/desk-workspace.png)

- **Get started with Research Desk**, at the top, is a checklist for a new library (see
  [below](#the-getting-started-checklist)). Hide it when you're done.
- **Shortcuts**: Ingest Profiles, Items, Collections, Background Jobs, Server, Open Portal,
  Settings and Help.
- **Cards** list everything else: the catalogue (items, collections, authors, subjects), ingest
  (profiles, runs, background jobs), setup, readers (sign-up requests, users) and metadata
  (exports, spreadsheet imports, push targets).

## Help, tours and the checklist

### Help on every screen

The help pages, in the Desk and on the portal, carry your library's logo (Settings → Logo &
Branding), or the Servants of Knowledge logo until you set one.

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

After the first run a profile keeps itself in step with archive.org: new books come in each
day, changed ones are refreshed, removed ones are unpublished, and its portal collection follows
along ([more](ingesting.md#keeping-in-step-with-archiveorg)). **Sync with archive.org** on the
profile does it straight away.

Books arrive in batches in the background. Only the details and the text of each page are
downloaded; scans stay on archive.org (or your server) and are shown from there. Details:
[Choosing & ingesting books](ingesting.md) and [Your own folders & servers](local-folders.md).

**Background Jobs** shows every run, queued job and schedule, with progress, and lets you
**Pause** and **Resume** a run, **Pause All** background work, or stop it
([more](operations.md#background-jobs-see-pause-and-stop-what-is-running)).

![Background Jobs](../sok_resdesk/public/images/guide/desk-jobs.png)

## The Server page

**Server** shows whether every part of Research Desk is working, which version runs and whether
a newer one is out, the backups, recent errors and logs. Managers get an alert (in the Desk, by
email or a webhook) when something stops working. With the updater helper turned on, a System
Manager can also upgrade, restart and apply resource presets from here.

![The Server page](../sok_resdesk/public/images/guide/desk-server.png)

Details: [Server: updates, health & backups](server.md).

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
| Logo & Branding | logo (portal, login page, Desk), a square icon (browser tab and the Desk's Research Desk icon) and a picture for the home page |
| Search Engine | the Meilisearch address and whether page text is indexed; **Rebuild Search Index** |
| Internet Archive | contact sent with requests, delay between requests, books per batch, page-text cache, pausing schedules |
| Machine Resources | the resource preset (light, standard, server), the book limit (how many books this machine may hold), and quiet hours that pause background work at set times ([more](operations.md#resources-how-much-of-the-machine-research-desk-may-use)) |
| Server & Updates | update checks, automatic backups, where alerts go, and whether upgrades may be started from the Desk ([more](server.md)) |
| Access & Sign-up | what visitors can do, the default for new books, reader accounts, what OAI-PMH shares, access rules |

![Settings](../sok_resdesk/public/images/guide/desk-settings.png)

Take the tour on the Settings form for the fields most libraries change first.

## The About page

**About Page** (Research Desk → Setup, or `/app/rd-about-page`) is the introduction to your
library at **`/about`**: what the library is, whose books these are, how to use it, and a big
button to the library. It has a link in the portal's top bar, next to *Library*.

![The About page](../sok_resdesk/public/images/guide/portal-about.png)

A new install starts with a ready-made page to change. Fill in the parts you want; empty parts
are left out:

| Part | What goes there |
|---|---|
| Page | **Show the About Page** (untick to hide it and its top-bar link; `/about` then goes to the library), the **label** in the top bar, the page title and description for search engines |
| Introduction | headline (empty: the portal's name), tagline, the **introduction** in a rich-text editor (headings, bold, lists, links, pictures), an optional image beside it, and **live numbers**: books, pages of searchable text, collections and languages, counted as visitors see them |
| Buttons | the main button (*Open the library* → `/`) and an optional second one (*How to search* → `/library/help`). Links are a page of this site (`/library/collections`, `/?q=hampi`) or a web address (`https://…`) |
| How to Use It | numbered steps: title, a sentence or two (`**bold**` works), and an optional link |
| Highlights | cards for what makes the library useful, and **Show Featured Collections** (the collections marked *Featured*) |
| More | anything else, written freely in the rich-text editor: the story of the collection, partners and funders, contact, credits |

**Save**, then **View Page**. Changes show straight away.

## The portal's address

The library's search page is the site's front page: **`/`**, e.g.
`https://research.example.org/`. Searches are `/?q=hampi`, and the other pages keep their
addresses: books at `/library/item/…` (the stable addresses in citations), collections at
`/library/collections`, help at `/library/help`, the About page at `/about`. Old links to
`/library` (and searches like `/library?q=hampi`) still work: they lead to `/`.

To have visitors land on the **About page** instead, set *Home Page* to `about` in Desk →
Website Settings. The library's search page then moves to `/library` by itself, and every link
to it follows; set *Home Page* back to `library` to return.

![Editing the About page](../sok_resdesk/public/images/guide/desk-about.png)

## Roles

| Role | Can |
|---|---|
| ResDesk Manager | everything in the library: settings, ingests, background jobs, access, pushes, readers; the Server page and backups |
| System Manager | also upgrades, restarts and downloading backups on the Server page |
| ResDesk Cataloguer | edit books, authors, subjects and collections; exports and spreadsheet imports; read ingest runs |
| ResDesk Reader | the portal only: read members-only books |

Give staff a role under **Users** in the Desk ([more](operations.md#users-and-roles)).
