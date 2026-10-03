"""Guards on hooks.py and the search settings. Pure Python: runs in CI with plain pytest."""

import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[1]


def _tree(name: str) -> ast.Module:
	return ast.parse((APP / name).read_text(encoding="utf-8"))


def test_no_dict_in_hooks_repeats_a_key():
	"""Python keeps the last of two equal keys, so a second "*/10 * * * *" cron entry silently
	replaced the first: the job that carries on interrupted runs never ran."""
	for node in ast.walk(_tree("hooks.py")):
		if isinstance(node, ast.Dict):
			keys = [ast.literal_eval(k) for k in node.keys if isinstance(k, ast.Constant)]
			repeated = {k for k in keys if keys.count(k) > 1}
			assert not repeated, f"hooks.py repeats {repeated}: put the values in one list"


def test_interrupted_runs_and_server_watch_are_both_scheduled():
	events = next(
		ast.literal_eval(n.value)
		for n in _tree("hooks.py").body
		if isinstance(n, ast.Assign) and n.targets[0].id == "scheduler_events"
	)
	every_ten = events["cron"]["*/10 * * * *"]
	assert "sok_resdesk.ingest.mark_interrupted_runs" in every_ten
	assert "sok_resdesk.server.watch" in every_ten


def test_the_book_count_is_not_capped_at_ten_thousand():
	"""The portal shows "N books" from the search engine's count, which stopped at maxTotalHits:
	with more than 10,000 books the number froze however many came in."""
	consts = {
		t.id: ast.literal_eval(n.value)
		for n in _tree("search.py").body
		if isinstance(n, ast.Assign)
		for t in n.targets
		if isinstance(t, ast.Name) and isinstance(n.value, ast.Constant)
	}
	assert consts["BOOKS_MAX_HITS"] >= 500_000
	assert consts["PAGES_MAX_HITS"] == 10_000  # page text keeps a small cap; the portal shows "10,000+"
