"""Every public (guest) endpoint has a rate limit: the claim in docs/technology.md and the Claude Doc."""

import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[1]


def test_every_guest_endpoint_is_rate_limited():
	missing = []
	for path in sorted(APP.rglob("*.py")):
		if {"tests", "patches"} & set(path.relative_to(APP).parts):
			continue
		for node in ast.parse(path.read_text(encoding="utf-8")).body:
			if not isinstance(node, ast.FunctionDef):
				continue
			decorators = [ast.unparse(d) for d in node.decorator_list]
			if any("allow_guest=True" in d for d in decorators) and not any(
				d.startswith("rate_limit(") for d in decorators
			):
				missing.append(f"{path.relative_to(APP)}:{node.name}")
	assert not missing, f"Add @rate_limit to: {missing}"
