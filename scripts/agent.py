#!/usr/bin/env python3
"""The updater helper: lets the Server page in the Desk upgrade, restart and back up this install.

Turned on with ./resdesk.sh updater on (docs/server.md). It runs next to Research Desk (a small
container on Docker installs, a process in the Procfile on native ones), and every few seconds:

  1. tells the site what it sees: version, git state, which parts are running, disk space;
  2. reports on the task it is running (log and result);
  3. picks up the next task the Desk asked for, if any.

It only does the things in TASKS below, with checked arguments, using the same commands a
person would type (./upgrade.sh, ./resdesk.sh …). Long tasks run detached, so they carry on
while the containers or processes they restart (this helper included) come and go.
Standard library only.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

AGENT_VERSION = "1"
ROOT = os.environ.get("RESDESK_DIR") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(ROOT, "logs", ".updater-task.json")
IN_DOCKER = os.environ.get("RESDESK_IN_DOCKER") == "1"
INTERVAL = 5
RELEASE = re.compile(r"^(latest|main|v\d+\.\d+\.\d+)$")
DOCKER_PARTS = {
	"web": ["backend", "websocket", "frontend"],
	"workers": ["queue"],
	"scheduler": ["scheduler"],
	"search": ["meilisearch"],
	"all": ["backend", "websocket", "queue", "scheduler", "meilisearch", "frontend"],
}
LOG_PARTS = {"backend", "queue", "scheduler", "frontend", "websocket", "meilisearch", "db", "updater"}


def log(msg: str) -> None:
	print(time.strftime("%Y-%m-%d %H:%M:%S"), msg, flush=True)


def env_file() -> dict:
	out = {}
	try:
		with open(os.path.join(ROOT, ".env")) as f:
			for line in f:
				line = line.strip()
				if "=" in line and not line.startswith("#"):
					k, v = line.split("=", 1)
					out[k.strip()] = v.strip().strip('"').strip("'")
	except OSError:
		pass
	return out


def run(cmd, timeout=60, env=None) -> tuple[int, str]:
	try:
		p = subprocess.run(
			cmd,
			cwd=ROOT,
			capture_output=True,
			text=True,
			timeout=timeout,
			env={**os.environ, **(env or {})},
		)
		return p.returncode, (p.stdout + p.stderr).strip()
	except (OSError, subprocess.TimeoutExpired) as e:
		return 1, str(e)


def compose_env(env: dict) -> dict:
	"""What docker compose needs from .env (it reads the file itself; developer mode and HTTPS
	add a file each)."""
	extra = {}
	if not env.get("COMPOSE_FILE") and (env.get("DEV_MODE") == "1" or env.get("HTTPS") == "1"):
		files = ["compose.yaml"]
		if env.get("DEV_MODE") == "1":
			files.append("compose.dev.yaml")
		if env.get("HTTPS") == "1":
			files.append("compose.https.yaml")
		extra["COMPOSE_FILE"] = ":".join(files)
	return extra


def version() -> str:
	try:
		with open(os.path.join(ROOT, "sok_resdesk", "__init__.py")) as f:
			m = re.search(r'__version__\s*=\s*"([^"]+)"', f.read())
			return m.group(1) if m else ""
	except OSError:
		return ""


# -- what the helper sees ------------------------------------------------------------------------


def services(env: dict) -> list[dict]:
	if IN_DOCKER:
		code, out = run(["docker", "compose", "ps", "-a", "--format", "json"], env=compose_env(env))
		if code:
			return [{"service": "docker", "state": "unknown", "status": out[:200]}]
		rows = []
		for line in out.splitlines():
			try:
				items = json.loads(line)
			except ValueError:
				continue
			for c in items if isinstance(items, list) else [items]:
				if c.get("Service") in ("configurator", "create-site"):
					continue
				rows.append(
					{
						"service": c.get("Service"),
						"name": c.get("Name"),
						"state": c.get("State"),
						"status": c.get("Status"),
						"health": c.get("Health") or "",
					}
				)
		return sorted(rows, key=lambda r: (r["service"] or "", r["name"] or ""))
	rows = []
	for label, pattern in (
		("web", "gunicorn|bench serve|frappe serve"),
		("workers", "frappe worker"),
		("scheduler", "frappe schedule"),
		("websocket", "socketio.js"),
		("search", "meilisearch"),
		("redis", "redis-server"),
	):
		code, out = run(["pgrep", "-fc", pattern], timeout=10)
		n = int(out) if not code and out.strip().isdigit() else 0
		rows.append({"service": label, "state": "running" if n else "stopped", "status": f"{n} process(es)"})
	return rows


def disk() -> dict:
	total, used, free = shutil.disk_usage(ROOT)
	return {"total": total, "free": free, "percent": round(used * 100 / total) if total else 0}


def git_facts() -> dict:
	facts = {}
	for key, cmd in (
		("head", ["git", "rev-parse", "--short", "HEAD"]),
		("describe", ["git", "describe", "--tags", "--always"]),
		("branch", ["git", "symbolic-ref", "--quiet", "--short", "HEAD"]),
		("remote", ["git", "remote", "get-url", "origin"]),
	):
		code, out = run(cmd, timeout=15)
		facts[key] = out if not code else ""
	code, out = run(["git", "status", "--porcelain", "--untracked-files=no"], timeout=30)
	facts["local_changes"] = bool(out.strip()) if not code else None
	return facts


def release_facts(fetch: bool) -> dict:
	"""Releases from the server's own git remote (what an upgrade would install)."""
	if fetch:
		run(["git", "fetch", "--quiet", "--tags", "origin"], timeout=120)
	code, out = run(["git", "tag", "-l", "v*"], timeout=15)
	tags = [t for t in out.split() if RELEASE.match(t)] if not code else []
	latest = max(tags, key=lambda t: tuple(int(x) for x in t[1:].split(".")), default="")
	changelog = ""
	if latest:
		code, text = run(["git", "show", f"{latest}:CHANGELOG.md"], timeout=15)
		changelog = text[:200000] if not code else ""
	frappe_latest = ""
	env = env_file()
	major = (env.get("FRAPPE_BRANCH") or "version-16").rsplit("-", 1)[-1]
	code, out = run(
		["git", "ls-remote", "--tags", "--refs", "https://github.com/frappe/frappe", f"refs/tags/v{major}.*"],
		timeout=60,
	)
	if not code:
		found = [ln.rsplit("/", 1)[-1] for ln in out.splitlines() if re.search(r"/v\d+\.\d+\.\d+$", ln)]
		if found:
			frappe_latest = max(found, key=lambda t: tuple(int(x) for x in t[1:].split(".")))
	return {"tags": tags, "changelog": changelog, "frappe_latest": frappe_latest, "git": git_facts()}


