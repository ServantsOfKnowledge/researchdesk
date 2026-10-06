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
		if (frm.doc.item_type === "Photograph" && !frm.doc.commons_file && frappe.user.has_role(["System Manager", "ResDesk Manager", "ResDesk Cataloguer", "ResDesk Proofreader"])) {
			frm.add_custom_button(__("Send to Wikimedia Commons"), () => send_to_commons(frm), __("Actions"));
		}
		if (frm.doc.source === "Local" && !["Queued", "Uploading", "On archive.org"].includes(frm.doc.ia_sent_status) && frappe.user.has_role(["System Manager", "ResDesk Manager", "ResDesk Cataloguer"])) {
			frm.add_custom_button(__("Send to the Internet Archive"), () => send_to_archive(frm), __("Actions"));
		}
		if (frm.doc.ia_sent_status) {
			frm.dashboard.add_indicator(__("archive.org: {0}", [__(frm.doc.ia_sent_status)]), frm.doc.ia_sent_status === "Failed" ? "red" : frm.doc.ia_sent_status === "On archive.org" ? "green" : "orange");
		}
		if (frm.doc.media_files && frm.doc.source === "Local" && frappe.user.has_role(["System Manager", "ResDesk Manager", "ResDesk Cataloguer"])) {
			frm.add_custom_button(__("Draft the Transcript (Speech to Text)"), () =>
				frappe.call({ method: "sok_resdesk.drafts.draft_transcript", args: { item: frm.doc.name }, freeze: true }).then(() => frappe.msgprint(__("Drafting in the background. You get a notification when it is done; every draft is for a person to proofread.")))
			, __("Actions"));
		}
		if (frm.doc.item_type === "Manuscript" && frappe.user.has_role(["System Manager", "ResDesk Manager", "ResDesk Cataloguer"])) {
			frm.add_custom_button(__("Draft the Text of the Leaves"), () =>
				frappe.prompt(
					[{ fieldname: "leaves", fieldtype: "Data", label: __("Leaves (from 0, e.g. 0-9,14; empty for all)"), description: __("Leaves a person has worked on are left alone. The engine and model are in Settings → Machine Drafts.") }],
					(v) => frappe.call({ method: "sok_resdesk.drafts.draft_leaves", args: { item: frm.doc.name, leaves: v.leaves || "" }, freeze: true }).then(() => frappe.msgprint(__("Drafting in the background. You get a notification when it is done; every draft is for a person to proofread."))),
					__("Draft the Text of the Leaves"),
					__("Draft")
				)
			, __("Actions"));
		}
		if (frm.doc.item_type === "Manuscript") {
			frm.add_custom_button(__("Label the Leaves"), () => label_leaves(frm), __("Actions"));
		}
		if (frm.doc.media_files) {
			if (frm.doc.source === "Local") {
				frm.add_custom_button(__("Read the Length"), () => frappe.call({ method: "sok_resdesk.media.read_length", args: { item: frm.doc.name }, freeze: true }).then(() => frm.reload_doc()), __("Actions"));
			}
			if (!frm.doc.leaf_times && frm.doc.duration) {
				frm.add_custom_button(
					__("Lay out Transcript Segments"),
					() =>
						frappe.prompt(
							[{ fieldname: "seconds", fieldtype: "Int", label: __("Seconds in a segment"), default: 60, description: __("People transcribe one segment at a time: a minute is usual, 30 seconds for fast speech.") }],
							(v) => frappe.call({ method: "sok_resdesk.media.lay_out_segments", args: { item: frm.doc.name, seconds: v.seconds }, freeze: true }).then(() => frm.reload_doc()),
							__("Lay out Transcript Segments"),
							__("Lay out")
						),
					__("Actions")
				);
			}
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

// Give the photograph to Wikimedia Commons under my own account, after seeing exactly what goes.
function send_to_commons(frm) {
	const esc = frappe.utils.escape_html;
	const ask = (d) => ({ item: frm.doc.name, filename: d ? d.get_value("filename") : "", description: d ? d.get_value("description") : "", categories: d ? d.get_value("categories") : "" });
	const show = (d, p) => {
		const warn = [];
		if (p.problem) warn.push(p.problem);
		if (p.duplicate && p.duplicate.length) warn.push(__("Commons already has this file as {0}.", [p.duplicate.map(esc).join(", ")]));
		if (p.name_taken) warn.push(__("A file with this name already exists on Commons: choose another."));
		if (p.missing_categories && p.missing_categories.length) warn.push(__("These categories do not exist on Commons: {0}.", [p.missing_categories.map(esc).join(", ")]));
		d.get_field("review").$wrapper.html(
			(warn.length ? `<div class="alert alert-warning">${warn.map((w) => `<div>${w}</div>`).join("")}</div>` : "") +
				`<p class="text-muted">${__("Licence")}: <b>${esc(p.licence || "—")}</b> · ${__("Author")}: <b>${esc(p.author || "—")}</b> · ${__("Depicts")}: ${p.depicts.length ? p.depicts.map((x) => esc(x.qid + (x.label ? " " + x.label : ""))).join(", ") : "—"}</p>` +
				(p.wikitext ? `<details open><summary>${__("The description page, as Commons will get it")}</summary><pre style="max-height:16em;overflow:auto;font-size:12px">${esc(p.wikitext)}</pre></details>` : "")
		);
		d.plan = p;
		d.set_df_property("confirmed", "hidden", p.problem ? 1 : 0);
	};
	frappe.call({ method: "sok_resdesk.commons.plan", args: ask(null), freeze: true, freeze_message: __("Checking with Commons…") }).then((r) => {
		const p = r.message;
		const d = new frappe.ui.Dialog({
			title: __("Send to Wikimedia Commons as {0}", [p.account || __("…")]),
			size: "large",
			fields: [
				{ fieldname: "filename", fieldtype: "Data", label: __("File name on Commons"), default: p.filename, description: __("Describe what it shows; this is its permanent name.") },
				{ fieldname: "description", fieldtype: "Small Text", label: __("Description"), default: p.description },
				{ fieldname: "categories", fieldtype: "Small Text", label: __("Commons categories"), default: (p.categories || []).join("\n"), description: __("One per line; each must already exist on Commons.") },
				{ fieldtype: "Button", fieldname: "check", label: __("Check again"), click: () => frappe.call({ method: "sok_resdesk.commons.plan", args: ask(d), freeze: true }).then((x) => show(d, x.message)) },
				{ fieldname: "review", fieldtype: "HTML" },
				{ fieldname: "confirmed", fieldtype: "Check", label: __("This photograph is mine to give, or its owner agreed, under the licence above, and I accept it cannot be taken back.") },
			],
			primary_action_label: __("Send"),
			primary_action() {
				if (!d.get_value("confirmed")) return frappe.msgprint(__("Confirm that the photograph is yours to give first."));
				frappe.call({ method: "sok_resdesk.commons.send", args: { ...ask(d), confirmed: 1 }, freeze: true, freeze_message: __("Uploading…") }).then((res) => {
					d.hide();
					const x = res.message;
					frappe.msgprint({ title: __("Sent"), message: `<a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.file)}</a>` + (x.depicts && x.depicts !== "added" ? `<p>${esc(x.depicts)}</p>` : "") });
					frm.reload_doc();
				});
			},
		});
		show(d, p);
		d.show();
	});
}

// Give the book to the Internet Archive under my own (or a shared) account, after seeing what goes.
function send_to_archive(frm) {
	const esc = frappe.utils.escape_html;
	const ask = (d) => ({ item: frm.doc.name, identifier: d ? d.get_value("identifier") : "", collection: d ? d.get_value("collection") : "", account: d ? d.get_value("account") : "me" });
	const show = (d, p) => {
		const warn = [];
		if (p.problem) warn.push(esc(p.problem));
		if (p.name_taken) warn.push(__("archive.org already has an item with this identifier: choose another."));
		d.get_field("review").$wrapper.html(
			(warn.length ? `<div class="alert alert-warning">${warn.map((w) => `<div>${w}</div>`).join("")}</div>` : "") +
				`<p class="text-muted">${__("Public at")} <b>${esc(p.url)}</b> · ${__("Licence")}: <b>${esc(p.licence || "—")}</b></p>` +
				`<p class="text-muted">${p.files.map((f) => `${esc(f.name)} (${Math.round(f.size / 1048576 * 10) / 10} MB)`).join(" · ") || "—"}</p>`
		);
		d.set_df_property("confirmed", "hidden", p.problem || p.name_taken ? 1 : 0);
	};
	frappe.call({ method: "sok_resdesk.archive_upload.plan", args: ask(null), freeze: true, freeze_message: __("Checking with archive.org…") }).then((r) => {
		const p = r.message;
		const d = new frappe.ui.Dialog({
			title: __("Send to the Internet Archive"),
			size: "large",
			fields: [
				{ fieldname: "identifier", fieldtype: "Data", label: __("archive.org identifier"), default: p.identifier, description: __("Its permanent address on archive.org.") },
				{ fieldname: "collection", fieldtype: "Data", label: __("Collection"), default: p.collection, read_only: p.may_choose_collection ? 0 : 1, description: __("A collection your account may add to.") },
				{ fieldname: "account", fieldtype: "Select", label: __("Send under"), options: p.accounts.map((a) => ({ value: a.value, label: a.label })), default: p.account },
				{ fieldtype: "Button", fieldname: "check", label: __("Check again"), click: () => frappe.call({ method: "sok_resdesk.archive_upload.plan", args: ask(d), freeze: true }).then((x) => show(d, x.message)) },
				{ fieldname: "review", fieldtype: "HTML" },
				{ fieldname: "confirmed", fieldtype: "Check", label: __("This work is mine to give, or its owner agreed, and I accept that it will be public on archive.org.") },
			],
			primary_action_label: __("Send"),
			primary_action() {
				if (!d.get_value("confirmed")) return frappe.msgprint(__("Confirm that the work is yours to give first."));
				frappe.call({ method: "sok_resdesk.archive_upload.send", args: { ...ask(d), confirmed: 1 }, freeze: true }).then((res) => {
					d.hide();
					frappe.msgprint({ title: __("Queued"), message: __("The upload runs in the background; this book shows its state. It will appear at {0}.", [esc(res.message.url)]) });
					frm.reload_doc();
				});
			},
		});
		show(d, p);
		d.show();
	});
}

// Photographs are numbered 1, 2, 3…; leaves are cited 12a, 12b. Say where the leaves begin and how
// many sides each shows, and see the labels before they are saved.
function label_leaves(frm) {
	const args = (d) => ({ item: frm.doc.name, sides: d.get_value("sides"), start_image: d.get_value("start_image"), leaves: d.get_value("leaves"), start_folio: d.get_value("start_folio") });
	const show = (d) =>
		frappe.call({ method: "sok_resdesk.manuscripts.label_leaves", args: { ...args(d), preview: 1 } }).then((r) => {
			const rows = r.message.labels.map((x) => `${x.image} → <b>${frappe.utils.escape_html(x.label)}</b>`).join(" · ");
			d.get_field("preview").$wrapper.html(`<p class="text-muted">${__("{0} images", [r.message.images])}: ${rows} …</p>`);
		});
	const d = new frappe.ui.Dialog({
		title: __("Label the Leaves"),
		fields: [
			{ fieldname: "sides", fieldtype: "Select", label: __("Sides shown by each image sequence"), options: ["a/b", "r/v", "none"], default: "a/b", description: __("a/b: 1a, 1b, 2a… · r/v: 1r, 1v… · none: 1, 2, 3…"), change: () => show(d) },
			{ fieldname: "start_image", fieldtype: "Int", label: __("First image of the first leaf"), default: 1, description: __("Images before it (a cover, a ruler and colour card) are labelled front 1, front 2…"), change: () => show(d) },
			{ fieldname: "leaves", fieldtype: "Int", label: __("Images that are leaves (0 = all the rest)"), default: 0, change: () => show(d) },
			{ fieldname: "start_folio", fieldtype: "Int", label: __("Number of the first leaf"), default: 1, change: () => show(d) },
			{ fieldname: "preview", fieldtype: "HTML" },
		],
		primary_action_label: __("Save Labels"),
		primary_action() {
			frappe.call({ method: "sok_resdesk.manuscripts.label_leaves", args: args(d), freeze: true }).then(() => {
				d.hide();
				frappe.show_alert({ message: __("Labels saved; search follows in a moment."), indicator: "green" });
				frm.reload_doc();
			});
		},
		secondary_action_label: __("Back to the Source's Numbers"),
		secondary_action() {
			frappe.call({ method: "sok_resdesk.manuscripts.clear_labels", args: { item: frm.doc.name } }).then(() => { d.hide(); frm.reload_doc(); });
		},
	});
	d.show();
	show(d);
}
