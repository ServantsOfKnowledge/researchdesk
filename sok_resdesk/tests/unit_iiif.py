"""IIIF manifests, collections and image requests (no Frappe)."""

import pytest

from sok_resdesk.core import iiif

BASE = "https://lib.example.org"
BOOK = {
	"item_id": "kanakadasa1950",
	"title": "ಕನಕದಾಸರ ಕೀರ್ತನೆಗಳು",
	"creators": ["Kanakadasa"],
	"year": 1950,
	"language": "kan",
	"language_label": "Kannada",
	"publisher": "Mysore Press",
	"subjects": ["Kirtana", "Haridasa"],
	"rights": "Public domain",
	"licence_url": "https://creativecommons.org/publicdomain/mark/1.0/",
	"on_archive_org": True,
	"ark": "ark:/12345/x1",
}


def make(**kw):
	args = dict(
		provider="SOK Research Desk",
		pages=3,
		image_url=lambda leaf: f"https://archive.org/download/kanakadasa1950/page/n{leaf}.jpg",
		book_url=f"{BASE}/library/item/kanakadasa1950",
		marcxml_url=f"{BASE}/marc/kanakadasa1950",
		pdf_url="https://archive.org/download/kanakadasa1950/k.pdf",
		text_pages=True,
		collections=[("vachana", "Vachana literature")],
	)
	args.update(kw)
	return iiif.manifest(BOOK, BASE, **args)


def test_the_manifest_describes_the_book_and_its_pages():
	m = make()
	assert m["@context"] == iiif.PRESENTATION and m["type"] == "Manifest"
	assert m["id"] == f"{BASE}/iiif/kanakadasa1950/manifest"
	assert m["label"] == {"kan": ["ಕನಕದಾಸರ ಕೀರ್ತನೆಗಳು"]}
	meta = {e["label"]["en"][0]: e["value"] for e in m["metadata"]}
	assert meta["Author"] == {"kan": ["Kanakadasa"]} and meta["Date"] == {"none": ["1950"]}
	assert "Series" not in meta and "ISBN" not in meta  # nothing to show, nothing listed
	assert m["rights"] == BOOK["licence_url"]
	assert m["requiredStatement"]["value"] == {"none": ["Public domain"]}
	assert [c["label"] for c in m["items"]] == [{"none": ["1"]}, {"none": ["2"]}, {"none": ["3"]}]
	canvas = m["items"][1]
	assert canvas["id"] == f"{BASE}/iiif/kanakadasa1950/canvas/1"
	anno = canvas["items"][0]["items"][0]
	assert anno["motivation"] == "painting" and anno["target"] == canvas["id"]
	assert anno["body"]["id"].endswith("/page/n1.jpg") and "service" not in anno["body"]
	assert canvas["annotations"] == [{"id": f"{BASE}/iiif/kanakadasa1950/text/1", "type": "AnnotationPage"}]
	assert m["rendering"][0]["format"] == "application/pdf"
	see = {s["format"] for s in m["seeAlso"]}
	assert see == {"application/marcxml+xml", "application/ld+json"}  # and archive.org's own manifest
	assert m["partOf"][0]["id"] == f"{BASE}/iiif/collection/vachana"


def test_rights_only_from_the_hosts_iiif_allows():
	rec = {**BOOK, "licence_url": "https://example.org/our-terms"}
	assert "rights" not in iiif.manifest(rec, BASE, provider="P", pages=0, image_url=str)


def test_an_image_service_on_the_painting():
	m = make(service=lambda leaf: iiif.service(BASE, "kanakadasa1950", leaf), size=(1200, 1700))
	body = m["items"][0]["items"][0]["items"][0]["body"]
	assert body["service"] == [
		{"id": f"{BASE}/iiif/image/kanakadasa1950/0", "type": "ImageService3", "profile": "level2"}
	]
	assert (m["items"][0]["width"], m["items"][0]["height"]) == (1200, 1700)


def test_page_text_as_a_supplementing_annotation():
	page = iiif.text_annotations(BASE, "kanakadasa1950", 2, "ಪುಟ ಮೂರು", "kan")
	anno = page["items"][0]
	assert anno["motivation"] == "supplementing" and anno["body"]["language"] == "kan"
	assert anno["target"] == f"{BASE}/iiif/kanakadasa1950/canvas/2"
	assert iiif.text_annotations(BASE, "x", 0, "   ")["items"] == []  # a blank page has no annotation


