#!/usr/bin/env python3
"""Why the updater helper isn't working, and putting it right (./resdesk.sh updater doctor [--fix]).

Run on the server. It looks at what kind of install this is (Docker, native or Coolify), at the values
in .env that the helper depends on, and at the live wiring (the helper's container or process, the
token in the site configuration, whether the helper can reach the site), and says what is wrong in
plain words. With --fix it repairs what is safe to repair: a value in .env, the token in the site
configuration, the helper's own container. Nothing is touched without --fix, and a token is never printed.

The judgement (diagnose) is pure so that it can be tested; RealProbe and the CLI at the bottom do the
looking and the fixing. Standard library only, like the helper.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys

OK, WARN, BAD, INFO = "ok", "warn", "bad", "info"
SYMBOL = {OK: "[ok]  ", WARN: "[!]   ", BAD: "[x]   ", INFO: "[i]   "}
DEFAULT_SOCKET = "/var/run/docker.sock"
# fixes that change a file or the site configuration (no restart) come first
CONFIG_FIXES = ("env_profile", "env_dir", "env_docker_gid", "site_token")
RESTART_FIXES = ("recreate_helper", "turn_on")

# What the helper asks the site, to see if it answers; the token is deliberately wrong, so that it neither
# claims a task nor marks the helper as connected (a real sync does both)
SITE_PROBE = r"""
import sys, urllib.request, urllib.parse, urllib.error
url, site = sys.argv[1:3]
req = urllib.request.Request(url.rstrip("/") + "/api/method/sok_resdesk.server.agent_sync",
    data=urllib.parse.urlencode({"token": "doctor", "facts": "{}"}).encode(),
    headers={"X-Frappe-Site-Name": site, "Accept": "application/json", "Host": site})
try:
    r = urllib.request.urlopen(req, timeout=15)
    print(r.status); print(r.read(2000).decode("utf-8", "replace"))
except urllib.error.HTTPError as e:
    print(e.code); print(e.read(2000).decode("utf-8", "replace"))
except Exception as e:
    print("ERR"); print(str(e)[:200])
