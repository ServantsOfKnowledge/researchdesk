"""Item → Send to the Internet Archive: a book given to archive.org under the sender's own account.

A person with an archive.org account (library staff, or a depositor sending their own accepted
deposit) connects its access keys once (Desk → My archive.org Account, or the deposit page), then
sends a book from here. Nothing is sent without a review: the plan shows the archive.org
identifier, the collection, the account, the details and the files that go. What is sent is always
public (Research Desk never makes a dark or hidden item), so only books that are public here, with
a licence, and files held on this server can go. The sender confirms the work is theirs to give.

People sending their own work use the collection set in Settings. Staff may choose another
collection they may add to, and may send under a shared account kept on a Push Target (Internet
Archive) instead of their own. The upload runs in the background (books are large) and the book
records its state: queued, uploading, on archive.org, or failed (sending again resumes).
"""

from __future__ import annotations

import os

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

from sok_resdesk import deposit, features
from sok_resdesk.core import ia_upload as ia
from sok_resdesk.core.push import IAWriter, PushError

DOCTYPE = "RD Archive Account"
STAFF = deposit.STAFF
UPLOADERS = deposit.DEPOSITORS
KEYS_URL = "https://archive.org/account/s3.php"
STEPS = [
	"Log in to your account on archive.org (make one, free, if you have none).",
	"Open the page below: it shows your S3-like access key and secret key.",
	"Copy both here, under Connect.",
]
BUSY = ("Queued", "Uploading", "On archive.org")


def _is_staff(user: str | None = None) -> bool:
	return bool(set(frappe.get_roles(user or frappe.session.user)) & set(STAFF))


def _on() -> None:
	if not (features.on("sharing") or features.on("deposit")):
		frappe.throw(features.off_message("sharing"), title=_("Switched off"))


def _account(user: str):
	return frappe.get_doc(DOCTYPE, user) if frappe.db.exists(DOCTYPE, user) else None


def _my_keys(user: str) -> tuple[str, str] | None:
	acc = _account(user)
	if not acc or not acc.access_key:
		return None
	secret = acc.get_password("secret_key", raise_exception=False) or ""
	return (acc.access_key, secret) if secret else None


def _shared_targets() -> list[dict]:
	"""Internet Archive Push Targets with keys: shared accounts staff may send under."""
	rows = frappe.get_all(
		"RD Push Target",
		filters={"target_type": "Internet Archive", "enabled": 1},
		fields=["name", "target_name", "ia_access"],
	)
	return [r for r in rows if r.ia_access]


def _target_keys(name: str) -> tuple[str, str] | None:
	row = next((r for r in _shared_targets() if r.name == name), None)
	if not row:
		return None
	secret = frappe.get_doc("RD Push Target", name).get_password("ia_secret", raise_exception=False) or ""
	return (row.ia_access, secret) if secret else None


def default_collection() -> str:
	return (
		frappe.db.get_single_value("RD Settings", "ia_upload_collection") or ia.DEFAULT_COLLECTION
	).strip()


# -- my keys -----------------------------------------------------------------------------------------


@frappe.whitelist()
def status() -> dict:
	"""My connection: whether and as whom. The keys are never sent to the browser."""
	frappe.only_for(UPLOADERS)
	acc = _account(frappe.session.user)
	return {
		"connected": bool(acc and acc.ia_user),
		"ia_user": acc.ia_user if acc else "",
		"connected_on": str(acc.connected_on or "") if acc else "",
		"last_used": str(acc.last_used or "") if acc else "",
		"keys_url": KEYS_URL,
		"steps": [_(s) for s in STEPS],
	}


@frappe.whitelist(methods=["POST"])
def connect(access: str, secret: str) -> dict:
	"""Check the keys with archive.org, then keep them (the secret encrypted) for this person."""
	frappe.only_for(UPLOADERS)
	access, secret = (access or "").strip(), (secret or "").strip()
	if not access or not secret:
		frappe.throw(_("Paste both the access key and the secret key."))
	try:
		who = IAWriter(access, secret).check()
	except PushError as e:
		frappe.throw(str(e)[:300])
	user = frappe.session.user
	acc = _account(user) or frappe.new_doc(DOCTYPE)
	acc.user = user
	acc.ia_user = who
	acc.access_key = access
	acc.secret_key = secret
	acc.connected_on = now_datetime()
	acc.flags.ignore_permissions = True
	acc.save() if not acc.is_new() else acc.insert()
	return status()


