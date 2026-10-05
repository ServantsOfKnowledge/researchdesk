"""0.64: archival description: levels, reference codes, the hierarchy and its EAD3 form."""

from xml.etree import ElementTree as ET

from sok_resdesk.core import archival as ar

UNITS = [
	{
		"name": "F1",
		"parent": "",
		"ref": "UAS-1",
		"title": "Papers of <A>",
		"level": "Fonds",
		"creator": "A. Scholar",
		"date_text": "1920-1950",
		"year_from": 1920,
		"year_to": 1950,
		"extent": "12 boxes",
		"scope_content": "One.\n\nTwo & three.",
	},
	{"name": "S10", "parent": "F1", "ref": "UAS-1-10", "title": "Letters", "level": "Series"},
	{
		"name": "S2",
		"parent": "F1",
		"ref": "UAS-1-2",
		"title": "Notebooks",
		"level": "Series",
		"language": "kan",
	},
	{"name": "I1", "parent": "S2", "ref": "UAS-1-2-1", "title": "Notebook one", "level": "Item"},
]


def test_reference_codes_are_web_safe():
	assert (
		ar.valid_code("UAS-1.2_a")
		and not ar.valid_code("a/b")
		and not ar.valid_code("a b")
		and not ar.valid_code("")
	)


def test_where_a_unit_may_sit():
	assert ar.child_allowed("", "Fonds") == ""
	assert ar.child_allowed("Fonds", "Series") == "" and ar.child_allowed("Series", "File") == ""
	assert ar.child_allowed("Series", "Sub-series") == "" and ar.child_allowed("Fonds", "Sub-fonds") == ""
	assert (
		ar.child_allowed("Item", "File")
		and ar.child_allowed("File", "Series")
		and ar.child_allowed("", "Series")
	)
	assert ar.child_allowed("Series", "Fonds") and ar.child_allowed("Series", "Sub-fonds")
	assert ar.child_allowed("Collection", "File") == ""  # a collection holds anything below it


def test_ancestors_and_natural_order():
	by = {u["name"]: u for u in UNITS}
	assert [u["ref"] for u in ar.ancestors(by, "I1")] == ["UAS-1", "UAS-1-2"]
	kids = ar.children_of(UNITS)
	assert [u["ref"] for u in kids["F1"]] == ["UAS-1-2", "UAS-1-10"]  # 2 before 10


def test_ead3_is_well_formed_nested_and_escaped():
	xml = ar.ead3("F1", UNITS, "Library <X>", "2026-11-06")
	root = ET.fromstring(xml)
	n = {"e": ar.NS}
	assert root.find("e:archdesc", n).get("level") == "fonds"
	assert root.find("e:archdesc/e:did/e:unittitle", n).text == "Papers of <A>"
	assert root.find("e:archdesc/e:did/e:origination/e:name/e:part", n).text == "A. Scholar"
	series = root.findall("e:archdesc/e:dsc/e:c", n)
	assert [c.find("e:did/e:unitid", n).text for c in series] == ["UAS-1-2", "UAS-1-10"]
	assert series[0].find("e:c", n).get("level") == "item"
	paras = root.findall("e:archdesc/e:scopecontent/e:p", n)
	assert [p.text for p in paras] == ["One.", "Two & three."]
	assert (
		root.find("e:archdesc/e:did/e:unitdatestructured/e:daterange/e:fromdate", n).get("standarddate")
		== "1920"
	)
	assert root.find("e:control/e:maintenanceagency/e:agencyname", n).text == "Library <X>"
