"""All collections on one page (core/collections.group_tree)."""

from sok_resdesk.core.collections import group_tree


def card(name, part_of=None):
	return {"name": name, "title": name.title(), "part_of": part_of}


def test_each_top_collection_lists_its_sub_collections():
	t = group_tree(
		[
			card("sok"),
			card("kannada", "sok"),
			card("poetry", "kannada"),
			card("tamil", "sok"),
			card("misc"),
			card("orphan", "unpublished"),
		]
	)
	assert [g["parent"]["name"] for g in t["groups"]] == ["sok"]
	kids = t["groups"][0]["children"]
	assert [(k["name"], k["depth"], k["trail"]) for k in kids] == [
		("kannada", 1, []),
		("poetry", 2, ["Kannada"]),
		("tamil", 1, []),
	]
	assert [c["name"] for c in t["single"]] == ["misc", "orphan"]  # a parent not on the portal: top level


def test_a_loop_shows_each_once():
	t = group_tree([card("a"), card("b", "a"), card("c", "b"), card("b2", "c")])
	assert [k["name"] for k in t["groups"][0]["children"]] == ["b", "c", "b2"]
	assert group_tree([]) == {"groups": [], "single": []}
