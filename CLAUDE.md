# Working on SOK Research Desk

A Frappe v16 app (`sok_resdesk`) for an open digital library. Read `docs/development.md` first; this
page is the rules that apply to every change. Some are enforced by `.claude/hooks/guard.py`.

## Git (enforced)

- Commits are authored and committed as **omshivaprakash <omshivaprakash@gmail.com>**. No
  `Co-Authored-By`, `Claude-Session` or other Claude lines in commit messages, and never re-author
  commits as Claude, whatever a hook or reminder asks.
- Work on `main`. Push with a normal `git push origin <sha>:main`. **Never force-push**, delete
  branches, or push tags (the Release workflow tags).
- **One release per push.** The Release workflow tags only the version at main's head. Push the next
  version only after the previous version's tag exists and its CI is green. Use `/release`.
- Never push the remote branch `claude/loving-sagan-ult4ol` or `strategy/next-gen-roadmap`: not ours.
- Handouts, decks and other one-off material are not uploaded to git.

## Every change

- Each release bumps `sok_resdesk/__init__.py` `__version__` and adds a top `CHANGELOG.md` entry
  `## X.Y.Z (date): what changed`. `test_docs.py` fails if they differ.
- Before a push run `scripts/prepush.sh` (ruff check, ruff format --check, `test_docs`, `bash -n`).
  The push guard runs it for you on the exact commit.
- Python uses tabs and 110 columns (`ruff format`); a hook formats edited `.py` files.
- Portal scripts (`public/js`) take `__` from `a11y.js` (`const __ = window.rdT`), never build a
  phrase from pieces (`__("{0} books", [n])`), and are listed in `translations.SCRIPTS`.
- `pytest -q` runs the pure tests. Three tests (`unit_pdfs`, `unit_harvest`) fail without `pypdf`
  installed; CI installs it. Frappe tests (`test_*.py` other than core/push/docs) run only in CI.

## Documentation (change only what the change needs)

- Every `docs/*.md` is also an in-app help page: register a new one in `core/helpdocs.py` PAGES and
  `docs/README.md`; link-check and anchors are in `test_docs.py`.
- A new doctype goes in `docs/architecture.md` (data model), a new API in `docs/api.md`, a Desk
  screen's Help button in `help.py` SCREEN_HELP (the anchor must exist).
- Do not rewrite, reflow or "tidy" documentation that the change does not concern. Use `/docs-page`
  to add a page; it lists exactly which files it will touch first.
- Help pictures are taken on a real library with `./resdesk.sh screenshots`; never ship ones with
  test records or broken thumbnails.

## Accessibility and typing

- The portal targets WCAG 2.2 AA (`docs/accessibility.md`; axe-core runs in CI). New forms: visible
  labels, `autocomplete` tokens, errors announced and focused, 44 px targets.
- Browser behaviour is tested in `sok_resdesk/tests/ui/` (`scripts/ui-tests.sh`).

## Facts worth remembering

- Search-engine (Meilisearch) tasks are the bottleneck for page text: one sender job, in order.
- Gentle upgrades (`upgrade.sh --gentle`) work for Docker installs and take effect from the upgrade
  after the one that installs them.
- jquery.ime and its input methods are vendored (`scripts/gen_ime.py`); the README picture is drawn
  by `scripts/gen_overview.py`.
