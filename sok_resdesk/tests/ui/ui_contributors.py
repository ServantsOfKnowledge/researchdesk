"""The Contributors page: accessible, and tells an empty list from a full one."""

from .conftest import axe_violations, page_shell, render_template

PEOPLE = [
	{
		"name": "Asha Rao",
		"kind": "Individual",
		"organisation": "Mysuru Library",
		"role_title": "Proofreader",
		"country": "India",
		"about": "Proofreads Kannada.",
		"website": "https://example.org",
	},
	{
		"name": "Open Texts Trust",
		"kind": "Organisation",
		"organisation": "",
		"role_title": "",
		"country": "",
		"about": "",
		"website": "",
	},
]


def _open(page, site, people):
	body, _script = render_template("contributors.html", people=people)
	page.goto(site.write("contributors.html", page_shell(body)))


def test_no_wcag_problems(page, site, axe_js):
	_open(page, site, PEOPLE)
	assert axe_violations(page, axe_js) == []


def test_each_person_is_a_heading_with_their_details(page, site):
	_open(page, site, PEOPLE)
	assert page.locator("h2").all_inner_texts() == ["Asha Rao", "Open Texts Trust"]
	assert "Proofreader \u00b7 Mysuru Library \u00b7 India" in page.inner_text(".rd-contrib-list li")
	assert page.get_attribute(".rd-contrib-list a", "rel") == "nofollow noopener"


def test_an_empty_list_says_so_and_nothing_scrolls_sideways(page, site):
	_open(page, site, [])
	assert "No one is named here yet." in page.inner_text(".rd-contributors")
	page.set_viewport_size({"width": 360, "height": 800})
	assert not page.evaluate("document.documentElement.scrollWidth > innerWidth")
