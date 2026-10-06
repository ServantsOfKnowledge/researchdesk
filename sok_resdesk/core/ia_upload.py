"""Giving a book to the Internet Archive: the identifier, the upload headers and what stops it.

archive.org takes an upload as plain HTTP PUTs to its S3-like endpoint: the first file makes the
item and carries its details as ``x-archive-meta…`` headers; later files are added to it. What
goes is always public: Research Desk never makes a dark or hidden item. Pure Python (no Frappe),
so it is unit-tested directly; sok_resdesk/archive_upload.py does the sending.
"""

from __future__ import annotations

import re
import unicodedata
from urllib.parse import quote

DEFAULT_COLLECTION = "opensource"  # archive.org's community collection for texts
MAX_IDENTIFIER = 100
_ID_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,99}$")
_COLLECTION_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
MEDIATYPES = {"texts": "texts", "audio": "audio", "movies": "movies", "image": "image"}
# the media type archive.org files an item under, from a kind of file
EXT_TYPE = {
	".pdf": "texts",
	".epub": "texts",
	".mobi": "texts",
	".azw3": "texts",
	".docx": "texts",
	".odt": "texts",
	".rtf": "texts",
	".txt": "texts",
	".djvu": "texts",
	".mp3": "audio",
	".ogg": "audio",
	".wav": "audio",
	".flac": "audio",
	".mp4": "movies",
	".webm": "movies",
	".jpg": "image",
	".jpeg": "image",
	".png": "image",
	".tif": "image",
	".tiff": "image",
}


def clean_identifier(value: str) -> str:
	"""An identifier archive.org accepts: letters, digits, dots, hyphens and underscores."""
	text = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode()
	text = re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-._")
	return text[:MAX_IDENTIFIER].strip("-._")


def make_identifier(title: str, year=None, creator: str = "", suffix: str = "") -> str:
	"""A readable identifier from the title (a title in another script falls back to the suffix)."""
	parts = [clean_identifier(title)[:60]]
	if creator:
		parts.append(clean_identifier(creator.split(",")[0])[:20])
	if year:
		parts.append(str(year))
	if suffix:
		parts.append(clean_identifier(suffix))
	return clean_identifier("-".join(p for p in parts if p))


def identifier_problem(value: str) -> str:
	if not _ID_OK.match(value or ""):
		return (
			"The archive.org identifier is 3 to 100 characters: letters, digits, dots, hyphens and "
			"underscores, starting with a letter or digit."
		)
	return ""


def collection_problem(value: str) -> str:
	if not _COLLECTION_OK.match(value or ""):
		return "The collection is the identifier of an archive.org collection you may add to."
	return ""


def mediatype(names: list[str]) -> str:
	"""texts, audio, movies or image: that of the first file archive.org would recognise."""
	import os

	for n in names:
		kind = EXT_TYPE.get(os.path.splitext(n)[1].lower())
		if kind:
			return kind
	return "texts"


def header_value(value) -> str:
	"""A header value; text outside ASCII goes the way archive.org asks, as uri(…)."""
	text = " ".join(str(value).split())
	try:
		text.encode("ascii")
		return text
	except UnicodeEncodeError:
		return f"uri({quote(text, safe='')})"


def metadata_headers(
	*,
	title: str,
	collection: str,
	mediatype_: str = "texts",
	creators: list[str] | None = None,
	date: str = "",
	language: str = "",
	description: str = "",
	subjects: list[str] | None = None,
	licence_url: str = "",
	publisher: str = "",
	source_url: str = "",
) -> dict[str, str]:
	"""x-archive-meta… headers for the first PUT. Repeated fields are numbered (meta01-, meta02-…)."""
	h = {
		"x-archive-auto-make-bucket": "1",
		"x-archive-queue-derive": "1",
		"x-archive-meta-mediatype": mediatype_,
		"x-archive-meta-collection": collection,
		"x-archive-meta-title": header_value(title),
	}
	single = {
		"date": date,
		"language": language,
		"description": description,
		"licenseurl": licence_url,
		"publisher": publisher,
		"source": source_url,
	}
	for key, value in single.items():
		if value:
			h[f"x-archive-meta-{key}"] = header_value(value)
	for key, values in (("creator", creators or []), ("subject", subjects or [])):
		for i, v in enumerate([x for x in values if (x or "").strip()], 1):
			h[f"x-archive-meta{i:02d}-{key}"] = header_value(v)
	return h


def file_name(name: str) -> str:
	"""A file name that is safe in the item's address."""
	import os

	stem, ext = os.path.splitext(os.path.basename(name or "file"))
	stem = re.sub(r"[^\w.-]+", "_", stem, flags=re.UNICODE).strip("._") or "file"
	return f"{stem[:120]}{ext.lower()}"
