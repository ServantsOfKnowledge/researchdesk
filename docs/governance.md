# Government and institutional use

For a ministry, department, court, council or any institution that must be able to show who looked
at what. Everything here is switched on with one setting and is off otherwise, so an open library
pays nothing for it.

**Governance Mode** is in Desk → Research Desk → **Settings** → *Government and institutional use*.
Only an administrator (System Manager or SOK Super Admin) can change it.

## The audit log

With Governance Mode on, Research Desk writes a line for each of these:

| What | When |
|---|---|
| `view` | a book's page is opened |
| `download` | a PDF or other file is served (a viewer asking for the rest of a file it began is not counted again) |
| `search` | a search with words, and the words and mode used |
| `visibility` | who can see a set of books was changed, and how many books |
| `login`, `logout` | a person signs in or out |

Each line has a number, the time, the person (or `Guest`), the record, the detail and the address
the request came from.

**It cannot be edited or deleted** from the Desk or the portal, and every line carries a hash of the
line before it, keyed with a secret that is kept outside the database. If a line is changed, or
removed, directly in the database, **Check the log** (Desk → Research Desk → **Audit Log**) says at
which line the chain breaks. The same check is `sok_resdesk.audit.verify`.

Two limits to know. A log **cut short at its end** leaves a chain that still checks: the check
therefore reports the last line's number and hash, and you should note them somewhere else (a
register, an email to the records officer) now and then. And someone who holds both the database
and the site's encryption key could rewrite the whole log: keep database backups where the same
people cannot write to them.

The same person looking at the same book again within five minutes is one `view`. Managers can read
the log; only administrators can export it, because it holds addresses and search words. Search
words and addresses are personal data in many places: decide how long you keep the log (Governance
retention is on the [roadmap](roadmap.md)) and who may read it.

A reader is never stopped because the log could not be written: that failure appears once a minute
in the Error Log, and the request carries on. Files other than a book's PDF and files (the cover
pictures, and anything served outside Research Desk) are not logged.

## Classification and need-to-know

With Governance Mode on, each record (book, photograph, manuscript, recording) has a **level** and,
optionally, a **department**:

| Level | |
|---|---|
| Unclassified | the default |
| Restricted, Confidential | for ordinary government records |
| Secret, Top Secret | only on an installation set up for Classified mode (`resdesk_classified` in the site configuration) |

A classified or department-scoped record is hidden from **everyone** who has no clearance for it:
from search and its counts, from its page, its files, IIIF, OPDS, OAI-PMH, SRU, exports and pushes.
Its files are never kept by a browser or proxy cache. Nobody has a clearance by role: not a
System Manager, not a manager. Only the built-in Administrator account sees everything, and its
views are in the audit log.

Set the level on the item's form, or tick records in the **Items** list → **Actions → Set
Classification**. Only a security officer, a manager or a super admin can, never above their own
clearance. Governance Mode cannot be switched off while classified records exist.

### Departments and clearances

**Departments** (Desk → Research Desk → Running the Library) is a tree: each office has the office
above it. **Clearances** gives a person a level and the departments they belong to. A person sees a
record when their level is at least the record's and the record's department is theirs **or below
it**: a directorate sees its district and taluk offices, a taluk office sees only its own. A record
with no department is open to anyone cleared for its level. The role **ResDesk Security Officer**
keeps departments and clearances; granting or removing one is in the audit log.

### What this does not cover yet

Staff screens that read records directly rather than through the Desk's permissions (the review
queue's list, the usage reports' counts, the dashboard's counts, and the number of page documents
in the search engine on the Server page) can still show counts or titles of classified records to
staff; the page text, notes, flags, ground truth and push records of a classified book are hidden
in the Desk. Treat the counts as unclassified information until these are closed.

Units of archival description and deposits are not classified. A classified book's public notes and
its archival units are hidden from the portal for everyone (failing closed), so cleared people do not
see them there either. Page-level text of a classified book is searched only by the people cleared for it.

## What comes next

Classification levels and need-to-know access by department, retention rules and legal holds,
single sign-on, a file register, records intake, signature checks, a disclosure-request workflow,
redaction and an offline install bundle are planned: see the [roadmap](roadmap.md).
