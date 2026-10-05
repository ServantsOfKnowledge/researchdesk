// Copyright (c) 2026, Servants of Knowledge and contributors
// License: MIT. See LICENSE

frappe.ui.form.on("RD Contributor Release", {
	refresh(frm) {
		frm.set_intro(
			`<p>${__("The pages you proofread and validate can help train better OCR for these scripts, if they are shared openly. Choose the open licence you are happy with. Nothing of yours is shared without it, and you can withdraw it (delete this record) at any time: sets made afterwards leave your pages out.")}</p>` +
				`<p class="text-muted">${__("Sets are reviewed by a person before they go on the portal, and carry only pages whose proofreaders and validators have all released them under a licence at least as strict as the set's.")}</p>`,
			"blue"
		);
	},
});
