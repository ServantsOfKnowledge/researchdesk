"""The Server page in the Desk: versions and updates, health, backups, logs and alerts, and the
updater helper that carries out upgrades and restarts on the server (docs/server.md).

The app can't replace or restart itself from inside its own process, so anything that changes
the installation is a *task* (RD Server Task) that the updater helper picks up. The helper is
opt-in (./resdesk.sh updater on): it polls agent_sync with a shared token, runs only the
actions listed in ACTIONS with checked arguments, and reports progress back. Without it the
page still shows everything and gives the command to run on the server.
"""

from __future__ import annotations

import hmac
import json
import os
import platform
import shutil
from pathlib import Path

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import add_to_date, cint, get_datetime, now_datetime

from sok_resdesk.core import updates as upd

MANAGERS = ("System Manager", "ResDesk Manager")
ADMINS = ("System Manager",)  # upgrades, restarts and resources change the installation
TASK = "RD Server Task"
REPO = "ServantsOfKnowledge/researchdesk"
AGENT_CACHE = "resdesk_agent_facts"
SEEN_WITHIN = 90  # seconds: the helper counts as connected when it synced this recently

# what the helper may be asked to do: action -> (who may ask, one at a time with the others)
ACTIONS = {
	"upgrade": (ADMINS, True),
	"restart": (ADMINS, True),
	"apply_resources": (ADMINS, True),
	"server_backup": (ADMINS, True),
	"check_updates": (MANAGERS, False),
	"logs": (MANAGERS, False),
}
LABELS = {
	"upgrade": "Upgrade",
	"restart": "Restart",
	"apply_resources": "Apply Resource Preset",
	"server_backup": "Server Backup",
	"check_updates": "Check for Updates",
	"logs": "Show Logs",
}
SERVICES = ("web", "workers", "scheduler", "search", "all")
LOG_SERVICES = ("backend", "queue", "scheduler", "frontend", "websocket", "meilisearch", "db", "updater")


def _settings() -> dict:
	return frappe.db.get_singles_dict("RD Settings")


def _is_admin() -> bool:
	return "System Manager" in frappe.get_roles()


# -- the updater helper -------------------------------------------------------------------------


def _agent_token() -> str:
	return frappe.conf.get("resdesk_agent_token") or ""


def helper_configured() -> bool:
	return bool(_agent_token())


def agent_facts() -> dict:
	return frappe.cache.get_value(AGENT_CACHE) or {}


def helper_connected(facts: dict | None = None) -> bool:
	facts = agent_facts() if facts is None else facts
	seen = facts.get("seen")
	return bool(seen and (now_datetime() - get_datetime(seen)).total_seconds() < SEEN_WITHIN)


def desk_control_allowed() -> bool:
	"""Upgrades and restarts may be started from the Desk (RD Settings; on by default)."""
	value = _settings().get("allow_desk_upgrades")
	return value in (None, "") or bool(cint(value))


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=240, seconds=60)
def agent_sync(token: str | None = None, facts=None, job=None) -> dict:
	"""Called every few seconds by the updater helper: it reports what it sees and how its
	current task is going, and gets the next task to run. Needs the shared token."""
	expected = _agent_token()
	if not expected or not token or not hmac.compare_digest(str(token), expected):
		frappe.throw(_("Not allowed."), frappe.PermissionError)
	facts = frappe.parse_json(facts) if facts else {}
	if not isinstance(facts, dict):
		facts = {}
	facts["seen"] = str(now_datetime())
	previous = agent_facts()
	for key in ("tags", "changelog", "frappe_latest", "git"):  # sent now and then, not every sync
		if key not in facts and key in previous:
			facts[key] = previous[key]
	frappe.cache.set_value(AGENT_CACHE, facts, expires_in_sec=3600)
	if job:
		_update_task(frappe.parse_json(job) if isinstance(job, str) else job)
	_expire_lost_tasks()
	frappe.db.commit()
	# after the cache was cleared (a restart), ask for the release list again straight away
	return {"task": _claim_next(), "allowed": desk_control_allowed(), "send_releases": "tags" not in facts}


