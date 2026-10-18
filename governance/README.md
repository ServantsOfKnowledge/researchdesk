# Research Desk Governance

The records-office features of [Research Desk](../README.md), for a library that needs them: the audit
log, classification and clearances, Classified mode, retention and legal holds, the file register,
directory sign-in, and disclosure requests with redaction.

It is a second Frappe app in the same repository, installed only when an install asks for it
(`./install.sh --edition governance`, or `RESDESK_EDITION=governance` in `.env`). Research Desk
never depends on it. See [Development](../docs/development.md#the-governance-seam) and
[Installation](../docs/installation.md#editions).

**Today this folder is the empty app that the install paths are proven with.** The governance code
itself still ships in Research Desk and moves here in 0.90.