def test_collections_page_through_big_ones():
	books = [(f"b{i}", f"Book {i}") for i in range(iiif.PER_PAGE)]
	c = iiif.collection(BASE, "Vachana", books, name="vachana", total=iiif.PER_PAGE + 5)
	assert c["next"]["id"].endswith("/iiif/collection/vachana?page=2")
	assert c["items"][0] == {
		"id": f"{BASE}/iiif/b0/manifest",
		"type": "Manifest",
		"label": {"none": ["Book 0"]},
	}
	last = iiif.collection(BASE, "Vachana", books[:5], name="vachana", page=2, total=iiif.PER_PAGE + 5)
	assert "next" not in last and last["partOf"][0]["id"].endswith("/iiif/collection/vachana")
	top = iiif.collection(BASE, "All", [], subcollections=[("vachana", "Vachana")])
	assert top["items"][0]["type"] == "Collection" and top["id"] == f"{BASE}/iiif/collection"


def test_image_info_lists_only_widths_the_page_has():
	info = iiif.image_info(BASE, "x", 4, 1000, 1400)
	assert info["profile"] == "level2" and info["type"] == "ImageService3"
	assert [s["width"] for s in info["sizes"]] == [400, 800, 1000]
	assert info["sizes"][0]["height"] == 560
	assert [s["width"] for s in iiif.image_info(BASE, "x", 0, 2000, 2800)["sizes"]] == [400, 800, 1600, 2000]


def plan(rest, w=1000, h=1400):
	return iiif.image_plan(rest, w, h)


def test_the_tiles_listed_cover_the_page_at_every_scale():
	info = iiif.image_info(BASE, "x", 0, 4000, 600)
	assert info["tiles"] == [{"width": 512, "height": 512, "scaleFactors": [1, 2, 4, 8]}]
	assert iiif.image_info(BASE, "x", 0, 300, 200)["tiles"][0]["scaleFactors"] == [1]
	assert "sizeUpscaling" in info["extraFeatures"]


def test_regions():
	assert plan("full/max/0/default.jpg")["region"] == (0, 0, 1000, 1400)
	assert plan("100,200,300,400/max/0/default.jpg")["region"] == (100, 200, 400, 600)
	assert plan("pct:10,10,50,50/max/0/default.jpg")["region"] == (100, 140, 600, 840)
	assert plan("square/max/0/default.jpg")["region"] == (0, 200, 1000, 1200)
	assert plan("900,1300,500,500/max/0/default.jpg")["region"] == (900, 1300, 1000, 1400)  # clipped


def test_sizes():
	assert plan("full/800,/0/default.jpg")["size"] == (800, 1120)
	assert plan("full/,700/0/default.jpg")["size"] == (500, 700)
	assert plan("full/300,300/0/default.jpg")["size"] == (300, 300)  # exactly, not keeping the shape
	assert plan("full/!500,500/0/default.jpg")["size"] == (357, 500)
	assert plan("full/pct:25/0/default.jpg")["size"] == (250, 350)
	assert plan("0,0,100,100/200,/0/default.jpg".replace("200,", "^200,"))["size"] == (
		200,
		200,
	)  # upscaled on request


def test_rotation_quality_and_format():
	p = plan("full/max/!270/gray.png")
	assert (p["rotation"], p["mirror"], p["quality"], p["format"]) == (270, True, "gray", "png")
	assert plan("full/max/0/default.jpg")["quality"] == "color"


def test_the_pixels_come_out_as_asked():
	from PIL import Image

	im = Image.new("RGB", (400, 200), (255, 0, 0))
	im.paste((0, 0, 255), (200, 0, 400, 200))  # the right half is blue
	data, kind = iiif.render_plan(im, iiif.image_plan("200,0,200,200/100,/0/default.jpg", 400, 200))
	assert kind == "image/jpeg"
	import io

	with Image.open(io.BytesIO(data)) as out:
		assert out.size == (100, 100) and out.getpixel((50, 50))[2] > 200  # blue
	turned, _k = iiif.render_plan(im, iiif.image_plan("full/max/90/default.png", 400, 200))
	with Image.open(io.BytesIO(turned)) as out:
		assert out.size == (200, 400)  # a quarter turn swaps the sides
		assert out.getpixel((100, 50))[0] > 200  # the red half is now at the top (clockwise)


@pytest.mark.parametrize(
	"rest,status",
	[
		("full/max", 400),
		("full/max/0/default", 501),
		("full/max/45/default.jpg", 501),
		("full/max/0/sepia.jpg", 501),
		("full/max/0/default.webp", 501),
		("2000,0,10,10/max/0/default.jpg", 400),
		("full/2000,/0/default.jpg", 400),  # larger than the page without ^
		("full/0,/0/default.jpg", 400),
		("full/banana/0/default.jpg", 400),
		("full/20000,/0/default.jpg".replace("20000", "^20000"), 400),  # over what the server makes
	],
)
def test_image_requests_refused(rest, status):
	with pytest.raises(iiif.BadRequest) as e:
		plan(rest)
	assert e.value.status == status
