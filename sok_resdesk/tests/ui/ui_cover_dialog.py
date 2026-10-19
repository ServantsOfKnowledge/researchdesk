"""The Desk's "Cover parts of a page" dialog (governance edition), in a real browser.

There is no Desk here: the doctype's own script runs against a small stand-in for `frappe` (a dialog that
makes real inputs, and `frappe.call` replies the test controls). What is tested is the script's
behaviour: drawing with the pointer, the guards against adding to a page that is not on the screen, and
a late reply for an old page being ignored. CI's Docker jobs remain the test against a live Desk.
"""

from urllib.parse import unquote

import pytest

from .conftest import APP

SCRIPT = (
	APP.parent
	/ "governance"
	/ "sok_resdesk_governance"
	/ "resdesk_governance"
	/ "doctype"
	/ "rd_disclosure_request"
	/ "rd_disclosure_request.js"
)

STUB = """
window.__ = (s, a) => (a || []).reduce((t, v, i) => t.replace('{' + i + '}', v), s);
window.__pending = []; window.__msgs = []; window.__form = {};
const PAGE = (n) => 'data:image/svg+xml,' + encodeURIComponent(
  '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="500"><text x="10" y="50">page ' + n + '</text></svg>');
window.PAGE = PAGE;
window.frappe = {
  ui: {
    form: { on: (name, h) => { window.__form = h; } },
    Dialog: class {
      constructor(o) {
        this.o = o; this.fields = {};
        this.$body = $('<div class="dlg"></div>');
        for (const f of o.fields) {
          if (/Break/.test(f.fieldtype)) continue;
          const w = $('<div></div>').attr('data-f', f.fieldname).appendTo(this.$body);
          let input = null;
          if (f.fieldtype === 'Select') {
            input = $('<select></select>').attr('aria-label', f.label || f.fieldname);
            f.options.forEach((x) => input.append($('<option>').val(x).text(x)));
          } else if (f.fieldtype !== 'HTML') {
            input = $('<input>').attr('aria-label', f.label || f.fieldname);
          }
          if (input) { input.attr('name', f.fieldname).val(f.default ?? '').appendTo(w);
            input.on('change', () => f.change && f.change()); }
          this.fields[f.fieldname] = { $wrapper: w, input };
        }
        $('<button class="primary"></button>').text(o.primary_action_label).appendTo(this.$body).on('click', o.primary_action);
      }
      get_field(n) { return this.fields[n]; }
      get_value(n) { return this.fields[n].input.val(); }
      set_value(n, v) { this.fields[n].input.val(v ?? ''); }
      show() { $('body').append($('<div id="dialog"></div>').append(this.$body)); }
      hide() { $('#dialog').remove(); }
    },
  },
  call: (o) => new Promise((resolve, reject) => window.__pending.push({ args: o.args, resolve, reject })),
  msgprint: (m) => window.__msgs.push(m),
};
"""

FRM = """
window.buttons = {};
window.frm = { doc: { name: 'DR-1', status: 'In review', records: [{ item: 'A' }, { item: 'B' }], redactions: [] },
  is_new: () => false, add_custom_button: (l, f) => { window.buttons[l] = f; },
  add_child: (t, row) => window.frm.doc[t].push(row), refresh_field() {}, dirty() {}, dashboard: { set_headline() {} },
  reload_doc() {} };
"""


@pytest.fixture
def dialog(page, site):
	if not SCRIPT.exists():
		pytest.skip("the governance app is not in this checkout")
	body = (
		'<script src="/jquery.min.js"></script><div id="root"></div>'
		f"<script>{STUB}</script><script>{SCRIPT.read_text(encoding='utf-8')}</script>"
		f"<script>{FRM}; window.__form.refresh(window.frm); window.buttons['Cover Parts of a Page']();</script>"
	)
	page.goto(site.write("cover.html", f"<!doctype html><html lang='en'><body>{body}</body></html>"))
	page.wait_for_selector(".dlg")
	return page


def _reply(page, index, n):
	page.evaluate(
		"([i, n]) => window.__pending[i].resolve({ message: { image: PAGE(n), pages: 9 } })", [index, n]
	)


def _status(page):
	return page.inner_text(".rd-cover-status")


def test_a_box_cannot_be_added_before_the_page_is_shown(dialog):
	assert "Loading" in _status(dialog)
	dialog.fill("[name=left]", "10")
	dialog.fill("[name=top]", "10")
	dialog.fill("[name=width]", "20")
	dialog.fill("[name=height]", "20")
	dialog.click(".primary")
	assert dialog.evaluate("window.frm.doc.redactions.length") == 0
	assert "Wait for the page" in dialog.evaluate("window.__msgs[0]")


def test_drawing_with_the_pointer_adds_a_box_in_percent_of_the_page(dialog):
	_reply(dialog, 0, 1)
	dialog.wait_for_function("document.querySelector('.rd-cover img').getAttribute('src')")
	box = dialog.locator(".rd-cover").bounding_box()
	x, y = box["x"], box["y"]
	dialog.mouse.move(x + box["width"] * 0.1, y + box["height"] * 0.2)
	dialog.mouse.down()
	dialog.mouse.move(x + box["width"] * 0.4, y + box["height"] * 0.3)
	dialog.mouse.up()
	assert abs(float(dialog.input_value("[name=left]")) - 10) < 1
	assert abs(float(dialog.input_value("[name=top]")) - 20) < 1
	assert abs(float(dialog.input_value("[name=width]")) - 30) < 1
	assert abs(float(dialog.input_value("[name=height]")) - 10) < 1
	dialog.click(".primary")
	rows = dialog.evaluate("window.frm.doc.redactions")
	assert len(rows) == 1 and rows[0]["item"] == "A" and rows[0]["page"] == 1
	assert 0 <= rows[0]["left"] and rows[0]["left"] + rows[0]["width"] <= 100
	assert "Added" in _status(dialog)


def test_a_box_leaving_the_page_is_refused(dialog):
	_reply(dialog, 0, 1)
	dialog.wait_for_function("document.querySelector('.rd-cover img').getAttribute('src')")
	for name, value in (("left", "80"), ("top", "10"), ("width", "30"), ("height", "10")):
		dialog.fill(f"[name={name}]", value)
	dialog.click(".primary")
	assert dialog.evaluate("window.frm.doc.redactions.length") == 0
	assert "stay inside" in dialog.evaluate("window.__msgs[0]")


def test_a_late_reply_for_an_old_page_is_ignored(dialog):
	dialog.fill("[name=page]", "2")
	dialog.dispatch_event("[name=page]", "change")  # a second request, while the first is unanswered
	assert dialog.evaluate("window.__pending.length") == 2
	_reply(dialog, 1, 2)
	dialog.wait_for_function("document.querySelector('.rd-cover img').getAttribute('src')")
	_reply(dialog, 0, 1)  # the first page's reply arrives last
	dialog.wait_for_timeout(100)
	src = dialog.get_attribute(".rd-cover img", "src")
	assert ">page 2<" in unquote(src)
	assert "Page 2 of 9" in _status(dialog)
