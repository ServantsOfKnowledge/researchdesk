"""Browser tests for the portal's pages and scripts, without a running site.

The page is rendered from its template (Jinja, with Frappe's `_` and helpers stubbed), the portal's
own scripts are served from public/ as /assets/sok_resdesk, and `fetch` is replaced by a stub, so
what is tested is the page's behaviour in a real browser (Chromium through Playwright) and
its accessibility (axe-core), not the server.

Needs: playwright with Chromium, jinja2, and the files of axe-core and jquery (scripts/ui-tests.sh
fetches them). Anything missing skips the tests. Run: scripts/ui-tests.sh
"""

from __future__ import annotations

import functools
import glob
import http.server
import os
import threading
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[2]
PUBLIC = APP / "public"
CACHE = Path(os.environ.get("RD_UI_CACHE") or APP.parents[0] / ".cache" / "ui")
AXE_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]


def _find(env: str, *patterns: str) -> Path | None:
	if os.environ.get(env) and Path(os.environ[env]).is_file():
		return Path(os.environ[env])
	for pattern in patterns:
		hits = sorted(glob.glob(str(pattern)))
		if hits:
			return Path(hits[0])
	return None


@pytest.fixture(scope="session")
def axe_js() -> str:
	path = _find("RD_AXE", CACHE / "axe" / "package" / "axe.min.js")
	if not path:
		pytest.skip("axe-core is not fetched (scripts/ui-tests.sh)")
	return path.read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def jquery_path() -> Path:
	path = _find("RD_JQUERY", CACHE / "jquery" / "package" / "dist" / "jquery.min.js")
	if not path:
		pytest.skip("jquery is not fetched (scripts/ui-tests.sh)")
	return path


@pytest.fixture(scope="session")
def site(tmp_path_factory, jquery_path):
	"""A tiny web server: /assets/sok_resdesk → public/, /jquery.min.js, and pages written by tests."""
	root = tmp_path_factory.mktemp("site")
	(root / "assets").mkdir()
	(root / "assets" / "sok_resdesk").symlink_to(PUBLIC, target_is_directory=True)
	(root / "jquery.min.js").write_bytes(jquery_path.read_bytes())
	handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root))
	handler.log_message = lambda *a, **k: None  # type: ignore[attr-defined]
	server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
	threading.Thread(target=server.serve_forever, daemon=True).start()

	class Site:
		url = f"http://127.0.0.1:{server.server_port}"

		def write(self, name: str, html: str) -> str:
			(root / name).write_text(html, encoding="utf-8")
			return f"{self.url}/{name}"

	yield Site()
	server.shutdown()


@pytest.fixture(scope="session")
def browser():
	sync_api = pytest.importorskip("playwright.sync_api")
	exe = _find("RD_CHROMIUM", "/opt/pw-browsers/chromium-*/chrome-linux*/chrome")
	with sync_api.sync_playwright() as p:
		try:
			b = p.chromium.launch(executable_path=str(exe)) if exe else p.chromium.launch()
		except Exception as e:  # no browser installed
			pytest.skip(f"no Chromium for Playwright: {str(e)[:80]}")
		yield b
		b.close()


@pytest.fixture
def page(browser):
	ctx = browser.new_context(viewport={"width": 1100, "height": 900})
	pg = ctx.new_page()
	pg.errors = []
	pg.on("pageerror", lambda e: pg.errors.append(str(e)))
	yield pg
	ctx.close()


def axe_violations(page, axe_js: str) -> list[tuple]:
	"""(rule, impact, first target) of every WCAG 2.2 A/AA problem axe finds on the page now."""
	page.evaluate(axe_js)
	result = page.evaluate(f"axe.run(document, {{ runOnly: {AXE_TAGS!r} }})")
	return [(v["id"], v["impact"], v["nodes"][0]["target"]) for v in result["violations"]]


STUB_GLOBALS = "window.csrf_token = 'x'; window.RD_I18N = { messages: {} };"


def render_template(name: str, **context) -> tuple[str, str]:
	"""(page_content html, script html) of a portal template under www/library, rendered with Jinja."""
	jinja2 = pytest.importorskip("jinja2")
	src = (APP / "www" / "library" / name).read_text(encoding="utf-8")
	env = jinja2.Environment()
	env.globals.update(_=lambda s: s, library_url=lambda: "/", portal_title="Library", **context)
	content = src.split("{% block page_content %}")[1].split("{% endblock %}")[0]
	script = (
		src.split("{% block script %}")[1].split("{% endblock %}")[0] if "{% block script %}" in src else ""
	)
	return env.from_string(content).render(title="x"), env.from_string(script).render()


def page_shell(body: str, scripts: str = "", lang: str = "en") -> str:
	css = (PUBLIC / "css" / "resdesk.css").read_text(encoding="utf-8")
	return (
		f'<!doctype html><html lang="{lang}"><head><meta charset="utf-8">'
		'<meta name="viewport" content="width=device-width"><title>Test page</title>'
		f"<style>{css}</style></head><body><main>{body}</main>{scripts}</body></html>"
	)
