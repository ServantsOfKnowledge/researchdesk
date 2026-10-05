"""Deposit: the parts that need no Frappe (what files may come in, names, checks, the folder store).

A deposited work becomes an IA-style item folder (``<id>/<id>_meta.xml`` and its files) under the
library's deposit folder, so the rest of Research Desk (catalogue, PDF text, OCR, search, downloads,
access, preservation) treats it like any book in a folder. See sok_resdesk/deposit.py.
"""

from __future__ import annotations

import difflib
import hashlib
import os
import re

from sok_resdesk.core.folder import META_SUFFIX, FolderStore

# document formats a person may deposit (other kinds of file come with later releases)
ALLOWED = (
	".pdf",
	".epub",
	".mobi",
	".azw3",
	".docx",
	".odt",
	".rtf",
	".txt",
	".csv",
	".xlsx",
	".zip",
)
DEFAULT_MAX_MB = 1024
LICENCE_URLS = {
	"CC0-1.0": "https://creativecommons.org/publicdomain/zero/1.0/",
	"CC-BY-4.0": "https://creativecommons.org/licenses/by/4.0/",
	"CC-BY-SA-4.0": "https://creativecommons.org/licenses/by-sa/4.0/",
	"CC-BY-NC-4.0": "https://creativecommons.org/licenses/by-nc/4.0/",
}


def extension(name: str) -> str:
	return os.path.splitext(name or "")[1].lower()


def file_problem(name: str, size: int, max_mb: int = DEFAULT_MAX_MB) -> str:
	"""'' when a file may be deposited, else why not."""
	if extension(name) not in ALLOWED:
		return f"{name}: only {', '.join(e.lstrip('.') for e in ALLOWED)} files can be deposited"
	if size <= 0:
		return f"{name} is empty"
	if size > max_mb << 20:
		return f"{name} is {size >> 20} MB: the limit is {max_mb} MB a file"
	return ""


def safe_name(name: str, taken: set[str]) -> str:
	"""A file name that is safe on any system and not yet used in the folder."""
	stem, ext = os.path.splitext(os.path.basename(name or "file"))
	stem = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "_", stem).strip(" .") or "file"
	out = f"{stem[:100]}{ext.lower()}"
	n = 1
	while out.lower() in taken or out.endswith(META_SUFFIX):
		n += 1
		out = f"{stem[:100]}-{n}{ext.lower()}"
	taken.add(out.lower())
	return out


def sha256_of(path: str) -> str:
	h = hashlib.sha256()
	with open(path, "rb") as f:
		for block in iter(lambda: f.read(1 << 20), b""):
			h.update(block)
	return h.hexdigest()


def lines(text: str) -> list[str]:
	"""A box of one-per-line values as a clean list (no blanks, no repeats)."""
	return list(dict.fromkeys(x.strip() for x in (text or "").splitlines() if x.strip()))


def _norm(title: str) -> str:
	return re.sub(r"\W+", " ", (title or "").lower(), flags=re.UNICODE).strip()


def similar_title(title: str, existing: list[str], at_least: float = 0.9) -> str:
	"""The existing title that reads like `title`, or ''."""
	mine = _norm(title)
	for other in existing:
		if mine and difflib.SequenceMatcher(None, mine, _norm(other)).ratio() >= at_least:
			return other
	return ""


class DepositStore(FolderStore):
	"""The deposit folder: every item folder's files are what a reader may download."""

	kind = "deposit"

	def downloads(self, loc: str) -> list[str]:
		return [f for f in self.list_files(loc) if extension(f) in ALLOWED]
