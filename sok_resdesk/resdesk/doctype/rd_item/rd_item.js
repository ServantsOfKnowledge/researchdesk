// Copyright (c) 2026, Servants of Knowledge and contributors
// License: MIT. See LICENSE

frappe.ui.form.on("RD Item", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_web_link(`/library/item/${encodeURIComponent(frm.doc.item_id)}`, __("View on Portal"));
		if (frm.doc.source_url) {
			frm.add_custom_button(__("Open Source"), () => window.open(frm.doc.source_url), __("Links"));
		}
		frm.add_custom_button(
			__("Refresh from Source"),
			() =>
				frappe.call({
					method: "sok_resdesk.ingest.refresh_item",
					args: { item_id: frm.doc.item_id },
					freeze: true,
					freeze_message: __("Fetching from the Internet Archive…"),
					callback: () => frm.reload_doc(),
				}),
			__("Actions")
		);
		if (frm.doc.doi) {
			const test = frm.doc.doi_state === "Test";
			frm.add_custom_button(__("Open DOI"), () => window.open(`https://${test ? "handle.test.datacite.org" : "doi.org"}/${frm.doc.doi}`), __("Links"));
		}
		if (frappe.user.has_role(["System Manager", "ResDesk Manager"])) {
			frm.add_custom_button(
				__("Send to DataCite"),
				() =>
					frappe.call({
						method: "sok_resdesk.datacite.register_book",
						args: { name: frm.doc.name },
						freeze: true,
						callback: (r) => {
							frappe.show_alert({ message: __("DOI {0}: {1}", [r.message.doi, r.message.result]), indicator: "green" });
							frm.reload_doc();
						},
					}),
				__("Actions")
			);
		}
		if (frm.doc.source === "Wikisource" && frm.doc.wiki_index) {
			frm.add_custom_button(__("Send to Wikisource"), () => send_to_wikisource(frm), __("Actions"));
		}
		frm.add_custom_button(
			__("Re-index"),
			() =>
				frappe.call({
					method: "sok_resdesk.search.reindex_item",
					args: { item_id: frm.doc.item_id },
					freeze: true,
					callback: () => {
						frappe.show_alert({ message: __("Re-indexed"), indicator: "green" });
						frm.reload_doc();
					},
				}),
			__("Actions")
		);
		if (frm.doc.persistent_id) {
			frm.add_web_link(`/${frm.doc.persistent_id}`, __("Permanent Link (ARK)"));
		}
		// read the book's page images again with OCR, keeping only the pages that get better
		frm.add_custom_button(
			__("Re-OCR this book"),
			() =>
				Promise.all([
					frappe.call({ method: "sok_resdesk.reocr.engine_status" }),
					frappe.call({ method: "sok_resdesk.reocr.languages", args: { item_id: frm.doc.name } }),
				]).then(([r, l]) => {
					const st = r.message;
					if (!st.installed) return frappe.msgprint(__("The OCR engine (Tesseract) isn't installed on this server."));
					const book = (l.message && l.message.book) || [];
					frappe.prompt(
						[
							{
								fieldname: "preset",
								fieldtype: "Select",
								label: __("Layout of the pages"),
								options: st.presets,
								default: "Whole page",
								description: __("Columns are read one by one, so they don't mix. Pages people have proofread are left alone; a page keeps its new text only if it reads better. For pages with their own layout, draw zones in Page & text → Proofread."),
							},
							{
								fieldname: "languages",
								fieldtype: "MultiCheck",
								label: __("Read in"),
								columns: 3,
								options: Object.entries(st.names || {}).map(([m, n]) => ({ label: n, value: m, checked: book.includes(m) })),
								description: __("The book's languages are ticked (OCR Languages on the form, else its catalogue languages). Add any the pages also use, e.g. Sanskrit verses; English is always included."),
							},
						],
						(v) =>
							frappe.call({ method: "sok_resdesk.reocr.enqueue_book", args: { item_id: frm.doc.name, preset: v.preset, languages: JSON.stringify(v.languages || []) } }).then((x) => {
								frappe.show_alert({ message: x.message.message, indicator: "green" });
								frm.reload_doc();
							}),
						__("Re-OCR this book"),
						__("Start")
					);
				}),
			__("Actions")
		);
		// a scan whose PDF has no text: every page read with OCR (Settings → Read Scans with OCR)
		if (frm.doc.source !== "Internet Archive" && !frm.doc.on_archive_org && (frm.doc.local_pdf || frm.doc.remote_pdf)) {
			frm.add_custom_button(
				__("Read with OCR"),
				() =>
					frappe.confirm(
						__("Read every page of this book's PDF with OCR, in its languages? Its text becomes what this reading finds (pages people proofread keep their text). This takes a few seconds a page, in the background."),
						() =>
							frappe.call({
								method: "sok_resdesk.pdfs.ocr_now",
								args: { item_id: frm.doc.name },
								callback: () => frappe.show_alert({ message: __("Queued: the book's Re-OCR line shows how far it is"), indicator: "green" }),
							})
					),
				__("Actions")
			);
		}
		// the library's own copy (Settings → Preservation)
		frm.add_custom_button(
			__("Preserve Now"),
			() =>
				frappe.call({
					method: "sok_resdesk.preservation.preserve_now",
					args: { item: frm.doc.name },
					freeze: true,
					freeze_message: __("Copying the book's files and checking them…"),
					callback: (r) => {
						frappe.show_alert({
							message: r.message.changed ? __("Copied: version {0}", [r.message.version]) : __("The copy is up to date"),
							indicator: "green",
						});
						frm.reload_doc();
					},
				}),
			__("Preservation")
		);
		if (frm.doc.preserved_on) {
			frm.add_custom_button(
				__("Check Copy"),
				() =>
					frappe.call({
						method: "sok_resdesk.preservation.check_now",
						args: { item: frm.doc.name },
						freeze: true,
						callback: (r) => {
							const ok = r.message.ok;
							frappe.show_alert({
								message: ok ? __("All {0} files match their checksums", [r.message.checked]) : r.message.problems.slice(0, 3).join("; "),
								indicator: ok ? "green" : "red",
							});
							frm.reload_doc();
						},
					}),
				__("Preservation")
			);
			frm.add_custom_button(
				__("Make Second Copy"),
				() =>
					frappe.call({
						method: "sok_resdesk.preservation.second_copy_now",
						args: { item: frm.doc.name },
						freeze: true,
						freeze_message: __("Copying to the second place and checking it…"),
						callback: (r) => {
							frappe.show_alert({
								message: r.message.ok ? __("Second copy made: {0}", [r.message.where]) : __("The second copy failed its check"),
								indicator: r.message.ok ? "green" : "red",
							});
							frm.reload_doc();
						},
					}),
				__("Preservation")
			);
			frm.add_custom_button(
				__("Export BagIt"),
				() =>
					frappe.call({
						method: "sok_resdesk.preservation.export_book",
						args: { item: frm.doc.name },
						freeze: true,
						freeze_message: __("Making the bag…"),
						callback: (r) => {
							window.open(`/api/method/sok_resdesk.preservation.download_export?file=${encodeURIComponent(r.message.file)}`);
						},
					}),
				__("Preservation")
			);
			const serving = frm.doc.served_from_copy;
			frm.add_custom_button(
				serving ? __("Stop Serving From Our Copy") : __("Serve From Our Copy"),
				() =>
					frappe.confirm(
						serving
							? __("Stop serving this book's PDF from our copy? If archive.org doesn't have it either, it leaves the portal.")
							: __("Serve this book's PDF from our preservation copy, instead of archive.org's? Do this only when the library may share it: archive.org often darkens books for rights reasons."),
						() =>
							frappe
								.call({ method: "sok_resdesk.preservation.serve_from_copy", args: { item: frm.doc.name, on: serving ? 0 : 1 } })
								.then(() => frm.reload_doc())
					),
				__("Preservation")
			);
			frm.add_custom_button(
				__("History"),
				() => frappe.set_route("List", "RD Preservation Event", { item: frm.doc.name }),
				__("Preservation")
			);
		}
		if (frm.doc.thumbnail_url) {
			frm.set_intro(
				`<img src="${frm.doc.thumbnail_url}" style="max-height:120px;border-radius:4px;margin-right:12px;float:left">
				 <div>${frappe.utils.escape_html(frm.doc.creator_display || "")}<br>${frm.doc.year || ""} · ${
					frm.doc.language_label || ""
				} · ${frm.doc.page_count || "?"} ${__("pages")}</div><div style="clear:both"></div>`,
				"blue"
			);
		}
	},
});

