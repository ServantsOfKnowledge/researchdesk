"""Lending: the Circulation Desk's calls and the member's own (My library, holds on a book's page).

Settings → Features → *Members, lending and acquisitions* turns it on. The rules are core/lending.py; this
reads the facts from the database, asks them, and writes what follows. Staff are Managers and Cataloguers.
Nothing here sends email: the member sees what is due on My library, and staff see what is overdue on the
Circulation Desk (account messages are the only email Research Desk sends).
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import add_days, cint, flt, getdate, now_datetime, nowdate

from sok_resdesk import access, features
from sok_resdesk.core import lending as rules
from sok_resdesk.core.access import like_literal

STAFF = ("System Manager", "ResDesk Manager", "ResDesk Cataloguer")
OUT_OF_CIRCULATION = ("Lost", "Withdrawn")


# -- small helpers -----------------------------------------------------------------------------------


def today():
	return getdate(nowdate())


def _s():
	from sok_resdesk.catalogue import settings

	return settings()


def currency() -> str:
	return (_s().get("lending_currency") or "₹").strip()


def _closed() -> set[int]:
	return rules.closed_days(_s().get("lending_closed_days") or "")


def _say(code: str) -> str:
	return _(rules.REASONS[code])


def refuse(code: str) -> None:
	frappe.throw(_say(code), title=_("Not allowed"))


def _category(name: str) -> frappe._dict:
	row = frappe.db.get_value(
		"RD Patron Category",
		name,
		[
			"loan_days",
			"max_loans",
			"max_renewals",
			"max_holds",
			"fine_per_day",
			"grace_days",
			"fine_cap",
			"block_fines_over",
		],
		as_dict=True,
	)
	return row or frappe._dict(
		loan_days=14,
		max_loans=3,
		max_renewals=2,
		max_holds=3,
		fine_per_day=0,
		grace_days=0,
		fine_cap=0,
		block_fines_over=0,
	)


def _patron(name: str) -> frappe._dict:
	row = frappe.db.get_value(
		"RD Patron",
		name,
		["name", "full_name", "category", "status", "valid_until", "user", "department", "institution_id"],
		as_dict=True,
	)
	if not row:
		frappe.throw(_("No such member."))
	return row


def patron_of(user: str | None = None) -> frappe._dict | None:
	"""The member behind a portal account, or None."""
	user = user or frappe.session.user
	if user == "Guest":
		return None
	name = frappe.db.get_value("RD Patron", {"user": user}, "name")
	return _patron(name) if name else None


def fines_due(patron: str) -> float:
	return flt(
		frappe.db.sql(
			"select coalesce(sum(amount), 0) from `tabRD Fine` where patron=%s and status='Due'", patron
		)[0][0]
	)


def loans_out(patron: str) -> int:
	return frappe.db.count("RD Loan", {"patron": patron, "status": "Out"})


def _standing(p) -> str | None:
	return rules.patron_standing(p.status, p.valid_until and getdate(p.valid_until), today())


def _on() -> None:
	if not features.on("lending"):
		frappe.throw(features.off_message("lending"), title=_("Switched off"))


def _staff() -> None:
	_on()
	frappe.only_for(STAFF)


def _title(item: str) -> str:
	return frappe.db.get_value("RD Item", item, "title") or item


# -- copies and holds --------------------------------------------------------------------------------


def _release_copy(copy: str, item: str) -> dict | None:
	"""A copy came back or its hold ended: the next member waiting for the title gets it on the hold
	shelf, else it goes back on the shelf. Returns the hold it was kept for, if any."""
	nxt = frappe.db.get_value(
		"RD Hold",
		{"item": item, "status": "Waiting"},
		["name", "patron"],
		as_dict=True,
		order_by="placed_on asc",
		for_update=True,  # two copies of one title coming back together must not take the same hold
	)
	if not nxt:
		frappe.db.set_value("RD Copy", copy, "status", "Available")
		return None
	days = cint(_s().get("lending_hold_days") or 7)
	frappe.db.set_value(
		"RD Hold", nxt.name, {"status": "Ready", "copy": copy, "ready_until": add_days(today(), days)}
	)
	frappe.db.set_value("RD Copy", copy, "status", "On hold shelf")
	return nxt


def counts(item: str) -> tuple[int, int]:
	"""(copies the library can lend, of them on the shelf now) for a title."""
	lendable = frappe.get_all(
		"RD Copy",
		filters={"item": item, "status": ("not in", OUT_OF_CIRCULATION), "reference_only": 0},
		fields=["status"],
	)
	return len(lendable), sum(1 for c in lendable if c.status == "Available")


def _held_for(copy: str) -> str | None:
	return frappe.db.get_value("RD Hold", {"copy": copy, "status": "Ready"}, "patron")


# -- the Circulation Desk (staff) --------------------------------------------------------------------


def _loan_row(loan) -> dict:
	due = getdate(loan.due_on)
	return {
		"name": loan.name,
		"copy": loan.copy,
		"item": loan.item,
		"title": _title(loan.item),
		"due_on": str(due),
		"overdue": due < today(),
		"renewals": loan.renewals or 0,
	}


def snapshot(patron: str) -> dict:
	"""Everything the desk or My library shows about one member."""
	p = _patron(patron)
	cat = _category(p.category)
	loans = frappe.get_all(
		"RD Loan",
		filters={"patron": patron, "status": "Out"},
		fields=["name", "copy", "item", "due_on", "renewals"],
		order_by="due_on asc",
	)
	holds = frappe.get_all(
		"RD Hold",
		filters={"patron": patron, "status": ("in", ("Waiting", "Ready"))},
		fields=["name", "item", "status", "ready_until", "copy"],
		order_by="placed_on asc",
	)
	fines = frappe.get_all(
		"RD Fine",
		filters={"patron": patron, "status": "Due"},
		fields=["name", "amount", "reason", "note"],
		order_by="creation asc",
	)
	why = _standing(p)
	from sok_resdesk import ill, payments  # they use this module too

	return {
		"patron": {
			"name": p.name,
			"full_name": p.full_name,
			"category": p.category,
			"status": p.status,
			"valid_until": str(p.valid_until or ""),
			"department": p.department or "",
			"institution_id": p.institution_id or "",
		},
		"limits": {"loans": cat.max_loans, "holds": cat.max_holds, "renewals": cat.max_renewals},
		"standing": _say(why) if why else "",
		"loans": [_loan_row(loan) for loan in loans],
		"holds": [{**h, "title": _title(h.item), "ready_until": str(h.ready_until or "")} for h in holds],
		"fines": fines,
		"fines_total": round(sum(f.amount for f in fines), 2),
		"currency": currency(),
		"ill": ill.mine(patron),
		"pay_online": payments.configured(),
	}


@frappe.whitelist()
def find_patron(query: str) -> dict:
	"""A scanned card number or an ID number finds one member; a name or part of one finds a short list."""
	_staff()
	q = (query or "").strip()
	if not q:
		return {"choices": []}
	hit = frappe.db.get_value("RD Patron", q.upper(), "name")
	if not hit:
		wanted = rules.normal_id(q)
		if wanted:
			hit = frappe.db.sql(
				"select name from `tabRD Patron` where upper(replace(replace(replace(replace(institution_id,' ',''),'-',''),'/',''),'.','')) = %s limit 1",
				wanted,
			)
			hit = hit[0][0] if hit else None
	if hit:
		return {"snapshot": snapshot(hit)}
	like = f"%{like_literal(q)}%"
	rows = frappe.get_all(
		"RD Patron",
		or_filters={"full_name": ("like", like), "email": ("like", like), "phone": ("like", like)},
		fields=["name", "full_name", "category", "status", "department"],
		limit=10,
	)
	if len(rows) == 1:
		return {"snapshot": snapshot(rows[0].name)}
	return {"choices": rows}


@frappe.whitelist()
def desk_snapshot(patron: str) -> dict:
	_staff()
	return snapshot(patron)


@frappe.whitelist(methods=["POST"])
def checkout(patron: str, barcode: str) -> dict:
	"""Lend the copy with this barcode to this member."""
	_staff()
	return lend(patron, barcode)


def lend(patron: str, barcode: str) -> dict:
	"""The loan itself, with every rule of the member's category. The desk (staff) and the kiosk (the member
	after card and PIN) both come through here and nowhere else."""
	code = (barcode or "").strip().upper()
	copy = frappe.db.get_value(
		"RD Copy", code, ["name", "item", "status", "reference_only"], as_dict=True, for_update=True
	)
	if not copy:
		frappe.throw(_("No copy has the barcode {0}.").format(code))
	frappe.db.get_value("RD Patron", patron, "name", for_update=True)  # one loan at a time per member
	p = _patron(patron)
	cat = _category(p.category)
	why = rules.borrow_check(
		status=p.status,
		valid_until=p.valid_until and getdate(p.valid_until),
		today=today(),
		loans_out=loans_out(p.name),
		max_loans=cat.max_loans,
		fines_due=fines_due(p.name),
		block_fines_over=cat.block_fines_over,
		copy_status=copy.status,
		reference_only=bool(copy.reference_only),
		held_for=_held_for(copy.name),
		patron=p.name,
	)
	if why:
		refuse(why)
	due = rules.due_date(today(), cat.loan_days, _closed())
	loan = frappe.get_doc(
		{
			"doctype": "RD Loan",
			"copy": copy.name,
			"item": copy.item,
			"patron": p.name,
			"status": "Out",
			"issued_on": today(),
			"due_on": due,
			"renewals": 0,
			"issued_by": frappe.session.user,
		}
	)
	loan.insert(ignore_permissions=True)
	frappe.db.set_value("RD Copy", copy.name, "status", "On loan")
	# the member's own hold on this title is done
	for hold in frappe.get_all(
		"RD Hold",
		filters={"patron": p.name, "item": copy.item, "status": ("in", ("Waiting", "Ready"))},
		pluck="name",
	):
		frappe.db.set_value("RD Hold", hold, "status", "Fulfilled")
	return {
		"loan": loan.name,
		"title": _title(copy.item),
		"due_on": str(due),
		"snapshot": snapshot(p.name),
		"message": _("{0} lent to {1}, due {2}.").format(_title(copy.item), p.full_name, due),
	}


@frappe.whitelist(methods=["POST"])
def checkin(barcode: str) -> dict:
	"""A copy comes back: close the loan, charge a late fine, and keep the copy for the next member waiting."""
	_staff()
	code = (barcode or "").strip().upper()
	loan = frappe.db.get_value(
		"RD Loan",
		{"copy": code, "status": "Out"},
		["name", "item", "patron", "due_on"],
		as_dict=True,
		for_update=True,
	)
	if not loan:
		if frappe.db.exists("RD Copy", code):
			frappe.throw(_("{0} is not on loan.").format(code))
		frappe.throw(_("No copy has the barcode {0}.").format(code))
	p = _patron(loan.patron)
	cat = _category(p.category)
	amount = rules.fine(getdate(loan.due_on), today(), cat.fine_per_day, cat.grace_days, cat.fine_cap)
	frappe.db.set_value("RD Loan", loan.name, {"status": "Returned", "returned_on": today()})
	if amount:
		late = rules.days_overdue(getdate(loan.due_on), today(), 0)
		frappe.get_doc(
			{
				"doctype": "RD Fine",
				"patron": p.name,
				"loan": loan.name,
				"reason": "Overdue",
				"amount": amount,
				"status": "Due",
				"note": _("{0} days late").format(late),
			}
		).insert(ignore_permissions=True)
	kept = _release_copy(code, loan.item)
	for_whom = _patron(kept.patron).full_name if kept else ""
	message = _("{0} returned by {1}.").format(_title(loan.item), p.full_name)
	if amount:
		message += " " + _("Fine: {0}{1}.").format(currency(), amount)
	if for_whom:
		message += " " + _("Keep it on the hold shelf for {0}.").format(for_whom)
	return {
		"title": _title(loan.item),
		"patron": p.name,
		"patron_name": p.full_name,
		"fine": amount,
		"hold_for": for_whom,
		"message": message,
	}


def _renew(loan, standing_of) -> dict:
	"""Extend one open loan, if the rules allow; `standing_of` is the member the renewal is for."""
	cat = _category(standing_of.category)
	due = getdate(loan.due_on)
	why = rules.renew_check(
		renewals=loan.renewals or 0,
		max_renewals=cat.max_renewals,
		overdue=due < today(),
		waiting_holds=frappe.db.count("RD Hold", {"item": loan.item, "status": "Waiting"}),
		allow_overdue=bool(cint(_s().get("lending_renew_overdue"))),
		standing=_standing(standing_of),
	)
	if why:
		refuse(why)
	new_due = rules.due_date(today(), cat.loan_days, _closed())
	frappe.db.set_value("RD Loan", loan.name, {"due_on": new_due, "renewals": (loan.renewals or 0) + 1})
	return {"due_on": str(new_due), "message": _("Renewed: now due {0}.").format(new_due)}


def _open_loan(name: str):
	loan = frappe.db.get_value(
		"RD Loan",
		name,
		["name", "item", "patron", "due_on", "renewals", "status"],
		as_dict=True,
		for_update=True,
	)
	if not loan or loan.status != "Out":
		frappe.throw(_("That loan is not open."))
	return loan


@frappe.whitelist(methods=["POST"])
def renew(loan: str) -> dict:
	_staff()
	row = _open_loan(loan)
	return _renew(row, _patron(row.patron))


@frappe.whitelist(methods=["POST"])
def mark_lost(loan: str) -> dict:
	"""The member cannot return it: the loan is closed as lost and the copy's price becomes a fine."""
	_staff()
	row = _open_loan(loan)
	copy = frappe.db.get_value("RD Loan", row.name, "copy")
	frappe.db.set_value("RD Loan", row.name, {"status": "Lost", "returned_on": today()})
	frappe.db.set_value("RD Copy", copy, "status", "Lost")
	price = flt(frappe.db.get_value("RD Copy", copy, "price"))
	if price > 0:
		frappe.get_doc(
			{
				"doctype": "RD Fine",
				"patron": row.patron,
				"loan": row.name,
				"reason": "Lost",
				"amount": price,
				"status": "Due",
				"note": copy,
			}
		).insert(ignore_permissions=True)
	return {"snapshot": snapshot(row.patron), "message": _("Marked lost.")}


