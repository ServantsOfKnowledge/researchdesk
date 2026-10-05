#!/usr/bin/env python3
"""Refresh the parts of docs/ that are generated from the code, so they can't go stale:

  docs/operations.md  <!-- generated:settings -->  every field of Settings, from rd_settings.json
  docs/operations.md  <!-- generated:commands -->  ./resdesk.sh help and every `bench resdesk` option

    ./resdesk.sh docs            rewrite them
    python3 scripts/gen_docs.py --check   exit 1 if they are out of date (tests/test_docs.py does this)

Pure Python; needs nothing installed.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SETTINGS_JSON = ROOT / "sok_resdesk/resdesk/doctype/rd_settings/rd_settings.json"
COMMANDS_PY = ROOT / "sok_resdesk/commands.py"
RESDESK_SH = ROOT / "resdesk.sh"
TARGETS = {"settings": ROOT / "docs/operations.md", "commands": ROOT / "docs/operations.md"}
LAYOUT = {"Section Break", "Column Break", "Tab Break", "HTML"}


def _cell(text: str) -> str:
	return " ".join((text or "").split()).replace("|", "\\|")


def settings_block() -> str:
	d = json.loads(SETTINGS_JSON.read_text())
	out = []
	for f in d["fields"]:
		if f["fieldtype"] == "Tab Break":
			out += ["", f"### {f.get('label')}"]
		elif f["fieldtype"] == "Section Break":
			out += ["", f"**{f.get('label') or 'General'}**", "", "| Setting | What it does |", "|---|---|"]
		elif f["fieldtype"] not in LAYOUT and not f.get("hidden"):
			desc = f.get("description") or ""
			if f["fieldtype"] == "Select" and f.get("options"):
				desc += " Choices: " + ", ".join(f"*{o}*" for o in f["options"].split("\n") if o) + "."
			out.append(f"| {_cell(f.get('label'))} | {_cell(desc)} |")
	return "\n".join(out).strip()


def _options(call_list) -> list[tuple[str, str]]:
	opts = []
	for c in call_list:
		if not (isinstance(c, ast.Call) and getattr(c.func, "attr", "") in ("option", "argument")):
			continue
		names = [a.value for a in c.args if isinstance(a, ast.Constant) and str(a.value).startswith("-")]
		if getattr(c.func, "attr", "") == "argument":
			names = [str(c.args[0].value).upper()]
		helptext = next(
			(k.value.value for k in c.keywords if k.arg == "help" and isinstance(k.value, ast.Constant)), ""
		)
		if names:
			opts.append((" ".join(names), helptext))
	return opts


def commands_block() -> str:
	sh = RESDESK_SH.read_text()
	m = re.search(r"help\|\*\)\s*\n\s*cat <<EOF\n(.*?)\nEOF", sh, re.S)
	usage = m.group(1).replace("  (this install: $MODE)", "") if m else ""
	tree = ast.parse(COMMANDS_PY.read_text())
	scope = next(
		n.value.elts
		for n in tree.body
		if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "_scope_options"
	)
	rows = []
	for fn in tree.body:
		if not isinstance(fn, ast.FunctionDef):
			continue
		cmd = next(
			(
				d.args[0].value
				for d in fn.decorator_list
				if isinstance(d, ast.Call) and getattr(d.func, "attr", "") == "command" and d.args
			),
			None,
		)
		if not cmd:
			continue
		decos = list(fn.decorator_list)
		opts = []
		for d in decos:
			if isinstance(d, ast.Name) and d.id == "scope_options":
				opts += _options(scope)
			elif isinstance(d, ast.Call):
				opts += _options([d])
		doc = (ast.get_docstring(fn) or "").split("\n")[0]
		rows.append(
			f"| `{cmd}` | {_cell(doc)} | " + "<br>".join(f"`{n}` {_cell(h)}".strip() for n, h in opts) + " |"
		)
	return "\n".join(
		[
			"`./resdesk.sh help` prints:",
			"",
			"```text",
			usage.rstrip(),
			"```",
			"",
			"The Research Desk commands behind it (`./resdesk.sh <command>` runs "
			"`bench --site <site> resdesk <command>`):",
			"",
			"| Command | What it does | Options |",
			"|---|---|---|",
			*rows,
		]
	)


BLOCKS = {"settings": settings_block, "commands": commands_block}


def render(text: str, name: str, body: str) -> str:
	start, end = f"<!-- generated:{name} -->", f"<!-- /generated:{name} -->"
	pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.S)
	block = f"{start}\n<!-- made by scripts/gen_docs.py from the code: edit the code, then run ./resdesk.sh docs -->\n{body}\n{end}"
	if not pattern.search(text):
		raise SystemExit(f"{name}: markers {start} … {end} not found")
	return pattern.sub(lambda _m: block, text)


def main() -> int:
	check = "--check" in sys.argv
	stale = []
	for name, fn in BLOCKS.items():
		path = TARGETS[name]
		old = path.read_text()
		new = render(old, name, fn())
		if new != old:
			stale.append(f"{path.relative_to(ROOT)} ({name})")
			if not check:
				path.write_text(new)
	if check and stale:
		print("Out of date, run ./resdesk.sh docs: " + ", ".join(stale))
		return 1
	print("Updated: " + ", ".join(stale) if stale else "Generated docs are up to date.")
	return 0


if __name__ == "__main__":
	sys.exit(main())