// The person's own corrections, shown against the wiki's pages before anything is sent as them.
function send_to_wikisource(frm) {
	const esc = frappe.utils.escape_html;
	frappe.call({ method: "sok_resdesk.wikisource.send_plan", args: { item: frm.doc.name }, freeze: true, freeze_message: __("Reading the pages on Wikisource…") }).then((r) => {
		const plan = r.message;
		if (plan.problem) return frappe.msgprint({ title: __("Not yet"), message: esc(plan.problem) });
		const ready = plan.pages.filter((p) => p.kind);
		const left = plan.pages.filter((p) => !p.kind);
		if (!ready.length) {
			return frappe.msgprint({
				title: __("Nothing to send"),
				message:
					__("None of your corrections here can go to Wikisource as {0}.", [esc(plan.account)]) +
					(left.length ? "<ul>" + left.slice(0, 15).map((p) => `<li>${esc(p.page)}: ${esc(p.skip)}</li>`).join("") + "</ul>" : ""),
			});
		}
		const row = (p) =>
			`<div class="mb-3"><label><input type="checkbox" class="ws-send" data-leaf="${p.leaf}" data-rev="${p.revid}" checked> <b>${esc(p.page)}</b>
			 ${p.kind === "validated" ? __("validate (level 4)") : __("proofread (level 3)")}</label>` +
			(p.diff && p.diff.length ? `<pre style="max-height:12em;overflow:auto;font-size:12px">${p.diff.map(esc).join("\n")}</pre>` : "") +
			"</div>";
		const d = new frappe.ui.Dialog({
			title: __("Send to Wikisource as {0}", [plan.account]),
			size: "large",
			fields: [
				{
					fieldtype: "HTML",
					options:
						`<p class="text-muted">${__("Only pages you corrected or validated yourself. Each is an edit under your own Wikimedia account, and nothing changed on Wikisource since you looked is overwritten. At most {0} at a time.", [plan.max])}</p>` +
						ready.slice(0, plan.max).map(row).join("") +
						(left.length ? `<details><summary>${__("{0} pages left out", [left.length])}</summary><ul>${left.slice(0, 40).map((p) => `<li>${esc(p.page)}: ${esc(p.skip)}</li>`).join("")}</ul></details>` : ""),
				},
			],
			primary_action_label: __("Send"),
			primary_action() {
				const chosen = d.$wrapper.find(".ws-send:checked").map((_, el) => ({ leaf: +el.dataset.leaf, revid: +el.dataset.rev })).get();
				if (!chosen.length) return;
				frappe.call({ method: "sok_resdesk.wikisource.send_pages", args: { item: frm.doc.name, pages: chosen }, freeze: true, freeze_message: __("Sending, one page at a time…") }).then((res) => {
					d.hide();
					frappe.msgprint({ title: __("Sent"), message: "<ul>" + res.message.map((x) => `<li>${esc(x.page)}: ${esc(x.result)}</li>`).join("") + "</ul>" });
				});
			},
		});
		d.show();
	});
}
