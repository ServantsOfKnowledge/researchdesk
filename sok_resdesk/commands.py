"""bench commands:  bench --site <site> resdesk <subcommand>

  resdesk count    --collection ServantsOfKnowledge --filter "language:kan"
  resdesk ingest   --collection ServantsOfKnowledge --filter "language:kan" --limit 50
  resdesk ingest   --profile "SoK Kannada sample"
  resdesk ingest   --ids "id1,id2"   |  --ids-file ids.txt
  resdesk reindex  [--no-pages]
  resdesk configure --meili-url http://meilisearch:7700 --meili-key KEY --title "My Library"
  resdesk status
"""

import click
from frappe.commands import get_site, pass_context


def _connect(context):
	import frappe

	site = get_site(context)
	frappe.init(site=site)
	frappe.connect()
	return frappe


@click.group("resdesk")
def resdesk():
	"""Research Desk: ingest, index and manage the catalogue."""


def _scope(collection, filter_, query, ids, ids_file, folder=None, server=None, manifest=None):
	if folder or server:
		return {"source": "Folder or Server", "location": folder or server, "manifest_url": manifest or "",
				"check_archive_org": 1}
	if ids_file:
		with open(ids_file) as f:
			ids = ",".join(line.strip() for line in f if line.strip())
	if ids:
		return {"scope_type": "Identifier List", "identifiers": "\n".join(i.strip() for i in ids.split(",") if i.strip())}
	if query:
		return {"scope_type": "Search Query", "ia_query": query}
	return {"scope_type": "Collection", "ia_collection": collection or "ServantsOfKnowledge", "extra_filter": filter_ or ""}


_scope_options = [
	click.option("--collection", help="IA collection id, e.g. ServantsOfKnowledge"),
	click.option("--filter", "filter_", help='Extra IA query to narrow a collection, e.g. "language:kan"'),
	click.option("--query", help="A full IA advanced-search query instead of a collection"),
	click.option("--ids", help="Comma-separated IA identifiers"),
	click.option("--ids-file", type=click.Path(exists=True), help="File with one IA identifier per line"),
	click.option("--folder", help="Folder of IA-style item folders, e.g. /library-source or /library-source/2026"),
	click.option("--server", help="Web server with IA-style item folders, e.g. https://books.example.org/items/"),
	click.option("--manifest", help="With --server: URL of a list of item folders (one per line)"),
]


def scope_options(f):
	for opt in reversed(_scope_options):
		f = opt(f)
	return f


@resdesk.command("count")
@scope_options
@pass_context
def count(context, collection, filter_, query, ids, ids_file, folder, server, manifest):
	"""How many IA items match (before you ingest)."""
	frappe = _connect(context)
	try:
		from sok_resdesk.core.ia import IAClient
		from sok_resdesk.ingest import client

		s = _scope(collection, filter_, query, ids, ids_file, folder, server, manifest)
		if s.get("source") == "Folder or Server":
			from sok_resdesk.local_source import open_profile_store

			n = sum(1 for _ in open_profile_store(frappe._dict(s)).iter_items())
			click.echo(f"Item folders under {s['location']}: {n:,}")
			return
		q = IAClient.build_query(
			s["scope_type"], s.get("ia_collection", ""), s.get("extra_filter", ""), s.get("ia_query", ""),
			(s.get("identifiers") or "").splitlines(),
		)
		click.echo(f"Query: {q}")
		click.echo(f"Matching items: {client().count(q):,}")
	finally:
		frappe.destroy()


@resdesk.command("ingest")
@click.option("--profile", help="Run an existing RD Ingest Profile by name")
@scope_options
@click.option("--limit", type=int, default=None, help="Max items (0 = all). Default 50, or the profile's own limit")
@click.option("--no-fulltext", is_flag=True, help="Metadata only; skip OCR text")
@click.option("--update", is_flag=True, help="Refresh items already in the catalogue")
@click.option("--name", help="Save the scope as a profile with this name")
@click.option("--background", is_flag=True,
			  help="Hand the work to the queue workers (parallel; best for large runs) and watch progress")