def _claim_next() -> dict | None:
	rows = frappe.db.sql(
		f"select name, action, args from `tab{TASK}` where status='Queued' order by creation limit 1 for update",
		as_dict=True,
	)
	if not rows:
		return None
	row = rows[0]
	if ACTIONS.get(row.action, (None, False))[1] and not desk_control_allowed():
		frappe.db.sql(
			f"update `tab{TASK}` set status='Cancelled', finished_on=%s, summary=%s where name=%s",
			(
				now_datetime(),
				_("Upgrades and restarts from the Desk are switched off in Settings."),
				row.name,
			),
		)
		frappe.db.commit()
		return None
	frappe.db.sql(
		f"update `tab{TASK}` set status='Running', started_on=%s where name=%s", (now_datetime(), row.name)
	)
	frappe.db.commit()
	return {"name": row.name, "action": row.action, "args": json.loads(row.args or "{}")}


def _update_task(job: dict) -> None:
	name = job.get("task")
	if not name or not frappe.db.exists(TASK, name):
		return
	status = {"running": "Running", "succeeded": "Succeeded", "failed": "Failed"}.get(job.get("status"))
	if not status:
		return
	before = frappe.db.get_value(TASK, name, ["status", "action", "args"], as_dict=True)
	values = {"status": status}
	if job.get("log") is not None:
		values["log"] = str(job["log"])[-60000:]
	if job.get("summary"):
		values["summary"] = str(job["summary"])[:500]
	if status != "Running":
		values["finished_on"] = now_datetime()
		values["exit_code"] = cint(job.get("exit_code"))
	frappe.db.set_value(TASK, name, values, update_modified=True)
	if before.status == "Running" and status in ("Succeeded", "Failed") and before.action == "upgrade":
		version = (agent_facts().get("version") or "") if status == "Succeeded" else ""
		send_alert(
			"upgrade_" + status.lower(),
			"info" if status == "Succeeded" else "bad",
			_("Upgrade finished: now on v{0}.").format(version or "?")
			if status == "Succeeded"
			else _("The upgrade ({0}) did not finish. Nothing was lost; see the task log.").format(name),
			link=f"/app/rd-server-task/{name}",
		)


def _expire_lost_tasks() -> None:
	"""A task the helper stopped reporting on (the server was switched off mid-way, say)."""
	cutoff = add_to_date(now_datetime(), hours=-3)
	frappe.db.sql(
		f"""update `tab{TASK}` set status='Failed', finished_on=%s,
		summary='The updater helper stopped reporting on this task.' where status='Running' and modified < %s""",
		(now_datetime(), cutoff),
	)


def _check_args(action: str, args: dict) -> dict:
	if action == "upgrade":
		try:
			target = upd.safe_release_ref(args.get("target") or "latest")
		except ValueError:
			frappe.throw(_("Choose a release such as v0.11.0, or latest."))
		return {
			"target": target,
			"backup": 1 if cint(args.get("backup", 1)) else 0,
			"frappe": cint(args.get("frappe", 1)),
		}
	if action == "restart":
		service = args.get("service") or "all"
		if service not in SERVICES:
			frappe.throw(_("Unknown part: {0}").format(service))
		return {"service": service}
	if action == "apply_resources":
		preset = args.get("preset") or ""
		if preset not in ("light", "standard", "server"):
			frappe.throw(_("Choose light, standard or server."))
		return {"preset": preset}
	if action == "logs":
		service = args.get("service") or "backend"
		if service not in LOG_SERVICES:
			frappe.throw(_("Unknown part: {0}").format(service))
		return {"service": service, "lines": max(20, min(cint(args.get("lines") or 200), 1000))}
	return {}


@frappe.whitelist()
def request_task(action: str, args=None) -> str:
	"""Ask the updater helper to do something (Server page buttons)."""
	if action not in ACTIONS:
		frappe.throw(_("Unknown action."))
	roles, exclusive = ACTIONS[action]
	frappe.only_for(roles)
	if not helper_configured() or not helper_connected():
		frappe.throw(
			_(
				"The updater helper isn't running, so this has to be done on the server. See Server → "
				"Updater helper for the command, or turn the helper on with: ./resdesk.sh updater on"
			)
		)
	if exclusive and not desk_control_allowed():
		frappe.throw(
			_("Upgrades and restarts from the Desk are switched off in Settings → Server & Updates.")
		)
	args = _check_args(action, frappe.parse_json(args) if args else {})
	if exclusive:
		busy = frappe.db.sql(
			f"select name from `tab{TASK}` where status in ('Queued','Running') and action in %s limit 1",
			([a for a, (_r, ex) in ACTIONS.items() if ex],),
		)
		if busy:
			frappe.throw(_("{0} is still in progress. Wait for it to finish.").format(busy[0][0]))
	task = frappe.get_doc(
		{
			"doctype": TASK,
			"action": action,
			"title": _describe(action, args),
			"args": json.dumps(args),
			"status": "Queued",
			"requested_by": frappe.session.user,
		}
	).insert(ignore_permissions=True)
	return task.name


