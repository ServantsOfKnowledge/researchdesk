"""0.63: machine drafts: engines, parsing, filling segments, never over a person's work."""

import json

import pytest

from sok_resdesk.core import draft


def test_whisper_json_gives_cues_without_empty_ones():
	raw = json.dumps(
		{"segments": [{"start": 0, "end": 2.5, "text": " ನಮಸ್ಕಾರ "}, {"start": 3, "end": 4, "text": "  "}]}
	)
	assert draft.parse_whisper_json(raw) == [{"start": 0.0, "end": 2.5, "text": "ನಮಸ್ಕಾರ"}]
	with pytest.raises(draft.DraftError):
		draft.parse_whisper_json("not json")


def test_cues_fill_the_slots_they_begin_in():
	cues = [
		{"start": 1, "end": 4, "text": "one"},
		{"start": 58, "end": 63, "text": "two"},
		{"start": 61, "end": 70, "text": "three"},
	]
	assert draft.fill_segments([(0, 60), (60, 120), (120, 180)], cues) == ["one two", "three", ""]


def test_a_person_s_work_is_never_overwritten():
	assert draft.may_draft(None) and draft.may_draft("Machine")
	assert not draft.may_draft("Proofread") and not draft.may_draft("Validated")


def test_kraken_needs_a_model_file_and_builds_its_command(tmp_path):
	assert draft.kraken_command("a.png", "o.txt", "m.mlmodel")[-2:] == ["-m", "m.mlmodel"]
	with pytest.raises(draft.DraftError, match="model file"):
		draft.kraken_read(str(tmp_path / "a.png"), str(tmp_path / "none.mlmodel"))


def test_no_engine_says_what_to_install(monkeypatch):
	monkeypatch.setattr(draft, "asr_engine", lambda: "")
	with pytest.raises(draft.DraftError, match="install"):
		draft.transcribe("x.mp3")
