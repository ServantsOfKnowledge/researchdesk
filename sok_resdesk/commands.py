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


def _scope(collection, filter_, query, ids, ids_file):
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
]


def scope_options(f):
	for opt in reversed(_scope_options):
		f = opt(f)
	return f


@resdesk.command("count")
@scope_options
@pass_context
def count(context, collection, filter_, query, ids, ids_file):
	"""How many IA items match (before you ingest)."""
	frappe = _connect(context)
	try:
		from sok_resdesk.core.ia import IAClient
		from sok_resdesk.ingest import client

		s = _scope(collection, filter_, query, ids, ids_file)
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
@pass_context
def ingest(context, profile, collection, filter_, query, ids, ids_file, limit, no_fulltext, update, name):
	"""Ingest items from the Internet Archive (runs in the foreground, prints progress)."""
	frappe = _connect(context)
	try:
		from sok_resdesk.ingest import create_run, ensure_profile, run_ingest

		profile_given = bool(profile)
		if not profile:
			values = _scope(collection, filter_, query, ids, ids_file)
			values.update({"max_items": 50 if limit is None else limit, "fetch_fulltext": 0 if no_fulltext else 1, "update_existing": 1 if update else 0})
			profile = ensure_profile(name or "Command line ingest", **values)
		run = create_run(frappe.get_doc("RD Ingest Profile", profile), "Command Line")
		click.echo(f"Run {run.name} for profile '{profile}'")
		run_ingest(run.name, verbose=True, limit_override=limit if profile_given else None)
		run.reload()
		click.echo(f"Status: {run.status}")
	finally:
		frappe.destroy()


@resdesk.command("reindex")
@click.option("--no-pages", is_flag=True, help="Only book-level records (fast)")
@pass_context
def reindex(context, no_pages):
	"""Rebuild the search index from the catalogue."""
	frappe = _connect(context)
	try:
		from sok_resdesk.search import rebuild_all

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
