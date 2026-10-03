"""DOIs from DataCite for chosen collections: the record DataCite keeps for each book. Pure Python.

A DOI (https://doi.org/10.…) is the identifier journals, repositories and citation indexes
expect. A library that is a DataCite member (directly or through a consortium) can give the
books of chosen collections DOIs. Each DOI points at the book's permanent link on the portal and
carries the book's metadata in the DataCite schema (4.5), sent through DataCite's REST API
(JSON:API); when the catalogue record changes, the metadata is sent again.

DOIs can't be deleted once findable: a book that leaves the catalogue keeps its DOI, which then
points at the page saying what happened to it (its tombstone).
"""

from __future__ import annotations

import hashlib
import json
import re

from sok_resdesk.core.citations import split_name

PREFIX = re.compile(r"^10\.\d{4,9}$")
SUFFIX_SAFE = re.compile(r"[^a-z0-9._-]+")
PRODUCTION = "https://api.datacite.org"
TEST = "https://api.test.datacite.org"
# the catalogue's document types → DataCite resourceTypeGeneral
RESOURCE_TYPES = {
	"Book": "Book",
	"Periodical": "Journal",
	"Article": "JournalArticle",
	"Thesis": "Dissertation",
	"Report": "Report",
	"Manuscript": "Text",
	"Map": "Image",
	"Other": "Text",
}


class DataCiteError(ValueError):
	pass


def check_prefix(prefix: str) -> str:
	prefix = (prefix or "").strip()
	if not PREFIX.match(prefix):
		raise DataCiteError(
			f"{prefix or 'The prefix'} is not a DOI prefix (10. and 4 to 9 digits, e.g. 10.12345)"
		)
	return prefix


def suffix_for(item_id: str, shoulder: str = "") -> str:
	"""The DOI's suffix for a book: the shoulder and its identifier, in safe lower case
	(DOIs are case-insensitive; DataCite keeps them upper case)."""
	raw = f"{shoulder or ''}{item_id}".lower()
	out = SUFFIX_SAFE.sub("-", raw).strip("-.")
	if not out:
		raise DataCiteError("The book has no identifier to make a DOI from")
	return out[:200]


def doi_for(prefix: str, item_id: str, shoulder: str = "") -> str:
	return f"{check_prefix(prefix)}/{suffix_for(item_id, shoulder)}".upper()


def doi_url(doi: str) -> str:
	return f"https://doi.org/{doi}"


def _creators(record: dict) -> list[dict]:
	out = []
	for name in record.get("creators") or []:
		if not name:
			continue
		family, given = split_name(name)
		person = {"name": f"{family}, {given}" if given else family, "nameType": "Personal"}
		if given:
			person.update({"givenName": given, "familyName": family})
		out.append(person)
	return out or [{"name": ":unav", "nameType": "Organizational"}]


def attributes(record: dict, url: str, publisher: str, year_now: int) -> dict:
	"""The book's DataCite metadata (schema 4.5 attributes, without doi/event)."""
	titles = [{"title": record.get("title") or record["item_id"]}]
	if record.get("alt_title") and record["alt_title"] != record.get("title"):
		titles.append({"title": record["alt_title"], "titleType": "TranslatedTitle"})
	year = record.get("year")
	kind = record.get("item_type") or "Book"
	attrs = {
		"creators": _creators(record),
		"titles": titles,
		"publisher": {"name": publisher or "Research Desk"},
		"publicationYear": int(year) if year else int(year_now),
		"types": {"resourceTypeGeneral": RESOURCE_TYPES.get(kind, "Text"), "resourceType": kind},
		"url": url,
		"schemaVersion": "http://datacite.org/schema/kernel-4",
		"alternateIdentifiers": [
			{
				"alternateIdentifier": record["item_id"],
				"alternateIdentifierType": "Internet Archive identifier",
			}
		],
	}
	if record.get("persistent_id"):
		attrs["alternateIdentifiers"].append(
			{"alternateIdentifier": record["persistent_id"], "alternateIdentifierType": "ARK"}
		)
	if record.get("language"):
		attrs["language"] = record["language"]
	if record.get("subjects"):
		attrs["subjects"] = [{"subject": s} for s in record["subjects"][:50]]
	if record.get("description"):
		attrs["descriptions"] = [{"description": record["description"][:5000], "descriptionType": "Abstract"}]
	if record.get("licence_url"):
		attrs["rightsList"] = [{"rightsUri": record["licence_url"]}]
	elif record.get("rights"):
		attrs["rightsList"] = [{"rights": record["rights"][:500]}]
	if record.get("page_count"):
		attrs["sizes"] = [f"{record['page_count']} pages"]
	if year:
		attrs["dates"] = [{"date": str(year), "dateType": "Issued"}]
	if record.get("publisher"):  # the original publisher; the DOI's publisher is the library
		attrs.setdefault("contributors", []).append(
			{"name": record["publisher"], "nameType": "Organizational", "contributorType": "Other"}
		)
	if record.get("on_archive_org", True) and record.get("source") in (None, "", "Internet Archive"):
		attrs["relatedIdentifiers"] = [
			{
				"relatedIdentifier": f"https://archive.org/details/{record['item_id']}",
				"relatedIdentifierType": "URL",
				"relationType": "IsVariantFormOf",
			}
		]
	return attrs


def fingerprint(attrs: dict) -> str:
	"""Changes when the metadata DataCite holds would change (to send it again only then)."""
	return hashlib.sha256(json.dumps(attrs, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:32]


def payload(doi: str, attrs: dict, event: str | None = "publish") -> dict:
	"""The JSON:API document to PUT (create or update) or POST to DataCite."""
	body = {"data": {"id": doi, "type": "dois", "attributes": {"doi": doi, **attrs}}}
	if event:
		body["data"]["attributes"]["event"] = event
	return body


def error_text(data) -> str:
	"""DataCite's error answer as one line."""
	try:
		errors = data.get("errors") or []
		return (
			"; ".join(f"{e.get('source', '')}: {e.get('title', '')}".strip(": ") for e in errors)
			or str(data)[:300]
		)
	except Exception:
		return str(data)[:300]
