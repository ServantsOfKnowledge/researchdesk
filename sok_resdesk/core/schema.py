"""Does the database need `bench migrate`?

`bench migrate` brings the database in line with the code: it runs new patches, updates the
tables of changed DocTypes, then runs every app's after_migrate hooks. When neither the code
that defines the database nor the setup that after_migrate applies has changed, it has nothing
to do but still takes a while, so the Docker start-up and upgrades skip it.

The *fingerprint* is a hash of everything migrate acts on, for every app in the bench: its
version, hooks.py, patches.txt and patch files, every JSON definition (DocTypes, pages,
workspaces, reports, fixtures...) and, for Research Desk, the Python that after_migrate runs.
A successful migrate records it in the database (`after_migrate` → `record`), so a database
restored from a backup carries the fingerprint of the code it was migrated with.

No Frappe here: create-site.sh runs this with the bench's Python before Frappe starts:

    env/bin/python -m sok_resdesk.core.schema check SITE   # exit 0: up to date, 1: migrate
    env/bin/python -m sok_resdesk.core.schema show         # print the code's fingerprint
"""

from __future__ import annotations

import hashlib
import json
import os
import sys

# change this to make every install migrate once (e.g. when the recipe below changes)
FORMAT = "1"
KEY = "resdesk_schema_fingerprint"

SKIP_DIRS = {"public", "node_modules", "__pycache__", ".git", "dist", "locale", "translations"}
# Python that after_migrate runs: a change to it must re-run migrate
AFTER_MIGRATE_FILES = {
	"sok_resdesk": (
		"setup.py",
		"guide.py",
		"resdesk/doctype/rd_settings/rd_settings.py",
	),
}


def apps(bench: str) -> list[str]:
	try:
		with open(os.path.join(bench, "sites", "apps.txt")) as f:
			return [a.strip() for a in f if a.strip()]
	except OSError:
		return []


def app_files(bench: str, app: str) -> list[str]:
	"""The files of one app that migrate acts on, relative to the app's package folder."""
	root = os.path.join(bench, "apps", app, app)
	found = []
	for top, dirs, files in os.walk(root):
		dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
		rel_top = os.path.relpath(top, root)
		in_patches = rel_top == "patches" or rel_top.startswith("patches" + os.sep)
		for name in files:
			rel = os.path.normpath(os.path.join(rel_top, name))
			if (
				name.endswith(".json")
				or (in_patches and name.endswith(".py"))
				or rel in ("__init__.py", "hooks.py", "patches.txt", "modules.txt")
			):
				found.append(rel)
	for rel in AFTER_MIGRATE_FILES.get(app, ()):
		if os.path.exists(os.path.join(root, rel)):
			found.append(os.path.normpath(rel))
	return sorted(set(found))


def fingerprint(bench: str) -> str:
	h = hashlib.sha256(f"format {FORMAT}\n".encode())
	for app in apps(bench):
		root = os.path.join(bench, "apps", app, app)
		h.update(f"app {app}\n".encode())
		for rel in app_files(bench, app):
			h.update(rel.replace(os.sep, "/").encode() + b"\0")
			with open(os.path.join(root, rel), "rb") as f:
				h.update(hashlib.sha256(f.read()).digest())
	return h.hexdigest()


def site_config(bench: str, site: str) -> dict:
	conf = {}
	for path in (
		os.path.join(bench, "sites", "common_site_config.json"),
		os.path.join(bench, "sites", site, "site_config.json"),
	):
		try:
			with open(path) as f:
				conf.update(json.load(f))
		except (OSError, ValueError):
			pass
	return conf


def stored(bench: str, site: str) -> str | None:
	"""The fingerprint recorded by the site's last successful migrate (None if unknown)."""
	conf = site_config(bench, site)
	if not conf.get("db_name"):
		return None
	args = {
		"host": conf.get("db_host") or "127.0.0.1",
		"port": int(conf.get("db_port") or 3306),
		"user": conf.get("db_user") or conf["db_name"],
		"password": conf.get("db_password") or "",
		"database": conf["db_name"],
		"connect_timeout": 10,
	}
	try:
		try:
			import MySQLdb as db

			args["passwd"] = args.pop("password")
			args["db"] = args.pop("database")
		except ImportError:
			import pymysql as db
		conn = db.connect(**args)
		try:
			cur = conn.cursor()
			cur.execute(
				"select defvalue from `tabDefaultValue` where parent='__default' and defkey=%s "
				"order by modified desc limit 1",
				(KEY,),
			)
			row = cur.fetchone()
		finally:
			conn.close()
	except Exception as e:
		print(f"could not read the database ({e.__class__.__name__}): migrating to be safe", file=sys.stderr)
		return None
	return row[0] if row else None


def needs_migrate(bench: str, site: str) -> tuple[bool, str]:
	if not os.path.isdir(os.path.join(bench, "sites", site)):
		return True, "no such site"
	current = fingerprint(bench)
	last = stored(bench, site)
	if not last:
		return True, "no record of an earlier migrate"
	if last != current:
		return True, "the code has changed since the last migrate"
	return False, "the database is up to date with the code"


def record() -> None:
	"""Called at the end of after_migrate (inside Frappe): remember what was migrated."""
	import frappe
	from frappe.utils import get_bench_path

	frappe.db.set_default(KEY, fingerprint(get_bench_path()))


def main(argv: list[str]) -> int:
	bench = os.environ.get("BENCH_DIR") or os.getcwd()
	if argv[:1] == ["show"]:
		print(fingerprint(bench))
		return 0
	if len(argv) == 2 and argv[0] == "check":
		needed, why = needs_migrate(bench, argv[1])
		print(why)
		return 1 if needed else 0
	print(__doc__.split("\n\n")[-1], file=sys.stderr)
	return 2


if __name__ == "__main__":
	sys.exit(main(sys.argv[1:]))
