# Who can see what: members-only books and reader accounts

Research Desk can be a fully open library, a public catalogue with reading for members, an
internal library for one organisation, or anything in between. You decide per book, per
collection or for the whole site. Logged-in **readers** and staff always see every published
book (except records the governance edition has classified: see [Government and institutional use](governance.md)).

## The four choices for a book

| Visibility | Visitors who are not logged in | Logged-in readers |
|---|---|---|
| **Public** (default) | find it, read it, search inside it, download the PDF | everything |
| **Login to read** | find it, see its details, **cite it** (BibTeX, RIS, …); reading, search inside and the PDF need a login | everything |
| **Approval to read** | find it, see its details, **cite it**; reading needs a login *and* a librarian's approval | find it and see its details; **read it once a librarian approves them for that book** (staff always can) |
| **Login to find** | nothing: it doesn't appear in search, and its page asks them to log in | everything |

**Page & text, and the text downloads, are for members on every book**, even a Public one: the
page images beside their text, notes, read aloud, and *The text, to read your way* (the accessible
EPUB and plain text) need a login as a reader or staff. They are what a scraper wants and what costs
bandwidth, so visitors who are not logged in get the book's details, the citations and the book
reader (archive.org's, or the PDF where the book is open), and a note on the book page that says
why. With open sign-up every logged-in account is a member.

On the portal, members-only books carry a small 🔒 badge, and the book page shows a
**Log in to read** button instead of the reader.

## Approval to read

For theses, research data, a university's own papers, lending-only or other restricted books: set **Who can see it** to *Approval to read*
(on a book, in bulk, per collection or ingest profile, or by an access rule, like any other level).

- Everyone can **find** the book, see its details and cite it; the search shows no words of its text to a reader who is not approved.
- A logged-in reader opens the book and sees **Ask to read this book**, with a box for why they need it. A guest is asked to log in first.
- Staff (managers and cataloguers, the library's librarians) get an alert and decide in the Desk: **Research Desk → Access Requests**. Tick
  requests → **Actions → Approve / Decline**, or open one to set an **Approved Until** date and a **Note to the Reader**. The reader sees the decision on the book's page
  (Research Desk sends email only for account messages).
- An approval is for one reader and one book. **Settings → Access & Sign-up → Days an Approval Lasts** sets how long approvals last
  (0 = no end); an approval past its end date stops working by itself and the reader can ask again. A declined or withdrawn request can be
  asked again too.
- An approved reader reads the book like a member reads a members-only book, and searching all the text includes its pages for them. Staff
  read it without a request. For everyone else it behaves as unreadable everywhere: the reader, page images, downloads, IIIF, OPDS, notes.

## How a book can be used: read only and research only

*Who can see it* decides who may open a book. **How it can be used** decides what they can do with it once they have. Set it on a book
(*How It Can Be Used*), or for many books: Items list → tick books → **Actions → Set How They Can Be Used** (or **⋯ → Set How All
Matching Books Can Be Used** for a filter). Like *who can see it*, only managers and super admins change it.

| Level | The reader can | The reader cannot |
|---|---|---|
| **Full** (default) | read, download the PDF and other files, the text as EPUB or plain text | |
| **Read only** | read the book page by page in **Page & text** (page image and its text) | download the PDF or any file, download the text, use IIIF, OPDS file links, or open archive.org's own reader or a PDF in a frame (the Book reader tab is not offered) |
| **Research only** | read the page images and **search** the text: hit pages with short snippets | see the page text, read aloud, download anything |

It combines with *Approval to read*: a thesis can need approval, then be read only. Staff are not limited, so they can work on the
book. Limits to know: nothing can stop a screenshot or someone copying by hand; a book that is also open on archive.org stays open
there; page images still reach the reader's browser to be shown. Research only is for material where the text must not leave the library.

*Unpublished* books (untick **Published on Portal** on the item) are hidden from everyone
except staff, whatever their visibility.

The same choices apply to everything else the library holds: photographs, manuscripts and
recordings are items; **units of archival description** have their own *Who can see it* and show
only if every unit above them is published too; a **deposit** is private until a reviewer accepts
it, and then follows the visibility and embargo the depositor chose
([Repository deposit](deposit.md)). The IIIF addresses, the OPDS catalogue and offline copies
follow the same rules, and an offline copy contains the files and text only of books that are
open to read and public.

## The site-wide setting

Desk → Research Desk → **Settings** → *Access & Sign-up* → **Visitors Who Are Not Logged In**:

| Setting | Use it for |
|---|---|
| **Each item's setting** (default) | a public library with some members-only books: guests follow each book's visibility |
| **Records only** | a public catalogue: guests can search the catalogue and cite, but every book needs a login to read and to search inside |
| **Login required** | an internal library: the whole portal is behind the login page |

From the terminal:

```bash
./resdesk.sh access --guests "Records only"
./resdesk.sh access                    # show the current settings and how many books have each visibility
```

## Who can change it

Only **managers and super admins** decide who can see a book, one at a time (the *Who can see it*
field) or many at once (below). A Cataloguer can read the field but not change it, and readers
never can. Ingest profiles, access rules and *Default for New Books* set it for books that come in.

## Setting visibility for many books at once

Pick whichever fits the job; all of them update the catalogue and the search index together,
without re-indexing.

**Ticked rows in the Desk.** Desk → *Items*, tick the books → **Actions → Set Who Can See Them**.

**Everything matching a filter in the Desk.** Filter the Items list (by collection, language,
ingest profile, source, year…), then **⋯ menu → Set Who Can See All Matching Books**.

**Books you tick.** In the Items list, tick as many books as you like (the box in the header
ticks every book shown) → **Actions → Mark Public**, or **Actions → Set Who Can See Them** for
the other levels. Before 0.121 the portal's search page had a staff bar for this; it is in the
Desk now, where books can be ticked one by one.

**A whole ingest profile.** Open the profile, set **Access for Its Books**, save, then
**Apply Access to Its Books**. Books the profile ingests later get the same visibility
automatically.

**By collection, language or anything else, now and in future.** Settings → *Access Rules*:
add rows such as

| When | Is | Who can see it |
|---|---|---|
| Collection | `KannadaUniversity` | Login to read |
| Source | `Local` | Login to find |
| Language | `Tulu` | Login to read |

New books get the first rule that matches (an ingest profile's own setting comes first, then
the rules, then **Default for New Books**). Click **Apply Access Rules** to update the books
already in the catalogue. That leaves alone books whose visibility was set by hand or in bulk,
unless you tick the box to include them.

**From the terminal**, for scripts and very large batches:

```bash
./resdesk.sh access login-to-read --collection KannadaUniversity
./resdesk.sh access members --profile "Staff scans"          # members = Login to find
./resdesk.sh access public --ids "id1,id2,id3"               # or --ids-file list.txt
./resdesk.sh access login-to-read --language Kannada
./resdesk.sh access public --all
./resdesk.sh access --apply-rules [--include-manual]
./resdesk.sh ingest --folder /library-source/staff --visibility members   # new books arrive hidden
```

Changes to more than 200 books run in the background; a few thousand books take about a
minute.

Each book records **Visibility Set By** (Default, Profile, Rule, Bulk or Manual), so you can
always see why a book is visible or not.

## Reader accounts

Settings → *Access & Sign-up* → **Reader Accounts**:

| Setting | What happens |
|---|---|
| **Admins add readers** (default) | No sign-up page. Staff create accounts. |
| **Anyone can sign up** | A one-page *Create an account* (name, email, password) signs the person in at once; every new account can read straight away, with no email to wait for. |
| **Sign up, admin approves** | Anyone can sign up (the same page, signed in at once), but the account waits in **Reader Requests** until staff approve it. Managers get a notification for each request. |

**Adding readers yourself:** Desk → *User* → *Add User*, set *User Type* to *Website User* and
give the **ResDesk Reader** role. Or from the terminal:

```bash
./resdesk.sh add-reader priya@example.org --name "Priya Rao"
```

Frappe emails a welcome link to set a password. Set up outgoing email first, in **Connections →
Outgoing email** ([Sign-in email and sign-ups](sign-in-email.md)); without email, set the password in the User form and share it yourself, and use
`--no-email`).

**Approving requests:** Desk → Research Desk → *Readers* → **Reader Requests**. Open a request
and set *Status* to *Approved* or *Rejected*, or tick several and use **Actions → Approve**.
Approving gives the ResDesk Reader role and emails the person; rejecting (or setting back to
Pending) removes it. Until approved, people can log in but see only what visitors see, with a
note that their account is waiting.

Readers land on the portal (`/`) after logging in, never in the Desk.

## Koha, OAI-PMH and exports

Harvesters don't log in. Settings → **OAI-PMH Shares** decides what they get:

| Setting | Harvesters receive |
|---|---|
| **Records guests can find** (default) | Public and Login-to-read books (with *Login required*, nothing) |
| **All published records** | every published book: for a Koha or VuFind on an internal network |
| **Off** | the endpoint is switched off |

The MARCXML and citation downloads on the portal follow the visitor's own access. Staff can
always export everything with `sok_resdesk.api.marcxml_all`.

## Good to know

- For books that are also on archive.org, "Login to read" hides the reader on *this* portal;
  the scan is still wherever the Internet Archive publishes it. For books from your own folders
  or server, the PDF and page text are only served to logged-in readers.
- Citations for Login-to-read books stay public on purpose: people can cite a book they
  cannot open yet.
- Books indexed before v0.5 count as Public; nothing needs re-indexing after the upgrade.
