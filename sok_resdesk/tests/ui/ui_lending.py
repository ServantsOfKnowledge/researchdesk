"""Joining with an ID card, My library and the ID card: accessible, announce what is wrong, send what was typed."""

from .conftest import STUB_GLOBALS, axe_violations, page_shell, render_template

OK = "window.fetch = (u, o) => { window.sent = [u, JSON.parse(o.body)]; return Promise.resolve({ json: () => Promise.resolve({ message: { joined: 1, status: 'member', next: '#done' } }) }); };"
REFUSED = "window.fetch = () => Promise.resolve({ json: () => Promise.resolve({ exc: 'x', _server_messages: JSON.stringify([JSON.stringify({ message: 'We could not match that to the roster.' })]) }) });"

# a refusal that also records the call (a success reloads the page, which would forget it)
RECORD = "window.fetch = (u, o) => { window.sent = [u, JSON.parse(o.body)]; return Promise.resolve({ json: () => Promise.resolve({ exc: 'x', _server_messages: JSON.stringify([JSON.stringify({ message: 'This loan cannot be renewed again.' })]) }) }); };"

PATRON = {
	"name": "M-00001",
	"full_name": "Asha K",
	"category": "Student",
	"status": "Active",
	"valid_until": "2027-06-14",
	"department": "",
	"institution_id": "CS21045",
}
ME = {
	"patron": PATRON,
	"limits": {"loans": 3, "holds": 3, "renewals": 2},
	"standing": "",
	"loans": [
		{
			"name": "L-000001",
			"copy": "C-000001",
			"item": "b1",
			"title": "A Book",
			"due_on": "2026-11-20",
			"overdue": False,
			"renewals": 0,
		}
	],
	"holds": [
		{"name": "H-00001", "item": "b2", "title": "Another Book", "status": "Waiting", "ready_until": ""}
	],
	"fines": [{"name": "F-00001", "amount": 10.0, "reason": "Overdue", "note": "5 days late"}],
	"fines_total": 10.0,
	"currency": "₹",
	"ill": [
		{
			"name": "ILL-00001",
			"title": "A Rare Book",
			"author": "Someone",
			"status": "Requested",
			"due_on": "",
		}
	],
	"pay_online": True,
}


def _membership(page, site, fetch, signed_in=False):
	body, script = render_template(
		"membership.html", open=True, signed_in=signed_in, min_password=8, login_url="/login"
	)
	page.goto(
		site.write(
			f"membership_{signed_in}.html",
			page_shell(body, f"<script>{STUB_GLOBALS}{fetch}</script>{script}"),
		)
	)


def test_membership_has_no_wcag_problems(page, site, axe_js):
	for signed_in in (False, True):
		_membership(page, site, OK, signed_in)
		assert axe_violations(page, axe_js) == []


def test_what_is_missing_is_announced_and_nothing_is_sent(page, site):
	_membership(page, site, OK)
	page.click("button[type=submit]")
	assert "ID card" in page.inner_text("#rd-mb-err")
	assert page.get_attribute("[name=id_number]", "aria-invalid") == "true"
	page.fill("[name=id_number]", "CS21045")
	page.click("button[type=submit]")
	assert "name" in page.inner_text("#rd-mb-err")
	assert page.evaluate("window.sent") is None


def test_a_good_form_is_sent_with_the_id_number_and_birth_date(page, site):
	_membership(page, site, OK)
	page.fill("[name=full_name]", "Asha K")
	page.fill("[name=email]", "asha@example.org")
	page.fill("[name=password]", "longenough1")
	page.fill("[name=id_number]", "CS-21/045")
	page.fill("[name=date_of_birth]", "2008-05-04")
	page.click("button[type=submit]")
	page.wait_for_function("window.sent")
	url, body = page.evaluate("window.sent")
	assert url.endswith("sok_resdesk.patrons.apply")
	assert body["id_number"] == "CS-21/045" and body["date_of_birth"] == "2008-05-04" and body["rd_hp"] == ""
	assert "photo" not in body


