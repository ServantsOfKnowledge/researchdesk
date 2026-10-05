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
		// a Frappe screen that no sidebar of ours lists (Milestone, Print Format…) would show none:
		// keep Research Desk's, so there is always a way back
		const sb = frappe.app && frappe.app.sidebar;
		if (sb && !sb.sidebar_title && frappe.boot.workspace_sidebar_item["research desk"]) {
			setTimeout(() => !sb.sidebar_title && sb.setup("Research Desk"), 150);
		}
		const path = location.pathname.replace(/\/+$/, "");
		if (path === "/desk" || path === "/desk/desktop" || path === "/app" || path === "/desk/apps") {
			frappe.set_route(HOME);
		}
	}

	// the account menu's way back to Frappe: Desktop, Workspaces (its list of Frappe's workspaces), Website
	const WAYS_BACK = ["Desktop", "Workspaces", "Website"];
	function close_menu() {
		if (!only()) return;
		const titles = new Set(WAYS_BACK.flatMap((t) => [t, __(t)]));
		document.querySelectorAll(".dropdown-menu-item").forEach((el) => {
			const t = el.querySelector(".menu-item-title");
			if (t && titles.has(t.textContent.trim())) el.style.display = "none";
		});
	}
	new MutationObserver(close_menu).observe(document.body, { childList: true, subtree: true });

	$(document).on("page-change", guard);
	$(function () {
		guard();
		if (frappe.router && frappe.router.on) frappe.router.on("change", () => setTimeout(guard, 0));
	});
})();
