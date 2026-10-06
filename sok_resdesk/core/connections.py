"""The Connections screen's catalogue: every way Research Desk talks to other systems, by kind.

Pure data (no Frappe): what each connection is for, who may use it, which feature it needs, and
where to open it. sok_resdesk/connections.py adds the live status (connected, switched off, how
many) and the viewer's own access. Kept here so a new integration is one entry, and unit-tested.
"""

from __future__ import annotations

from dataclasses import dataclass, field

MANAGERS = ("System Manager", "SOK Super Admin", "ResDesk Manager")
CATALOGUERS = (*MANAGERS, "ResDesk Cataloguer")
WORKERS = (*CATALOGUERS, "ResDesk Proofreader")
SENDERS = (*CATALOGUERS, "ResDesk Depositor")

ROUTE, URL = "route", "url"


@dataclass(frozen=True)
class Action:
	label: str
	kind: str  # route (a Desk route) or url
	target: tuple[str, ...] | str
	primary: bool = False


@dataclass(frozen=True)
class Card:
	key: str
	group: str
	title: str
	what: str
	who: str  # a sentence for people: who may use it
	roles: tuple[str, ...]  # the roles that may use its actions
	actions: tuple[Action, ...]
	feature: str = ""  # the feature (Settings → Features) it needs
	urls: tuple[tuple[str, str], ...] = ()  # (label, address on this library) others can use


@dataclass(frozen=True)
class Group:
	key: str
	title: str
	what: str
	icon: str
	cards: tuple[str, ...] = field(default=())


def _r(*parts: str) -> tuple[str, ...]:
	return tuple(parts)


GROUPS: tuple[Group, ...] = (
	Group("archive", "Internet Archive", "Bring books in from archive.org, give books to it", "archive"),
	Group(
		"wikimedia",
		"Wikimedia",
		"Wikidata, Wikisource and Wikimedia Commons, under each person's own account",
		"globe",
	),
	Group("library", "Library systems", "Koha and other catalogues the library already runs", "library"),
	Group(
		"repositories",
		"Repositories and deposit",
		"University repositories in, people's own work in",
		"inbox",
	),
	Group("ebooks", "E-books and offline", "Calibre, e-reader apps, Kiwix and the text to take away", "book"),
	Group(
		"standards",
		"Open standards for others to reach this library",
		"Addresses that harvesters, viewers and library tools use",
		"link",
	),
	Group(
		"data",
		"Import and export",
		"Spreadsheets, metadata files, exports and moving the library",
		"arrow-left-right",
	),
	Group("hooks", "Webhooks and your own tools", "Tell your own systems when something happens", "zap"),
)

