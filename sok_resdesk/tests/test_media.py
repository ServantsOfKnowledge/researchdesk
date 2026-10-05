"""0.57: recordings through an ingest run: files, transcript segments as pages, captions, the IIIF
manifest, access, and the tools staff use. The search engine is stood in for."""

import json
import os
import shutil
import struct
import tempfile
import wave
from unittest import mock

import frappe

from sok_resdesk.tests.test_operations import OpsTestCase

ID = "av-talks-Ramesh-2019"
VTT = """WEBVTT

00:00:01.000 --> 00:00:30.500
ನಮಸ್ಕಾರ. ಇದು ಮೊದಲ ಭಾಗ.

00:00:31.000 --> 00:01:05.000
Second part of the talk, in English. It ends here.

00:01:06.000 --> 00:01:20.000
A short last part.
"""


def write_wav(path, seconds=90):
	with wave.open(path, "wb") as w:
		w.setnchannels(1)
		w.setsampwidth(2)
		w.setframerate(8000)
		w.writeframes(struct.pack("<h", 0) * 8000 * seconds)


class TestRecordings(OpsTestCase):
	def setUp(self):
		super().setUp()
		frappe.db.set_single_value("RD Settings", {"book_limit": "No limit", "feature_media": 1})
		self.root = tempfile.mkdtemp(prefix="rd-av-")
		frappe.local.conf["resdesk_library_roots"] = [self.root]
		talks = os.path.join(self.root, "talks")
		os.makedirs(talks)
		write_wav(os.path.join(talks, "Ramesh 2019.wav"))
		with open(os.path.join(talks, "Ramesh 2019.vtt"), "w", encoding="utf-8") as f:
			f.write(VTT)
		with open(os.path.join(talks, "Ramesh 2019.json"), "w", encoding="utf-8") as f:
			json.dump(
				{
					"title": "Ramesh on temple music",
					"creator": ["Ramesh, K."],
					"language": "kan",
					"date": "2019",
					"recording": {
						"speakers": ["K. Ramesh", "An interviewer"],
						"place": "Udupi",
						"consent": "Consent on file",
					},
				},
				f,
			)
		with open(os.path.join(talks, "Silent.wav"), "wb") as f:
			pass
		write_wav(os.path.join(talks, "Silent.wav"), 30)  # a second recording, with no transcript
		for p in (
			mock.patch("sok_resdesk.search.index_record", return_value=0),
			mock.patch("sok_resdesk.search.IndexBuffer.flush"),
			mock.patch("sok_resdesk.search.update_item_fields"),
			mock.patch("sok_resdesk.search.remove_record"),
			mock.patch("sok_resdesk.search.MeiliClient.from_settings"),
		):
			p.start()
			self.addCleanup(p.stop)
		self.profile = frappe.get_doc(
			{
				"doctype": "RD Ingest Profile",
				"profile_name": "rdtest recordings",
				"source": "Folder or Server",
				"location": self.root,
				"fetch_fulltext": 1,
				"check_archive_org": 1,
			}
		).insert(ignore_permissions=True)
		frappe.db.commit()
		self.addCleanup(self._clean)

	def _clean(self):
		for name in frappe.get_all("RD Item", filters={"name": ("like", "av-%")}, pluck="name"):
			frappe.delete_doc("RD Item", name, force=True, ignore_permissions=True)
		frappe.db.delete("RD Ingest Run", {"profile": self.profile.name})
		frappe.db.delete("RD Ingest Profile", self.profile.name)
		frappe.db.delete("RD Creator", {"name": "Ramesh, K."})
		frappe.local.conf.pop("resdesk_library_roots", None)
		frappe.db.set_single_value("RD Settings", "feature_media", 1)
		shutil.rmtree(self.root, ignore_errors=True)
		frappe.db.commit()

	def run_profile(self):
		from sok_resdesk.ingest import create_run, run_ingest

		with mock.patch("sok_resdesk.local_source.on_archive_org") as asked:
			run = create_run(frappe.get_doc("RD Ingest Profile", self.profile.name), "Manual")
			frappe.db.commit()
			run_ingest(run.name, foreground=True)
		asked.assert_not_called()  # a recording is never looked for on archive.org
		return frappe.get_doc("RD Ingest Run", run.name)

	def publish(self):
		frappe.db.set_value("RD Item", ID, {"published": 1, "visibility": "Public", "access_status": "Open"})

	def test_a_recording_in_a_folder_with_its_transcript(self):
		from sok_resdesk.catalogue import item_to_record
		from sok_resdesk.ingest import fetch_pages

		run = self.run_profile()
		self.assertEqual((run.status, run.created_count), ("Completed", 2), run.log)
		book = frappe.get_doc("RD Item", ID)
		self.assertEqual(
			(book.title, book.item_type, book.language, book.source),
			("Ramesh on temple music", "Audio", "kan", "Local"),
		)
		self.assertEqual((book.duration, book.page_count, book.has_page_text), (90, 2, 1))
		self.assertEqual(book.rec_place, "Udupi")
		self.assertEqual(book.rec_speakers.splitlines(), ["K. Ramesh", "An interviewer"])
		self.assertEqual(book.local_files.splitlines(), ["Ramesh 2019.wav", "Ramesh 2019.vtt"])
		pages = fetch_pages(ID)
		self.assertEqual([(p["leaf"], p["label"]) for p in pages], [(0, "0:01"), (1, "1:06")])
		self.assertTrue(
			pages[0]["text"].startswith("ನಮಸ್ಕಾರ. ಇದು ಮೊದಲ ಭಾಗ. Second part")
		)  # cues join into a segment of about 30 s
		record = item_to_record(book)
		self.assertEqual(record["media"]["kind"], "Audio")
		self.assertEqual(record["media"]["files"][0]["mime"], "audio/wav")
		self.assertIn(
			"api.file?item_id=av-talks-Ramesh-2019&name=Ramesh%202019.wav", record["media"]["files"][0]["url"]
		)
		self.assertEqual(
			[r["label"] for r in record["recording"]], ["Speakers", "Place recorded", "Speaker's consent"]
		)
		# the second recording has no transcript: found by its details, with nothing to read yet
		silent = frappe.get_doc("RD Item", "av-talks-Silent")
		self.assertEqual((silent.duration, silent.has_page_text, silent.page_count), (30, 0, 0))

	def test_a_second_run_changes_nothing_and_a_switched_off_feature_collects_nothing(self):
		self.run_profile()
		modified = frappe.db.get_value("RD Item", ID, "modified")
		self.assertEqual(self.run_profile().created_count, 0)
		self.assertEqual(frappe.db.get_value("RD Item", ID, "modified"), modified)
		frappe.delete_doc("RD Item", ID, force=True, ignore_permissions=True)
		frappe.db.set_single_value("RD Settings", "feature_media", 0)
		self.assertEqual(self.run_profile().created_count, 0)  # not collected
		self.assertFalse(frappe.db.exists("RD Item", ID))

	def test_the_transcript_and_the_captions_follow_the_access_rules(self):
		from werkzeug.test import EnvironBuilder
		from werkzeug.wrappers import Request

		from sok_resdesk import api

		self.run_profile()
		self.publish()
		frappe.local.request = Request(EnvironBuilder(path="/").get_environ())
		frappe.local.request_ip = "127.0.0.1"
		frappe.set_user("Guest")
		try:
			got = api.transcript(ID)
			self.assertEqual(
				[(s["label"], s["start"], s["end"]) for s in got["segments"]],
				[("0:01", 1.0, 65.0), ("1:06", 66.0, 80.0)],
			)
			self.assertFalse(got["can_proofread"])
			resp = api.captions(ID)
			vtt = resp.get_data(as_text=True)
			self.assertEqual(resp.mimetype, "text/vtt")
			self.assertIn("00:00:01.000 --> 00:01:05.000\nನಮಸ್ಕಾರ. ಇದು ಮೊದಲ ಭಾಗ. Second part of the talk", vtt)
			self.assertTrue(vtt.startswith("WEBVTT\nLanguage: kan"))
			# a recording for logged-in readers only
			frappe.set_user("Administrator")
			frappe.db.set_value("RD Item", ID, "visibility", "Login to read")
			frappe.set_user("Guest")
			self.assertEqual(api.transcript(ID), {"login_needed": True})
			with self.assertRaises(frappe.PermissionError):
				api.captions(ID)
		finally:
			frappe.set_user("Administrator")

	def test_the_recording_is_downloadable_and_a_range_can_be_asked_for(self):
		from werkzeug.test import EnvironBuilder
		from werkzeug.wrappers import Request

		from sok_resdesk import api

		self.run_profile()
		self.publish()
		frappe.local.request = Request(
			EnvironBuilder(path="/", headers={"Range": "bytes=0-99"}).get_environ()
		)
		frappe.local.request_ip = "127.0.0.1"
		frappe.set_user("Guest")
		try:
			resp = api.file(ID, "Ramesh 2019.wav")
			self.assertEqual(resp.status_code, 206)  # the player can seek without loading it all
			resp = api.file(ID, "Ramesh 2019.vtt")
			resp.direct_passthrough = False
			self.assertIn("WEBVTT", resp.get_data(as_text=True))
			self.assertRaises(frappe.PageDoesNotExistError, api.file, ID, "Ramesh 2019.json")
		finally:
			frappe.set_user("Administrator")

	def test_the_iiif_manifest_is_a_canvas_with_a_duration_and_the_transcript_by_time(self):
		from werkzeug.test import EnvironBuilder
		from werkzeug.wrappers import Request

		from sok_resdesk import iiif

		self.run_profile()
		self.publish()
		frappe.db.set_single_value("RD Settings", "feature_sharing", 1)
		frappe.local.request = Request(EnvironBuilder(path="/").get_environ())
		frappe.set_user("Guest")
		try:
			m = json.loads(iiif.manifest(ID).get_data(as_text=True))
		finally:
			frappe.set_user("Administrator")
		canvas = m["items"][0]
		self.assertEqual((canvas["type"], canvas["duration"]), ("Canvas", 90))
		body = canvas["items"][0]["items"][0]["body"]
		self.assertEqual((body["type"], body["format"]), ("Sound", "audio/wav"))
		notes = canvas["annotations"][0]["items"]
		self.assertEqual(len(notes), 2)
		self.assertTrue(notes[0]["target"].endswith("#t=1,65"))
		self.assertTrue(notes[1]["target"].endswith("#t=66,80"))
		self.assertEqual(notes[0]["body"]["language"], "kan")

	def test_staff_read_the_length_and_lay_out_blank_segments_for_people_to_transcribe(self):
		from sok_resdesk import api, media, pagetext

		self.run_profile()
		self.publish()
		silent = "av-talks-Silent"
		frappe.db.set_value(
			"RD Item",
			silent,
			{"published": 1, "visibility": "Public", "access_status": "Open", "duration": 0},
		)
		self.assertEqual(media.read_length(silent)["duration"], 30)
		self.assertEqual(media.lay_out_segments(silent, 10)["segments"], 3)
		with self.assertRaisesRegex(frappe.ValidationError, "already"):
			media.lay_out_segments(silent, 10)
		record = api.get_record(silent)
		segs = api._segments(record)
		self.assertEqual(
			[(s["start"], s["end"], s["text"]) for s in segs],
			[(0.0, 10.0, ""), (10.0, 20.0, ""), (20.0, 30.0, "")],
		)
		# a person transcribes the second segment from nothing: the recording becomes searchable
		pagetext.save_page(silent, 1, "ಎರಡನೇ ಭಾಗ")
		self.assertEqual(frappe.db.get_value("RD Item", silent, "has_page_text"), 1)
		again = api._segments(api.get_record(silent))
		self.assertEqual([s["text"] for s in again], ["", "ಎರಡನೇ ಭಾಗ", ""])
		self.assertEqual(again[1]["status"], "Proofread")
