"""Machine drafts of transcripts: speech to text for recordings, handwriting recognition for
manuscript leaves. Both are *drafts*: a person corrects them (proofreading), and nothing here
ever replaces a person's work. The engines are optional and run on the library's own server:

* speech: ``faster-whisper`` (Python) or the ``whisper`` command;
* handwriting: ``kraken`` (with a model file), or Tesseract through the re-OCR code.

Pure Python (no Frappe), so it is unit-tested directly.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile

HUMAN = ("Proofread", "Validated")
ASR_ENGINES = ("faster-whisper", "whisper")
TIMEOUT = 6 * 3600


class DraftError(Exception):
	pass


def asr_engine() -> str:
	"""Which speech engine this server has ('' when none)."""
	try:
		import faster_whisper  # noqa: F401

		return "faster-whisper"
	except ImportError:
		pass
	return "whisper" if shutil.which("whisper") else ""


def htr_engines() -> list[str]:
	"""Handwriting engines this server has: 'tesseract' and/or 'kraken'."""
	return [e for e in ("tesseract", "kraken") if shutil.which(e)]


def parse_whisper_json(raw: str) -> list[dict]:
	"""[{start, end, text}] from the whisper command's JSON (empty segments dropped)."""
	try:
		data = json.loads(raw)
	except ValueError as e:
		raise DraftError("whisper's output is not JSON") from e
	out = []
	for s in data.get("segments") or []:
		text = (s.get("text") or "").strip()
		if text:
			out.append({"start": float(s.get("start", 0)), "end": float(s.get("end", 0)), "text": text})
	return out


def transcribe(path: str, language: str = "", model: str = "small") -> list[dict]:
	"""Speech to text: cues [{start, end, text}] for the audio or video file."""
	engine = asr_engine()
	if not engine:
		raise DraftError("No speech engine on this server: install faster-whisper (pip) or whisper.")
	lang = (language or "").strip().lower()[:3]
	lang = {"kan": "kn", "hin": "hi", "san": "sa", "tam": "ta", "tel": "te", "mal": "ml", "eng": "en"}.get(
		lang, lang
	)
	if engine == "faster-whisper":
		from faster_whisper import WhisperModel

		m = WhisperModel(model, compute_type="int8")
		segments, _info = m.transcribe(path, language=lang or None)
		return [
			{"start": float(s.start), "end": float(s.end), "text": s.text.strip()}
			for s in segments
			if s.text.strip()
		]
	with tempfile.TemporaryDirectory() as out:
		cmd = ["whisper", path, "--model", model, "--output_format", "json", "--output_dir", out]
		if lang:
			cmd += ["--language", lang]
		try:
			subprocess.run(cmd, check=True, capture_output=True, timeout=TIMEOUT)
		except (subprocess.SubprocessError, OSError) as e:
			raise DraftError(f"whisper failed: {e}") from e
		name = os.path.splitext(os.path.basename(path))[0] + ".json"
		with open(os.path.join(out, name), encoding="utf-8") as f:
			return parse_whisper_json(f.read())


def fill_segments(slots: list[tuple[float, float]], cues: list[dict]) -> list[str]:
	"""The text for each (start, end) slot: the cues that begin inside it, in order."""
	out = []
	for start, end in slots:
		words = [c["text"] for c in cues if start <= c["start"] < end]
		out.append(" ".join(words).strip())
	return out


def kraken_command(image: str, out_txt: str, model: str) -> list[str]:
	"""The kraken command that reads one leaf with a recognition model file."""
	return ["kraken", "-i", image, out_txt, "binarize", "segment", "-bl", "ocr", "-m", model]


def kraken_read(image: str, model: str) -> str:
	if not model or not os.path.isfile(model):
		raise DraftError("Kraken needs a recognition model file: set its path in Settings → Machine Drafts.")
	with tempfile.TemporaryDirectory() as tmp:
		out = os.path.join(tmp, "leaf.txt")
		try:
			subprocess.run(kraken_command(image, out, model), check=True, capture_output=True, timeout=1800)
		except (subprocess.SubprocessError, OSError) as e:
			raise DraftError(f"kraken failed: {e}") from e
		with open(out, encoding="utf-8") as f:
			return f.read().strip()


def may_draft(status: str | None) -> bool:
	"""A page may get a machine draft when nobody has worked on it: no version yet, or only a
	machine one. Never over a person's work."""
	return status not in HUMAN
