"""0.84: old Kannada font text converted when a PDF's text layer is read."""

import shutil
import unittest
from unittest import mock

import frappe
from frappe.tests import IntegrationTestCase

from sok_resdesk import legacy_kannada

UNICODE = "ಕನ್ನಡ ಸಾಹಿತ್ಯ ಪರಿಷತ್ತು ಕರ್ನಾಟಕ ಸರ್ಕಾರದ ಗ್ರಂಥಾಲಯ ಇಲಾಖೆಯ ಹಳೆಯ ಪುಸ್ತಕಗಳು"
NUDI = "PÀ£ï£ÀqÀ ¸Á»vïAiÀÄ ¥ÀjµÀvïvÀÄ PÀgï£ÁlPÀ ¸ÀgïPÁgÀzÀ UïgÀAxÁ®AiÀÄ E¯ÁSÉAiÀÄ ºÀ¼ÉAiÀÄ ¥ÀÅ¸ïvÀPÀUÀ¼ÀÄ"
ENGLISH = "The district library keeps its records of the department for twenty years before review."


class TestLegacyKannada(IntegrationTestCase):
	def setUp(self):
		self.was = frappe.db.get_single_value("RD Settings", "legacy_kannada_font")
		self.addCleanup(
			lambda: frappe.db.set_single_value("RD Settings", "legacy_kannada_font", self.was or "Off")
		)

	def pages(self):
		return [{"leaf": 0, "label": "", "text": NUDI}, {"leaf": 1, "label": "", "text": ENGLISH}]

	def test_nothing_changes_while_the_setting_is_off(self):
		frappe.db.set_single_value("RD Settings", "legacy_kannada_font", "Off")
		pages = self.pages()
		assert legacy_kannada.fix_pages(pages) == pages

	@unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
	def test_a_page_in_the_chosen_font_is_converted_and_an_english_page_is_not(self):
		frappe.db.set_single_value("RD Settings", "legacy_kannada_font", "Nudi / Baraha")
		fixed = legacy_kannada.fix_pages(self.pages())
		assert fixed[0]["text"] == UNICODE and fixed[1]["text"] == ENGLISH

	def test_a_failing_converter_keeps_the_text_and_does_not_stop_the_ingest(self):
		frappe.db.set_single_value("RD Settings", "legacy_kannada_font", "Nudi / Baraha")
		pages = self.pages()
		with mock.patch.object(legacy_kannada, "convert", side_effect=legacy_kannada.ConverterError("no")):
			assert legacy_kannada.fix_pages(pages) == pages

	def test_only_staff_may_use_the_tool_and_the_font_must_be_known(self):
		with self.assertRaises(frappe.ValidationError):
			legacy_kannada.convert_text("x", "not a font")

	def test_pages_go_to_the_converter_in_batches_of_bounded_size(self):
		frappe.db.set_single_value("RD Settings", "legacy_kannada_font", "Nudi / Baraha")
		calls = []

		def fake(texts, font, *a, **k):
			calls.append(sum(len(t) for t in texts))
			return ["x" for _ in texts]

		pages = [
			{"leaf": i, "label": "", "text": NUDI * 400} for i in range(40)
		]  # about 36,000 characters a page
		with mock.patch.object(legacy_kannada, "convert", side_effect=fake):
			fixed = legacy_kannada.fix_pages(pages)
		assert all(c <= legacy_kannada.BATCH_CHARS + len(NUDI * 400) for c in calls) and len(calls) > 1
		assert all(p["text"] == "x" for p in fixed)
