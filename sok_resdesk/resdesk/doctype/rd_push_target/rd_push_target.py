import frappe
from frappe import _
from frappe.model.document import Document


class RDPushTarget(Document):
	def validate(self):
		if self.scope == "Collection" and not self.collection:
			frappe.throw(_("Choose the collection to send, or set Books to Send to Everything."))
		needed = {
			"Internet Archive": ("ia_access", _("IA access key")),
			"Koha": ("koha_url", _("Koha URL")),
			"Wikidata": ("wd_user", _("bot user name")),
			"Webhook": ("hook_url", _("webhook URL")),
		}.get(self.target_type)
		if self.enabled and needed and not self.get(needed[0]):
			frappe.throw(_("Fill in the {0} before enabling this target.").format(needed[1]))
		if self.target_type == "Wikidata" and not self.wd_api:
			self.wd_api = "https://www.wikidata.org/w/api.php"

	def on_trash(self):
		# the runs and "what was sent" records only mean something for this target
		frappe.db.delete("RD External Record", {"target": self.name})
		frappe.db.delete("RD Push Run", {"target": self.name})
		frappe.db.set_value("RD Push Target", self.name, "last_run", None, update_modified=False)
