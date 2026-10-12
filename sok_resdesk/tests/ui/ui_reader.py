"""Page & text reader (reader.js): says so when a page image is slow to arrive."""

import base64

from .conftest import page_shell

PNG = base64.b64decode(
	"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
BODY = """
<div id="rd-item" data-item="b1">
<section id="rd-pages" data-start="0">
<input id="rd-pages-n" type="number"><span id="rd-pages-of"></span><span id="rd-pages-label"></span>
<button id="rd-pages-link" type="button">Link</button><button id="rd-pages-book" type="button">Book</button>
<figure id="rd-pages-image"></figure><div id="rd-pages-text"></div>
</section></div>
<script>window.RD_I18N = { messages: {} };
window.fetch = () => Promise.resolve({ json: () => Promise.resolve({ message:
  { leaf: 0, last: 1, label: "1", image: "/slow.jpg", text: "Hello text" } }) });</script>
<script src="/assets/sok_resdesk/js/a11y.js"></script>
<script src="/assets/sok_resdesk/js/reader.js"></script>
"""


def _open(page, site):
	held = []
	page.route("**/slow.jpg", lambda route: held.append(route))  # the image waits until the test lets it go
	page.goto(site.write("reader.html", page_shell(BODY)), wait_until="domcontentloaded")
	return held


def test_a_slow_image_is_announced_and_the_notice_goes_when_it_arrives(page, site):
	held = _open(page, site)
	page.wait_for_selector(".rd-slow", timeout=9000)  # after five seconds
	assert page.get_attribute(".rd-slow", "role") == "status"
	assert "Hello text" in page.inner_text("#rd-pages-text")  # the text is already there
	held[0].fulfill(status=200, content_type="image/png", body=PNG)
	page.wait_for_selector(".rd-slow", state="detached")


def test_an_image_that_fails_shows_the_usual_message_not_the_slow_one(page, site):
	held = _open(page, site)
	page.wait_for_selector(".rd-slow", timeout=9000)
	held[0].abort()
	page.wait_for_selector("#rd-pages-image [data-to-book]")
	assert page.locator(".rd-slow").count() == 0
