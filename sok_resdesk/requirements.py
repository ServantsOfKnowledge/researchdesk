"""Requirements: how well this server is equipped for Research Desk, and installing what is
missing (Server page → Requirements; `bench resdesk requirements`).

Each line says what a tool is for, what was found, what is needed, and how to put it right on this
kind of install. On a native install the updater helper can install the Python packages and
Tesseract with its language models (scripts/requirements.sh: Homebrew on macOS; apt on
Ubuntu/Debian when sudo needs no password, otherwise the command to run is shown). On Docker
everything comes with the image, so the answer is to upgrade.
"""

from __future__ import annotations

import os
import platform
import shutil
import sys

import frappe
from frappe import _
from frappe.utils import cint

from sok_resdesk.core import equipment as eq

ADMINS = ("System Manager", "ResDesk Manager")
INSTALLABLE = ("python", "ocr")
CACHE_KEY = "resdesk:requirements"
GB = 1024**3
LANGUAGE_NAMES = {
	"kan": "Kannada", "hin": "Hindi", "mar": "Marathi", "san": "Sanskrit", "nep": "Nepali",
	"tam": "Tamil", "tel": "Telugu", "mal": "Malayalam", "ben": "Bengali", "guj": "Gujarati",
	"pan": "Punjabi", "ori": "Oriya", "urd": "Urdu", "eng": "English",
}  # fmt: skip


def install_mode() -> str:
	from sok_resdesk.server import agent_facts

	return agent_facts().get("mode") or ("docker" if os.environ.get("RESDESK_RESOURCES") else "native")


def system() -> str:
	if platform.system() == "Darwin":
		return "mac"
	if os.path.exists("/etc/debian_version"):
		return "debian"
	return "other"


DOCKER_OCR_LANGS = "all"  # compose.yaml's default: every model Tesseract has


def _fix(part: str, mode: str, osname: str, models: list[str] | None = None, add: bool = False) -> str:
	"""How to put a missing tool right, on this kind of install. add=True: language models the
	Docker image lacks (OCR_LANGS in .env replaces the default list, so the whole value is given)."""
	if mode == "docker":
		if add and models:
			have = (os.environ.get("RESDESK_OCR_LANGS") or DOCKER_OCR_LANGS).split()
			if "all" in have:
				return _(
					"Comes with the Research Desk image (every language model): upgrade (Server → Upgrade, or ./upgrade.sh)."
				)
			value = " ".join(dict.fromkeys([*have, *models]))
			return _(
				'Set OCR_LANGS="{0}" in .env on the server, then upgrade: the image is rebuilt with it.'
			).format(value)
		return _("Comes with the Research Desk image: upgrade (Server → Upgrade, or ./upgrade.sh).")
	if part == "python":
		return "./resdesk.sh requirements install python"
	if part == "ocr":
		if osname == "mac":
			return "brew install tesseract tesseract-lang poppler"
		if osname == "debian":
			return "sudo apt-get install tesseract-ocr poppler-utils tesseract-ocr-all"
		return _(
			"Install Tesseract, its language models and poppler (pdftoppm) with this system's package manager."
		)
	return ""


def _catalogue_models() -> list[tuple[str, int]]:
	"""[(Tesseract model, books)] for the catalogue's languages, the most books first."""
	from sok_resdesk.core.ocr_engine import models_in

	counts: dict[str, int] = {}
	for code, label, chosen, n in frappe.db.sql(
		"""select language, language_label, ocr_languages, count(*) from `tabRD Item` where published = 1
		group by language, language_label, ocr_languages order by 4 desc limit 80"""
	):
		# a book in several languages counts for each ("Kannada; English"); OCR Languages win
		for model in models_in(chosen) or models_in(code, label):
			counts[model] = counts.get(model, 0) + cint(n)
	return sorted(counts.items(), key=lambda kv: kv[1], reverse=True)


def _meili() -> dict:
	from sok_resdesk.search import MeiliClient

	try:
		return MeiliClient.from_settings()._req("GET", "/version")
	except Exception as e:
		return {"error": str(e)[:200]}


def _writable(path: str) -> tuple[bool, str]:
	try:
		os.makedirs(path, exist_ok=True)
		probe = os.path.join(path, ".resdesk-write-check")
		with open(probe, "w") as f:
			f.write("ok")
		os.remove(probe)
		free = shutil.disk_usage(path).free
		return True, _("{0} GB free").format(round(free / GB, 1))
	except OSError as e:
		return False, str(e)[:200]


def _archive_org() -> tuple[bool, str]:
	import requests

	try:
		r = requests.get("https://archive.org/metadata/ServantsOfKnowledge/metadata/identifier", timeout=8)
		return r.status_code == 200, f"HTTP {r.status_code}"
	except requests.RequestException as e:
		return False, str(e)[:120]


