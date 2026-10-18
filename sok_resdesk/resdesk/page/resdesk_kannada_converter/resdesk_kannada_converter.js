// Copyright (c) 2026, Servants of Knowledge and contributors
// License: MIT. See LICENSE
//
// Convert Old Kannada Text: paste text typed in an old font (Nudi, Baraha, ShreeLipi…) and get Unicode,
// or the other way round (sok_resdesk/legacy_kannada.py, with the Sanchaya converter).

frappe.pages["resdesk-kannada-converter"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Convert Old Kannada Text"), single_column: true });
	const $body = $('<div class="rdk"></div>').appendTo(page.main);
	const fonts = ["Nudi / Baraha", "ShreeLipi (KAN-850)", "Prakashak (Praja)", "Akruti (Mono)", "Surabhi (KND-series)", "ISM (KNTT-Nandi)", "Dharma ILs", "Janna Mono", "SriLipi 850", "Shree Deccan", "Surabhi KN", "Suchi Kan", "ISM (KNB TT-Nandi)", "Akruti Bi", "WinKey KanEng"];
	const field = (label, el) => `<div class="form-group"><label class="control-label">${label}</label>${el}</div>`;
	$body.html(
		`<p class="text-muted">${__("Paste text typed in an old Kannada font, such as PÀ£ÀßqÀ, and get Unicode (ಕನ್ನಡ). Nothing is saved.")}</p>` +
		field(__("Font"), `<select class="form-control rdk-font">${fonts.map((f) => `<option>${frappe.utils.escape_html(f)}</option>`).join("")}</select>`) +
		field(__("Direction"), `<select class="form-control rdk-dir"><option value="a2u">${__("Old font to Unicode")}</option><option value="u2a">${__("Unicode to old font")}</option></select>`) +
		field(__("Text"), `<textarea class="form-control rdk-in" rows="8" maxlength="50000"></textarea>`) +
		field(__("Result"), `<textarea class="form-control rdk-out" rows="8" readonly></textarea>`)
	);
	page.set_primary_action(__("Convert"), () => {
		const text = $body.find(".rdk-in").val();
		if (!text.trim()) return frappe.show_alert({ message: __("Paste some text first."), indicator: "orange" });
		frappe.call({
			method: "sok_resdesk.legacy_kannada.convert_text",
			type: "POST",
			args: { text, font: $body.find(".rdk-font").val(), direction: $body.find(".rdk-dir").val() },
			freeze: true,
		}).then((r) => $body.find(".rdk-out").val(r.message || ""));
	}, "retweet");
	page.add_menu_item(__("Help for this screen"), () =>
		window.rd_open_help ? window.rd_open_help("/app/resdesk-help/legacy-kannada") : frappe.set_route("resdesk-help", "legacy-kannada")
	);
};
