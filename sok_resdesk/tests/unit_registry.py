"""The install note (core/registry.py): exactly what is sent, what is accepted, how it is counted. Pure."""

from datetime import date, datetime

from sok_resdesk.core import registry as r

ID = "123e4567-e89b-42d3-a456-426614174000"


def test_the_note_has_five_things_and_only_clean_profile_names():
	note = r.payload(
		ID, "0.109.0", "standard", "docker", ["school", "archive", "school", "Bad Name", "x" * 40]
	)
	assert set(note) == {"id", "version", "edition", "kind", "profiles"}
	assert note["profiles"] == ["archive", "school"]


def test_only_an_exact_note_is_accepted():
	ok = r.payload(ID, "0.109.0", "standard", "linux", ["school"])
	assert r.valid(ok) == ok
	for bad in (
		None,
		[],
		{**ok, "domain": "library.example.org"},  # an extra field is refused, not kept
		{k: v for k, v in ok.items() if k != "kind"},
		{**ok, "id": "not-a-uuid"},
		{**ok, "id": ID.replace("-4", "-1", 1)},  # not a random (version 4) id
		{**ok, "version": "v0.109"},
		{**ok, "edition": "other"},
		{**ok, "kind": "windows"},
		{**ok, "profiles": "school"},
		{**ok, "profiles": ["a"] * 13},
		{**ok, "profiles": ["Not Ok"]},
	):
		assert r.valid(bad) is None, bad


def test_a_note_is_due_after_four_weeks():
	today = date(2026, 11, 1)
	assert r.due(None, today)
	assert not r.due(datetime(2026, 10, 20, 9, 0), today)
	assert r.due(date(2026, 10, 4), today)


def test_the_count_only_includes_installs_heard_from_lately():
	today = date(2026, 11, 1)
	rows = [
		{
			"last_seen": date(2026, 10, 30),
			"version": "0.109.0",
			"edition": "standard",
			"kind": "docker",
			"profiles": "school,archive",
		},
		{
			"last_seen": date(2026, 10, 1),
			"version": "0.108.0",
			"edition": "standard",
			"kind": "linux",
			"profiles": "school",
		},
		{
			"last_seen": date(2026, 6, 1),
			"version": "0.100.0",
			"edition": "standard",
			"kind": "linux",
			"profiles": "portal",
		},
	]
	s = r.summarize(rows, today)
	assert (s["ever"], s["active"]) == (3, 2)
	assert s["versions"] == {"0.109.0": 1, "0.108.0": 1} and s["profiles"] == {"school": 2, "archive": 1}
