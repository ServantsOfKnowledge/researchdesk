"""Wikisource as its API answers: an Index page, the Pages of its scan, and a category."""

INDEX = """{{:MediaWiki:Proofreadpage_index_template
|Type=book
|wikidata_item=
|Title=[[w:Kanakadasa|ಕನಕದಾಸ]] ಕೀರ್ತನೆಗಳು
|Language=kn
|Volume=
|Author=[[Author:Kanakadasa|Kanakadasa]]; [[Author:Other|Other Poet]]
|Translator=
|Editor=
|Publisher=Mysore Press
|Address=Mysore
|Year=1931
|Key=
|ISBN=
|OCLC=
|LCCN=
|BNF_ark=
|ARC=
|DNB=
|Source=pdf
|Image=1
|Progress=C
|Pages=<pagelist 1to3=roman />
|Volumes=
|Remarks=A small collection, typed in by volunteers.
|Width=
|Css=
|Header=
|Footer=
}}
"""

PAGE_VALIDATED = (
	'<noinclude><pagequality level="4" user="Volunteer" /><div class="pagetext">{{rh|1||ಕೀರ್ತನೆ}}\n\n</noinclude>'
	"{{larger|ಮೊದಲ ಪುಟ}}\n\n'''ಕನಕದಾಸ''' ಹೇಳಿದ [[ಹರಿ|ಹರಿಯ]] ಮಹಿಮೆ.<ref>note</ref>{{Footnote|skipped}}"
	"<noinclude>\n</div></noinclude>"
)
PAGE_PROOFREAD = (
	'<noinclude><pagequality level="3" user="Reader" /></noinclude>ಎರಡನೇ ಪುಟ<noinclude></noinclude>'
)
PAGE_RAW = '<noinclude><pagequality level="1" user="" /></noinclude>ocr text not checked'
PAGE_BLANK = '<noinclude><pagequality level="0" user="" /></noinclude>'


def api_pages(titles_text: dict[str, str]) -> dict:
	return {
		"batchcomplete": True,
		"query": {
			"pages": [
				{"pageid": i, "ns": 250, "title": t, "revisions": [{"slots": {"main": {"content": c}}}]}
				for i, (t, c) in enumerate(titles_text.items(), 1)
			]
		},
	}


PAGES = api_pages(
	{
		"Page:Kanaka.pdf/1": PAGE_VALIDATED,
		"Page:Kanaka.pdf/2": PAGE_PROOFREAD,
		"Page:Kanaka.pdf/3": PAGE_RAW,
		"Page:Kanaka.pdf/4": PAGE_BLANK,
		"Page:Kanaka.pdf/note": PAGE_RAW,
	}
)
INDEX_API = {
	"query": {
		"pages": [
			{"pageid": 9, "title": "Index:Kanaka.pdf", "revisions": [{"slots": {"main": {"content": INDEX}}}]}
		]
	}
}
CATEGORY = {
	"query": {
		"categorymembers": [
			{"pageid": 9, "ns": 252, "title": "Index:Kanaka.pdf"},
			{"pageid": 10, "ns": 252, "title": "Index:Other book.djvu"},
		]
	}
}
FILEINFO = {
	"query": {
		"pages": [{"title": "File:Kanaka.pdf", "imageinfo": [{"width": 600, "height": 900, "pagecount": 5}]}]
	}
}
SITEINFO = {
	"query": {
		"namespaces": {
			"250": {"id": 250, "canonical": "Page", "name": "ಪುಟ"},
			"252": {"id": 252, "canonical": "Index", "name": "ಸೂಚಿ"},
		}
	}
}


class Resp:
	def __init__(self, data, status=200):
		self._d, self.status_code = data, status

	def json(self):
		return self._d


class Session:
	"""Answers by the API parameters it is asked with."""

	def __init__(self, *answers):
		self.answers, self.headers, self.asked = list(answers), {}, []

	def get(self, url, params=None, timeout=None):
		self.asked.append(params)
		return Resp(self.answers.pop(0))