def _describe(action: str, args: dict) -> str:
	if action == "upgrade":
		return _("Upgrade to {0}").format(args["target"]) + (
			"" if args.get("frappe") else _(" (keep Frappe)")
		)
	if action == "restart":
		return _("Restart {0}").format(args["service"])
	if action == "apply_resources":
		return _("Apply the {0} preset").format(args["preset"])
	if action == "logs":
		return _("Logs: {0}").format(args["service"])
	return _(LABELS[action])


@frappe.whitelist()
def cancel_task(name: str) -> None:
	frappe.only_for(MANAGERS)
	frappe.db.sql(
		f"update `tab{TASK}` set status='Cancelled', finished_on=%s where name=%s and status='Queued'",
		(now_datetime(), name),
	)


@frappe.whitelist()
def get_task(name: str) -> dict:
	frappe.only_for(MANAGERS)
	return frappe.db.get_value(
		TASK,
		name,
		["name", "action", "title", "status", "log", "summary", "started_on", "finished_on", "exit_code"],
		as_dict=True,
	)


# -- versions and updates -----------------------------------------------------------------------


def _get_json(url: str):
	import requests

	r = requests.get(
		url,
		timeout=15,
		headers={
			"User-Agent": "SOK-ResearchDesk/0.11 update check (+https://github.com/ServantsOfKnowledge/researchdesk)",
			"Accept": "application/vnd.github+json",
		},
	)
	r.raise_for_status()
	return r.json() if "json" in r.headers.get("content-type", "") else r.text


def _tags(repo: str, prefix: str) -> list[str]:
	refs = _get_json(f"https://api.github.com/repos/{repo}/git/matching-refs/tags/{prefix}")
	return [r["ref"].rsplit("/", 1)[-1] for r in refs if isinstance(r, dict) and r.get("ref")]


@frappe.whitelist()
def check_updates(quiet: int = 0) -> dict:
	"""Look for new Research Desk releases and Frappe v16 patches (daily, and on request)."""
	if not quiet:
		frappe.only_for(MANAGERS)
	from sok_resdesk import __version__

	repo = frappe.conf.get("resdesk_update_repo") or REPO
	info = {"checked_on": str(now_datetime()), "current": __version__, "error": ""}
	try:
		tags = _tags(repo, "v")
		info["tags"] = tags
		info["latest"] = upd.latest_release(tags)
		if info["latest"] and upd.is_newer(info["latest"], __version__):
			text = _get_json(f"https://raw.githubusercontent.com/{repo}/{info['latest']}/CHANGELOG.md")
			info["notes"] = upd.changelog_sections(text if isinstance(text, str) else "", __version__)
	except Exception as e:
		info["error"] = _("Could not reach GitHub: {0}").format(str(e)[:160])
	try:
		major = upd.parse_version(frappe.__version__)
		info["frappe_latest"] = upd.latest_release(
			_tags("frappe/frappe", f"v{major[0]}."), major[0] if major else None
		)
	except Exception:
		pass
	if helper_connected() and not quiet:
		try:
			request_task("check_updates")  # the helper also fetches from the server's own git remote
		except Exception:
			pass
	frappe.db.set_default("resdesk_updates", json.dumps(info, default=str))
	if info.get("latest") and upd.is_newer(info["latest"], __version__):
		if frappe.db.get_default("resdesk_update_notified") != info["latest"]:
			frappe.db.set_default("resdesk_update_notified", info["latest"])
			send_alert(
				"update_available",
				"info",
				_("Research Desk {0} is available (this server runs v{1}).").format(
					info["latest"], __version__
				),
				link="/app/resdesk-server",
			)
	return updates_view()


