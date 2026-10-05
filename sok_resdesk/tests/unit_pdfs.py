"""Loose PDFs in folders (core/folder.py) and drawing PDF pages (core/pdfrender.py). Pure Python."""

import io
import os

from PIL import Image

from sok_resdesk.core import folder, pdfrender
from sok_resdesk.tests.oai_fixtures import make_pdf


def scan_pdf(pages: int = 2) -> bytes:
	"""A PDF that is only page images, as a scanner makes."""
	imgs = [Image.new("L", (850, 1100), 255) for _ in range(pages)]
	buf = io.BytesIO()
	imgs[0].save(buf, format="PDF", save_all=True, append_images=imgs[1:], resolution=100)
	return buf.getvalue()


def test_identifiers_and_titles_for_loose_pdfs():
	assert folder.bare_id("Some thesis (2019).pdf") == "Some-thesis-2019"
	assert folder.bare_id("ಕನ್ನಡ.pdf").startswith("pdf-")  # nothing usable: a fingerprint
	meta = folder.bare_meta(
		"x", "ವಚನ_ಸಾಹಿತ್ಯ.pdf", {"title": "Microsoft Word - draft.docx", "author": "A. Rao; B. Shetty"}
	)
	assert meta["title"] == "ವಚನ ಸಾಹಿತ್ಯ"  # the file name, not Word's
	assert meta["creator"] == ["A. Rao", "B. Shetty"]
	assert folder.bare_meta("x", "f.pdf", {"title": "Vachana Sahitya"})["title"] == "Vachana Sahitya"


def test_a_folder_of_loose_pdfs(tmp_path):
	(tmp_path / "theses").mkdir()
	(tmp_path / "theses" / "A thesis.pdf").write_bytes(make_pdf(["Some text on the first page here"]))
	(tmp_path / "theses" / "Scan 2.pdf").write_bytes(scan_pdf())
	item = tmp_path / "ia-item"
	item.mkdir()
	(item / "ia-item_meta.xml").write_bytes(b"<metadata><title>T</title></metadata>")
	(item / "ia-item.pdf").write_bytes(make_pdf(["x"]))  # an item folder's PDF is not a loose one
	store = folder.FolderStore(str(tmp_path))
	items = dict(store.iter_items())
	assert items == {
		"ia-item": "ia-item",
		"A-thesis": os.path.join("theses", "A thesis.pdf"),
		"Scan-2": os.path.join("theses", "Scan 2.pdf"),
	}
	loc = items["A-thesis"]
	data = store.load_item("A-thesis", loc)
	assert data["metadata"]["title"] == "A thesis"
	assert store.pdf_name("A-thesis", loc) == "A thesis.pdf"
	assert store.file_path(loc, "A thesis.pdf").endswith("A thesis.pdf")
	sig = store.signature(loc, "A-thesis")
	assert sig == store.signature(loc, "A-thesis") and len(sig) == 16


def test_a_scanned_page_is_drawn_from_its_image(tmp_path):
	path = tmp_path / "scan.pdf"
	path.write_bytes(scan_pdf(3))
	assert pdfrender.page_count(str(path)) == 3
	png = pdfrender._largest_image(str(path), 1, 150, True, "png")
	img = Image.open(io.BytesIO(png))
	assert img.mode == "L" and img.width > 100
	jpeg = pdfrender._largest_image(str(path), 0, 100, False, "jpeg")
	assert jpeg[:2] == b"\xff\xd8"
