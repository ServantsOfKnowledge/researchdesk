from sok_resdesk import access
from sok_resdesk.catalogue import settings
from sok_resdesk.portal import collection_cards

no_cache = 1


def get_context(context):
	access.require_login_for_portal()
	s = settings()
	context.no_cache = 1
	context.full_width = 1
	context.show_sidebar = 0
	context.portal_title = s.portal_title or "SoK Research Desk"
	context.title = f"Collections · {context.portal_title}"
	# sub-collections are listed on the page of the collection they belong to
	context.collections = [c for c in collection_cards() if not c.part_of]
	context.metatags = {"title": context.title, "description": s.portal_tagline or ""}
	return context
