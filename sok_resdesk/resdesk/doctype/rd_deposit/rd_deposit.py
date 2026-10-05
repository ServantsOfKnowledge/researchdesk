# Copyright (c) 2026, Servants of Knowledge and contributors
# License: MIT. See LICENSE

from frappe.model.document import Document


class RDDeposit(Document):
	"""One deposit: a person's own work, waiting for or past review (see sok_resdesk/deposit.py)."""

	def before_insert(self):
		from sok_resdesk import deposit

		deposit.before_insert(self)

	def validate(self):
		from sok_resdesk import deposit

		deposit.validate(self)
