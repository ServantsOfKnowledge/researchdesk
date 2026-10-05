"""0.57: audio and video: formats, time, transcripts as segments, captions (no Frappe)."""

import struct
import wave

from sok_resdesk.core import media as m

VTT = """WEBVTT

1
00:00:01.000 --> 00:00:04.500
<v Speaker>Namaskara. This is the first line.</v>

2
00:00:05.000 --> 00:00:31.200
The second line goes on for a while and ends here.

00:00:32.000 --> 00:00:40.000
A cue without a number
across two lines.
"""
SRT = """1
00:00:01,000 --> 00:00:04,500
First line.

2
00:01:05,250 --> 00:01:09,000
Second line.
"""


def test_what_is_playable_and_in_what_order():
	assert m.kind_of("a.MP3") == "Audio" and m.kind_of("a.webm") == "Video" and m.kind_of("a.pdf") == ""
	assert m.mime_of("x.m4a") == "audio/mp4"
	assert m.preferred(["z.wav", "z.ogg", "z.mp3", "z.txt"]) == ["z.mp3", "z.ogg", "z.wav"]
	assert m.stem_of("talk 1.final.mp3") == "talk 1.final"


def test_time_both_ways():
	assert m.fmt(65) == "1:05" and m.fmt(3725.5) == "1:02:05" and m.fmt(3725.5, True) == "01:02:05.500"
	assert (
		m.parse_time("01:02:05.500") == 3725.5
		and m.parse_time("02:05,250") == 125.25
		and m.parse_time("65") == 65
	)
	assert m.parse_time("nonsense") == 0 and m.length_of("1:30") == 90 and m.length_of("") == 0


def test_cues_from_vtt_and_srt():
	cues = m.parse_cues(VTT)
	assert [(c["start"], c["end"]) for c in cues] == [(1.0, 4.5), (5.0, 31.2), (32.0, 40.0)]
	assert cues[0]["text"] == "Namaskara. This is the first line."  # speaker tags go
	assert cues[2]["text"] == "A cue without a number across two lines."
	srt = m.parse_cues(SRT)
	assert srt[1] == {"start": 65.25, "end": 69.0, "text": "Second line."}
	assert m.parse_cues("") == [] and m.parse_cues("WEBVTT\n\nNOTE nothing") == []


def test_cues_are_grouped_into_segments_that_end_on_a_sentence():
	segs = m.segments(m.parse_cues(VTT), window=30)
	assert len(segs) == 2
	assert (segs[0]["start"], segs[0]["end"]) == (1.0, 31.2) and segs[0]["text"].endswith("ends here.")
	assert segs[1]["text"].startswith("A cue without")  # the rest, however short
	assert m.segments([]) == []


def test_blank_segments_cover_the_whole_recording():
	segs = m.blank_segments(150, 60)
	assert [(s["start"], s["end"]) for s in segs] == [(0, 60), (60, 120), (120, 150)]
	assert m.blank_segments(0) == [] and m.blank_segments(100, 1)[0]["end"] == 10  # never finer than 10 s


def test_captions_are_webvtt_of_the_segments_with_text():
	segs = [
		{"start": 0, "end": 5, "text": "One"},
		{"start": 5, "end": 9, "text": ""},
		{"start": 9, "end": 12.5, "text": "Three"},
	]
	vtt = m.to_vtt(segs, "kan")
	assert vtt.startswith("WEBVTT\nLanguage: kan\n")
	assert "00:00:09.000 --> 00:00:12.500\nThree" in vtt and vtt.count("-->") == 2
	assert m.parse_cues(vtt)[1]["text"] == "Three"  # and it reads back


def test_times_are_stored_and_read_back():
	segs = [{"start": 0, "end": 60.004}, {"start": 60, "end": 90}]
	assert m.times_from(m.times_json(segs)) == {0: (0.0, 60.0), 1: (60.0, 90.0)}
	assert m.times_from("not json") == {} and m.times_from(None) == {}


def test_the_length_of_a_wav_file(tmp_path):
	path = tmp_path / "t.wav"
	with wave.open(str(path), "wb") as w:
		w.setnchannels(1)
		w.setsampwidth(2)
		w.setframerate(8000)
		w.writeframes(struct.pack("<h", 0) * 16000)  # two seconds
	assert round(m.duration_of(str(path))) == 2
	assert m.duration_of(str(tmp_path / "missing.mp3")) == 0


def test_the_internet_archives_playable_files():
	files = [
		{"name": "t.mp3", "format": "VBR MP3", "length": "125.5"},
		{"name": "t_64kb.mp3", "format": "64Kbps MP3", "length": "125.5"},
		{"name": "t.ogg", "format": "Ogg Vorbis"},
		{"name": "t_spectrogram.png", "format": "PNG"},
		{"name": "t.vtt", "format": "WebVTT"},
	]
	got = m.ia_media(files, "audio")
	assert [f["name"] for f in got] == ["t.mp3", "t_64kb.mp3", "t.ogg"] and got[0]["length"] == 125.5
	assert (
		m.ia_media(
			[{"name": "v.mp4", "format": "h.264"}, {"name": "v.ogv", "format": "Ogg Video"}], "movies"
		)[0]["name"]
		== "v.mp4"
	)
	assert m.ia_transcript_file(files) == "t.vtt" and m.ia_transcript_file([]) == ""


def test_an_archive_org_recording_is_catalogued_with_its_playable_files():
	from sok_resdesk.core.normalize import normalize_ia_item

	meta = {
		"mediatype": "audio",
		"title": "Harikatha",
		"creator": "Someone",
		"language": "kan",
		"length": "1:05:30",
	}
	files = [
		{"name": "h.mp3", "format": "VBR MP3", "length": "3930.2"},
		{"name": "h.ogg", "format": "Ogg Vorbis", "length": "3930.2"},
		{"name": "h_spectrogram.png", "format": "PNG"},
	]
	r = normalize_ia_item("harikatha-1", meta, files)
	assert (r["item_type"], r["duration"]) == ("Audio", 3930)
	assert r["media_files"].splitlines() == ["h.mp3|VBR MP3|3930", "h.ogg|Ogg Vorbis|3930"]
	assert not r["has_page_text"]
	video = normalize_ia_item(
		"v1", {"mediatype": "movies", "title": "V"}, [{"name": "v.mp4", "format": "h.264", "length": "60"}]
	)
	assert video["item_type"] == "Video" and video["duration"] == 60
	assert normalize_ia_item("b1", {"mediatype": "texts", "title": "B"}, [])["media_files"] == ""


def test_the_media_option_widens_the_archive_org_search():
	from sok_resdesk.core.ia import IAClient

	assert IAClient.build_query("Collection", collection="x").endswith("mediatype:(texts)")
	assert "audio OR movies" in IAClient.build_query("Collection", collection="x", media=True)
