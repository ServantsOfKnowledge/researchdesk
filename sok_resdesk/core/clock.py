"""Advice about dates, time zones and sign-in links (pure: no Frappe)."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo, available_timezones

DAY = 86400
MAIL_LATE = 600  # an email waiting longer than this (seconds) is late


def zone_names() -> set[str]:
	return available_timezones()


def offset_seconds(zone: str, at: datetime | None = None) -> int:
	"""The zone's offset from UTC at this moment."""
	at = at or datetime.now(UTC)
	return int(at.astimezone(ZoneInfo(zone)).utcoffset().total_seconds())


def advise(
	expiry_seconds: int | None, oldest_mail_wait: int, host_offset: int, system_offset: int
) -> list[str]:
	"""Codes for what is likely to make a mailed sign-in link arrive expired:
	- "no_setting": this Frappe has no link lifetime setting to show
	- "short": the link lives less than a day
	- "mail_late": an email has waited more than ten minutes to be sent; its link is already using up its life
	- "mail_outlives": an email has waited longer than the link lives, so it can only arrive expired
	- "zone_differs": the server's own clock zone is not the System Settings zone (Frappe stores and compares
	  times in the System Settings zone; the server's logs use theirs)"""
	out = []
	if expiry_seconds is None:
		out.append("no_setting")
	elif 0 < expiry_seconds < DAY:
		out.append("short")
	if oldest_mail_wait > MAIL_LATE:
		out.append("mail_late")
		if expiry_seconds and oldest_mail_wait >= expiry_seconds:
			out.append("mail_outlives")
	if host_offset != system_offset:
		out.append("zone_differs")
	return out
