"""bench commands:  bench --site <site> resdesk <subcommand>

  resdesk count    --collection ServantsOfKnowledge --filter "language:kan"
  resdesk ingest   --collection ServantsOfKnowledge --filter "language:kan" --limit 50
  resdesk ingest   --profile "SoK Kannada sample"
  resdesk ingest   --ids "id1,id2"   |  --ids-file ids.txt
  resdesk reindex  [--no-pages]
  resdesk configure --meili-url http://meilisearch:7700 --meili-key KEY --title "My Library"
  resdesk status
  resdesk access   login-to-read --collection ServantsOfKnowledge     (or --profile, --language, --ids, --all)
  resdesk access   --apply-rules  |  --guests "Records only"  |  --signup "Sign up, admin approves"
  resdesk add-reader reader@example.org --name "A Reader"
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
@click.option("--visibility", help="Who can see the new books: public, login-to-read or members (default: rules in Settings)")
@click.option("--background", is_flag=True,
			  help="Hand the work to the queue workers (parallel; best for large runs) and watch progress")
@pass_context
def ingest(context, profile, collection, filter_, query, ids, ids_file, folder, server, manifest, limit, no_fulltext,
		   update, name, visibility, background):
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
			values.update({"max_items": 50 if limit is None else limit, "fetch_fulltext": 0 if no_fulltext else 1, "update_existing": 1 if update else 0,
						   "visibility": _VIS_ALIASES.get((visibility or "").strip().lower(), visibility or "")})
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

		frappe.set_user("Administrator")  # count every published book, not only what guests see
		for k, v in stats().items():
			click.echo(f"{k:15} {v}")
	finally:
		frappe.destroy()


_VIS_ALIASES = {
	"public": "Public", "open": "Public",
	"login-to-read": "Login to read", "login to read": "Login to read", "read": "Login to read",
	"login-to-find": "Login to find", "login to find": "Login to find", "find": "Login to find",
	"members": "Login to find", "members-only": "Login to find", "hidden": "Login to find",
}


@resdesk.command("access")
@click.argument("visibility", required=False)
@click.option("--collection", help="Books in this collection, e.g. ServantsOfKnowledge")
@click.option("--profile", help="Books ingested by this RD Ingest Profile")
@click.option("--language", help='Books in this language, e.g. Kannada or kan')
@click.option("--ids", help="Comma-separated item identifiers")
@click.option("--ids-file", type=click.Path(exists=True), help="File with one identifier per line")
@click.option("--all", "everything", is_flag=True, help="Every book in the catalogue")
@click.option("--apply-rules", is_flag=True, help="Re-apply profiles, rules and the default (Settings → Access)")
@click.option("--include-manual", is_flag=True, help="With --apply-rules: also change books set by hand or in bulk")
@click.option("--guests", type=click.Choice(["Each item's setting", "Records only", "Login required"]),
			  help="What visitors who are not logged in may do")
@click.option("--signup", type=click.Choice(["Admins add readers", "Anyone can sign up", "Sign up, admin approves"]),
			  help="How people get reader accounts")
@click.option("--default", "default_vis", help="Visibility for new books when no profile or rule decides")
@pass_context
def access_cmd(context, visibility, collection, profile, language, ids, ids_file, everything, apply_rules,
			   include_manual, guests, signup, default_vis):
	"""Who can see what: public, login-to-read or login-to-find (members only).

	\b
	Examples:
	  resdesk access login-to-read --collection ServantsOfKnowledge
	  resdesk access members --profile "Internal scans"
	  resdesk access public --ids "id1,id2"
	  resdesk access --guests "Login required" --signup "Sign up, admin approves"
	  resdesk access --apply-rules
	With no arguments: show the current settings and how many books have each visibility.
	"""
	frappe = _connect(context)
	try:
		frappe.set_user("Administrator")
		from sok_resdesk import access

		if guests or signup or default_vis:
			s = frappe.get_single("RD Settings")
			if guests:
				s.guest_access = guests
			if signup:
				s.reader_signup = signup
			if default_vis:
				s.default_visibility = _VIS_ALIASES.get(default_vis.lower(), default_vis)
			s.save(ignore_permissions=True)
			frappe.db.commit()
		if apply_rules:
			click.echo(f"Changed {access.recompute(include_manual)['changed']} books.")
		if visibility:
			vis = _VIS_ALIASES.get(visibility.strip().lower(), visibility)
			if ids_file:
				with open(ids_file) as f:
					ids = ",".join(line.strip() for line in f if line.strip())
			names = access.select_items(names=ids or None, collection=collection, profile=profile,
										language=language, everything=everything)
			if not names:
				click.echo("No books matched.")
			else:
				click.echo(f"Setting {len(names)} books to '{vis}'…")
				access.apply_visibility(names, vis, "Bulk")
				click.echo("Done.")
		s = frappe.get_single("RD Settings")
		click.echo(f"Visitors not logged in:  {s.guest_access}")
		click.echo(f"Reader accounts:         {s.reader_signup}")
		click.echo(f"Default for new books:   {s.default_visibility}")
		click.echo(f"OAI-PMH shares:          {s.oai_scope}")
		for vis, n in frappe.db.sql("select ifnull(visibility,'Public'), count(*) from `tabRD Item` group by 1 order by 1"):
			click.echo(f"  {vis:15} {n:>8} books")
	finally:
		frappe.destroy()


@resdesk.command("add-reader")
@click.argument("email")
@click.option("--name", "full_name", default="", help="Full name")
@click.option("--no-email", is_flag=True, help="Don't send the welcome email (set a password in the Desk instead)")
@pass_context
def add_reader_cmd(context, email, full_name, no_email):
	"""Create a reader account (or give an existing account the Reader role)."""
	frappe = _connect(context)
	try:
		frappe.set_user("Administrator")
		from sok_resdesk.access import add_reader

		user = add_reader(email, full_name, send_welcome=not no_email)
		frappe.db.commit()
		click.echo(f"{user} can now log in and read members-only books.")
	finally:
		frappe.destroy()


commands = [resdesk]
