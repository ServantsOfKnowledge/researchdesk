"""Integration tests for 0.34, the portal in other languages: portal languages in Settings, the
Portal Translations page (save, spreadsheet out and back), the library's own words, and what a
portal page sends the browser."""

import frappe

from sok_resdesk.tests.test_operations import OpsTestCase

SOURCE = "rdtest phrase {0}"


class TranslationsTestCase(OpsTestCase):
	def setUp(self):
		super().setUp()
		self._langs = frappe.db.get_single_value("RD Settings", "portal_languages")
		self.addCleanup(self._back)

	def _back(self):
		frappe.db.set_single_value("RD Settings", "portal_languages", self._langs)
		frappe.db.delete("Translation", {"source_text": ("like", "rdtest%")})
		frappe.db.commit()
		frappe.local.lang = "en"

	def _offer(self, codes: str):
		s = frappe.get_doc("RD Settings")
		s.portal_languages = codes
		s.save()


class TestPortalLanguages(TranslationsTestCase):
	def test_codes_are_checked_and_switched_on(self):
		from sok_resdesk import translations

		self._offer("kn, hi\nkn\nen")
		self.assertEqual(translations.portal_languages(), ["kn", "hi"])
		self.assertEqual(frappe.db.get_value("Language", "kn", "enabled"), 1)
		s = frappe.get_doc("RD Settings")
		s.portal_languages = "kn\nxx-nope"
		self.assertRaises(frappe.ValidationError, s.save)


class TestPortalTranslations(TranslationsTestCase):
	def test_save_overview_and_remove(self):
		from sok_resdesk import translations

		self._offer("kn")
		self.assertEqual(translations._save("kn", SOURCE, "rdtest ಪದ {0}"), "added")
		self.assertEqual(translations._save("kn", SOURCE, "rdtest ಪದ {0}"), "unchanged")
		self.assertEqual(translations._save("kn", SOURCE, "rdtest ಹೊಸ ಪದ {0}"), "changed")
		self.assertRaises(frappe.ValidationError, translations._save, "kn", SOURCE, "no place")
		frappe.local.lang = "kn"
		self.assertEqual(frappe._(SOURCE), "rdtest ಹೊಸ ಪದ {0}")  # Frappe serves it
		self.assertEqual(translations._save("kn", SOURCE, ""), "removed")
		self.assertFalse(frappe.db.exists("Translation", {"source_text": SOURCE}))

		data = translations.overview()
		self.assertEqual([lang["code"] for lang in data["languages"]], ["kn"])
		sources = {r["source"]: r for r in data["rows"]}
		self.assertIn("Add to my list", sources)  # a script phrase
		self.assertTrue(sources["Add to my list"]["script"])
		self.assertIn("All collections", sources)  # a template phrase

	def test_spreadsheet_out_and_back(self):
		from sok_resdesk import translations
		from sok_resdesk.core import phrases

		self._offer("kn\nhi")
		sheet = phrases.to_csv(
			[
				{"source": "rdtest Search", "where": "", "t": {"kn": "rdtest ಹುಡುಕಿ", "hi": ""}},
				{"source": SOURCE, "where": "", "t": {"kn": "rdtest {0} ಪದ", "hi": "rdtest no place"}},
			],
			["kn", "hi", "ta"],
		)
		out = translations.upload(sheet)
		self.assertEqual(out["added"], 2)
		self.assertEqual(out["skipped"], 1)  # the Hindi one lost its {0}
		self.assertEqual(out["not_offered"], ["ta"])
		self.assertEqual(
			frappe.db.get_value(
				"Translation", {"source_text": "rdtest Search", "language": "kn"}, "translated_text"
			),
			"rdtest ಹುಡುಕಿ",
		)
		self.assertEqual(translations.upload(sheet)["unchanged"], 2)


class TestOnThePortal(TranslationsTestCase):
	def test_library_words_and_script_messages(self):
		from sok_resdesk import translations

		self._offer("kn")
		frappe.get_doc(
			{
				"doctype": "Translation",
				"language": "kn",
				"source_text": "Add to my list",
				"translated_text": "rdtest ಸೇರಿಸಿ",
			}
		).insert()
		frappe.get_doc(
			{
				"doctype": "Translation",
				"language": "kn",
				"source_text": "rdtest Old maps",
				"translated_text": "rdtest ಹಳೆಯ ನಕ್ಷೆಗಳು",
			}
		).insert()
		frappe.local.lang = "kn"
		self.assertEqual(translations.tr("rdtest Old maps"), "rdtest ಹಳೆಯ ನಕ್ಷೆಗಳು")
		self.assertEqual(translations.script_messages("kn").get("Add to my list"), "rdtest ಸೇರಿಸಿ")
		head = translations.website_context(frappe._dict(path="library/item/x"))["head_include"]
		self.assertIn("window.RD_I18N", head)
		self.assertIn('"code": "kn"', head)
		self.assertIn("rdtest ಸೇರಿಸಿ", head)
		self.assertIsNone(translations.website_context(frappe._dict(path="app/rd-item")))
		frappe.local.lang = "en"
		self.assertEqual(translations.tr("rdtest Old maps"), "rdtest Old maps")
		self.assertEqual(translations.script_messages("en"), {})


class TestDeskKeepsItsLanguage(TranslationsTestCase):
	"""0.40: the portal's language switch is for the portal; the Desk keeps the account's language."""

	def request(self, path, referer=""):
		from types import SimpleNamespace

		return SimpleNamespace(
			path=path, cookies={"preferred_language": "kn"}, headers={"Referer": referer} if referer else {}
		)

	def test_switch_leaves_the_account_alone(self):
		from unittest import mock

		from sok_resdesk import translations

		self._offer("kn")
		before = frappe.db.get_value("User", "Administrator", "language")
		with mock.patch.object(frappe.local, "cookie_manager", mock.MagicMock(), create=True):
			translations.set_language("kn")
		self.assertEqual(frappe.db.get_value("User", "Administrator", "language"), before)

	def test_portal_pages_follow_the_switch_and_the_desk_does_not(self):
		from sok_resdesk import translations

		self._offer("kn")
		had, saved = hasattr(frappe.local, "request"), getattr(frappe.local, "request", None)
		self.addCleanup(
			lambda: setattr(frappe.local, "request", saved) if had else delattr(frappe.local, "request")
		)
		for path, referer, lang in (
			("/library", "", "kn"),
			("/library/item/x", "", "kn"),
			("/api/method/sok_resdesk.api.page", "https://lib.example/library/item/x", "kn"),
			("/app/rd-item", "", "en"),
			("/api/method/frappe.desk.form.load.getdoc", "https://lib.example/app/rd-item/x", "en"),
		):
			frappe.local.lang = "en"
			frappe.local.request = self.request(path, referer)
			translations.portal_language()
			self.assertEqual(frappe.local.lang, lang, path)
