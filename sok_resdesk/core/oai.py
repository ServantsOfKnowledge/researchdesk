"""OAI-PMH 2.0 data provider (protocol logic only).

Koha, DSpace, VuFind, BASE, CORE and most aggregators can harvest this. The
storage side is injected as a `Store`, so the protocol is tested without
Frappe. Metadata formats: oai_dc and marc21 (MARCXML).

Spec: https://www.openarchives.org/OAI/openarchivesprotocol.html
"""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from typing import Protocol
from xml.sax.saxutils import escape

from .citations import url_for
from .marc import MARC_NS, to_marcxml_record

PAGE_SIZE = 100

FORMATS = {
	"oai_dc": (
		"http://www.openarchives.org/OAI/2.0/oai_dc.xsd",
		"http://www.openarchives.org/OAI/2.0/oai_dc/",
	),
	"marc21": ("http://www.loc.gov/standards/marcxml/schema/MARC21slim.xsd", MARC_NS),
}


class Store(Protocol):
	def earliest(self) -> datetime | None: ...

	def sets(self) -> list[tuple[str, str]]: ...

	def get(self, item_id: str) -> dict | None: ...

	def list(
		self, start: int, limit: int, from_: datetime | None, until: datetime | None, set_spec: str | None
	) -> tuple[list[dict], int]: ...


class OAIError(Exception):
	def __init__(self, code: str, message: str):
		super().__init__(message)
		self.code = code
		self.message = message


def _now() -> str:
	return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _stamp(value: datetime | None) -> str:
	if not value:
		return _now()
	if value.tzinfo is None:
		value = value.replace(tzinfo=UTC)
	return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_date(value: str | None, end: bool = False) -> datetime | None:
	if not value:
		return None
	for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
		try:
			parsed = datetime.strptime(value, fmt)
			if fmt == "%Y-%m-%d" and end:
				parsed = parsed.replace(hour=23, minute=59, second=59)
			return parsed
		except ValueError:
			continue
	raise OAIError("badArgument", f"Invalid date: {value}")


def _encode_token(data: dict) -> str:
	return base64.urlsafe_b64encode(json.dumps(data).encode()).decode()


def _decode_token(token: str) -> dict:
	try:
		return json.loads(base64.urlsafe_b64decode(token.encode()))
	except Exception as exc:
		raise OAIError("badResumptionToken", "The resumption token is invalid") from exc


def oai_identifier(repo_id: str, item_id: str) -> str:
	return f"oai:{repo_id}:{item_id}"


def dc_record(item: dict, base_url: str = "") -> str:
	parts = []

	def add(tag, value):
		if value:
			parts.append(f"<dc:{tag}>{escape(str(value))}</dc:{tag}>")

	add("title", item.get("title"))
	if item.get("alt_title") and item["alt_title"] != item.get("title"):
		add("title", item["alt_title"])
	for c in item.get("creators") or []:
		add("creator", c)
	for s in item.get("subjects") or []:
		add("subject", s)
	add("description", item.get("description"))
	add("publisher", item.get("publisher"))
	add("date", item.get("year"))
	add("type", "Text")
	add("format", "application/pdf")
	add("identifier", url_for(item, base_url))
	add("identifier", item.get("source_url"))
	if item.get("ark"):
		add("identifier", item["ark"])
	if item.get("doi"):
		add("identifier", f"https://doi.org/{item['doi']}")
	add("language", item.get("language"))
	add("rights", item.get("licence_url") or item.get("rights"))
	add("source", "Internet Archive")
	return (
		'<oai_dc:dc xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/" '
		'xmlns:dc="http://purl.org/dc/elements/1.1/" '
		'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
		'xsi:schemaLocation="http://www.openarchives.org/OAI/2.0/oai_dc/ '
		'http://www.openarchives.org/OAI/2.0/oai_dc.xsd">' + "".join(parts) + "</oai_dc:dc>"
	)


