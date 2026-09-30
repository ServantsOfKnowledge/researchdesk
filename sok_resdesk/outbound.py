"""Send catalogue metadata to other systems: Internet Archive, Koha, Wikidata, webhooks.

A Push Target says where and which books; a Push Run is one pass over them with a log.
What was sent is remembered per book (RD External Record) so unchanged books are skipped
and later runs update rather than duplicate (Koha biblionumber, Wikidata QID).
"""

from __future__ import annotations

import time

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

from sok_resdesk.catalogue import base_url, item_to_record
from sok_resdesk.core import metaio
from sok_resdesk.core.marc import to_marcxml_record
from sok_resdesk.core.push import (
	IA_FIELDS,
	IAWriter,
	KohaClient,
	PushError,
	Webhook,
	WikidataClient,
	ia_patch,
	payload_hash,
	wikidata_entity,
)

MANAGERS = ("System Manager", "ResDesk Manager")
RUN = "tabRD Push Run"


# -- clients ------------------------------------------------------------------------------------

def _client(t):
	if t.target_type == "Internet Archive":
		return IAWriter(t.ia_access or "", t.get_password("ia_secret", raise_exception=False) or "")
	if t.target_type == "Koha":
		secret = t.get_password("koha_password", raise_exception=False) or ""
		auth = ("oauth" if t.koha_auth == "OAuth2 Client Credentials" else "basic", t.koha_user or "", secret)
		return KohaClient(t.koha_url or "", auth, t.koha_framework or "")
	if t.target_type == "Wikidata":
		return WikidataClient(t.wd_api or "https://www.wikidata.org/w/api.php", t.wd_user or "",
							  t.get_password("wd_password", raise_exception=False) or "")
	return Webhook(t.hook_url or "", t.get_password("hook_secret", raise_exception=False) or "")


@frappe.whitelist()
def test_connection(target: str) -> dict:
	frappe.only_for(MANAGERS)
	t = frappe.get_doc("RD Push Target", target)
	c = _client(t)
	try:
		if t.target_type == "Wikidata":
			who = c.login()
		elif t.target_type == "Webhook":
			who = f"HTTP {c.send('ping', {'target': t.name, 'portal': base_url()})}"
		else:
			who = c.check()
	except Exception as e:  # PushError and network errors
		frappe.throw(_("Connection failed: {0}").format(str(e)[:300]))
	return {"message": _("Connected ({0}).").format(who)}


# -- choosing books --------------------------------------------------------------------------------

def _books(t) -> list[str]:
	if t.scope == "Collection":
		names = frappe.db.sql_list(
			"""select distinct c.parent from `tabRD Item Collection` c join `tabRD Item` i on i.name=c.parent
			where c.collection=%s and i.published=1 order by i.creation""", t.collection)
	else:
		names = frappe.get_all("RD Item", filters={"published": 1}, pluck="name", order_by="creation asc")
	if t.target_type == "Internet Archive" and names:
		on_ia = set(frappe.get_all("RD Item", filters={"name": ("in", names), "on_archive_org": 1}, pluck="name"))
		names = [n for n in names if n in on_ia]
	return names


def in_scope(t, item: str) -> bool:
	published, on_ia = frappe.db.get_value("RD Item", item, ["published", "on_archive_org"]) or (0, 0)
	if not published or (t.target_type == "Internet Archive" and not on_ia):
		return False
	if t.scope == "Collection":
		return bool(frappe.db.exists("RD Item Collection", {"parent": item, "collection": t.collection}))
	return True


# -- per-book push ----------------------------------------------------------------------------------

def _external(target: str, item: str):
	name = frappe.db.get_value("RD External Record", {"target": target, "item": item}, "name")
	return frappe.get_doc("RD External Record", name) if name else None


def _remember(target: str, item: str, ext_id: str, url: str, fingerprint: str, ext=None):
	ext = ext or _external(target, item) or frappe.new_doc("RD External Record")
	ext.update({"target": target, "item": item, "external_id": ext_id, "external_url": url,
				"last_pushed": now_datetime(), "last_hash": fingerprint})
	ext.save(ignore_permissions=True)


