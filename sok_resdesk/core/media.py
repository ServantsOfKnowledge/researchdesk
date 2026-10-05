"""Audio and video: what files are playable, their transcripts as time-coded segments, captions.

A recording's transcript is kept as *pages* like a book's text (so search, proofreading with a
second person's validation, versions and citations all work), one **segment** per page, with the
segment's start and end seconds kept beside it. Segments come from a WebVTT or SRT file, or are laid
out blank (every minute, say) for people to transcribe. Pure Python (no Frappe), tested directly.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

# extension → (kind, content type): what a browser's player can be given
EXT = {
	".mp3": ("Audio", "audio/mpeg"),
	".m4a": ("Audio", "audio/mp4"),
	".aac": ("Audio", "audio/aac"),
	".ogg": ("Audio", "audio/ogg"),
	".oga": ("Audio", "audio/ogg"),
	".opus": ("Audio", "audio/ogg; codecs=opus"),
	".wav": ("Audio", "audio/wav"),
	".flac": ("Audio", "audio/flac"),
	".mp4": ("Video", "video/mp4"),
	".m4v": ("Video", "video/mp4"),
	".webm": ("Video", "video/webm"),
	".ogv": ("Video", "video/ogg"),
}
# the order a stem's files are offered in the player: what plays everywhere first
PREFERENCE = (
	".mp3",
	".m4a",
	".mp4",
	".webm",
	".ogg",
	".oga",
	".opus",
	".ogv",
	".aac",
	".wav",
	".flac",
	".m4v",
)
TRANSCRIPTS = (".vtt", ".srt")
POSTERS = (".jpg", ".jpeg", ".png")
WINDOW = 30  # seconds: cues are grouped into segments about this long
# Internet Archive's names for derivative formats, best first
IA_AUDIO = ("VBR MP3", "MP3", "128Kbps MP3", "64Kbps MP3", "Ogg Vorbis", "Flac", "WAVE")
IA_VIDEO = ("h.264", "MPEG4", "512Kb MPEG4", "h.264 HD", "Ogg Video", "WebM")


def ext_of(name: str) -> str:
	i = name.rfind(".")
	return name[i:].lower() if i >= 0 else ""


def is_media(name: str) -> bool:
	return ext_of(name) in EXT


def kind_of(name: str) -> str:
	return EXT.get(ext_of(name), ("", ""))[0]


def mime_of(name: str) -> str:
	return EXT.get(ext_of(name), ("", "application/octet-stream"))[1]


def stem_of(name: str) -> str:
	i = name.rfind(".")
	return name[:i] if i > 0 else name


def preferred(names: list[str]) -> list[str]:
	"""Media files of one recording, the one to play first first."""
	rank = {e: n for n, e in enumerate(PREFERENCE)}
	return sorted((n for n in names if is_media(n)), key=lambda n: (rank.get(ext_of(n), 99), n.lower()))


def media_id(rel_path: str) -> str:
	"""`talks/Ramesh 2019.mp3` → `av-talks-Ramesh-2019` (the folder and the name, without the extension)."""
	base = rel_path[: -len(ext_of(rel_path))] if is_media(rel_path) else rel_path
	return ("av-" + re.sub(r"[^\w.-]+", "-", base.strip("/"), flags=re.UNICODE).strip("-"))[:140]


def sidecar(raw: bytes | None, stem: str) -> tuple[dict, dict]:
	"""A recording's `<name>.json` → (details in IA's names, the recording's own fields).
	Keys: title, creator, date, language, description, subject, publisher, and `recording`:
	{speakers, place, recorded_on, consent}. Without one the file's name is the title."""
	try:
		data = json.loads(raw.decode("utf-8-sig")) if raw else {}
	except ValueError:
		data = {}
	data = data if isinstance(data, dict) else {}
	rec = data.pop("recording", None)
	rec = {f"rec_{k}": v for k, v in (rec or {}).items() if isinstance(v, (str, int, list))}
	if isinstance(rec.get("rec_speakers"), list):
		rec["rec_speakers"] = "\n".join(str(x) for x in rec["rec_speakers"])
	data.setdefault("title", re.sub(r"[_]+", " ", stem).strip() or stem)
	return data, rec


# -- time ---------------------------------------------------------------------------------------------


def fmt(seconds: float, ms: bool = False) -> str:
	"""`3725.5` → `1:02:05` (or `01:02:05.500` with ms, as WebVTT writes it)."""
	seconds = max(0.0, float(seconds or 0))
	h, rest = divmod(int(seconds), 3600)
	m, s = divmod(rest, 60)
	if ms:
		return f"{h:02d}:{m:02d}:{s:02d}.{int(round((seconds - int(seconds)) * 1000)) % 1000:03d}"
	return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def parse_time(text: str) -> float:
	"""`01:02:05.500`, `02:05,500` or `65` → seconds."""
	text = (text or "").strip().replace(",", ".")
	parts = text.split(":")
	try:
		secs = [float(p) for p in parts]
	except ValueError:
		return 0.0
	total = 0.0
	for p in secs:
		total = total * 60 + p
	return total