# -- talking to the site --------------------------------------------------------------------------


def sync(url: str, site: str, token: str, facts: dict, job: dict | None) -> dict:
	data = {"token": token, "facts": json.dumps(facts)}
	if job:
		data["job"] = json.dumps(job)
	req = urllib.request.Request(
		url.rstrip("/") + "/api/method/sok_resdesk.server.agent_sync",
		data=urllib.parse.urlencode(data).encode(),
		headers={"X-Frappe-Site-Name": site, "Accept": "application/json", "Host": site},
	)
	with urllib.request.urlopen(req, timeout=20) as r:
		return json.loads(r.read().decode()).get("message") or {}


# -- tasks -----------------------------------------------------------------------------------------


def command_for(action: str, args: dict, env: dict) -> list[str] | None:
	"""The shell command for a task, or None when it isn't allowed here."""
	native = env.get("INSTALL_MODE") == "native"
	if action == "upgrade":
		target = str(args.get("target") or "latest")
		if not RELEASE.match(target):
			return None
		cmd = ["./upgrade.sh", "--yes"]
		cmd += [] if target == "latest" else ["--main"] if target == "main" else [target]
		cmd += [] if args.get("backup", 1) else ["--no-backup"]
		cmd += [] if args.get("frappe", 1) else ["--no-frappe"]
		return cmd
	if action == "restart":
		part = args.get("service") or "all"
		if native:
			return ["./resdesk.sh", "restart"] if part == "all" else None
		if part not in DOCKER_PARTS:
			return None
		return ["docker", "compose", "restart", *DOCKER_PARTS[part]]
	if action == "apply_resources":
		preset = args.get("preset")
		return ["./resdesk.sh", "resources", preset] if preset in ("light", "standard", "server") else None
	if action == "server_backup":
		return ["./resdesk.sh", "backup"]
	if action == "install_requirements":
		# native installs only: on Docker the tools come with the image (upgrade instead)
		part = args.get("part")
		return (
			["./resdesk.sh", "requirements", "install", part]
			if native and part in ("python", "ocr")
			else None
		)
	return None


def own_container() -> dict:
	code, out = run(["docker", "inspect", socket.gethostname()], timeout=20)
	try:
		return json.loads(out)[0] if not code else {}
	except (ValueError, IndexError):
		return {}


