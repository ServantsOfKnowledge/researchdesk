// Research Desk is the whole Desk: when Settings → The Desk says so (frappe.boot.resdesk_desk_only),
// the way to Frappe's own desktop is closed, so an administrator never lands in a place Research Desk's
// sidebar does not lead out of. Frappe's tools are in the sidebar under Administration.
(function () {
	const HOME = "research-desk";

	function only() {
		return !!(window.frappe && frappe.boot && frappe.boot.resdesk_desk_only);
	}

	// Frappe's desktop (the apps grid) is the bare /desk address
	function guard() {
		if (!only()) return;
		document.body.classList.add("rd-desk-only");
		const path = location.pathname.replace(/\/+$/, "");
		if (path === "/desk" || path === "/desk/desktop" || path === "/app" || path === "/desk/apps") {
			frappe.set_route(HOME);
		}
	}

	$(document).on("page-change", guard);
	$(function () {
		guard();
		if (frappe.router && frappe.router.on) frappe.router.on("change", () => setTimeout(guard, 0));
	});
})();
