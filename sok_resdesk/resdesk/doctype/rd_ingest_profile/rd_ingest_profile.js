// Copyright (c) 2026, Servants of Knowledge and contributors
// License: MIT. See LICENSE

frappe.ui.form.on("RD Ingest Profile", {
	refresh(frm) {
		frm.set_intro(
			__(
				"Choose books from archive.org (a collection, a search or a list of identifiers), from IA-style item folders on this computer, a NAS or a web server, or from a repository that offers OAI-PMH (DSpace, EPrints and most others). Use <b>Check Count</b> to see how many items match, then <b>Run Ingest</b>. Start with a small Maximum Items value for a test."
			),
			"blue"
		);
		if (frm.is_new()) return;

		frm.add_custom_button(__("Check Count"), () => {
			frappe.call({
				method: "sok_resdesk.ingest.count_profile",
				args: { profile: frm.doc.name },
				freeze: true,
				freeze_message: frm.doc.source === "Internet Archive" ? __("Asking the Internet Archive…") : __("Counting…"),
				callback: (r) => {
					frappe.msgprint({
						title: __("Matching items"),
						message:
							(r.message.count == null
								? __("The repository doesn't say how many records it has; a run lists them all.")
								: __("{0} items match this profile.", [(r.message.count || 0).toLocaleString()])) +
							(r.message.room != null && r.message.count > r.message.room
								? `<br><br><span class="text-warning">${__(
										"Room for about {0} more books under the book limit ({1}): books past it are skipped. See Settings → Machine Resources.",
										[r.message.room.toLocaleString(), (r.message.limit || 0).toLocaleString()]
								  )}</span>`
								: "") +
							`<br><br><code>${frappe.utils.escape_html(r.message.query)}</code>`,
						indicator: "blue",
					});
					frm.reload_doc();
				},
			});
		});

		if (frm.doc.source === "Repository (OAI-PMH)") {
			frm.add_custom_button(__("Check Repository"), () =>
				frappe.call({
					method: "sok_resdesk.repository.check",
					args: { profile: frm.doc.name },
					freeze: true,
					freeze_message: __("Asking the repository…"),
					callback: (r) => {
						const m = r.message, esc = frappe.utils.escape_html, s = m.sample;
						const sets = m.sets.slice(0, 50).map((x) => `<li><code>${esc(x.spec)}</code> ${esc(x.name)}</li>`).join("");
						frappe.msgprint({
							title: esc(m.repository.name || __("Repository")),
							indicator: "green",
							message:
								`<p>${__("It answers as an OAI-PMH repository.")}${m.repository.admin_email ? " " + __("Contact: {0}", [esc(m.repository.admin_email)]) : ""}</p>` +
								(s
									? `<p><b>${__("A record")}</b>: ${esc(s.title)}${s.creators.length ? " · " + esc(s.creators.join("; ")) : ""}${s.date ? " · " + esc(s.date) : ""}<br>` +
									  `${__("Catalogued as")} <code>${esc(s.item_id)}</code><br>` +
									  `${__("Web page")}: ${s.landing ? esc(s.landing) : __("none in the record")}<br>` +
									  `${__("PDF")}: ${s.pdf ? esc(s.pdf) : __("not in the record (looked for on the web page when Find Each Record's PDF is on)")}</p>`
									: `<p>${__("No records in this set.")}</p>`) +
								(m.sets.length ? `<p><b>${__("Sets")}</b> (${m.sets.length})</p><ul style="max-height:240px;overflow:auto">${sets}</ul>` : ""),
						});
					},
				})
			);
		}

		frm.add_custom_button(__("Run Ingest"), () => {
			const limit = frm.doc.max_items ? frm.doc.max_items : __("all");
			frappe.confirm(__("Start ingesting up to {0} items in the background?", [limit]), () => {
				frappe.call({
					method: "sok_resdesk.ingest.start_ingest",
					args: { profile: frm.doc.name },
					callback: (r) => {
						frappe.show_alert({ message: __("Ingest queued: {0}", [r.message]), indicator: "green" });
						frappe.set_route("Form", "RD Ingest Run", r.message);
					},
				});
			});
		}).addClass("btn-primary");

		if (frm.doc.visibility) {
			frm.add_custom_button(__("Apply Access to Its Books"), () =>
				frappe.confirm(
					__("Set every book ingested by this profile to “{0}”? Changes made by hand to those books are replaced.", [__(frm.doc.visibility)]),
					() =>
						frappe.call({
							method: "sok_resdesk.access.apply_profile",
							args: { profile: frm.doc.name },
							freeze: true,
							callback: (r) => frappe.show_alert({ message: r.message.message, indicator: "green" }),
						})
				)
			);
		}
		if (frm.doc.source === "Internet Archive" && frm.doc.keep_in_sync && frm.doc.synced_on) {
			frm.add_custom_button(__("Sync with archive.org"), () =>
				frappe.call({
					method: "sok_resdesk.ia_sync.sync_now",
					args: { profile: frm.doc.name },
					callback: (r) => {
						frappe.show_alert({ message: __("Bringing in what changed since {0}: {1}", [frappe.datetime.str_to_user(frm.doc.synced_on), r.message]), indicator: "green" });
						frappe.set_route("Form", "RD Ingest Run", r.message);
					},
				})
			);
		}
		if (frm.doc.portal_collection) {
			frm.add_custom_button(__("Portal Collection"), () => frappe.set_route("Form", "RD Collection", frm.doc.portal_collection));
		}
		frm.add_custom_button(__("Items from this Profile"), () =>
			frappe.set_route("List", "RD Item", { ingest_profile: frm.doc.name })
		);
		frm.add_custom_button(__("Run History"), () =>
			frappe.set_route("List", "RD Ingest Run", { profile: frm.doc.name })
		);
	},
});
