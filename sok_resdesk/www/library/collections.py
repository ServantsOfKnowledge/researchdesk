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
	from frappe import _

	from sok_resdesk.translations import tr

	context.portal_title = tr(s.portal_title) or "SOK Research Desk"
	context.title = f"{_('Collections')} · {context.portal_title}"
	# every collection on one page: each top-level collection with its sub-collections under it
	from sok_resdesk.core.collections import group_tree

	cards = collection_cards()
	tree = group_tree(cards)
	context.groups, context.single = tree["groups"], tree["single"]
	context.collections = cards
	context.metatags = {"title": context.title, "description": tr(s.portal_tagline)}
	return context
