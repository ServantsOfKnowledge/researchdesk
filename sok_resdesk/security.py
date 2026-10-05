"""Secure by default.

* **Headers** on every response Research Desk makes (core/seo.py: no content sniffing, no
  framing by other sites, no plugins, a strict referrer, HSTS over HTTPS).
* **Logins**: a few wrong passwords lock an account for a while; passwords must be strong
  (set once on upgrade, from Frappe's looser defaults; a library may change them in System
  Settings).
* **Server → Security**: what to fix, checked every time the Server page is opened: HTTPS, the
  Administrator password, developer mode, the password policy and lock-out, two-factor login,
  the search engine's key.
* Addresses that come from outside are fetched only on the public internet (core/netguard.py),
  and the public endpoints are rate-limited per visitor.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint

from sok_resdesk.core.seo import security_headers

DESK = ("/app", "/desk", "/api/method/frappe.", "/api/resource/")


def add_headers(response=None, request=None) -> None:
	"""after_request: the security headers, unless something set its own."""
	if response is None or request is None:
		return
	path = request.path or "/"
	https = (request.scheme == "https") or request.headers.get("X-Forwarded-Proto", "") == "https"
	for name, value in security_headers(https, path.startswith(DESK)).items():
		if name not in response.headers:
			response.headers[name] = value


LOCK_AFTER = 5  # wrong passwords in a row
LOCK_FOR = 300  # seconds


def harden_logins() -> None:
	"""Once, on upgrade: Frappe's defaults allow 10 wrong passwords and lock for a minute."""
	s = frappe.get_single("System Settings")
	changed = False
	if cint(s.allow_consecutive_login_attempts) in (0, 10):
		s.allow_consecutive_login_attempts = LOCK_AFTER
		changed = True
	if cint(s.allow_login_after_fail) in (0, 60):
		s.allow_login_after_fail = LOCK_FOR
		changed = True
	if not cint(s.enable_password_policy):
		s.enable_password_policy = 1
		changed = True
	if cint(s.minimum_password_score or 0) < 2:
		s.minimum_password_score = "2"
		changed = True
	if changed:
		s.flags.ignore_mandatory = True
		s.save(ignore_permissions=True)


def _default_admin_password() -> bool:
	from frappe.utils.password import check_password

	try:
		check_password("Administrator", "admin", delete_tracker_cache=False)
		return True
	except Exception:
		return False


def checks() -> list[dict]:
	"""Server page → Security: [{key, label, state, detail, link}]."""
	from sok_resdesk.catalogue import base_url

	def check(key, label, state, detail, link=""):
		return {"key": key, "label": label, "state": state, "detail": detail, "link": link}

	out = []
	url = base_url()
	out.append(
		check("https", _("HTTPS"), "ok", url)
		if url.startswith("https://")
		else check(
			"https",
			_("HTTPS"),
			"warn" if "localhost" in url or "127.0.0.1" in url else "bad",
			_(
				"the portal's address is {0}: passwords travel unencrypted. ./resdesk.sh https on DOMAIN"
			).format(url),
		)
	)
	out.append(
		check("admin_password", _("Administrator password"), "bad", _("still the default: change it now"))
		if _default_admin_password()
		else check("admin_password", _("Administrator password"), "ok", _("changed from the default"))
	)
	out.append(
		check("developer_mode", _("Developer mode"), "warn", _("on: turn it off on a public server"))
		if cint(frappe.conf.get("developer_mode"))
		else check("developer_mode", _("Developer mode"), "ok", _("off"))
	)
	s = frappe.get_single("System Settings")
	strong = cint(s.enable_password_policy) and cint(s.minimum_password_score or 0) >= 2
	out.append(
		check(
			"password_policy",
			_("Password strength"),
			"ok" if strong else "warn",
			_("strong passwords required")
			if strong
			else _("weak passwords allowed: System Settings → Password"),
			"/app/system-settings",
		)
	)
	tries, wait = cint(s.allow_consecutive_login_attempts), cint(s.allow_login_after_fail)
	out.append(
		check(
			"lockout",
			_("Wrong passwords"),
			"ok" if 0 < tries <= 10 and wait >= 60 else "warn",
			_("locked after {0} tries for {1} minutes").format(tries, round(wait / 60, 1))
			if tries
			else _("never locked: System Settings → Login"),
			"/app/system-settings",
		)
	)
	out.append(
		check(
			"two_factor",
			_("Two-factor login"),
			"ok" if cint(s.enable_two_factor_auth) else "info",
			_("on")
			if cint(s.enable_two_factor_auth)
			else _("off: worth turning on for staff (System Settings → Login → Two Factor Authentication)"),
			"/app/system-settings",
		)
	)
	key = frappe.conf.get("resdesk_meili_key") or frappe.db.get_single_value("RD Settings", "meili_api_key")
	out.append(
		check("search_key", _("Search engine key"), "ok", _("set"))
		if key
		else check(
			"search_key",
			_("Search engine key"),
			"bad",
			_("none: anyone who can reach Meilisearch can change the index"),
		)
	)
	return out