class Repository:
	def __init__(self, store: Store, repo_id: str, name: str, base_url: str, admin_email: str):
		self.store = store
		self.repo_id = repo_id
		self.name = name
		self.base_url = base_url.rstrip("/")
		self.admin_email = admin_email or "admin@example.org"
		self.endpoint = f"{self.base_url}/api/method/sok_resdesk.oai.endpoint"

	# -- public entry --------------------------------------------------------
	def handle(self, args: dict) -> str:
		args = {k: v for k, v in args.items() if k not in ("cmd",) and v not in (None, "")}
		verb = args.get("verb", "")
		try:
			handler = {
				"Identify": self.identify,
				"ListMetadataFormats": self.list_formats,
				"ListSets": self.list_sets,
				"GetRecord": self.get_record,
				"ListIdentifiers": lambda a: self.list_records(a, headers_only=True),
				"ListRecords": self.list_records,
			}.get(verb)
			if not handler:
				raise OAIError("badVerb", "Illegal OAI verb")
			body = handler(args)
			return self._wrap(args, body)
		except OAIError as err:
			attrs = "" if err.code in ("badVerb", "badArgument") else self._request_attrs(args)
			return self._wrap_raw(
				f"<request{attrs}>{escape(self.endpoint)}</request>"
				f'<error code="{err.code}">{escape(err.message)}</error>'
			)

	# -- envelope -----------------------------------------------------------
	def _request_attrs(self, args: dict) -> str:
		return "".join(f' {k}="{escape(str(v))}"' for k, v in sorted(args.items()))

	def _wrap(self, args: dict, body: str) -> str:
		return self._wrap_raw(f"<request{self._request_attrs(args)}>{escape(self.endpoint)}</request>{body}")

	def _wrap_raw(self, inner: str) -> str:
		return (
			'<?xml version="1.0" encoding="UTF-8"?>\n'
			'<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/" '
			'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
			'xsi:schemaLocation="http://www.openarchives.org/OAI/2.0/ '
			'http://www.openarchives.org/OAI/2.0/OAI-PMH.xsd">'
			f"<responseDate>{_now()}</responseDate>{inner}</OAI-PMH>"
		)

	# -- verbs ---------------------------------------------------------------
	def _only(self, args: dict, allowed: set[str]):
		extra = set(args) - allowed - {"verb"}
		if extra:
			raise OAIError("badArgument", f"Illegal arguments: {', '.join(sorted(extra))}")

	def identify(self, args: dict) -> str:
		self._only(args, set())
		earliest = _stamp(self.store.earliest())
		return (
			"<Identify>"
			f"<repositoryName>{escape(self.name)}</repositoryName>"
			f"<baseURL>{escape(self.endpoint)}</baseURL>"
			"<protocolVersion>2.0</protocolVersion>"
			f"<adminEmail>{escape(self.admin_email)}</adminEmail>"
			f"<earliestDatestamp>{earliest}</earliestDatestamp>"
			"<deletedRecord>no</deletedRecord>"
			"<granularity>YYYY-MM-DDThh:mm:ssZ</granularity>"
			'<description><oai-identifier xmlns="http://www.openarchives.org/OAI/2.0/oai-identifier" '
			'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
			'xsi:schemaLocation="http://www.openarchives.org/OAI/2.0/oai-identifier '
			'http://www.openarchives.org/OAI/2.0/oai-identifier.xsd">'
			f"<scheme>oai</scheme><repositoryIdentifier>{escape(self.repo_id)}</repositoryIdentifier>"
			"<delimiter>:</delimiter>"
			f"<sampleIdentifier>{oai_identifier(self.repo_id, 'sampleitem0000')}</sampleIdentifier>"
			"</oai-identifier></description>"
			"</Identify>"
		)

	def list_formats(self, args: dict) -> str:
		self._only(args, {"identifier"})
		if "identifier" in args:
			self._item_for(args["identifier"])
		rows = "".join(
			f"<metadataFormat><metadataPrefix>{p}</metadataPrefix><schema>{s}</schema>"
			f"<metadataNamespace>{n}</metadataNamespace></metadataFormat>"
			for p, (s, n) in FORMATS.items()
		)
		return f"<ListMetadataFormats>{rows}</ListMetadataFormats>"

	def list_sets(self, args: dict) -> str:
		self._only(args, {"resumptionToken"})
		sets = self.store.sets()
		if not sets:
			raise OAIError("noSetHierarchy", "This repository does not support sets")
		rows = "".join(
			f"<set><setSpec>{escape(spec)}</setSpec><setName>{escape(name)}</setName></set>"
			for spec, name in sets
		)
		return f"<ListSets>{rows}</ListSets>"

	def _item_for(self, identifier: str) -> dict:
		prefix = f"oai:{self.repo_id}:"
		if not identifier.startswith(prefix):
			raise OAIError("idDoesNotExist", "Unknown identifier")
		item = self.store.get(identifier[len(prefix) :])
		if not item:
			raise OAIError("idDoesNotExist", "Unknown identifier")
		return item

	def _header(self, item: dict) -> str:
		sets = "".join(f"<setSpec>{escape(s)}</setSpec>" for s in item.get("set_specs") or [])
		return (
			f"<header><identifier>{oai_identifier(self.repo_id, item['item_id'])}</identifier>"
			f"<datestamp>{_stamp(item.get('modified'))}</datestamp>{sets}</header>"
		)

	def _record(self, item: dict, prefix: str) -> str:
		if prefix == "oai_dc":
			meta = dc_record(item, self.base_url)
		else:
			meta = to_marcxml_record(item, self.base_url, with_namespace=True)
		return f"<record>{self._header(item)}<metadata>{meta}</metadata></record>"

	def get_record(self, args: dict) -> str:
		self._only(args, {"identifier", "metadataPrefix"})
		if "identifier" not in args or "metadataPrefix" not in args:
			raise OAIError("badArgument", "identifier and metadataPrefix are required")
		prefix = args["metadataPrefix"]
		if prefix not in FORMATS:
			raise OAIError("cannotDisseminateFormat", f"Unsupported metadataPrefix: {prefix}")
		item = self._item_for(args["identifier"])
		return f"<GetRecord>{self._record(item, prefix)}</GetRecord>"

	def list_records(self, args: dict, headers_only: bool = False) -> str:
		tag = "ListIdentifiers" if headers_only else "ListRecords"
		if "resumptionToken" in args:
			self._only(args, {"resumptionToken"})
			state = _decode_token(args["resumptionToken"])
		else:
			self._only(args, {"metadataPrefix", "from", "until", "set"})
			if "metadataPrefix" not in args:
				raise OAIError("badArgument", "metadataPrefix is required")
			state = {
				"p": args["metadataPrefix"],
				"f": args.get("from"),
				"u": args.get("until"),
				"s": args.get("set"),
				"o": 0,
			}
		if state["p"] not in FORMATS:
			raise OAIError("cannotDisseminateFormat", f"Unsupported metadataPrefix: {state['p']}")
		from_, until = _parse_date(state.get("f")), _parse_date(state.get("u"), end=True)
		items, total = self.store.list(state["o"], PAGE_SIZE, from_, until, state.get("s"))
		if not items:
			raise OAIError("noRecordsMatch", "No records match the request")
		if headers_only:
			rows = "".join(self._header(i) for i in items)
		else:
			rows = "".join(self._record(i, state["p"]) for i in items)
		next_offset = state["o"] + len(items)
		token = ""
		if next_offset < total:
			tok = _encode_token({**state, "o": next_offset})
			token = (
				f'<resumptionToken completeListSize="{total}" cursor="{state["o"]}">{tok}</resumptionToken>'
			)
		elif state["o"] > 0:
			token = f'<resumptionToken completeListSize="{total}" cursor="{state["o"]}"/>'
		return f"<{tag}>{rows}{token}</{tag}>"
