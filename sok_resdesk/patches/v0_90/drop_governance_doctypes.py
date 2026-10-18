import frappe

# The records-office doctypes moved to the sok_resdesk_governance app (0.90). A site that has that app
# keeps its tables; a site that does not (every site so far, none used them) loses the empty ones.
DOCTYPES = [
	"RD Audit Event",
	"RD Clearance",
	"RD Clearance Department",
	"RD Department",
	"RD Directory Account",
	"RD Disclosure Record",
	"RD Disclosure Redaction",
	"RD Disclosure Request",
	"RD Disposal",
	"RD Disposal Item",
	"RD File",
	"RD File Movement",
	"RD File Record",
	"RD Item Scope",
	"RD Legal Hold",
	"RD Legal Hold Item",
	"RD Retention Rule",
]


def execute():
	if "sok_resdesk_governance" in frappe.get_installed_apps():
		for name in DOCTYPES:  # the doctypes now belong to the new app's module
			if frappe.db.exists("DocType", name):
				frappe.db.set_value("DocType", name, "module", "ResDesk Governance", update_modified=False)
		return
	kept = []
	for name in DOCTYPES:
		if not frappe.db.exists("DocType", name):
			continue
		table = f"tab{name}"
		if frappe.db.table_exists(name) and frappe.db.sql(f"select 1 from `{table}` limit 1"):
			kept.append(name)
			continue
		try:
			frappe.delete_doc("DocType", name, force=True, ignore_missing=True)
		except Exception:
			frappe.log_error(f"Could not remove the unused doctype {name}")
	if kept:
		print("Governance records are held on this site: " + ", ".join(kept))
		print(
			"The rows are kept in the database. Install the governance app (RESDESK_EDITION=governance) to see them again."
		)
	frappe.db.commit()