@frappe.whitelist(methods=["POST"])
def settle_fine(fine: str, waive: int = 0) -> dict:
	"""The member paid the fine (or the library waives it)."""
	_staff()
	row = frappe.db.get_value("RD Fine", fine, ["name", "patron", "status"], as_dict=True)
	if not row or row.status != "Due":
		frappe.throw(_("That fine is not due."))
	frappe.db.set_value("RD Fine", fine, {"status": "Waived" if cint(waive) else "Paid", "paid_on": today()})
	return {"snapshot": snapshot(row.patron)}


@frappe.whitelist()
def overview() -> dict:
	"""For the desk's side lists: what is overdue, and what waits on the hold shelf."""
	_staff()
	overdue = frappe.get_all(
		"RD Loan",
		filters={"status": "Out", "due_on": ("<", today())},
		fields=["name", "item", "patron", "due_on", "copy"],
		order_by="due_on asc",
		limit=100,
	)
	names = {p: frappe.db.get_value("RD Patron", p, "full_name") for p in {o.patron for o in overdue}}
	shelf = frappe.get_all(
		"RD Hold",
		filters={"status": "Ready"},
		fields=["name", "item", "patron", "copy", "ready_until"],
		order_by="ready_until asc",
		limit=100,
	)
	names.update({p: frappe.db.get_value("RD Patron", p, "full_name") for p in {s.patron for s in shelf}})
	return {
		"overdue": [
			{**o, "title": _title(o.item), "patron_name": names.get(o.patron), "due_on": str(o.due_on)}
			for o in overdue
		],
		"shelf": [
			{
				**s,
				"title": _title(s.item),
				"patron_name": names.get(s.patron),
				"ready_until": str(s.ready_until or ""),
			}
			for s in shelf
		],
	}


