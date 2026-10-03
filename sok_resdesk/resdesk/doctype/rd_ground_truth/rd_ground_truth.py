# Copyright (c) 2026, Servants of Knowledge and contributors
# License: MIT. See LICENSE

from frappe.model.document import Document


class RDGroundTruth(Document):
	def validate(self):
		from sok_resdesk.groundtruth import check_set

		check_set(self)

	def on_trash(self):
		from sok_resdesk.groundtruth import remove_file

		remove_file(self)
