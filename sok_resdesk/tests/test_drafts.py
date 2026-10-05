"""0.63: machine drafts of transcripts, with the engines stood in for. A draft is saved as a Machine
version, searchable and for a person to proofread, and never replaces a person's work."""

from unittest import mock

import frappe

from sok_resdesk import drafts, pagetext
from sok_resdesk.tests.test_photographs import PhotoBase

BUNDLE = "img-Bundle"


class FakeStore:
	def media_files(self, loc):
		return ["talk.mp3"]

	def file_path(self, loc, name):
		return "/tmp/talk.mp3"


class TestDrafts(PhotoBase):
	def setUp(self):
		super().setUp()
		frappe.db.delete("RD Page Text", {"item": BUNDLE})
		self.addCleanup(lambda: frappe.db.delete("RD Page Text", {"item": BUNDLE}))
		self.run_profile(self.bundles)
		frappe.db.set_value("RD Item", BUNDLE, {"published": 1, "visibility": "Public"})
		frappe.db.commit()
		self.patches = [
			mock.patch("sok_resdesk.drafts._finish"),
			mock.patch("sok_resdesk.drafts._notify"),
		]
		for p in self.patches:
			p.start()
			self.addCleanup(p.stop)

	def versions(self):
		return {leaf: (v.status, v.source, v.text) for leaf, v in pagetext.current(BUNDLE).items()}

	def test_which_leaves(self):
		self.assertEqual(drafts.leaf_numbers("", 3), [0, 1, 2])
		self.assertEqual(drafts.leaf_numbers("0-1, 5, x", 4), [0, 1])  # inside the book, junk ignored

	def test_handwriting_drafts_are_machine_versions_and_leave_a_person_s_work_alone(self):
		pagetext.save(BUNDLE, 0, "by a person", "Proofreading", "Proofread", reindex=False)
		with mock.patch("sok_resdesk.drafts._read_leaf", side_effect=lambda i, leaf, e, m: f"draft {leaf}"):
			saved = drafts.run_leaves(BUNDLE, "Administrator")
		self.assertEqual(saved, 1)  # leaf 1 only: leaf 0 is a person's
		v = self.versions()
		self.assertEqual(v[0], ("Proofread", "Proofreading", "by a person"))
		self.assertEqual(v[1], ("Machine", "Machine draft", "draft 1"))
		# a second run replaces the machine draft, still not the person's page
		with mock.patch("sok_resdesk.drafts._read_leaf", side_effect=lambda i, leaf, e, m: f"better {leaf}"):
			drafts.run_leaves(BUNDLE, "Administrator")
		self.assertEqual(self.versions()[1][2], "better 1")
		self.assertEqual(self.versions()[0][0], "Proofread")

	def test_a_leaf_that_cannot_be_read_does_not_stop_the_rest(self):
		def read(item, leaf, engine, model):
			if leaf == 0:
				raise RuntimeError("blurred")
			return "ok"

		with mock.patch("sok_resdesk.drafts._read_leaf", side_effect=read):
			self.assertEqual(drafts.run_leaves(BUNDLE, "Administrator"), 1)

	def test_speech_becomes_transcript_segments(self):
		cues = [
			{"start": 0.0, "end": 31.0, "text": "First part."},
			{"start": 32.0, "end": 70.0, "text": "Second part."},
		]
		with (
			mock.patch("sok_resdesk.local_source.store_for_item", return_value=FakeStore()),
			mock.patch("sok_resdesk.core.draft.transcribe", return_value=cues),
			mock.patch("sok_resdesk.core.draft.asr_engine", return_value="whisper"),
		):
			saved = drafts.run_transcript(BUNDLE, "Administrator")
		self.assertEqual(saved, 2)
		v = self.versions()
		self.assertEqual((v[0][0], v[0][2]), ("Machine", "First part."))
		self.assertEqual(frappe.db.get_value("RD Item", BUNDLE, "page_count"), 2)
		self.assertTrue(frappe.db.get_value("RD Item", BUNDLE, "leaf_times"))