def scheduled_update_check() -> None:
	value = _settings().get("check_updates")
	if value is None or cint(value):
		check_updates(quiet=1)


def updates_view() -> dict:
	from sok_resdesk import __version__

	info = json.loads(frappe.db.get_default("resdesk_updates") or "{}")
	facts = agent_facts()
	tags = sorted(
		set((facts.get("tags") or []) + (info.get("tags") or [])),
		key=lambda t: upd.parse_version(t) or (0, 0, 0),
	)
	latest = upd.latest_release(tags) or info.get("latest")
	notes = info.get("notes") or []
	if facts.get("changelog"):
		notes = upd.changelog_sections(facts["changelog"], __version__) or notes
	notes = [n for n in notes if upd.is_newer(n["version"], __version__)]
	return {
		"current": __version__,
		"latest": latest,
		"newer": bool(latest and upd.is_newer(latest, __version__)),
		"releases": upd.releases_between(tags, "0.0.0")[:15],
		"notes": notes,
		"needs_reindex": upd.needs_reindex(notes),
		"frappe": frappe.__version__,
		"frappe_latest": facts.get("frappe_latest") or info.get("frappe_latest"),
		"frappe_newer": upd.is_newer(
			facts.get("frappe_latest") or info.get("frappe_latest"), frappe.__version__
		),
		"checked_on": info.get("checked_on"),
		"error": info.get("error") or "",
		"repo": frappe.conf.get("resdesk_update_repo") or REPO,
	}


# -- health -------------------------------------------------------------------------------------


def _check(key, label, state, detail="", link=""):
	return {"key": key, "label": label, "state": state, "detail": detail, "link": link}


def health() -> list[dict]:
	"""Every part Research Desk needs, as ok / warn / bad / off, with a sentence each."""
	from datetime import UTC, datetime

	from frappe.utils.background_jobs import get_redis_conn

	from sok_resdesk import holding

	s = _settings()
	out = [_check("database", _("Database"), "ok", _("answering"))]
	try:
		frappe.cache.ping()
		out.append(_check("cache", _("Cache (Redis)"), "ok", _("answering")))
	except Exception as e:
		out.append(_check("cache", _("Cache (Redis)"), "bad", str(e)[:120]))

	try:
		from rq import Worker

		conn = get_redis_conn()
		conn.ping()
		workers = Worker.all(connection=conn)
		now = datetime.now(UTC)
		fresh = [
			w
			for w in workers
			if not w.last_heartbeat or (now - w.last_heartbeat.replace(tzinfo=UTC)).total_seconds() < 600
		]
		if holding.is_paused():
			out.append(
				_check(
					"workers",
					_("Background workers"),
					"warn",
					_("{0} running; Pause All is on").format(len(fresh)),
					"/app/resdesk-jobs",
				)
			)
		elif fresh:
			out.append(
				_check(
					"workers",
					_("Background workers"),
					"ok",
					_("{0} running").format(len(fresh)),
					"/app/resdesk-jobs",
				)
			)
		else:
			out.append(
				_check(
					"workers",
					_("Background workers"),
					"bad",
					_("none running: ingests and exports wait"),
					"/app/resdesk-jobs",
				)
			)
	except Exception as e:
		out.append(
			_check(
				"workers",
				_("Background workers"),
				"bad",
				_("job queue not reachable: {0}").format(str(e)[:100]),
			)
		)

	out.append(_scheduler_check())

	from sok_resdesk.search import MeiliClient, SearchError

	try:
		MeiliClient.from_settings()._req("GET", "/health")
		out.append(_check("search", _("Search engine"), "ok", _("answering")))
	except SearchError as e:
		out.append(_check("search", _("Search engine"), "bad", str(e)[:120]))

	disk = disk_usage()
	limit = cint(s.get("alert_disk_percent")) or 90
	state = "bad" if disk["percent"] >= limit else "warn" if disk["percent"] >= limit - 10 else "ok"
	out.append(
		_check(
			"disk",
			_("Disk"),
			state,
			_("{0}% used, {1} GB free").format(disk["percent"], round(disk["free"] / 1024**3, 1)),
		)
	)

	out.append(_backup_check(s))

	from sok_resdesk.capacity import health_check

	out.append(health_check())

	day = add_to_date(now_datetime(), days=-1)
	errors = frappe.db.count("Error Log", {"creation": (">", day)})
	failed = failed_job_count()
	out.append(
		_check(
			"errors",
			_("Errors"),
			"warn" if errors or failed else "ok",
			_("{0} errors logged and {1} failed jobs in the last day").format(errors, failed)
			if errors or failed
			else _("none in the last day"),
			"/app/error-log",
		)
	)

	if helper_configured():
		facts = agent_facts()
		if helper_connected(facts):
			out.append(
				_check(
					"helper", _("Updater helper"), "ok", _("connected ({0})").format(facts.get("mode") or "")
				)
			)
		else:
			out.append(
				_check(
					"helper",
					_("Updater helper"),
					"bad",
					_("not reporting: is it running? ./resdesk.sh updater status"),
				)
			)
	else:
		out.append(
			_check(
				"helper", _("Updater helper"), "off", _("off: upgrades and restarts are done on the server")
			)
		)

	view = updates_view()
	if view["newer"]:
		out.append(_check("updates", _("Updates"), "info", _("{0} is available").format(view["latest"])))
	else:
		out.append(
			_check(
				"updates", _("Updates"), "ok", _("up to date") if view.get("latest") else _("not checked yet")
			)
		)
	return out


