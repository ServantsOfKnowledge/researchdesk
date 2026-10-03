// Research Desk item page: the Cite window (book or page), my list, search inside, reader jumps.
(function () {
	const $ = (sel) => document.querySelector(sel);
	const root = () => $("#rd-item");

	function esc(s) {
		return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
	}
	function safeMarked(s) {
		return esc(s).replace(/&lt;mark&gt;/g, "<mark>").replace(/&lt;\/mark&gt;/g, "</mark>");
	}

	// One Cite window for the book and for the page showing in Page & text (reader.js)
	function initCite() {
		const dlg = $("#rd-cite");
		if (!dlg) return;
		const itemId = root().dataset.item;
		let scope = "book", fmt = "apa", page = null;
		const pageText = $("#rd-cite-page-text");

		function paint() {
			dlg.querySelectorAll("[data-scope]").forEach((t) => t.classList.toggle("is-active", t.dataset.scope === scope));
			dlg.querySelectorAll("[data-fmt]").forEach((t) => {
				if (t.tagName === "BUTTON") t.classList.toggle("is-active", t.dataset.fmt === fmt);
			});
			dlg.querySelectorAll("pre.rd-cite[data-fmt]").forEach((p) => p.classList.toggle("is-hidden", scope !== "book" || p.dataset.fmt !== fmt));
			pageText.classList.toggle("is-hidden", scope !== "page");
			if (scope === "page") pageText.textContent = page ? page.formats[fmt] || "" : "…";
			$("#rd-cite-where").textContent = scope === "page" && page ? `${page.page} · ${page.url}` : "";
			$("#rd-download").hidden = scope !== "book";
			$("#rd-download").href = `/api/method/sok_resdesk.api.cite?item_id=${encodeURIComponent(itemId)}&format=${fmt}&download=1`;
		}

		async function show(want) {
			const pages = window.RDPages;
			const pageTab = $("#rd-cite-page-tab");
			const canPage = !!(pages && pageTab && pages.state().shown);
			if (pageTab) {
				pageTab.disabled = !canPage;
				pageTab.title = canPage ? "" : "Open a page in Page & text to cite it";
			}
			scope = want === "page" && canPage ? "page" : "book";
			page = null;
			paint();
			if (!dlg.open) dlg.showModal ? dlg.showModal() : dlg.setAttribute("open", "");
			if (scope === "page") {
				page = await pages.citation();
				paint();
			}
		}

		document.addEventListener("click", (e) => {
			const opener = e.target.closest("#rd-cite-open, #rd-pages-cite, [data-cite-open]");
			if (opener) return show(opener.dataset.scope);
			if (!dlg.contains(e.target)) return;
			const s = e.target.closest(".rd-cite-scope [data-scope]");
			if (s && !s.disabled) show(s.dataset.scope);
			const f = e.target.closest("button[data-fmt]");
			if (f) {
				fmt = f.dataset.fmt;
				paint();
			}
		});
		dlg.addEventListener("click", (e) => {
			if (e.target === dlg) dlg.close(); // a click on the backdrop
		});
		const copy = async (text, btn) => {
			const was = btn.textContent;
			try {
				await navigator.clipboard.writeText(text);
				btn.textContent = "Copied ✓";
			} catch (e) {
				prompt("Copy:", text);
			}
			setTimeout(() => (btn.textContent = was), 1500);
		};
		$("#rd-copy").addEventListener("click", (e) => {
			copy(dlg.querySelector("pre.rd-cite:not(.is-hidden)").textContent, e.target);
			window.rdTrack && rdTrack("Citation copied", { scope, format: fmt });
		});
		$("#rd-copy-link").addEventListener("click", (e) => copy(scope === "page" && page ? page.url : dlg.dataset.url, e.target));
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
			window.rdTrack && rdTrack("Search inside a book");
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
