import frappe
from frappe.utils import cint

from sok_resdesk import access
from sok_resdesk.catalogue import settings

no_cache = 1


def get_context(context):
	"""Proofreading work list: pages readers reported OCR errors on, and the books whose text is
	worst, for the library's proofreaders."""
	from sok_resdesk import features
	from sok_resdesk.pagetext import HUMAN, can_proofread

	if not features.on("proofreading"):
		raise frappe.PageDoesNotExistError
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = access.login_url("/library/proofread")
		raise frappe.Redirect
	s = settings()
	context.update(
		{
			"no_cache": 1,
			"full_width": 1,
			"show_sidebar": 0,
			"portal_title": s.portal_title or "SOK Research Desk",
		}
	)
	context.title = frappe._("Proofreading") + f" · {context.portal_title}"
	context.metatags = {"title": context.title, "robots": "noindex"}
	context.allowed = can_proofread()
	if not context.allowed:
		return context
	language = frappe.form_dict.get("language") or ""
	lang_cond = "and i.language_label = %(language)s" if language else ""
	params = {"language": language, "human": HUMAN, "me": frappe.session.user}
	# OCR errors readers reported that no one has corrected since
	context.reports = frappe.db.sql(
		f"""select a.item, a.leaf, a.page_label, a.exact, a.body, a.creation, i.title
		from `tabRD Annotation` a join `tabRD Item` i on i.name = a.item
		where a.kind = 'OCR error' and i.published = 1 {lang_cond}
		and not exists (select 1 from `tabRD Page Text` t where t.item = a.item and t.leaf = a.leaf
			and t.is_current = 1 and t.status in %(human)s and t.creation > a.creation)
		order by a.creation limit 100""",
		params,
		as_dict=True,
	)
	# the books with the worst text first
	context.worst = frappe.db.sql(
		f"""select i.name, i.title, i.language_label, i.ocr_quality, i.ocr_low_pages, i.pages_proofread, i.page_count
		from `tabRD Item` i where i.published = 1 and i.has_page_text = 1 and i.ocr_quality > 0 {lang_cond}
		order by i.ocr_quality asc limit 50""",
		params,
		as_dict=True,
	)
	# manuscripts and palm-leaf bundles, with the fewest leaves transcribed first
	context.manuscripts = frappe.db.sql(
		f"""select i.name, i.title, i.language_label, i.ms_script, i.ms_material, i.pages_proofread, i.page_count
		from `tabRD Item` i where i.published = 1 and i.item_type = 'Manuscript' {lang_cond}
		order by i.pages_proofread / greatest(i.page_count, 1) asc, i.title limit 50""",
		params,
		as_dict=True,
	)
	for row in context.manuscripts:
		row.percent_done = (
			round(100 * cint(row.pages_proofread) / cint(row.page_count)) if cint(row.page_count) else 0
		)
	context.languages = frappe.db.sql_list(
		"""select distinct language_label from `tabRD Item` where published = 1 and has_page_text = 1
		and ifnull(language_label, '') != '' order by language_label"""
	)
	context.language = language
	context.mine = frappe.db.sql(
		"""select count(*) from `tabRD Page Text` where proofread_by = %(me)s and status in %(human)s""",
		params,
	)[0][0]
	context.validated = frappe.db.count("RD Page Text", {"validated_by": frappe.session.user})
	context.waiting_validation = frappe.db.sql(
		"""select t.item, t.leaf, t.page_label, i.title from `tabRD Page Text` t join `tabRD Item` i on i.name = t.item
		where t.is_current = 1 and t.status = 'Proofread' and t.proofread_by != %(me)s order by t.creation limit 50""",
		params,
		as_dict=True,
	)
	for row in context.worst:
		row.percent_done = (
			round(100 * cint(row.pages_proofread) / cint(row.page_count)) if cint(row.page_count) else 0
		)
	return context
