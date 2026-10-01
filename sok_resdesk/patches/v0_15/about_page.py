import frappe


def execute():
	"""The About page (/about): starting content and its link in the portal's top bar."""
	frappe.reload_doc("resdesk", "doctype", "rd_about_item")
	frappe.reload_doc("resdesk", "doctype", "rd_about_page")
	from sok_resdesk.setup import set_up_about_page

	set_up_about_page()
