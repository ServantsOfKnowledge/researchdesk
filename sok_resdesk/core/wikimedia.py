"""Writing to Wikimedia sites (Wikidata, Wikisource, Commons…) as the person doing the work.

Wikimedia expects edits under the editor's own account: Wikisource credits who proofread and who
validated each page, and a shared account would break that. So every contributor connects
their own account with an **OAuth 2.0 access token**: an *owner-only* consumer registered at
meta.wikimedia.org gives its owner an access token at once (no approval wait), and it works on
every Wikimedia wiki. This module is the client; nothing here imports Frappe.
"""

from __future__ import annotations

import time

import requests

USER_AGENT = "SOK-ResearchDesk (+https://github.com/ServantsOfKnowledge/researchdesk; contributor edits)"
META_API = "https://meta.wikimedia.org/w/api.php"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
REGISTER = "https://meta.wikimedia.org/wiki/Special:OAuthConsumerRegistration/propose"
# a token must be allowed at least these for the work Research Desk does
NEEDED = ("edit",)


class WikimediaError(Exception):
	pass


class WikimediaClient:
	def __init__(self, api_url: str, token: str, session=None, maxlag: int = 5, timeout: int = 60):
		if not api_url.startswith("https://") or "/w/api.php" not in api_url:
			raise WikimediaError("An API address such as https://kn.wikisource.org/w/api.php")
		self.api = api_url
		self.maxlag = maxlag
		self.timeout = timeout
		self.session = session or requests.Session()
		self.session.headers["User-Agent"] = USER_AGENT
		self.session.headers["Authorization"] = f"Bearer {token.strip()}"
		self._csrf: str | None = None

	@classmethod
	def for_site(cls, site: str, token: str, **kw) -> WikimediaClient:
		return cls(f"https://{site}/w/api.php", token, **kw)

	def _read(self, resp) -> dict:
		if resp.status_code in (401, 403):
			raise WikimediaError("Wikimedia refused the access token: reconnect your account")
		try:
			out = resp.json()
		except ValueError as e:
			raise WikimediaError(f"{self.api}: HTTP {resp.status_code}, not an API answer") from e
		return out

	def get(self, **params) -> dict:
		out = self._read(
			self.session.get(
				self.api, params={"format": "json", "formatversion": 2, **params}, timeout=self.timeout
			)
		)
		self._check(out)
		return out

	def post(self, **data) -> dict:
		"""A write: waits and tries again while the wiki is lagging (maxlag), as bots must."""
		for attempt in range(5):
			out = self._read(
				self.session.post(
					self.api,
					data={"format": "json", "formatversion": 2, "maxlag": self.maxlag, **data},
					timeout=self.timeout * 2,
				)
			)
			if out.get("error", {}).get("code") == "maxlag":
				time.sleep(5 * (attempt + 1))
				continue
			self._check(out)
			return out
		raise WikimediaError("The wiki is busy (maxlag); try again later")

	@staticmethod
	def _check(out: dict) -> None:
		err = out.get("error")
		if err:
			raise WikimediaError(f"{err.get('code', 'error')}: {err.get('info', '')}".strip(": "))

	def whoami(self) -> dict:
		"""{"name", "id", "rights", "groups"} of the account the token belongs to."""
		info = (
			self.get(action="query", meta="userinfo", uiprop="rights|groups")
			.get("query", {})
			.get("userinfo", {})
		)
		if info.get("anon") or not info.get("name"):
			raise WikimediaError("The token does not belong to a logged-in account")
		return {
			"name": info["name"],
			"id": info.get("id"),
			"rights": info.get("rights", []),
			"groups": info.get("groups", []),
		}

	def csrf(self) -> str:
		if not self._csrf:
			self._csrf = self.get(action="query", meta="tokens")["query"]["tokens"]["csrftoken"]
		return self._csrf

	def missing_rights(self) -> list[str]:
		"""What the token lacks of NEEDED (it was granted fewer rights than Research Desk uses)."""
		rights = set(self.whoami()["rights"])
		return [r for r in NEEDED if r not in rights]
