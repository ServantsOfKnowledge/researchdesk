# Who can see what: members-only books and reader accounts

Research Desk can be a fully open library, a public catalogue with reading for members, an
internal library for one organisation, or anything in between. You decide per book, per
collection or for the whole site. Logged-in **readers** and staff always see every published
book.

## The three choices for a book

| Visibility | Visitors who are not logged in | Logged-in readers |
|---|---|---|
| **Public** (default) | find it, read it, search inside it, download the PDF | everything |
| **Login to read** | find it, see its details, **cite it** (BibTeX, RIS, …); reading, search inside and the PDF need a login | everything |
| **Login to find** | nothing: it doesn't appear in search, and its page asks them to log in | everything |

On the portal, members-only books carry a small 🔒 badge, and the book page shows a
**Log in to read** button instead of the reader.

*Unpublished* books (untick **Published on Portal** on the item) are hidden from everyone
except staff, whatever their visibility.

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

## Setting visibility for many books at once

Pick whichever fits the job; all of them update the catalogue and the search index together,
without re-indexing.

**Ticked rows in the Desk.** Desk → *Items*, tick the books → **Actions → Set Who Can See Them**.

**Everything matching a filter in the Desk.** Filter the Items list (by collection, language,
ingest profile, source, year…), then **⋯ menu → Set Who Can See All Matching Books**.

**From a portal search.** Log in as staff and search on the portal (`/`) as usual (words, facets,
years, or *Inside the text*). A staff bar above the results says *set who can see N matching
books*: pick a visibility → **Apply**. In *Inside the text* mode it changes the books that have
a matching page.

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
| **Anyone can sign up** | The login page gets a *Sign up* link; every new account can read straight away. |
| **Sign up, admin approves** | Anyone can sign up, but the account waits in **Reader Requests** until staff approve it. Managers get a notification for each request. |

**Adding readers yourself:** Desk → *User* → *Add User*, set *User Type* to *Website User* and
give the **ResDesk Reader** role. Or from the terminal:

```bash
./resdesk.sh add-reader priya@example.org --name "Priya Rao"
```

Frappe emails a welcome link to set a password (set up outgoing email in Desk → *Email
Account*; without email, set the password in the User form and share it yourself, and use
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