"""


# -- pure judgement -------------------------------------------------------------------------------


def parse_env(text: str) -> dict:
	out = {}
	for line in text.splitlines():
		line = line.strip()
		if "=" in line and not line.startswith("#"):
			k, v = line.split("=", 1)
			out[k.strip()] = v.strip().strip('"').strip("'")
	return out


def set_env_text(text: str, key: str, value: str) -> str:
	"""`text` (a .env file) with KEY=value set: the line replaced if there is one, else added."""
	line, done, out = f"{key}={value}", False, []
	for old in text.splitlines():
		if re.match(rf"^\s*{re.escape(key)}\s*=", old):
			if not done:
				out.append(line)
			done = True
		else:
			out.append(old)
	if not done:
		out.append(line)
	return "\n".join(out) + "\n"


def with_profile(profiles: str, name: str) -> str:
	parts = [p for p in (profiles or "").split(",") if p.strip()]
	return ",".join(parts if name in parts else parts + [name])


def install_kind(env: dict) -> str:
	if env.get("RESDESK_ON_COOLIFY") or env.get("RESDESK_COOLIFY_API"):
		return "coolify"
	return "native" if env.get("INSTALL_MODE") == "native" else "docker"


def classify_refusal(status, body: str = "") -> str:
	"""What an answer from the site (status, or None/"ERR" when there was none) means for the helper:
	ok, token (refused: it is not the one in the site configuration), classified (off by design),
	site (this address is not Research Desk or not this site), down (the site is starting or failing),
	unreachable."""
	if status in (None, "ERR"):
		return "unreachable"
	status = int(status)
	if status == 200:
		return "ok"
	if status == 403:
		return "classified" if "Classified mode" in body else "token"
	if status == 404:
		return "site"
	return "down"


def diagnose(env: dict, probe, here: str) -> list[dict]:
	"""Findings, each {id, level, text, fix}; `probe` answers what only the machine can say."""
	out: list[dict] = []

	def add(id_: str, level: str, text: str, fix: str | None = None) -> None:
		out.append({"id": id_, "level": level, "text": text, "fix": fix})

	kind = install_kind(env)
	token = env.get("RESDESK_AGENT_TOKEN", "")
	add("kind", INFO, f"This is a {kind} install.")
	if kind == "coolify":
		add(
			"coolify",
			INFO,
			"Under Coolify the updater helper is not used: restarts and redeploys go through Coolify's API "
			"(RESDESK_COOLIFY_API, RESDESK_COOLIFY_TOKEN, RESDESK_COOLIFY_APP in the resource's environment).",
		)
		return out
	if env.get("RESDESK_CLASSIFIED") == "1":
		add(
			"classified",
			INFO,
			"RESDESK_CLASSIFIED=1: the helper is switched off in Classified mode, on purpose.",
		)
		return out

	switched_on = bool(token)
	if kind == "docker":
		listed = "updater" in [p.strip() for p in env.get("COMPOSE_PROFILES", "").split(",")]
		state = probe.helper_state()
		if not switched_on and not listed and state is None:
			add("off", INFO, "The updater helper is off. Turn it on with: ./resdesk.sh updater on")
			return out
		if not token:
			add(
				"token_env",
				BAD,
				"RESDESK_AGENT_TOKEN is missing from .env, so the helper cannot sign in.",
				"turn_on",
			)
		if not listed:
			add(
				"profile",
				BAD,
				"COMPOSE_PROFILES in .env does not list 'updater', so docker compose does not start the helper.",
				"env_profile",
			)
		if os.path.realpath(env.get("RESDESK_DIR") or "/nonexistent") != os.path.realpath(here):
			add(
				"dir",
				BAD,
				f"RESDESK_DIR in .env is {env.get('RESDESK_DIR') or 'not set'}, but this folder is {here}: "
				"the helper mounts the wrong folder (was it moved?).",
				"env_dir",
			)
		sock = env.get("DOCKER_SOCKET") or DEFAULT_SOCKET
		gid = probe.socket_gid(sock)
		if gid is None:
			add("socket", BAD, f"The Docker socket {sock} was not found: set DOCKER_SOCKET in .env.")
		elif env.get("RESDESK_UID", "0") not in ("", "0") and str(gid) != env.get("DOCKER_GID", "0"):
			add(
				"gid",
				BAD,
				f"DOCKER_GID in .env is {env.get('DOCKER_GID') or 'not set'}, but the Docker socket belongs to group "
				f"{gid}: the helper (running as user {env.get('RESDESK_UID')}) cannot use Docker.",
				"env_docker_gid",
			)
		if state is None:
			add("container", BAD, "The helper's container does not exist.", "recreate_helper")
		elif state == "running":
			add("container", OK, "The helper's container is running.")
			if "permission denied" in probe.helper_log().lower():
				add("log", BAD, "The helper's log says 'permission denied' (see DOCKER_GID and RESDESK_UID).")
		else:
			add(
				"container",
				BAD,
				f"The helper's container is {state}: ./resdesk.sh updater status shows why.",
				"recreate_helper",
			)
	else:
		if env.get("UPDATER") != "1":
			add("off", INFO, "The updater helper is off. Turn it on with: ./resdesk.sh updater on")
			return out
		if not token:
			add("token_env", BAD, "RESDESK_AGENT_TOKEN is missing from .env.", "turn_on")
		if not probe.procfile_has_agent():
			add("procfile", BAD, "The bench's Procfile does not start the helper.", "turn_on")
		if probe.native_running():
			add("container", OK, "The helper's process is running.")
		else:
			add(
				"container", BAD, "The helper's process is not running (it starts with the bench).", "turn_on"
			)

	if token:
		if not 32 <= len(token) <= 128 or re.search(r"\s", token):
			add(
				"token_shape",
				WARN,
				"RESDESK_AGENT_TOKEN in .env does not look like one made by 'updater on'.",
				"turn_on",
			)
		site = probe.site_token()
		if site is None:
			add("site_token", WARN, "The site configuration could not be read (is the site running?).")
		elif site == token:
			add("site_token", OK, "The token in the site configuration matches .env.")
		else:
			add(
				"site_token",
				BAD,
				"The site configuration has "
				+ ("a different" if site else "no")
				+ " helper token, so the Server page says the helper is off and the helper is refused.",
				"site_token",
			)
		status, body = probe.site_answer()
		why = classify_refusal(status, body)
		if why == "token":
			add(
				"reach",
				OK,
				"The helper's address reaches the site (it answers, and refuses a made-up token).",
			)
		elif why == "classified":
			add("reach", INFO, "The site refuses the helper because it is in Classified mode.")
		elif why == "unreachable":
			add(
				"reach",
				BAD,
				"The helper's address does not answer: is the web service up? (./resdesk.sh status)",
			)
		elif why == "site":
			add(
				"reach",
				BAD,
				"The address answers but is not this Research Desk site: check SITE_NAME and HTTP_PORT in .env.",
			)
		elif why == "down":
			add(
				"reach",
				WARN,
				f"The site answered {status}: it may be starting or failing (./resdesk.sh logs).",
			)
		elif why == "ok":
			add("reach", WARN, "The site accepted a made-up token: this should not happen.")
	return out


def plan_fixes(findings: list[dict], restart: bool = True) -> list[str]:
	"""The fixes to run, once each, config before restarts; 'turn_on' does everything the others do.
	Without `restart` only the fixes that change a file or the site configuration are planned."""
	wanted = {f["fix"] for f in findings if f["fix"]}
	if not restart:
		wanted -= set(RESTART_FIXES)
	if "turn_on" in wanted:
		return ["turn_on"]
	return [f for f in (*CONFIG_FIXES, *RESTART_FIXES) if f in wanted]


# -- looking and fixing ---------------------------------------------------------------------------


def run(cmd, timeout=60, cwd=None, stdin=None) -> tuple[int, str]:
	try:
		p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd, input=stdin)
		return p.returncode, (p.stdout + p.stderr).strip()
	except (OSError, subprocess.TimeoutExpired) as e:
		return 1, str(e)


def compose_env(env: dict) -> dict:
	extra = {}
	if not os.environ.get("COMPOSE_FILE") and not env.get("COMPOSE_FILE"):
		files = ["compose.yaml"]
		if env.get("DEV_MODE") == "1":
			files.append("compose.dev.yaml")
		if env.get("HTTPS") == "1":
			files.append("compose.https.yaml")
		if len(files) > 1:
			extra["COMPOSE_FILE"] = ":".join(files)
	return {**os.environ, **extra}


class RealProbe:
	def __init__(self, env: dict, here: str):
		self.env, self.here = env, here
		self.site = env.get("SITE_NAME") or "resdesk.localhost"
		self.docker = install_kind(env) == "docker"
		self.cenv = compose_env(env)

	def _compose(self, *args, timeout=60, stdin=None):
		try:
			p = subprocess.run(
				["docker", "compose", *args],
				capture_output=True,
				text=True,
				timeout=timeout,
				cwd=self.here,
				env=self.cenv,
				input=stdin,
			)
			return p.returncode, (p.stdout + p.stderr).strip()
		except (OSError, subprocess.TimeoutExpired) as e:
			return 1, str(e)

	def helper_state(self):
		code, out = self._compose("ps", "-a", "--format", "json", "updater")
		if code or not out.strip():
			return None
		for line in out.splitlines():
			try:
				items = json.loads(line)
			except ValueError:
				continue
			for c in items if isinstance(items, list) else [items]:
				if c.get("Service") == "updater":
					return c.get("State") or "unknown"
		return None

	def helper_log(self):
		return self._compose("logs", "--tail", "40", "updater")[1]

	def socket_gid(self, sock):
		try:
			return os.stat(sock).st_gid
		except OSError:
			return None

	def site_token(self):
		code_script = "import json,sys;print(json.load(open(sys.argv[1])).get('resdesk_agent_token',''))"
		if self.docker:
			code, out = self._compose(
				"exec", "-T", "backend", "python3", "-c", code_script, f"sites/{self.site}/site_config.json"
			)
		else:
			bench = self.env.get("BENCH_DIR") or os.path.expanduser("~/researchdesk-bench")
			code, out = run(
				[
					sys.executable,
					"-c",
					code_script,
					os.path.join(bench, "sites", self.site, "site_config.json"),
				]
			)
		return None if code else out.strip()

	def site_answer(self):
		if self.docker:
			code, out = self._compose(
				"exec", "-T", "updater", "python3", "-c", SITE_PROBE, "http://frontend:8080", self.site
			)
		else:
			url = f"http://127.0.0.1:{self.env.get('HTTP_PORT') or '8000'}"
			code, out = run([sys.executable, "-c", SITE_PROBE, url, self.site], timeout=30)
		if code:
			return "ERR", out[:200]
		head, _, body = out.partition("\n")
		return (head.strip() if head.strip() == "ERR" else int(head.strip() or 0)), body

	def procfile_has_agent(self):
		bench = self.env.get("BENCH_DIR") or os.path.expanduser("~/researchdesk-bench")
		try:
			with open(os.path.join(bench, "Procfile")) as f:
				return "scripts/agent.py" in f.read()
		except OSError:
			return False

	def native_running(self):
		return run(["pgrep", "-f", "scripts/agent.py"], timeout=10)[0] == 0


def _hide(text: str, env: dict) -> str:
	"""A command's output without the token in it."""
	token = env.get("RESDESK_AGENT_TOKEN") or ""
	return text.replace(token, "***") if token else text


