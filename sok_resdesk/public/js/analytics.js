// Research Desk usage statistics on portal pages (sok_resdesk/analytics.py): loads the
// service chosen in Settings (PostHog, Plausible or Umami), cookieless, and offers
// window.rdTrack(name, props) for a few named events. Never runs in the Desk.
(function () {
	if (location.pathname.startsWith("/app") || location.pathname.startsWith("/desk")) return;
	const KEY = "rd-analytics";
	const queue = [];
	window.rdTrack = function (name, props) {
		try {
			if (window.posthog && window.posthog.capture) window.posthog.capture(name, props || {});
			else if (window.umami && window.umami.track) window.umami.track(name, props || {});
			else if (window.plausible) window.plausible(name, { props: props || {} });
			else queue.push([name, props]);
		} catch (e) {}
	};
	function add(src, attrs, onload) {
		const s = document.createElement("script");
		s.async = true;
		s.src = src;
		Object.entries(attrs || {}).forEach(([k, v]) => s.setAttribute(k, v));
		if (onload) s.onload = onload;
		document.head.appendChild(s);
	}
	const flush = () => queue.splice(0).forEach(([n, p]) => window.rdTrack(n, p));
	function start(c) {
		if (!c || !c.provider || !c.host || !c.key) {
			queue.length = 0;
			window.rdTrack = function () {}; // statistics off (or built-in, counted on the server)
			return;
		}
		if (c.provider === "PostHog") {
			add(c.host.replace(".i.posthog.com", "-assets.i.posthog.com") + "/static/array.js", {}, () => {
				if (!window.posthog) return;
				window.posthog.init(c.key, {
					api_host: c.host,
					persistence: "memory", // no cookies, nothing stored in the browser
					person_profiles: "identified_only", // readers are never identified
					disable_session_recording: true,
					capture_pageview: true,
					autocapture: true,
				});
				flush();
			});
		} else if (c.provider === "Plausible") {
			window.plausible = window.plausible || function () { (window.plausible.q = window.plausible.q || []).push(arguments); };
			add(c.host + "/js/script.js", { "data-domain": c.key, defer: "" });
			flush();
		} else if (c.provider === "Umami") {
			add(c.host + "/script.js", { "data-website-id": c.key, defer: "" }, flush);
		}
	}
	let c = null;
	try {
		c = JSON.parse(sessionStorage.getItem(KEY) || "null");
	} catch (e) {}
	if (c) return start(c);
	fetch("/api/method/sok_resdesk.analytics.config", { headers: { Accept: "application/json" } })
		.then((r) => r.json())
		.then((b) => {
			c = b.message || {};
			try {
				sessionStorage.setItem(KEY, JSON.stringify(c));
			} catch (e) {}
			start(c);
		})
		.catch(() => {});
})();
