"""Clients that send catalogue metadata to other systems. Pure Python (requests only).

  IAWriter        Internet Archive item metadata (Metadata Write API, JSON Patch)
  KohaClient      Koha REST API, /api/v1/biblios (Koha 23.11+), MARCXML
  WikidataClient  Wikibase action API: find by Internet Archive ID, create or complete items
  Webhook         POST JSON to any URL, signed with HMAC-SHA256

Each takes a `session` so tests can use a fake one. Nothing here touches Frappe.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time

import requests

USER_AGENT = "SoK-ResearchDesk/0.10 (+https://github.com/ServantsOfKnowledge/researchdesk)"


class PushError(Exception):
	pass


def payload_hash(payload) -> str:
	return hashlib.sha1(
		json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode()
	).hexdigest()


def _session(session=None, user_agent: str = USER_AGENT):
	s = session or requests.Session()
	s.headers.setdefault("User-Agent", user_agent)
	return s


# -- Internet Archive ------------------------------------------------------------------------------

IA_FIELDS = (
	"title",
	"alt_title",
	"creator",
	"alt_creator",
	"date",
	"publisher",
	"language",
	"subject",
	"description",
	"volume",
	"isbn",
	"licenseurl",
	"rights",
)


def _as_list(value) -> list:
	if value in (None, ""):
		return []
	return list(value) if isinstance(value, (list, tuple)) else [value]


def ia_patch(current: dict, desired: dict, fields=IA_FIELDS) -> list[dict]:
	"""JSON Patch turning the item's metadata on archive.org into ours.

	Only fields we have a value for are written; we never delete a field there. Lists are
	compared as lists (IA stores a single value as a string)."""
	ops = []
	for key in fields:
		want = desired.get(key)
		if want in (None, "", []):
			continue
		have = current.get(key)
		if isinstance(want, list) or isinstance(have, list):
			if [str(v) for v in _as_list(have)] == [str(v) for v in _as_list(want)]:
				continue
			value = want if len(_as_list(want)) > 1 else _as_list(want)[0]
		else:
			if str(have or "") == str(want):
				continue
			value = want
		ops.append({"op": "replace" if key in current else "add", "path": f"/{key}", "value": value})
	return ops


class IAWriter:
	METADATA = "https://archive.org/metadata/{id}"
	CHECK = "https://s3.us.archive.org/?check_auth=1"

	def __init__(self, access: str, secret: str, session=None):
		self.auth = f"LOW {access}:{secret}"
		self.session = _session(session)

	def check(self) -> str:
		r = self.session.get(self.CHECK, headers={"Authorization": self.auth}, timeout=30)
		data = r.json() if r.content else {}
		if r.status_code != 200 or not data.get("authorized"):
			raise PushError(
				f"Internet Archive keys not accepted ({r.status_code}): {data.get('error') or r.text[:200]}"
			)
		return data.get("username") or data.get("screenname") or "ok"

	def current(self, identifier: str) -> dict:
		r = self.session.get(self.METADATA.format(id=identifier), timeout=60)
		if r.status_code != 200 or not r.json().get("metadata"):
			raise PushError(f"{identifier}: not found on archive.org ({r.status_code})")
		return r.json()["metadata"]

	def write(self, identifier: str, patch: list[dict]) -> dict:
		r = self.session.post(
			self.METADATA.format(id=identifier),
			data={"-target": "metadata", "-patch": json.dumps(patch)},
			headers={"Authorization": self.auth},
			timeout=120,
		)
		data = r.json() if r.content else {}
		if r.status_code >= 400 or not data.get("success"):
			raise PushError(f"{identifier}: {data.get('error') or r.text[:300]}")
		return data


# -- Koha -------------------------------------------------------------------------------------------


class KohaClient:
	"""Koha REST API. Needs Koha 23.11 or later for POST/PUT /biblios with MARCXML.

	auth: ("basic", user, password) with the RESTBasicAuth system preference on, or
		  ("oauth", client_id, client_secret) with RESTOAuth2ClientCredentials on.
	"""

	def __init__(self, base_url: str, auth: tuple, framework: str = "", session=None):
		self.base = base_url.rstrip("/")
		self.api = self.base + "/api/v1"
		self.auth = auth
		self.framework = framework
		self.session = _session(session)
		self._token = None

	def _headers(self, extra: dict | None = None) -> dict:
		h = {"Accept": "application/json", **(extra or {})}
		if self.auth[0] == "oauth":
			if not self._token:
				r = self.session.post(
					f"{self.api}/oauth/token",
					timeout=30,
					data={
						"grant_type": "client_credentials",
						"client_id": self.auth[1],
						"client_secret": self.auth[2],
					},
				)
				if r.status_code != 200:
					raise PushError(f"Koha OAuth2 token refused ({r.status_code}): {r.text[:200]}")
				self._token = r.json()["access_token"]
			h["Authorization"] = f"Bearer {self._token}"
		return h

	def _kw(self) -> dict:
		return {"auth": (self.auth[1], self.auth[2])} if self.auth[0] == "basic" else {}

	def check(self) -> str:
		r = self.session.get(
			f"{self.api}/libraries",
			params={"_per_page": 1},
			headers=self._headers(),
			timeout=30,
			**self._kw(),
		)
		if r.status_code != 200:
			raise PushError(f"Koha answered {r.status_code}: {r.text[:200]}")
		return "ok"

	def _marc_headers(self) -> dict:
		h = {
			"Content-Type": "application/marcxml+xml",
			"x-record-schema": "MARC21",
			"x-confirm-not-duplicate": "1",
		}
		if self.framework:
			h["x-framework-id"] = self.framework
		return self._headers(h)

	def create(self, marcxml: str) -> str:
		r = self.session.post(
			f"{self.api}/biblios",
			data=marcxml.encode(),
			headers=self._marc_headers(),
			timeout=60,
			**self._kw(),
		)
		if r.status_code not in (200, 201):
			raise PushError(f"Koha create failed ({r.status_code}): {r.text[:300]}")
		data = r.json() if r.content else {}
		biblio_id = data.get("id") or data.get("biblio_id")
		if not biblio_id:
			raise PushError(f"Koha did not return a biblio id: {r.text[:200]}")
		return str(biblio_id)

	def update(self, biblio_id: str, marcxml: str) -> None:
		r = self.session.put(
			f"{self.api}/biblios/{biblio_id}",
			data=marcxml.encode(),
			headers=self._marc_headers(),
			timeout=60,
			**self._kw(),
		)
		if r.status_code == 404:
			raise PushError("gone")
		if r.status_code not in (200, 204):
			raise PushError(f"Koha update failed ({r.status_code}): {r.text[:300]}")


# -- Wikidata ---------------------------------------------------------------------------------------

LANG_QID = {  # ISO 639-3 -> Wikidata item for the language (checked against Wikidata)
	"kan": "Q33673",
	"eng": "Q1860",
	"hin": "Q1568",
	"tam": "Q5885",
	"tel": "Q8097",
	"mal": "Q36236",
	"mar": "Q1571",
	"san": "Q11059",
	"kok": "Q34239",
	"tcy": "Q34251",
	"urd": "Q1617",
	"ben": "Q9610",
	"guj": "Q5137",
	"pan": "Q58635",
	"ori": "Q33810",
	"ara": "Q13955",
	"fas": "Q9168",
	"fra": "Q150",
	"deu": "Q188",
}
LANG_CODE = {  # ISO 639-3 -> Wikimedia language code for labels and monolingual text
	"kan": "kn",
	"eng": "en",
	"hin": "hi",
	"tam": "ta",
	"tel": "te",
	"mal": "ml",
	"mar": "mr",
	"san": "sa",
	"kok": "gom",
	"tcy": "tcy",
	"urd": "ur",
	"ben": "bn",
	"guj": "gu",
	"pan": "pa",
	"ori": "or",
	"ara": "ar",
	"fas": "fa",
	"fra": "fr",
	"deu": "de",
}
EDITION = "Q3331189"  # version, edition or translation
P = {
	"instance": "P31",
	"title": "P1476",
	"author_string": "P2093",
	"date": "P577",
	"language": "P407",
	"ia": "P724",
	"ark": "P8091",
	"pages": "P1104",
	"url": "P953",
	"isbn13": "P212",
	"isbn10": "P957",
	"ref_url": "P854",
}


def _snak(prop: str, datatype: str, value) -> dict:
	return {"snaktype": "value", "property": prop, "datavalue": {"value": value, "type": datatype}}


def _claim(prop: str, datatype: str, value, ref_url: str = "") -> dict:
	c = {"mainsnak": _snak(prop, datatype, value), "type": "statement", "rank": "normal"}
	if ref_url:
		c["references"] = [{"snaks": {P["ref_url"]: [_snak(P["ref_url"], "string", ref_url)]}}]
	return c


def _item(qid: str) -> dict:
	return {"entity-type": "item", "numeric-id": int(qid[1:]), "id": qid}


def wikidata_entity(record: dict, portal_url: str = "") -> dict:
	"""Wikibase JSON for a digitised edition. Labels in the book's language and English."""
	lang = LANG_CODE.get(record.get("language") or "", "mul")
	title = (record.get("title") or record["item_id"])[:250]
	labels = {lang: {"language": lang, "value": title}}
	en = record.get("alt_title") if lang != "en" and record.get("alt_title") else title
	labels.setdefault("en", {"language": "en", "value": en[:250]})
	year = record.get("year")
	kind = (record.get("item_type") or "Book").lower()
	desc = " ".join(str(x) for x in (year, record.get("language_label"), kind) if x)
	src = record.get("source_url") or portal_url
	claims = [
		_claim(P["instance"], "wikibase-entityid", _item(EDITION), src),
		_claim(
			P["title"], "monolingualtext", {"text": title, "language": lang if lang != "mul" else "en"}, src
		),
	]
	for i, name in enumerate(record.get("creators") or []):
		c = _claim(P["author_string"], "string", name[:400], src)
		c["qualifiers"] = {"P1545": [_snak("P1545", "string", str(i + 1))]}  # series ordinal
		claims.append(c)
	if year:
		claims.append(
			_claim(
				P["date"],
				"time",
				{
					"time": f"+{int(year):04d}-00-00T00:00:00Z",
					"timezone": 0,
					"before": 0,
					"after": 0,
					"precision": 9,
					"calendarmodel": "http://www.wikidata.org/entity/Q1985727",
				},
				src,
			)
		)
	if LANG_QID.get(record.get("language") or ""):
		claims.append(_claim(P["language"], "wikibase-entityid", _item(LANG_QID[record["language"]]), src))
	if record.get("on_archive_org", record.get("source") == "Internet Archive"):
		claims.append(_claim(P["ia"], "string", record["item_id"]))
	if record.get("ark"):
		claims.append(_claim(P["ark"], "string", record["ark"]))
	if record.get("page_count"):
		claims.append(
			_claim(P["pages"], "quantity", {"amount": f"+{int(record['page_count'])}", "unit": "1"}, src)
		)
	if portal_url:
		claims.append(_claim(P["url"], "string", portal_url))
	isbn = "".join(ch for ch in record.get("isbn") or "" if ch.isdigit() or ch in "Xx")
	if len(isbn) in (10, 13):
		claims.append(_claim(P["isbn13"] if len(isbn) == 13 else P["isbn10"], "string", record["isbn"]))
	data = {"labels": labels, "claims": claims}
	if desc:
		data["descriptions"] = {
			"en": {"language": "en", "value": f"{desc} digitised by Servants of Knowledge"[:250]}
		}
	return data


