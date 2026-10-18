"""LDAP and single sign-on (docs/governance.md#directory-sign-in).

Frappe does the signing in: LDAP Settings (a directory server, with groups mapped to roles) and
Social Login Key (OpenID Connect and OAuth 2 providers). This module adds what a government
installation needs on top:

  - rules checked whenever those settings are saved: no encryption-free LDAP, no unverified server
    certificate, no mapping of a directory group to a governance duty (security officer, records
    officer, super admin, system manager), no provider on plain http, no "trust the email" shortcuts;
  - a record of who signs in through the directory (RD Directory Account);
  - a daily check that switches off, and signs out, an LDAP account the directory no longer has.
Clearances are never taken from a directory: only a security officer grants them.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import now_datetime

from sok_resdesk_governance import audit
from sok_resdesk_governance.core import directory as rules

ACCOUNT = "RD Directory Account"
LDAP_LOGIN = "frappe.integrations.doctype.ldap_settings.ldap_settings.login"
OAUTH_LOGINS = "frappe.integrations.oauth2_logins."
MAX_CHECKED = 5000  # a night's check stays a few minutes of directory queries


def _outside(url: str | None) -> bool:
	"""Classified mode: an address that is not the machine or a host named in resdesk_allowed_hosts."""
	from urllib.parse import urlparse

	from sok_resdesk_governance import classified
	from sok_resdesk_governance.core.classified import host_allowed

	if not url or not classified.on():
		return False
	host = urlparse(url if "://" in url else "//" + url).hostname
	return not host_allowed(host, classified.allowed())


def _duties(roles) -> list[str]:
	from sok_resdesk import access

	named = rules.privileged_mapped(roles, _allowed_duties())
	# whatever the People & Roles screen protects is protected here too
	extra = [r for r in roles if r in access.SUPER_ROLES and r not in _allowed_duties() and r not in named]
	return sorted({*named, *extra})


def _allowed_duties() -> list[str]:
	allowed = frappe.conf.get("resdesk_directory_roles_allowed") or []
	return [allowed] if isinstance(allowed, str) else list(allowed)


# -- rules checked when the settings are saved ----------------------------------------------------


def _ldap_problems(doc) -> list[str]:
	out = [
		_("LDAP must {0}.").format(_(p))
		for p in rules.ldap_connection_problems(
			doc.ldap_server_url, doc.ssl_tls_mode, doc.require_trusted_certificate
		)
	]
	if _outside(doc.get("ldap_server_url")):
		out.append(
			_(
				"In Classified mode the directory must be the machine itself or a host in resdesk_allowed_hosts."
			)
		)
	mapped = [r.erpnext_role for r in doc.get("ldap_groups") or []] + [doc.get("default_role") or ""]
	duties = _duties(mapped)
	if duties:
		out.append(
			_(
				"A directory cannot hand out {0}: give these in the Desk (People & Roles), "
				"or name them in resdesk_directory_roles_allowed in the site configuration."
			).format(", ".join(duties))
		)
	return out


def check_ldap(doc, method=None) -> None:
	"""LDAP Settings before_validate: before Frappe tries the connection with the password."""
	if doc.enabled and (bad := _ldap_problems(doc)):
		frappe.throw("<br>".join(bad), title=_("Directory sign-in"))


def _social_problems(doc) -> list[str]:
	out = []
	for field, label in (
		("authorize_url", _("sign-in")),
		("access_token_url", _("token")),
		("api_endpoint", _("user information")),
	):
		value = doc.get(field)
		if value and "://" in value and not rules.https_or_local(value):
			out.append(_("The {0} address must use https://.").format(label))
		if _outside(value):
			out.append(
				_("The {0} address is outside what Classified mode allows (resdesk_allowed_hosts).").format(
					label
				)
			)
	for field in ("trust_email_without_verified_claim", "trust_any_tenant"):
		if doc.get(field):
			out.append(
				_(
					"{0} lets a provider's claim take over an existing account: it is not allowed here."
				).format(field)
			)
	return out


def check_social_key(doc, method=None) -> None:
	if doc.enable_social_login and (bad := _social_problems(doc)):
		frappe.throw("<br>".join(bad), title=_("Single sign-on"))


# -- who signs in through the directory -----------------------------------------------------------


def _source() -> str | None:
	cmd = frappe.form_dict.get("cmd") or ""
	if cmd == LDAP_LOGIN:
		return "LDAP"
	if cmd.startswith(OAUTH_LOGINS):
		return "SSO"
	return None


def _refuse_unsafe_login(source: str, user: str) -> None:
	"""A directory sign-in is refused while its settings break the rules (a database edit can get past
	the save check), and into a privileged account the directory did not create."""
	bad = []
	if source == "LDAP" and (ldap := frappe.get_doc("LDAP Settings")).enabled:
		bad = _ldap_problems(ldap)
	if source == "SSO":
		for key in frappe.get_all("Social Login Key", filters={"enable_social_login": 1}, pluck="name"):
			bad += _social_problems(frappe.get_doc("Social Login Key", key))
	if bad:
		frappe.throw(
			_("Directory sign-in is switched off until its settings are corrected."), frappe.PermissionError
		)
	if not frappe.db.exists(ACCOUNT, user):
		# the directory matched an existing account by its email: not into one that carries a duty
		if _duties(frappe.get_roles(user)):
			frappe.throw(
				_("This account carries an officer's duty and signs in with its own password."),
				frappe.PermissionError,
			)


def on_login(login_manager=None) -> None:
	"""on_session_creation: note that this person came in through the directory."""
	source = _source()
	user = frappe.session.user
	if not source or user in ("Guest", "Administrator"):
		return
	_refuse_unsafe_login(source, user)
	try:
		now = now_datetime()
		if frappe.db.exists(ACCOUNT, user):
			# an LDAP account stays one: the nightly check must keep looking at it
			values = {"last_seen": now, "missing_runs": 0, "disabled_on": None}
			if frappe.db.get_value(ACCOUNT, user, "source") != "LDAP":
				values["source"] = source
			frappe.db.set_value(ACCOUNT, user, values, update_modified=False)
		else:
			frappe.get_doc(
				{"doctype": ACCOUNT, "user": user, "source": source, "first_seen": now, "last_seen": now}
			).insert(ignore_permissions=True)
		audit.record("login", detail=f"through the directory ({source})")
	except Exception:
		frappe.log_error(title="Research Desk: could not note a directory sign-in")


# -- leavers ---------------------------------------------------------------------------------


def _last_admin(user: str) -> bool:
	"""Switching this person off would leave no other enabled system manager (the built-in Administrator
	is not counted: it is usually kept locked away)."""
	others = frappe.db.sql(
		"""select count(*) from `tabHas Role` r join `tabUser` u on u.name = r.parent
		where r.role = 'System Manager' and r.parenttype = 'User' and u.enabled = 1
		and u.name not in (%s, 'Administrator')""",
		user,
	)[0][0]
	return not others


def _switch_off(user: str, why: str) -> bool:
	from frappe.sessions import clear_sessions

	if user == "Administrator" or ("System Manager" in frappe.get_roles(user) and _last_admin(user)):
		frappe.log_error(title="Research Desk: a leaver was not switched off", message=f"{user}: {why}")
		return False
	frappe.db.set_value("User", user, "enabled", 0)
	frappe.db.set_value(ACCOUNT, user, "disabled_on", now_datetime(), update_modified=False)
	audit.record("directory", detail=f"{user} switched off: {why}")
	frappe.db.commit()  # recorded before the sessions go, so a person is never signed out but still enabled
	clear_sessions(user=user, force=True)
	return True


def _in_directory(ldap, conn, user: str) -> bool:
	"""Whether the directory has this person, by the sign-in filter with their user name or their email
	(whichever the filter is written for)."""
	from ldap3.utils.conv import escape_filter_chars

	username, email = frappe.db.get_value("User", user, ["username", "email"])
	for value in {v for v in (username, email) if v}:
		conn.search(
			search_base=ldap.ldap_search_path_user,
			search_filter=ldap.ldap_search_string.format(escape_filter_chars(value)),
			attributes=[ldap.ldap_username_field],
		)
		if conn.entries:
			return True
	return False


def sync() -> dict:
	"""Daily. Each LDAP account is looked up with the sign-in filter; one the directory has not had for two
	checks in a row is switched off and signed out. Nothing is changed when the directory cannot be reached,
	when it answers as though empty, or when the check would switch off more than a fifth of everyone."""
	result = {"checked": 0, "switched_off": 0}
	if not frappe.db.get_single_value("LDAP Settings", "enabled"):
		return result
	accounts = frappe.get_all(
		ACCOUNT,
		filters={"source": "LDAP", "disabled_on": ("is", "not set")},
		fields=["name", "missing_runs"],
		limit=MAX_CHECKED,
	)
	accounts = [a for a in accounts if frappe.db.get_value("User", a.name, "enabled")]
	if not accounts:
		return result
	ldap = frappe.get_doc("LDAP Settings")
	problems = _ldap_problems(ldap)
	if problems:  # settings that no longer meet the rules (an outside host in Classified mode…)
		frappe.log_error(title="Research Desk: the directory check did not run", message="; ".join(problems))
		return {**result, "skipped": problems}
	try:
		conn = ldap.connect_to_ldap(ldap.base_dn, ldap.get_password(raise_exception=False))
		conn.search(
			search_base=ldap.ldap_search_path_user, search_filter="(objectClass=*)", attributes=["cn"]
		)
		if not conn.entries:  # the service account sees nothing: the answers below would mean nothing
			raise RuntimeError("the directory's user search returns no entries at all")
		seen = {a.name: _in_directory(ldap, conn, a.name) for a in accounts}
	except Exception:  # out of reach, or not to be believed: nobody is blamed for that
		frappe.db.rollback()
		frappe.log_error(title="Research Desk: the directory check could not finish")
		return result
	count = {a.name: rules.missing_after(a.missing_runs or 0, seen[a.name]) for a in accounts}
	leaving = [u for u, n in count.items() if rules.to_switch_off(n)]
	if rules.too_many(len(leaving), len(accounts)):
		frappe.log_error(
			title="Research Desk: the directory check stopped",
			message=f"{len(leaving)} of {len(accounts)} accounts would be switched off: check the LDAP settings.",
		)
		return result
	for user, n in count.items():
		frappe.db.set_value(ACCOUNT, user, "missing_runs", n, update_modified=False)
		result["checked"] += 1
		if user in leaving and _switch_off(user, "no longer in the directory"):
			result["switched_off"] += 1
	frappe.db.commit()
	return result


# -- the Server page ---------------------------------------------------------------------------


def problems() -> list[str]:
	"""Directory settings that no longer meet the rules (changed in the database, or before they existed)."""
	out = []
	if frappe.db.get_single_value("LDAP Settings", "enabled"):
		out += _ldap_problems(frappe.get_doc("LDAP Settings"))
	for key in frappe.get_all("Social Login Key", filters={"enable_social_login": 1}, pluck="name"):
		out += _social_problems(frappe.get_doc("Social Login Key", key))
	return out


def summary() -> str | None:
	"""One line for the Server page, or None when no directory is set up."""
	parts = []
	if frappe.db.get_single_value("LDAP Settings", "enabled"):
		n = frappe.db.count(ACCOUNT, {"source": "LDAP", "disabled_on": ("is", "not set")})
		parts.append(_("LDAP ({0} people signed in)").format(n))
	keys = frappe.get_all("Social Login Key", filters={"enable_social_login": 1}, pluck="provider_name")
	if keys:
		parts.append(_("single sign-on: {0}").format(", ".join(k for k in keys if k)))
	return "; ".join(parts) or None


def health() -> list[tuple]:
	"""Hook resdesk_health_checks: a line for the Server page when directory sign-in is set up."""
	line = summary()
	if not line:
		return []
	bad = problems()
	return [("directory", _("Directory sign-in"), "warn" if bad else "ok", " ".join(bad) or line)]
