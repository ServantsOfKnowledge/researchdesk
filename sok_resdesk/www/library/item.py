import json

import frappe
from frappe.utils import cint

from sok_resdesk.catalogue import base_url, get_record, settings
from sok_resdesk.core import citations

no_cache = 1


def get_context(context):
	item_id = frappe.form_dict.get("item_id")
	record = get_record(item_id) if item_id else None
	if not record:
		raise frappe.PageDoesNotExistError

	root = base_url()
	s = settings()
	context.no_cache = 1
	context.full_width = 1
	context.show_sidebar = 0
	context.portal_title = s.portal_title or "SoK Research Desk"
	context.item = record
	context.title = citations.display_title(record)
	context.start_leaf = cint(frappe.form_dict.get("page"))
	context.q = frappe.form_dict.get("q") or ""
	context.portal_url = f"{root}/library/item/{item_id}"
	context.formats = [(k, v[0]) for k, v in citations.FORMATS.items()]
	context.cites = {k: citations.render(record, k, root) for k in citations.FORMATS}
	context.highwire = citations.highwire_tags(record, root)
	context.json_ld = json.dumps(citations.json_ld(record, root), ensure_ascii=False)
	context.coins = citations.coins(record, root)
	context.metatags = {
		"title": context.title,
		"description": (record.get("description") or "")[:300],
		"image": record.get("thumbnail_url"),
	}
	return context