def _scheduler_check() -> dict:
	from frappe.utils.scheduler import is_scheduler_inactive

	if is_scheduler_inactive(verbose=False):
		return _check(
			"scheduler",
			_("Scheduler"),
			"warn",
			_("switched off: scheduled ingests, backups and alerts don't run"),
		)
	last = frappe.db.get_value(
		"Scheduled Job Type", {"method": "sok_resdesk.jobs.apply_quiet_hours"}, "last_execution"
	)
	if last and (now_datetime() - get_datetime(last)).total_seconds() < 20 * 60:
		return _check("scheduler", _("Scheduler"), "ok", _("running"))
	return _check(
		"scheduler",
		_("Scheduler"),
		"bad",
		_("not running: last seen {0}").format(str(last or _("never"))[:16]),
	)


def disk_usage() -> dict:
	total, used, free = shutil.disk_usage(frappe.get_site_path())
	return {"total": total, "used": used, "free": free, "percent": round(used * 100 / total) if total else 0}


def failed_job_count() -> int:
	try:
		from frappe.utils.background_jobs import get_queues, get_redis_conn
		from rq.registry import FailedJobRegistry

		conn = get_redis_conn()
		return sum(len(FailedJobRegistry(queue=q)) for q in get_queues(connection=conn))
	except Exception:
		return 0


# -- backups ------------------------------------------------------------------------------------


def _backup_dir() -> Path:
	return Path(frappe.get_site_path("private", "backups"))


def list_backups() -> list[dict]:
	"""Backups made by Frappe (Desk, schedule, ./resdesk.sh backup), newest first, one row per set."""
	d = _backup_dir()
	if not d.exists():
		return []
	sets = {}
	site = frappe.local.site.replace(".", "_")
	for f in d.iterdir():
		if not f.is_file():
			continue
		key = f.name.rsplit("-" + site, 1)[0]
		kind = (
			"database"
			if f.name.endswith(".sql.gz")
			else "private files"
			if "private-files" in f.name
			else "files"
			if f.name.endswith("files.tar") or f.name.endswith("files.tgz")
			else "config"
		)
		entry = sets.setdefault(key, {"name": key, "files": [], "size": 0, "when": 0})
		entry["files"].append({"name": f.name, "kind": kind, "size": f.stat().st_size})
		entry["size"] += f.stat().st_size
		entry["when"] = max(entry["when"], f.stat().st_mtime)
	out = sorted(sets.values(), key=lambda x: x["when"], reverse=True)
	for e in out:
		e["when"] = _ts(e["when"])
		e["files"].sort(key=lambda f: ("database", "files", "private files", "config").index(f["kind"]))
	return out


def _ts(epoch: float) -> str:
	from datetime import UTC, datetime

	from frappe.utils.data import convert_utc_to_system_timezone

	local = convert_utc_to_system_timezone(datetime.fromtimestamp(epoch, tz=UTC))
	return str(local.replace(microsecond=0, tzinfo=None))