def apply_fix(fix: str, env: dict, here: str, probe: RealProbe) -> str:
	"""Do one repair; returns what was done, or why it could not be."""
	path = os.path.join(here, ".env")

	def write_env(key, value):
		with open(path) as f:
			text = f.read()
		tmp = path + ".tmp"  # whole or not at all: .env holds the passwords
		with open(tmp, "w") as f:
			f.write(set_env_text(text, key, value))
			f.flush()
			os.fsync(f.fileno())
		shutil.copymode(path, tmp)
		os.replace(tmp, path)
		env[key] = value

	if fix == "env_profile":
		write_env("COMPOSE_PROFILES", with_profile(env.get("COMPOSE_PROFILES", ""), "updater"))
		return "added 'updater' to COMPOSE_PROFILES in .env"
	if fix == "env_dir":
		write_env("RESDESK_DIR", here)
		return f"set RESDESK_DIR={here} in .env"
	if fix == "env_docker_gid":
		gid = probe.socket_gid(env.get("DOCKER_SOCKET") or DEFAULT_SOCKET)
		write_env("DOCKER_GID", str(gid))
		return f"set DOCKER_GID={gid} in .env"
	if fix == "site_token":
		token = env["RESDESK_AGENT_TOKEN"]
		if probe.docker:
			code, out = probe._compose(
				"exec",
				"-T",
				"backend",
				"bench",
				"--site",
				probe.site,
				"set-config",
				"resdesk_agent_token",
				token,
			)
		else:
			bench = env.get("BENCH_DIR") or os.path.expanduser("~/researchdesk-bench")
			code, out = run(
				["bench", "--site", probe.site, "set-config", "resdesk_agent_token", token], cwd=bench
			)
		return (
			"put the token in the site configuration"
			if not code
			else f"could not set the token: {_hide(out, env)[-200:]}"
		)
	if fix == "recreate_helper":
		for cmd in (["build", "updater"], ["up", "-d", "--no-deps", "--force-recreate", "updater"]):
			code, out = probe._compose(*cmd, timeout=600)
			if code:
				return f"docker compose {' '.join(cmd)} failed: {_hide(out, env)[-200:]}"
		return "rebuilt and restarted the helper's container"
	if fix == "turn_on":
		code, out = run(["./resdesk.sh", "updater", "on"], timeout=900, cwd=here)
		return "ran ./resdesk.sh updater on" if not code else f"updater on failed: {_hide(out, env)[-200:]}"
	return f"unknown fix {fix}"


