"""Recorded-style OAI-PMH answers and a small PDF maker, shared by unit_harvest.py and
test_repository.py (no pytest here: the Frappe test runner imports it too)."""

HEAD = '<?xml version="1.0"?><OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">'
DC = (
	'<oai_dc:dc xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/" '
	'xmlns:dc="http://purl.org/dc/elements/1.1/">{}</oai_dc:dc>'
)


def record(ident, dc="", deleted=False, stamp="2024-05-01"):
	status = ' status="deleted"' if deleted else ""
	meta = "" if deleted else f"<metadata>{DC.format(dc)}</metadata>"
	return (
		f"<record><header{status}><identifier>{ident}</identifier><datestamp>{stamp}</datestamp>"
		f"<setSpec>col_1</setSpec></header>{meta}</record>"
	)


PAGE1 = (
	HEAD
	+ "<ListRecords>"
	+ record(
		"oai:repo.example.org:123456789/42",
		"<dc:title>ಕನ್ನಡ ಸಾಹಿತ್ಯ ಚರಿತ್ರೆ</dc:title><dc:title>History of Kannada literature</dc:title>"
		"<dc:creator>Mugali, R. S.</dc:creator><dc:subject>Kannada literature</dc:subject>"
		"<dc:date>2012-03-01T10:00:00Z</dc:date><dc:date>1953</dc:date>"
		"<dc:language>kan</dc:language><dc:publisher>Kannada Sahitya Parishat</dc:publisher>"
		"<dc:identifier>http://hdl.handle.net/123456789/42</dc:identifier>"
		"<dc:identifier>https://repo.example.org/bitstream/123456789/42/1/book.pdf</dc:identifier>"
		"<dc:rights>http://creativecommons.org/licenses/by/4.0/</dc:rights>"
		"<dc:rights>Open access</dc:rights>",
	)
	+ '<resumptionToken completeListSize="3">tok1</resumptionToken></ListRecords></OAI-PMH>'
)
PAGE2 = (
	HEAD
	+ "<ListRecords>"
	+ record(
		"oai:repo.example.org:123456789/43",
		"<dc:title>Second</dc:title><dc:identifier>10.5555/xyz</dc:identifier>",
	)
	+ record("oai:repo.example.org:123456789/7", deleted=True)
	+ "<resumptionToken/></ListRecords></OAI-PMH>"
)


class Resp:
	def __init__(self, text, status=200, headers=None):
		self.content = text.encode()
		self.status_code = status
		self.headers = headers or {}


class Session:
	def __init__(self, answers):
		self.answers, self.asked, self.headers = list(answers), [], {}

	def get(self, url, params=None, timeout=None):
		self.asked.append(dict(params or {}))
		return self.answers.pop(0)


def make_pdf(pages: list[str]) -> bytes:
	"""A small PDF with one line of text per page (Helvetica)."""
	objs = ["<< /Type /Catalog /Pages 2 0 R >>", ""]
	kids = []
	for text in pages:
		stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
		objs.append(f"<< /Length {len(stream)} >>\nstream\n{stream.decode()}\nendstream")
		content = len(objs)
		objs.append(
			f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {content} 0 R "
			"/Resources << /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >> >>"
		)
		kids.append(f"{len(objs)} 0 R")
	objs[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>"
	out, offsets = b"%PDF-1.4\n", []
	for n, body in enumerate(objs, 1):
		offsets.append(len(out))
		out += f"{n} 0 obj\n{body}\nendobj\n".encode()
	xref = len(out)
	out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
	out += "".join(f"{o:010d} 00000 n \n" for o in offsets).encode()
	out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
	return out
