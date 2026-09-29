"""WSGI entry point for native installs (no nginx in front).

Frappe's production app does not serve /assets and /files itself, and it picks the site
from the Host header (nginx does both jobs in Docker and in `bench setup production`).
For a native install we run gunicorn with this application instead:

* Frappe's own static-file middleware serves /assets and /files;
* every request goes to the bench's default site (``bench use <site>``), so the portal
  works at http://localhost:8000, a LAN IP or any host name;
* there is no development server and no interactive debugger.

    gunicorn --chdir sites sok_resdesk.native_wsgi:application
"""

import os

import frappe.app

_app = frappe.app.application_with_statics()


def _default_site() -> str:
	"""RESDESK_SITE, else the bench default (`bench use`: common_site_config or currentsite.txt)."""
	import json

	site = os.environ.get("RESDESK_SITE", "")
	if not site and os.path.exists("common_site_config.json"):
		with open("common_site_config.json") as f:
			site = (json.load(f) or {}).get("default_site", "")
	if not site and os.path.exists("currentsite.txt"):
		with open("currentsite.txt") as f:
			site = f.read().strip()
	return site


SITE = _default_site()


def application(environ, start_response):
	if SITE and not environ.get("HTTP_X_FRAPPE_SITE_NAME"):
		environ["HTTP_X_FRAPPE_SITE_NAME"] = SITE
	return _app(environ, start_response)
