"""Asking Coolify to restart or redeploy (core/coolify.py)."""

import pytest

from sok_resdesk.core.coolify import request_for, settings

ENV = {
	"RESDESK_COOLIFY_API": "https://coolify.example.org/",
	"RESDESK_COOLIFY_TOKEN": " 1|abc ",
	"RESDESK_COOLIFY_APP": "k4s8",
}


def test_needs_all_three_and_a_web_address():
	assert settings(ENV) == {"api": "https://coolify.example.org", "token": "1|abc", "app": "k4s8"}
	for missing in ENV:
		assert settings({k: v for k, v in ENV.items() if k != missing}) is None
	assert settings({**ENV, "RESDESK_COOLIFY_API": "coolify.example.org"}) is None


def test_restart_and_redeploy_are_the_documented_calls():
	cfg = settings(ENV)
	url, headers = request_for("restart", cfg)
	assert url == "https://coolify.example.org/api/v1/applications/k4s8/restart"
	assert headers["Authorization"] == "Bearer 1|abc"
	assert request_for("upgrade", cfg)[0] == "https://coolify.example.org/api/v1/deploy?uuid=k4s8&force=false"


def test_nothing_else_can_be_asked_and_the_uuid_is_quoted():
	with pytest.raises(ValueError):
		request_for("logs", settings(ENV))
	url, _ = request_for("restart", {**settings(ENV), "app": "a/../b?x"})
	assert "/applications/a%2F..%2Fb%3Fx/restart" in url
