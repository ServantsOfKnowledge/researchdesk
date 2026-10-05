// Copyright (c) 2026, Servants of Knowledge and contributors
// License: MIT. See LICENSE

frappe.ui.form.on("RD Ground Truth", {
	refresh(frm) {
		if (frm.is_new()) {
			frm.set_intro(__("Choose which proofread pages go in the set, then Save and <b>Make the Set</b>."), "blue");
			return;
		}
		const call = (method, args, done) =>
			frappe.call({ method: `sok_resdesk.groundtruth.${method}`, args: { name: frm.doc.name, ...(args || {}) }, freeze: true, callback: done || (() => frm.reload_doc()) });
		if (["Queued", "Running"].includes(frm.doc.status)) {
			frm.set_intro(__("Making the set: page images come from archive.org one at a time. This page refreshes by itself."), "orange");
			setTimeout(() => frm.reload_doc(), 5000);
			return;
		}
		frappe.call({ method: "sok_resdesk.groundtruth.preview", args: { name: frm.doc.name } }).then((r) => {
			const p = r.message || {};
			const licence = p.licence
				? __("It will carry the licence {0}.", [`<b>${frappe.utils.escape_html(p.licence)}</b>`])
				: __("No licence is chosen yet (Settings → Ground Truth): the set is for the library's own use and cannot go on the portal.");
			if (frm.doc.status === "Ready") {
				frm.set_intro(
					__("Ready: {0} pages and {1} page parts from {2} books.", [frm.doc.page_count, frm.doc.zone_count, frm.doc.book_count]) +
						" " + (frm.doc.published ? __("On the portal at {0}.", ['<a href="/library/ground-truth" target="_blank">/library/ground-truth</a>']) : ""),
					"green"
				);
			} else {
				const ask = (p.to_ask || []).length
					? "<br>" + __("Left out for want of a release: {0} pages. To ask: {1}.", [p.left_out, p.to_ask.map((x) => `${frappe.utils.escape_html(x.name)} (${x.pages}, ${frappe.utils.escape_html(x.why)})`).join("; ")])
					: p.left_out ? "<br>" + __("Left out for want of a release: {0} pages.", [p.left_out]) : "";
				frm.set_intro(__("{0} proofread pages match now.", [p.pages || 0]) + " " + licence + ask, p.pages ? "blue" : "orange");
			}
		});
		frm.add_custom_button(frm.doc.status === "Ready" ? __("Make Again") : __("Make the Set"), () => call("build")).addClass(frm.doc.status === "Ready" ? "" : "btn-primary");
		if (frm.doc.status === "Ready") {
			frm.add_custom_button(__("Download"), () => window.open(`/api/method/sok_resdesk.groundtruth.download?name=${encodeURIComponent(frm.doc.name)}`)).addClass("btn-primary");
			frm.add_custom_button(__("Review the Set"), () => review(frm));
			if (frm.doc.published) frm.add_custom_button(__("Take off the Portal"), () => call("publish", { on: 0 }));
			else frm.add_custom_button(__("Put on the Portal"), () => call("publish", { on: 1 }));
		}
	},
});

// Look through a spread of the set, then say it may be shared.
function review(frm) {
	const esc = frappe.utils.escape_html;
	frappe.call({ method: "sok_resdesk.groundtruth.sample", args: { name: frm.doc.name }, freeze: true }).then((r) => {
		const x = r.message;
		const d = new frappe.ui.Dialog({
			title: __("Review the set"),
			size: "large",
			fields: [
				{
					fieldtype: "HTML",
					options:
						`<p>${__("{0} pages under {1}; {2} left out because their proofreaders have not released them.", [x.pages, `<b>${esc(x.licence || "—")}</b>`, x.left_out || 0])}</p>` +
						x.sample.map((p) => `<div style="margin:0 0 .8em"><a href="${esc(p.url)}" target="_blank" rel="noopener">${esc(p.book)} · ${esc(p.label)}</a> <span class="text-muted">${esc(p.status)}</span><pre style="white-space:pre-wrap;max-height:8em;overflow:auto;font-size:12px">${esc(p.text)}</pre></div>`).join(""),
				},
			],
			primary_action_label: __("Mark Reviewed"),
			primary_action() {
				frappe.call({ method: "sok_resdesk.groundtruth.mark_reviewed", args: { name: frm.doc.name }, freeze: true }).then(() => {
					d.hide();
					frm.reload_doc();
				});
			},
		});
		d.show();
	});
}
