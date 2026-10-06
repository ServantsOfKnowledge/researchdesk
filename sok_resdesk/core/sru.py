"""SRU 1.2 (Search/Retrieve via URL) for the catalogue: CQL queries in, MARCXML or Dublin Core out.

Older library systems, union catalogues and Z39.50 gateways query a catalogue this way. Pure Python
(no Frappe), so it is unit-tested directly. The CQL accepted is the part catalogues use:

    term                         any of title, author, subject, description
    index = term                 title, author (creator), subject, identifier, date, language
    index all "two words"        every word          index any "two words"   some word
    index exact "A title"        the whole value     index adj "a phrase"    the phrase
    a and b · a or b · a not b   joined left to right; brackets group
"""

from __future__ import annotations

import re
from xml.sax.saxutils import escape, quoteattr

SRU_NS = "http://www.loc.gov/zing/srw/"
DIAG_NS = "http://www.loc.gov/zing/srw/diagnostic/"
MAX_RECORDS = 50
DEFAULT_RECORDS = 10

# CQL index -> the catalogue column it searches ("subject" is a child table)
INDEXES = {
	"cql.serverchoice": "any",
	"cql.anywhere": "any",
	"any": "any",
	"title": "title",
	"dc.title": "title",
	"author": "creator",
	"creator": "creator",
	"dc.creator": "creator",
	"subject": "subject",
	"dc.subject": "subject",
	"identifier": "identifier",
	"dc.identifier": "identifier",
	"date": "year",
	"dc.date": "year",
	"year": "year",
	"language": "language",
	"dc.language": "language",
}
# the order shown in the explain response (the bare names; the dc.* forms work too)
EXPLAIN_INDEXES = ["title", "creator", "subject", "identifier", "date", "language"]
RELATIONS = {"=", "all", "any", "adj", "exact", "<>"}
BOOLEANS = {"and", "or", "not"}
SCHEMAS = {
	"marcxml": ("info:srw/schema/1/marcxml-v1.1", "MARCXML 1.1"),
	"dc": ("info:srw/schema/1/dc-v1.1", "Dublin Core"),
}


class Diagnostic(Exception):
	def __init__(self, number: int, details: str = ""):
		super().__init__(f"{number}: {details}")
		self.number = number
		self.details = details


_TOKEN = re.compile(r'\s*(?:"((?:[^"\\]|\\.)*)"|(<>|=|\(|\))|([^\s()="]+))')


def tokenize(query: str) -> list[tuple[str, str]]:
	"""[(kind, text)]: kind is 'str' (quoted), 'op' (= <> brackets) or 'word'."""
	out, pos = [], 0
	query = query.strip()
	while pos < len(query):
		m = _TOKEN.match(query, pos)
		if not m or m.end() == pos:
			raise Diagnostic(10, f"Query syntax error near {query[pos : pos + 12]!r}")
		if m.group(1) is not None:
			out.append(("str", m.group(1).replace('\\"', '"')))
		elif m.group(2):
			out.append(("op", m.group(2)))
		else:
			out.append(("word", m.group(3)))
		pos = m.end()
	return out


def parse(query: str):
	"""A tree: ('term', index, relation, value) or ('bool', op, left, right). Raises Diagnostic."""
	tokens = tokenize(query)
	if not tokens:
		raise Diagnostic(7, "query")
	pos = 0

	def peek():
		return tokens[pos] if pos < len(tokens) else (None, None)

	def take():
		nonlocal pos
		pos += 1
		return tokens[pos - 1]

	def term():
		kind, text = peek()
		if kind is None:
			raise Diagnostic(10, "Query ends early")
		if (kind, text) == ("op", "("):
			take()
			node = expr()
			if peek() != ("op", ")"):
				raise Diagnostic(10, "Missing closing bracket")
			take()
			return node
		if kind == "op":
			raise Diagnostic(10, f"Unexpected {text}")
		take()
		nxt_kind, nxt = peek()
		is_relation = nxt_kind == "op" and nxt in ("=", "<>")
		is_word_relation = nxt_kind == "word" and nxt.lower() in RELATIONS and kind == "word"
		if is_relation or is_word_relation:
			take()
			vkind, value = peek()
			if vkind not in ("str", "word") or (vkind == "word" and value.lower() in BOOLEANS):
				raise Diagnostic(10, "A search term is missing")
			take()
			rel = nxt.lower()
			index = text.lower()
			if index not in INDEXES:
				raise Diagnostic(16, text)
			if rel not in RELATIONS:
				raise Diagnostic(19, nxt)
			return ("term", INDEXES[index], rel, value)
		if kind == "word" and text.lower() in BOOLEANS:
			raise Diagnostic(10, f"Unexpected {text}")
		return ("term", "any", "all", text)

	def expr():
		left = term()
		while True:
			kind, text = peek()
			if kind == "word" and text.lower() in BOOLEANS:
				take()
				left = ("bool", text.lower(), left, term())
			else:
				return left

	tree = expr()
	if pos != len(tokens):
		raise Diagnostic(10, f"Unexpected {tokens[pos][1]}")
	return tree


