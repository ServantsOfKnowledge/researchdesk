"""Keep the documentation in step with the code. Pure Python: runs in CI with plain pytest.

Each test names what to update when it fails. The rule of thumb: a change that adds something
people can see or call (a setting, a screen, an API, a command, a DocType) updates docs/ in the
same commit, and `./resdesk.sh docs` refreshes the generated parts.
"""

import ast
import importlib.util
import json
import re
from pathlib import Path

from sok_resdesk.core import helpdocs

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "sok_resdesk"
DOCS = ROOT / "docs"
DOCTYPES = APP / "resdesk" / "doctype"


def _read(path: Path) -> str:
	return path.read_text(encoding="utf-8")


def _load_script(name: str):
	spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
	mod = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(mod)
	return mod


def _literal(path: Path, name: str):
	"""A module-level constant (dict/list literal) without importing the module (it needs Frappe)."""
	for node in ast.parse(_read(path)).body:
		target = node.targets[0] if isinstance(node, ast.Assign) else getattr(node, "target", None)
		if getattr(target, "id", None) == name:
			return ast.literal_eval(node.value)
	raise AssertionError(f"{name} not found in {path}")


def _doctype(name: str) -> dict:
	folder = DOCTYPES / name.lower().replace(" ", "_")
	return json.loads(_read(folder / f"{folder.name}.json"))


def test_every_api_is_documented():
	"""A new @frappe.whitelist() function goes into docs/api.md."""
	api = _read(DOCS / "api.md")
	missing = []
	for path in sorted(APP.rglob("*.py")):
		if {"tests", "patches", "doctype", "page", "www"} & set(path.relative_to(APP).parts):
			continue
		module = ".".join(path.relative_to(ROOT).with_suffix("").parts)
		for node in ast.parse(_read(path)).body:
			if not isinstance(node, ast.FunctionDef):
				continue
			whitelisted = any("whitelist" in ast.unparse(d) for d in node.decorator_list)
			if (
				whitelisted
				and f"{module}.{node.name}" not in api
				and not (f"`{node.name}`" in api and f"{module}." in api)
			):
				missing.append(f"{module}.{node.name}")
	assert not missing, f"Add these to docs/api.md: {missing}"


def test_every_doctype_is_in_the_data_model():
	"""A new DocType gets a row in docs/architecture.md → Data model."""
	arch = _read(DOCS / "architecture.md")
	missing = []
	for folder in sorted(DOCTYPES.iterdir()):
		spec = folder / f"{folder.name}.json"
		if spec.exists() and json.loads(_read(spec))["name"] not in arch:
			missing.append(json.loads(_read(spec))["name"])
	assert not missing, f"Describe these in docs/architecture.md: {missing}"


def test_every_setting_explains_itself():
	"""Settings fields need a description: it shows under the field and in docs/operations.md."""
	fields = _doctype("RD Settings")["fields"]
	missing = [
		f["fieldname"]
		for f in fields
		if f["fieldtype"] not in ("Section Break", "Column Break", "Tab Break")
		and not f.get("hidden")
		and not f.get("description")
	]
	assert not missing, f"Give these RD Settings fields a description: {missing}"


def test_generated_docs_are_current():
	"""The settings and command reference in docs/operations.md are made from the code."""
	gen = _load_script("gen_docs")
	for name, make in gen.BLOCKS.items():
		text = _read(gen.TARGETS[name])
		assert gen.render(text, name, make()) == text, "Run ./resdesk.sh docs and commit the result"


def test_every_shell_command_is_documented():
	docs = "\n".join(_read(p) for p in DOCS.glob("*.md")) + _read(ROOT / "README.md")
	cases = re.findall(r"^  ([a-z][a-z-]*)\)", _read(ROOT / "resdesk.sh"), re.M)
	lines = [line for line in docs.splitlines() if "resdesk.sh" in line]
	missing = [
		c for c in cases if not any(re.search(rf"(resdesk\.sh |\| ){re.escape(c)}\b", line) for line in lines)
	]
	assert not missing, f"Document ./resdesk.sh {missing} (add them to its help text, then ./resdesk.sh docs)"


def test_links_images_and_anchors_resolve():
	"""Every relative link in the docs points at a file (and heading) that exists."""
	problems = []
	anchors = {p.name: helpdocs.anchors(_read(p)) for p in DOCS.glob("*.md")}
	for page in [*DOCS.glob("*.md"), ROOT / "README.md"]:
		md = _read(page)
		own = helpdocs.anchors(md)
		for _is_image, target in helpdocs.links(md):
			if re.match(r"^[a-z]+:", target) or target.startswith("/"):
				continue
			path, anchor = helpdocs.split_target(target)
			if not path:
				if anchor not in own:
					problems.append(f"{page.name}: #{anchor}")
				continue
			resolved = (page.parent / path).resolve()
			if not resolved.exists():
				problems.append(f"{page.name}: {target}")
			elif anchor and resolved.suffix == ".md" and anchor not in anchors.get(resolved.name, set()):
				problems.append(f"{page.name}: {target} (no such heading)")
	assert not problems, "Broken links: " + "; ".join(problems)