# -- holds (staff for a member, or the member for themselves) ----------------------------------------


def _hold_for(member: frappe._dict, item: str, by_member: bool = False) -> dict:
	book = frappe.db.get_value("RD Item", item, ["published", "visibility"], as_dict=True)
	if not book or (by_member and not (book.published and access.can_read(book.visibility))):
		frappe.throw(_("No such book."))  # a book the member may not see is not there for them
	frappe.db.get_value("RD Patron", member.name, "name", for_update=True)
	cat = _category(member.category)
	total, available = counts(item)
	has = bool(
		frappe.db.exists(
			"RD Hold", {"patron": member.name, "item": item, "status": ("in", ("Waiting", "Ready"))}
		)
		or frappe.db.sql(
			"select 1 from `tabRD Loan` l where l.patron=%s and l.item=%s and l.status='Out' limit 1",
			(member.name, item),
		)
	)
	why = rules.hold_check(
		standing=_standing(member),
		holds=frappe.db.count("RD Hold", {"patron": member.name, "status": ("in", ("Waiting", "Ready"))}),
		max_holds=cat.max_holds,
		already_has=has,
		copies_total=total,
		copies_available=available,
	)
	if why:
		refuse(why)
	hold = frappe.get_doc(
		{
			"doctype": "RD Hold",
			"item": item,
			"patron": member.name,
			"status": "Waiting",
			"placed_on": now_datetime(),
		}
	)
	hold.insert(ignore_permissions=True)
	return {
		"hold": hold.name,
		"message": _("Hold placed on {0}. We keep the next returned copy for you.").format(_title(item)),
	}


