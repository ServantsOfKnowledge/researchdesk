# Usage reports in COUNTER form

Funders and consortia ask libraries to report use in the COUNTER format. Research Desk produces
the **Title Master Report (TR)** in the COUNTER Release 5 form, as JSON or as a table for a
spreadsheet, from the portal's own page-view log.

**What it reports.** For each book, by month:

* `Total_Item_Investigations`: every view of the book's page
* `Unique_Item_Investigations`: the first view of that book by a visitor in a day

**What it does not report.** *Requests* (a file opened or downloaded) are not recorded, so the
report carries COUNTER's exception 3040 (partial data) that says so; the two *investigation*
counts are what is honest to give. COUNTER's own robot and double-click filtering is not applied
beyond what Frappe's page-view log does. The report is COUNTER **style**, not an audited,
COUNTER-compliant platform report: say so when you send it.

## Getting it

Settings → Usage Statistics must be on **Built-in** (that is what records the views). Managers
then ask for the report:

    /api/method/sok_resdesk.counter.report?report_id=TR&begin_date=2026-01&end_date=2026-06&format=tsv

| Parameter | What it does |
|---|---|
| `report_id` | `TR` (the only report offered; `/api/method/sok_resdesk.counter.reports` lists it) |
| `begin_date`, `end_date` | `YYYY-MM` or `YYYY-MM-DD`; default the last twelve full months |
| `format` | `json` (default) or `tsv` (the table, to download) |

It needs a manager's login (or API key), and only books that were viewed in the period appear.
Items that are not public are marked `Controlled`, the rest `OA_Gold`.
