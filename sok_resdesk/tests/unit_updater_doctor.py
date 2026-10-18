"""The updater helper's doctor: what it finds for each kind of install, and what it fixes."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))

from updater_doctor import (  # noqa: E402
	classify_refusal,
	diagnose,
	install_kind,
	parse_env,
	plan_fixes,
	set_env_text,
	with_profile,
)

HERE = "/srv/resdesk"
TOKEN = "a" * 64


class Probe:
	def __init__(self, **kw):
		self.v = {
			"state": "running",
			"gid": 999,
			"site_token": TOKEN,
			"answer": (403, '{"_server_messages": "Not allowed."}'),
			"log": "",
			"procfile": True,
			"native": True,
			**kw,
		}

	def helper_state(self):
		return self.v["state"]

	def helper_log(self):
		return self.v["log"]

	def socket_gid(self, sock):
		return self.v["gid"]

	def site_token(self):
		return self.v["site_token"]

	def site_answer(self):
		return self.v["answer"]

	def procfile_has_agent(self):
		return self.v["procfile"]

	def native_running(self):
		return self.v["native"]


def good_env(**kw):
	return {
		"RESDESK_AGENT_TOKEN": TOKEN,
		"COMPOSE_PROFILES": "updater",
		"RESDESK_DIR": HERE,
		"RESDESK_UID": "1000",
		"DOCKER_GID": "999",
		**kw,
	}


def fixes(env, **probe):
	return sorted({f["fix"] for f in diagnose(env, Probe(**probe), HERE) if f["fix"]})


def levels(env, **probe):
	return {f["id"]: f["level"] for f in diagnose(env, Probe(**probe), HERE)}


def test_a_healthy_docker_install_has_nothing_to_fix():
	assert fixes(good_env()) == []
	assert "bad" not in levels(good_env()).values()


def test_the_install_kind_is_read_from_env():
	assert install_kind({}) == "docker"
	assert install_kind({"INSTALL_MODE": "native"}) == "native"
	assert install_kind({"RESDESK_COOLIFY_API": "https://c.example"}) == "coolify"
	assert install_kind({"RESDESK_ON_COOLIFY": "1", "INSTALL_MODE": "native"}) == "coolify"


def test_coolify_and_classified_installs_are_told_the_helper_is_not_used():
	assert fixes({"RESDESK_ON_COOLIFY": "1"}) == []
	assert "classified" in levels(good_env(RESDESK_CLASSIFIED="1"))


def test_a_helper_never_turned_on_is_just_off():
	found = diagnose({"COMPOSE_PROFILES": ""}, Probe(state=None), HERE)
	assert [f["id"] for f in found] == ["kind", "off"] and not any(f["fix"] for f in found)


def test_the_site_losing_the_token_is_found_and_fixed_by_putting_it_back():
	assert fixes(good_env(), site_token="") == ["site_token"]
	assert fixes(good_env(), site_token="b" * 64) == ["site_token"]


def test_an_unreadable_site_configuration_is_a_warning_not_a_fix():
	assert levels(good_env(), site_token=None)["site_token"] == "warn"
	assert fixes(good_env(), site_token=None) == []


def test_the_profile_missing_from_env_is_found():
	assert fixes(good_env(COMPOSE_PROFILES="monitor")) == ["env_profile"]


def test_a_moved_folder_is_found():
	assert fixes(good_env(RESDESK_DIR="/old/place")) == ["env_dir"]


def test_a_wrong_docker_group_is_found_only_for_a_non_root_helper():
	assert fixes(good_env(DOCKER_GID="1"), gid=999) == ["env_docker_gid"]
	assert fixes(good_env(DOCKER_GID="1", RESDESK_UID="0"), gid=999) == []


def test_a_missing_socket_is_a_problem_with_no_automatic_fix():
	assert levels(good_env(), gid=None)["socket"] == "bad"
	assert fixes(good_env(), gid=None) == []


def test_a_missing_or_stopped_container_is_recreated():
	assert fixes(good_env(), state=None) == ["recreate_helper"]
	assert fixes(good_env(), state="restarting") == ["recreate_helper"]


def test_no_token_in_env_with_the_helper_switched_on_needs_turning_on_again():
	assert fixes(good_env(RESDESK_AGENT_TOKEN="")) == ["turn_on"]


def test_the_helper_that_cannot_reach_the_site_is_reported():
	assert levels(good_env(), answer=("ERR", "refused"))["reach"] == "bad"
	assert levels(good_env(), answer=(404, "not found"))["reach"] == "bad"
	assert levels(good_env(), answer=(502, ""))["reach"] == "warn"


def test_a_native_install_is_checked_for_its_process_and_procfile():
	env = {"INSTALL_MODE": "native", "UPDATER": "1", "RESDESK_AGENT_TOKEN": TOKEN}
	assert fixes(env) == []
	assert fixes(env, native=False) == ["turn_on"]
	assert fixes(env, procfile=False) == ["turn_on"]
	assert fixes({"INSTALL_MODE": "native", "UPDATER": "0"}) == []


def test_one_turn_on_covers_the_rest_and_config_comes_before_restarts():
	found = [{"fix": "recreate_helper"}, {"fix": "site_token"}, {"fix": "env_profile"}]
	assert plan_fixes(found) == ["env_profile", "site_token", "recreate_helper"]
	assert plan_fixes(found + [{"fix": "turn_on"}]) == ["turn_on"]


def test_an_upgrade_applies_only_the_fixes_that_need_no_restart():
	found = [{"fix": "recreate_helper"}, {"fix": "site_token"}, {"fix": "turn_on"}]
	assert plan_fixes(found, restart=False) == ["site_token"]


def test_what_the_site_answered_is_understood():
	assert classify_refusal(200) == "ok"
	assert classify_refusal(403, '{"_server_messages": "Not allowed."}') == "token"
	assert classify_refusal(403, "The updater helper is off in Classified mode.") == "classified"
	assert classify_refusal(404) == "site"
	assert classify_refusal(502) == "down"
	assert classify_refusal(None) == classify_refusal("ERR") == "unreachable"


def test_env_text_is_edited_in_place_and_comments_survive():
	text = "# keep me\nA=1\nCOMPOSE_PROFILES=\nB=2\n"
	out = set_env_text(text, "COMPOSE_PROFILES", "updater")
	assert out == "# keep me\nA=1\nCOMPOSE_PROFILES=updater\nB=2\n"
	assert set_env_text("A=1\n", "NEW", "x") == "A=1\nNEW=x\n"
	assert set_env_text("A=1\nA=2\n", "A", "3") == "A=3\n"  # a repeated key keeps one line
	assert parse_env(out)["COMPOSE_PROFILES"] == "updater"


def test_a_profile_is_added_once():
	assert with_profile("", "updater") == "updater"
	assert with_profile("monitor", "updater") == "monitor,updater"
	assert with_profile("monitor,updater", "updater") == "monitor,updater"


def test_the_helper_shares_the_judgement():
	import agent

	assert agent.doctor.classify_refusal is classify_refusal


def test_a_folder_reached_through_a_link_is_not_called_moved(tmp_path):
	real = tmp_path / "real"
	real.mkdir()
	link = tmp_path / "link"
	link.symlink_to(real)
	assert "dir" not in {f["id"] for f in diagnose(good_env(RESDESK_DIR=str(link)), Probe(), str(real))}
	assert "dir" in {f["id"] for f in diagnose(good_env(RESDESK_DIR="/old/place"), Probe(), str(real))}


def test_the_token_is_not_put_back_after_the_helper_was_turned_off_or_renewed(monkeypatch):
	import agent

	calls = []
	monkeypatch.setattr(agent, "run", lambda *a, **k: calls.append(a) or (0, ""))
	monkeypatch.setattr(agent, "env_file", lambda: {"RESDESK_AGENT_TOKEN": ""})
	assert "changed meanwhile" in agent.heal_token({}, "s", "old")
	monkeypatch.setattr(agent, "env_file", lambda: {"RESDESK_AGENT_TOKEN": "new"})
	assert "changed meanwhile" in agent.heal_token({}, "s", "old")
	assert calls == []
	monkeypatch.setattr(agent, "env_file", lambda: {"RESDESK_AGENT_TOKEN": "old"})
	assert "put back" in agent.heal_token({}, "s", "old")
	assert len(calls) == 1


def test_the_token_never_shows_in_a_failed_commands_output(monkeypatch):
	import agent
	from updater_doctor import _hide

	monkeypatch.setattr(agent, "env_file", lambda: {"RESDESK_AGENT_TOKEN": "secret-token"})
	monkeypatch.setattr(agent, "run", lambda *a, **k: (1, "No such option: secret-token"))
	out = agent.heal_token({}, "s", "secret-token")
	assert "secret-token" not in out and "***" in out
	assert _hide("x secret-token y", {"RESDESK_AGENT_TOKEN": "secret-token"}) == "x *** y"
