"""The test accounts: one for every kind of person the system knows (pure data)."""

import secrets
from dataclasses import dataclass

DOMAIN = "example.org"  # reserved for examples: mail to it goes nowhere
PREFIX = "rdtest."


@dataclass(frozen=True)
class Account:
	key: str
	roles: tuple[str, ...]
	desk: bool  # works in the Desk (a System User), not only on the portal
	enabled: bool
	kind: str  # what this account is for, in one line

	@property
	def email(self) -> str:
		return f"{PREFIX}{self.key}@{DOMAIN}"

	@property
	def name(self) -> str:
		return f"Test {self.key.replace('_', ' ').title()}"


ACCOUNTS = (
	Account("signed_in", (), False, True, "signed in, but not a member (sign-up open, no Reader role)"),
	Account("reader", ("ResDesk Reader",), False, True, "reader: finds and reads members-only books"),
	Account(
		"depositor",
		("ResDesk Reader", "ResDesk Depositor"),
		False,
		True,
		"deposits their own work for review",
	),
	Account(
		"proofreader",
		("ResDesk Reader", "ResDesk Proofreader"),
		False,
		True,
		"volunteer who corrects page text",
	),
	Account("cataloguer", ("ResDesk Cataloguer",), True, True, "edits catalogue records in the Desk"),
	Account("manager", ("ResDesk Manager",), True, True, "librarian: portal, ingests, people"),
	Account("super_admin", ("SOK Super Admin",), True, True, "manages the installation as a whole"),
	Account("system_manager", ("System Manager",), True, True, "Frappe's own top role"),
	Account("switched_off", ("ResDesk Reader",), False, False, "a reader whose account is switched off"),
)


def new_password() -> str:
	"""A password that passes any policy and is read out once, never kept in the code."""
	return secrets.token_urlsafe(12) + "-Aa9"