def main(argv: list[str]) -> int:
	fix = "--fix" in argv
	no_restart = "--no-restart" in argv
	quiet = "--quiet" in argv
	here = os.getcwd()
	try:
		with open(os.path.join(here, ".env")) as f:
			env = parse_env(f.read())
	except OSError:
		print("No .env here: run this in the install folder.")
		return 2
	probe = RealProbe(env, here)
	findings = diagnose(env, probe, here)
	if not quiet:
		for f in findings:
			print(SYMBOL[f["level"]] + f["text"])
	problems = [f for f in findings if f["level"] == BAD]
	if not problems:
		if not quiet:
			print("\nNothing wrong found." if any(f["id"] == "container" for f in findings) else "")
		return 0
	plan = plan_fixes(findings, restart=not no_restart)
	if not fix:
		print(f"\n{len(problems)} problem(s). Put them right with: ./resdesk.sh updater doctor --fix")
		return 1
	for step in plan:
		print(f"  fixing: {apply_fix(step, env, here, probe)}")
	if no_restart:  # the upgrade restarts the helper itself; what needs more is left for the person
		return 0
	after = [f for f in diagnose(env, RealProbe(env, here), here) if f["level"] == BAD]
	for f in after:
		print(SYMBOL[BAD] + f["text"])
	print("\nFixed." if not after else f"\n{len(after)} problem(s) remain: they need a look by hand.")
	return 0 if not after else 1


if __name__ == "__main__":
	sys.exit(main(sys.argv[1:]))
