# Sign-in email and sign-ups

Reader sign-up, "set my password" and "forgot password" all send email. A fresh install has no
mailbox to send from, so these emails go nowhere until you set one up. This page is for
administrators and managers.

## Setting up outgoing email

**Research Desk → Exchange → Connections → People and sign-in → Outgoing email.** Pick your
provider (it fills in the server, port and security), type the mailbox address and its password, and
press **Save and send test**. The test goes to your own address and says in plain words what went
wrong if it fails. The dialog says at each step what happened (*Saving…*, *Saved. Sending a test
email…*); if the test fails the settings are still saved, so change what the message points at and
press the button again. Choosing a provider fills in its server, port and login (for Resend the
login is `resend`; for the others it is cleared, so a login left from an earlier set-up cannot make
Gmail refuse you). When the test works, any emails that failed earlier are sent again.

| Provider | What to enter |
|---|---|
| **Resend** (open and simple) | login `resend`, password is your API key; verify your sending domain in Resend first (the address must be on it) |
| **Gmail / Google Workspace** | the mailbox address; use an **app password** (Google Account → Security → App passwords), not your normal password |
| **Microsoft 365** | the mailbox address and an app password |
| **Zoho, Brevo, Amazon SES** | the server shown in the list, and the provider's SMTP login |

A domain you send from should have SPF and DKIM records, which providers such as Resend show you
when you verify the domain. Without them mail often lands in spam.

## When the test fails

The message is the provider's, put into words. Common ones:

- *The mailbox name or password was refused*: use an app password, and check the login.
- *550 … domain is not verified*: the sender address is not on a domain you verified with the
  provider (Resend), or you changed provider and the address is still the old one.
- *The server did not answer / name not found*: check the server name and port, and the security
  choice (STARTTLS on 587, SSL on 465).

If the dialog shows **earlier emails failed**, that is the error from the earlier try. **Forget the
failed emails** discards them (use it after changing provider); a successful test resends them.

## Who may sign up

**Settings → Access & Sign-up → Reader Accounts** (the same choices as in [Who can see what](access.md#reader-accounts)):

| Choice | What happens |
|---|---|
| **Admins add readers** | no sign-up link; you create accounts |
| **Anyone can sign up** | the person gets an email and can read at once |
| **Sign up, admin approves** | a **Reader Request** is created for you to approve |

## Finding people who tried to sign up

- **Users** (Desk → Users) lists every account, including ones that never set a password.
- **Reader Requests** lists sign-ups waiting for approval, with the email address.
- **Email Queue** (search it in the Desk) shows the emails the library tried to send, to whom, and
  the error when one failed.

## Reader profiles and volunteers

People may fill in **About me** (see [Signing in](signing-in.md)). In the Desk, **Reader Profiles**
lists them. Volunteers appear as a Desk notice; open the profile and use **Volunteers → Make a
proofreader / Make a reviewer** to give the role. The private *Support* section is visible to you
and the person only: use it to offer large text, screen-reader help or audio. More:
[Staff guide](staff-guide.md#reader-profiles-and-volunteers).
