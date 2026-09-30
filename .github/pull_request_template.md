## What changes

<!-- one or two sentences, for people who use Research Desk -->

## Checks

- [ ] `ruff check sok_resdesk scripts` and `ruff format --check sok_resdesk scripts` pass
- [ ] `pytest` passes; `bench run-tests --app sok_resdesk` if the database is involved

## Docs

- [ ] `docs/` updated for anything a reader, librarian or admin will notice (the in-app Help shows these pages)
- [ ] `./resdesk.sh docs` run (settings and command reference)
- [ ] changed screens retaken with `./resdesk.sh screenshots`
- [ ] `CHANGELOG.md` entry
- [ ] `pytest sok_resdesk/tests/test_docs.py` passes
