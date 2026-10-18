"""The governance layer is optional: core must not import it (sok_resdesk/seams.py is how core asks).

A library installed without governance must have nothing of it to review, so this fails the day a
core module imports a governance module, however lazily (inside a function counts).
"""

import ast
import os

ROOT = os.path.join(os.path.dirname(__file__), "..")

# governance modules, dotted from sok_resdesk
GOVERNANCE = {
	"audit",
	"classification",
	"classified",
	"clearance",
	"directory",
	"disclosure",
	"mirror",
	"register",
	"retention",
	"core.audit",
	"core.classification",
	"core.classified",
	"core.directory",
	"core.disclosure",
	"core.redact",
	"core.retention",
}
GOVERNANCE_DOCTYPES = {
	"rd_audit_event",
	"rd_clearance",
	"rd_clearance_department",
	"rd_department",
	"rd_directory_account",
	"rd_disclosure_record",
	"rd_disclosure_redaction",
	"rd_disclosure_request",
	"rd_disposal",
	"rd_disposal_item",
	"rd_file",
	"rd_file_movement",
	"rd_file_record",
	"rd_item_scope",
	"rd_legal_hold",
	"rd_legal_hold_item",
	"rd_retention_rule",
}


def _module(path: str) -> str:
	rel = os.path.relpath(path, ROOT)[:-3].replace(os.sep, ".")
	return rel


def _governance_file(path: str) -> bool:
	mod = _module(path)
	if mod in GOVERNANCE:
		return True
	parts = mod.split(".")
	return "doctype" in parts and any(p in GOVERNANCE_DOCTYPES for p in parts)


def _imports(tree) -> set[str]:
	found = set()
	for node in ast.walk(tree):
		if isinstance(node, ast.Import):
			for a in node.names:
				if a.name.startswith("sok_resdesk."):
					found.add(a.name[len("sok_resdesk.") :])
		elif isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] == "sok_resdesk":
			base = node.module[len("sok_resdesk") :].lstrip(".")
			found.add(base) if base else None
			for a in node.names:
				found.add(f"{base}.{a.name}" if base else a.name)
	return found


def _core_files():
	for folder, dirs, files in os.walk(ROOT):
		dirs[:] = [d for d in dirs if d not in ("tests", "__pycache__", "node_modules", "vendor", "public")]
		for f in files:
			if f.endswith(".py"):
				path = os.path.join(folder, f)
				if not _governance_file(path):
					yield path


def test_core_does_not_import_the_governance_layer():
	bad = []
	for path in _core_files():
		with open(path, encoding="utf-8") as fh:
			tree = ast.parse(fh.read())
		for name in sorted(_imports(tree)):
			if name in GOVERNANCE:
				bad.append(f"{_module(path)} imports {name}")
	assert not bad, "core must reach governance only through seams.py:\n" + "\n".join(bad)


def test_the_governance_modules_listed_exist():
	for name in GOVERNANCE:
		assert os.path.exists(os.path.join(ROOT, *name.split(".")) + ".py"), name