def push_one(t, client, item: str, dry: bool, force: bool = False) -> tuple[str, str]:
	"""Returns (outcome, message); outcome is sent | unchanged | skipped."""
	record = item_to_record(frappe.get_doc("RD Item", item))
	portal = f"{base_url()}/library/item/{item}"
	ext = _external(t.name, item)

	if t.target_type == "Internet Archive":
		desired = metaio.ia_metadata(record)
		fields = [f.strip() for f in (t.ia_fields or "").replace("\n", ",").split(",") if f.strip()]
		patch = ia_patch(client.current(item), desired, fields or IA_FIELDS)
		if not patch:
			return "unchanged", "already matches archive.org"
		summary = ", ".join(op["path"][1:] for op in patch)
		if dry:
			return "sent", f"would update {summary}"
		result = client.write(item, patch)
		_remember(t.name, item, item, f"https://archive.org/details/{item}", payload_hash(patch), ext)
		return "sent", f"updated {summary} (task {result.get('task_id')})"

	if t.target_type == "Koha":
		marcxml = to_marcxml_record(record, base_url(), with_namespace=True)
		fingerprint = payload_hash(marcxml)
		if ext and ext.last_hash == fingerprint and not force:
			return "unchanged", f"biblio {ext.external_id} already up to date"
		if dry:
			return "sent", f"would {'update biblio ' + ext.external_id if ext and ext.external_id else 'create a biblio'}"
		koha_url = (t.koha_url or "").rstrip("/")
		if ext and ext.external_id:
			try:
				client.update(ext.external_id, marcxml)
				_remember(t.name, item, ext.external_id,
						  f"{koha_url}/cgi-bin/koha/catalogue/detail.pl?biblionumber={ext.external_id}", fingerprint, ext)
				return "sent", f"updated biblio {ext.external_id}"
			except PushError as e:
				if str(e) != "gone":
					raise
		biblio = client.create(marcxml)
		_remember(t.name, item, biblio, f"{koha_url}/cgi-bin/koha/catalogue/detail.pl?biblionumber={biblio}", fingerprint, ext)
		return "sent", f"created biblio {biblio}"

	if t.target_type == "Wikidata":
		data = wikidata_entity(record, portal)
		fingerprint = payload_hash(data)
		if ext and ext.last_hash == fingerprint and not force:
			return "unchanged", f"{ext.external_id} already up to date"
		qid = (ext.external_id if ext else None) or (client.find_by_ia(item) if record.get("on_archive_org") else None)
		summary = "Research Desk: metadata from Servants of Knowledge"
		if qid:
			if dry:
				return "sent", f"would add missing statements to {qid}"
			n = client.add_missing(qid, data, summary)
			_remember(t.name, item, qid, f"https://www.wikidata.org/wiki/{qid}", fingerprint, ext)
			return ("sent" if n else "unchanged"), f"{qid}: {n} statements added"
		if not cint(t.wd_create):
			return "skipped", "no Wikidata item yet (Create New Items is off)"
		if dry:
			return "sent", f"would create an item with {len(data['claims'])} statements"
		qid = client.create(data, summary)
		_remember(t.name, item, qid, f"https://www.wikidata.org/wiki/{qid}", fingerprint, ext)
		return "sent", f"created {qid}"

	# webhook
	payload = metaio.json_record(record, base_url())
	fingerprint = payload_hash(payload)
	if ext and ext.last_hash == fingerprint and not force:
		return "unchanged", "not changed since last sent"
	if dry:
		return "sent", "would POST the record"
	status = client.send("record.updated", payload)
	_remember(t.name, item, "", t.hook_url, fingerprint, ext)
	return "sent", f"HTTP {status}"


# -- runs -----------------------------------------------------------------------------------------

def _log(run: str, line: str):
	frappe.db.sql(f"update `{RUN}` set log = right(concat(ifnull(log,''), %s), 200000) where name=%s",
				  (f"{now_datetime().strftime('%H:%M:%S')} {line}\n", run))


@frappe.whitelist()
def start(target: str, force: int = 0, dry_run: int | None = None, items=None) -> str:
	"""Push Now / Dry Run from the form or the API."""
	frappe.only_for(MANAGERS)
	return _start(target, force, dry_run, items, "Manual")


def _start(target: str, force: int = 0, dry_run: int | None = None, items=None, triggered_by: str = "Manual") -> str:
	t = frappe.get_doc("RD Push Target", target)
	dry = cint(t.dry_run) if dry_run in (None, "") else cint(dry_run)
	run = frappe.get_doc({"doctype": "RD Push Run", "target": target, "status": "Queued", "dry_run": dry,
						  "triggered_by": triggered_by}).insert(ignore_permissions=True)
	frappe.db.set_value("RD Push Target", target, "last_run", run.name, update_modified=False)
	frappe.enqueue("sok_resdesk.outbound.run", queue="long", timeout=12 * 3600, run_name=run.name, force=cint(force),
				   items=frappe.parse_json(items) if isinstance(items, str) else items,
				   enqueue_after_commit=True, job_id=f"resdesk-push-{run.name}")
	return run.name


