"""The governance layer is optional: core must not import it (sok_resdesk/seams.py is how core asks).

A library installed without governance must have nothing of it to review. Governance is its own app,
sok_resdesk_governance (governance/), so this fails the day a core module imports it, however lazily
(inside a function counts), and the day the app imports a name core does not have.
"""

import ast
import os

ROOT = os.path.join(os.path.dirname(__file__), "..")
GOVERNANCE = os.path.join(ROOT, "..", "governance", "sok_resdesk_governance")


def _py_files(base):
	for folder, dirs, files in os.walk(base):
		dirs[:] = [d for d in dirs if d not in ("tests", "__pycache__", "node_modules", "vendor", "public")]
		for f in files:
			if f.endswith(".py"):
				yield os.path.join(folder, f)


def test_core_does_not_import_the_governance_app():
	bad = []
	for path in _py_files(ROOT):
		with open(path, encoding="utf-8") as fh:
			tree = ast.parse(fh.read())
		for node in ast.walk(tree):
			names = []
			if isinstance(node, ast.Import):
				names = [a.name for a in node.names]
			elif isinstance(node, ast.ImportFrom) and node.module:
				names = [node.module]
			bad += [
				f"{os.path.relpath(path, ROOT)} imports {n}"
				for n in names
				if n.split(".")[0] == "sok_resdesk_governance"
			]
	assert not bad, "core must reach governance only through seams.py:\n" + "\n".join(bad)


def test_the_governance_app_is_where_the_docs_say():
	assert os.path.isdir(GOVERNANCE)
	for name in ("audit", "classification", "clearance", "disclosure", "retention", "core/redact"):
		assert os.path.exists(os.path.join(GOVERNANCE, *name.split("/")) + ".py"), name
	assert not os.path.exists(os.path.join(ROOT, "audit.py"))
