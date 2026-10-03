"""The W3C Web Annotation Protocol (https://www.w3.org/TR/annotation-protocol/) for readers' notes.

Other annotation tools (Hypothesis-style clients, Mirador, research software) read and write a
book's notes as Web Annotations, with the same rules as the page reader:

* ``…/api/method/sok_resdesk.annotation_protocol.annotations/<book>/`` is the book's
  container (an LDP Basic Container and AnnotationCollection): GET lists the notes this visitor
  may see, in pages of 100 (``?page=0``, ``?iris=1`` for just their addresses); POST adds one.
* ``…/annotations/<book>/<note>`` is one note: GET, PUT (change its words, tags, link or
  Wikidata item; its place on the page stays), DELETE.

Reading needs nothing for public notes. Writing needs a reader's login: their session, or an API
key (``Authorization: token <key>:<secret>``). Notes written this way are private to their author
until the author shares them from the page reader. ETags and If-Match guard against overwriting
someone's change.
"""

from __future__ import annotations

import hashlib
import json

import frappe
from frappe.utils import cint
from werkzeug.wrappers import Response

from sok_resdesk import access
from sok_resdesk import annotations as notes
from sok_resdesk.core import annotations as core

ENDPOINT = "sok_resdesk.annotation_protocol.annotations"
PROFILE = 'application/ld+json; profile="http://www.w3.org/ns/anno.jsonld"'
PER_PAGE = 100
CONSTRAINED = '<http://www.w3.org/TR/annotation-protocol/>; rel="http://www.w3.org/ns/ldp#constrainedBy"'


def container_iri(item_id: str) -> str:
	from sok_resdesk.catalogue import base_url

	return f"{base_url()}/api/method/{ENDPOINT}/{item_id}/"


def annotation_iri(item_id: str, name: str) -> str:
	return f"{container_iri(item_id)}{name}"


def _respond(body, status: int = 200, headers: dict | None = None) -> Response:
	text = "" if body is None else json.dumps(body, ensure_ascii=False, indent=1, default=str)
	resp = Response(text, status=status, content_type=PROFILE if text else None)
	for k, v in (headers or {}).items():
		resp.headers[k] = v
	resp.headers["Access-Control-Allow-Origin"] = "*"
	resp.headers["Access-Control-Expose-Headers"] = "ETag, Link, Location, Allow, Accept-Post"
	resp.headers["Vary"] = "Accept, Prefer, Cookie, Authorization"
	return resp


def _problem(status: int, message: str) -> Response:
	return _respond({"error": message}, status)


def _etag(data) -> str:
	return '"' + hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()[:32] + '"'


def _path() -> list[str]:
	"""The book and note named after the endpoint in the request's path."""
	path = frappe.local.request.path
	tail = path.split(ENDPOINT, 1)[1] if ENDPOINT in path else ""
	return [p for p in tail.split("/") if p]


@frappe.whitelist(allow_guest=True, methods=["GET", "HEAD", "POST", "PUT", "DELETE", "OPTIONS"])
def annotations(**kwargs):
	"""The protocol's one entry point: the container (…/<book>/) or one annotation (…/<book>/<note>)."""
	parts = _path()
	method = frappe.local.request.method
	if not parts or len(parts) > 2:
		return _problem(404, "Name a book: …/annotations/<book>/ (and a note: …/<book>/<note>).")
	item_id = parts[0]
	try:
		book = notes._book(item_id)
	except frappe.DoesNotExistError:
		return _problem(404, "No such book.")
	if len(parts) == 1:
		if method in ("GET", "HEAD"):
			return _container_get(book)
		if method == "POST":
			return _create(book)
		if method == "OPTIONS":
			return _respond(None, 204, _container_headers(book))
		return _problem(405, "A container takes GET, HEAD, OPTIONS and POST.")
	name = parts[1]
	if method in ("GET", "HEAD"):
		return _annotation_get(book, name)
	if method == "PUT":
		return _update(book, name)
	if method == "DELETE":
		return _delete(book, name)
	if method == "OPTIONS":
		return _respond(None, 204, {"Allow": "GET, HEAD, OPTIONS, PUT, DELETE"})
	return _problem(405, "An annotation takes GET, HEAD, OPTIONS, PUT and DELETE.")


# -- reading -----------------------------------------------------------------------------------------


def _visible_rows(book, start: int = 0, limit: int = PER_PAGE, name: str | None = None):
	if not access.can_read(book.visibility):
		return [], 0
	cond, params = notes._visible_condition(frappe.session.user)
	where = f"a.item = %(item)s and {cond}" + (" and a.name = %(name)s" if name else "")
	params = {**params, "item": book.name, "name": name, "limit": limit, "start": start}
	total = frappe.db.sql(f"select count(*) from `tab{notes.DT}` a where {where}", params)[0][0]
	rows = frappe.db.sql(
		f"""select {", ".join("a." + f for f in notes.FIELDS)}, i.title as book_title, i.persistent_id
		from `tab{notes.DT}` a join `tabRD Item` i on i.name = a.item where {where}
		order by a.leaf, a.pos_start, a.creation limit %(limit)s offset %(start)s""",
		params,
		as_dict=True,
	)
	return rows, total


def _w3c_rows(rows) -> list[dict]:
	return [notes._w3c(n) for n in notes._with_citation(rows)]


def _container_headers(book) -> dict:
	allow = "GET, HEAD, OPTIONS" + (", POST" if notes._can_annotate(book) else "")
	return {
		"Link": f'<http://www.w3.org/ns/ldp#BasicContainer>; rel="type", {CONSTRAINED}',
		"Allow": allow,
		"Accept-Post": PROFILE,
	}


