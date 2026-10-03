"""Usage statistics for the portal (Settings → Usage Statistics), with as little weight as can be.

* **Built-in**: Frappe's own page-view log (Website Settings → view tracking): counted on this
  server, nothing leaves it; the Research Desk dashboard shows the numbers.
* **PostHog**, **Plausible** or **Umami**: public/js/analytics.js loads the service's script on
  portal pages only (never the Desk), cookieless, and sends a few named events (a search, a
  reader opened, a citation copied, a note, a proofread page) besides page views. Nothing about
  who the reader is goes with them.

The browser asks for the choice once per visit (config, cached here and in the visit).
"""

from __future__ import annotations

from urllib.parse import urlparse

import frappe
from frappe import _

PROVIDERS = ("Off", "Built-in", "PostHog", "Plausible", "Umami")
EXTERNAL = ("PostHog", "Plausible", "Umami")
CACHE_KEY = "resdesk:analytics-config"


@frappe.whitelist(allow_guest=True, methods=["GET"])
def config() -> dict:
	"""What portal pages load: {provider, host, key} (all public: they are in every page anyway)."""
	cached = frappe.cache.get_value(CACHE_KEY)
	if cached is not None:
		return cached
	s = frappe.get_cached_doc("RD Settings")
	provider = s.get("analytics_provider") or "Off"
	out = {"provider": provider if provider in EXTERNAL else ""}
	if out["provider"] and s.get("analytics_host") and s.get("analytics_key"):
		out.update({"host": s.analytics_host.rstrip("/"), "key": s.analytics_key.strip()})
	else:
		out = {"provider": ""}
	frappe.cache.set_value(CACHE_KEY, out, expires_in_sec=3600)
	return out


def validate_settings(s) -> None:
	provider = s.get("analytics_provider") or "Off"
	if provider not in PROVIDERS:
		frappe.throw(_("Unknown statistics service {0}").format(provider))
	if provider in EXTERNAL:
		host = (s.get("analytics_host") or "").strip().rstrip("/")
		url = urlparse(host)
		if url.scheme != "https" or not url.netloc:
			frappe.throw(
				_("The statistics service address must start with https://, e.g. https://eu.i.posthog.com")
			)
		if not (s.get("analytics_key") or "").strip():
			frappe.throw(_("Give the project key or site id for {0}.").format(provider))
		s.analytics_host = host


def apply_settings(s) -> None:
	"""Built-in statistics = Frappe's page-view log on; anything else = off (no double counting)."""
	frappe.cache.delete_value(CACHE_KEY)
	ws = frappe.get_single("Website Settings")
	if not ws.meta.has_field("enable_view_tracking"):
		return
	want = 1 if (s.get("analytics_provider") or "Off") == "Built-in" else 0
	if int(ws.enable_view_tracking or 0) != want:
		ws.enable_view_tracking = want
		ws.flags.ignore_permissions = True
		ws.save()


def page_views(days: int = 7) -> dict | None:
	"""For the dashboard, with Built-in statistics: views and visitors over `days`, top books."""
	if not frappe.db.exists("DocType", "Web Page View"):
		return None
	since = frappe.utils.add_days(frappe.utils.nowdate(), -days)
	views = frappe.db.count("Web Page View", {"creation": (">=", since)})
	unique = frappe.db.count("Web Page View", {"creation": (">=", since), "is_unique": "1"})
	top = frappe.db.sql(
		"""select path, count(*) as views from `tabWeb Page View`
		where creation >= %s and path like '%%library/item/%%' group by path order by views desc limit 5""",
		since,
		as_dict=True,
	)
	for t in top:
		t.item = t.path.split("library/item/", 1)[-1].split("/")[0].split("?")[0]
		t.title = frappe.db.get_value("RD Item", t.item, "title") or t.item
	return {"views": views, "visitors": unique, "top": top}
