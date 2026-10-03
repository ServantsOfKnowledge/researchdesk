import frappe

from sok_resdesk.catalogue import settings

no_cache = 1


def get_context(context):
	"""The library's ground truth: proofread pages with their images, free to download, once the
	library has chosen a licence for them (groundtruth.py)."""
	from sok_resdesk.core import groundtruth as core
	from sok_resdesk.groundtruth import chosen_licence, public_sets

	s = settings()
	context.update({"no_cache": 1, "full_width": 1, "show_sidebar": 0})
	context.portal_title = s.portal_title or "SOK Research Desk"
	context.title = frappe._("OCR ground truth") + f" · {context.portal_title}"
	context.metatags = {
		"title": context.title,
		"description": frappe._(
			"Proofread page images with their corrected text, for training and testing OCR."
		),
	}
	context.sets = public_sets()
	context.licence = core.licence(chosen_licence())
	context.attribution = s.get("ground_truth_attribution") or ""
	return context
