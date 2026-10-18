"""Every `from sok_resdesk.<module> import <name>` names something that module still has.

A function moved to another module leaves its old import behind, and only the page that runs it
notices (0.87: the item page). This reads the code instead, so it is found before anyone opens a page.
"""

import ast
import os

ROOT = os.path.join(os.path.dirname(__file__), "..")


def _defined(path: str) -> set[str] | None:
	"""Top-level names of a module; None if it builds names dynamically (then it is not checked)."""
	with open(path, encoding="utf-8") as f:
		tree = ast.parse(f.read())
	names = set()
	for node in ast.walk(tree):
		if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
			names.add(node.name)
		elif isinstance(node, ast.Assign):
			for t in node.targets:
				names |= {n.id for n in ast.walk(t) if isinstance(n, ast.Name)}  # also D, P = ...
		elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
			names.add(node.target.id)
		elif isinstance(node, (ast.Import, ast.ImportFrom)):
			for a in node.names:
				if a.name == "*":
					return None
				names.add((a.asname or a.name).split(".")[0])
	if "__getattr__" in names:
		return None
	return names


def _files():
	for folder, dirs, files in os.walk(ROOT):
		dirs[:] = [d for d in dirs if d not in ("__pycache__", "node_modules", "vendor", "public")]
		for f in files:
			if f.endswith(".py"):
				yield os.path.join(folder, f)


def test_imported_names_exist():
	bad = []
	for path in _files():
		with open(path, encoding="utf-8") as fh:
			tree = ast.parse(fh.read())
		for node in ast.walk(tree):
			if not (isinstance(node, ast.ImportFrom) and node.module and node.level == 0):
				continue
			if node.module.split(".")[0] != "sok_resdesk":
				continue
			target = os.path.join(ROOT, *node.module.split(".")[1:])
			if os.path.isfile(target + ".py"):
				have = _defined(target + ".py")
				if have is None:
					continue
				for a in node.names:
					if a.name not in have:
						bad.append(f"{os.path.relpath(path, ROOT)}: {node.module} has no {a.name}")
			elif os.path.isdir(target):
				for a in node.names:  # a submodule, or a name the package's __init__ defines
					if os.path.exists(os.path.join(target, a.name + ".py")) or os.path.isdir(
						os.path.join(target, a.name)
					):
						continue
					init = os.path.join(target, "__init__.py")
					have = _defined(init) if os.path.exists(init) else set()
					if have is not None and a.name not in have:
						bad.append(f"{os.path.relpath(path, ROOT)}: {node.module} has no {a.name}")
	assert not bad, "\n".join(bad)
