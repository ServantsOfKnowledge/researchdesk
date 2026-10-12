"""What the contributors page may show of a profile (pure: no Frappe)."""

SHOWN = ("organisation", "role_title", "country", "about")


def public_row(row: dict) -> dict | None:
	"""Only the fields a person agreed to show, trimmed; None when there is no name to show.
	Never the volunteering notes, the support needs or the staff note. A website is shown only
	if it is a plain web address."""
	name = (row.get("full_name") or "").strip()
	if not name:
		return None
	out = {"name": name, "kind": "Organisation" if row.get("kind") == "Organisation" else "Individual"}
	for key in SHOWN:
		out[key] = (row.get(key) or "").strip()
	site = (row.get("website") or "").strip()
	out["website"] = site if site.lower().startswith(("http://", "https://")) and " " not in site else ""
	return out
