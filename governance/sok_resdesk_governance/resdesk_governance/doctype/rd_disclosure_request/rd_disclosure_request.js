// Copyright (c) 2026, Servants of Knowledge and contributors
// License: MIT. See LICENSE

frappe.ui.form.on("RD Disclosure Request", {
	refresh(frm) {
		if (frm.is_new()) return;
		const call = (method, args, done) =>
			frappe.call({ method: "sok_resdesk_governance.disclosure." + method, args: { name: frm.doc.name, ...args }, freeze: true }).then(() => {
				frm.reload_doc();
				if (done) done();
			});
		if (frm.doc.status === "In review") {
			frm.add_custom_button(__("Decide"), () => frappe.confirm(__("Record the decision on every listed record?"), () => call("decide")));
		}
		if (frm.doc.status === "Decided") {
			frm.add_custom_button(__("Make the Package"), () => call("release"));
		}
		if (["In review", "Decided", "Received", "Released"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Close"), () =>
				frappe.prompt({ fieldname: "reason", fieldtype: "Small Text", label: __("Reason") }, (v) => call("close", { reason: v.reason }), __("Close this request"))
			);
		}
		if (frm.doc.records && frm.doc.records.length && ["Received", "In review"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Cover Parts of a Page"), () => cover_dialog(frm));
		}
		if (frm.doc.records && frm.doc.records.length) {
			frm.add_custom_button(__("Preview a Page"), () =>
				frappe.prompt(
					[
						{ fieldname: "item", fieldtype: "Select", label: __("Record"), options: frm.doc.records.map((r) => r.item), reqd: 1 },
						{ fieldname: "leaf", fieldtype: "Int", label: __("Page"), default: 1, reqd: 1 },
					],
					(v) =>
						frappe.call({ method: "sok_resdesk_governance.disclosure.preview", args: { name: frm.doc.name, item: v.item, leaf: v.leaf }, freeze: true }).then((r) => {
							const d = new frappe.ui.Dialog({ title: __("As it would be released"), size: "large" });
							d.$body.html($("<img>", { src: r.message, alt: __("The page with the covered parts black"), style: "max-width:100%" }));
							d.show();
						}),
					__("Preview a page")
				)
			);
		}
		if (frm.doc.release_error) frm.dashboard.set_headline(frappe.utils.escape_html(__("The package could not be made: {0}", [frm.doc.release_error])), "red");
		else if (frm.doc.status === "Preparing") frm.dashboard.set_headline(__("The package is being made. Reload in a few minutes."), "blue");
	},
});


// Draw boxes on a page. The boxes are kept as percentages of the page in the "Covered parts" table; the
// four number fields do the same by keyboard (a box can also be typed without drawing).
function cover_dialog(frm) {
	const items = [...new Set(frm.doc.records.map((r) => r.item))];
	let box = null; // the box being drawn, in percent
	let shown = null; // the record and page whose image is on the screen; boxes are added only to that
	let seq = 0; // the latest request for a page: an older reply that arrives late is ignored
	const d = new frappe.ui.Dialog({
		title: __("Cover parts of a page"),
		size: "extra-large",
		fields: [
			{ fieldname: "item", fieldtype: "Select", label: __("Record"), options: items, default: items[0], reqd: 1, change: () => load() },
			{ fieldname: "page", fieldtype: "Int", label: __("Page"), default: 1, reqd: 1, change: () => load() },
			{ fieldname: "col", fieldtype: "Column Break" },
			{ fieldname: "reason", fieldtype: "Data", label: __("Reason (kept in the file, not shown to the applicant)") },
			{ fieldname: "sec", fieldtype: "Section Break", label: __("Draw on the page with the mouse or a finger, or type the numbers") },
			{ fieldname: "stage", fieldtype: "HTML" },
			{ fieldname: "sec2", fieldtype: "Section Break" },
			{ fieldname: "left", fieldtype: "Float", label: __("Left % from the left edge"), change: () => draw() },
			{ fieldname: "top", fieldtype: "Float", label: __("Top % from the top edge"), change: () => draw() },
			{ fieldname: "col2", fieldtype: "Column Break" },
			{ fieldname: "width", fieldtype: "Float", label: __("Width %"), change: () => draw() },
			{ fieldname: "height", fieldtype: "Float", label: __("Height %"), change: () => draw() },
		],
		primary_action_label: __("Add This Box"),
		primary_action: () => add(),
		secondary_action_label: __("Done"),
		secondary_action: () => d.hide(),
	});
	d.$body.find(".modal-footer, .standard-actions").css("min-height", "44px");
	const $stage = $(`<div class="rd-cover" style="position:relative;display:inline-block;max-width:100%;touch-action:none;cursor:crosshair;user-select:none">
		<img alt="" style="max-width:100%;display:block;pointer-events:none"><div class="rd-cover-layer" style="position:absolute;inset:0"></div></div>
		<p class="text-muted rd-cover-status" role="status" aria-live="polite" style="margin-top:8px"></p>`);
	d.get_field("stage").$wrapper.html($stage);
	const $img = $stage.find("img"), $layer = $stage.find(".rd-cover-layer"), $status = $stage.siblings(".rd-cover-status");
	const say = (t) => $status.text(t);
	const mine = () => (frm.doc.redactions || []).filter((r) => r.item === d.get_value("item") && cint(r.page) === cint(d.get_value("page")));
	function cint(x) { return parseInt(x, 10) || 0; }
	function rect(b, style) {
		return `<div style="position:absolute;left:${b.left}%;top:${b.top}%;width:${b.width}%;height:${b.height}%;${style}"></div>`;
	}
	function draw() {
		const typed = { left: +d.get_value("left"), top: +d.get_value("top"), width: +d.get_value("width"), height: +d.get_value("height") };
		box = typed.width > 0 && typed.height > 0 ? typed : null;
		$layer.html(
			mine().map((r) => rect(r, "background:#000;opacity:.75")).join("") +
				(box ? rect(box, "border:2px dashed #d00;background:rgba(220,0,0,.2)") : "")
		);
	}
	function load() {
		const item = d.get_value("item"), page = cint(d.get_value("page"));
		if (!item || page < 1) return;
		const mine_seq = ++seq;
		shown = null;
		$img.removeAttr("src"); // never the old page under a new number
		say(__("Loading the page…"));
		frappe
			.call({ method: "sok_resdesk_governance.disclosure.page_image", args: { name: frm.doc.name, item, leaf: page }, silent: true })
			.then((r) => {
				if (mine_seq !== seq) return;
				$img.attr("src", r.message.image);
				shown = { item, page };
				say(__("Page {0} of {1}. {2} covered part(s) so far on this page.", [page, r.message.pages, mine().length]));
				draw();
			})
			.catch(() => {
				if (mine_seq !== seq) return;
				say(__("This page could not be shown, so no box can be added to it."));
			});
	}
	function add() {
		if (!shown || shown.item !== d.get_value("item") || shown.page !== cint(d.get_value("page"))) {
			frappe.msgprint(__("Wait for the page to be shown: a box is added only to the page on the screen."));
			return;
		}
		if (!box || box.width <= 0 || box.height <= 0 || box.left < 0 || box.top < 0 || box.left + box.width > 100.001 || box.top + box.height > 100.001) {
			frappe.msgprint(__("Draw a box on the page, or give a left, top, width and height that stay inside it."));
			return;
		}
		frm.add_child("redactions", { item: d.get_value("item"), page: cint(d.get_value("page")), ...box, reason: d.get_value("reason") || "" });
		frm.refresh_field("redactions");
		frm.dirty();
		["left", "top", "width", "height"].forEach((f) => d.set_value(f, null));
		box = null;
		draw();
		say(__("Added. Save the request to keep it. {0} covered part(s) on this page.", [mine().length]));
	}
	let start = null;
	const pct = (e) => {
		const r = $stage[0].getBoundingClientRect();
		return { x: Math.min(100, Math.max(0, ((e.clientX - r.left) / r.width) * 100)), y: Math.min(100, Math.max(0, ((e.clientY - r.top) / r.height) * 100)) };
	};
	const round = (n) => Math.round(n * 10) / 10;
	$stage.on("pointerdown", (e) => { start = pct(e); $stage[0].setPointerCapture(e.originalEvent.pointerId); });
	$stage.on("pointermove", (e) => {
		if (!start) return;
		const p = pct(e);
		d.set_value("left", round(Math.min(start.x, p.x)));
		d.set_value("top", round(Math.min(start.y, p.y)));
		d.set_value("width", round(Math.abs(p.x - start.x)));
		d.set_value("height", round(Math.abs(p.y - start.y)));
	});
	$stage.on("pointerup pointercancel", () => { start = null; draw(); });
	d.show();
	load();
}
