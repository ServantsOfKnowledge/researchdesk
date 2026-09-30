"""Access control glue: who is a member, bulk visibility changes, reader sign-up.

The rules themselves live in core/access.py (no Frappe, unit-tested).
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint

from sok_resdesk.catalogue import settings
from sok_resdesk.core import access as core
from sok_resdesk.core.access import LOGIN_TO_FIND, LOGIN_TO_READ, PUBLIC, VISIBILITIES  # noqa: F401
from sok_resdesk.holding import hold_when_paused

READER_ROLE = "ResDesk Reader"
STAFF_ROLES = ("System Manager", "ResDesk Manager", "ResDesk Cataloguer")
MANAGER_ROLES = ("System Manager", "ResDesk Manager")
BACKGROUND_OVER = 200  # bulk changes bigger than this run in a queue worker


# -- who is looking ------------------------------------------------------------------

def _roles(user: str | None = None) -> set[str]:
	return set(frappe.get_roles(user or frappe.session.user))


def is_staff(user: str | None = None) -> bool:
	user = user or frappe.session.user
	return user == "Administrator" or bool(_roles(user) & set(STAFF_ROLES))


def is_member(user: str | None = None) -> bool:
	"""A logged-in reader: has the Reader role or a staff role.

	With open sign-up every logged-in account counts, so accounts made before the
	setting changed don't need the role added by hand.
	"""
	user = user or frappe.session.user
	if user == "Guest":
		return False
	if is_staff(user) or READER_ROLE in _roles(user):
		return True
	return settings().reader_signup == core.SIGNUP_OPEN


def guest_mode() -> str:
	return settings().guest_access or core.GUEST_ITEM


def can_find(visibility: str | None, user: str | None = None) -> bool:
	return core.can_find(visibility, guest_mode(), is_member(user))


def can_read(visibility: str | None, user: str | None = None) -> bool:
	return core.can_read(visibility, guest_mode(), is_member(user))


def search_filter(kind: str) -> str | None:
	return core.search_filter(kind, guest_mode(), is_member())


def sql_condition(column: str = "visibility") -> str:
	return core.sql_condition(guest_mode(), is_member(), column)


def viewer() -> dict:
	"""What the portal templates need to know about the current visitor."""
	user = frappe.session.user
	member = is_member(user)
	mode = guest_mode()
	return {
		"logged_in": user != "Guest",
		"member": member,
		"staff": is_staff(user),
		"pending": user != "Guest" and not member,
		"guest_mode": mode,
		"signup": (settings().reader_signup or core.SIGNUP_CLOSED) != core.SIGNUP_CLOSED,
		"login_required": mode == core.GUEST_NONE and user == "Guest",
	}


def login_url(path: str) -> str:
	from urllib.parse import quote

	return f"/login?redirect-to={quote(path, safe='/')}"


def require_login_for_portal() -> None:
	"""Send guests to the login page when the site is set to 'Login required'."""
	if frappe.session.user == "Guest" and guest_mode() == core.GUEST_NONE:
		frappe.local.flags.redirect_location = login_url(frappe.local.request.full_path.rstrip("?") if frappe.local.request else "/library")
		raise frappe.Redirect


# -- new books -------------------------------------------------------------------------

def rules() -> list[dict]:
	return [
		{"match_on": r.match_on, "value": r.value, "visibility": r.visibility}
		for r in settings().get("access_rules") or []
	]


def initial_visibility(record: dict, profile: str | None) -> tuple[str, str]:
	profile_vis = frappe.db.get_value("RD Ingest Profile", profile, "visibility") if profile else None
	record = {**record, "ingest_profile": profile or ""}
	return core.initial_visibility(record, profile_vis, rules(), settings().default_visibility)


# -- bulk changes ------------------------------------------------------------------------

def _check_visibility(visibility: str) -> str:
	if visibility not in VISIBILITIES:
		frappe.throw(_("Visibility must be one of: {0}").format(", ".join(VISIBILITIES)))
	return visibility


@hold_when_paused("long")
def apply_visibility(names: list[str], visibility: str, set_by: str = "Bulk", wait: bool = False) -> int:
	"""Set visibility on many items at once, in the database and in both search indexes."""
	_check_visibility(visibility)
	names = list(dict.fromkeys(n for n in names if n))
	for i in range(0, len(names), 500):
		chunk = names[i:i + 500]
		frappe.db.sql(
			"""update `tabRD Item` set visibility=%(v)s, visibility_set_by=%(by)s, modified=now()
			where name in %(names)s""",
			{"v": visibility, "by": set_by[:140], "names": tuple(chunk)},
		)
		frappe.db.commit()
	update_index_visibility(names, visibility, wait=wait)
	return len(names)


def update_index_visibility(names: list[str], visibility: str, wait: bool = False) -> None:
	"""Rewrite the visibility attribute of book and page documents in place (no re-index)."""
	from sok_resdesk.search import MeiliClient, SearchError, _quote

	if not names:
		return
	try:
		client = MeiliClient.from_settings()
		last = None
		# books: PUT is a partial update, but it would also create a stub for an unindexed id,
		# so only touch documents that are already in the index
		for i in range(0, len(names), 500):
			chunk = names[i:i + 500]
			res = client._req("POST", f"/indexes/{client.books}/documents/fetch", json={
				"filter": f"item_id IN [{', '.join(_quote(n) for n in chunk)}]", "fields": ["id"], "limit": 1000,
			})
			todo = [{"id": d["id"], "visibility": visibility} for d in res.get("results", [])]
			if todo:
				last = client._req("PUT", f"/indexes/{client.books}/documents", json=todo)
		for i in range(0, len(names), 50):
			flt = f"item_id IN [{', '.join(_quote(n) for n in names[i:i + 50])}]"
			offset = 0
			while True:
				res = client._req("POST", f"/indexes/{client.pages}/documents/fetch",
								  json={"filter": flt, "fields": ["id"], "limit": 10000, "offset": offset})
				ids = [d["id"] for d in res.get("results", [])]
				if ids:
					last = client._req("PUT", f"/indexes/{client.pages}/documents",
									   json=[{"id": x, "visibility": visibility} for x in ids])
				offset += len(ids)
				if not ids or offset >= res.get("total", 0):
					break
		if wait and last:
			client.wait(last, timeout=120)  # tasks run in order: the last one done means all are
	except SearchError as e:
		frappe.log_error("Research Desk: could not update visibility in the search index", str(e))


def select_items(names=None, filters=None, collection=None, profile=None, language=None,
				 search=None, everything: bool = False) -> list[str]:
	"""Resolve one of several ways of choosing items into a list of item names."""
	if names:
		if isinstance(names, str):
			names = frappe.parse_json(names) if names.strip().startswith("[") else [n.strip() for n in names.split(",")]
		return [n for n in names if n]
	if filters not in (None, "", "[]", "{}", []):
		return frappe.get_list("RD Item", filters=frappe.parse_json(filters) if isinstance(filters, str) else filters,
							   pluck="name", limit_page_length=0)
	if search:
		return _names_from_search(frappe.parse_json(search) if isinstance(search, str) else search)
	conditions, values = [], {}
	if collection:
		conditions.append("concat('\n', ifnull(collections, ''), '\n') like %(coll)s")
		values["coll"] = f"%\n{collection.strip()}\n%"
	if profile:
		conditions.append("ingest_profile = %(profile)s")
		values["profile"] = profile
	if language:
		conditions.append("(language_label = %(lang)s or language = %(lang)s)")
		values["lang"] = language
	if not conditions and not everything:
		frappe.throw(_("Choose the items: selected rows, a filter, a collection, a profile, a language or a search."))
	where = " and ".join(conditions) or "1=1"
	return frappe.db.sql_list(f"select name from `tabRD Item` where {where}", values)


def _names_from_search(spec: dict) -> list[str]:
	"""Every item matching a portal search (what the staff bar on /library sends)."""
	from sok_resdesk.search import MeiliClient, build_filter

	client = MeiliClient.from_settings()
	flt = build_filter(spec.get("filters") or {})
	q = (spec.get("q") or "").strip()
	names: list[str] = []
	if spec.get("mode") == "pages" and q:
		# books that have a matching page
		for offset in range(0, 10000, 1000):
			res = client.search(client.pages, {"q": q, "filter": flt, "limit": 1000, "offset": offset,
											   "attributesToRetrieve": ["item_id"]})
			hits = res.get("hits", [])
			names.extend(h["item_id"] for h in hits)
			if len(hits) < 1000:
				break
		return list(dict.fromkeys(names))
	if not q:
		# no text query: fetch by filter, no 10,000 cap
		expr = " AND ".join("(" + " OR ".join(p) + ")" if isinstance(p, list) else p for p in flt) or None
		offset = 0
		while True:
			res = client._req("POST", f"/indexes/{client.books}/documents/fetch",
							  json={"filter": expr, "fields": ["item_id"], "limit": 10000, "offset": offset})
			batch = [d["item_id"] for d in res.get("results", [])]
			names.extend(batch)
			offset += len(batch)
			if not batch or offset >= res.get("total", 0):
				return names
	for page in range(1, 11):
		res = client.search(client.books, {"q": q, "filter": flt, "hitsPerPage": 1000, "page": page,
										   "attributesToRetrieve": ["item_id"]})
		names.extend(h["item_id"] for h in res.get("hits", []))
		if page >= res.get("totalPages", 0):
			break
	return names


@frappe.whitelist()
def bulk_set_visibility(visibility: str, names=None, filters=None, collection=None, profile=None,
						language=None, search=None, everything: int = 0) -> dict:
	"""Set who can see a group of books. Staff only.

	Choose the books with exactly one of: names (list), filters (Desk list filters),
	collection, profile, language, search ({"q", "mode", "filters"} from the portal),
	or everything=1.
	"""
	frappe.only_for(STAFF_ROLES)
	_check_visibility(visibility)
	selected = select_items(names, filters, collection, profile, language, search, bool(cint(everything)))
	if not selected:
		return {"count": 0, "queued": False, "message": _("No books matched.")}
	if len(selected) > BACKGROUND_OVER:
		frappe.enqueue("sok_resdesk.access.apply_visibility", queue="long", timeout=6 * 3600,
					   names=selected, visibility=visibility, set_by="Bulk")
		return {"count": len(selected), "queued": True,
				"message": _("Changing {0} books to “{1}” in the background. It takes about a minute per few thousand books.")
				.format(len(selected), _(visibility))}
	apply_visibility(selected, visibility, "Bulk", wait=True)
	return {"count": len(selected), "queued": False,
			"message": _("{0} books are now “{1}”.").format(len(selected), _(visibility))}


def _rule_records() -> dict[str, dict]:
	"""Just the fields rules look at, for every item, in a few queries (fast on 50,000+ books)."""
	records: dict[str, dict] = {}
	for row in frappe.db.sql(
		"select name, collections, language, language_label, source, ingest_profile from `tabRD Item`", as_dict=True
	):
		records[row.name] = {
			"collections": [c for c in (row.collections or "").splitlines() if c.strip()],
			"language": row.language, "language_label": row.language_label, "source": row.source,
			"ingest_profile": row.ingest_profile or "", "subjects": [], "creators": [],
		}
	for parent, subject in frappe.db.sql("select parent, subject from `tabRD Item Subject` where parenttype='RD Item'"):
		if parent in records:
			records[parent]["subjects"].append(subject)
	for parent, given, creator in frappe.db.sql(
		"select parent, name_as_given, creator from `tabRD Item Creator` where parenttype='RD Item'"
	):
		if parent in records:
			records[parent]["creators"] += [x for x in (given, creator) if x]
	return records


@hold_when_paused("long")
def recompute(include_manual: bool = False) -> dict:
	"""Re-apply the profiles, rules and default to books already in the catalogue."""
	rows = frappe.db.sql(
		"select name, ifnull(visibility_set_by, '') as set_by, ifnull(visibility, '') as visibility from `tabRD Item`",
		as_dict=True,
	)
	profiles = dict(frappe.db.sql("select name, ifnull(visibility, '') from `tabRD Ingest Profile`"))
	site_rules, default = rules(), settings().default_visibility
	records = _rule_records()
	moved: dict[tuple[str, str], list[str]] = {}
	relabel: dict[str, list[str]] = {}
	for row in rows:
		if not include_manual and row.set_by in ("Manual", "Bulk"):
			continue
		record = records.get(row.name, {})
		vis, by = core.initial_visibility(record, profiles.get(record.get("ingest_profile")), site_rules, default)
		if vis != row.visibility:
			moved.setdefault((vis, by), []).append(row.name)
		elif by != row.set_by:
			relabel.setdefault(by, []).append(row.name)
	for by, names in relabel.items():  # same visibility, only the reason changed: no search update needed
		for i in range(0, len(names), 500):
			frappe.db.sql("update `tabRD Item` set visibility_set_by=%s where name in %s", (by[:140], tuple(names[i:i + 500])))
	frappe.db.commit()
	changed = sum(apply_visibility(names, vis, by) for (vis, by), names in moved.items())
	return {"changed": changed}


@frappe.whitelist()
def apply_rules(include_manual: int = 0) -> dict:
	"""Settings button: apply profiles, rules and the default to existing books."""
	frappe.only_for(MANAGER_ROLES)
	frappe.enqueue("sok_resdesk.access.recompute", queue="long", timeout=6 * 3600,
				   include_manual=bool(cint(include_manual)))
	return {"message": _("Applying access rules to existing books in the background.")}


@frappe.whitelist()
def apply_profile(profile: str) -> dict:
	"""Ingest Profile button: give every book from this profile the profile's visibility."""
	frappe.only_for(MANAGER_ROLES)
	vis = frappe.db.get_value("RD Ingest Profile", profile, "visibility")
	if vis not in VISIBILITIES:
		frappe.throw(_("Set “Access for its books” on this profile first."))
	names = frappe.get_all("RD Item", filters={"ingest_profile": profile}, pluck="name")
	if len(names) > BACKGROUND_OVER:
		frappe.enqueue("sok_resdesk.access.apply_visibility", queue="long", timeout=6 * 3600,
					   names=names, visibility=vis, set_by="Profile")
		return {"count": len(names), "message": _("Updating {0} books in the background.").format(len(names))}
	apply_visibility(names, vis, "Profile", wait=True)
	return {"count": len(names), "message": _("{0} books are now “{1}”.").format(len(names), _(vis))}


