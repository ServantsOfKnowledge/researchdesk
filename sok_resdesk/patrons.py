"""Members: joining the portal with an ID card, approval by staff, and the member's ID card.

A library that lends keeps a *roster* of its members (students, staff, subscribers): each is an RD Patron
with status *Listed* and the number on their own ID card. A person who joins the portal types that number and
their date of birth, or the email the library has for them. A match is a member at once (the Reader role, an
active membership, a card to show). Anything else becomes a *Pending* member, with the picture of the ID card
if they sent one, for staff to look at and approve. The answer to the person is the same whether the number
was on the roster or not, so the form cannot be used to find out who is a member.
"""

from __future__ import annotations

import base64

import frappe
from frappe import _
from frappe.utils import cint, getdate, now_datetime, nowdate

from sok_resdesk import access, features, signup
from sok_resdesk.core import idphoto
from sok_resdesk.core import lending as rules
from sok_resdesk.core import signup as signup_rules
from sok_resdesk.core.barcode import svg as barcode_svg
from sok_resdesk.lending import STAFF
from sok_resdesk.ratelimit import rate_limit

MEMBER_STATUSES = (rules.ACTIVE, rules.EXPIRED, rules.BLOCKED)


def _on() -> None:
	if not features.on("lending"):
		frappe.throw(features.off_message("lending"), title=_("Switched off"))


def default_category() -> str:
	"""The category new sign-ups get: the one chosen in Settings, else the only one, else none."""
	chosen = frappe.db.get_single_value("RD Settings", "lending_default_category")
	if chosen and frappe.db.exists("RD Patron Category", chosen):
		return chosen
	names = frappe.get_all("RD Patron Category", pluck="name", limit=2)
	return names[0] if len(names) == 1 else ""


def _roster_row(id_number: str):
	"""The roster member (listed, not yet joined) with this ID number, or None."""
	wanted = rules.normal_id(id_number)
	if not wanted:
		return None
	rows = frappe.db.sql(
		"""select name, email, date_of_birth from `tabRD Patron`
		where status='Listed' and (user is null or user='')
		and upper(replace(replace(replace(replace(institution_id,' ',''),'-',''),'/',''),'.','')) = %s
		limit 1""",
		wanted,
		as_dict=True,
	)
	return rows[0] if rows else None


def _dob(text: str):
	try:
		return getdate(text) if (text or "").strip() else None
	except Exception:
		return None


TRIES = 10  # wrong guesses at one ID number in an hour, from anyone, before it is refused for a while


def _guess_key(id_number: str) -> str:
	return f"resdesk:idtries:{rules.normal_id(id_number)}"


def _check_tries(id_number: str) -> None:
	"""Dates of birth are few, so an ID number could be tried against all of them: after a few wrong
	answers it is closed for the hour, whoever is asking."""
	if cint(frappe.cache.get_value(_guess_key(id_number))) >= TRIES:
		frappe.throw(_("Too many tries with that ID number. Please ask the library."))


def _wrong_guess(id_number: str) -> None:
	key = _guess_key(id_number)
	frappe.cache.set_value(key, cint(frappe.cache.get_value(key)) + 1, expires_in_sec=3600)


def _forget_photo(patron: str) -> None:
	"""The picture of the ID card is kept only while staff decide: deleted once they have."""
	url = frappe.db.get_value("RD Patron", patron, "id_card_photo")
	if not url:
		return
	for name in frappe.get_all("File", filters={"file_url": url, "attached_to_name": patron}, pluck="name"):
		frappe.delete_doc("File", name, ignore_permissions=True, force=True)
	frappe.db.set_value("RD Patron", patron, "id_card_photo", None)


def _activate(patron: str, user) -> None:
	"""The member is confirmed: tie the account, start the membership and give the Reader role."""
	user.flags.ignore_permissions = (
		True  # the roles of the person being confirmed, not the one pressing the button
	)
	doc = frappe.get_doc("RD Patron", patron)
	doc.user = user.name
	doc.status = rules.ACTIVE
	doc.joined_on = now_datetime()
	doc.date_of_birth = None  # it did its job; the library keeps no more of it than it needs
	if not doc.valid_until:
		months = frappe.db.get_value("RD Patron Category", doc.category, "validity_months")
		doc.valid_until = rules.membership_end(getdate(nowdate()), cint(months))
	doc.flags.ignore_permissions = True
	doc.save()
	_forget_photo(patron)
	user.add_roles(access.READER_ROLE)