@frappe.whitelist(methods=["POST"])
def disconnect() -> dict:
	frappe.only_for(UPLOADERS)
	if frappe.db.exists(DOCTYPE, frappe.session.user):
		frappe.delete_doc(DOCTYPE, frappe.session.user, ignore_permissions=True)
	return status()


# -- sending -----------------------------------------------------------------------------------------


def _item(name: str):
	"""The book, if this person may send it: staff any book, a depositor only their own deposit."""
	frappe.only_for(UPLOADERS)
	if not frappe.db.exists("RD Item", name):
		frappe.throw(_("No such item."))
	if not _is_staff() and not frappe.db.exists(
		deposit.DT, {"item": name, "depositor": frappe.session.user, "status": "Accepted"}
	):
		frappe.throw(_("You can send only your own accepted deposits."), frappe.PermissionError)
	return frappe.get_doc("RD Item", name)


def _files(doc) -> list[tuple[str, str]]:
	"""(name, path) of the files held on this server for the book."""
	from sok_resdesk.core.folder import HttpStore
	from sok_resdesk.local_source import store_for_item

	store = store_for_item(doc)
	if store is None or isinstance(store, HttpStore):
		return []
	names = dict.fromkeys([doc.local_pdf, *(doc.local_files or "").splitlines()])
	out = []
	for n in names:
		if not n or n.endswith("_meta.xml"):
			continue
		path = store.file_path(doc.local_path, n)
		if path and os.path.isfile(path):
			out.append((n, path))
	return out


def _accounts_for(user: str) -> list[dict]:
	mine = _account(user)
	out = [
		{
			"value": "me",
			"label": _("My account ({0})").format(mine.ia_user) if mine and mine.ia_user else _("My account"),
		}
	]
	if _is_staff(user):
		out += [{"value": f"target:{r.name}", "label": r.target_name or r.name} for r in _shared_targets()]
	return out


def _keys_for(account: str, user: str) -> tuple[str, str] | None:
	if account.startswith("target:"):
		return _target_keys(account[7:]) if _is_staff(user) else None
	return _my_keys(user)


def _description(doc) -> str:
	return " ".join(x for x in ((doc.description or "").strip(), (doc.rights or "").strip()) if x)


def _problem(doc, files, keys, identifier: str, collection: str, account: str) -> str:
	if doc.ia_sent_status in BUSY and doc.ia_sent_id:
		return _("Already sent to archive.org as {0} ({1}).").format(doc.ia_sent_id, _(doc.ia_sent_status))
	if doc.on_archive_org or doc.source == "Internet Archive":
		return _("This book already comes from archive.org.")
	if not doc.published or doc.visibility != "Public" or doc.access_status != "Open":
		return _(
			"Only a book that is public here can be sent: whatever is sent to archive.org is public there too."
		)
	if not (doc.licence_url or "").strip():
		return _("The book has no licence: set a Licence URL (Rights section) first.")
	if not (doc.title or "").strip():
		return _("The book has no title.")
	if not files:
		return _("The book's files are not held on this server, so there is nothing to upload.")
	if account.startswith("target:") and not _is_staff():
		return _("Only library staff send under a shared account.")
	if not keys:
		return _("Connect your archive.org account first (Research Desk → My archive.org Account).")
	if ia.identifier_problem(identifier):
		return _(ia.identifier_problem(identifier))
	if ia.collection_problem(collection):
		return _(ia.collection_problem(collection))
	if collection != default_collection() and not _is_staff():
		return _("Your work goes to the library's collection ({0}).").format(default_collection())
	return ""


@frappe.whitelist()
def plan(item: str, identifier: str = "", collection: str = "", account: str = "me") -> dict:
	"""What would be sent, and anything that stops it. Nothing is sent."""
	_on()
	doc = _item(item)
	user = frappe.session.user
	staff = _is_staff()
	account = account if staff else "me"
	collection = (collection or "").strip() if staff else ""
	collection = collection or default_collection()
	identifier = (
		ia.clean_identifier(identifier)
		or doc.ia_sent_id
		or ia.make_identifier(
			doc.title, doc.year, (doc.creator_display or "").split(";")[0], suffix=doc.item_id
		)
	)
	files = _files(doc)
	keys = _keys_for(account, user)
	problem = _problem(doc, files, keys, identifier, collection, account)
	out = {
		"identifier": identifier,
		"collection": collection,
		"may_choose_collection": staff,
		"account": account,
		"accounts": _accounts_for(user),
		"title": doc.title,
		"creators": doc.creator_display or "",
		"year": doc.year or "",
		"licence": doc.licence_url or "",
		"files": [{"name": ia.file_name(n), "size": os.path.getsize(p)} for n, p in files],
		"problem": problem,
		"name_taken": False,
		"url": f"https://archive.org/details/{identifier}",
		"public": True,
	}
	if problem or not keys:
		return out
	resume = doc.ia_sent_status == "Failed" and doc.ia_sent_id == identifier
	if not resume:
		try:
			out["name_taken"] = IAWriter(*keys).exists(identifier)
		except Exception as e:  # network trouble: say so, send nothing
			out["problem"] = _("archive.org did not answer: {0}").format(str(e)[:200])
	return out


