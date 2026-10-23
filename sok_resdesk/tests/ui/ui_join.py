"""The join page: accessible, says what is wrong, shows the password on request, and signs in."""

from .conftest import STUB_GLOBALS, axe_violations, page_shell, render_template

FAIL = "window.fetch = () => Promise.resolve({ json: () => Promise.resolve({ exc: 'x', _server_messages: JSON.stringify([JSON.stringify({ message: 'This email already has an account.' })]) }) });"
OK = "window.fetch = (u, o) => { window.sent = JSON.parse(o.body); return Promise.resolve({ json: () => Promise.resolve({ message: { joined: 1, status: 'member' } }) }); };"


def _open(page, site, fetch, approval=False):
	body, script = render_template(
		"join.html", approval=approval, min_password=8, next_url="#joined", login_url="/login"
	)
	page.goto(
		site.write(
			f"join_{approval}.html", page_shell(body, f"<script>{STUB_GLOBALS}{fetch}</script>{script}")
		)
	)


def test_no_wcag_problems(page, site, axe_js):
	_open(page, site, OK)
	assert axe_violations(page, axe_js) == []
	_open(page, site, OK, approval=True)
	assert axe_violations(page, axe_js) == []


def test_each_missing_thing_is_announced_and_focused_without_calling_the_server(page, site):
	_open(page, site, OK)
	page.click("button[type=submit]")
	assert "name" in page.inner_text("#rd-jn-err")
	assert page.get_attribute("[name=full_name]", "aria-invalid") == "true"
	page.fill("[name=full_name]", "Asha")
	page.fill("[name=email]", "nobody")
	page.click("button[type=submit]")
	assert "email" in page.inner_text("#rd-jn-err")
	page.fill("[name=email]", "asha@example.org")
	page.fill("[name=password]", "short")
	page.click("button[type=submit]")
	assert "at least 8" in page.inner_text("#rd-jn-err")
	assert page.evaluate("document.activeElement.id") == "rd-jn-err"
	assert page.evaluate("window.sent") is None


def test_the_servers_refusal_is_shown(page, site):
	_open(page, site, FAIL)
	page.fill("[name=full_name]", "Asha")
	page.fill("[name=email]", "asha@example.org")
	page.fill("[name=password]", "longenough1")
	page.click("button[type=submit]")
	page.wait_for_selector("#rd-jn-err:not(:empty)")
	assert "already has an account" in page.inner_text("#rd-jn-err")


def test_the_password_can_be_shown_and_a_good_form_is_sent(page, site):
	_open(page, site, OK)
	page.fill("[name=full_name]", "Asha")
	page.fill("[name=email]", "asha@example.org")
	page.fill("[name=password]", "longenough1")
	assert page.get_attribute("[name=password]", "type") == "password"
	page.check("#rd-jn-show")
	assert page.get_attribute("[name=password]", "type") == "text"
	page.click("button[type=submit]")
	page.wait_for_function("window.sent")
	assert page.evaluate("window.sent") == {
		"full_name": "Asha",
		"email": "asha@example.org",
		"password": "longenough1",
		"rd_hp": "",
	}


def test_it_fits_a_phone_and_the_trap_is_out_of_the_way(page, site):
	_open(page, site, OK)
	page.set_viewport_size({"width": 360, "height": 800})
	assert not page.evaluate("document.documentElement.scrollWidth > innerWidth")
	assert page.evaluate("document.querySelector('[name=rd_hp]').getBoundingClientRect().left") < 0
