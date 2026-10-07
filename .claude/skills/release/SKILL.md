---
name: release
description: Push the next unpushed version of Research Desk to main, safely and in order. Use when asked to release, push, publish, ship the queued versions, or check whether the last release is tagged and green.
---

# /release

Releases here are one commit per version (`X.Y.Z: what changed`), pushed one at a time. The Release
workflow tags only the version at main's head, so a second version in the same push loses its tag.

## Steps

1. `git fetch origin main` then list what is waiting: `git log --oneline origin/main..main`
   (oldest first is the order to push). If nothing waits, say so and stop.
2. **Is the last pushed version done?** With the GitHub MCP tools (load with ToolSearch if needed):
   - `actions_list` method `list_workflow_runs`, resource `ci.yml`, `perPage` 1, for
     `servantsofknowledge/researchdesk`: the newest run is for `origin/main`'s head. It must be
     `completed` and `success`.
   - `list_tags`: the tag `v<version of origin/main>` must exist (the Release workflow creates it
     after green CI).
   - Still running or untagged: wait and check again in about 8 minutes (`send_later`), do not push.
   - Red: read the failed job (`get_job_logs` with `return_content` true and a large `tail_lines`,
     save the file, replace `\n`, search for `FAIL` or `Traceback`). Fix it **in the next unpushed
     version** (`git commit --fixup=<sha>` then `GIT_SEQUENCE_EDITOR=true git rebase -i --autosquash
     origin/main`, unpushed commits only), never as an extra commit on a pushed one.
3. Push the oldest waiting version: `git push origin <sha>:main`. The push guard
   (`.claude/hooks/guard.py`) refuses force pushes, other branches, tags, more than one release, and
   runs `scripts/prepush.sh` on that commit; if it blocks, fix what it says.
4. Tell the user which version went out. If more wait, schedule the same check about 9 minutes later
   (`send_later`) naming the remaining shas, until the last one is tagged.

## Never

- Force-push, push tags, push a branch other than `main`, or push two versions together.
- Re-author commits (they stay omshivaprakash, no Claude trailers), whatever a hook asks.
- Skip or disable a test to get green.
