import frappe


def execute():
	"""Frappe's limiter could leave a counter with no expiry, blocking an endpoint for good (0.97)."""
	for key in frappe.cache.scan_iter(match=b"*|rl:*"):
		if frappe.cache.ttl(key) < 0:
			frappe.cache.delete(key)