def test_a_signed_in_person_links_without_a_password(page, site):
	_membership(page, site, OK, signed_in=True)
	assert page.query_selector("[name=password]") is None
	page.fill("[name=id_number]", "CS21045")
	page.click("button[type=submit]")
	page.wait_for_function("window.sent")
	assert page.evaluate("window.sent")[0].endswith("sok_resdesk.patrons.claim")


def test_the_servers_refusal_is_shown(page, site):
	_membership(page, site, REFUSED, signed_in=True)
	page.fill("[name=id_number]", "X1")
	page.click("button[type=submit]")
	page.wait_for_selector("#rd-mb-err:not(:empty)")
	assert "could not match" in page.inner_text("#rd-mb-err")


def test_my_library_has_no_wcag_problems_and_buttons_call_the_server(page, site, axe_js):
	body, script = render_template("loans.html", state="member", status="Active", me=ME)
	page.goto(site.write("loans.html", page_shell(body, f"<script>{STUB_GLOBALS}{RECORD}</script>{script}")))
	assert axe_violations(page, axe_js) == []
	page.click("[data-renew]")
	page.wait_for_function("window.sent")
	url, sent = page.evaluate("window.sent")
	assert url.endswith("sok_resdesk.lending.my_renew") and sent == {"loan": "L-000001"}
	page.wait_for_selector("#rd-ln-msg:not(:empty)")
	assert "cannot be renewed" in page.inner_text("#rd-ln-msg")


def test_a_member_who_is_not_yet_approved_is_told_so(page, site, axe_js):
	body, script = render_template("loans.html", state="pending", status="Pending", me=None)
	page.goto(site.write("loans_pending.html", page_shell(body, f"<script>{STUB_GLOBALS}</script>{script}")))
	assert "checking" in page.inner_text("main, body")
	assert axe_violations(page, axe_js) == []


def test_the_id_card_is_credit_card_size_and_has_no_wcag_problems(page, site, axe_js):
	card = {
		"name": "M-00001",
		"full_name": "Asha K",
		"category": "Student",
		"department": "Class 10",
		"institution_id": "CS21045",
		"valid_until": "2027-06-14",
		"status": "Active",
		"photo": "",
		"barcode": "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 10 10' width='10' height='10' role='img' aria-label='M-00001'><rect width='10' height='10'/></svg>",
		"library": "Library",
		"logo": "",
		"back": "Open 9 to 5",
	}
	body, script = render_template("card.html", cards=[card])
	page.goto(site.write("card.html", page_shell(body, f"<script>{STUB_GLOBALS}</script>{script}")))
	width = page.evaluate(
		"Math.round(document.querySelector('.rd-idc').getBoundingClientRect().width / 96 * 25.4)"
	)
	assert 84 <= width <= 87  # 85.6 mm
	assert axe_violations(page, axe_js) == []


def test_online_payment_and_interlibrary_requests_call_the_server(page, site, axe_js):
	body, script = render_template("loans.html", state="member", status="Active", me=ME)
	page.goto(
		site.write("loans_more.html", page_shell(body, f"<script>{STUB_GLOBALS}{RECORD}</script>{script}"))
	)
	assert axe_violations(page, axe_js) == []
	page.click("#rd-pay")
	page.wait_for_function("window.sent")
	assert page.evaluate("window.sent")[0].endswith("sok_resdesk.payments.start")
	page.evaluate("window.sent = null")
	page.click("[data-ill-cancel]")
	page.wait_for_function("window.sent")
	assert page.evaluate("window.sent")[0].endswith("sok_resdesk.ill.cancel_mine")
	page.evaluate("window.sent = null; document.querySelector('details').open = true")
	page.click("#rd-ill-form button[type=submit]")
	assert "title" in page.inner_text("#rd-ln-msg")  # nothing is sent without one
	assert page.evaluate("window.sent") is None
	page.fill("#rd-ill-form [name=title]", "Another Rare Book")
	page.click("#rd-ill-form button[type=submit]")
	page.wait_for_function("window.sent")
	url, sent = page.evaluate("window.sent")
	assert url.endswith("sok_resdesk.ill.request_mine") and sent["title"] == "Another Rare Book"
