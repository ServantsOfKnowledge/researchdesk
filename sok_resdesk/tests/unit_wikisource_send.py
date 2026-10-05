"""0.50: pages sent back to Wikisource: splitting a page, never losing markup, the diff."""

from sok_resdesk.core import wikisource as ws
from sok_resdesk.tests.wikisource_fixtures import PAGE_PROOFREAD, PAGE_RAW, PAGE_VALIDATED


def test_a_page_splits_into_kept_parts_and_its_body():
	head, body, foot = ws.split_page(PAGE_VALIDATED)
	assert 'level="4"' in head and head.endswith("</noinclude>")
	assert body.startswith("{{larger|") and foot.startswith("<noinclude>")
	head, body, foot = ws.split_page(PAGE_RAW)
	assert (body, foot) == ("ocr text not checked", "")


def test_a_page_without_a_quality_tag_is_not_edited():
	assert ws.split_page("plain text only") is None
	assert ws.split_page("<noinclude>{{header}}</noinclude>text") is None


def test_building_sets_level_and_person_and_keeps_the_rest():
	head, body, foot = ws.split_page(PAGE_PROOFREAD)
	built = ws.build_page(head, "ಹೊಸ ಪಠ್ಯ\n", foot, 4, "Someone")
	assert built.startswith(
		'<noinclude><pagequality level="4" user="Someone" /></noinclude>ಹೊಸ ಪಠ್ಯ<noinclude>'
	)
	parsed = ws.parse_page(built)
	assert (parsed["quality"], parsed["user"], parsed["text"]) == (4, "Someone", "ಹೊಸ ಪಠ್ಯ")


def test_only_pages_plain_text_cannot_hurt_are_rewritten():
	assert ws.markup_safe("just words\nand more words")
	for body in ("{{larger|big}} word", "a [[link|label]]", "''italic''", "note<ref>x</ref>"):
		assert not ws.markup_safe(body)


def test_same_text_ignores_line_ends_and_blank_runs():
	assert ws.same_text("a  \nb\n\n\n\nc\n", "a\nb\n\nc")
	assert not ws.same_text("a b", "a c")


def test_the_diff_shows_what_changes():
	d = ws.diff_lines("one\ntwo\nthree", "one\n2\nthree")
	assert "-two" in d and "+2" in d
	assert ws.diff_lines("same", "same") == []


def test_revisions_reads_existing_pages_only():
	class Api:
		def get(self, **kw):
			return {
				"query": {
					"pages": [
						{
							"title": "Page:A.pdf/1",
							"revisions": [
								{"revid": 5, "timestamp": "t", "slots": {"main": {"content": "x"}}}
							],
						},
						{"title": "Page:A.pdf/2", "missing": True},
					]
				}
			}

	assert ws.revisions(Api(), ["Page:A.pdf/1", "Page:A.pdf/2"]) == {
		"Page:A.pdf/1": {"revid": 5, "timestamp": "t", "content": "x"}
	}
