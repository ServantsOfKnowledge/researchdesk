def execute():
	"""Lock an account for 5 minutes after 5 wrong passwords, and ask for strong passwords
	(from Frappe's looser defaults; a library that set its own keeps them)."""
	from sok_resdesk.security import harden_logins

	harden_logins()
