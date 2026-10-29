# The install note

Servants of Knowledge would like to know how many libraries run Research Desk, so that it can see who uses it and
what to build next. A library can **say yes** and its installation then sends a short note. It is a choice you
make, you can see exactly what is sent, and it is never sent where it should not be.

## What is sent

Five things, about once a month:

| | |
|---|---|
| `id` | a random number made on your machine when it was first needed. It is not made from your domain, your hardware or any person, and it never changes |
| `version` | the Research Desk version, for example `0.109.0` |
| `edition` | `standard` (a site that runs the governance edition never sends a note) |
| `kind` | how it was installed: `docker`, `macos`, `linux` or `other` |
| `profiles` | the kinds of institution ticked in Settings → Features, for example `school, archive` |

**Nothing else.** No library name, domain, address, email, user, member, book, setting or password. The receiving
server's web server sees the address a request comes from, as every web server does. Research Desk does not
record it (the rate limiter holds it in memory for a minute); the registry's own web-server log is for Servants
of Knowledge to keep short or switch off.

## Where it goes and what is kept

To `research.servantsofknowledge.in`, over HTTPS. There, one record is kept for each `id`: the five things above, the first
and last time a note was received, and how many. That is the whole of it. The count shown to supporters is the number
of `id`s heard from in the last 45 days. It is an estimate: anyone can switch the note off, a reinstall is a new `id`, and nothing stops someone sending made-up ones, so treat it as "about this many".

## When it is sent, and when it never is

- **Only if you said yes.** The installer asks and offers "yes" (an install run with `--yes`, where nobody is asked, sends nothing unless `RESDESK_SHARE_INSTALL=yes` is set); the answer is in `.env` as `RESDESK_SHARE_INSTALL` and in Settings → **Install Note**.
  A site that was installed before this existed sends nothing until someone ticks the box.
- **Never from a Classified installation, or the governance edition,** whatever the box says. Those make no outside
  connections that nobody chose.
- **Never from an offline install**, which is not asked the question.
- **Never from this project's own automated tests**, which install with the answer set to no.

## See it, send it, stop it

In Settings → **Install Note**: tick or untick *Tell Servants of Knowledge this installation exists*; **Show the Install Note**
prints exactly what would be sent and where, and says if the site is not allowed to send it; **Send It Now** sends it
once; *What Was Sent* keeps the last one. To stop, untick the box (or change `RESDESK_SHARE_INSTALL` to `no` in `.env`
before a first install). The code is `sok_resdesk/registry.py` and `sok_resdesk/core/registry.py`: it can be read in
a few minutes.

## For the registry (Servants of Knowledge only)

The same app receives the notes: Settings → **This Site Is the Registry** (System Manager), on `research.servantsofknowledge.in`
and nowhere else. On any other site the endpoint answers as if it did not exist. It takes only an exact note (the five
fields, correct shapes and sizes), at most one a hour per `id`, at most 500 new `id`s a day (after that the sender gets an error and tries again the next day), 30 requests a minute from
one address. **RD Install Ping** lists what was received; `sok_resdesk.registry.summary` (System Manager) counts the
installs heard from lately by version, edition, kind and kind of institution.
