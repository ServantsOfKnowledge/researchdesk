// Research Desk accessibility helpers on every portal page (hooks.py web_include_js):
// a "Skip to content" link, the language of Indic text for screen readers, and less motion for
// readers who ask their system for it. See docs/accessibility.md.
(function () {
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
		a.textContent = (window.__ && window.__("Skip to content")) || "Skip to content";
		document.body.insertBefore(a, document.body.firstChild);
	}
	document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", skipLink) : skipLink();
})();