def test_every_doc_is_a_help_page():
	"""docs/*.md show up in the in-app help (sok_resdesk/core/helpdocs.py → PAGES)."""
	files = {p.name for p in DOCS.glob("*.md")} - {"README.md"}
	registered = {p.file for p in helpdocs.PAGES}
	assert files == registered, f"Add to / remove from helpdocs.PAGES: {sorted(files ^ registered)}"
	index = _read(DOCS / "README.md")
	missing = [f for f in files if f"({f})" not in index]
	assert not missing, f"List these in docs/README.md: {missing}"


def test_help_buttons_point_at_real_sections():
	screen_help = _literal(APP / "help.py", "SCREEN_HELP")
	links = [(slug, anchor, f"help.py {screen}") for screen, (slug, anchor) in screen_help.items()]
	for js in [*APP.rglob("*.js"), *APP.rglob("*.html")]:
		for slug, anchor in re.findall(r"/app/resdesk-help/([a-z-]+)#([a-z0-9-]+)", _read(js)):
			links.append((slug, anchor, js.name))
	for slug, anchor, where in links:
		page = helpdocs.BY_SLUG.get(slug)
		assert page, f"{where}: no help page {slug}"
		assert anchor in helpdocs.anchors(_read(DOCS / page.file)), (
			f"{where}: {page.file} has no heading #{anchor}"
		)
	doctypes = {
		json.loads(_read(f / f"{f.name}.json"))["name"]
		for f in DOCTYPES.iterdir()
		if (f / f"{f.name}.json").exists() and not json.loads(_read(f / f"{f.name}.json")).get("istable")
	}
	missing = sorted(doctypes - set(screen_help))
	assert not missing, f"Give these screens a Help section in help.py SCREEN_HELP: {missing}"


def test_tours_point_at_real_fields():
	"""Form tours (guide.py) must follow the forms: a renamed or removed field breaks the tour."""
	for doctype, steps in _literal(APP / "guide.py", "TOURS").items():
		fields = {f["fieldname"]: f for f in _doctype(doctype)["fields"]}
		for fieldname, *_ in steps:
			assert fieldname in fields, f"Tour {doctype}: no field {fieldname}"
			assert not fields[fieldname].get("hidden"), f"Tour {doctype}: {fieldname} is hidden"


def test_checklist_steps_are_valid():
	tours = _literal(APP / "guide.py", "TOURS")
	pages = {p.name for p in (APP / "resdesk" / "page").iterdir() if p.is_dir()}
	for key, _title, _desc, action, _when in _literal(APP / "guide.py", "STEPS"):
		route = action["route"]
		if route[0] == "Form":
			_doctype(route[1])  # exists
		else:
			assert route[0].replace("-", "_") in pages, f"checklist {key}: no page {route[0]}"
		if action.get("tour"):
			assert action["tour"] in tours, f"checklist {key}: no tour {action['tour']}"
		if action.get("field"):
			assert action["field"] in {f["fieldname"] for f in _doctype(route[1])["fields"]}


def test_screenshots_match_the_docs():
	"""Pictures used in the docs are taken by scripts/screenshots.py, and every picture is used."""
	shots = set(_load_script("screenshots").SHOTS)
	used = set()
	for page in DOCS.glob("*.md"):
		for is_image, target in helpdocs.links(_read(page)):
			if is_image and helpdocs.IMAGE_DIR in target:
				used.add(Path(target).stem)
	on_disk = {p.stem for p in (ROOT / helpdocs.IMAGE_DIR).glob("*.png")}
	assert used <= shots, f"Add to scripts/screenshots.py SHOTS: {sorted(used - shots)}"
	assert shots <= on_disk, f"Take these with ./resdesk.sh screenshots: {sorted(shots - on_disk)}"
	assert on_disk <= used, f"Pictures no page uses (delete them or use them): {sorted(on_disk - used)}"


def test_changelog_matches_version():
	"""Every release has a CHANGELOG entry for __version__ (the top one)."""
	version = re.search(r'__version__ = "([^"]+)"', _read(APP / "__init__.py")).group(1)
	top = re.search(r"^## (\S+)", _read(ROOT / "CHANGELOG.md"), re.M).group(1)
	assert top == version, f"CHANGELOG.md starts with {top} but __version__ is {version}"


def test_shell_scripts_run_on_macos_bash():
	"""macOS ships bash 3.2, which reads a character like … straight after $NAME as part of the
	name ("HOST…: unbound variable"). Write ${NAME}… instead."""
	bad = []
	for path in [
		ROOT / "resdesk.sh",
		ROOT / "upgrade.sh",
		ROOT / "install.sh",
		*(ROOT / "scripts").glob("*.sh"),
	]:
		for n, line in enumerate(_read(path).splitlines(), 1):
			if re.search(r"\$[A-Za-z_][A-Za-z0-9_]*[^\x00-\x7F]", line):
				bad.append(f"{path.name}:{n}")
	assert not bad, f"Use ${{NAME}} before non-ASCII characters: {bad}"
