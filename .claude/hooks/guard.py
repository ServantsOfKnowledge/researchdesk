#!/usr/bin/env python3
"""PreToolUse hook for Bash: the repository's rules for git, enforced.

Blocks (exit 2, the reason goes back to Claude):
  - git push that forces, deletes, pushes tags, targets anything but main, or carries more than one
    release (each commit message starting with a version number is one release);
  - a push whose commit fails scripts/prepush.sh (checked in a clean export of that commit);
  - a commit message with Co-Authored-By / Claude-Session trailers, or a change of author to Claude.
Everything else passes. Rules: CLAUDE.md.
"""

import json
import os
import re
import shlex
import subprocess
import sys
import tempfile

ROOT = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()


def block(msg):
	print(f"BLOCKED by .claude/hooks/guard.py: {msg}", file=sys.stderr)
	sys.exit(2)


def git(*args, check=False):
	return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=check)


def git_words(segment):
	"""The words after `git` (and its own options) in one shell command, or None if not git."""
	try:
		words = shlex.split(segment)
	except ValueError:
		words = segment.split()
	while words and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", words[0]):
		words.pop(0)  # VAR=value prefixes
	if not words or os.path.basename(words[0]) != "git":
		return None
	# redirections (2>&1, >file, &>out) are the shell's, not git's arguments
	rest = [w for w in words[1:] if not re.match(r"^(\d*[<>]|&>)", w)]
	while rest and rest[0].startswith("-"):
		rest = rest[2:] if rest[0] in ("-c", "-C", "--git-dir", "--work-tree") else rest[1:]
	return rest


def check_commit(command, rest):
	low = command.lower()  # the whole command: a multi-line message spans several "segments"
	for bad in ("co-authored-by", "claude-session", "--reset-author", "noreply@anthropic.com"):
		if bad in low:
			block(f"commits are authored as omshivaprakash with no Claude trailers ({bad!r} found).")


def check_config(segment, rest):
	low = segment.lower()
	if "noreply@anthropic.com" in low or re.search(r"user\.name\s+['\"]?claude\b", low):
		block("git identity stays omshivaprakash; do not set it to Claude.")


def check_push(segment, rest):
	args = rest[1:]
	flags = [a for a in args if a.startswith("-")]
	for f in flags:
		if f in ("-f", "--force", "--delete", "-d", "--mirror", "--tags", "--prune") or f.startswith(
			"--force-with-lease"
		):
			block(f"{f}: never force-push, delete or push tags (the Release workflow tags).")
	pos = [a for a in args if not a.startswith("-")]
	refspecs = pos[1:]
	branch = git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
	if not refspecs:
		if branch != "main":
			block(f"push only to main; you are on {branch!r}. Use: git push origin <sha>:main")
		refspecs = ["HEAD:main"]
	src = "HEAD"
	for spec in refspecs:
		if spec.startswith("+"):
			block("a + refspec forces the push.")
		if ":" in spec:
			src, dst = spec.split(":", 1)
			if not src:
				block("an empty source deletes the remote branch.")
		else:
			src, dst = spec, spec
			if spec == "HEAD" and branch != "main":
				block(f"HEAD is {branch!r}; push to main with <sha>:main.")
		if dst not in ("main", "refs/heads/main") and not (spec == "HEAD" and branch == "main"):
			block(f"push only to main (target {dst!r}).")
	sha = git("rev-parse", "--verify", f"{src}^{{commit}}").stdout.strip()
	if not sha:
		block(f"cannot find {src!r}.")
	# one release per push: the Release workflow tags only the version at main's head
	rng = "origin/main.." + sha
	subjects = git("log", "--format=%s", rng).stdout.splitlines()
	releases = [s for s in subjects if re.match(r"^\d+\.\d+\.\d+[:\s]", s)]
	if len(releases) > 1:
		block(
			f"{len(releases)} releases in one push ({', '.join(r.split(':')[0] for r in releases)}): "
			"push one version at a time, after the previous tag exists and its CI is green."
		)
	# the checks, on exactly the commit being pushed
	with tempfile.TemporaryDirectory() as tmp:
		archive = subprocess.run(["git", "archive", sha], cwd=ROOT, capture_output=True)
		if archive.returncode:
			block("could not export the commit to check it.")
		subprocess.run(["tar", "-x", "-C", tmp], input=archive.stdout, check=True)
		check = subprocess.run(
			["bash", os.path.join(ROOT, "scripts", "prepush.sh"), "--dir", tmp],
			capture_output=True,
			text=True,
		)
	if check.returncode:
		tail = "\n".join((check.stdout + check.stderr).splitlines()[-40:])
		block(f"scripts/prepush.sh failed for {sha[:7]}:\n{tail}")


def main():
	try:
		data = json.load(sys.stdin)
	except ValueError:
		return
	command = (data.get("tool_input") or {}).get("command") or ""
	for segment in re.split(r"&&|\|\||;|\n|\|", command):
		rest = git_words(segment.strip())
		if not rest:
			continue
		sub = rest[0]
		if sub == "commit":
			check_commit(command, rest)
		elif sub == "config":
			check_config(segment, rest)
		elif sub == "push":
			check_push(segment, rest)
		elif sub == "rebase" and "--exec" in segment and "reset-author" in segment:
			block("do not re-author commits as Claude.")


main()
