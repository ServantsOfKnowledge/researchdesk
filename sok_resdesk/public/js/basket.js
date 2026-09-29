// "My list": a reading list kept in the browser, exportable as BibTeX / RIS /
// CSL-JSON / APA / MARCXML, and shareable as a link (?list=id1,id2,...).
(function () {
	const KEY = "rd-basket";

	function read() {
		try {
			return JSON.parse(localStorage.getItem(KEY) || "[]");
		} catch (e) {
			return [];
		}
	}
	function write(ids) {
		try {
			localStorage.setItem(KEY, JSON.stringify(ids));
		} catch (e) {
			/* private mode: list lasts for this page only */
		}
		document.dispatchEvent(new CustomEvent("rd-basket-change", { detail: ids }));
	}

	const RDBasket = {
		ids: read,
		has: (id) => read().includes(id),
		add(id) {
			const ids = read();
			if (!ids.includes(id)) ids.push(id);
			write(ids);
		},
		remove(id) {
			write(read().filter((x) => x !== id));
		},
		toggle(id) {
			RDBasket.has(id) ? RDBasket.remove(id) : RDBasket.add(id);
		},
		clear() {
			write([]);
		},
		merge(ids) {
			const cur = read();
			ids.forEach((i) => i && !cur.includes(i) && cur.push(i));
			write(cur);
		},
		exportUrl(fmt) {
			const ids = encodeURIComponent(JSON.stringify(read()));
			if (fmt === "marc") return `/api/method/sok_resdesk.api.marcxml?item_ids=${ids}`;
			return `/api/method/sok_resdesk.api.cite_many?format=${fmt}&item_ids=${ids}`;
		},
		shareUrl() {
			return `${location.origin}/library?list=${read().map(encodeURIComponent).join(",")}`;
		},
	};

	// A shared link (?list=a,b,c) adds those items to this browser's list.
	const shared = new URLSearchParams(location.search).get("list");
	if (shared) RDBasket.merge(shared.split(","));

	window.RDBasket = RDBasket;
})();