def check() -> list[dict]:
	"""Every requirement, as eq.item() lines, in the order the page shows them."""
	from sok_resdesk.core import ocr_engine

	mode, osname = install_mode(), system()
	s = frappe.db.get_singles_dict("RD Settings")
	items: list[dict] = []
	add = items.append
	core, search, ocr, pres, net = (
		_("Core"),
		_("Search"),
		_("OCR and proofreading"),
		_("Preservation"),
		_("Network and disk"),
	)

	py = ".".join(str(x) for x in sys.version_info[:3])
	add(
		eq.item(
			"python",
			core,
			"Python",
			_("runs Research Desk"),
			"ok" if sys.version_info >= (3, 11) else "old",
			py,
			"3.11",
		)
	)
	fv = getattr(frappe, "__version__", "")
	add(
		eq.item(
			"frappe", core, "Frappe", _("the framework"), "ok" if eq.at_least(fv, "16.0") else "old", fv, "16"
		)
	)
	try:
		db = frappe.db.sql("select version()")[0][0]
	except Exception:
		db = ""
	add(
		eq.item(
			"mariadb",
			core,
			"MariaDB",
			_("the catalogue database"),
			"ok" if eq.at_least(db, "10.6") else "old",
			db,
			"10.6",
		)
	)
	try:
		redis_ok = bool(frappe.cache.ping())
	except Exception:
		redis_ok = False
	add(
		eq.item(
			"redis",
			core,
			"Redis",
			_("cache and background-job queues"),
			"ok" if redis_ok else "missing",
			_("answers") if redis_ok else _("no answer"),
		)
	)
	from sok_resdesk.server import helper_connected

	helper = helper_connected()
	add(
		eq.item(
			"helper",
			core,
			_("Updater helper"),
			_("upgrades, restarts and installing tools from the Desk"),
			"ok" if helper else "warn",
			_("connected") if helper else _("not running"),
			fix="" if helper else "./resdesk.sh updater on",
		)
	)
	if mode == "native":
		for prog, purpose in (("git", _("upgrades")), ("uv", _("installing Python packages"))):
			found = eq.program(prog)
			add(
				eq.item(
					prog,
					core,
					prog,
					purpose,
					"ok" if found else "missing",
					found.get("version", ""),
					fix=_("run ./install.sh --native again"),
				)
			)

	meili = _meili()
	mv = meili.get("pkgVersion", "")
	add(
		eq.item(
			"meilisearch",
			search,
			"Meilisearch",
			_("search; Latin-letter spellings and OR need 1.11 or newer"),
			"missing" if meili.get("error") else ("ok" if eq.at_least(mv, "1.11") else "old"),
			mv or meili.get("error", ""),
			"1.11",
			_("upgrade (the image carries it)")
			if mode == "docker"
			else _("install a newer Meilisearch, then ./resdesk.sh restart"),
		)
	)

	pil = eq.package("pillow") or eq.package("Pillow")
	add(
		eq.item(
			"pillow",
			ocr,
			"Pillow",
			_("cutting page images into zones for OCR"),
			"ok" if pil else "missing",
			pil or "",
			fix=_fix("python", mode, osname),
			install="python" if mode == "native" else "",
		)
	)
	tess = eq.program("tesseract")
	models = ocr_engine.available()
	wanted = _catalogue_models()
	missing_models = [m for m, _n in wanted if m not in models]
	add(
		eq.item(
			"tesseract",
			ocr,
			"Tesseract",
			_("re-OCR of pages and books"),
			("ok" if eq.at_least(tess.get("version"), "4.0") else "old") if tess else "missing",
			tess.get("version", ""),
			"4.0",
			_fix("ocr", mode, osname, [m for m, _n in wanted] + ["eng"]),
			"ocr" if mode == "native" else "",
		)
	)
	pop = eq.program("pdftoppm", ("-v",))
	add(
		eq.item(
			"poppler",
			ocr,
			"Poppler (pdftoppm)",
			_("drawing the pages of PDFs: OCR, proofreading and Page & text for books not on archive.org"),
			"ok" if pop else "warn",
			pop.get("version", ""),
			fix="" if pop else _fix("ocr", mode, osname),
			install="" if pop or mode != "native" else "ocr",
		)
	)
	for model, books in wanted:
		add(
			eq.item(
				f"model-{model}",
				ocr,
				_("Tesseract model: {0}").format(LANGUAGE_NAMES.get(model, model)),
				_("{0} books in this language").format(f"{books:,}"),
				"ok" if model in models else ("missing" if tess else "off"),
				model if model in models else "",
				fix="" if model in models else _fix("ocr", mode, osname, missing_models or [model], add=True),
				install="" if model in models or mode != "native" else "ocr",
			)
		)

	root = (s.get("preservation_root") or "").strip()
	if root:
		ok, detail = _writable(root)
		add(
			eq.item(
				"preservation",
				pres,
				_("Preservation folder"),
				root,
				"ok" if ok else "missing",
				detail,
				fix=_("check the folder exists and Research Desk may write to it"),
			)
		)
	else:
		add(
			eq.item(
				"preservation",
				pres,
				_("Preservation folder"),
				_("the library's own copies"),
				"off",
				_("not set"),
				fix=_("Settings → Preservation"),
			)
		)
	kind = s.get("second_copy") or "Off"
	b3 = eq.package("boto3")
	add(
		eq.item(
			"boto3",
			pres,
			"boto3",
			_("a second copy on S3-compatible storage"),
			"ok" if b3 else ("missing" if kind == "S3-compatible" else "off"),
			b3 or "",
			fix=_fix("python", mode, osname),
			install="python" if mode == "native" and not b3 else "",
		)
	)
	if kind == "Folder" and (s.get("second_folder") or "").strip():
		ok, detail = _writable(s["second_folder"].strip())
		add(
			eq.item(
				"second-copy",
				pres,
				_("Second copy folder"),
				s["second_folder"],
				"ok" if ok else "missing",
				detail,
				fix=_("mount the share, or check its permissions"),
			)
		)
	elif kind == "S3-compatible":
		try:
			from sok_resdesk.preservation import second

			rep = second()
			rep.client.head_bucket(Bucket=rep.bucket)
			add(eq.item("second-copy", pres, _("Second copy bucket"), rep.describe(), "ok", _("reachable")))
		except Exception as e:
			add(
				eq.item(
					"second-copy",
					pres,
					_("Second copy bucket"),
					s.get("s3_bucket") or "",
					"missing",
					str(e)[:200],
					fix=_("check the endpoint, bucket and keys in Settings → Preservation"),
				)
			)

	ok, detail = _archive_org()
	add(
		eq.item(
			"archive-org",
			net,
			"archive.org",
			_("bringing books in, page images, sync"),
			"ok" if ok else "missing",
			detail,
			fix=_("check the server's internet connection or proxy"),
		)
	)
	try:
		du = shutil.disk_usage(frappe.get_site_path())
		free_gb = du.free / GB
		state = (
			"ok" if free_gb >= 10 and du.free / du.total >= 0.1 else ("warn" if free_gb >= 3 else "missing")
		)
		add(
			eq.item(
				"disk",
				net,
				_("Disk space"),
				_("the database, search index and page-text cache"),
				state,
				_("{0} GB free of {1} GB").format(round(free_gb, 1), round(du.total / GB)),
				_("10 GB"),
				_("free space, or move to a bigger disk (docs/moving.md)"),
			)
		)
	except OSError:
		pass
	return items


