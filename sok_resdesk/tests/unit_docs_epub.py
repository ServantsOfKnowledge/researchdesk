"""0.61: the guide as an EPUB: every help page in it, well-formed, with working links and pictures."""

import importlib.util
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

pytest.importorskip("markdown")

from sok_resdesk.core import helpdocs  # noqa: E402

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "docs_epub.py"


@pytest.fixture(scope="module")
def book(tmp_path_factory):
	spec = importlib.util.spec_from_file_location("docs_epub", SCRIPT)
	mod = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(mod)
	out = tmp_path_factory.mktemp("epub") / "guide.epub"
	count = mod.build(out)
	return zipfile.ZipFile(out), count


def test_every_help_page_is_a_chapter_and_the_book_is_well_formed(book):
	z, count = book
	assert count == len(helpdocs.PAGES)
	assert z.namelist()[0] == "mimetype" and z.read("mimetype") == b"application/epub+zip"
	for name in z.namelist():
		if name.endswith((".xhtml", ".opf", ".xml")):
			ET.fromstring(z.read(name))  # raises on a stray <tag>
	for page in helpdocs.PAGES:
		assert f"OEBPS/{page.slug}.xhtml" in z.namelist()


def test_links_between_pages_and_pictures_resolve_inside_the_book(book):
	z, _ = book
	names = set(z.namelist())
	for name in names:
		if not name.endswith(".xhtml"):
			continue
		text = z.read(name).decode()
		for src in re.findall(r'src="(images/[^"]+)"', text):
			assert "OEBPS/" + src in names, (name, src)
		for target, anchor in re.findall(r'href="([a-z0-9-]+\.xhtml)(?:#([^"]+))?"', text):
			assert "OEBPS/" + target in names, (name, target)
			if anchor:
				assert f'id="{anchor}"' in z.read("OEBPS/" + target).decode(), (name, target, anchor)
