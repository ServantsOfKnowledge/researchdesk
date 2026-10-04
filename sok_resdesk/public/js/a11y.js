// Research Desk accessibility helpers on every portal page (hooks.py web_include_js):
// a "Skip to content" link, the language of Indic text for screen readers, and less motion for
// readers who ask their system for it. See docs/accessibility.md.
// Also the portal's words in the reader's language: window.rdT (used as __ by the portal's
// scripts) and the language switch, from RD_I18N (translations.py website_context).
(function () {
	const I18N = window.RD_I18N || {};
	const MESSAGES = I18N.messages || {};
	// __("{0} books", [n]): the phrase in the reader's language, with its places filled in
	window.rdT = function (txt, args) {
		let out = (txt && MESSAGES[txt]) || txt || "";
		if (args) out = out.replace(/\{(\d+)\}/g, (m, n) => (args[n] !== undefined ? args[n] : m));
		return out;
	};
	const __ = window.rdT;

	// catalogue language (ISO 639-3) → BCP 47, as core/normalize.py BCP47
	const BCP47 = { eng: "en", kan: "kn", hin: "hi", kok: "kok", ory: "or", ori: "or", tam: "ta", mal: "ml", tel: "te", san: "sa", mar: "mr", ben: "bn",
		guj: "gu", pan: "pa", urd: "ur", tcy: "tcy", kfa: "kfa", asm: "as", nep: "ne", pli: "pi", pra: "pra", ara: "ar", per: "fa", fre: "fr", ger: "de",
		por: "pt", lat: "la", rus: "ru", spa: "es", jpn: "ja", chi: "zh" };
	// script → [its usual language, languages written in it] (core/normalize.py SCRIPT_BLOCKS)
	const BLOCKS = { 0x900: ["hi", ["hi", "mr", "sa", "ne", "kok", "pi", "pra"]], 0x980: ["bn", ["bn", "as"]], 0xa00: ["pa", ["pa"]], 0xa80: ["gu", ["gu"]],
		0xb00: ["or", ["or"]], 0xb80: ["ta", ["ta"]], 0xc00: ["te", ["te"]], 0xc80: ["kn", ["kn", "kok", "tcy", "kfa", "sa"]], 0xd00: ["ml", ["ml"]] };

	function langTag(code) {
		code = String(code || "").trim().toLowerCase();
		if (!code || ["mul", "und", "zxx"].includes(code)) return "";
		return code.length === 2 ? code : BCP47[code] || "";
	}

	// the lang for a title or quote: the book's language when the text is in its script, else the
	// script's usual language, else "" (Latin letters keep the page's language)
	function textLang(text, code) {
		const tag = langTag(code);
		for (const ch of String(text || "")) {
			const b = BLOCKS[ch.codePointAt(0) & ~0x7f];
			if (b) return b[1].includes(tag) ? tag : b[0];
		}
		return "";
	}

	window.rdLangTag = langTag;
	window.rdTextLang = textLang;
	window.rdLangAttr = (text, code) => {
		const l = textLang(text, code);
		return l ? ` lang="${l}"` : "";
	};
	window.rdReducedMotion = () => window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
	window.rdScroll = (el, block) => el && el.scrollIntoView({ block: block || "nearest", behavior: window.rdReducedMotion() ? "auto" : "smooth" });

	function skipLink() {
		const main = document.querySelector("main");
		if (!main || document.querySelector(".rd-skip")) return;
		if (!main.id) main.id = "rd-main";
		if (!main.hasAttribute("tabindex")) main.setAttribute("tabindex", "-1"); // so focus lands there
		const a = document.createElement("a");
		a.className = "rd-skip";
		a.href = `#${main.id}`;
		a.textContent = __("Skip to content");
		document.body.insertBefore(a, document.body.firstChild);
	}

	// the top bar's tools (reading settings, language): at the end of the top bar; on phones beside
	// the menu button, so they stay visible when the menu is folded away (resdesk.css orders them)
	function tools() {
		let box = document.querySelector(".rd-tools");
		if (box) return box;
		box = document.createElement("div");
		box.className = "rd-tools";
		const toggler = document.querySelector(".navbar .navbar-toggler");
		const nav = document.querySelector(".navbar");
		if (toggler) toggler.parentNode.appendChild(box);
		else if (nav) (nav.querySelector(".container") || nav).appendChild(box);
		else document.body.insertBefore(box, document.body.firstChild);
		return box;
	}

	// the language switch (only when the portal is offered in other languages)
	function languageSwitch() {
		const langs = I18N.languages || [];
		if (langs.length < 2 || document.querySelector(".rd-langs")) return;
		const wrap = document.createElement("div");
		wrap.className = "rd-langs";
		const id = "rd-lang-switch";
		wrap.innerHTML = `<label class="rd-sr-only" for="${id}">${__("Language")}</label>
			<select id="${id}" class="rd-langs__select"></select>`;
		const select = wrap.querySelector("select");
		langs.forEach((l) => {
			const o = document.createElement("option");
			o.value = l.code;
			o.textContent = l.name;
			o.lang = l.code;
			select.appendChild(o);
		});
		select.value = langs.some((l) => l.code === I18N.lang) ? I18N.lang : "en";
		select.addEventListener("change", async () => {
			const lang = select.value;
			document.cookie = `preferred_language=${encodeURIComponent(lang)}; path=/; max-age=31536000; SameSite=Lax`;
			try {
				const body = new URLSearchParams({ lang });
				await fetch("/api/method/sok_resdesk.translations.set_language", {
					method: "POST",
					headers: { "X-Frappe-CSRF-Token": (window.frappe && frappe.csrf_token) || "", Accept: "application/json" },
					body,
				});
			} catch (e) {
				/* the cookie alone is enough for visitors */
			}
			location.reload();
		});
		tools().appendChild(wrap);
	}

	// Reading settings: text size, line spacing, letter and word spacing, colours. Each reader's
	// choice is kept in their browser (translations.py applies it in the page's head, before the
	// page is drawn); WCAG 1.4.4, 1.4.8 and 1.4.12.
	const READING = {
		size: { label: __("Text size"), options: [["sm", __("Smaller")], ["", __("Normal")], ["lg", __("Larger")], ["xl", __("Largest")]] },
		leading: { label: __("Line spacing"), options: [["", __("Normal")], ["wide", __("Wide")], ["wider", __("Wider")]] },
		spacing: { label: __("Letter and word spacing"), options: [["", __("Normal")], ["wide", __("Wide")]] },
		colours: { label: __("Colours"), options: [["", __("The site's")], ["contrast", __("High contrast")], ["dark", __("Light on dark")], ["sepia", __("Soft (sepia)")]] },
	};
	const KEY = "rd-reading";
	function loadReading() {
		try {
			return JSON.parse(localStorage.getItem(KEY) || "{}") || {};
		} catch (e) {
			return {};
		}
	}
	function applyReading(prefs) {
		Object.keys(READING).forEach((k) => {
			if (prefs[k]) document.documentElement.setAttribute(`data-rd-${k}`, prefs[k]);
			else document.documentElement.removeAttribute(`data-rd-${k}`);
		});
	}
	function readingSettings() {
		if (document.querySelector(".rd-reading")) return;
		const prefs = loadReading();
		const wrap = document.createElement("div");
		wrap.className = "rd-reading";
		const groups = Object.entries(READING)
			.map(
				([k, g]) => `<fieldset><legend>${g.label}</legend>${g.options
					.map(([v, l]) => `<label><input type="radio" name="rd-reading-${k}" value="${v}" ${(prefs[k] || "") === v ? "checked" : ""}> ${l}</label>`)
					.join("")}</fieldset>`
			)
			.join("");
		wrap.innerHTML = `<button type="button" class="rd-reading__btn" aria-expanded="false" aria-controls="rd-reading-panel" title="${__("Reading settings")}">
				<span aria-hidden="true">Aa</span><span class="rd-sr-only">${__("Reading settings")}</span></button>
			<div class="rd-reading__panel" id="rd-reading-panel" role="group" aria-label="${__("Reading settings")}" hidden>${groups}
				<button type="button" class="rd-reading__reset">${__("Back to normal")}</button></div>`;
		const btn = wrap.querySelector(".rd-reading__btn");
		const panel = wrap.querySelector(".rd-reading__panel");
		const show = (on) => {
			panel.hidden = !on;
			btn.setAttribute("aria-expanded", on ? "true" : "false");
			if (!on) return;
			// under the button, inside the window whatever the top bar's layout
			const r = btn.getBoundingClientRect();
			const w = panel.offsetWidth;
			panel.style.position = "fixed";
			panel.style.top = `${Math.round(r.bottom + 6)}px`;
			panel.style.right = "auto";
			panel.style.left = `${Math.round(Math.max(8, Math.min(r.right - w, document.documentElement.clientWidth - w - 8)))}px`;
			(panel.querySelector("input:checked") || panel.querySelector("input")).focus();
		};
		const save = () => {
			const now = {};
			Object.keys(READING).forEach((k) => {
				const c = panel.querySelector(`input[name="rd-reading-${k}"]:checked`);
				if (c && c.value) now[k] = c.value;
			});
			applyReading(now);
			try {
				localStorage.setItem(KEY, JSON.stringify(now));
			} catch (e) {
				/* private window: the settings last for this page */
			}
		};
		btn.addEventListener("click", () => show(panel.hidden));
		panel.addEventListener("change", save);
		panel.querySelector(".rd-reading__reset").addEventListener("click", () => {
			panel.querySelectorAll("input").forEach((i) => (i.checked = i.value === ""));
			save();
		});
		panel.addEventListener("keydown", (e) => {
			if (e.key === "Escape") show(false), btn.focus();
		});
		document.addEventListener("click", (e) => {
			if (!panel.hidden && !wrap.contains(e.target)) show(false);
		});
		tools().prepend(wrap);
	}
	applyReading(loadReading()); // pages without the head script (Frappe's own pages)

	function ready() {
		skipLink();
		readingSettings();
		languageSwitch();
	}
	document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", ready) : ready();
})();
