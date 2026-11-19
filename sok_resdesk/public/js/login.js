// Frappe's login page has its own "Sign up" tab, which emails a link to set a password. When the library
// lets people join (Settings → Reader Accounts), send that click to the library's one-page sign-up instead:
// name, email and a password, and the reader is in at once, with no email needed. Social login buttons are
// untouched; this only changes where "Sign up" goes.
(function () {
	if (!/^\/login\/?$/.test(location.pathname)) return;

	function join() {
		const next = new URLSearchParams(location.search).get("redirect-to");
		location.href = "/library/join" + (next ? `?redirect-to=${encodeURIComponent(next)}` : "");
	}

	async function init() {
		try {
			const r = await fetch("/api/method/sok_resdesk.signup.can_join", { headers: { Accept: "application/json" } });
			if (!((await r.json()).message || {}).open) return;
		} catch (e) {
			return; // leave Frappe's own page as it is
		}
		if (location.hash === "#signup") return join();
		document.addEventListener(
			"click",
			(e) => {
				const link = e.target.closest('a[href="#signup"], .sign-up-message a, .btn-signup');
				if (!link) return;
				e.preventDefault();
				e.stopPropagation();
				join();
			},
			true
		);
		window.addEventListener("hashchange", () => location.hash === "#signup" && join());
	}

	document.addEventListener("DOMContentLoaded", init);
})();
