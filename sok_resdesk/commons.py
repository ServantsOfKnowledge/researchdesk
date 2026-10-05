"""Item → Send to Wikimedia Commons: a photograph given to Commons under the sender's own account.

Nothing is sent without a review: the plan shows the file name, the description page exactly as
Commons will get it, the categories (which must already exist), the licence, the Wikidata items
it depicts and whether Commons already has the same file. The sender confirms the photograph is
theirs to give under that licence. One photograph at a time; the upload is refused, never
forced, on any warning from Commons (a duplicate, a name taken).
"""

from __future__ import annotations

import os

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

from sok_resdesk import features
from sok_resdesk.core import commons as cm
from sok_resdesk.core import wikimedia as wm

SUMMARY = "Uploaded with SOK Research Desk"


def _item(name: str):
	from sok_resdesk import wikimedia

	frappe.only_for(wikimedia.WORKERS)
	if not frappe.db.exists("RD Item", name):
		frappe.throw(_("No such item."))
	doc = frappe.get_doc("RD Item", name)
	if doc.item_type != "Photograph":
		frappe.throw(_("Only photographs go to Commons."))
	return doc


def _original(doc) -> str:
	from sok_resdesk import pdfs

	return pdfs.leaf_image_path(doc.item_id, 0) or ""


def _client() -> wm.WikimediaClient:
	from sok_resdesk import wikimedia

	return wm.WikimediaClient.for_site(cm.SITE, wikimedia.need_account())


def _missing(client, titles: list[str]) -> list[str]:
	"""Which of these pages do not exist on Commons."""
	if not titles:
		return []
	pages = client.get(action="query", prop="info", titles="|".join(titles)).get("query", {}).get("pages", [])
	return [p["title"] for p in pages if p.get("missing")]


def _problem(doc, path: str, account: str) -> str:
	if not account:
		return _("Connect your own Wikimedia account first (Research Desk → My Wikimedia Account).")
	if doc.commons_file:
		return _("Already sent to Commons as {0}.").format(doc.commons_file)
	if doc.access_status != "Open":
		return _("This photograph is not open to read here, so it is not published elsewhere.")
	if cm.licence_problem(doc.licence_url):
		return _(cm.licence_problem(doc.licence_url))
	if not (doc.creator_display or "").strip():
		return _("Name the photographer (Creators) first: Commons credits the author.")
	if not path or not os.path.isfile(path):
		return _("The original file is not held here.")
	if not cm.extension(path):
		return _("Commons takes JPEG, PNG, TIFF and WebP photographs.")
	if os.path.getsize(path) > cm.MAX_BYTES:
		return _("The file is over 100 MB, which is more than a plain upload takes.")
	return ""