# -- readers and sign-up --------------------------------------------------------------------

def on_user_insert(doc, method=None):
	"""A new account from the portal's sign-up page: make it a reader, or ask staff to approve."""
	if doc.user_type != "Website User" or doc.name in ("Guest", "Administrator"):
		return
	if frappe.session.user not in ("Guest", doc.name):
		return  # created by staff in the Desk: they choose the roles themselves
	# open sign-up gives the Reader role through Portal Settings → Default Role (see apply_signup_setting)
	mode = settings().reader_signup or core.SIGNUP_CLOSED
	if mode == core.SIGNUP_APPROVE and not frappe.db.exists("RD Reader Request", {"user": doc.name}):
		frappe.get_doc({
			"doctype": "RD Reader Request", "user": doc.name, "full_name": doc.full_name,
			"email": doc.email, "status": "Pending",
		}).insert(ignore_permissions=True)


def notify_managers(request) -> None:
	managers = {
		u for u in frappe.get_all("Has Role", filters={"role": ("in", MANAGER_ROLES), "parenttype": "User"}, pluck="parent")
		if u not in ("Guest",) and frappe.db.get_value("User", u, "enabled")
	}
	for user in managers:
		try:
			frappe.get_doc({
				"doctype": "Notification Log", "for_user": user, "type": "Alert",
				"document_type": "RD Reader Request", "document_name": request.name,
				"subject": _("{0} asked for a reader account").format(request.full_name or request.email),
			}).insert(ignore_permissions=True)
		except Exception:  # a missing alert must not stop the sign-up
			frappe.log_error(title="Research Desk: could not alert a manager about a reader request")


