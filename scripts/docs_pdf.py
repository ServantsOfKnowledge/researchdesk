#!/usr/bin/env python3
"""Make a PDF of documentation pages, for reading offline or sending to partners.

    python3 scripts/docs_pdf.py                       # docs/architecture.md (+ scaling) → dist/
    python3 scripts/docs_pdf.py docs/api.md -o api.pdf --title "API"

Needs the `markdown` package (pip install markdown) and Chrome or Chromium (found on PATH, in
Playwright's folder, or named by CHROME=/path/to/chrome). Links between pages point to the
pages on GitHub, so they still work in the PDF. Releases carry the architecture PDF
(.github/workflows/release.yml).
"""

from __future__ import annotations

import argparse
import datetime as dt
import glob
import html
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = "https://github.com/ServantsOfKnowledge/researchdesk/blob/main"
DEFAULT = ["docs/architecture.md", "docs/scaling.md"]

CSS = """
@page { size: A4; margin: 18mm 16mm 20mm; }
body { font: 10.5pt/1.5 "Noto Sans", "DejaVu Sans", "Noto Sans Kannada", "Lohit Kannada", "Noto Sans Devanagari", "Lohit Devanagari", sans-serif;
  color: #1d1d1f; }
.cover { height: 240mm; display: flex; flex-direction: column; justify-content: center; page-break-after: always; }
.cover img { height: 22mm; width: auto; align-self: flex-start; margin-bottom: 14mm; }
.cover h1 { font-size: 30pt; margin: 0 0 4mm; border: 0; }
.cover .sub { font-size: 14pt; color: #444; margin: 0 0 14mm; }
.cover .meta { font-size: 10pt; color: #555; }
nav.toc { page-break-after: always; }
nav.toc h2 { border: 0; }
nav.toc ol { padding-left: 5mm; }
nav.toc li { margin: 1.2mm 0; }
nav.toc ul { list-style: none; padding-left: 6mm; columns: 2; font-size: 9.5pt; }
nav.toc a { color: inherit; text-decoration: none; }
section.page { page-break-before: always; }
h1 { font-size: 20pt; border-bottom: 2px solid #8a1c1c; padding-bottom: 2mm; }
h2 { font-size: 14pt; color: #8a1c1c; margin-top: 8mm; break-after: avoid; }
h3 { font-size: 11.5pt; break-after: avoid; }
a { color: #0b5394; }
code { font: 9pt "DejaVu Sans Mono", monospace; background: #f3f3f3; padding: 0 1px; }
pre { background: #f6f6f6; border: 1px solid #ddd; padding: 3mm; overflow: hidden; break-inside: avoid;
  font-size: 7.4pt; line-height: 1.25; white-space: pre; }
pre code { background: none; font-size: inherit; padding: 0; }
table { border-collapse: collapse; width: 100%; margin: 3mm 0; font-size: 8.6pt; }
th, td { border: 1px solid #ccc; padding: 1.4mm 2mm; vertical-align: top; text-align: left; }
th { background: #f0eceb; }
tr { break-inside: avoid; }
img { max-width: 100%; }
"""


def chrome() -> str:
	for path in [
		os.environ.get("CHROME"),
		*(shutil.which(n) for n in ("google-chrome", "chromium", "chromium-browser", "chrome")),
		*sorted(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"), reverse=True),
		"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
	]:
		if path and Path(path).exists():
			return path
	sys.exit("Chrome or Chromium not found: set CHROME=/path/to/chrome")


def version() -> str:
	text = (ROOT / "sok_resdesk/__init__.py").read_text()
	return re.search(r'__version__ = "([^"]+)"', text).group(1)


def page_html(path: Path, slug: str) -> tuple[str, str, list[tuple[str, str]]]:
	"""(title, html, [(section id, section title)]) of one Markdown page: links to other pages go
	to GitHub, images inline."""
	import markdown

	text = path.read_text(encoding="utf-8")
	title = re.search(r"^# (.+)$", text, re.M).group(1).strip()
	body = markdown.markdown(text, extensions=["tables", "fenced_code", "toc"])

	def link(m):
		href = m.group(1)
		if href.startswith(("http:", "https:", "mailto:", "#")):
			return m.group(0)
		target = (path.parent / href.split("#")[0]).resolve()
		anchor = "#" + href.split("#", 1)[1] if "#" in href else ""
		try:
			rel = target.relative_to(ROOT)
		except ValueError:
			return m.group(0)
		return f'href="{REPO}/{rel.as_posix()}{anchor}"'

	def image(m):
		target = (path.parent / m.group(1)).resolve()
		return f'src="{target.as_uri()}"' if target.exists() else m.group(0)

	body = re.sub(r'href="([^"]+)"', link, body)
	body = re.sub(r'src="([^":]+)"', image, body)
	body = re.sub(r'id="([^"]+)"', lambda m: f'id="{slug}-{m.group(1)}"', body)
	sections = [(i, re.sub(r"<[^>]+>", "", t)) for i, t in re.findall(r'<h2 id="([^"]+)">(.*?)</h2>', body)]
	return title, f'<section class="page" id="{slug}">{body}</section>', sections


def build(files: list[str], out: Path, title: str, subtitle: str) -> Path:
	pages = [page_html(ROOT / f, f"p{n}") for n, f in enumerate(files)]
	logo = ROOT / "sok_resdesk/public/images/sok-logo.png"
	toc = "".join(
		f'<li><a href="#p{n}"><b>{html.escape(t)}</b></a><ul>'
		+ "".join(f'<li><a href="#{i}">{t2}</a></li>' for i, t2 in secs)
		+ "</ul></li>"
		for n, (t, _h, secs) in enumerate(pages)
	)
	doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>{html.escape(title)}</title><style>{CSS}</style></head><body>
<div class="cover">
  {f'<img src="{logo.as_uri()}" alt="Servants of Knowledge">' if logo.exists() else ""}
  <h1>{html.escape(title)}</h1>
  <p class="sub">{html.escape(subtitle)}</p>
  <p class="meta">Version {version()} · {dt.date.today():%d %B %Y}<br>
  {REPO.rsplit("/blob", 1)[0]}</p>
</div>
<nav class="toc"><h2>Contents</h2><ol>{toc}</ol></nav>
{"".join(h for _t, h, _s in pages)}
</body></html>"""
	out.parent.mkdir(parents=True, exist_ok=True)
	with tempfile.TemporaryDirectory() as tmp:
		src = Path(tmp) / "doc.html"
		src.write_text(doc, encoding="utf-8")
		subprocess.run(
			[
				chrome(),
				"--headless",
				"--no-sandbox",
				"--disable-gpu",
				"--no-pdf-header-footer",
				"--allow-file-access-from-files",
				f"--print-to-pdf={out.resolve()}",
				src.as_uri(),
			],
			check=True,
			capture_output=True,
			timeout=180,
		)
	return out


def main() -> None:
	ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
	ap.add_argument("files", nargs="*", default=DEFAULT, help="Markdown pages, in order")
	ap.add_argument("-o", "--out", default=f"dist/research-desk-architecture-{version()}.pdf")
	ap.add_argument("--title", default="SOK Research Desk: Architecture")
	ap.add_argument(
		"--subtitle",
		default="How the open research portal and digital library is built, how it connects to "
		"the authorities and services libraries trust, and how it scales",
	)
	a = ap.parse_args()
	print(build(a.files, ROOT / a.out, a.title, a.subtitle))


if __name__ == "__main__":
	main()
