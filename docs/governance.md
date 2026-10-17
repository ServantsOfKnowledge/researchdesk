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

## What comes next

Classification levels and need-to-know access by department, retention rules and legal holds,
single sign-on, a file register, records intake, signature checks, a disclosure-request workflow,
redaction and an offline install bundle are planned: see the [roadmap](roadmap.md).