def _counts(run_name: str, counts: dict, extra: str = "", values: tuple = ()):
	frappe.db.sql(f"update `{RUN}` set sent=%s, unchanged=%s, skipped=%s, failed=%s{extra} where name=%s",
				  (counts["sent"], counts["unchanged"], counts["skipped"], counts["failed"], *values, run_name))


def run(run_name: str, force: int = 0, items: list | None = None) -> None:
	r = frappe.get_doc("RD Push Run", run_name)
	if r.status == "Cancelled":
		return
	t = frappe.get_doc("RD Push Target", r.target)
	names = items or _books(t)
	frappe.db.sql(f"update `{RUN}` set status='Running', total=%s where name=%s", (len(names), run_name))
	_log(run_name, f"{'DRY RUN: ' if r.dry_run else ''}{len(names)} books → {t.target_type} ({t.name})")
	frappe.db.commit()
	counts = {"sent": 0, "unchanged": 0, "skipped": 0, "failed": 0}
	failed_in_a_row = 0
	try:
		client = _client(t)
		if t.target_type == "Wikidata" and not r.dry_run:
			_log(run_name, f"logged in as {client.login()}")
	except Exception as e:
		_log(run_name, f"FAILED to connect: {e}")
		frappe.db.sql(f"update `{RUN}` set status='Failed', finished_on=%s where name=%s", (now_datetime(), run_name))
		frappe.db.commit()
		return
	for n, item in enumerate(names, 1):
		if frappe.db.get_value("RD Push Run", run_name, "status") == "Cancelled":
			_log(run_name, "cancelled")
			break
		try:
			outcome, msg = push_one(t, client, item, bool(r.dry_run), bool(force))
			counts[outcome] += 1
			failed_in_a_row = 0
			if outcome != "unchanged" or len(names) <= 50:
				label = "WOULD" if r.dry_run and outcome == "sent" else outcome.upper()
				_log(run_name, f"{label:9} {item}: {msg}")
		except Exception as e:
			frappe.db.rollback()
			counts["failed"] += 1
			failed_in_a_row += 1
			_log(run_name, f"FAILED    {item}: {str(e)[:300]}")
			if failed_in_a_row >= 10:
				_log(run_name, "stopping: 10 books in a row failed (is the other system reachable?)")
				break
		if n % 10 == 0 or n == len(names):
			_counts(run_name, counts)
		frappe.db.commit()
		if t.target_type == "Wikidata" and not r.dry_run:
			time.sleep(1)  # Wikidata asks bots to edit at most about once a second
	status = frappe.db.get_value("RD Push Run", run_name, "status")
	final = "Cancelled" if status == "Cancelled" else ("Completed with Errors" if counts["failed"] else "Completed")
	_counts(run_name, counts, ", status=%s, finished_on=%s", (final, now_datetime()))
	_log(run_name, f"Done: {counts['sent']} {'would be sent' if r.dry_run else 'sent'}, {counts['unchanged']} unchanged, "
		 f"{counts['skipped']} skipped, {counts['failed']} failed")
	frappe.db.commit()


@frappe.whitelist()
def cancel(run_name: str) -> None:
	"""Stop a push run: a queued one never starts, a running one stops after its current book."""
	frappe.only_for(MANAGERS)
	frappe.db.sql(f"update `{RUN}` set status='Cancelled' where name=%s and status in ('Queued','Running')", run_name)
	_log(run_name, f"cancel requested by {frappe.session.user}")
	frappe.db.commit()
	from frappe.utils.background_jobs import get_redis_conn
	from rq.job import Job

	try:
		job = Job.fetch(f"{frappe.local.site}||resdesk-push-{run_name}", connection=get_redis_conn())
		if job.get_status() == "queued":
			job.cancel()
			frappe.db.set_value("RD Push Run", run_name, "finished_on", now_datetime(), update_modified=False)
	except Exception:
		pass


# -- automatic pushes -------------------------------------------------------------------------------

def on_item_change(doc, method=None):
	"""RD Item saved (form, bulk edit, import): queue a push to targets that want it."""
	if doc.flags.from_ingest or frappe.flags.in_install or frappe.flags.in_migrate:
		return
	for name in frappe.get_all("RD Push Target", filters={"enabled": 1, "auto_push": 1}, pluck="name"):
		t = frappe.get_cached_doc("RD Push Target", name)
		if in_scope(t, doc.name):
			frappe.enqueue("sok_resdesk.outbound.auto_push", queue="default", target=name, item=doc.name,
						   job_id=f"resdesk-autopush-{name}-{doc.name}", deduplicate=True, enqueue_after_commit=True)


def auto_push(target: str, item: str):
	if frappe.db.get_value("RD Push Target", target, "enabled"):
		_start(target, items=[item], triggered_by="Automatic")
