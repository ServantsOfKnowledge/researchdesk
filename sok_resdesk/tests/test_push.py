"""Push clients against a fake HTTP session (no network)."""

import hashlib
import hmac
import json
import re
from contextlib import contextmanager

from sok_resdesk.core.push import (
	IAWriter,
	KohaClient,
	PushError,
	Webhook,
	WikidataClient,
	ia_patch,
	payload_hash,
	wikidata_entity,
)


@contextmanager
def raises(exc, match=""):
	"""Like pytest.raises; Frappe's test runner has no pytest."""
	try:
		yield
	except exc as e:
		assert re.search(match, str(e)), str(e)
	else:
		raise AssertionError(f"{exc.__name__} not raised")


class Resp:
	def __init__(self, status=200, data=None, text=""):
		self.status_code = status
		self._data = data
		self.text = text or (json.dumps(data) if data is not None else "")
		self.content = self.text.encode()

	def json(self):
		return self._data if self._data is not None else json.loads(self.text)


class FakeSession:
	"""Answers from a list of (method, url-substring, response) in order of matching."""

	def __init__(self, routes):
		self.routes = list(routes)
		self.headers = {}
		self.calls = []

	def _answer(self, method, url, **kw):
		self.calls.append((method, url, kw))
		for m, part, resp in self.routes:
			if m == method and part in url:
				if callable(resp):
					return resp(url, kw)
				return resp
		raise AssertionError(f"unexpected {method} {url}")

	def get(self, url, **kw):
		return self._answer("GET", url, **kw)

	def post(self, url, **kw):
		return self._answer("POST", url, **kw)

	def put(self, url, **kw):
		return self._answer("PUT", url, **kw)


RECORD = {
	"item_id": "in.ernet.dli.2015.1234",
	"title": "ಕನ್ನಡ ಸಾಹಿತ್ಯ ಚರಿತ್ರೆ",
	"alt_title": "Kannada Sahitya Charitre",
	"creators": ["Mugali, R. S.", "Someone Else"],
	"year": 1953,
	"language": "kan",
	"language_label": "Kannada",
	"item_type": "Book",
	"on_archive_org": 1,
	"ark": "ark:/13960/t0abc",
	"page_count": 412,
	"source_url": "https://archive.org/details/in.ernet.dli.2015.1234",
	"isbn": "",
}


def test_ia_patch_only_adds_or_replaces():
	current = {"title": "Old", "subject": "History", "creator": "A"}
	desired = {"title": "New", "subject": ["History"], "creator": "A", "language": "kan", "date": ""}
	ops = ia_patch(current, desired, ("title", "subject", "creator", "language", "date", "volume"))
	assert ops == [
		{"op": "replace", "path": "/title", "value": "New"},
		{"op": "add", "path": "/language", "value": "kan"},
	]
	assert ia_patch(current, {"title": "Old"}, ("title",)) == []


def test_ia_writer():
	s = FakeSession(
		[
			("GET", "check_auth", Resp(200, {"authorized": True, "username": "om@example.org"})),
			("GET", "/metadata/abc", Resp(200, {"metadata": {"identifier": "abc", "title": "x"}})),
			("POST", "/metadata/abc", Resp(200, {"success": True, "task_id": 42})),
		]
	)
	w = IAWriter("KEY", "SECRET", session=s)
	assert w.check() == "om@example.org"
	assert w.current("abc")["title"] == "x"
	assert w.write("abc", [{"op": "replace", "path": "/title", "value": "y"}])["task_id"] == 42
	method, url, kw = s.calls[-1]
	assert kw["headers"]["Authorization"] == "LOW KEY:SECRET"
	assert kw["data"]["-target"] == "metadata"
	assert json.loads(kw["data"]["-patch"])[0]["value"] == "y"

	bad = IAWriter(
		"K",
		"S",
		session=FakeSession([("GET", "check_auth", Resp(403, {"authorized": False, "error": "bad keys"}))]),
	)
	with raises(PushError):
		bad.check()


def test_koha_basic_and_oauth():
	s = FakeSession(
		[
			("GET", "/libraries", Resp(200, [])),
			("POST", "/biblios", Resp(201, {"id": 77})),
			("PUT", "/biblios/77", Resp(200, {})),
			("PUT", "/biblios/78", Resp(404, {"error": "not found"})),
		]
	)
	k = KohaClient("https://koha.example.org/", ("basic", "u", "p"), framework="FA", session=s)
	assert k.check() == "ok"
	assert k.create("<record/>") == "77"
	_, url, kw = s.calls[-1]
	assert url == "https://koha.example.org/api/v1/biblios"
	assert kw["auth"] == ("u", "p")
	assert kw["headers"]["Content-Type"] == "application/marcxml+xml"
	assert kw["headers"]["x-framework-id"] == "FA"
	k.update("77", "<record/>")
	with raises(PushError, match="gone"):
		k.update("78", "<record/>")

	s2 = FakeSession(
		[
			("POST", "/oauth/token", Resp(200, {"access_token": "T0K"})),
			("POST", "/biblios", Resp(200, {"biblio_id": 5})),
		]
	)
	k2 = KohaClient("https://koha.example.org", ("oauth", "cid", "csecret"), session=s2)
	assert k2.create("<record/>") == "5"
	assert s2.calls[0][2]["data"]["client_id"] == "cid"
	assert s2.calls[1][2]["headers"]["Authorization"] == "Bearer T0K"
	assert "auth" not in s2.calls[1][2]