def start_detached(task: str, cmd: list[str], env: dict) -> dict:
	"""Start a long task so that it outlives this helper (an upgrade restarts it)."""
	os.makedirs(os.path.join(ROOT, "logs"), exist_ok=True)
	logf, exitf = f"logs/task-{task}.log", f"logs/task-{task}.exit"
	for f in (logf, exitf):
		try:
			os.remove(os.path.join(ROOT, f))
		except OSError:
			pass
	inner = f"{shlex.join(cmd)} > {logf} 2>&1; echo $? > {exitf}"
	state = {"task": task, "cmd": cmd, "log": logf, "exit": exitf, "started": time.time()}
	if IN_DOCKER:
		me = own_container()
		image = (me.get("Config") or {}).get("Image") or "sok-resdesk-updater:local"
		networks = list(((me.get("NetworkSettings") or {}).get("Networks") or {}).keys())
		sock = env.get("DOCKER_SOCKET") or "/var/run/docker.sock"
		name = f"resdesk-task-{task.lower()}"
		run(["docker", "rm", "-f", name], timeout=30)
		docker = ["docker", "run", "-d", "--name", name, "--label", "org.researchdesk.task=" + task]
		if networks:
			docker += ["--network", networks[0]]
		docker += ["-v", f"{sock}:/var/run/docker.sock", "-v", f"{ROOT}:{ROOT}", "-w", ROOT]
		docker += ["-e", "HOME=/tmp", "-e", "RESDESK_HEALTH_URL=http://frontend:8080"]
		if os.getuid() != 0:
			docker += ["--user", f"{os.getuid()}:{os.getgid()}"]
			docker += [x for g in os.getgroups() if g != os.getgid() for x in ("--group-add", str(g))]
		docker += [image, "bash", "-c", inner]
		code, out = run(docker, timeout=120)
		if code:
			with open(os.path.join(ROOT, logf), "w") as f:
				f.write(f"Could not start the task container:\n{out}\n")
			with open(os.path.join(ROOT, exitf), "w") as f:
				f.write("1\n")
		state["container"] = name
	else:
		# double fork: the task is not a child of this helper, so stopping the bench (which
		# an upgrade or restart does) doesn't stop the task
		subprocess.Popen(
			["bash", "-c", f"nohup bash -c {shlex.quote(inner)} >/dev/null 2>&1 &"],
			cwd=ROOT,
			start_new_session=True,
			stdin=subprocess.DEVNULL,
			stdout=subprocess.DEVNULL,
			stderr=subprocess.DEVNULL,
		)
	save_state(state)
	return state


def save_state(state: dict | None) -> None:
	if state is None:
		try:
			os.remove(STATE)
		except OSError:
			pass
		return
	with open(STATE, "w") as f:
		json.dump(state, f)


def load_state() -> dict | None:
	try:
		with open(STATE) as f:
			return json.load(f)
	except (OSError, ValueError):
		return None


def tail(path: str, limit: int = 60000) -> str:
	try:
		with open(os.path.join(ROOT, path), "rb") as f:
			f.seek(0, os.SEEK_END)
			f.seek(max(0, f.tell() - limit))
			text = f.read().decode("utf-8", "replace")
	except OSError:
		return ""
	return re.sub(r"\x1b\[[0-9;]*m", "", text)  # no terminal colours in the Desk


def job_report(state: dict) -> dict:
	"""How the detached task is doing: running, or finished with its exit code."""
	text = tail(state["log"])
	code = None
	try:
		with open(os.path.join(ROOT, state["exit"])) as f:
			code = int(f.read().strip() or "1")
	except (OSError, ValueError):
		if state.get("container"):
			rc, out = run(["docker", "inspect", "-f", "{{.State.Status}}", state["container"]], timeout=20)
			if rc or out.strip() in ("exited", "dead"):
				code = 1  # the task container is gone without writing its result
				text += "\n(The task container stopped without reporting a result.)"
		elif time.time() - state.get("started", 0) > 6 * 3600:
			code = 1
			text += "\n(No result after six hours.)"
	if code is None:
		return {"task": state["task"], "status": "running", "log": text}
	summary = last_line(text) if code else "Done."
	return {
		"task": state["task"],
		"status": "failed" if code else "succeeded",
		"exit_code": code,
		"log": text,
		"summary": summary,
	}


def last_line(text: str) -> str:
	lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
	return lines[-1][:300] if lines else "Failed."


