// Read aloud in Page & text: the page's text spoken by the browser's own speech (the Web Speech
// API), in a voice for the book's language when the device has one (Kannada, Hindi, Tamil… on
// Android and Chrome; Windows and macOS have voices to add). See docs/accessibility.md.
(function () {
	const $ = (s) => document.querySelector(s);
	let text = "", speaking = false;

	const synth = () => window.speechSynthesis;
	function lang() {
		return ($("#rd-pages-text") && $("#rd-pages-text").getAttribute("lang")) || document.documentElement.lang || "en";
	}
	function say(msg) {
		const s = $("#rd-read-status");
		if (s) s.textContent = msg;
	}
	function voiceFor(tag) {
		const voices = synth().getVoices();
		return voices.find((v) => v.lang.toLowerCase() === `${tag}-in`) || voices.find((v) => v.lang.toLowerCase().split(/[-_]/)[0] === tag);
	}
	// short pieces: some browsers stop a long utterance after a few seconds
	function pieces(t) {
		const out = [];
		for (const para of t.split(/\n\s*\n/)) {
			let cur = "";
			for (const part of para.replace(/\s+/g, " ").split(/(?<=[.!?।॥|])\s+/)) {
				if ((cur + " " + part).length > 220 && cur) out.push(cur), (cur = part);
				else cur = cur ? `${cur} ${part}` : part;
			}
			if (cur.trim()) out.push(cur.trim());
		}
		return out;
	}
	function stop() {
		if (synth()) synth().cancel();
		speaking = false;
		const b = $("#rd-read-aloud");
		if (b) b.setAttribute("aria-pressed", "false"), (b.textContent = "Read aloud");
	}
	function start() {
		if (!text.trim()) return say("This page has no text to read.");
		const tag = lang().toLowerCase().split("-")[0];
		const voice = voiceFor(tag);
		if (!voice && tag !== "en") {
			say(`This device has no voice for this language (${tag}). Add one (Android: Settings → Text-to-speech; Windows: Settings → Time & language → Speech), or use a screen reader.`);
			return;
		}
		synth().cancel();
		const list = pieces(text);
		speaking = true;
		const b = $("#rd-read-aloud");
		b.setAttribute("aria-pressed", "true");
		b.textContent = "Stop reading";
		say(voice ? `Reading with ${voice.name}.` : "");
		list.forEach((p, i) => {
			const u = new SpeechSynthesisUtterance(p);
			u.lang = voice ? voice.lang : tag;
			if (voice) u.voice = voice;
			if (i === list.length - 1) u.onend = () => (stop(), say("Finished this page."));
			synth().speak(u);
		});
	}

	function init() {
		const b = $("#rd-read-aloud");
		if (!b) return;
		if (!synth() || !window.SpeechSynthesisUtterance) return; // not offered where the browser can't
		b.hidden = false;
		synth().getVoices(); // some browsers load their voices on the first ask
		b.addEventListener("click", () => (speaking ? stop() : start()));
		document.addEventListener("rd-page-shown", (e) => {
			text = (e.detail && e.detail.text) || "";
			if (speaking) stop(), say("");
		});
		window.addEventListener("pagehide", stop);
	}
	document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", init) : init();
})();