def _words(value: str) -> list[str]:
	return [w for w in re.split(r"\s+", value.strip()) if w]


def _like(value: str) -> str:
	return "%" + value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _field_condition(index: str, relation: str, value: str, params: list) -> str:
	"""SQL for one term; appends its values to params (%s placeholders)."""
	if relation not in RELATIONS:
		raise Diagnostic(19, relation)
	cols = {
		"title": ["title", "alt_title"],
		"creator": ["creator_display"],
		"identifier": ["item_id", "ark", "doi", "isbn", "persistent_id"],
		"language": ["language", "language_label"],
		"any": ["title", "alt_title", "creator_display", "description"],
	}
	if index == "year":
		m = re.fullmatch(r"\s*(\d{4})\s*", value)
		if not m:
			raise Diagnostic(36, "date must be a four-digit year")
		params.append(int(m.group(1)))
		return "year " + ("<>" if relation == "<>" else "=") + " %s"
	if index == "subject":
		name = "exists (select 1 from `tabRD Item Subject` s where s.parent=`tabRD Item`.name and s.subject {op} %s)"
	else:
		name = None
	words = _words(value)
	if not words:
		raise Diagnostic(10, "A search term is missing")

	def one(op_like: bool, text: str) -> str:
		if name:
			if op_like:
				params.append(_like(text))
				return name.format(op="like")
			params.append(text)
			return name.format(op="=")
		parts = []
		for col in cols[index]:
			if op_like:
				parts.append(f"`tabRD Item`.{col} like %s")
				params.append(_like(text))
			else:
				parts.append(f"`tabRD Item`.{col} = %s")
				params.append(text)
		return "(" + " or ".join(parts) + ")"

	if relation in ("exact", "="):
		# "=" is a phrase for a title/subject and a word match elsewhere; both are contains-style
		sql = one(relation != "exact", " ".join(words))
	elif relation == "adj":
		sql = one(True, " ".join(words))
	elif relation == "any":
		sql = "(" + " or ".join(one(True, w) for w in words) + ")"
	elif relation == "all":
		sql = "(" + " and ".join(one(True, w) for w in words) + ")"
	elif relation == "<>":
		sql = "not " + one(True, " ".join(words))
	else:
		raise Diagnostic(19, relation)
	return sql


def to_sql(tree, params: list | None = None) -> tuple[str, list]:
	"""(SQL condition on `tabRD Item`, values). Joins parse trees with and / or / and-not."""
	params = [] if params is None else params
	if tree[0] == "term":
		return _field_condition(tree[1], tree[2], tree[3], params), params
	_, op, left, right = tree
	lsql, _p = to_sql(left, params)
	rsql, _p = to_sql(right, params)
	joiner = {"and": "and", "or": "or", "not": "and not"}[op]
	return f"({lsql} {joiner} {rsql})", params


def clamp(value, default: int, maximum: int, minimum: int = 0) -> int:
	try:
		n = int(value)
	except (TypeError, ValueError):
		return default
	return max(minimum, min(n, maximum))


def _diagnostic_xml(number: int, details: str = "") -> str:
	messages = {
		1: "General system error",
		7: "Mandatory parameter not supplied",
		10: "Query syntax error",
		16: "Unsupported index",
		19: "Unsupported relation",
		36: "Term in invalid format for index or relation",
		61: "First record position out of range",
		66: "Unknown schema for retrieval",
		6: "Unsupported parameter value",
	}
	return (
		f'<diagnostic xmlns="{DIAG_NS}">'
		f"<uri>info:srw/diagnostic/1/{number}</uri>"
		f"<details>{escape(details)}</details>"
		f"<message>{escape(messages.get(number, 'Diagnostic'))}</message>"
		"</diagnostic>"
	)


