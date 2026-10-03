"""Managing the search engine's queue (Background Jobs → Search queue).

Meilisearch works through its tasks strictly in order, so hours of page text queued earlier
hold up the book records behind it: the catalogue grows but the portal doesn't. Here:

* **Overview**: tasks waiting for books and for page text, the batch being worked on, how fast
  the queue is draining and how long it has to go, and the size of the task history.
* **Books first**: page text is held for a moment, the page-text tasks still waiting are
  cancelled, and the books they carried are marked *pages pending*. The book records behind
  them are then next in line, so new books reach the portal within minutes. The cancelled page
  text is sent again in the background (from the text kept on this server) at a pace the
  engine keeps up with. Nothing is lost.
* **Hold / resume page text**: while held, books are still catalogued and listed on the portal;
  their page text waits (marked *pages pending*) and is sent when it is resumed.
* **Clear finished tasks**: Meilisearch keeps a record of every task it has done; on a big
  catalogue that history grows to gigabytes. It is cleared weekly, and on request.
"""

from __future__ import annotations

import datetime as _dt
import time

import frappe
from frappe import _
from frappe.utils import cint

from sok_resdesk.holding import hold_when_paused
from sok_resdesk.search import MAX_WAITING, MeiliClient, SearchError

MANAGERS = ("System Manager", "ResDesk Manager")
RATE_MINUTES = 30  # how far back the draining speed is measured
SEND_BATCH = 25  # books whose page text goes in one send
KEEP_HISTORY_DAYS = 7


