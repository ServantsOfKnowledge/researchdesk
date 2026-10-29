# Quick start: looking after the installation

For the person who installs it, upgrades it and keeps it running.

## First install

1. Run `./install.sh` and answer the questions (press Enter for the defaults). About 20 minutes, mostly waiting. [Installation](installation.md)
2. Open the address it prints and sign in as the administrator. The password is in `.env`.
3. Walk through the checklist on the Research Desk page. [Quick start: running the library](quickstart-library.md)

## Keeping it healthy

Open Desk → **Server**.

- **Health** lists every part (database, cache, workers, scheduler, search, disk, backups) as OK, Check or Problem, with a sentence saying why.
- **Backups:** the schedule, **Back up now**, and the list. Download one and keep it somewhere else. [More](server.md)
- **Updates:** the newest release and what is new; **Upgrade** (with the updater helper) or the command to run on the server. Take a backup first.
- **Services:** restart a part, and read that part's log.

Open **Logs** for errors, failed background jobs and log files. **Log QA** matches each error to the release that fixed it, so you know which are safe to ignore. [More](server.md#log-qa-and-folding-sections)

**Background Jobs** shows ingests and other work: pause, resume or stop it. [More](operations.md#background-jobs-see-pause-and-stop-what-is-running)

## When it gets big

The Server page shows the book limit for the machine and what each of CPU, memory and disk can hold. [Scaling to 50,000 books](scaling.md)

## Good to know

- Moving to another server: [Moving](moving.md).
- Single sign-on: [Keycloak](keycloak.md).
- Testing with test accounts: [Test accounts](test-accounts.md).
- What an install tells Servants of Knowledge, and how to see or stop it: [The install note](install-count.md).
