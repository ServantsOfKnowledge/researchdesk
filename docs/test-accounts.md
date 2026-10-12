# Testing with test accounts

One command makes a test account for every kind of person the system knows, so each can be tried by
signing in as them. The addresses end in `@example.org`, a name reserved for examples, so no email
can reach a real person. No email is sent when they are made.

## Making them

On the server, in the Research Desk folder:

```
./resdesk.sh bench resdesk test-accounts
```

or, on a bench: `bench --site <site> resdesk test-accounts`. It prints one password for all of them,
once. Choose your own with `--password`. Run it again to reset the passwords and put the accounts back
as listed. Remove them when you have finished:

```
bench --site <site> resdesk test-accounts --remove
```

Make them on a test site, or remove them after: they are real accounts with real roles, one of them
a System Manager.

## The accounts

| Sign in as | Is | Should be able to | Should not be able to |
| --- | --- | --- | --- |
| *(no account)* | a visitor | search and read Public books | open members-only books, annotate, deposit |
| `rdtest.signed_in@example.org` | signed in, not a member | the same as a visitor (with open sign-up, members-only books too) | open the Desk |
| `rdtest.reader@example.org` | reader | read members-only books, keep notes, edit **About me** | open the Desk, proofread |
| `rdtest.depositor@example.org` | reader who deposits | send work through **Deposit** | review other deposits |
| `rdtest.proofreader@example.org` | proofreading volunteer | correct page text (**Page & text → Proofread**) | open the Desk |
| `rdtest.cataloguer@example.org` | cataloguer | edit catalogue records in the Desk | change Settings, people or the Server page |
| `rdtest.manager@example.org` | librarian | Settings, ingests, collections, people, Connections | the Server page's upgrades and restarts |
| `rdtest.super_admin@example.org` | Servants of Knowledge administrator | everything above, features, Server page, security | |
| `rdtest.system_manager@example.org` | Frappe System Manager | everything, including Frappe's own users and settings | |
| `rdtest.switched_off@example.org` | a reader switched off | nothing: signing in is refused | sign in |

*Administrator*, Frappe's built-in account, is the one account this does not make: use the one you
installed with.

## What to try as each

1. Sign in on `/login`, then open `/library` and the **About me** page.
2. Open a Public book, a login-to-read book and a staff-only book (**Settings → Access**): each should
   open or refuse as the table says.
3. Try one action the table says is *not* allowed, for example the Desk (`/app`) as the reader. It
   should refuse, not show an empty page.
4. Sign out and check the portal returns to what a visitor sees.

## Sign-in links and the clock

A welcome or password email carries a link that lives for a set time from the moment the email is
made. Check it with the accounts:

1. As a manager, open **Server → Date, time and sign-in links**. Check the time zone and the time are
   right for where the library is, and that a link lives at least a day.
2. Press **Send a new link…** and give `rdtest.reader@example.org`. The email is queued when you press.
3. Open the link within its life: it asks for a new password. Open the same link again: it says it has
   been used.
4. To see an expired link on purpose, set the life to 1 hour, send a link, and use it two hours later.

If links arrive expired, see [Links that arrive expired](sign-in-email.md#links-that-arrive-expired).