def _backup_check(s: dict) -> dict:
	last = json.loads(frappe.db.get_default("resdesk_last_backup") or "{}")
	if last and not last.get("ok"):
		return _check(
			"backups",
			_("Backups"),
			"bad",
			_("the last backup failed: {0}").format(last.get("error", "")[:120]),
		)
	sets = list_backups()
	schedule = s.get("backup_schedule") or "Off"
	newest = get_datetime(sets[0]["when"]) if sets else None
	age_h = (now_datetime() - newest).total_seconds() / 3600 if newest else None
	limit = {"Daily": 36, "Weekly": 8 * 24}.get(schedule)
	if not sets:
		return _check("backups", _("Backups"), "warn", _("no backups yet"))
	if limit and age_h > limit:
		return _check(
			"backups", _("Backups"), "bad", _("the newest backup is {0} hours old").format(int(age_h))
		)
	if schedule == "Off":
		return _check(
			"backups", _("Backups"), "warn", _("no schedule; newest {0}").format(sets[0]["when"][:16])
		)
	return _check(
		"backups", _("Backups"), "ok", _("{0}; newest {1}").format(_(schedule), sets[0]["when"][:16])
	)


@frappe.whitelist()
def take_backup(with_files: int = 0) -> dict:
	frappe.only_for(MANAGERS)
	frappe.enqueue(
		"sok_resdesk.server.run_backup",
		queue="long",
		timeout=4 * 3600,
		with_files=cint(with_files),
		who=frappe.session.user,
		job_id=f"resdesk-backup-{frappe.local.site}",
		deduplicate=True,
	)
	return {"message": _("Backup started. It appears in the list below when it is ready.")}


def run_backup(with_files: int = 0, who: str = "Schedule") -> None:
	from frappe.utils.backups import new_backup

	try:
		odb = new_backup(ignore_files=not cint(with_files), force=True)
		result = {
			"ok": True,
			"when": str(now_datetime()),
			"by": who,
			"file": os.path.basename(odb.backup_path_db),
		}
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(title="Research Desk: backup failed")
		result = {"ok": False, "when": str(now_datetime()), "by": who, "error": str(e)[:300]}
	frappe.db.set_default("resdesk_last_backup", json.dumps(result))
	frappe.db.commit()
	if not result["ok"]:
		send_alert(
			"backup_failed",
			"bad",
			_("The backup failed: {0}").format(result["error"]),
			link="/app/resdesk-server",
		)
	else:
		trim_backups(cint(_settings().get("backup_keep")) or 7)


def trim_backups(keep: int) -> int:
	"""Keep the newest `keep` backup sets; delete older ones. Returns how many sets were removed."""
	sets = list_backups()
	removed = 0
	for old in sets[max(keep, 1) :]:
		for f in old["files"]:
			(_backup_dir() / f["name"]).unlink(missing_ok=True)
		removed += 1
	return removed


def scheduled_backup() -> None:
	"""Daily at night (hooks.py): back up when Settings → Server & Updates asks for it."""
	s = _settings()
	schedule = s.get("backup_schedule") or "Off"
	if schedule == "Off" or (schedule == "Weekly" and now_datetime().weekday() != 6):
		return
	run_backup(with_files=cint(s.get("backup_with_files")), who="Schedule")


@frappe.whitelist()
def delete_backup(name: str) -> None:
	frappe.only_for(ADMINS)
	for s in list_backups():
		if s["name"] == name:
			for f in s["files"]:
				(_backup_dir() / f["name"]).unlink(missing_ok=True)
			return
	frappe.throw(_("No such backup."))


# -- logs ---------------------------------------------------------------------------------------


def _log_dir() -> Path:
	from frappe.utils import get_bench_path

	return Path(get_bench_path()) / "logs"


@frappe.whitelist()
def logs(source: str = "errors", name: str = "", lines: int = 200) -> dict:
	"""Recent errors, failed jobs, or the end of a log file (Server → Logs)."""
	frappe.only_for(MANAGERS)
	lines = max(20, min(cint(lines) or 200, 2000))
	if source == "errors":
		rows = frappe.get_all(
			"Error Log",
			fields=["name", "method", "creation", "error"],
			order_by="creation desc",
			limit=50,
		)
		for r in rows:
			r["error"] = (r.get("error") or "").strip().splitlines()[-1:][0][:300] if r.get("error") else ""
		return {"rows": rows}
	if source == "failed_jobs":
		return {"rows": _failed_jobs()}
	if source == "files":
		d = _log_dir()
		files = (
			sorted(
				(
					{"name": f.name, "size": f.stat().st_size, "modified": _ts(f.stat().st_mtime)}
					for f in d.glob("*.log")
				),
				key=lambda f: f["modified"],
				reverse=True,
			)
			if d.exists()
			else []
		)
		text = ""
		if name:
			if "/" in name or name not in {f["name"] for f in files}:
				frappe.throw(_("No such log file."))
			text = _tail(d / name, lines)
		return {"files": files, "text": text}
	frappe.throw(_("Unknown log source."))


