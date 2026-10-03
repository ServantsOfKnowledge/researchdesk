// Research Desk item page: citation tabs, copy/download, search inside, reader jumps.
(function () {
	const $ = (sel) => document.querySelector(sel);
	const root = () => $("#rd-item");

	function esc(s) {
		return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
	}
	function safeMarked(s) {
		return esc(s).replace(/&lt;mark&gt;/g, "<mark>").replace(/&lt;\/mark&gt;/g, "</mark>");
	}

	function initCite() {
		const tabs = document.querySelectorAll(".rd-tab");
		const itemId = root().dataset.item;
		tabs.forEach((t) =>
			t.addEventListener("click", () => {
				tabs.forEach((x) => x.classList.toggle("is-active", x === t));
				document.querySelectorAll(".rd-cite").forEach((p) => p.classList.toggle("is-hidden", p.dataset.fmt !== t.dataset.fmt));
				$("#rd-download").href = `/api/method/sok_resdesk.api.cite?item_id=${encodeURIComponent(itemId)}&format=${t.dataset.fmt}&download=1`;
			})
		);
		$("#rd-copy").addEventListener("click", async () => {
			const text = document.querySelector(".rd-cite:not(.is-hidden)").textContent;
			try {
				await navigator.clipboard.writeText(text);
				$("#rd-copy").textContent = "Copied ✓";
				setTimeout(() => ($("#rd-copy").textContent = "Copy"), 1500);
			} catch (e) {
				const r = document.createRange();
				r.selectNodeContents(document.querySelector(".rd-cite:not(.is-hidden)"));
				getSelection().removeAllRanges();
				getSelection().addRange(r);
			}
		});
	}

	function initList() {
		const btn = $("#rd-add-list");
		const id = root().dataset.item;
		const paint = () => (btn.textContent = RDBasket.has(id) ? "✓ In my list" : "Add to my list");
		btn.addEventListener("click", () => RDBasket.toggle(id));
		document.addEventListener("rd-basket-change", paint);
		paint();
	}

	function jumpTo(leaf) {
		const el = root();
		// the page reader, when it is the one showing: it opens the page with the words marked
		if (window.RDPages && RDPages.active() && Number(leaf) >= 0) return RDPages.go(leaf, ($("#rd-inside-q") || {}).value || "");
		const frame = $("#rd-reader-frame");
		if (!frame || Number(leaf) < 0) return; // text sections without a page number
		if (el.dataset.reader === "pdf") {
			frame.src = `${el.dataset.pdf}#page=${Number(leaf) + 1}`;
		} else {
			frame.src = `https://archive.org/embed/${encodeURIComponent(el.dataset.item)}#page/n${leaf}/mode/1up`;
		}
		frame.scrollIntoView({ behavior: "smooth", block: "start" });
	}

	function pageLabel(h) {
		if (h.page_label && String(h.page_label).startsWith("§")) return esc(h.page_label);
		return h.page_label ? "p. " + esc(h.page_label) : "leaf " + h.leaf;
	}

	async function searchInside(q) {
		const list = $("#rd-inside-hits");
		if (!q) return (list.innerHTML = "");
		list.innerHTML = '<li class="rd-muted">Searching…</li>';
		const params = new URLSearchParams({ item_id: root().dataset.item, q });
		try {
			const res = await fetch(`/api/method/sok_resdesk.api.search_inside?${params}`);
			const data = (await res.json()).message || { hits: [] };
			if (!data.hits.length) return (list.innerHTML = '<li class="rd-muted">No matches in this book’s OCR text.</li>');
			list.innerHTML = data.hits
				.map(
					(h) => `<li><button type="button" class="rd-linkish" data-leaf="${h.leaf}">
						<b>${pageLabel(h)}</b> ${safeMarked(h.snippet)}</button></li>`
				)
				.join("");
		} catch (e) {
			list.innerHTML = '<li class="rd-error">Search inside is unavailable.</li>';
		}
	}

	function initInside() {
		const form = $("#rd-inside-form");
		if (!form) return; // members-only book, visitor not logged in
		form.addEventListener("submit", (e) => {
			e.preventDefault();
			searchInside($("#rd-inside-q").value.trim());
		});
		$("#rd-inside-hits").addEventListener("click", (e) => {
			const b = e.target.closest("[data-leaf]");
			if (b) jumpTo(b.dataset.leaf);
		});
		const q = $("#rd-inside-q").value.trim();
		if (q && !$("#rd-inside-q").disabled) searchInside(q);
	}

	document.addEventListener("DOMContentLoaded", () => {
		if (!root()) return;
		initCite();
		initList();
		initInside();
	});
})();