@frappe.whitelist()
@features.needs("photographs")
def plan(item: str, filename: str = "", description: str = "", categories: str = "") -> dict:
	"""What would be sent for this photograph, and anything that stops it. Writes nothing to Commons."""
	from sok_resdesk import wikimedia
	from sok_resdesk.catalogue import base_url

	doc = _item(item)
	path = _original(doc)
	account = frappe.db.get_value(wikimedia.DOCTYPE, frappe.session.user, "wikimedia_user") or ""
	out = {
		"account": account,
		"problem": _problem(doc, path, account),
		"site": cm.SITE,
		"licence": "",
		"depicts": [{"qid": q, "label": label} for q, label in cm.depicts(doc.ph_depicts)],
		"duplicate": [],
		"name_taken": False,
		"missing_categories": [],
		"needs_upload_right": False,
	}
	ext = cm.extension(path) if path else "jpg"
	desc = (description or "").strip() or ". ".join(
		x
		for x in (
			doc.title,
			doc.description,
			(_("Event: {0}").format(doc.ph_event) if doc.ph_event else ""),
			(_("Shown: {0}").format(", ".join((doc.ph_people or "").splitlines())) if doc.ph_people else ""),
		)
		if x
	)
	name = cm.clean_name(filename) or cm.file_name(doc.title, ext, doc.ph_taken_on, doc.ph_place)
	if not name.lower().endswith("." + ext):
		name += "." + ext
	cats = cm.split_names(categories)
	licence = cm.licence_for(doc.licence_url)
	out.update(
		{
			"filename": name,
			"description": desc,
			"categories": cats,
			"licence": licence[1] if licence else "",
			"author": doc.creator_display or "",
			"taken": doc.ph_taken_on or "",
			"size": os.path.getsize(path) if path and os.path.isfile(path) else 0,
			"dimensions": doc.ph_dimensions or "",
		}
	)
	if licence:
		out["wikitext"] = cm.description_page(
			description=desc,
			lang=(doc.language or "").split(",")[0].strip().lower()[:3],
			taken=doc.ph_taken_on or "",
			author=doc.creator_display or "",
			source=f"{base_url()}/library/item/{doc.item_id}",
			licence=licence[0],
			categories=cats,
			gps=doc.ph_gps or "",
			accession=doc.item_id,
		)
	if out["problem"]:
		return out
	client = _client()
	try:
		if "upload" not in set(client.whoami()["rights"]):
			out["needs_upload_right"] = True
			out["problem"] = _(
				"Your token is not allowed to upload files: register the consumer again with “Upload new files” granted."
			)
			return out
		found = client.get(action="query", list="allimages", aisha1=cm.sha1_of(path), ailimit=5)
		out["duplicate"] = [i["name"] for i in found.get("query", {}).get("allimages", [])]
		out["name_taken"] = not _missing(client, [f"File:{name}"])
		out["missing_categories"] = [
			t.split(":", 1)[1] for t in _missing(client, [f"Category:{c}" for c in cats])
		]
	except wm.WikimediaError as e:
		frappe.throw(_("Commons did not answer as expected: {0}").format(str(e)[:300]))
	return out


@frappe.whitelist(methods=["POST"])
@features.needs("photographs")
def send(item: str, filename: str, description: str = "", categories: str = "", confirmed: int = 0) -> dict:
	"""Upload the reviewed photograph. The plan is made again first: nothing stale is sent."""
	from sok_resdesk import wikimedia

	if not cint(confirmed):
		frappe.throw(_("Confirm that the photograph is yours to give under this licence."))
	p = plan(item, filename, description, categories)
	if p["problem"]:
		frappe.throw(p["problem"])
	if p["duplicate"]:
		frappe.throw(_("Commons already has this file as {0}.").format(", ".join(p["duplicate"])))
	if p["name_taken"]:
		frappe.throw(_("A file called {0} already exists on Commons: choose another name.").format(p["filename"]))
	if p["missing_categories"]:
		frappe.throw(
			_("These categories do not exist on Commons: {0}. Choose existing ones.").format(
				", ".join(p["missing_categories"])
			)
		)
	doc = _item(item)
	client = _client()
	try:
		client.upload(p["filename"], _original(doc), p["wikitext"], SUMMARY)
	except wm.WikimediaError as e:
		frappe.throw(_("Commons did not accept the file: {0}").format(str(e)[:300]))
	result = {"file": p["filename"], "url": f"https://{cm.SITE}/wiki/File:{p['filename'].replace(' ', '_')}", "depicts": ""}
	qids = [d["qid"] for d in p["depicts"]]
	if qids:
		try:
			pages = client.get(action="query", prop="info", titles=f"File:{p['filename']}")["query"]["pages"]
			client.post(
				action="wbeditentity",
				id=f"M{pages[0]['pageid']}",
				data=cm.depicts_claims(qids),
				summary="Depicts, from SOK Research Desk",
				token=client.csrf(),
			)
			result["depicts"] = "added"
		except (wm.WikimediaError, KeyError, IndexError) as e:
			result["depicts"] = _("The file is uploaded but its depicts statements were not added: {0}").format(
				str(e)[:200]
			)
	me = frappe.db.get_value(wikimedia.DOCTYPE, frappe.session.user, "wikimedia_user")
	frappe.db.set_value(
		"RD Item",
		doc.name,
		{"commons_file": p["filename"], "commons_sent_by": me, "commons_sent_on": now_datetime()},
		update_modified=False,
	)
	wikimedia.touch(frappe.session.user)
	doc.add_comment("Info", _("{0} sent this photograph to Commons as {1} ({2}).").format(frappe.session.user, p["filename"], me))
	return result