def _report(refresh: int = 0) -> dict:
	if not cint(refresh):
		cached = frappe.cache.get_value(CACHE_KEY)
		if cached:
			return cached
	from sok_resdesk.server import desk_control_allowed, helper_connected

	items = check()
	mode = install_mode()
	out = {
		"items": items,
		"summary": eq.summary(items),
		"mode": mode,
		"system": system(),
		"can_install": mode == "native" and helper_connected() and desk_control_allowed(),
	}
	frappe.cache.set_value(CACHE_KEY, out, expires_in_sec=600)
	return out


@frappe.whitelist()
def report(refresh: int = 0) -> dict:
	"""For the Server page: the list, the counts, the install mode and what can be installed here
	(worked out at most every ten minutes; refresh=1 for now)."""
	frappe.only_for(ADMINS)
	return _report(refresh)


@frappe.whitelist(methods=["POST"])
def install(part: str) -> str:
	"""Ask the updater helper to install `part` (python or ocr). Returns the Server Task's name."""
	frappe.only_for(ADMINS)
	if part not in INSTALLABLE:
		frappe.throw(_("Research Desk installs only: {0}").format(", ".join(INSTALLABLE)))
	if install_mode() != "native":
		frappe.throw(_("On Docker the tools come with the image: upgrade instead."))
	from sok_resdesk.server import request_task

	frappe.cache.delete_value(CACHE_KEY)
	return request_task("install_requirements", {"part": part})


def health_check() -> dict:
	"""For the Server page's health list (and its alerts): one line summing the requirements up."""
	items = _report()["items"]
	counts = eq.summary(items)
	missing = [i["label"] for i in items if i["state"] in ("missing", "old")]
	return {
		"key": "requirements",
		"label": _("Requirements"),
		"state": "bad" if missing else ("warn" if counts["warn"] else "ok"),
		"detail": _("missing or too old: {0}").format(", ".join(missing[:4]))
		if missing
		else _("{0} in place").format(counts["ok"]),
		"link": "/app/resdesk-server#requirements",
	}