def _tail(path: Path, lines: int) -> str:
	with open(path, "rb") as f:
		f.seek(0, os.SEEK_END)
		size = f.tell()
		f.seek(max(0, size - 256 * 1024))
		data = f.read().decode("utf-8", "replace")
	return "\n".join(data.splitlines()[-lines:])


def _failed_jobs() -> list[dict]:
	try:
		from frappe.utils.background_jobs import get_queues, get_redis_conn
		from rq.job import Job
		from rq.registry import FailedJobRegistry

		conn = get_redis_conn()
		out = []
		# get_queues: the queues under their real names (Frappe prefixes them with the bench's)
		for queue in get_queues(connection=conn):
			q = queue.name.split(":")[-1]
			registry = FailedJobRegistry(queue=queue)
			for job_id in registry.get_job_ids()[-30:]:
				try:
					job = Job.fetch(job_id, connection=conn)
				except Exception:
					continue
				kw = job.kwargs or {}
				exc = (job.exc_info or "").strip().splitlines()
				out.append(
					{
						"id": job_id.split("||")[-1],
						"method": kw.get("job_name") or kw.get("method") or job.func_name,
						"ended_at": str(job.ended_at or "")[:19],
						"error": exc[-1][:300] if exc else "",
						"queue": q,
					}
				)
		return sorted(out, key=lambda j: j["ended_at"], reverse=True)[:50]
	except Exception:
		return []


# -- alerts -------------------------------------------------------------------------------------


def _managers() -> list[str]:
	users = frappe.db.sql(
		"""select distinct u.name from `tabUser` u join `tabHas Role` r on r.parent=u.name
		where r.role in %s and u.enabled=1 and u.user_type='System User' and u.name not in ('Guest')""",
		(MANAGERS,),
	)
	return [u[0] for u in users]


def send_alert(key: str, severity: str, message: str, link: str = "") -> None:
	"""Tell managers: a Desk notification, email (if outgoing email is set up) and a webhook."""
	s = _settings()
	title = frappe.db.get_single_value("RD Settings", "portal_title") or "Research Desk"
	subject = f"[{title}] {message}"[:140]
	for user in _managers():
		try:
			frappe.get_doc(
				{
					"doctype": "Notification Log",
					"for_user": user,
					"type": "Alert",
					"subject": subject,
					"email_content": message,
					"link": link or "/app/resdesk-server",
				}
			).insert(ignore_permissions=True)
		except Exception:
			frappe.log_error(title="Research Desk: could not add a Desk alert")
	if cint(s.get("alert_email") if s.get("alert_email") is not None else 1):
		recipients = set(_managers()) - {"Administrator"}
		recipients |= {
			e.strip() for e in (s.get("alert_emails") or "").replace("\n", ",").split(",") if "@" in e
		}
		if recipients and frappe.db.exists("Email Account", {"enable_outgoing": 1}):
			try:
				url = frappe.utils.get_url(link or "/app/resdesk-server")
				frappe.sendmail(
					recipients=sorted(recipients),
					subject=subject,
					message=f"<p>{frappe.utils.escape_html(message)}</p><p><a href='{url}'>{url}</a></p>",
				)
			except Exception:
				frappe.log_error(title="Research Desk: could not email an alert")
	url = (s.get("alert_webhook_url") or "").strip()
	if url.startswith(("http://", "https://")):
		try:
			import requests

			requests.post(
				url,
				json={
					"text": subject,
					"event": key,
					"severity": severity,
					"message": message,
					"site": frappe.local.site,
					"link": frappe.utils.get_url(link or "/app/resdesk-server"),
					"at": str(now_datetime()),
				},
				timeout=10,
			)
		except Exception:
			frappe.log_error(title="Research Desk: could not post an alert to the webhook")


