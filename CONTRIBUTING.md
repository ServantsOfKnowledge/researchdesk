# Contributing

Thank you for helping build an open research portal for digitised books.

- **Librarians, archivists, researchers:** issues describing what you need, confusing steps in
  the docs, or bad metadata you spot are just as valuable as code.
- **Developers:** read [docs/development.md](docs/development.md). In short:
  1. Fork and create a branch.
  2. Keep format/protocol logic in `sok_resdesk/core/` with tests in `tests/test_core.py` or `tests/unit_*.py`.
  3. `ruff check sok_resdesk scripts && ruff format --check sok_resdesk scripts && pytest` must pass
     (and `bench run-tests --app sok_resdesk` for anything touching the database). `tests/test_docs.py` fails when
     something you added isn't documented, and says where it goes.
  4. Update `docs/` and `CHANGELOG.md` for anything user-visible, run `./resdesk.sh docs`,
     and retake changed screens with `./resdesk.sh screenshots`
     (see [Keeping the docs current](docs/development.md#keeping-the-docs-current)).
  5. Open a pull request; CI runs the full Docker install.

Be kind and patient; many users are new to terminals and Docker. Write docs for them.

By contributing you agree that your contributions are licensed under the MIT licence.
