"""The Wikimedia client with a person's token, and the Wikidata client in token mode (no network)."""

import pytest

from sok_resdesk.core import push
from sok_resdesk.core import wikimedia as wm
from sok_resdesk.tests.wikisource_fixtures import Resp


class Session:
	"""Answers in turn; remembers what was asked and the headers."""

	def __init__(self, *answers):
		self.answers, self.headers, self.asked = list(answers), {}, []

	def _next(self):
		a = self.answers.pop(0)
		return a if isinstance(a, Resp) else Resp(a)

	def get(self, url, params=None, timeout=None, **kw):
		self.asked.append(("GET", params))
		return self._next()

	def post(self, url, data=None, timeout=None, **kw):
		self.asked.append(("POST", data))
		return self._next()


USER = {
	"query": {
		"userinfo": {
			"id": 7,
			"name": "Volunteer",
			"rights": ["read", "edit", "createpage"],
			"groups": ["*", "user"],
		}
	}
}


def client(*answers, token=" tok-123 "):
	return wm.WikimediaClient(wm.META_API, token, session=Session(*answers))


def test_the_token_is_sent_as_a_bearer_and_names_a_user():
	c = client(USER)
	who = c.whoami()
	assert who["name"] == "Volunteer" and "edit" in who["rights"]
	assert c.session.headers["Authorization"] == "Bearer tok-123"
	assert "SOK-ResearchDesk" in c.session.headers["User-Agent"]
	assert c.session.asked[0][1]["meta"] == "userinfo"


def test_an_anonymous_answer_means_the_token_is_no_good():
	with pytest.raises(wm.WikimediaError, match="logged-in account"):
		client({"query": {"userinfo": {"id": 0, "name": "1.2.3.4", "anon": True}}}).whoami()
	with pytest.raises(wm.WikimediaError, match="refused the access token"):
		client(Resp({}, 401)).whoami()


def test_rights_the_token_lacks():
	assert client(USER).missing_rights() == []
	read_only = {"query": {"userinfo": {"id": 7, "name": "V", "rights": ["read"], "groups": []}}}
	assert client(read_only).missing_rights() == ["edit"]


def test_api_errors_and_the_csrf_token_once():
	c = client({"query": {"tokens": {"csrftoken": "abc+\\"}}})
	assert c.csrf() == "abc+\\" and c.csrf() == "abc+\\"
	assert len(c.session.asked) == 1  # kept after the first
	with pytest.raises(wm.WikimediaError, match="permissiondenied: no"):
		client({"error": {"code": "permissiondenied", "info": "no"}}).get(action="query")


def test_a_lagging_wiki_is_waited_for(monkeypatch):
	monkeypatch.setattr(wm.time, "sleep", lambda s: None)
	c = client({"error": {"code": "maxlag", "info": "lagged"}}, {"edit": {"result": "Success"}})
	assert c.post(action="edit")["edit"]["result"] == "Success"
	assert [kind for kind, _ in c.session.asked] == ["POST", "POST"]
	assert c.session.asked[0][1]["maxlag"] == 5
	busy = client(*[{"error": {"code": "maxlag", "info": "x"}}] * 5)
	with pytest.raises(wm.WikimediaError, match="busy"):
		busy.post(action="edit")


@pytest.mark.parametrize("api", ["http://kn.wikisource.org/w/api.php", "https://example.org/api", ""])
def test_only_https_mediawiki_apis(api):
	with pytest.raises(wm.WikimediaError):
		wm.WikimediaClient(api, "t")


def wikidata(token="", *answers):
	return push.WikidataClient(wm.WIKIDATA_API, "bot", "pw", session=Session(*answers), token=token)


def test_wikidata_as_a_person_has_no_bot_flag_and_no_password_login():
	c = wikidata(
		"person-token-xxxxxxxx",
		{"query": {"userinfo": {"id": 7, "name": "Volunteer"}}},
		{"query": {"tokens": {"csrftoken": "csrf+\\"}}},
		{"entity": {"id": "Q1"}},
	)
	assert c.login() == "Volunteer"
	c.edit("Q1", {"labels": {}}, "summary")
	kind, sent = c.session.asked[-1]
	assert kind == "POST" and "bot" not in sent and sent["token"] == "csrf+\\"
	assert c.session.headers["Authorization"] == "Bearer person-token-xxxxxxxx"
	assert all(m == "GET" for m, _ in c.session.asked[:2])  # no login with a password


def test_wikidata_by_bot_password_still_flags_bot_edits():
	c = wikidata(
		"",
		{"query": {"tokens": {"logintoken": "lt"}}},
		{"login": {"result": "Success", "lgusername": "bot"}},
		{"query": {"tokens": {"csrftoken": "csrf"}}},
		{"entity": {"id": "Q1"}},
	)
	assert c.login() == "bot"
	c.edit("Q1", {"labels": {}}, "summary")
	assert c.session.asked[-1][1]["bot"] == 1
	assert "Authorization" not in c.session.headers


def test_wikidata_refuses_an_anonymous_token():
	c = wikidata("t" * 30, {"query": {"userinfo": {"id": 0, "name": "1.2.3.4", "anon": True}}})
	with pytest.raises(push.PushError, match="reconnect"):
		c.login()