CARDS: tuple[Card, ...] = (
	Card(
		"ia_bring",
		"archive",
		"Bring books in from archive.org",
		"Ingest a collection, a search or a list of identifiers; the portal keeps in step with archive.org for new, changed and removed books.",
		"Managers set it up; it runs by itself.",
		MANAGERS,
		(
			Action("Ingest profiles", ROUTE, _r("List", "RD Ingest Profile"), True),
			Action("Runs", ROUTE, _r("List", "RD Ingest Run")),
		),
	),
	Card(
		"ia_send",
		"archive",
		"Give a book to archive.org",
		"Upload a book's files to the Internet Archive under your own archive.org account. What is sent is always public.",
		"Library staff and depositors, each with their own archive.org account. Staff choose the collection.",
		SENDERS,
		(
			Action("Connect my archive.org account", ROUTE, _r("List", "RD Archive Account"), True),
			Action("Deposit page (for depositors)", URL, "/library/deposit"),
			Action("How it works", ROUTE, _r("resdesk-help", "archive-upload")),
		),
	),
	Card(
		"ia_metadata",
		"archive",
		"Keep archive.org's details in step",
		"Push corrected titles, authors and subjects to books that are already on archive.org (it never deletes a field there).",
		"Managers, with the keys of the archive.org account that owns the books.",
		MANAGERS,
		(
			Action("Push targets", ROUTE, _r("List", "RD Push Target"), True),
			Action("Push runs", ROUTE, _r("List", "RD Push Run")),
		),
		"sharing",
	),
	Card(
		"wm_account",
		"wikimedia",
		"My Wikimedia account",
		"Connect your own account once: what you give back to Wikidata, Wikisource and Commons is sent as you, so Wikimedia's histories credit you.",
		"Cataloguers, proofreaders and managers, each their own.",
		WORKERS,
		(
			Action("Connect my account", ROUTE, _r("List", "RD Wikimedia Account"), True),
			Action("How it works", ROUTE, _r("resdesk-help", "wikimedia")),
		),
	),
	Card(
		"wikidata",
		"wikimedia",
		"Wikidata and authority control",
		"Match authors to Wikidata people (with VIAF) and subjects to Library of Congress headings; give names and links back.",
		"Cataloguers and managers.",
		CATALOGUERS,
		(Action("Authorities", ROUTE, _r("resdesk-authorities"), True),),
		"authorities",
	),
	Card(
		"wikisource",
		"wikimedia",
		"Wikisource",
		"Bring scanned books transcribed on any language's Wikisource in as books, and send proofread, validated pages back after a diff review.",
		"Managers bring books in; proofreaders send pages back under their own account.",
		WORKERS,
		(Action("Ingest profiles (source: Wikisource)", ROUTE, _r("List", "RD Ingest Profile"), True),),
		"repositories",
	),
	Card(
		"commons",
		"wikimedia",
		"Wikimedia Commons",
		"Give a photograph to Commons: reviewed file name, description, licence and categories, under your own account.",
		"Cataloguers, proofreaders and managers, for photographs they may give.",
		WORKERS,
		(Action("Items (open a photograph → Actions)", ROUTE, _r("List", "RD Item")),),
		"photographs",
	),
	Card(
		"koha",
		"library",
		"Koha and other library systems",
		"Match the library's own catalogue (Koha, Evergreen, SOUL or any MARC file) to the books here, review unsure matches, send links back as 856 fields.",
		"Managers connect it; cataloguers review matches.",
		CATALOGUERS,
		(
			Action("Library systems", ROUTE, _r("List", "RD Library System"), True),
			Action("Matched records", ROUTE, _r("List", "RD Library Record")),
			Action("Push targets (Koha)", ROUTE, _r("List", "RD Push Target")),
		),
		"library_systems",
	),
	Card(
		"repo_in",
		"repositories",
		"Books from repositories",
		"Harvest DSpace, EPrints and any OAI-PMH repository, with each record's PDF text; only changes after the first run.",
		"Managers.",
		MANAGERS,
		(Action("Ingest profiles (source: Repository)", ROUTE, _r("List", "RD Ingest Profile"), True),),
		"repositories",
	),
	Card(
		"deposit",
		"repositories",
		"Deposit: people give their own work",
		"A depositor submits files with a licence and an optional embargo; a different staff member reviews and accepts, and it becomes a book.",
		"Depositors submit on the portal; cataloguers and managers review.",
		SENDERS,
		(
			Action("Deposits to review", ROUTE, _r("List", "RD Deposit"), True),
			Action("Deposit page", URL, "/library/deposit"),
		),
		"deposit",
	),
	Card(
		"doi",
		"repositories",
		"DOIs and ARKs",
		"Permanent identifiers for books and pages: ARKs (with a check character) and optional DataCite DOIs for chosen collections.",
		"Managers; the super admin holds the credentials.",
		MANAGERS,
		(Action("Settings → Identifiers", ROUTE, _r("Form", "RD Settings")),),
		"identifiers",
	),
	Card(
		"calibre",
		"ebooks",
		"Calibre",
		"Read a whole Calibre library in place (never written to), and export a small collection as a Calibre library to take away.",
		"Managers import; cataloguers export.",
		CATALOGUERS,
		(
			Action(
				"Ingest profiles (source: Folder or Server)", ROUTE, _r("List", "RD Ingest Profile"), True
			),
			Action("Exports", ROUTE, _r("List", "RD Export")),
		),
	),
	Card(
		"offline",
		"ebooks",
		"Offline copies and Kiwix",
		"A collection as web pages that open with no server and no internet, packaged for Kiwix as a ZIM file.",
		"Cataloguers and managers.",
		CATALOGUERS,
		(Action("Exports (Offline copy)", ROUTE, _r("List", "RD Export"), True),),
	),
	Card(
		"opds",
		"ebooks",
		"E-reader apps (OPDS)",
		"The library as a catalogue e-reader apps can browse and download from.",
		"Anyone with an e-reader app; readers see what their access allows.",
		(),
		(),
		"sharing",
		(("OPDS catalogue", "/opds"),),
	),
	Card(
		"oai",
		"standards",
		"OAI-PMH",
		"Harvesters (aggregators, union catalogues, Wikimedia tools) collect the library's records, in Dublin Core or MARC21.",
		"Public records only, as set in Settings → Sharing & Identifiers.",
		(),
		(Action("Settings → Sharing", ROUTE, _r("Form", "RD Settings")),),
		"sharing",
		(("OAI-PMH endpoint", "/api/method/sok_resdesk.oai.endpoint?verb=Identify"),),
	),
	Card(
		"sru",
		"standards",
		"SRU (for Z39.50 gateways)",
		"Older library systems search the catalogue by title, author, subject, identifier, date and language.",
		"Public records only.",
		(),
		(Action("How it works", ROUTE, _r("resdesk-help", "sru")),),
		"sharing",
		(("SRU explain record", "/sru"),),
	),
	Card(
		"iiif",
		"standards",
		"IIIF",
		"Every book is a IIIF manifest with an image service, so any IIIF viewer can open it.",
		"Public books only.",
		(),
		(),
		"sharing",
		(("A book's manifest", "/iiif/<book>/manifest"),),
	),
	Card(
		"counter",
		"standards",
		"COUNTER usage report",
		"A COUNTER Release 5 style Title Master Report for funders and consortia, from the portal's page views.",
		"Managers.",
		MANAGERS,
		(Action("How it works", ROUTE, _r("resdesk-help", "usage-reports")),),
		"statistics",
		(("Report (JSON)", "/api/method/sok_resdesk.counter.report"),),
	),
	Card(
		"imports",
		"data",
		"Spreadsheet and metadata-file imports",
		"Edit many books at once by spreadsheet (with a preview), or bring a whole catalogue in from a metadata file.",
		"Cataloguers and managers.",
		CATALOGUERS,
		(Action("Metadata imports", ROUTE, _r("List", "RD Metadata Import"), True),),
	),
	Card(
		"exports",
		"data",
		"Exports",
		"Spreadsheet, JSON, Dublin Core, MODS, MARCXML, JSON-LD, CSL-JSON, BibTeX, RIS, Internet Archive upload files, BagIt, Calibre and offline copies.",
		"Cataloguers and managers.",
		CATALOGUERS,
		(Action("Exports", ROUTE, _r("List", "RD Export"), True),),
	),
	Card(
		"moving",
		"data",
		"Moving or backing up the library",
		"One file moves a whole library to another server, or between Docker and a native install.",
		"The super admin, on the server.",
		("System Manager", "SOK Super Admin"),
		(Action("Server", ROUTE, _r("resdesk-server"), True),),
	),
	Card(
		"webhooks",
		"hooks",
		"Webhooks",
		"Tell your own systems, signed with a secret, when a book is added or changes.",
		"Managers.",
		MANAGERS,
		(Action("Push targets (Webhook)", ROUTE, _r("List", "RD Push Target"), True),),
		"sharing",
	),
)


def card(key: str) -> Card | None:
	return next((c for c in CARDS if c.key == key), None)


def group_of(card_key: str) -> str:
	c = card(card_key)
	return c.group if c else ""


def can_use(c: Card, roles: set[str]) -> bool:
	"""Whether someone with these roles may use a card's actions (a card with no roles is open to all)."""
	return not c.roles or bool(roles & set(c.roles))