@pass_context
def ingest(context, profile, collection, filter_, query, ids, ids_file, folder, server, manifest, limit, no_fulltext,
		   update, name, background):
	"""Ingest items from the Internet Archive.

	By default runs here in the foreground, one book at a time. With --background the
	books are split into batches processed in parallel by the queue workers.
	"""
	frappe = _connect(context)
	try:
		from sok_resdesk.ingest import create_run, ensure_profile, run_ingest

		profile_given = bool(profile)
		if not profile:
			values = _scope(collection, filter_, query, ids, ids_file, folder, server, manifest)
			values.update({"max_items": 50 if limit is None else limit, "fetch_fulltext": 0 if no_fulltext else 1, "update_existing": 1 if update else 0})
			default_name = "Command line folder ingest" if values.get("source") else "Command line ingest"
			profile = ensure_profile(name or default_name, **values)
		run = create_run(frappe.get_doc("RD Ingest Profile", profile), "Command Line")
		click.echo(f"Run {run.name} for profile '{profile}'")
		limit_override = limit if profile_given else None
		if background:
			run_ingest(run.name, verbose=True, limit_override=limit_override, foreground=False)
			if frappe.db.get_value("RD Ingest Run", run.name, "status") in ("Queued", "Running"):
				click.echo("Batches queued for the workers. Following progress (Ctrl+C stops watching, not the run):")
				_watch(frappe, run.name)
		else:
			run_ingest(run.name, verbose=True, limit_override=limit_override)
		run.reload()
		click.echo(f"Status: {run.status}")
	finally:
		frappe.destroy()


def _watch(frappe, run_name: str, interval: int = 10):
	import time

	start, first = time.monotonic(), None
	while True:
		frappe.db.commit()  # end the read snapshot so we see the workers' updates
		r = frappe.db.get_value(
			"RD Ingest Run", run_name,
			["status", "total_found", "processed", "created_count", "failed_count", "pending_chunks"], as_dict=True,
		)
		elapsed = time.monotonic() - start
		if first is None:
			first = r.processed or 0
		rate = ((r.processed or 0) - first) / elapsed * 3600 if elapsed > 30 else 0
		click.echo(
			f"  {r.status:<22} {r.processed or 0:>7,}/{r.total_found or 0:,}  new {r.created_count or 0:,}  "
			f"failed {r.failed_count or 0:,}  batches left {r.pending_chunks or 0}"
			+ (f"  ~{rate:,.0f} books/h" if rate else "")
		)
		if r.status not in ("Queued", "Running"):
			return
		time.sleep(interval)


@resdesk.command("progress")
@click.argument("run", required=False)
@pass_context
def progress(context, run):
	"""Watch an ingest run (default: the latest)."""
	frappe = _connect(context)
	try:
		run = run or frappe.db.get_value("RD Ingest Run", {}, "name", order_by="creation desc")
		if not run:
			click.echo("No ingest runs yet.")
			return
		click.echo(f"Run {run}")
		_watch(frappe, run)
	finally:
		frappe.destroy()


@resdesk.command("reindex")
@click.option("--no-pages", is_flag=True, help="Only book-level records (fast)")
@click.option("--background", is_flag=True, help="Split across the queue workers (parallel)")
@click.option("--reset", is_flag=True, help="Drop and recreate the page index first")
@pass_context
def reindex(context, no_pages, background, reset):
	"""Rebuild the search index from the catalogue (page text comes from the local cache when present)."""
	frappe = _connect(context)
	try:
		from sok_resdesk.search import queue_rebuild, rebuild_all, reset_pages_index

		if reset:
			reset_pages_index()
			click.echo("Page index recreated")
		if background:
			n = queue_rebuild(with_pages=0 if no_pages else 1)
			frappe.db.commit()
			click.echo(f"Queued re-indexing of {n} items for the workers")
		else:
			n = rebuild_all(with_pages=0 if no_pages else 1, verbose=True)
			click.echo(f"Re-indexed {n} items")
	finally:
		frappe.destroy()


@resdesk.command("configure")
@click.option("--meili-url")
@click.option("--meili-key")
@click.option("--title", help="Portal title")
@click.option("--base-url", help="Public URL, e.g. https://library.example.org")
@click.option("--contact", help="Email/URL sent to the Internet Archive in the User-Agent")
@pass_context
def configure(context, meili_url, meili_key, title, base_url, contact):
	"""Set Research Desk settings from the command line."""
	frappe = _connect(context)
	try:
		s = frappe.get_single("RD Settings")
		for field, value in (("meili_url", meili_url), ("meili_api_key", meili_key), ("portal_title", title),
							 ("base_url", base_url), ("ia_contact", contact)):
			if value:
				s.set(field, value)
		if contact and "@" in contact:
			s.admin_email = contact
		s.save(ignore_permissions=True)
		frappe.db.commit()
		from sok_resdesk.search import setup_indexes

		frappe.set_user("Administrator")
		click.echo(setup_indexes())
	finally:
		frappe.destroy()


@resdesk.command("status")
@pass_context
def status(context):
	"""Catalogue and search-engine health."""
	frappe = _connect(context)
	try:
		from sok_resdesk.api import stats

		for k, v in stats().items():
			click.echo(f"{k:15} {v}")
	finally:
		frappe.destroy()


commands = [resdesk]