def _iso(dt: _dt.datetime) -> str:
	return dt.astimezone(_dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _system_time(iso: str | None):
	"""Meilisearch's UTC timestamp as the site's local time (how Frappe stores datetimes), less a
	minute's margin; None when it can't be read."""
	if not iso:
		return None
	try:
		from frappe.utils import convert_utc_to_system_timezone

		utc = _dt.datetime.fromisoformat(iso[:19])  # YYYY-MM-DDTHH:MM:SS, always UTC
		local = convert_utc_to_system_timezone(utc).replace(tzinfo=None)
		return local - _dt.timedelta(minutes=1)
	except Exception:
		return None


def _count(client: MeiliClient, **params) -> int:
	return cint(client._req("GET", "/tasks", params={"limit": 1, **params}).get("total"))


def overview(client: MeiliClient | None = None) -> dict:
	"""Everything the Search queue panel shows."""
	client = client or MeiliClient.from_settings()
	since = _iso(_dt.datetime.now(_dt.UTC) - _dt.timedelta(minutes=RATE_MINUTES))
	waiting_books = _count(client, statuses="enqueued", indexUids=client.books)
	waiting_pages = _count(client, statuses="enqueued", indexUids=client.pages)
	waiting_all = _count(client, statuses="enqueued")
	done_lately = _count(client, statuses="succeeded", afterFinishedAt=since)
	failed_lately = _count(client, statuses="failed", afterFinishedAt=since)
	per_minute = done_lately / RATE_MINUTES
	eta = round(waiting_all / per_minute) if per_minute else None
	return {
		"waiting_books": waiting_books,
		"waiting_pages": waiting_pages,
		"waiting_other": max(0, waiting_all - waiting_books - waiting_pages),
		"waiting": waiting_all,
		"done_per_minute": round(per_minute, 1),
		"failed_lately": failed_lately,
		"eta_minutes": eta,
		"history": _count(client),  # every task Meilisearch still remembers
		"held": bool(cint(frappe.db.get_single_value("RD Settings", "hold_page_text"))),
		"auto": bool(cint(frappe.db.get_single_value("RD Settings", "auto_books_first"))),
		"auto_last": frappe.cache.get_value("resdesk:auto-books-first-last"),
		"pages_pending": frappe.db.count("RD Item", {"pages_pending": 1}),
	}


@frappe.whitelist()
def get_overview() -> dict:
	frappe.only_for(MANAGERS + ("ResDesk Cataloguer",))
	cached = frappe.cache.get_value("resdesk:search-queue")
	if cached:
		return cached
	try:
		out = overview()
	except SearchError as e:
		out = {"error": str(e)[:300]}
	frappe.cache.set_value("resdesk:search-queue", out, expires_in_sec=5)
	return out


def _hold(on: bool) -> None:
	frappe.db.set_single_value("RD Settings", "hold_page_text", 1 if on else 0)
	frappe.db.commit()
	frappe.cache.delete_value("resdesk:search-queue")


def _wait(client: MeiliClient, task: dict, timeout: float = 120) -> dict:
	try:
		return client.wait(task, timeout=timeout)
	except SearchError:
		return {}


def _oldest_waiting(client: MeiliClient, index: str) -> dict | None:
	found = client._req(
		"GET", "/tasks", params={"statuses": "enqueued", "indexUids": index, "limit": 1, "reverse": "true"}
	).get("results")
	return found[0] if found else None


def _cancel_pages(client: MeiliClient) -> tuple[int, int]:
	"""Cancel the waiting page-text tasks; mark their books' page text pending. (tasks, books)"""
	first = _oldest_waiting(client, client.pages)
	if not first:
		return 0, 0
	lowest, since = cint(first["uid"]), _system_time(first.get("enqueuedAt"))
	info = _wait(
		client,
		client._req("POST", "/tasks/cancel", params={"statuses": "enqueued", "indexUids": client.pages}),
	)
	# every waiting page task from the lowest one on is now cancelled (the queue runs in order): a
	# book whose last page task is among them has its page text sent again. Books sent before
	# their task was recorded (page_task 0: Frappe keeps whole numbers at 0, never empty) are
	# matched by when they were sent instead.
	frappe.db.sql(
		"""update `tabRD Item` set pages_pending = 1
		where ifnull(indexed_pages, 0) > 0
		and (page_task >= %(lowest)s or (ifnull(page_task, 0) = 0 and %(since)s is not null and indexed_on >= %(since)s))""",
		{"lowest": lowest, "since": since},
	)
	books = cint(frappe.db.sql("select row_count()")[0][0])
	frappe.db.commit()
	return cint((info.get("details") or {}).get("canceledTasks")), books


def _cancel_books(client: MeiliClient) -> tuple[int, int]:
	"""Cancel the waiting book-record tasks; their books count as not sent yet (Send them, on
	Background Jobs → Machine, sends them again). (tasks, books)"""
	first = _oldest_waiting(client, client.books)
	if not first:
		return 0, 0
	since = _system_time(first.get("enqueuedAt"))
	info = _wait(
		client,
		client._req("POST", "/tasks/cancel", params={"statuses": "enqueued", "indexUids": client.books}),
	)
	books = 0
	if since:
		frappe.db.sql("update `tabRD Item` set indexed_on = null where indexed_on >= %s", since)
		books = cint(frappe.db.sql("select row_count()")[0][0])
		frappe.db.commit()
	return cint((info.get("details") or {}).get("canceledTasks")), books


def cancel_waiting(include_books: bool = False) -> dict:
	"""Cancel what waits in the search engine without losing track of it: page text is marked
	pending (and sent again), book records count as not sent (Send them). Tasks already being
	worked on finish."""
	client = MeiliClient.from_settings()
	was_held = bool(cint(frappe.db.get_single_value("RD Settings", "hold_page_text")))
	_hold(True)  # no new page text while the waiting tasks are cancelled
	try:
		time.sleep(2)  # a send that read the setting a moment ago finishes adding
		page_tasks, page_books = _cancel_pages(client)
		book_tasks, books = _cancel_books(client) if include_books else (0, 0)
	finally:
		_hold(was_held)
	if page_books and not was_held:
		_queue_send()
	return {
		"cancelled": page_tasks + book_tasks,
		"books": page_books,
		"unsent": books,
		"message": _(
			"{0} waiting page-text tasks cancelled: new books go next. The page text of {1} books is sent again in the background."
		).format(page_tasks, page_books)
		+ (
			" " + _("{0} book records cancelled too: Send them on Background Jobs → Machine.").format(books)
			if include_books
			else ""
		),
	}


@frappe.whitelist()
def books_first() -> dict:
	"""Cancel the page-text tasks still waiting so the book records behind them go next; their
	books' page text is marked pending and sent again in the background."""
	frappe.only_for(MANAGERS)
	return cancel_waiting(include_books=False)


@frappe.whitelist()
def hold_page_text(hold: int = 1) -> dict:
	"""Hold page text (books still go to the portal) or resume it (what waited is sent)."""
	frappe.only_for(MANAGERS)
	_hold(bool(cint(hold)))
	if not cint(hold):
		_queue_send()
	return overview()


def _queue_send() -> None:
	frappe.enqueue(
		"sok_resdesk.search_queue.send_pending",
		queue="long",
		timeout=6 * 3600,
		job_id="resdesk-send-pending-pages",
		deduplicate=True,
	)


@hold_when_paused("long")
def send_pending(limit: int = 2000) -> int:
	"""Send the page text of books marked *pages pending*, oldest first, a few books at a time and
	only while the engine has room (search.wait_for_room). Every 10 minutes too (hooks)."""
	from sok_resdesk.catalogue import item_to_record
	from sok_resdesk.ingest import fetch_pages
	from sok_resdesk.search import IndexBuffer, pages_held

	sent = 0
	while sent < limit and not pages_held():
		if frappe.cache.get_value("resdesk:stop-background"):
			break
		names = frappe.get_all(
			"RD Item",
			filters={"pages_pending": 1},
			pluck="name",
			order_by="creation asc",
			limit=SEND_BATCH,
		)
		if not names:
			break
		buffer = IndexBuffer(flush_books=SEND_BATCH)
		for name in names:
			doc = frappe.get_doc("RD Item", name)
			try:
				pages = fetch_pages(doc.item_id) if doc.has_page_text else []
			except Exception as e:  # one unreadable book doesn't stop the rest
				frappe.log_error("Research Desk: page text not sent", f"{name}: {e}")
				pages = []
			if not pages:
				frappe.db.set_value("RD Item", name, "pages_pending", 0, update_modified=False)
				continue
			buffer.add(item_to_record(doc), pages, replace_pages=True)
		buffer.flush()  # waits for room first; clears pages_pending for what it sent
		frappe.db.commit()
		sent += len(names)
	return sent


AUTO_AFTER_MINUTES = 15  # a book record waiting this long behind page text: Books first by itself
AUTO_EVERY_MINUTES = 30  # and not more often than this


def every_ten_minutes() -> None:
	"""Scheduler: Books first by itself when book records are stuck behind page text, then keep
	pending page text moving when the engine has room."""
	if cint(frappe.db.get_single_value("RD Settings", "hold_page_text")):
		return
	try:
		client = MeiliClient.from_settings()
		auto_books_first(client)
		if frappe.db.count("RD Item", {"pages_pending": 1}):
			if _count(client, statuses="enqueued") > MAX_WAITING // 2:
				return  # busy: the next turn
			_queue_send()
	except SearchError:
		return


def auto_books_first(client: MeiliClient) -> dict | None:
	"""Settings → Books First Automatically: when the oldest waiting book record has waited more
	than AUTO_AFTER_MINUTES with page text queued ahead of it, do what the Books first button does.
	At most once every AUTO_EVERY_MINUTES. Returns what it did, or None."""
	if not cint(frappe.db.get_single_value("RD Settings", "auto_books_first", cache=False)):
		return None
	if frappe.cache.get_value("resdesk:auto-books-first"):
		return None
	book = _oldest_waiting(client, client.books)
	page = _oldest_waiting(client, client.pages)
	if not book or not page or cint(page["uid"]) > cint(book["uid"]):
		return None  # no book waiting, or no page text ahead of it
	since = _system_time(book.get("enqueuedAt"))
	if not since or (frappe.utils.now_datetime() - since).total_seconds() < AUTO_AFTER_MINUTES * 60:
		return None
	frappe.cache.set_value("resdesk:auto-books-first", 1, expires_in_sec=AUTO_EVERY_MINUTES * 60)
	result = cancel_waiting(include_books=False)
	frappe.cache.set_value(
		"resdesk:auto-books-first-last",
		{"at": str(frappe.utils.now_datetime())[:19], **{k: result[k] for k in ("cancelled", "books")}},
		expires_in_sec=7 * 24 * 3600,
	)
	return result


@frappe.whitelist()
def clear_history(days: int = KEEP_HISTORY_DAYS) -> dict:
	"""Forget finished tasks (done, failed or cancelled) older than `days`."""
	frappe.only_for(MANAGERS)
	return _clear(cint(days))


def _clear(days: int) -> dict:
	client = MeiliClient.from_settings()
	before = _iso(_dt.datetime.now(_dt.UTC) - _dt.timedelta(days=max(0, days)))
	task = client._req(
		"DELETE",
		"/tasks",
		params={"statuses": "succeeded,failed,canceled", "beforeFinishedAt": before},
	)
	info = _wait(client, task, timeout=300)
	deleted = cint((info.get("details") or {}).get("deletedTasks"))
	return {"deleted": deleted, "message": _("{0} finished tasks cleared.").format(deleted)}


def weekly() -> None:
	"""Scheduler: keep the task history to the last week."""
	try:
		_clear(KEEP_HISTORY_DAYS)
	except SearchError:
		pass
