"""Picking and recognising a collection's picture on archive.org (no network)."""

from sok_resdesk.core.ia import IMAGE_MAX, IAClient, image_candidates, image_kind


def test_image_kind_reads_the_bytes():
	assert image_kind(b"\xff\xd8\xff\xe0xx") == "jpg"
	assert image_kind(b"\x89PNG\r\n\x1a\nxx") == "png"
	assert image_kind(b"GIF89axx") == "gif"
	assert image_kind(b"RIFF\0\0\0\0WEBPxx") == "webp"
	assert image_kind(b"<html>not found</html>") is None
	assert image_kind(b"") is None and image_kind(None) is None
	assert image_kind(b"\xff\xd8\xff" + b"0" * IMAGE_MAX) is None


def test_candidates_thumbnail_then_logos():
	names = ["book.pdf", "SOK_Logo.png", "__ia_thumb.jpg", "banner.webp", "page.jpg"]
	assert image_candidates(names) == ["__ia_thumb.jpg", "SOK_Logo.png", "banner.webp"]


class Resp:
	def __init__(self, status, content=b"", data=None):
		self.status_code, self.content, self._data = status, content, data

	def json(self):
		return self._data


class Session:
	def __init__(self, routes):
		self.routes, self.headers, self.asked = routes, {}, []

	def get(self, url, timeout=None, **kw):
		self.asked.append(url)
		for part, resp in self.routes.items():
			if part in url:
				return resp
		return Resp(404)


def test_the_thumbnail_file_first_then_the_image_service():
	jpg = b"\xff\xd8\xff\xe0thumb"
	s = Session(
		{
			"/metadata/coll": Resp(200, data={"metadata": {"title": "C"}, "files": [{"name": "__ia_thumb.jpg"}]}),
			"/download/coll/__ia_thumb.jpg": Resp(200, jpg),
		}
	)
	assert IAClient(delay=0, session=s).collection_image("coll") == (jpg, "jpg")
	png = b"\x89PNG\r\n\x1a\nsvc"
	s = Session(
		{
			"/metadata/other": Resp(200, data={"metadata": {"title": "O"}, "files": []}),
			"/services/img/other": Resp(200, png),
		}
	)
	assert IAClient(delay=0, session=s).collection_image("other") == (png, "png")
	s = Session({"/metadata/gone": Resp(200, data={})})
	assert IAClient(delay=0, session=s).collection_image("gone") is None
	s = Session(
		{"/metadata/html": Resp(200, data={"metadata": {}, "files": []}), "/services/img/html": Resp(200, b"<html>")}
	)
	assert IAClient(delay=0, session=s).collection_image("html") is None