@frappe.whitelist(methods=["POST"])
def place_hold_for(patron: str, item: str) -> dict:
	_staff()
	return _hold_for(_patron(patron), item)


def cancel_hold_row(hold: str) -> None:
	row = frappe.db.get_value("RD Hold", hold, ["name", "item", "status", "copy"], as_dict=True)
	if not row or row.status not in ("Waiting", "Ready"):
		frappe.throw(_("That hold is not open."))
	frappe.db.set_value("RD Hold", hold, "status", "Cancelled")
	if row.status == "Ready" and row.copy:
		_release_copy(row.copy, row.item)


@frappe.whitelist(methods=["POST"])
def cancel_hold_staff(hold: str) -> dict:
	_staff()
	cancel_hold_row(hold)
	return {"message": _("Hold cancelled.")}


# -- the member (portal) -----------------------------------------------------------------------------


def _me() -> frappe._dict:
	_on()
	member = patron_of()
	if not member or member.status in (rules.PENDING, rules.LISTED, rules.REJECTED):
		frappe.throw(_("You are not a member of this library yet."), frappe.PermissionError)
	return member


@frappe.whitelist()
def my() -> dict:
	"""My library: my loans, holds and fines."""
	return snapshot(_me().name)


@frappe.whitelist(methods=["POST"])
def my_renew(loan: str) -> dict:
	member = _me()
	if frappe.db.get_value("RD Loan", loan, "patron") != member.name:
		frappe.throw(_("That is not your open loan."), frappe.PermissionError)  # the same words for any loan
	return _renew(_open_loan(loan), member)


