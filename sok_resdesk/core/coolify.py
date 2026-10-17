"""Asking Coolify to restart or redeploy Research Desk (pure: no Frappe, no network).

Under Coolify the updater helper can't work (Coolify owns the containers), so the Server page asks
Coolify's own API instead. The three settings come from the resource's Environment Variables in
Coolify (compose.yaml passes them to the backend); Coolify's own COOLIFY_URL names the app, so these
are RESDESK_COOLIFY_*.
"""

from urllib.parse import quote

# the Server page action -> what it asks Coolify: restart the resource, or deploy its branch again
ACTIONS = ("restart", "upgrade")


def settings(env) -> dict | None:
	"""{"api", "token", "app"} when all three are set (the dashboard's address, an API token with the
	deploy permission, and the resource's uuid), else None."""
	api = (env.get("RESDESK_COOLIFY_API") or "").strip().rstrip("/")
	token = (env.get("RESDESK_COOLIFY_TOKEN") or "").strip()
	app = (env.get("RESDESK_COOLIFY_APP") or "").strip()
	if not (api.startswith(("http://", "https://")) and token and app):
		return None
	return {"api": api, "token": token, "app": app}


def request_for(action: str, cfg: dict) -> tuple[str, dict]:
	"""(url, headers) of the GET that makes Coolify restart the resource, or deploy it again."""
	if action not in ACTIONS:
		raise ValueError(f"Coolify can't do {action}")
	app = quote(cfg["app"], safe="")
	url = (
		f"{cfg['api']}/api/v1/applications/{app}/restart"
		if action == "restart"
		else f"{cfg['api']}/api/v1/deploy?uuid={app}&force=false"
	)
	return url, {"Authorization": f"Bearer {cfg['token']}", "Accept": "application/json"}
