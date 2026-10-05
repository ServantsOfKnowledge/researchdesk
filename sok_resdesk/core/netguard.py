"""Fetching addresses that came from outside (a repository record's links, a page's PDF) without
being steered at this server's own network: no loopback, private, link-local or reserved
addresses unless the library named that host itself (a repository on the intranet).

Pure Python so it is unit-tested directly.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urljoin, urlparse

MAX_REDIRECTS = 5


class Blocked(ValueError):
	pass


def check(url: str, trusted_hosts: tuple[str, ...] = (), resolve=socket.getaddrinfo) -> str:
	"""`url` if it may be fetched, else Blocked: http(s) only, and a host that resolves to public
	addresses only (or one of `trusted_hosts`, which the library set up itself)."""
	parts = urlparse(url or "")
	if parts.scheme not in ("http", "https") or not parts.hostname:
		raise Blocked(f"not a web address: {url[:100]}")
	host = parts.hostname.lower()
	if host in {h.lower() for h in trusted_hosts if h}:
		return url
	try:
		infos = resolve(host, parts.port or (443 if parts.scheme == "https" else 80))
	except (OSError, UnicodeError) as e:
		raise Blocked(f"{host} can't be found") from e
	for info in infos:
		addr = ipaddress.ip_address(info[4][0])
		if (
			addr.is_private
			or addr.is_loopback
			or addr.is_link_local
			or addr.is_reserved
			or addr.is_multicast
			or addr.is_unspecified
		):
			raise Blocked(f"{host} is on a private network")
	return url


def get(session, url: str, trusted_hosts: tuple[str, ...] = (), **kwargs):
	"""session.get, following redirects by hand so each hop is checked."""
	kwargs.pop("allow_redirects", None)
	for _hop in range(MAX_REDIRECTS + 1):
		check(url, trusted_hosts)
		resp = session.get(url, allow_redirects=False, **kwargs)
		if resp.status_code in (301, 302, 303, 307, 308) and resp.headers.get("Location"):
			url = urljoin(url, resp.headers["Location"])
			resp.close()
			continue
		return resp
	raise Blocked("too many redirects")
