"""The documentation in docs/*.md, shown inside the app as help pages. Pure Python.

The same Markdown files are read on GitHub and in the app, so there is one place to update.
This module knows which files are help pages, for whom, and how to turn their links and
images into in-app addresses. The doc checks in tests/test_docs.py use it too.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

REPO_URL = "https://github.com/ServantsOfKnowledge/researchdesk"
# screenshots live in the app's public folder so the web server can serve them;
# the docs reference them relatively so they also show on GitHub
IMAGE_DIR = "sok_resdesk/public/images/guide"
IMAGE_URL = "/assets/sok_resdesk/images/guide"


@dataclass(frozen=True)
class Page:
	slug: str
	file: str
	title: str
	audience: str  # "reader": portal and Desk; "staff": Desk only
	group: str


PAGES = [
	Page("reader-guide", "reader-guide.md", "Using the library", "reader", "For readers"),
	Page("searching", "searching.md", "Searching", "reader", "For readers"),
	Page("citations", "citations.md", "Citations & reading lists", "reader", "For readers"),
	Page("accessibility", "accessibility.md", "Accessibility", "reader", "For readers"),
	Page("staff-guide", "staff-guide.md", "Staff guide: a tour of the Desk", "staff", "For library staff"),
	Page("ingesting", "ingesting.md", "Choosing & ingesting books", "staff", "For library staff"),
	Page(
		"local-folders",
		"local-folders.md",
		"Books from your own folders or servers",
		"staff",
		"For library staff",
	),
	Page(
		"photographs",
		"photographs.md",
		"Photographs",
		"staff",
		"For library staff",
	),
	Page(
		"audio-video",
		"audio-video.md",
		"Audio and video",
		"staff",
		"For library staff",
	),
	Page(
		"manuscripts",
		"manuscripts.md",
		"Manuscripts and palm leaves",
		"staff",
		"For library staff",
	),
	Page(
		"deposit",
		"deposit.md",
		"Repository deposit",
		"staff",
		"For library staff",
	),
	Page(
		"calibre",
		"calibre.md",
		"Books from a Calibre library",
		"staff",
		"For library staff",
	),
	Page(
		"repositories",
		"repositories.md",
		"Books from repositories (DSpace, EPrints, OAI-PMH)",
		"staff",
		"For library staff",
	),
	Page(
		"wikisource",
		"wikisource.md",
		"Books from Wikisource",
		"staff",
		"For library staff",
	),
	Page(
		"wikimedia",
		"wikimedia.md",
		"Giving back to Wikimedia with your own account",
		"staff",
		"For library staff",
	),
	Page(
		"collections-and-metadata",
		"collections-and-metadata.md",
		"Collections, metadata & pushing",
		"staff",
		"For library staff",
	),
	Page("access", "access.md", "Who can see what", "staff", "For library staff"),
	Page(
		"preservation",
		"preservation.md",
		"Permanent links, preservation & OCR quality",
		"staff",
		"For library staff",
	),
	Page("koha", "koha.md", "Koha & interoperability", "staff", "For library staff"),
	Page("iiif", "iiif.md", "IIIF: books in any viewer", "staff", "For library staff"),
	Page(
		"getting-started", "getting-started.md", "Getting started (installing)", "staff", "For administrators"
	),
	Page("installation", "installation.md", "Installation", "staff", "For administrators"),
	Page("server", "server.md", "Server: updates, health & backups", "staff", "For administrators"),
	Page("operations", "operations.md", "Operations", "staff", "For administrators"),
	Page("moving", "moving.md", "Moving to another server", "staff", "For administrators"),
	Page("scaling", "scaling.md", "Scaling to 50,000 books", "staff", "For administrators"),
	Page("api", "api.md", "HTTP API", "staff", "Technical"),
	Page("architecture", "architecture.md", "Architecture", "staff", "Technical"),
	Page("development", "development.md", "Development", "staff", "Technical"),
	Page("roadmap", "roadmap.md", "Roadmap", "staff", "Technical"),
]
BY_SLUG = {p.slug: p for p in PAGES}
BY_FILE = {p.file: p for p in PAGES}

_FENCE = re.compile(r"^\s*(```|~~~)")
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_LINK = re.compile(r"(!?)\[((?:[^\[\]]|\[[^\]]*\])*)\]\(([^)\s]+)(\s+\"[^\"]*\")?\)")


def github_slug(text: str) -> str:
	"""The anchor GitHub gives a heading: lower case, punctuation dropped, spaces to hyphens."""
	text = (
		re.sub(r"`|\*\*|__|\*|_(?=\W)|\[([^\]]*)\]\([^)]*\)", lambda m: m.group(1) or "", text)
		.strip()
		.lower()
	)
	out = []
	for ch in text:
		cat = unicodedata.category(ch)
		if ch in " -":
			out.append("-" if ch == " " else ch)
		elif ch == "_" or cat[0] in "LNM":
			out.append(ch)
	return "".join(out)


def headings(md: str) -> list[tuple[int, str, str]]:
	"""(level, text, anchor) for every heading outside code blocks, anchors made unique the
	way GitHub does (-1, -2 … for repeats)."""
	seen: dict[str, int] = {}
	out = []
	fenced = False
	for line in md.splitlines():
		if _FENCE.match(line):
			fenced = not fenced
			continue
		if fenced:
			continue
		m = _HEADING.match(line)
		if not m:
			continue
		text = m.group(2)
		slug = github_slug(text)
		if slug in seen:
			seen[slug] += 1
			slug = f"{slug}-{seen[slug]}"
		else:
			seen[slug] = 0
		out.append((len(m.group(1)), text, slug))
	return out


def anchors(md: str) -> set[str]:
	return {h[2] for h in headings(md)}


def links(md: str) -> list[tuple[bool, str]]:
	"""(is_image, target) for every Markdown link outside code blocks."""
	out = []
	fenced = False
	for line in md.splitlines():
		if _FENCE.match(line):
			fenced = not fenced
			continue
		if fenced:
			continue
		for m in _LINK.finditer(re.sub(r"`[^`]*`", "", line)):
			out.append((m.group(1) == "!", m.group(3)))
	return out


def split_target(target: str) -> tuple[str, str]:
	path, _, anchor = target.partition("#")
	return path, anchor


def rewrite(md: str, page_url, image_url=lambda name: f"{IMAGE_URL}/{name}") -> str:
	"""Point links between docs at in-app help pages (page_url(page, anchor) -> url or None
	for "not shown here", which falls back to GitHub) and images at the served copies."""

	def sub(m):
		bang, text, target, title = m.group(1), m.group(2), m.group(3), m.group(4) or ""
		if re.match(r"^[a-z]+:|^/|^#", target):
			return m.group(0)
		path, anchor = split_target(target)
		name = path.rsplit("/", 1)[-1]
		if bang:
			if path.startswith("../" + IMAGE_DIR + "/"):
				return f"{bang}[{text}]({image_url(name)}{title})"
			return m.group(0)
		if path.endswith(".md") and "/" not in path.replace("./", ""):
			page = BY_FILE.get(name)
			url = page_url(page, anchor) if page else None
			if url:
				return f"[{text}]({url}{title})"
			return f"[{text}]({REPO_URL}/blob/main/docs/{name}{'#' + anchor if anchor else ''}{title})"
		# anything else in the repo (LICENSE, scripts/…) goes to GitHub
		clean = path[3:] if path.startswith("../") else f"docs/{path}"
		return f"[{text}]({REPO_URL}/blob/main/{clean}{'#' + anchor if anchor else ''}{title})"

	out, fenced = [], False
	for line in md.splitlines():
		if _FENCE.match(line):
			fenced = not fenced
		out.append(line if fenced else _LINK.sub(sub, line))
	return "\n".join(out)


def add_heading_ids(html: str, md: str) -> str:
	"""Give the rendered headings the same anchors GitHub uses, in document order."""
	slugs = iter(headings(md))

	def sub(m):
		h = next(slugs, None)
		attrs = re.sub(r'\s*id="[^"]*"', "", m.group(2))
		return f'<h{m.group(1)}{attrs} id="{h[2]}">' if h else m.group(0)

	return re.sub(r"<h([1-6])([^>]*)>", sub, html)


def docs_dir(start: Path) -> Path:
	"""The docs folder next to the app package (repository root / docs)."""
	return start.resolve().parent / "docs"
