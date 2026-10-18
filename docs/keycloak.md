# Single sign-on with Keycloak

[Keycloak](https://www.keycloak.org/) is a free identity provider that many departments already run. Put
it in front of Research Desk and people sign in once, with the accounts the department already keeps:
from its own user list, from Active Directory or another LDAP directory (Keycloak *federates* them), or
from a **SAML** identity provider (Keycloak *brokers* it). Research Desk talks to Keycloak over **OpenID
Connect**, which Frappe supports; it does not speak SAML itself, so Keycloak is also the answer when your
identity service only offers SAML. The rules Research Desk adds to any directory sign-in are in
[Directory sign-in](governance.md#directory-sign-in).

Menu names in Keycloak change between versions; the steps below follow the current admin console, so
check them against yours. The Research Desk side follows Frappe's own *Keycloak* provider.

## Before you start

- Keycloak and Research Desk each on an **https** address (the settings are refused otherwise; a
  provider on the same machine may use http). Say they are `https://sso.example.gov.in` and
  `https://library.example.gov.in`.
- A realm for the department (or an existing one), say `staff`.
- A Research Desk administrator (System Manager or SOK Super Admin) and a Keycloak realm administrator.
- **Classified mode:** add Keycloak's host (`sso.example.gov.in`) to `resdesk_allowed_hosts` in the site
  configuration, or the sign-in is refused as an outside connection.

## 1. In Keycloak

1. **Switch off self-registration** (Realm settings → Login → *User registration* off). Anyone who can
   register in the realm could otherwise sign in to the library.
2. **Create the client** (Clients → Create client): *Client type* OpenID Connect, *Client ID*
   `researchdesk`, then *Client authentication* **On** and **only** *Standard flow* ticked.
3. **Redirect address** (the client's *Valid redirect URIs*), exactly:
   `https://library.example.gov.in/api/method/frappe.integrations.oauth2_logins.login_via_keycloak`
   Leave *Web origins* empty or set it to the library's address.
4. **Copy the secret** (the client's Credentials tab).
5. **Every person who may sign in needs an email address, marked verified.** Research Desk signs a person
   in by email and refuses an address the provider has not verified. For people who come from the
   department's own directory, tick *Email verified* on the user, or (for a federated directory whose
   emails you trust) add a *Hardcoded attribute*-type mapper for `email_verified` = `true` to the client.
   Do not do that for a realm that anyone can join.
6. **Optional: bring the accounts in.** *User federation* adds an LDAP or Active Directory server;
   *Identity providers* adds a SAML 2.0 provider (or another OpenID Connect one). People then choose
   nothing: they arrive at Keycloak, which sends them on to the right place, and Research Desk only ever
   sees Keycloak.
7. **Short sessions** (Realm settings → Sessions): set *SSO Session Idle* and *SSO Session Max* to what the
   department accepts (for example 30 minutes and 8 hours).

## 2. In Research Desk

1. Desk → Administration → **Social Login Keys** → New. *Social Login Provider*: **Keycloak** (the form
   fills in the paths).
2. *Client ID* `researchdesk`; *Client Secret* the secret from step 4.
3. *Base URL*: the realm's address, `https://sso.example.gov.in/realms/staff` (older Keycloak versions
   add `/auth` before `/realms`). *Custom Base URL* stays on.
4. *Sign ups* (blank means "follow the site's sign-up setting"): **Allow** lets anyone Keycloak knows get a portal account the first time they sign in;
   **Deny** only lets in people whose Research Desk account already exists (an administrator creates it
   first, with the same email address). For a department's own staff, Allow is usual; the new account is
   an ordinary member with no clearance (a security officer grants those) and no staff roles (People &
   Roles).
5. Leave *trust email without a verified claim* and *trust any tenant* **off**: Research Desk refuses to
   save them.
6. Save. Research Desk checks that every address is https and that the trust options are off.

The sign-in page then shows **Login with Keycloak**.

## 3. Try it

- Open the library in a private window → *Login with Keycloak* → sign in at Keycloak → you land in the
  library as that person. In Desk → Administration → **Users** they now exist, with the email Keycloak
  gave.
- **Directory Sign-ins** (Desk → Running the Library) lists the person as *SSO*.
- A person who should work in the Desk: give them the role in **People & Roles**.
- Once it works for everyone who needs it, consider *Disable username/password login* (System Settings),
  keeping the built-in **Administrator** account and its own password for emergencies, and **two-factor
  login** where passwords remain.

## When something goes wrong

| What you see | Why, and what to do |
|---|---|
| Keycloak says *Invalid parameter: redirect_uri* | the redirect address in the client is not exactly the one above (https, no trailing slash, the right site name) |
| *Email not verified with Keycloak* | the person has no email, or *Email verified* is off (step 1.5) |
| *Signup is Disabled* | *Sign ups* is Deny, or it is blank and the site's own sign-up setting is off: create the person first, or set *Sign ups* to Allow |
| Back to the sign-in page with no message | the site's address (`host_name`) is not the public https address, so the redirect lands elsewhere; check the site configuration and the reverse proxy |
| *The sign-in address must use https://* when saving | the Base URL or a path is http; use https (Keycloak behind a proxy: give it its public https address) |
| Works for some people, not others | the client's access: in Keycloak, a user may need a role or group allowed to use the client |
| The library cannot reach Keycloak (Classified mode) | the host is not in `resdesk_allowed_hosts` |

## What Keycloak does not do here

- **Roles and groups are not mapped.** Frappe maps LDAP groups to roles but not single sign-on claims, so
  a person who signs in through Keycloak gets their roles from an administrator. A group in Keycloak
  cannot make anyone a security officer, records officer or administrator in any case.
- **Leavers.** Disable the person in Keycloak, and they cannot sign in again; but a session already open
  in the library lasts until it expires. The nightly leaver check covers LDAP accounts only, since Keycloak
  has no directory for Research Desk to ask. Shorten sessions (step 1.7, and System Settings →
  *Session Expiry* in the library) and switch the person off in the Desk when someone leaves.
- **Signing out** of the library does not sign the person out of Keycloak, and the other way round.
- **LDAP twice.** If Keycloak federates your directory, use Keycloak only. Do not also turn on the
  library's own LDAP login for the same people.
