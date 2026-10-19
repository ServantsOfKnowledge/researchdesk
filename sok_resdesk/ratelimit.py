"""Frappe's `rate_limit`, with the window kept.

Frappe reads the counter, sets its expiry only if the key is missing, then increments it. A request that
lands as the key expires re-creates it by the increment, with no expiry: the counter then only grows and
the endpoint answers 429 for good (seen on `agent_sync`). Here the increment comes first and the expiry is
set whenever the key has none.
"""

from functools import wraps

import frappe


def rate_limit(key=None, limit=5, seconds=24 * 60 * 60, methods="ALL", ip_based=True):
	def decorator(fn):
		@wraps(fn)
		def wrapper(*args, **kwargs):
			if not frappe.request or (
				methods != "ALL" and frappe.request.method and frappe.request.method.upper() not in methods
			):
				return fn(*args, **kwargs)
			ip = frappe.local.request_ip if ip_based is True else None
			identity = (":".join([ip, frappe.form_dict.get(key, "")]) if key and ip_based else None) or (
				ip or frappe.form_dict.get(key, "")
			)
			if not identity:
				frappe.throw("Either key or IP flag is required.")
			cache_key = (
				frappe.cache.make_key(f"rl:{frappe.form_dict.cmd}:{identity}") + f":{seconds}".encode()
			)
			value = frappe.cache.incrby(cache_key, 1)
			if value == 1 or frappe.cache.ttl(cache_key) < 0:
				frappe.cache.expire(cache_key, seconds)
			if value > (limit() if callable(limit) else limit):
				frappe.throw(
					frappe._(
						"You hit the rate limit because of too many requests. Please try after sometime."
					),
					frappe.RateLimitExceededError,
				)
			return fn(*args, **kwargs)

		return wrapper

	return decorator
