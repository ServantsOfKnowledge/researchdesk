"""0.66: the identifier, headers and checks for giving a book to the Internet Archive."""

from sok_resdesk.core import ia_upload as ia
from sok_resdesk.core.push import IAWriter


def test_identifiers_are_made_safe_and_checked():
	assert ia.clean_identifier("The Red Fort: a history!") == "The-Red-Fort-a-history"
	assert ia.clean_identifier("ಕನಕದಾಸ") == ""
	assert (
		ia.make_identifier("Vachanas", 1880, "Basava, Guru", "dep-00077") == "Vachanas-Basava-1880-dep-00077"
	)
	assert ia.make_identifier("ಕನಕದಾಸ", 1900, "", "dep-5") == "1900-dep-5"
	assert ia.identifier_problem("Vachanas-1880") == ""
	assert ia.identifier_problem("ab") != ""
	assert ia.identifier_problem("-bad") != ""
	assert ia.collection_problem("opensource") == ""
	assert ia.collection_problem("has space") != ""


def test_headers_carry_the_details_and_never_make_a_dark_item():
	h = ia.metadata_headers(
		title="Red Fort",
		collection="opensource",
		creators=["A", "B"],
		subjects=["Delhi"],
		date="1880",
		licence_url="https://creativecommons.org/licenses/by/4.0/",
	)
	assert h["x-archive-meta-collection"] == "opensource"
	assert h["x-archive-meta-mediatype"] == "texts"
	assert h["x-archive-auto-make-bucket"] == "1"
	assert h["x-archive-meta01-creator"] == "A" and h["x-archive-meta02-creator"] == "B"
	assert h["x-archive-meta01-subject"] == "Delhi"
	assert not any("noindex" in k or "hidden" in k for k in h)


def test_text_outside_ascii_is_sent_as_uri():
	assert ia.header_value("ಕನಕ  ದಾಸ").startswith("uri(%E0%B2")
	assert ia.header_value("plain  text") == "plain text"


def test_media_type_and_file_names():
	assert ia.mediatype(["a.mp3"]) == "audio"
	assert ia.mediatype(["x.xyz", "b.pdf"]) == "texts"
	assert ia.file_name("My book (1).PDF") == "My_book_1.pdf"


class FakeSession:
	def __init__(self):
		self.calls = []
		self.headers = {}

	def put(self, url, data=None, headers=None, timeout=None):
		self.calls.append((url, headers))

		class R:
			status_code = 200
			text = ""

		return R()


def test_the_writer_puts_a_file_with_the_keys():
	s = FakeSession()
	IAWriter("K", "S", session=s).upload("my-id", "a b.pdf", b"x", {"x-archive-meta-title": "T"})
	url, headers = s.calls[0]
	assert url == "https://s3.us.archive.org/my-id/a%20b.pdf"
	assert headers["Authorization"] == "LOW K:S" and headers["x-archive-meta-title"] == "T"