def test_wikidata_entity_shape():
	data = wikidata_entity(RECORD, "https://desk.example.org/library/item/in.ernet.dli.2015.1234")
	assert data["labels"]["kn"]["value"] == RECORD["title"]
	assert data["labels"]["en"]["value"] == "Kannada Sahitya Charitre"
	props = [c["mainsnak"]["property"] for c in data["claims"]]
	for p in ("P31", "P1476", "P2093", "P577", "P407", "P724", "P8091", "P1104", "P953"):
		assert p in props
	authors = [c for c in data["claims"] if c["mainsnak"]["property"] == "P2093"]
	assert authors[1]["qualifiers"]["P1545"][0]["datavalue"]["value"] == "2"
	date = next(c for c in data["claims"] if c["mainsnak"]["property"] == "P577")
	assert date["mainsnak"]["datavalue"]["value"]["time"] == "+1953-00-00T00:00:00Z"
	lang = next(c for c in data["claims"] if c["mainsnak"]["property"] == "P407")
	assert lang["mainsnak"]["datavalue"]["value"]["id"] == "Q33673"


def test_wikidata_client_flow():
	edits = []

	def edit(url, kw):
		edits.append(kw["data"])
		if kw["data"].get("new"):
			return Resp(200, {"entity": {"id": "Q999"}, "success": 1})
		return Resp(200, {"success": 1})

	lag = {"n": 0}

	def login(url, kw):
		if kw["data"]["action"] == "login":
			return Resp(200, {"login": {"result": "Success", "lgusername": "OmBot"}})
		return edit(url, kw)

	def maybe_lag(url, kw):
		if lag["n"] == 0 and kw["data"]["action"] == "wbeditentity":
			lag["n"] += 1
			return Resp(200, {"error": {"code": "maxlag"}})
		return login(url, kw)

	def get(url, kw):
		p = kw["params"]
		if p.get("meta") == "tokens":
			key = "logintoken" if p.get("type") == "login" else "csrftoken"
			return Resp(200, {"query": {"tokens": {key: "tok+\\"}}})
		if p.get("list") == "search":
			return Resp(200, {"query": {"search": [{"title": "Q123"}]}})
		if p.get("action") == "wbgetentities":
			return Resp(200, {"entities": {"Q123": {"claims": {"P31": [], "P1476": [], "P724": []}}}})
		raise AssertionError(p)

	s = FakeSession([("GET", "api.php", get), ("POST", "api.php", maybe_lag)])
	c = WikidataClient("https://www.wikidata.org/w/api.php", "Om@bot", "pw", session=s, maxlag=5)
	import sok_resdesk.core.push as push

	push.time.sleep, real = (lambda _s: None), push.time.sleep
	try:
		assert c.login() == "OmBot"
		assert c.find_by_ia("in.ernet.dli.2015.1234") == "Q123"
		data = wikidata_entity(RECORD)
		added = c.add_missing("Q123", data, "test")
		assert added == len(
			[x for x in data["claims"] if x["mainsnak"]["property"] not in ("P31", "P1476", "P724")]
		)
		sent = json.loads(edits[-1]["data"])["claims"]
		assert {x["mainsnak"]["property"] for x in sent}.isdisjoint({"P31", "P1476", "P724"})
		assert edits[-1]["token"] == "tok+\\" and edits[-1]["maxlag"] == 5
		assert c.create(data, "test") == "Q999"
	finally:
		push.time.sleep = real


def test_webhook_signature():
	s = FakeSession([("POST", "hooks.example.org", Resp(202, {}))])
	assert (
		Webhook("https://hooks.example.org/x", "s3cret", session=s).send("record.updated", {"id": "a"}) == 202
	)
	_, _, kw = s.calls[0]
	body = kw["data"]
	sig = kw["headers"]["X-ResDesk-Signature"]
	assert sig == "sha256=" + hmac.new(b"s3cret", body, hashlib.sha256).hexdigest()
	assert json.loads(body)["data"] == {"id": "a"}
	fail = FakeSession([("POST", "hooks", Resp(500, text="boom"))])
	with raises(PushError):
		Webhook("https://hooks.example.org/x", session=fail).send("ping", {})


def test_payload_hash_stable():
	assert payload_hash({"b": 1, "a": [1, 2]}) == payload_hash({"a": [1, 2], "b": 1})
	assert payload_hash({"a": 1}) != payload_hash({"a": 2})