def add_reader(email: str, full_name: str = "", send_welcome: bool = True) -> str:
	"""Create (or upgrade) a portal account with the Reader role. Used by the CLI."""
	email = email.strip().lower()
	if frappe.db.exists("User", email):
		user = frappe.get_doc("User", email)
	else:
		first, _sep, last = (full_name or email.split("@")[0]).partition(" ")
		user = frappe.get_doc({
			"doctype": "User", "email": email, "first_name": first, "last_name": last,
			"user_type": "Website User", "send_welcome_email": 1 if send_welcome else 0,
		})
		user.flags.ignore_permissions = True
		user.insert()
	if READER_ROLE not in {r.role for r in user.roles}:
		user.flags.ignore_permissions = True
		user.add_roles(READER_ROLE)
	return user.name


@frappe.whitelist()
def decide_requests(names, status: str) -> str:
	"""Approve or reject several reader requests (list view action)."""
	frappe.only_for(MANAGER_ROLES)
	if status not in ("Approved", "Rejected", "Pending"):
		frappe.throw(_("Unknown status"))
	names = frappe.parse_json(names) if isinstance(names, str) else names
	for name in names or []:
		doc = frappe.get_doc("RD Reader Request", name)
		if doc.status != status:
			doc.status = status
			doc.save()
	return _("{0} requests marked {1}").format(len(names or []), _(status))


def apply_signup_setting(s=None) -> None:
	"""Mirror the sign-up choice into Frappe's own Website Settings."""
	s = s or frappe.get_single("RD Settings")
	mode = s.reader_signup or core.SIGNUP_CLOSED
	ws = frappe.get_single("Website Settings")
	disable = 1 if mode == core.SIGNUP_CLOSED else 0
	if cint(ws.disable_signup) != disable:
		ws.disable_signup = disable
		ws.flags.ignore_permissions = True
		ws.save()
	# Frappe gives new sign-ups Portal Settings' default role
	ps = frappe.get_single("Portal Settings")
	role = READER_ROLE if mode == core.SIGNUP_OPEN else None
	if ps.meta.has_field("default_role") and (ps.default_role or None) != role and (role or ps.default_role == READER_ROLE):
		ps.default_role = role
		ps.flags.ignore_permissions = True
		ps.save()
