"""0.58: photographs: EXIF, details from a person, identifiers (no Frappe)."""

import json

from PIL import Image

from sok_resdesk.core import photo


def make_photo(path, with_exif=True, size=(640, 480)):
	im = Image.new("RGB", size, (200, 120, 60))
	if not with_exif:
		im.save(path, "JPEG")
		return
	exif = Image.Exif()
	exif[photo.T_MAKE] = "Nikon"
	exif[photo.T_MODEL] = "FM2"
	exif[photo.T_ARTIST] = "K. Ramesh"
	exif[photo.T_DESC] = "A temple car at dusk"
	exif[photo.T_COPYRIGHT] = "(c) Ramesh"
	exif.get_ifd(photo.IFD_EXIF)[photo.T_TAKEN] = "1987:03:14 18:20:00"
	gps = exif.get_ifd(photo.IFD_GPS)
	gps[1], gps[2] = "N", (13.0, 20.0, 0.0)
	gps[3], gps[4] = "E", (74.0, 45.0, 0.0)
	im.save(path, "JPEG", exif=exif)


def test_exif_is_read_from_the_file(tmp_path):
	p = str(tmp_path / "a.jpg")
	make_photo(p)
	info = photo.exif_info(p)
	assert info["taken_on"] == "1987-03-14" and info["camera"] == "Nikon FM2"
	assert (info["photographer"], info["description"], info["copyright"]) == (
		"K. Ramesh",
		"A temple car at dusk",
		"(c) Ramesh",
	)
	assert (info["lat"], info["lon"]) == (13.333333, 74.75)
	assert (info["width"], info["height"]) == (640, 480)


def test_a_file_without_exif_or_not_an_image_gives_what_it_can(tmp_path):
	p = str(tmp_path / "b.jpg")
	make_photo(p, with_exif=False)
	assert photo.exif_info(p) == {"width": 640, "height": 480}
	(tmp_path / "c.jpg").write_bytes(b"not an image")
	assert photo.exif_info(str(tmp_path / "c.jpg")) == {}


def test_dates_and_the_southern_western_hemispheres():
	assert (
		photo.exif_date("2019:03:14 10:22:05") == "2019-03-14"
		and photo.exif_date("0000:00:00") == ""
		and photo.exif_date(None) == ""
	)
	assert photo._degrees((10.0, 30.0, 0.0), "S") == -10.5 and photo._degrees("x", "N") is None


def test_identifiers():
	assert photo.photo_id("1931/Mysore palace.jpg") == "ph-1931-Mysore-palace"
	assert photo.photo_id("a.JPG") == "ph-a"


def test_a_persons_words_win_over_the_cameras():
	exif = {
		"photographer": "Camera Owner",
		"taken_on": "1987-03-14",
		"camera": "Nikon FM2",
		"lat": 13.0,
		"lon": 74.0,
		"width": 640,
		"height": 480,
		"description": "from the camera",
	}
	raw = json.dumps(
		{
			"title": "Ratha at dusk",
			"creator": ["K. Ramesh"],
			"description": "Udupi car festival",
			"subject": ["festivals"],
			"photo": {
				"people": ["A", "B"],
				"place": "Udupi",
				"event": "Paryaya 1987",
				"depicts": ["Q1234", "Q99"],
			},
		}
	).encode()
	meta, fields = photo.sidecar(raw, "IMG_0042", exif)
	assert (meta["title"], meta["creator"], meta["description"], meta["date"]) == (
		"Ratha at dusk",
		["K. Ramesh"],
		"Udupi car festival",
		"1987-03-14",
	)
	assert meta["mediatype"] == "image" and meta["subject"] == ["festivals"]
	assert fields == {
		"ph_people": "A\nB",
		"ph_place": "Udupi",
		"ph_event": "Paryaya 1987",
		"ph_depicts": "Q1234\nQ99",
		"ph_taken_on": "1987-03-14",
		"ph_camera": "Nikon FM2",
		"ph_gps": "13.0, 74.0",
		"ph_dimensions": "640 × 480 px",
	}
	plain, none = photo.sidecar(None, "IMG_0042", {})
	assert plain["title"] == "IMG 0042" and none == {}
	assert photo.sidecar(b"not json", "x", {})[0]["title"] == "x"


def test_fixity_of_the_original(tmp_path):
	p = tmp_path / "a.bin"
	p.write_bytes(b"abc")
	assert photo.sha256_of(str(p)) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
