"""An offline copy of a collection: a plain folder of web pages that opens from a USB stick or a
phone with no server and no internet, and that Kiwix can package as a ZIM file.

The site has an index with search (a script reading one data file, so it works from ``file://``),
a page per book (details, cover, downloads) and, where the library holds the text, the book's
text page by page. Pure Python (no Frappe), so it is unit-tested directly.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import zipfile
from collections.abc import Iterator
from html import escape

MAX_TEXT_PER_BOOK = 400_000  # characters of a book's text kept in the search data
UNPACKED = {".pdf", ".epub", ".jpg", ".jpeg", ".png", ".mp3", ".mp4", ".zip", ".djvu"}

CSS = """body{font:16px/1.5 system-ui,sans-serif;margin:0 auto;max-width:56rem;padding:0 1rem;color:#1d1d1f}
a{color:#0b5394}h1{border-bottom:2px solid #8a1c1c;padding-bottom:.2em}
.book{display:flex;gap:1rem;margin:1rem 0;padding-bottom:1rem;border-bottom:1px solid #ddd}
.book img{width:80px;height:auto;align-self:flex-start}.meta{color:#555;font-size:.9em}
input[type=search]{width:100%;font-size:1.1em;padding:.5em;box-sizing:border-box}
pre.page{white-space:pre-wrap;font:inherit}.pg{color:#8a1c1c;font-weight:bold;margin-top:1.2em}
footer{color:#666;font-size:.85em;margin:2rem 0}"""

SEARCH_JS = """(function(){
var box=document.getElementById('q'),out=document.getElementById('results'),all=document.getElementById('all');
function norm(s){return (s||'').toLowerCase();}
function show(list){out.innerHTML='';list.slice(0,100).forEach(function(b){var d=document.createElement('div');
d.className='book';d.innerHTML=(b.c?'<img src="'+b.c+'" alt="">':'')+'<div><a href="'+b.u+'"><b></b></a><div class="meta"></div></div>';
d.querySelector('b').textContent=b.t;d.querySelector('.meta').textContent=[b.a,b.y].filter(Boolean).join(' · ');out.appendChild(d);});
if(!list.length)out.textContent='Nothing found.';}
box.addEventListener('input',function(){var q=norm(box.value).trim();
if(!q){out.innerHTML='';all.style.display='';return;}all.style.display='none';
var words=q.split(/\\s+/);show(SEARCH.filter(function(b){var h=norm(b.t+' '+b.a+' '+b.s+' '+b.x);
return words.every(function(w){return h.indexOf(w)>=0;});}));});})();"""


def slug(identifier: str) -> str:
	"""A file-name-safe form of an identifier, kept unique when characters had to change."""
	clean = re.sub(r"[^A-Za-z0-9._-]+", "_", identifier).strip("._") or "book"
	if clean != identifier:
		clean += "-" + hashlib.sha1(identifier.encode()).hexdigest()[:6]
	return clean[:100]


def _page(title: str, body: str, up: str = "") -> str:
	return (
		'<!DOCTYPE html>\n<html lang="en"><head><meta charset="utf-8">'
		'<meta name="viewport" content="width=device-width,initial-scale=1">'
		f'<title>{escape(title)}</title><link rel="stylesheet" href="{up}style.css"></head><body>'
		f"{body}</body></html>\n"
	)


def book_page(b: dict, s: str, text_pages: int) -> str:
	rows = []
	for label, value in (
		("Authors", ", ".join(b.get("authors") or [])),
		("Year", b.get("year") or ""),
		("Language", b.get("language") or ""),
		("Publisher", b.get("publisher") or ""),
		("Subjects", ", ".join(b.get("subjects") or [])),
	):
		if value:
			rows.append(f"<tr><th>{label}</th><td>{escape(str(value))}</td></tr>")
	body = [f'<p><a href="../index.html">← Index</a></p><h1>{escape(b["title"])}</h1>']
	if b.get("cover"):
		body.append(f'<p><img src="../covers/{s}.jpg" alt="" style="max-width:200px"></p>')
	body.append(f"<table>{''.join(rows)}</table>")
	if b.get("description"):
		body.append(f"<p>{escape(b['description'])}</p>")
	if text_pages:
		body.append(f'<p><a href="../text/{s}.html"><b>Read the text</b></a> ({text_pages} pages)</p>')
	for name, _path in b.get("files") or []:
		body.append(f'<p><a href="../files/{s}/{escape(name)}">Download {escape(name)}</a></p>')
	if b.get("link"):
		body.append(f'<p class="meta">Online: {escape(b["link"])}</p>')
	if not (b.get("files") or text_pages):
		body.append('<p class="meta">Only the details of this book are in this copy.</p>')
	return _page(b["title"], "".join(body), "../")


def text_page(b: dict, pages: list[dict], s: str) -> str:
	parts = [f'<p><a href="../books/{s}.html">← {escape(b["title"])}</a></p><h1>{escape(b["title"])}</h1>']
	for p in pages:
		label = p.get("label") or ""
		parts.append(
			f'<div class="pg">{escape(str(label))}</div><pre class="page">{escape(p.get("text") or "")}</pre>'
		)
	return _page(b["title"], "".join(parts), "../")


def index_page(books: list[dict], title: str, intro: str, stamp: str) -> str:
	listing = "".join(
		'<div class="book">'
		+ (f'<img src="covers/{b["slug"]}.jpg" alt="">' if b.get("cover") else "")
		+ f'<div><a href="books/{b["slug"]}.html"><b>{escape(b["title"])}</b></a>'
		f'<div class="meta">{escape(", ".join(b.get("authors") or []))}'
		f"{' · ' + escape(str(b['year'])) if b.get('year') else ''}</div></div></div>"
		for b in books
	)
	body = (
		f"<h1>{escape(title)}</h1><p>{escape(intro)}</p>"
		'<input type="search" id="q" placeholder="Search titles, authors, subjects and text" autocomplete="off">'
		f'<div id="results"></div><div id="all">{listing}</div>'
		f"<footer>{len(books)} books. Made {escape(stamp)} with SOK Research Desk.</footer>"
		'<script src="search-data.js"></script><script src="search.js"></script>'
	)
	return _page(title, body)


def search_data(books: list[dict], texts: dict[str, str]) -> str:
	rows = [
		{
			"t": b["title"],
			"a": ", ".join(b.get("authors") or []),
			"y": str(b.get("year") or ""),
			"s": ", ".join(b.get("subjects") or []),
			"x": texts.get(b["slug"], "")[:MAX_TEXT_PER_BOOK],
			"u": f"books/{b['slug']}.html",
			"c": f"covers/{b['slug']}.jpg" if b.get("cover") else "",
		}
		for b in books
	]
	return "var SEARCH=" + json.dumps(rows, ensure_ascii=False, separators=(",", ":")) + ";"


ZIM_NOTE = """Kiwix: to make a ZIM file of this folder (Kiwix apps open it offline):

    zimwriterfs --welcome=index.html --illustration=cover.png --language={lang} \\
      --title="{title}" --description="{title}" --creator="{creator}" --publisher="{creator}" \\
      --name=research-desk . ../{zim}

(zimwriterfs is part of zim-tools; on Debian/Ubuntu: apt install zim-tools.) Research Desk makes
the ZIM itself when zimwriterfs is installed on the server.
"""


def iter_site(
	books: list[dict], title: str, intro: str, stamp: str, creator: str = "Research Desk", lang: str = "eng"
) -> Iterator[tuple[str, bytes | str, bool]]:
	"""(path, content, is_file): content is bytes to write, or the path of a file to copy."""
	used: set[str] = set()
	for b in books:
		s = slug(b["item_id"])
		while s in used:
			s += "_"
		used.add(s)
		b["slug"] = s
	texts: dict[str, str] = {}
	yield "style.css", CSS.encode(), False
	yield "search.js", SEARCH_JS.encode(), False
	for b in books:
		s = b["slug"]
		pages = [p for p in (b.get("pages") or []) if (p.get("text") or "").strip()]
		if pages:
			texts[s] = " ".join(p["text"] for p in pages).lower()
			yield f"text/{s}.html", text_page(b, pages, s).encode(), False
		yield f"books/{s}.html", book_page(b, s, len(pages)).encode(), False
		for name, path in b.get("files") or []:
			yield f"files/{s}/{name}", path, True
		if b.get("cover"):
			yield f"covers/{s}.jpg", b["cover"], True
	yield "search-data.js", search_data(books, texts).encode("utf-8"), False
	yield "index.html", index_page(books, title, intro, stamp).encode(), False
	yield (
		"HOW-TO-MAKE-A-ZIM.txt",
		ZIM_NOTE.format(lang=lang, title=title, creator=creator, zim="library.zim").encode(),
		False,
	)


def write_zip(dest: str, books: list[dict], title: str, intro: str, stamp: str, **kw) -> int:
	count = 0
	with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as z:
		for path, content, is_file in iter_site(books, title, intro, stamp, **kw):
			if is_file:
				ext = os.path.splitext(path)[1].lower()
				z.write(content, path, zipfile.ZIP_STORED if ext in UNPACKED else zipfile.ZIP_DEFLATED)
			else:
				z.writestr(path, content)
			count += 1
	return count


def write_folder(root: str, books: list[dict], title: str, intro: str, stamp: str, **kw) -> int:
	import shutil

	count = 0
	for path, content, is_file in iter_site(books, title, intro, stamp, **kw):
		target = os.path.join(root, path)
		os.makedirs(os.path.dirname(target), exist_ok=True)
		if is_file:
			shutil.copyfile(content, target)
		else:
			with open(target, "wb") as f:
				f.write(content)
		count += 1
	return count