def _container_get(book) -> Response:
	args = frappe.local.request.args
	iris = cint(args.get("iris")) or "PreferContainedIRIs" in (frappe.get_request_header("Prefer") or "")
	container = container_iri(book.name)
	if "page" in args:
		page = max(0, cint(args.get("page")))
		rows, total = _visible_rows(book, page * PER_PAGE)
		body = core.collection_page(_w3c_rows(rows), container, page, total, PER_PAGE, embed=not iris)
		headers = {"Link": '<http://www.w3.org/ns/ldp#Resource>; rel="type"', "Allow": "GET, HEAD, OPTIONS"}
	else:
		_, total = _visible_rows(book, 0, 0)
		body = core.collection(container, f"Notes on {book.title}", total, PER_PAGE, embed=not iris)
		headers = _container_headers(book)
	headers["ETag"] = _etag(body)
	if frappe.get_request_header("If-None-Match") == headers["ETag"]:
		return _respond(None, 304, headers)
	return _respond(body, 200, headers)


def _one(book, name: str) -> dict | None:
	rows, _ = _visible_rows(book, 0, 1, name=name)
	return _w3c_rows(rows)[0] if rows else None


def _annotation_headers(book, anno: dict) -> dict:
	mine = frappe.db.get_value(notes.DT, anno["id"].rsplit("/", 1)[-1], "owner") == frappe.session.user
	allow = "GET, HEAD, OPTIONS" + (", PUT, DELETE" if mine or notes._is_manager() else "")
	return {"Link": '<http://www.w3.org/ns/ldp#Resource>; rel="type"', "Allow": allow, "ETag": _etag(anno)}


def _annotation_get(book, name: str) -> Response:
	anno = _one(book, name)
	if not anno:
		return _problem(404, "No such note, or it is not yours to see.")
	headers = _annotation_headers(book, anno)
	if frappe.get_request_header("If-None-Match") == headers["ETag"]:
		return _respond(None, 304, headers)
	return _respond(anno, 200, headers)


# -- writing -----------------------------------------------------------------------------------------


def _body() -> dict:
	try:
		return json.loads(frappe.local.request.get_data(as_text=True) or "{}")
	except ValueError as e:
		raise core.AnnotationError("The body is not JSON.") from e


def _target(book, note: dict) -> dict:
	"""Where on the page: a region, or start/end in the page text (found by the quote if needed)."""
	if note.get("region"):
		return {"region": note["region"].replace("xywh=percent:", "")}
	text = notes._page_text(book.name, note["leaf"]) or ""
	start, end = note.get("start"), note.get("end")
	if note.get("exact"):
		where = core.anchor(
			text, start, end, note["exact"], note.get("prefix") or "", note.get("suffix") or ""
		)
		if not where:
			raise core.AnnotationError("The quoted words are not in the page's text.")
		start, end = where
	if start is None or end is None or not (0 <= start < end <= len(text)):
		raise core.AnnotationError("The target's position is outside the page's text.")
	return {"start": start, "end": end}


def _need_login(book) -> Response | None:
	if frappe.session.user == "Guest":
		return _problem(401, "Log in, or send an API key (Authorization: token <key>:<secret>).")
	if not notes._can_annotate(book):
		return _problem(403, "You may not add notes to this book.")
	return None


def _create(book) -> Response:
	denied = _need_login(book)
	if denied:
		return denied
	try:
		note = core.from_w3c(_body())
		where = _target(book, note)
		saved = notes.add(
			item_id=book.name,
			leaf=note["leaf"],
			kind=note["kind"],
			body=note["body"],
			tags=note["tags"],
			link=note["link"],
			entity=note["entity"],
			visibility="Private",
			**where,
		)
	except core.AnnotationError as e:
		return _problem(400, str(e))
	except frappe.ValidationError as e:
		return _problem(400, frappe.utils.strip_html(str(e)))
	anno = _one(book, saved["name"])
	headers = _annotation_headers(book, anno)
	headers["Location"] = anno["id"]
	return _respond(anno, 201, headers)


def _guard(book, name: str) -> tuple[dict | None, Response | None]:
	denied = _need_login(book)
	if denied:
		return None, denied
	anno = _one(book, name)
	if not anno:
		return None, _problem(404, "No such note, or it is not yours to see.")
	owner = frappe.db.get_value(notes.DT, name, "owner")
	if owner != frappe.session.user and not notes._is_manager():
		return None, _problem(403, "Only its author can change this note.")
	match = frappe.get_request_header("If-Match")
	if match and match != "*" and match != _etag(anno):
		return None, _problem(412, "The note changed since you read it: GET it again.")
	return anno, None


def _update(book, name: str) -> Response:
	_, problem = _guard(book, name)
	if problem:
		return problem
	try:
		note = core.from_w3c(_body())
		notes.edit(
			name=name,
			kind=note["kind"],
			body=note["body"],
			tags=note["tags"],
			link=note["link"],
			entity=note["entity"],
		)
	except core.AnnotationError as e:
		return _problem(400, str(e))
	except frappe.ValidationError as e:
		return _problem(400, frappe.utils.strip_html(str(e)))
	anno = _one(book, name)
	return _respond(anno, 200, _annotation_headers(book, anno))


def _delete(book, name: str) -> Response:
	_, problem = _guard(book, name)
	if problem:
		return problem
	notes.remove(name=name)
	return _respond(None, 204)