def inline_task(task: dict, env: dict) -> dict:
	"""Quick tasks that don't change anything: answered straight away."""
	action, args = task["action"], task.get("args") or {}
	if action == "check_updates":
		facts = release_facts(fetch=True)
		latest = max(facts["tags"], key=lambda t: tuple(int(x) for x in t[1:].split(".")), default="none")
		return {
			"task": task["name"],
			"status": "succeeded",
			"exit_code": 0,
			"summary": f"Latest release on the server's git remote: {latest}",
			"log": "\n".join(facts["tags"][-20:]),
			"_facts": facts,
		}
	if action == "logs":
		part = args.get("service") or "backend"
		lines = str(max(20, min(int(args.get("lines") or 200), 1000)))
		if part not in LOG_PARTS:
			return {"task": task["name"], "status": "failed", "exit_code": 1, "summary": "Unknown part."}
		if IN_DOCKER:
			code, out = run(
				["docker", "compose", "logs", "--no-color", "--tail", lines, part],
				timeout=60,
				env=compose_env(env),
			)
		else:
			bench = env.get("BENCH_DIR") or os.path.expanduser("~/researchdesk-bench")
			name = {
				"backend": "web.error.log",
				"queue": "worker.error.log",
				"meilisearch": "meilisearch.log",
			}.get(part, "bench-start.log")
			code, out = run(["tail", "-n", lines, os.path.join(bench, "logs", name)], timeout=30)
		return {
			"task": task["name"],
			"status": "failed" if code else "succeeded",
			"exit_code": code,
			"summary": f"Last {lines} lines from {part}",
			"log": re.sub(r"\x1b\[[0-9;]*m", "", out)[-60000:],
		}
	return {"task": task["name"], "status": "failed", "exit_code": 1, "summary": "This helper can't do that."}


# -- main loop -----------------------------------------------------------------------------------


def main() -> None:
	me = os.path.abspath(__file__)
	started_mtime = os.path.getmtime(me)
	env = env_file()
	site = env.get("SITE_NAME") or "resdesk.localhost"
	url = os.environ.get("RESDESK_AGENT_URL") or f"http://127.0.0.1:{env.get('HTTP_PORT') or '8000'}"
	log(f"Research Desk updater helper for {site} ({'docker' if IN_DOCKER else 'native'}) talking to {url}")
	slow, releases, pending_report, extra = 0.0, 0.0, None, {}
	facts = {}
	while True:
		env = env_file()
		token = env.get("RESDESK_AGENT_TOKEN") or ""
		if not token:
			log("No RESDESK_AGENT_TOKEN in .env: turn the helper on with ./resdesk.sh updater on")
			time.sleep(30)
			continue
		now = time.time()
		facts.update(
			{
				"version": version(),
				"mode": "docker" if IN_DOCKER else "native",
				"agent_version": AGENT_VERSION,
				"host": socket.gethostname() if not IN_DOCKER else "",
			}
		)
		send = dict(facts)
		if now - slow > 30:
			send["services"], send["disk"] = services(env), disk()
			facts["services"], facts["disk"] = send["services"], send["disk"]
			slow = now
		if now - releases > 6 * 3600:
			send.update(release_facts(fetch=True))
			releases = now
		send.update(extra)
		state = load_state()
		report = pending_report or (job_report(state) if state else None)
		try:
			answer = sync(url, site, token, send, report)
			extra = {}
			if answer.get("send_releases"):
				releases = 0  # the site lost what we told it (restarted): tell it again next time
			if report and report["status"] != "running":
				if state and state.get("task") == report["task"]:
					if state.get("container"):
						run(["docker", "rm", "-f", state["container"]], timeout=30)
					for f in (state["log"], state["exit"]):  # the log is kept in the task itself
						try:
							os.remove(os.path.join(ROOT, f))
						except OSError:
							pass
					save_state(None)
					releases = 0  # after an upgrade, report the new git state soon
				pending_report = None
			task = answer.get("task")
			if task and not load_state():
				log(f"task {task['name']}: {task['action']} {task.get('args') or ''}")
				if task["action"] in ("check_updates", "logs"):
					result = inline_task(task, env)
					extra = result.pop("_facts", {})
					pending_report = result
				else:
					cmd = command_for(task["action"], task.get("args") or {}, env)
					if cmd is None:
						pending_report = {
							"task": task["name"],
							"status": "failed",
							"exit_code": 1,
							"summary": "Not possible on this install.",
						}
					else:
						start_detached(task["name"], cmd, env)
				continue  # report straight away
		except urllib.error.HTTPError as e:
			if e.code == 403:
				log("The site refused the token: run ./resdesk.sh updater on again.")
				time.sleep(30)
			else:
				log(f"site answered {e.code}")
		except (urllib.error.URLError, OSError, ValueError) as e:
			log(f"site not reachable ({e}); trying again")  # normal while it restarts
		if os.path.getmtime(me) != started_mtime and not load_state():
			log("new version of the helper: restarting it")
			os.execv(sys.executable, [sys.executable, me])
		time.sleep(INTERVAL)


if __name__ == "__main__":
	main()