@frappe.whitelist(methods=["POST"])
def my_hold(item: str) -> dict:
	return _hold_for(_me(), item, by_member=True)


@frappe.whitelist(methods=["POST"])
def my_cancel_hold(hold: str) -> dict:
	member = _me()
	if frappe.db.get_value("RD Hold", hold, "patron") != member.name:
		frappe.throw(_("That is not your hold."), frappe.PermissionError)
	cancel_hold_row(hold)
	return {"message": _("Hold cancelled.")}


PIN_FIELD = "kiosk_pin"


def has_pin(patron: str) -> bool:
	return bool(
		frappe.db.sql(
			"select 1 from `__Auth` where doctype='RD Patron' and name=%s and fieldname=%s",
			(patron, PIN_FIELD),
		)
	)


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=10, seconds=300)
def my_set_pin(pin: str, password: str) -> dict:
	"""A member chooses the PIN that goes with their card at a self-service kiosk (4 to 6 digits). It needs the
	account's password, so a borrowed browser cannot set one. Only a hash is kept, in the same place passwords
	are, not on the member's record."""
	member = _me()
	pin = str(pin or "").strip()
	if not (pin.isascii() and pin.isdigit() and 4 <= len(pin) <= 6):
		frappe.throw(_("A PIN is 4 to 6 digits."))
	from frappe.utils.password import check_password, update_password

	try:
		check_password(frappe.session.user, password or "")
	except frappe.AuthenticationError:
		frappe.throw(_("The password is not right."))
	update_password(member.name, pin, doctype="RD Patron", fieldname=PIN_FIELD)
	return {"message": _("Your PIN is set.")}