@frappe.whitelist(methods=["POST"])
def send(item: str, identifier: str, collection: str = "", account: str = "me", confirmed: int = 0) -> dict:
	"""Queue the reviewed upload. The plan is made again first: nothing stale is sent."""
	if not cint(confirmed):
		frappe.throw(_("Confirm that the work is yours to give, and that it will be public on archive.org."))
	p = plan(item, identifier, collection, account)
	if p["problem"]:
		frappe.throw(p["problem"])
	if p["name_taken"]:
		frappe.throw(
			_("archive.org already has an item called {0}: choose another identifier.").format(
				p["identifier"]
			)
		)
	doc = _item(item)
	frappe.db.set_value(
		"RD Item",
		doc.name,
		{
			"ia_sent_id": p["identifier"],
			"ia_sent_status": "Queued",
			"ia_sent_by": frappe.session.user,
			"ia_sent_on": now_datetime(),
			"ia_sent_note": "",
		},
		update_modified=False,
	)
	frappe.db.commit()
	frappe.enqueue(
		"sok_resdesk.archive_upload.run_upload",
		queue="long",
		timeout=4 * 3600,
		item=doc.name,
		identifier=p["identifier"],
		collection=p["collection"],
		account=p["account"] if _is_staff() else "me",
		user=frappe.session.user,
	)
	return {"identifier": p["identifier"], "url": p["url"], "status": "Queued"}


@frappe.whitelist()
def state(item: str) -> dict:
	"""Where a sent book is: for the page that sent it."""
	doc = _item(item)
	return {
		"status": doc.ia_sent_status or "",
		"identifier": doc.ia_sent_id or "",
		"url": f"https://archive.org/details/{doc.ia_sent_id}" if doc.ia_sent_id else "",
		"note": doc.ia_sent_note or "",
	}


def _set(item: str, **values) -> None:
	frappe.db.set_value("RD Item", item, values, update_modified=False)
	frappe.db.commit()


def run_upload(item: str, identifier: str, collection: str, account: str, user: str) -> None:
	"""The background upload (as the sender): the first file makes the item, the rest join it."""
	frappe.set_user(user)
	doc = frappe.get_doc("RD Item", item)
	keys = _keys_for(account, user)
	files = _files(doc)
	if not keys or not files:
		_set(item, ia_sent_status="Failed", ia_sent_note=_("The keys or the files are no longer there."))
		return
	try:
		writer = IAWriter(*keys)
		who = writer.check()
		_set(item, ia_sent_status="Uploading")
		from sok_resdesk.catalogue import base_url

		first = {
			**ia.metadata_headers(
				title=doc.title,
				collection=collection,
				mediatype_=ia.mediatype([n for n, _p in files]),
				creators=[c.strip() for c in (doc.creator_display or "").split(";") if c.strip()],
				date=str(doc.year or ""),
				language=(doc.language or "").split(",")[0].strip(),
				description=_description(doc),
				subjects=[r.subject for r in doc.subjects or [] if r.subject],
				licence_url=doc.licence_url or "",
				source_url=f"{base_url()}/library/item/{doc.item_id}",
			)
		}
		for i, (name, path) in enumerate(files):
			with open(path, "rb") as fh:
				writer.upload(identifier, ia.file_name(name), fh, first if i == 0 else None)
	except Exception as e:
		frappe.log_error(title="Upload to archive.org failed")
		_set(item, ia_sent_status="Failed", ia_sent_note=str(e)[:500])
		return
	_set(item, ia_sent_status="On archive.org", ia_sent_note="")
	if account == "me" and frappe.db.exists(DOCTYPE, user):
		frappe.db.set_value(DOCTYPE, user, "last_used", now_datetime(), update_modified=False)
	frappe.get_doc("RD Item", item).add_comment(
		"Info",
		_("{0} sent this book to archive.org as {1} ({2}, collection {3}).").format(
			user, identifier, who, collection
		),
	)
	frappe.db.commit()
