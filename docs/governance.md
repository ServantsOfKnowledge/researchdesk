# Government and institutional use

For a ministry, department, court, council or any institution that must be able to show **who may
see what, and who did see what**. Everything here is switched on with one setting and is off
otherwise, so an open library pays nothing for it.

![Governance Mode: the decision on every request, offices read downward, the audit chain, and where it is enforced](../sok_resdesk/public/images/governance.svg)

**Governance Mode** is in Desk → Research Desk → **Settings** → *Government and institutional use*.
Only an administrator (System Manager or SOK Super Admin) can change it.

This page is the whole design. [What you get](#what-you-get) and [Setting it up](#setting-it-up)
are for the people running it; [How it works](#how-it-works) and
[Where it is enforced](#where-it-is-enforced) are for the people who must trust it.

## What you get

| | |
|---|---|
| **Classification** | each record has a level (Unclassified, Restricted, Confidential; Secret and Top Secret on a Classified-mode installation) and optionally a department |
| **Need-to-know** | a person sees a record only with a clearance: a level, and the departments (and the offices below them) they belong to |
| **Audit log** | every view, download, search, change of visibility or classification, clearance granted, sign-in and sign-out, in a log that cannot be edited and shows any tampering |
| **Separation of duties** | the role **ResDesk Security Officer** grants clearances and classifies; a system administrator holds no clearance by role; the department tree belongs to the super admin |

It does not make an installation *approved*. That is for your security officers and an audit
(for an Indian government body, normally by a CERT-In empanelled auditor before it goes live), and
this page describes what the software does, not what the law requires: check each requirement with
your legal and records officers.

## Setting it up

1. **Switch on** Governance Mode (Settings → *Government and institutional use*).
2. **Departments** (Desk → Research Desk → Running the Library): enter the tree, top first. Each
   office has the office it reports to. A super admin keeps this.
3. **Security officers**: give the role **ResDesk Security Officer** to the people who will grant
   clearances (People & Roles).
4. **Clearances**: for each person who may see more than unclassified, department-free records,
   add a clearance: a level and the departments they belong to. An officer can only grant
   within their own level and departments, never to themselves.
5. **Classify**: tick records in **Items → Actions → Set Classification**, or add a line for one record
   in **Classified Records** (its level and department). Only a security officer, a manager or a
   super admin can, never above their own clearance. Deleting a record's line declassifies it.
6. **Check the log** now and then (Audit Log → *Check the log*) and write down the last line's
   number and hash somewhere else.

Governance Mode cannot be switched off while classified records exist.

## How it works

### One rule, hiding first

A classified or department-scoped record carries the visibility **Cleared only**. It is not one of
the three choices a person makes by hand and it is not in the plain rules at all: the rules that
decide whether a guest or a reader may find or read a book (`core/access.py`) answer *no* to it for
everyone. The people who are cleared reach it through one door, `access.effective()`, which gives
them the record as if it were members-only. So a place that was never taught about classification
fails **closed**: the record is simply not there.

The hiding does not depend on Governance Mode being on, or readable: with the switch off a
classified record stays hidden from everyone, and the switch only adds the people who are cleared.

### The decision

For a request that reaches a record (a search hit, a page, a file, an export, a push):

1. The plain rules (guest mode, member or not, Public / Login to read / Login to find) apply as
   they always did.
2. If the record is not *Cleared only*, that is the answer.
3. Otherwise the person must be signed in and a member, their **level** must be at least the
   record's, and the record's **department** must be empty, or one of their departments or below one.
4. If any step fails, the record is **not found**: no trace in search, counts, facets, pages,
   files, exports, IIIF, OPDS, OAI-PMH, SRU or pushes.

The pure rules are in `core/classification.py` (levels, `expand`, `cleared`, and the two filters
built from a clearance) with unit tests; `access.py` applies them.

### Departments and clearances

**Departments** is a tree: each has the office above it. A person sees a record when their level is
at least the record's and the record's department is theirs **or below theirs**: a directorate sees
its district and taluk offices, a taluk office sees only its own. A record with no department is
open to anyone cleared for its level. A person with no clearance sees only Unclassified records that
belong to no department. Nobody has a clearance by role (not a System Manager, not a manager); only
the built-in **Administrator** account sees everything, and its use is in the audit log.

Rules that keep it honest: a level is never granted above the grantor's own; departments granted must
be within the grantor's own; nobody edits their own clearance; the tree is kept by super admins, so
a security officer cannot place their own office above the rest; a department name cannot contain `%`.
Granting or removing a clearance is in the audit log.

### Where the level and department live

A classified record has one line in **RD Item Scope** (its level and department; none means
unclassified, and it is kept apart because the item's own table is full) and the visibility
*Cleared only*. Every record and every page of its text in the search engine carries `class_rank`
(the level as a number) and `department`, beside `visibility`. A person's search is filtered by
`NOT visibility = "Cleared only" OR (NOT class_rank > N AND (department is empty OR in [their
offices]))`; documents indexed before the fields existed count as level 0 with no department. The
same condition, written for SQL, is added to every portal count and list. Changing a classification
updates the records and the index together (at once for up to 200 records, in the background for more).

### The audit log

With Governance Mode on, Research Desk writes a line for each of these:

| What | When |
|---|---|
| `view` | a book's page is opened (the same person opening it again within five minutes counts once) |
| `download` | a PDF or other file is served (a viewer asking for the rest of a file it began is not counted again) |
| `search` | a search with words, and the words (first 200 characters) and mode used |
| `visibility`, `classification` | who can see a set of books, or their level, was changed, and how many |
| `clearance` | a clearance was granted, changed or removed |
| `login`, `logout` | a person signs in or out |

Each line has a number, the time, the person (or `Guest`), the record, the detail and the address
the request came from.

**It cannot be edited or deleted** from the Desk or the portal, and every line carries a hash of the
line before it, keyed with a secret that is kept outside the database. If a line is changed, or
removed, directly in the database, **Check the log** (Desk → Research Desk → **Audit Log**) says at
which line the chain breaks. The same check is `sok_resdesk.audit.verify`. Lines are written under a
short database lock, so the order is the order of the numbers; a reader is never stopped because the
log could not be written (that failure shows once a minute in the Error Log).

Two limits to know. A log **cut short at its end** leaves a chain that still checks: the check
therefore reports the last line's number and hash, and you should note them somewhere else (a
register, an email to the records officer) now and then. And someone who holds both the database
and the site's encryption key could rewrite the whole log: keep database backups where the same
people cannot write to them.

Managers can read the log; only administrators can export it, because it holds addresses and search
words. Search words and addresses are personal data in many places (in India, the Digital Personal
Data Protection Act 2023): decide how long you keep the log and who may read it; a retention policy
for the log is on the [roadmap](roadmap.md).

## Where it is enforced

| Surface | How |
|---|---|
| Search and facets | the engine filter above, added to every book and page search, including inside one book |
| Counts and lists on the portal | the SQL condition (`access.sql_condition`) |
| The book's page and its files | `get_record` and the file endpoint use the person's own view; classified files are sent `private, no-store`, never cached |
| OAI-PMH, SRU | the harvest condition excludes *Cleared only* in every scope |
| OPDS, IIIF, annotations, page text | the plain rules answer *no* (fail closed) |
| Exports and bulk actions | `select_items` drops what the person is not cleared for; the all-records MARCXML and usage reports skip classified records |
| Pushes (Koha, webhooks, archive.org), Commons upload, DOIs | never for a classified record |
| Deletion | a deleted classified record leaves no public tombstone |
| Embargo end | does not make a classified record public |
| The Desk | lists and forms of items, and of their page text, notes, flags, ground truth and push records, follow the person's clearance |
| Bulk visibility and rules | skip classified records: their visibility is their classification's |

### What this does not cover yet

Staff screens that read records directly rather than through the Desk's permissions (the review
queue's list, the usage reports' counts, the dashboard's counts, and the number of page documents
in the search engine on the Server page) can still show counts or titles of classified records to
staff. Treat those counts as unclassified information until they are closed.

Units of archival description and deposits are not classified. A classified book's public notes and
its archival units are hidden from the portal for everyone (failing closed), so cleared people do not
see them there either.

## Deploying it

**One installation** is the default: Governance Mode on the library's own server, behind its login.
For a government body, host it in the department's own data centre (in India, with data kept in the
country), switch on **Login required** under *Visitors who are not logged in* (Settings → Access &
Sign-up) so the whole portal is behind sign-in, and use HTTPS.

**Planned**, in this order (see the [roadmap](roadmap.md)):

- **Classified mode** for Secret and Top Secret: an installation that refuses every outbound
  connection, switches off the features that talk to outside services, keeps classified content out
  of logs, and checks at start that nothing leaks. Chosen when installing, by the question *"Will
  this installation hold Secret or Top Secret records?"* (default no). It would be run on a separate,
  air-gapped machine; the software cannot encrypt the disk or separate the network for you.
- **A public mirror**: a second, read-only Research Desk on another container or server that holds
  only what the main system has released (Unclassified, public, published), sent by the main system
  and withdrawn from the mirror the moment a record is classified, withdrawn or unpublished. The
  main system alone decides what is public.

## What comes next

Retention rules and legal holds (with a configurable schedule per department and transfer to the
state archives), single sign-on and directory sync, a file register, records intake, signature
checks, a disclosure-request workflow, redaction, conversion of old Kannada font text to Unicode,
and an offline install bundle are planned: see the [roadmap](roadmap.md).