def availability(item: str) -> dict | None:
	"""For a book's page: how many copies the library has and how many are on the shelf (None: it has none,
	or lending is off)."""
	if not features.on("lending"):
		return None
	total, available = counts(item)
	if not total:
		return None
	member = patron_of()
	mine = {}
	if member:
		hold = frappe.db.get_value(
			"RD Hold",
			{"patron": member.name, "item": item, "status": ("in", ("Waiting", "Ready"))},
			["name", "status"],
			as_dict=True,
		)
		mine = {"hold": hold.name if hold else "", "hold_status": hold.status if hold else ""}
	return {
		"copies": total,
		"available": available,
		"waiting": frappe.db.count("RD Hold", {"item": item, "status": "Waiting"}),
		"member": bool(member and member.status in (rules.ACTIVE, rules.EXPIRED, rules.BLOCKED)),
		"logged_in": frappe.session.user != "Guest",
		**mine,
	}


# -- every night -------------------------------------------------------------------------------------


@features.scheduled("lending")
def daily() -> None:
	"""Holds that were not collected go to the next member; memberships past their end date expire; old
	returned loans are forgotten (Settings → Members and Lending → Keep Returned Loans)."""
	for hold in frappe.get_all(
		"RD Hold", filters={"status": "Ready", "ready_until": ("<", today())}, fields=["name", "item", "copy"]
	):
		frappe.db.set_value("RD Hold", hold.name, "status", "Expired")
		if hold.copy:
			_release_copy(hold.copy, hold.item)
	for name in frappe.get_all(
		"RD Patron", filters={"status": "Active", "valid_until": ("<", today())}, pluck="name"
	):
		frappe.db.set_value("RD Patron", name, "status", "Expired")
	for name in frappe.get_all(
		"RD Patron",
		filters={"status": "Rejected", "modified": ("<", add_days(now_datetime(), -30))},
		pluck="name",
	):
		frappe.delete_doc(
			"RD Patron", name, ignore_permissions=True, force=True
		)  # a turned-down sign-up is not kept
	keep = cint(_s().get("lending_keep_days"))
	if keep > 0:
		old = frappe.get_all(
			"RD Loan",
			filters={"status": ("in", ("Returned", "Lost")), "returned_on": ("<", add_days(today(), -keep))},
			pluck="name",
		)
		for i in range(0, len(old), 500):
			chunk = old[i : i + 500]
			due = set(
				frappe.get_all("RD Fine", filters={"loan": ("in", chunk), "status": "Due"}, pluck="loan")
			)
			free = [n for n in chunk if n not in due]
			if free:
				frappe.db.set_value(
					"RD Fine", {"loan": ("in", free)}, "loan", None
				)  # a settled fine keeps no book
				frappe.db.delete("RD Loan", {"name": ("in", free)})
	frappe.db.commit()
