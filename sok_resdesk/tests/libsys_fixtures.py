"""A library system's catalogue, as Koha exports it (MARCXML) and as ISO 2709, for
unit_libsys.py and test_libsys.py (no pytest here: the Frappe test runner imports it too)."""

KOHA_XML = """<?xml version="1.0" encoding="UTF-8"?>
<collection xmlns="http://www.loc.gov/MARC21/slim">
<record>
  <leader>00000nam a22000007a 4500</leader>
  <controlfield tag="001">KUD-1931-77</controlfield>
  <controlfield tag="008">200101s1931    ii            000 0 kan d</controlfield>
  <datafield tag="100" ind1="1" ind2=" "><subfield code="a">Halakatti, P. G.</subfield><subfield code="6">880-01</subfield></datafield>
  <datafield tag="245" ind1="1" ind2="0"><subfield code="6">880-02</subfield><subfield code="a">Vachana sahitya /</subfield><subfield code="c">P. G. Halakatti.</subfield></datafield>
  <datafield tag="260" ind1=" " ind2=" "><subfield code="a">Dharwad :</subfield><subfield code="b">Karnatak Vidyavardhaka Sangha,</subfield><subfield code="c">1931.</subfield></datafield>
  <datafield tag="650" ind1=" " ind2="0"><subfield code="a">Vachanas.</subfield></datafield>
  <datafield tag="880" ind1="1" ind2="0"><subfield code="6">245-02</subfield><subfield code="a">ವಚನ ಸಾಹಿತ್ಯ /</subfield></datafield>
  <datafield tag="999" ind1=" " ind2=" "><subfield code="c">4512</subfield><subfield code="d">4512</subfield></datafield>
</record>
<record>
  <leader>00000nam a22000007a 4500</leader>
  <controlfield tag="001">KUD-2</controlfield>
  <datafield tag="020" ind1=" " ind2=" "><subfield code="a">978-81-7201-123-4 (pbk.)</subfield></datafield>
  <datafield tag="245" ind1="0" ind2="0"><subfield code="a">A thesis on Haridasa songs</subfield></datafield>
  <datafield tag="856" ind1="4" ind2="0"><subfield code="u">https://archive.org/details/rdtestlib-linked</subfield></datafield>
  <datafield tag="999" ind1=" " ind2=" "><subfield code="c">4513</subfield></datafield>
</record>
</collection>
"""


def iso2709(fields: list) -> bytes:
	"""One ISO 2709 record (UTF-8) from [(tag, value)] or [(tag, ind1, ind2, [(code, value)])]."""
	body, directory = b"", b""
	for f in fields:
		data = (
			f[1].encode()
			if len(f) == 2
			else (f[1] + f[2]).encode() + b"".join(b"\x1f" + c.encode() + v.encode() for c, v in f[3])
		)
		data += b"\x1e"
		directory += f"{f[0]}{len(data):04d}{len(body):05d}".encode()
		body += data
	base = 24 + len(directory) + 1
	total = base + len(body) + 1
	leader = f"{total:05d}nam a22{base:05d}7a 4500".encode()
	return leader + directory + b"\x1e" + body + b"\x1d"
