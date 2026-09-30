# Autopilot state: SoK Research Desk

## Last run
2026-09-30 (first run, v0.10.0 at e1e8f74)

## Project conventions
- Frappe v16 app (`sok_resdesk/`), Docker Compose or native bench; shell entry points `install.sh`, `upgrade.sh`, `resdesk.sh`, `scripts/*.sh`.
- Checks: `ruff check sok_resdesk scripts` · `python3 -m pytest -q` (48 tests) · `bash -n` + `shellcheck -S warning` on scripts · `python3 scripts/gen_docs.py --check` · in a bench: `bench --site SITE run-tests --app sok_resdesk`.
- Style: tabs in Python/JS; plain-English user-facing text; docs are the in-app help (`core/helpdocs.PAGES`), and `tests/test_docs.py` guards drift.
- Commits: author omshivaprakash <omshivaprakash@gmail.com>, no Claude attribution. Releases via `scripts/release.sh`; Om pushes to GitHub himself.

## Baseline (this run)
ruff pass · pytest 48 passed · bash -n pass · gen_docs up to date · shellcheck: 5 warnings (fixed 3, 2 intentional).

## Changed this run (Tier A)
- `outbound.py`: pausing/cancelling a queued push no longer swallows every error: a job that already started is ignored as before, anything else is written to the Error Log (previously a failed save could lose the held items silently).
- `access.py`, `jobs.py`: two other silent `except: pass` now log to the Error Log.
- `scripts/move.sh`: shellcheck directive; `move-to` no longer reuses the `ARGS` array name from `import` as a string.

## Open proposals — needs your call (Tier B)
1. Native installs untested for resource presets, `import` and the v0.10 portable-folder patch: try on a native test machine.
2. IA / Koha / Wikidata pushes only tested against fakes: dry run against real sandboxes (Koha test instance, test.wikidata.org).
3. `ruff format` would reformat ~33 files: one-off formatting commit, or leave style as is.
4. `test_integration.py` not in the default pytest run (needs a bench): add a CI job with a bench, or document as manual.
5. Scratch e2e `push_test` cancel-before-start check reports a false failure: fix the test's timing.
6. Queue workers showed nice 19 regardless of preset: confirm whether the preset should set the nice level.
7. `resdesk.sh` sets `APP_DIR` but never uses it: remove, or keep for sourced scripts.

## Tier C — flagged, never automatic
- Pushing to GitHub, archive.org, Koha or Wikidata.
- `.env`, `site_config.json`, and export archives in `site-backups/` (they hold the encryption key). One is present now: `site-backups/resdesk-move-20260930-1209.tar.gz` (a sandbox test export; delete by hand when not needed).
- Deleting data or books; rewriting commit authorship.

## Do not touch
- Commit authorship/attribution (Om: "as omshivaprakash - don't include claude").
- Anything under `site-backups/` or `library/` content.

## Summary
First autopilot run on a healthy v0.10.0: all checks pass. Fixed silent error handling in the pause/cancel path of metadata pushes (the one place an error could lose work without a trace) and tidied the move script. Seven decisions are waiting above, mostly real-world testing of native installs and live push targets.