def length_of(value) -> float:
	"""A `length` the Internet Archive gives: seconds, or h:mm:ss."""
	return parse_time(str(value)) if value not in (None, "") else 0.0


# -- transcripts --------------------------------------------------------------------------------------

_TIME = re.compile(r"(\d+:)?(\d+):(\d+)[.,](\d+)\s*-->\s*(\d+:)?(\d+):(\d+)[.,](\d+)")
_TAG = re.compile(r"<[^>]+>")


def parse_cues(text: str) -> list[dict]:
	"""Cues of a WebVTT or SRT file: [{"start", "end", "text"}] in seconds."""
	text = (text or "").lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")
	cues = []
	for block in re.split(r"\n\s*\n", text):
		lines = [ln for ln in block.split("\n") if ln.strip()]
		for i, ln in enumerate(lines):
			m = _TIME.search(ln)
			if not m:
				continue
			t = ln.split("-->")
			body = " ".join(_TAG.sub("", x).strip() for x in lines[i + 1 :]).strip()
			if body:
				cues.append(
					{"start": parse_time(t[0].split()[-1]), "end": parse_time(t[1].split()[0]), "text": body}
				)
			break
	return cues


def segments(cues: list[dict], window: float = WINDOW) -> list[dict]:
	"""Cues grouped into segments of about `window` seconds, each with its start and end: the
	granularity of search hits and of a person's transcribing."""
	out: list[dict] = []
	cur: dict | None = None
	for c in cues:
		if cur is None:
			cur = {"start": c["start"], "end": c["end"], "text": c["text"]}
		else:
			cur["end"] = c["end"]
			cur["text"] += " " + c["text"]
		if cur["end"] - cur["start"] >= window and re.search(r"[.?!।॥”\"']\s*$", cur["text"]):
			out.append(cur)
			cur = None
	if cur:
		out.append(cur)
	return out


def blank_segments(duration: float, window: float = 60) -> list[dict]:
	"""Empty segments every `window` seconds over a recording, for people to transcribe."""
	window = max(10.0, float(window))
	n = int(-(-float(duration) // window)) if duration else 0
	return [
		{"start": i * window, "end": min(float(duration), (i + 1) * window), "text": ""} for i in range(n)
	]


def to_vtt(segs: list[dict], language: str = "") -> str:
	"""WebVTT captions from segments ({"start", "end", "text"}): the text is the transcript."""
	out = ["WEBVTT"]
	if language:
		out.append(f"Language: {language}")
	n = 0
	for s in segs:
		text = (s.get("text") or "").strip()
		if not text:
			continue
		n += 1
		out += ["", str(n), f"{fmt(s['start'], True)} --> {fmt(s['end'], True)}", text.replace("\n\n", "\n")]
	return "\n".join(out) + "\n"


def times_json(segs: list[dict]) -> str:
	"""Segments' times as stored: {"0": [start, end], …} (leaf → seconds)."""
	return json.dumps({str(i): [round(s["start"], 2), round(s["end"], 2)] for i, s in enumerate(segs)})


def times_from(raw) -> dict[int, tuple[float, float]]:
	try:
		data = json.loads(raw) if isinstance(raw, str) else (raw or {})
	except ValueError:
		return {}
	out = {}
	for k, v in data.items():
		try:
			out[int(k)] = (float(v[0]), float(v[1]))
		except (TypeError, ValueError, IndexError):
			continue
	return out


# -- probing a file -----------------------------------------------------------------------------------


def duration_of(path: str) -> float:
	"""Seconds a media file plays: from its own headers (mutagen, when installed) or ffprobe's;
	0 when neither can tell."""
	try:
		import mutagen

		f = mutagen.File(path)
		if f is not None and getattr(f, "info", None) and getattr(f.info, "length", 0):
			return float(f.info.length)
	except Exception:
		pass
	if path.lower().endswith(".wav"):  # plain WAV needs no library
		try:
			import wave

			with wave.open(path) as w:
				return w.getnframes() / float(w.getframerate() or 1)
		except Exception:
			pass
	if shutil.which("ffprobe"):
		try:
			done = subprocess.run(
				["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", path],
				capture_output=True,
				timeout=60,
			)
			return float(json.loads(done.stdout or b"{}").get("format", {}).get("duration") or 0)
		except Exception:
			return 0.0
	return 0.0


# -- the Internet Archive's files ---------------------------------------------------------------------


def ia_media(files: list[dict], mediatype: str) -> list[dict]:
	"""The playable derivatives among an IA item's files: [{"name", "format", "length"}] best first."""
	order = IA_VIDEO if mediatype == "movies" else IA_AUDIO
	found = []
	for f in files or []:
		name, fmt_name = f.get("name", ""), f.get("format", "")
		if fmt_name in order and is_media(name):
			found.append({"name": name, "format": fmt_name, "length": length_of(f.get("length"))})
	return sorted(found, key=lambda f: (order.index(f["format"]), f["name"]))


def ia_transcript_file(files: list[dict]) -> str:
	"""The WebVTT or SRT file of an IA item, if it has one."""
	for want in TRANSCRIPTS:
		for f in files or []:
			if f.get("name", "").lower().endswith(want):
				return f["name"]
	return ""
