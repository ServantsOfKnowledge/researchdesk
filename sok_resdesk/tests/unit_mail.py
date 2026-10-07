"""0.67.0: outgoing email set-up checks and plain-words errors."""

from sok_resdesk.core import mail as m


def test_form_problems_are_named():
	assert m.problem("lib@example.org", "smtp.example.org", 587, "tls") == ""
	assert "address" in m.problem("nope", "smtp.example.org", 587, "tls")
	assert "server" in m.problem("lib@example.org", "", 587, "tls")
	assert "port" in m.problem("lib@example.org", "smtp.example.org", "x", "tls")
	assert "port" in m.problem("lib@example.org", "smtp.example.org", 70000, "tls")
	assert "STARTTLS" in m.problem("lib@example.org", "smtp.example.org", 587, "weird")


def test_errors_are_put_in_plain_words():
	assert "app password" in m.plain_error("(535, b'5.7.8 Username and Password not accepted')")
	assert "name could not be found" in m.plain_error("[Errno -2] Name or service not known")
	assert "did not answer" in m.plain_error("timed out")
	assert m.plain_error("") == ""
	assert m.plain_error("odd\nlast line") == "last line"


def test_presets_are_complete():
	for p in m.PRESETS:
		assert p["port"] and p["security"] in m.SECURITY


def test_resend_is_a_ready_made_choice():
	resend = next(p for p in m.PRESETS if p["label"].startswith("Resend"))
	assert resend["server"] == "smtp.resend.com" and resend["login"] == "resend"
	assert resend["port"] == 587 and resend["security"] == "tls"


def test_resends_login_name_does_not_follow_you_to_another_provider():
	assert m.login_for("smtp.resend.com", "resend") == "resend"
	assert m.login_for("smtp.gmail.com", "resend") == ""  # left over from the Resend set-up
	assert m.login_for("smtp.gmail.com", " me@gmail.com ") == "me@gmail.com"
	assert m.login_for("smtp.gmail.com", "") == ""


def test_the_security_choice_follows_the_port():
	assert m.security_for(465, "tls") == "ssl"  # "Connection unexpectedly closed" otherwise
	assert m.security_for("587", "ssl") == "tls"
	assert m.security_for(2525, "none") == "none"
	assert m.security_for("x", "tls") == "tls"


def test_a_server_that_hangs_up_is_explained():
	raw = "Invalid Outgoing Mail Server or Port: Connection unexpectedly closed"
	assert "587" in m.plain_error(raw) and "465" in m.plain_error(raw)