def _envelope(name: str, inner: str, version: str = "1.2") -> str:
	return (
		'<?xml version="1.0" encoding="UTF-8"?>\n'
		f'<srw:{name} xmlns:srw="{SRU_NS}"><srw:version>{escape(version)}</srw:version>{inner}</srw:{name}>\n'
	)


def diagnostics_response(operation: str, diags: list[Diagnostic]) -> str:
	"""An error answer (SRU answers 200 with diagnostics, not an HTTP error)."""
	body = "".join(_diagnostic_xml(d.number, d.details) for d in diags)
	if operation == "explain":
		return _envelope("explainResponse", f"<srw:diagnostics>{body}</srw:diagnostics>")
	return _envelope(
		"searchRetrieveResponse",
		f"<srw:numberOfRecords>0</srw:numberOfRecords><srw:diagnostics>{body}</srw:diagnostics>",
	)


def search_response(
	*,
	total: int,
	records: list[str],
	schema: str,
	start: int,
	next_start: int | None,
	query: str,
	maximum: int,
) -> str:
	"""A searchRetrieveResponse: `records` are the XML of each record (already in `schema`)."""
	uri = SCHEMAS[schema][0]
	rows = "".join(
		"<srw:record>"
		f"<srw:recordSchema>{uri}</srw:recordSchema>"
		"<srw:recordPacking>xml</srw:recordPacking>"
		f"<srw:recordData>{xml}</srw:recordData>"
		f"<srw:recordPosition>{start + i}</srw:recordPosition>"
		"</srw:record>"
		for i, xml in enumerate(records)
	)
	nxt = f"<srw:nextRecordPosition>{next_start}</srw:nextRecordPosition>" if next_start else ""
	return _envelope(
		"searchRetrieveResponse",
		f"<srw:numberOfRecords>{total}</srw:numberOfRecords>"
		f"<srw:records>{rows}</srw:records>{nxt}"
		f"<srw:echoedSearchRetrieveRequest><srw:version>1.2</srw:version>"
		f"<srw:query>{escape(query)}</srw:query><srw:startRecord>{start}</srw:startRecord>"
		f"<srw:maximumRecords>{maximum}</srw:maximumRecords>"
		f"<srw:recordSchema>{escape(schema)}</srw:recordSchema></srw:echoedSearchRetrieveRequest>",
	)


def explain_response(*, host: str, port: str, database: str, title: str, description: str = "") -> str:
	"""The ZeeRex explain record: where the server is, what it holds, which indexes and schemas."""
	indexes = "".join(
		f'<index><title>{i}</title><map><name set="cql">{i}</name></map></index>' for i in EXPLAIN_INDEXES
	)
	schemas = "".join(
		f"<schema identifier={quoteattr(uri)} name={quoteattr(name)}><title>{escape(label)}</title></schema>"
		for name, (uri, label) in SCHEMAS.items()
	)
	record = (
		'<explain xmlns="http://explain.z3950.org/dtd/2.0/">'
		f'<serverInfo protocol="SRU" version="1.2"><host>{escape(host)}</host><port>{escape(port)}</port>'
		f"<database>{escape(database)}</database></serverInfo>"
		f"<databaseInfo><title>{escape(title)}</title><description>{escape(description)}</description></databaseInfo>"
		f'<indexInfo><set identifier="info:srw/cql-context-set/1/cql-v1.2" name="cql"/>{indexes}</indexInfo>'
		f"<schemaInfo>{schemas}</schemaInfo>"
		f'<configInfo><default type="numberOfRecords">{DEFAULT_RECORDS}</default>'
		f'<setting type="maximumRecords">{MAX_RECORDS}</setting></configInfo>'
		"</explain>"
	)
	inner = (
		"<srw:record><srw:recordSchema>http://explain.z3950.org/dtd/2.0/</srw:recordSchema>"
		f"<srw:recordPacking>xml</srw:recordPacking><srw:recordData>{record}</srw:recordData></srw:record>"
	)
	return _envelope("explainResponse", inner)
