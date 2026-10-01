# Autopilot state: SOK Research Desk

## Last run
2026-10-02: v0.11.0 (Server page, book limit, archive.org sync). Autopilot passes: 2026-09-30 (v0.10.0, v0.10.1).

## Project conventions
- Frappe v16 app (`sok_resdesk/`), Docker Compose or native bench; shell entry points `install.sh`, `upgrade.sh`, `resdesk.sh`, `scripts/*.sh`.
- Checks: `ruff check sok_resdesk scripts` · `ruff format --check sok_resdesk scripts` · `python3 -m pytest -q` (48 tests) · `bash -n` + `shellcheck -S warning` on scripts · `python3 scripts/gen_docs.py --check` · in a bench: `bench --site SITE run-tests --app sok_resdesk` (50 tests: test_integration, test_operations, test_server).
- Style: tabs in Python/JS; plain-English user-facing text; docs are the in-app help (`core/helpdocs.PAGES`), and `tests/test_docs.py` guards drift.
- Commits: author omshivaprakash <omshivaprakash@gmail.com>, no Claude attribution. Releases via `scripts/release.sh`; Om pushes to GitHub himself.

## Baseline
Run 1: ruff pass · pytest 48 · bash -n pass · gen_docs current · shellcheck 5 warnings.
Run 2: all of the above clean (shellcheck 0 warnings) · Frappe run-tests 26 passed.

## Changed
Run 1 (4752667): errors when pausing/cancelling a queued push go to the Error Log instead of
being swallowed; two more silent `except: pass` now log; move.sh shellcheck tidy.
Run 2 (v0.10.1), all asked for by Om:
- `ruff format` over the code (42 files), and CI checks it.
- `tests/test_operations.py` (13 Frappe tests): push send/unchanged, dry run, pause mid-run and
  resume, cancel before start and mid-run, pause refused when idle, Pause All/Resume All,
  schedules paused beforehand stay paused, held jobs release/discard, quiet hours pause/resume,
  manual choices respected, checklist, choose_preset, portable paths + relink. Mutation-checked.
- CI: worker-priority check (nice 19) and a move round trip (export, import back, count books).
- Worker priority: Frappe added +10 on top of our `nice`, so every preset ended at 19 anyway.
  Now `background_process_niceness 0` and `WORKER_NICE` (default 19, not part of presets;
  replaces QUEUE_NICE) is the exact level. Om: lowest priority until he asks for more.
- Removed unused APP_DIR in resdesk.sh; replaced the scratch push_test cancel check with the
  in-repo cancel test.

Run 3 (v0.11.0, features Om asked for, not autopilot): Server page (updates, health, backups,
logs, alerts) with the optional updater helper (scripts/agent.py, compose profile `updater`);
book limit (core/capacity.py, capacity.py); keeping profiles in step with archive.org and
mirror collections (ia_sync.py). Upgrade from the Desk tested end to end in a second install
(upgrade and roll back). Fixed: 1020 "Record has changed" on tabSingles during create-site
(Om's v0.10.1 upgrade stopped there), offline `git ls-remote` aborting upgrades, orphaned
collection rules blocking new books.

## Pipeline — agreed with Om, to fix and test later
1. Native install: resource presets, WORKER_NICE via the Procfile, `import`, the v0.10
   portable-folder patch. Needs a native test machine.
2. Live pushes: Internet Archive, Koha and Wikidata against real sandboxes (Koha test
   instance, test.wikidata.org, an IA test item); so far only fakes and the webhook.
3. Updater helper on a native install (Procfile process, detached upgrade) and on Docker
   Desktop for Mac; Frappe rebuild via FRAPPE_COMMIT (the sandbox can't reach GitHub over TLS).
4. Book-limit numbers: measure on Om's server and adjust PAGE_MEMORY / PAGES_PER_CPU if needed.

## Open proposals — needs your call (Tier B)
(none open)

## Tier C — flagged, never automatic
- Pushing to GitHub, archive.org, Koha or Wikidata.
- `.env`, `site_config.json`, and export archives in `site-backups/` (they hold the encryption key). One is present now: `site-backups/resdesk-move-20260930-1209.tar.gz` (a sandbox test export; delete by hand when not needed).
- Deleting data or books; rewriting commit authorship.

## Do not touch
- Commit authorship/attribution (Om: "as omshivaprakash - don't include claude").
- Anything under `site-backups/` or `library/` content.

## Summary
Two passes on 2026-09-30. The code is formatted and checked in CI; pushing, pausing, quiet
hours and moving now have integration tests that run in CI, and the background workers really
run at the lowest priority unless WORKER_NICE says otherwise. Released as v0.10.1. What's left
is real-world testing: a native install and live pushes to archive.org, Koha and Wikidata.
