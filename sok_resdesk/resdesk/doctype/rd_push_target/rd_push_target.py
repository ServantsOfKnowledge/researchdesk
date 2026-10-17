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
			"Public mirror": ("mirror_url", _("mirror URL")),
		}.get(self.target_type)
		if self.enabled and needed and not self.get(needed[0]):
			frappe.throw(_("Fill in the {0} before enabling this target.").format(needed[1]))
		if self.target_type == "Public mirror" and self.mirror_url:
			url = self.mirror_url.strip().lower()
			if not url.startswith(("https://", "http://localhost", "http://127.0.0.1")):
				frappe.throw(
					_("The mirror must be reached over https:// (the token and the books travel there).")
				)
		if self.target_type == "Wikidata" and not self.wd_api:
			self.wd_api = "https://www.wikidata.org/w/api.php"

	def on_trash(self):
		if self.target_type == "Public mirror":
			# books sent here are taken off the mirror first; if it cannot be reached, the target stays
			from sok_resdesk import outbound

			try:
				outbound.withdraw_all(self.name)
			except Exception as e:
				frappe.throw(_("Could not take the books off the mirror first: {0}").format(str(e)[:200]))
		# the runs and "what was sent" records only mean something for this target
		frappe.db.delete("RD External Record", {"target": self.name})
		frappe.db.delete("RD Push Run", {"target": self.name})
		frappe.db.set_value("RD Push Target", self.name, "last_run", None, update_modified=False)