def _keep_photo(patron: str, photo: str) -> None:
	try:
		content = idphoto.clean(photo)
	except idphoto.PhotoError:
		return  # a bad picture does not stop the sign-up; staff can ask for another
	from frappe.utils.file_manager import save_file

	saved = save_file(f"id-{patron}.jpg", content, "RD Patron", patron, is_private=1)
	frappe.db.set_value("RD Patron", patron, "id_card_photo", saved.file_url)


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=6, seconds=3600)
def apply(
	full_name: str = "",
	email: str = "",
	password: str = "",
	id_number: str = "",
	date_of_birth: str = "",
	photo: str = "",
	rd_hp: str = "",
) -> dict:
	"""Join the portal as a member of this library, with the number on an ID card.

	The answer is the same whether or not the roster matched (My library shows the truth), so it cannot be
	used to test dates of birth against an ID number; and only a date of birth confirms a member at once,
	because an email is typed by anyone."""
	_on()
	signup.require_json()
	fields, why = signup_rules.clean(full_name, email, password, rd_hp)
	if why == "trap":
		return {"joined": 1, "status": "joined", "next": "/library/loans"}
	messages = {
		"name": _("Please give your name."),
		"email": _("That email address does not look right."),
		"password": _("Please choose a password of at least {0} characters.").format(
			signup_rules.MIN_PASSWORD
		),
	}
	if why:
		frappe.throw(messages[why])
	idn = (id_number or "").strip()[:60]
	if not rules.normal_id(idn):
		frappe.throw(_("Please give the number on your ID card."))
	category = default_category()
	if not category:
		frappe.throw(_("This library has not opened membership yet. Please ask the library."))
	_check_tries(idn)
	user = signup.make_user(fields, reader_request=False)
	row = _roster_row(idn)
	level = rules.match_level(row, _dob(date_of_birth), fields["email"]) if row else ""
	if level == "strong":
		_activate(row.name, user)
	else:
		if not level:
			_wrong_guess(idn)
		_wait_for_staff(row if level else None, user, fields, category, idn, _dob(date_of_birth), photo)
	frappe.db.commit()
	login = getattr(frappe.local, "login_manager", None)  # none outside a web request (tests)
	if login:
		login.login_as(user.name)
	return {"joined": 1, "status": "joined", "next": "/library/loans"}


def _wait_for_staff(row, user, fields: dict, category: str, idn: str, dob, photo: str) -> None:
	"""A pending member for a librarian to approve: the roster row itself when only the email matched,
	else a new one (with what the person claimed)."""
	if row:
		patron = frappe.get_doc("RD Patron", row.name)
		patron.user = user.name
		patron.status = rules.PENDING
		patron.flags.ignore_permissions = True
		patron.save()
	else:
		taken = frappe.db.get_value(
			"RD Patron", {"institution_id": idn, "status": ("!=", rules.REJECTED)}, "name"
		)
		patron = frappe.get_doc(
			{
				"doctype": "RD Patron",
				"full_name": fields["full_name"],
				"email": fields["email"],
				"category": category,
				"status": rules.PENDING,
				"user": user.name,
				"date_of_birth": dob,
				# an ID number already on file is not entered twice: staff see what was claimed
				"institution_id": "" if taken else idn,
				"notes": _("Gave ID number {0}, already on file as {1}.").format(idn, taken) if taken else "",
			}
		)
		patron.flags.ignore_permissions = True
		patron.insert()
	if photo:
		_keep_photo(patron.name, photo)
	access.notify_managers(patron, _("A member is waiting for approval: {0}").format(fields["full_name"]))


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=10, seconds=3600)
def claim(id_number: str, date_of_birth: str = "") -> dict:
	"""A signed-in person links their account to the roster (they joined before, or were added by staff).
	Only the date of birth proves it: the email of a self-made account has not been checked by anyone."""
	_on()
	user = frappe.session.user
	if user == "Guest":
		frappe.throw(_("Please log in first."), frappe.PermissionError)
	if frappe.db.exists("RD Patron", {"user": user}):
		frappe.throw(_("Your account is already linked to a membership."))
	_check_tries(id_number)
	row = _roster_row(id_number)
	if not (row and rules.match_level(row, _dob(date_of_birth), "") == "strong"):
		_wrong_guess(id_number)
		frappe.throw(
			_("We could not match that to the roster. Please ask the library to check your membership.")
		)
	# one account per roster row, even when two requests arrive together
	if frappe.db.get_value("RD Patron", row.name, "user", for_update=True):
		frappe.throw(
			_("We could not match that to the roster. Please ask the library to check your membership.")
		)
	_activate(row.name, frappe.get_doc("User", user))
	return {"status": "member", "next": "/library/loans"}


