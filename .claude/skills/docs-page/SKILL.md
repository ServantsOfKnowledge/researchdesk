---
name: docs-page
description: Add a new help page to docs/ (it also becomes an in-app help page) with every required registration, changing nothing else in the documentation. Use when asked to add, write or register a documentation or help page.
---

# /docs-page

Adds one page and the registrations the tests require. **It does not edit other documentation.**

## Before touching anything

Tell the user the plan in one list, and wait for a yes:

- the new file `docs/<slug>.md` (title, audience, group);
- `sok_resdesk/core/helpdocs.py` PAGES: one `Page(...)` line (audience `reader` appears on the portal
  and in the Desk; `staff` in the Desk only; group is "For readers", "For library staff",
  "For administrators" or "Technical");
- `docs/README.md`: one list entry for the page;
- only if asked: a Help button (`sok_resdesk/help.py` SCREEN_HELP: `(slug, heading-anchor)` that
  must exist), a link from one named existing page, a CHANGELOG line.

Anything beyond that list needs the user's say-so. Never reflow, reword or "improve" existing
pages; never run `scripts/gen_docs.py` unless asked.

## Writing the page

- Plain words, short sections, second person for readers. Headings are the page's anchors (GitHub's
  rules: lower case, spaces to hyphens). Relative links to other docs as `other.md#anchor`; pictures
  only from `sok_resdesk/public/images/guide/` (`../sok_resdesk/public/images/guide/name.png`).
- If the page documents a new doctype, API or screen, `docs/architecture.md` (data model),
  `docs/api.md` and SCREEN_HELP also need an entry: say so in the plan, and add only those lines.

## After

1. `scripts/prepush.sh` (runs `test_docs`: every doc registered and listed, every link and anchor).
2. `git diff --stat -- docs README.md CHANGELOG.md`: it must show only the files in the plan. If
   anything else changed, revert it and say so.
3. Commit as omshivaprakash, with the version bump and CHANGELOG entry the release needs.
