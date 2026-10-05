"""Send catalogue metadata to other systems: Internet Archive, Koha, Wikidata, webhooks.

A Push Target says where and which books; a Push Run is one pass over them with a log.
What was sent is remembered per book (RD External Record) so unchanged books are skipped
and later runs update rather than duplicate (Koha biblionumber, Wikidata QID).
"""

from __future__ import annotations

import json
import time

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

from sok_resdesk import features
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
from sok_resdesk.holding import hold_when_paused

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
		return WikidataClient(
			t.wd_api or "https://www.wikidata.org/w/api.php",
			t.wd_user or "",
			t.get_password("wd_password", raise_exception=False) or "",
		)
	return Webhook(t.hook_url or "", t.get_password("hook_secret", raise_exception=False) or "")


@frappe.whitelist()
@features.needs("sharing")
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
			where c.collection=%s and i.published=1 order by i.creation""",
			t.collection,
		)
	else:
		names = frappe.get_all("RD Item", filters={"published": 1}, pluck="name", order_by="creation asc")
	if t.target_type == "Internet Archive" and names:
		on_ia = set(
			frappe.get_all("RD Item", filters={"name": ("in", names), "on_archive_org": 1}, pluck="name")
		)
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
	ext.update(
		{
			"target": target,
			"item": item,
			"external_id": ext_id,
			"external_url": url,
			"last_pushed": now_datetime(),
			"last_hash": fingerprint,
		}
	)
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
			return (
				"sent",
				f"would {'update biblio ' + ext.external_id if ext and ext.external_id else 'create a biblio'}",
			)
		koha_url = (t.koha_url or "").rstrip("/")
		if ext and ext.external_id:
			try:
				client.update(ext.external_id, marcxml)
				_remember(
					t.name,
					item,
					ext.external_id,
					f"{koha_url}/cgi-bin/koha/catalogue/detail.pl?biblionumber={ext.external_id}",
					fingerprint,
					ext,
				)
				return "sent", f"updated biblio {ext.external_id}"
			except PushError as e:
				if str(e) != "gone":
					raise
		biblio = client.create(marcxml)
		_remember(
			t.name,
			item,
			biblio,
			f"{koha_url}/cgi-bin/koha/catalogue/detail.pl?biblionumber={biblio}",
			fingerprint,
			ext,
		)
		return "sent", f"created biblio {biblio}"

	if t.target_type == "Wikidata":
		data = wikidata_entity(record, portal)
		fingerprint = payload_hash(data)
		if ext and ext.last_hash == fingerprint and not force:
			return "unchanged", f"{ext.external_id} already up to date"
		qid = (ext.external_id if ext else None) or (
			client.find_by_ia(item) if record.get("on_archive_org") else None
		)
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
	frappe.db.sql(
		f"update `{RUN}` set log = right(concat(ifnull(log,''), %s), 200000) where name=%s",
		(f"{now_datetime().strftime('%H:%M:%S')} {line}\n", run),
	)


@frappe.whitelist()
@features.needs("sharing")
def start(target: str, force: int = 0, dry_run: int | None = None, items=None) -> str:
	"""Push Now / Dry Run from the form or the API."""
	frappe.only_for(MANAGERS)
	return _start(target, force, dry_run, items, "Manual")


def _start(
	target: str, force: int = 0, dry_run: int | None = None, items=None, triggered_by: str = "Manual"
) -> str:
	t = frappe.get_doc("RD Push Target", target)
	dry = cint(t.dry_run) if dry_run in (None, "") else cint(dry_run)
	run = frappe.get_doc(
		{
			"doctype": "RD Push Run",
			"target": target,
			"status": "Queued",
			"dry_run": dry,
			"triggered_by": triggered_by,
		}
	).insert(ignore_permissions=True)
	frappe.db.set_value("RD Push Target", target, "last_run", run.name, update_modified=False)
	frappe.enqueue(
		"sok_resdesk.outbound.run",
		queue="long",
		timeout=12 * 3600,
		run_name=run.name,
		force=cint(force),
		items=frappe.parse_json(items) if isinstance(items, str) else items,
		enqueue_after_commit=True,
		job_id=f"resdesk-push-{run.name}",
	)
	return run.name


def _counts(run_name: str, counts: dict, extra: str = "", values: tuple = ()):
	frappe.db.sql(
		f"update `{RUN}` set sent=%s, unchanged=%s, skipped=%s, failed=%s{extra} where name=%s",
		(counts["sent"], counts["unchanged"], counts["skipped"], counts["failed"], *values, run_name),
	)


@hold_when_paused("long")
def run(run_name: str, force: int = 0, items: list | None = None, resume: int = 0) -> None:
	r = frappe.get_doc("RD Push Run", run_name)
	if r.status in ("Cancelled", "Paused"):
		return  # stopped or paused before this job started
	t = frappe.get_doc("RD Push Target", r.target)
	names = items or _books(t)
	if resume:
		counts = {k: cint(r.get(k)) for k in ("sent", "unchanged", "skipped", "failed")}
		frappe.db.sql(f"update `{RUN}` set status='Running' where name=%s", run_name)
		_log(run_name, f"carrying on: {len(names)} books left")
	else:
		counts = {"sent": 0, "unchanged": 0, "skipped": 0, "failed": 0}
		frappe.db.sql(f"update `{RUN}` set status='Running', total=%s where name=%s", (len(names), run_name))
		_log(run_name, f"{'DRY RUN: ' if r.dry_run else ''}{len(names)} books → {t.target_type} ({t.name})")
	frappe.db.commit()
	failed_in_a_row = 0
	try:
		client = _client(t)
		if t.target_type == "Wikidata" and not r.dry_run:
			_log(run_name, f"logged in as {client.login()}")
	except Exception as e:
		_log(run_name, f"FAILED to connect: {e}")
		frappe.db.sql(
			f"update `{RUN}` set status='Failed', finished_on=%s where name=%s", (now_datetime(), run_name)
		)
		frappe.db.commit()
		return
	for n, item in enumerate(names, 1):
		status = frappe.db.get_value("RD Push Run", run_name, "status")
		if status == "Cancelled":
			_log(run_name, "cancelled")
			break
		if status == "Paused" and _paused_here(run_name, names[n - 1 :], counts, cint(force)):
			return
		try:
			outcome, msg = push_one(t, client, item, bool(r.dry_run), bool(force))
			# commit the book's record first: the log line below touches the run row, which a
			# Pause or Cancel may have changed meanwhile (MariaDB would refuse the older snapshot)
			frappe.db.commit()
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
	final = (
		"Cancelled"
		if status == "Cancelled"
		else ("Completed with Errors" if counts["failed"] else "Completed")
	)
	_counts(run_name, counts, ", status=%s, finished_on=%s", (final, now_datetime()))
	_log(
		run_name,
		f"Done: {counts['sent']} {'would be sent' if r.dry_run else 'sent'}, {counts['unchanged']} unchanged, "
		f"{counts['skipped']} skipped, {counts['failed']} failed",
	)
	frappe.db.commit()


def _paused_here(run_name: str, remaining: list, counts: dict, force: int) -> bool:
	"""Paused mid-run: keep the books not yet sent on the run (checked under the row lock so a
	Resume at the same moment isn't missed)."""
	frappe.db.commit()
	if frappe.db.sql(f"select status from `{RUN}` where name=%s for update", run_name)[0][0] != "Paused":
		frappe.db.commit()
		return False
	_counts(run_name, counts, ", held_items=%s", (json.dumps({"items": remaining, "force": force}),))
	frappe.db.commit()
	_log(run_name, f"paused: {len(remaining)} books left for later")
	frappe.db.commit()
	return True


def pause_push(run_name: str, who: str) -> bool:
	"""Pause a push run (Background Jobs, the run form). Used by jobs.pause_run / pause_all."""
	status = frappe.db.sql(f"select status from `{RUN}` where name=%s for update", run_name)
	if not status or status[0][0] not in ("Queued", "Running"):
		frappe.db.rollback()
		return False
	frappe.db.sql(f"update `{RUN}` set status='Paused' where name=%s", run_name)
	frappe.db.commit()
	_log(run_name, f"pause requested by {who}")
	frappe.db.commit()
	# a run still waiting in the queue is taken out and started again on Resume
	from frappe.utils.background_jobs import get_redis_conn
	from rq.exceptions import NoSuchJobError
	from rq.job import Job

	try:
		job = Job.fetch(f"{frappe.local.site}||resdesk-push-{run_name}", connection=get_redis_conn())
		if job.get_status() == "queued":
			args = (job.kwargs or {}).get("kwargs") or {}
			job.cancel()
			frappe.db.sql(f"select name from `{RUN}` where name=%s for update", run_name)
			frappe.db.sql(
				f"update `{RUN}` set held_items=%s where name=%s",
				(
					json.dumps({"items": args.get("items"), "force": cint(args.get("force")), "fresh": 1}),
					run_name,
				),
			)
			frappe.db.commit()
	except NoSuchJobError:
		pass  # already started: the run notices the pause itself
	except Exception:
		frappe.log_error(title=f"Research Desk: could not hold push run {run_name}")
	return True


def resume_push(run_name: str, who: str) -> int:
	"""Carry on with a paused push run. Returns the number of books queued, or -1."""
	row = frappe.db.sql(f"select status, held_items from `{RUN}` where name=%s for update", run_name)
	if not row or row[0][0] != "Paused":
		frappe.db.rollback()
		return -1
	held = json.loads(row[0][1]) if row[0][1] else {}
	fresh = cint(held.get("fresh")) or "items" not in held
	frappe.db.sql(
		f"update `{RUN}` set status=%s, held_items=null where name=%s",
		("Queued" if fresh else "Running", run_name),
	)
	frappe.db.commit()
	_log(run_name, f"resumed by {who}")
	frappe.db.commit()
	frappe.enqueue(
		"sok_resdesk.outbound.run",
		queue="long",
		timeout=12 * 3600,
		run_name=run_name,
		force=cint(held.get("force")),
		items=held.get("items"),
		resume=0 if fresh else 1,
		job_id=f"resdesk-push-{run_name}",
	)
	return len(held.get("items") or [])


@frappe.whitelist()
def cancel(run_name: str) -> None:
	"""Stop a push run: a queued one never starts, a running one stops after its current book."""
	frappe.only_for(MANAGERS)
	frappe.db.sql(
		f"update `{RUN}` set status='Cancelled', held_items=null, finished_on=ifnull(finished_on, %s) "
		"where name=%s and status in ('Queued','Running','Paused')",
		(now_datetime(), run_name),
	)
	_log(run_name, f"cancel requested by {frappe.session.user}")
	frappe.db.commit()
	from frappe.utils.background_jobs import get_redis_conn
	from rq.exceptions import NoSuchJobError
	from rq.job import Job

	try:
		job = Job.fetch(f"{frappe.local.site}||resdesk-push-{run_name}", connection=get_redis_conn())
		if job.get_status() == "queued":
			job.cancel()
			frappe.db.set_value("RD Push Run", run_name, "finished_on", now_datetime(), update_modified=False)
	except NoSuchJobError:
		pass  # already started or finished
	except Exception:
		frappe.log_error(title=f"Research Desk: could not cancel queued push run {run_name}")


# -- automatic pushes -------------------------------------------------------------------------------


@features.scheduled("sharing")
def on_item_change(doc, method=None):
	"""RD Item saved (form, bulk edit, import): queue a push to targets that want it."""
	if doc.flags.from_ingest or frappe.flags.in_install or frappe.flags.in_migrate:
		return
	for name in frappe.get_all("RD Push Target", filters={"enabled": 1, "auto_push": 1}, pluck="name"):
		t = frappe.get_cached_doc("RD Push Target", name)
		if in_scope(t, doc.name):
			frappe.enqueue(
				"sok_resdesk.outbound.auto_push",
				queue="default",
				target=name,
				item=doc.name,
				job_id=f"resdesk-autopush-{name}-{doc.name}",
				deduplicate=True,
				enqueue_after_commit=True,
			)


@hold_when_paused("default")
def auto_push(target: str, item: str):
	if frappe.db.get_value("RD Push Target", target, "enabled"):
		_start(target, items=[item], triggered_by="Automatic")
