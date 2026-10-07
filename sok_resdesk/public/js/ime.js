// Typing in your own language, and language boxes you type a code into (hooks.py web_include_js).
//
// 1. window.rdLang: pick a language by typing its code or a bit of its name (resolve) instead of
//    scrolling a long list. A <datalist> offers the matches as you type (WCAG 3.3.2, 2.1.1).
// 2. window.rdIme: jquery.ime (Wikimedia's input methods, public/vendor/jquery.ime) on search boxes
//    and the proofreading text, so people can type Kannada, Hindi, Tamil… on any keyboard. The
//    typing language follows the portal's language until the reader picks another; the choice is
//    kept in this browser. It loads only when someone turns typing on. See docs/accessibility.md.
(function () {
	const __ = window.rdT || ((t, a) => (a ? t.replace(/\{(\d+)\}/g, (m, n) => (a[n] !== undefined ? a[n] : m)) : t));
	const norm = (s) => String(s == null ? "" : s).trim().toLowerCase();

	// What was typed → a language code. options is {code: name}. Returns {code, matches}:
	// code "" for nothing typed, a code when exactly one language fits, null when none or several do.
	function resolve(text, options) {
		let t = norm(text);
		if (!t) return { code: "", matches: [] };
		t = t.split(/\s+[—–-]\s+/)[0]; // "kan — Kannada" as the list shows it
		const codes = Object.keys(options || {});
		const exact = codes.find((c) => norm(c) === t) || codes.find((c) => norm(options[c]) === t);
		if (exact) return { code: exact, matches: [exact] };
		const some = codes.filter((c) => norm(c).startsWith(t) || norm(options[c]).startsWith(t));
		return { code: some.length === 1 ? some[0] : null, matches: some };
	}

	// "kan — Kannada", the form the suggestions and the box show
	const describe = (code, options) => (options && options[code] ? `${code} — ${options[code]}` : code);

	// (Re)fill the <datalist id> with the languages
	function datalist(id, options) {
		let dl = document.getElementById(id);
		if (!dl) {
			dl = document.createElement("datalist");
			dl.id = id;
			document.body.appendChild(dl);
		}
		dl.innerHTML = "";
		Object.keys(options || {}).forEach((c) => {
			const o = document.createElement("option");
			o.value = describe(c, options);
			dl.appendChild(o);
		});
		return dl;
	}

	window.rdLang = { resolve, describe, datalist };
	if (typeof module !== "undefined") module.exports = window.rdLang;
	if (typeof document === "undefined" || !document.documentElement) return;

	// ---- jquery.ime ------------------------------------------------------------------------
	const BASE = "/assets/sok_resdesk/vendor/jquery.ime/";
	const KEY = "rd-ime";
	const me = document.currentScript;
	const ver = me && /[?&]v=([^&]+)/.exec(me.src) ? "?v=" + RegExp.$1 : "";
	const store = {
		get() {
			try {
				return JSON.parse(window.localStorage.getItem(KEY) || "{}") || {};
			} catch (e) {
				return {};
			}
		},
		set(v) {
			try {
				window.localStorage.setItem(KEY, JSON.stringify(v));
			} catch (e) {
				/* no storage (a private window): it just isn't remembered */
			}
		},
	};
	const uiLang = () => norm(document.documentElement.lang).split("-")[0];
	const controls = [];
	let loading = null;

	function script(src) {
		return new Promise((ok, fail) => {
			const s = document.createElement("script");
			s.src = BASE + src + ver;
			s.onload = ok;
			s.onerror = () => fail(new Error(src));
			document.head.appendChild(s);
		});
	}

	// jquery.ime, its list of languages and its stylesheet, once, when first needed
	function load() {
		if (!loading) {
			if (!window.jQuery) return Promise.reject(new Error("jQuery"));
			const css = document.createElement("link");
			css.rel = "stylesheet";
			css.href = BASE + "jquery.ime.css" + ver;
			document.head.appendChild(css);
			window.jQuery.ime = window.jQuery.ime || {};
			window.jQuery.ime.path = BASE;
			loading = script("jquery.ime.min.js")
				.then(() => {
					window.jQuery.ime.setPath && window.jQuery.ime.setPath(BASE);
					return script("ime-sources.js");
				})
				.catch((e) => ((loading = null), Promise.reject(e)));
		}
		return loading;
	}

	const languages = () => Object.fromEntries(Object.entries(window.jQuery.ime.languages).map(([c, l]) => [c, l.autonym]));

	function methods(lang) {
		const l = window.jQuery.ime.languages[lang];
		return l ? l.inputmethods.map((id) => [id, window.jQuery.ime.sources[id].name]) : [];
	}

	// the way of typing most people start with: spell it in Latin letters (transliteration), else the first
	function preferred(lang) {
		const list = methods(lang);
		const t = list.find(([id]) => /transliteration$/.test(id));
		return (t || list[0])[0];
	}

	// Put typing in (or out of) one field
	async function apply(el, on, lang, method) {
		await load();
		const $el = window.jQuery(el);
		if (!$el.data("ime")) $el.ime({ showSelector: false });
		const ime = $el.data("ime");
		if (!on) return ime.disable();
		const id = method || preferred(lang);
		await new Promise((ok, fail) => ime.load(id).done(ok).fail(fail)); // fetch the rules, then use them
		ime.setLanguage(lang);
		ime.setIM(id);
		ime.enable();
	}

	function attach(field) {
		if (!field || field.dataset.rdIme || !window.jQuery) return null;
		field.dataset.rdIme = "1";
		const n = controls.length + 1;
		const box = document.createElement("span");
		box.className = "rd-ime";
		box.innerHTML = `<button type="button" class="rd-ime__btn" aria-pressed="false" title="${__("Type in your own language (Ctrl+M)")}">${__("Type in…")}</button>
			<input class="rd-ime__code" type="text" size="9" autocomplete="off" spellcheck="false" list="rd-ime-langs" id="rd-ime-code-${n}" aria-label="${__("Typing language: type a code such as kn, or part of the name")}" placeholder="${__("code, e.g. kn")}">
			<select class="rd-ime__method" id="rd-ime-method-${n}" aria-label="${__("Way of typing")}" hidden></select>
			<span class="rd-ime__msg" role="status"></span>`;
		field.insertAdjacentElement("afterend", box);
		const btn = box.querySelector("button"), code = box.querySelector("input"), method = box.querySelector("select"), msg = box.querySelector(".rd-ime__msg");
		const ctl = { field, sync };
		controls.push(ctl);

		function state() {
			const s = store.get();
			return { on: !!s.on, lang: s.lang || uiLang(), im: (s.im || {})[s.lang || uiLang()] };
		}
		async function sync() {
			const s = state();
			btn.setAttribute("aria-pressed", s.on ? "true" : "false");
			btn.classList.toggle("is-on", s.on);
			code.value = s.lang && s.lang !== "en" ? s.lang : "";
			if (!s.on) {
				method.hidden = true;
				if (field.dataset.rdImeLoaded) apply(field, false).catch(() => {});
				return;
			}
			try {
				await load();
				const list = methods(s.lang);
				if (!list.length) throw new Error("no methods");
				method.innerHTML = list.map(([id, name]) => `<option value="${id}" ${id === (s.im || preferred(s.lang)) ? "selected" : ""}>${name}</option>`).join("");
				method.hidden = list.length < 2;
				field.dataset.rdImeLoaded = "1";
				await apply(field, true, s.lang, method.value);
				field.setAttribute("lang", s.lang);
			} catch (e) {
				msg.textContent = __("Typing in this language is not available here.");
			}
		}
		function save(patch) {
			const s = store.get();
			store.set(Object.assign(s, patch));
			controls.forEach((c) => c.sync());
		}
		btn.addEventListener("click", () => {
			const s = state();
			msg.textContent = "";
			if (!s.on && !window.jQuery) return;
			const turning = !s.on;
			save({ on: turning, lang: s.lang });
			msg.textContent = turning ? __("Typing in your language is on.") : __("Typing in your language is off.");
		});
		// the suggestions need jquery.ime's list of languages: fetch it when the box is first used
		code.addEventListener("focus", () => load().then(() => window.rdLang.datalist("rd-ime-langs", languages())).catch(() => {}), { once: true });
		code.addEventListener("change", async () => {
			msg.textContent = "";
			try {
				await load();
			} catch (e) {
				msg.textContent = __("Typing in this language is not available here.");
				return;
			}
			const r = resolve(code.value, languages());
			if (r.code === "") return save({ on: false });
			if (!r.code) {
				msg.textContent = r.matches.length ? __("Several languages fit: keep typing the code.") : __("No typing language matches “{0}”.", [code.value]);
				return;
			}
			save({ lang: r.code, on: true });
		});
		method.addEventListener("change", () => {
			const s = store.get();
			const im = Object.assign({}, s.im);
			im[s.lang || uiLang()] = method.value;
			save({ im });
		});
		sync();
		return ctl;
	}

	function init() {
		document.querySelectorAll('input[type="search"], .rd-ime-field').forEach(attach);
	}
	window.rdIme = { attach };
	document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", init) : init();
})();
