# Quick start: government records

For security officers, records officers and the administrators who set up the governance edition. It exists only on that edition ([Editions](installation.md#editions)).

## Setting it up

1. **Switch on Governance Mode:** Settings → *Government and institutional use* (an administrator does this).
2. **Departments:** enter the tree of offices, top first, each with the office it reports to.
3. **Security officers:** give the role **ResDesk Security Officer** to the people who grant clearances (People & Roles).
4. **Clearances:** for each person who may see more than unclassified records, add a clearance: a level and their departments. Nobody can grant one to themselves.
5. **Classify records:** tick records in **Items → Actions → Set Classification**, or add a line in **Classified Records**. Deleting a record's line declassifies it.
6. **Check the log** now and then: Audit Log → *Check the log*, and write down the last line's number and hash somewhere else.

The whole procedure is in [Setting it up](governance.md#setting-it-up).

## Day to day

- **Security officer:** grants clearances and classifies. Holds no other power over the catalogue.
- **Records officer:** approves disposal when a retention period ends, and places legal holds that nobody can override.
- **Everyone:** sees only what their clearance allows; every view, download and search is written to the audit log.

## Remember

- Governance Mode cannot be switched off while classified records exist.
- An administrator holds no clearance by role: separation of duties is the point.
- Records that must be released with parts hidden: disclosure requests and redaction ([governance](governance.md)).