def watch() -> None:
	"""Every 10 minutes: alert when a part goes wrong, and again when it is fine again."""
	previous = json.loads(frappe.db.get_default("resdesk_alert_state") or "{}")
	current = {}
	for c in health():
		if c["key"] in ("updates", "errors"):
			continue
		bad = c["state"] == "bad"
		current[c["key"]] = "bad" if bad else "ok"
		link = c.get("link") or "/app/resdesk-server"
		if c["key"] == "capacity" and c["state"] == "warn":
			current["capacity"] = "warn"  # 90% of the book limit: worth one alert too
			if previous.get("capacity") not in ("warn", "bad"):
				send_alert("capacity", "warn", f"{c['label']}: {c['detail']}", link=link)
			continue
		was_bad = previous.get(c["key"]) in (("bad", "warn") if c["key"] == "capacity" else ("bad",))
		if bad and previous.get(c["key"]) != "bad":
			send_alert(c["key"], "bad", f"{c['label']}: {c['detail']}", link=link)
		elif not bad and was_bad:
			send_alert(c["key"], "ok", _("{0} is fine again.").format(c["label"]), link="/app/resdesk-server")
	frappe.db.set_default("resdesk_alert_state", json.dumps(current))
	frappe.db.commit()


@frappe.whitelist()
def test_alert() -> dict:
	frappe.only_for(MANAGERS)
	send_alert("test", "info", _("This is a test alert from the Server page."), link="/app/resdesk-server")
	return {"message": _("Test alert sent to the Desk, email (if set up) and the webhook (if set).")}


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=60, seconds=60)
def ping() -> dict:
	"""For uptime monitors (Uptime Kuma, a load balancer…): ok or degraded, nothing more."""
	try:
		checks = {
			c["key"]: c["state"] for c in health() if c["key"] in ("cache", "workers", "scheduler", "search")
		}
	except Exception:
		checks = {"health": "bad"}
	ok = all(v != "bad" for v in checks.values())
	if not ok:
		frappe.local.response.http_status_code = 503
	return {"status": "ok" if ok else "degraded"}


# -- the page -----------------------------------------------------------------------------------


@frappe.whitelist()
def status() -> dict:
	frappe.only_for(MANAGERS)
	from sok_resdesk import __version__

	facts = agent_facts()
	s = _settings()
	return {
		"now": str(now_datetime()),
		"version": __version__,
		"frappe": frappe.__version__,
		"python": platform.python_version(),
		"site": frappe.local.site,
		"mode": facts.get("mode") or ("docker" if os.environ.get("RESDESK_RESOURCES") else "native"),
		"updates": updates_view(),
		"health": health(),
		"disk": disk_usage(),
		"backups": list_backups()[:20],
		"last_backup": json.loads(frappe.db.get_default("resdesk_last_backup") or "{}"),
		"backup_schedule": s.get("backup_schedule") or "Off",
		"backup_keep": cint(s.get("backup_keep")) or 7,
		"backup_with_files": cint(s.get("backup_with_files")),
		"helper": {
			"configured": helper_configured(),
			"connected": helper_connected(facts),
			"seen": facts.get("seen"),
			"mode": facts.get("mode"),
			"services": facts.get("services") or [],
			"host_disk": facts.get("disk"),
			"git": facts.get("git") or {},
			"agent_version": facts.get("agent_version"),
			"allowed": desk_control_allowed(),
		},
		"tasks": frappe.get_all(
			TASK,
			fields=[
				"name",
				"action",
				"title",
				"status",
				"requested_by",
				"creation",
				"started_on",
				"finished_on",
				"summary",
			],
			order_by="creation desc",
			limit=12,
		),
		"alerts": {
			"email": cint(s.get("alert_email") if s.get("alert_email") is not None else 1),
			"email_ready": bool(frappe.db.exists("Email Account", {"enable_outgoing": 1})),
			"webhook": bool((s.get("alert_webhook_url") or "").strip()),
		},
		"is_admin": _is_admin(),
		"resource_preset": s.get("resource_preset") or "",
		"capacity": _capacity(),
	}


def _capacity() -> dict:
	from sok_resdesk.capacity import status as capacity_status

	return capacity_status()