def _managers() -> None:
	"""Granting the Reader role is a manager's call, as with reader requests."""
	_on()
	frappe.only_for(access.MANAGER_ROLES)


@frappe.whitelist(methods=["POST"])
def approve(patron: str) -> dict:
	"""A manager accepts a pending member: active, with the Reader role."""
	_managers()
	doc = frappe.get_doc("RD Patron", patron)
	if doc.status not in (rules.PENDING, rules.REJECTED):
		frappe.throw(_("Only a pending member can be approved."))
	if not doc.user:
		frappe.throw(_("This member has no portal account yet."))
	_activate(patron, frappe.get_doc("User", doc.user))
	return {"message": _("{0} is now a member.").format(doc.full_name)}


@frappe.whitelist(methods=["POST"])
def reject(patron: str) -> dict:
	_managers()
	doc = frappe.get_doc("RD Patron", patron)
	if doc.status != rules.PENDING:
		frappe.throw(_("Only a pending member can be turned down."))
	doc.status = rules.REJECTED
	doc.date_of_birth = None
	doc.flags.ignore_permissions = True
	doc.save()
	_forget_photo(patron)
	return {"message": _("{0} was turned down.").format(doc.full_name)}


# -- the ID card -------------------------------------------------------------------------------------


def _photo_uri(url: str) -> str:
	"""The member's photo as a data URI (it is a private file, so the page carries it, once access is checked)."""
	if not url:
		return ""
	try:
		content = frappe.get_doc("File", {"file_url": url}).get_content()
		content = content.encode() if isinstance(content, str) else content
		mime = idphoto.mime_of(content)
		return f"data:{mime};base64,{base64.b64encode(content).decode()}" if mime else ""
	except Exception:
		return ""


def card_context(patron: str) -> dict:
	"""What the printed or on-screen card shows. The caller has checked who may see it."""
	from sok_resdesk.catalogue import settings

	row = frappe.db.get_value(
		"RD Patron",
		patron,
		["name", "full_name", "category", "department", "institution_id", "valid_until", "photo", "status"],
		as_dict=True,
	)
	s = settings()
	return {
		"name": row.name,
		"full_name": row.full_name,
		"category": row.category,
		"department": row.department or "",
		"institution_id": row.institution_id or "",
		"valid_until": str(row.valid_until or ""),
		"status": row.status,
		"photo": _photo_uri(row.photo),
		"barcode": barcode_svg(row.name, height=44, module=2),
		"library": s.portal_title or "SOK Research Desk",
		"logo": s.portal_logo or "",
		"back": s.get("lending_card_back") or "",
	}


def cards_for(requested: str) -> list[dict]:
	"""The cards a signed-in person may see: staff any (a comma list of numbers), a member their own."""
	_on()
	user = frappe.session.user
	if user != "Guest" and set(frappe.get_roles(user)) & set(STAFF) and requested:
		names = [n.strip().upper() for n in requested.split(",") if n.strip()][:60]
		names = [n for n in names if frappe.db.exists("RD Patron", n)]
	else:
		own = frappe.db.get_value("RD Patron", {"user": user, "status": ("in", MEMBER_STATUSES)}, "name")
		names = [own] if own else []
	return [card_context(n) for n in names]
