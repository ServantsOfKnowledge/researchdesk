"""Page text from a PDF's text layer (born-digital PDFs, and scans a repository already OCR'd).

Pure Python on pypdf (which Frappe ships). A PDF whose pages have next to no text is a scan
without OCR: ``has_text_layer`` says so, and the caller decides what to do (0.40: OCR it).
"""

from __future__ import annotations

import io
import re

MIN_CHARS_PER_PAGE = 20  # less than this on most pages: the text layer is missing or empty


def pages_from_pdf(data: bytes | str, max_pages: int = 5000) -> list[dict]:
	"""[{leaf, label, text}] for each page (leaf counts from 0, as page images do; label is the
	printed page number the PDF gives, if any). Empty pages are kept, so leaves stay in step
	with the PDF's pages."""
	from pypdf import PdfReader

	reader = PdfReader(data if isinstance(data, str) else io.BytesIO(data))  # a path, or the bytes
	try:
		labels = list(reader.page_labels)
	except Exception:
		labels = []
	out = []
	for n, page in enumerate(reader.pages):
		if n >= max_pages:
			break
		try:
			text = page.extract_text() or ""
		except Exception:  # one damaged page doesn't lose the book
			text = ""
		label = labels[n] if n < len(labels) else ""
		out.append({"leaf": n, "label": "" if label == str(n + 1) else label, "text": tidy(text)})
	return out


def tidy(text: str) -> str:
	"""Text-layer text as readers want it: words hyphenated across lines joined, runs of spaces
	and blank lines closed up."""
	text = text.replace("\r", "\n").replace("\x00", "")
	text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
	text = re.sub(r"[ \t ]+", " ", text)
	text = re.sub(r" *\n *", "\n", text)
	return re.sub(r"\n{3,}", "\n\n", text).strip()


def has_text_layer(pages: list[dict]) -> bool:
	"""Whether most pages carry text (a scan with no OCR has none, or a stray header)."""
	if not pages:
		return False
	with_text = sum(1 for p in pages if len(p["text"]) >= MIN_CHARS_PER_PAGE)
	return with_text >= max(1, len(pages) // 2)


def page_count(data: bytes) -> int:
	from pypdf import PdfReader

	return len(PdfReader(io.BytesIO(data)).pages)
