"""0.69.0: what a gentle upgrade restarts, from the files a release changes (scripts/upgrade-plan.sh)."""

import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "upgrade-plan.sh"


def plan(*files: str) -> str:
	out = subprocess.run(
		["bash", "-c", f'. "{SCRIPT}"; upgrade_plan'],
		input="\n".join(files) + "\n",
		capture_output=True,
		text=True,
		check=True,
	)
	return out.stdout.strip()


def test_documents_screens_and_data_definitions_only_restart_the_web_part():
	line = plan(
		"CHANGELOG.md",
		"docs/server.md",
		"sok_resdesk/__init__.py",  # the version number changes every release
		"sok_resdesk/resdesk/page/resdesk_server/resdesk_server.js",
		"sok_resdesk/resdesk/doctype/rd_item/rd_item.json",
		"sok_resdesk/tests/test_mail.py",
		"sok_resdesk/public/css/desk.css",
	)
	assert line.startswith("web:"), line


def test_python_the_workers_run_restarts_them_one_at_a_time():
	assert plan("CHANGELOG.md", "sok_resdesk/search_queue.py").startswith("roll:")
	assert plan("sok_resdesk/resdesk/doctype/rd_item/rd_item.py").startswith("roll:")
	assert plan("sok_resdesk/hooks.py").startswith("roll:")


def test_images_and_services_restart_everything():
	for f in ("compose.yaml", "Dockerfile", "docker/entrypoint.sh", "pyproject.toml", "compose.https.yaml"):
		assert plan("sok_resdesk/search_queue.py", f).startswith("full:"), f


def test_no_change_at_all_is_web():
	assert plan().startswith("web:")
