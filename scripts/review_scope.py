#!/usr/bin/env python3
"""What an auditor reviews for each edition: the code files and lines of Research Desk, and of the
governance app on top (docs/installation.md#editions). Counts tracked files only, tests apart.

    python3 scripts/review_scope.py
"""

import subprocess

CODE = (".py", ".js", ".sh", ".json", ".html", ".yaml", ".yml", ".toml")
SKIP = ("/tests/", "/vendor/", "/node_modules/", "/dist/", "docs/")


def tracked() -> list[str]:
	return subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True).stdout.split()


def count(paths: list[str]) -> tuple[int, int]:
	files = lines = 0
	for p in paths:
		if p.endswith(CODE) and not any(s in "/" + p for s in SKIP):
			files += 1
			with open(p, encoding="utf-8", errors="replace") as f:
				lines += sum(1 for _ in f)
	return files, lines


def main() -> None:
	paths = tracked()
	core = [p for p in paths if not p.startswith("governance/")]
	gov = [p for p in paths if p.startswith("governance/")]
	(cf, cl), (gf, gl) = count(core), count(gov)
	print(f"standard edition   {cf:5d} code files  {cl:7d} lines")
	print(f"governance app     {gf:5d} code files  {gl:7d} lines   (added by --edition governance)")
	print(f"governance edition {cf + gf:5d} code files  {cl + gl:7d} lines")


if __name__ == "__main__":
	main()
