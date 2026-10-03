// Research Desk page reader ("Page & text" on the book page): each page image with its text,
// page links and page citations. It sits next to the book reader (archive.org's), which stays
// as it was: readers switch between the two, and each opens the other at the same page.
(function () {
	const $ = (sel, root) => (root || document).querySelector(sel);
	const esc = (s) =>
		String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
	const api = (method, args) =>
		fetch(`/api/method/sok_resdesk.api.${method}?${new URLSearchParams(args)}`, { headers: { Accept: "application/json" } })
			.then((r) => r.json())
			.then((b) => b.message);

	const FORMATS = [
		["apa", "APA"],
		["mla", "MLA"],
		["chicago", "Chicago"],
		["bibtex", "BibTeX"],
		["ris", "RIS"],
		["csl-json", "CSL-JSON"],
	];

	let pane, itemId, state = { leaf: 0, last: 0, label: "", q: "" }, cites = {}, citeFmt = "apa";

	function active() {
		return pane && !pane.classList.contains("is-hidden");
	}

	function setView(view, push) {
		document.querySelectorAll(".rd-view").forEach((b) => {
			const on = b.dataset.view === view;
			b.classList.toggle("is-active", on);
			b.setAttribute("aria-selected", on ? "true" : "false");
		});
		document.querySelectorAll(".rd-view-pane").forEach((p) => p.classList.toggle("is-hidden", p.dataset.pane !== view));
		if (view === "text") go(state.leaf, state.q, push);
		else remember(null);
	}

	// the address bar always says where the reader is, so it can be bookmarked or shared
	function remember(leaf) {
		const url = new URL(location.href);
		if (leaf == null) {
			url.searchParams.delete("view");
		} else {
			url.searchParams.set("page", leaf);
			url.searchParams.set("view", "text");
		}
		history.replaceState(null, "", url);
	}

	function highlight(text, q) {
		let html = esc(text);
		const words = (q || "")
			.split(/\s+/)
			.map((w) => w.replace(/[^\p{L}\p{M}\p{N}]/gu, ""))
			.filter((w) => w.length > 1);
		for (const w of words) {
			html = html.replace(new RegExp(`(${w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`, "giu"), "<mark>$1</mark>");
		}
		return html;
	}

	async function go(leaf, q, push) {
		state.q = q ?? state.q;
		const d = await api("page", { item_id: itemId, leaf: Math.max(0, Number(leaf) || 0) });
		if (!d) return;
		if (d.login_needed) {
			$("#rd-pages-text").innerHTML = `<p class="rd-muted">${esc("Log in to read this book.")}</p>`;
			return;
		}
		state = { ...state, leaf: d.leaf, last: d.last, label: d.label };
		cites = {};
		$("#rd-pages-n").value = d.leaf + 1;
		$("#rd-pages-n").max = d.last + 1;
		$("#rd-pages-of").textContent = `of ${d.last + 1}`;
		$("#rd-pages-label").textContent = d.label ? (/^\d/.test(d.label) ? `p. ${d.label}` : d.label) : "";
		const fig = $("#rd-pages-image");
		if (d.image) {
			fig.innerHTML = `<img src="${esc(d.image)}" alt="${esc(`Page image ${d.leaf + 1}`)}" loading="eager">`;
			$("img", fig).addEventListener("error", () => {
				fig.innerHTML = `<p class="rd-muted">${esc("This page image isn't available here.")} <a href="#" data-to-book>${esc("Open it in the book reader")}</a></p>`;
			});
			if (d.leaf < d.last) new Image().src = d.image.replace(/n\d+\.jpg$/, `n${d.leaf + 1}.jpg`); // the next one, ready
		} else if (d.pdf) {
			fig.innerHTML = `<p class="rd-muted"><a href="${esc(d.pdf)}#page=${d.leaf + 1}" target="_blank" rel="noopener">${esc("See this page in the PDF")}</a></p>`;
		} else {
			fig.innerHTML = "";
		}
		$("#rd-pages-text").innerHTML = d.text
			? highlight(d.text, state.q)
			: `<p class="rd-muted">${esc(d.has_text ? "No text on this page." : "No text for this book yet.")}</p>`;
		const mark = $("#rd-pages-text mark");
		if (mark) mark.scrollIntoView({ block: "center", behavior: "smooth" });
		else $("#rd-pages-text").scrollTop = 0;
		if (!$("#rd-pages-citebox").classList.contains("is-hidden")) showCite();
		// annotate.js draws the page's notes over this
		document.dispatchEvent(new CustomEvent("rd-page-shown", { detail: { ...d, text: d.text || "", q: state.q } }));
		if (active()) remember(d.leaf);
		if (push) pane.scrollIntoView({ behavior: "smooth", block: "start" });
	}

	async function citation() {
		if (!cites.formats) cites = await api("cite_page", { item_id: itemId, leaf: state.leaf, label: state.label });
		return cites;
	}

	async function showCite() {
		const c = await citation();
		$("#rd-pages-cite-tabs").innerHTML = FORMATS.map(
			([k, label]) => `<button type="button" class="rd-tab${k === citeFmt ? " is-active" : ""}" data-pfmt="${k}">${label}</button>`
		).join("");
		$("#rd-pages-cite-text").textContent = c.formats[citeFmt] || "";
	}

	async function copy(text, btn) {
		const was = btn.textContent;
		try {
			await navigator.clipboard.writeText(text);
			btn.textContent = "Copied ✓";
		} catch (e) {
			prompt("Copy:", text);
		}
		setTimeout(() => (btn.textContent = was), 1500);
	}

	function toBook(leaf) {
		const frame = $("#rd-reader-frame");
		setView("book");
		if (!frame) return;
		const root = $("#rd-item");
		frame.src =
			root.dataset.reader === "pdf"
				? `${root.dataset.pdf}#page=${Number(leaf) + 1}`
				: `https://archive.org/embed/${encodeURIComponent(root.dataset.item)}#page/n${leaf}/mode/1up`;
	}

	function init() {
		pane = $("#rd-pages");
		if (!pane) return;
		itemId = $("#rd-item").dataset.item;
		state.leaf = Number(pane.dataset.start) || 0;
		state.q = new URLSearchParams(location.search).get("q") || "";

		document.querySelectorAll(".rd-view").forEach((b) => b.addEventListener("click", () => setView(b.dataset.view)));
		pane.addEventListener("click", (e) => {
			const step = e.target.closest("[data-step]");
			if (step) go(state.leaf + Number(step.dataset.step));
			const fmt = e.target.closest("[data-pfmt]");
			if (fmt) {
				citeFmt = fmt.dataset.pfmt;
				showCite();
			}
			if (e.target.closest("[data-to-book]")) {
				e.preventDefault();
				toBook(state.leaf);
			}
		});
		$("#rd-pages-n").addEventListener("change", (e) => go(Number(e.target.value) - 1));
		$("#rd-pages-link").addEventListener("click", async (e) => copy((await citation()).url, e.target));
		$("#rd-pages-cite").addEventListener("click", () => {
			const box = $("#rd-pages-citebox");
			box.classList.toggle("is-hidden");
			if (!box.classList.contains("is-hidden")) showCite();
		});
		$("#rd-pages-cite-copy").addEventListener("click", (e) => copy($("#rd-pages-cite-text").textContent, e.target));
		$("#rd-pages-book").addEventListener("click", () => toBook(state.leaf));
		document.addEventListener("keydown", (e) => {
			if (!active() || e.target.closest("input, textarea, select, [contenteditable]")) return;
			if (e.key === "ArrowRight") go(state.leaf + 1);
			if (e.key === "ArrowLeft") go(state.leaf - 1);
		});
		if (active()) go(state.leaf);
	}

	// search inside the book (item.js) opens its hits here while this reader is showing
	window.RDPages = { active, go: (leaf, q) => go(leaf, q, true), state: () => ({ ...state }), esc };
	document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", init) : init();
})();
