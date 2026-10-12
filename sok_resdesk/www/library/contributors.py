from frappe import _

from sok_resdesk import access
from sok_resdesk.catalogue import settings
from sok_resdesk.profile import contributors

no_cache = 1


def get_context(context):
	"""People and organisations who chose to be named as contributors (About me → show me)."""
	access.require_login_for_portal()
	s = settings()
	from sok_resdesk.translations import tr

	context.update({"no_cache": 1, "full_width": 1, "show_sidebar": 0})
	context.portal_title = tr(s.portal_title) or "SOK Research Desk"
	context.title = f"{_('Contributors')} · {context.portal_title}"
	context.people = contributors()
	context.metatags = {"title": context.title}
	return context