class WikidataClient:
	def __init__(self, api_url: str, username: str, password: str, session=None, maxlag: int = 5):
		self.api = api_url
		self.username, self.password = username, password
		self.session = _session(session, USER_AGENT)
		self.maxlag = maxlag
		self._csrf = None

	def _get(self, **params) -> dict:
		r = self.session.get(self.api, params={"format": "json", **params}, timeout=60)
		return r.json()

	def _post(self, **data) -> dict:
		for attempt in range(5):
			r = self.session.post(
				self.api, data={"format": "json", "maxlag": self.maxlag, **data}, timeout=120
			)
			out = r.json()
			if out.get("error", {}).get("code") == "maxlag":
				time.sleep(5 * (attempt + 1))
				continue
			return out
		raise PushError("Wikidata is busy (maxlag); try again later")

	def login(self) -> str:
		token = self._get(action="query", meta="tokens", type="login")["query"]["tokens"]["logintoken"]
		out = self._post(action="login", lgname=self.username, lgpassword=self.password, lgtoken=token)
		if out.get("login", {}).get("result") != "Success":
			raise PushError(f"Wikidata login failed: {out.get('login', {}).get('reason') or out}")
		self._csrf = self._get(action="query", meta="tokens")["query"]["tokens"]["csrftoken"]
		return out["login"].get("lgusername", self.username)

	def find_by_ia(self, identifier: str) -> str | None:
		out = self._get(
			action="query", list="search", srsearch=f"haswbstatement:{P['ia']}={identifier}", srlimit=2
		)
		hits = out.get("query", {}).get("search", [])
		return hits[0]["title"] if hits else None

	def entity(self, qid: str) -> dict:
		return self._get(action="wbgetentities", ids=qid, props="claims|labels")["entities"][qid]

	def create(self, data: dict, summary: str) -> str:
		out = self._post(
			action="wbeditentity", new="item", data=json.dumps(data), token=self._csrf, summary=summary, bot=1
		)
		if "error" in out:
			raise PushError(f"Wikidata: {out['error'].get('info')}")
		return out["entity"]["id"]

	def add_missing(self, qid: str, data: dict, summary: str) -> int:
		"""Add statements for properties the item doesn't have yet. Never changes existing ones."""
		have = set(self.entity(qid).get("claims", {}))
		missing = [c for c in data["claims"] if c["mainsnak"]["property"] not in have]
		if not missing:
			return 0
		out = self._post(
			action="wbeditentity",
			id=qid,
			data=json.dumps({"claims": missing}),
			token=self._csrf,
			summary=summary,
			bot=1,
		)
		if "error" in out:
			raise PushError(f"Wikidata: {out['error'].get('info')}")
		return len(missing)


# -- Webhook ----------------------------------------------------------------------------------------


class Webhook:
	def __init__(self, url: str, secret: str = "", session=None):
		self.url, self.secret = url, secret
		self.session = _session(session)

	def send(self, event: str, payload: dict) -> int:
		body = json.dumps(
			{"event": event, "sent_at": int(time.time()), "data": payload}, ensure_ascii=False
		).encode()
		headers = {"Content-Type": "application/json", "X-ResDesk-Event": event}
		if self.secret:
			headers["X-ResDesk-Signature"] = (
				"sha256=" + hmac.new(self.secret.encode(), body, hashlib.sha256).hexdigest()
			)
		r = self.session.post(self.url, data=body, headers=headers, timeout=30)
		if r.status_code >= 400:
			raise PushError(f"webhook answered {r.status_code}: {r.text[:200]}")
		return r.status_code
