"""The limiter sets an expiry on a counter that has none, and refuses past the limit."""

import sys
import types
from types import SimpleNamespace

import pytest

sys.modules.setdefault("frappe", types.ModuleType("frappe"))  # the pure tests run without Frappe

import sok_resdesk.ratelimit as rl  # noqa: E402


class Limit(Exception):
	pass


class FakeCache:
	def __init__(self):
		self.n, self.ttl_s = {}, {}

	def make_key(self, k):
		return k.encode()

	def incrby(self, k, by):
		self.n[k] = self.n.get(k, 0) + by
		return self.n[k]

	def ttl(self, k):
		return self.ttl_s.get(k, -1)

	def expire(self, k, s):
		self.ttl_s[k] = s


def _throw(msg, exc=Exception):
	raise exc(msg)


def test_counter_without_expiry_gets_one_and_limit_holds(monkeypatch):
	cache = FakeCache()
	fake = SimpleNamespace(
		cache=cache,
		request=SimpleNamespace(method="POST"),
		form_dict=SimpleNamespace(cmd="x", get=lambda k, d="": d),
		local=SimpleNamespace(request_ip="1.2.3.4"),
		RateLimitExceededError=Limit,
		throw=_throw,
		_=lambda s: s,
	)
	monkeypatch.setattr(rl, "frappe", fake)
	key = b"rl:x:1.2.3.4:60"
	cache.n[key] = 100  # what a lost expiry leaves behind
	calls = rl.rate_limit(limit=101, seconds=60)(lambda: "ok")
	assert calls() == "ok" and cache.ttl_s[key] == 60
	with pytest.raises(Limit):
		calls()
