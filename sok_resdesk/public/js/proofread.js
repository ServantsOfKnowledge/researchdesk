// Research Desk proofreading in the page reader (Page & text → Proofread), for proofreaders and
// staff: correct the page text beside its image, and read parts of the page again with OCR.
//
// Zones: draw as many boxes on the page image as the page has parts (columns, a heading, side
// notes), in reading order; each is read on its own and their texts are joined in that order,
// so columns don't run into each other. A zone can be "skip" (a picture, a stamp). Presets give
// the common layouts in one click.
(function () {
	const $ = (sel, root) => (root || document).querySelector(sel);
	const esc = (s) =>
		String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

	let itemId, page = null, on = false, zones = [], presets = {}, versions = [], me = "", original = "";
	// OCR languages: the book's (ticked at the start) and those installed on the server
	let langs = { book: [], available: {} }, runLangs = [];

	function csrf() {
		return (window.frappe && frappe.csrf_token) || (document.cookie.match(/csrf_token=([^;]+)/) || [])[1] || "";
	}
	async function call(module, method, args, post) {
		const url = `/api/method/sok_resdesk.${module}.${method}`;
		const r = await fetch(post ? url : `${url}?${new URLSearchParams(args)}`, post
			? { method: "POST", headers: { "Content-Type": "application/json", Accept: "application/json", "X-Frappe-CSRF-Token": csrf() }, body: JSON.stringify(args) }
			: { headers: { Accept: "application/json" } });
		const body = await r.json().catch(() => ({}));
		if (!r.ok) {
			let msg = "Something went wrong.";
			try {
				msg = JSON.parse(JSON.parse(body._server_messages)[0]).message;
			} catch (e) {}
			throw new Error(msg);
		}
		return body.message;
	}

	function statusText(d) {
		if (d.text_status === "Validated") return `Validated by ${d.validated_by} · proofread by ${d.proofread_by}`;
		if (d.text_status === "Proofread") return `Proofread by ${d.proofread_by}`;
		if (d.text_status === "Machine") return "Read again by OCR, not proofread yet";
		return d.text ? "OCR from archive.org, not proofread yet" : "";
	}

	// -- the editor -------------------------------------------------------------------------------

	function frame() {
		const fig = $("#rd-pages-image");
		let f = $(".rd-image-frame", fig);
		const img = $("img", fig);
		if (!f && img) {
			f = document.createElement("div");
			f.className = "rd-image-frame";
			img.replaceWith(f);
			f.appendChild(img);
		}
		return f;
	}

	function drawZones() {
		const f = frame();
		if (!f) return;
		f.querySelectorAll(".rd-zone").forEach((z) => z.remove());
		zones.forEach((z, i) => {
			const div = document.createElement("div");
			div.className = `rd-zone${z.kind === "skip" ? " is-skip" : ""}`;
			Object.assign(div.style, { left: `${z.x}%`, top: `${z.y}%`, width: `${z.w}%`, height: `${z.h}%` });
			div.innerHTML = `<span class="rd-zone__n">${z.kind === "skip" ? "×" : i + 1}</span>`;
			div.dataset.zone = i;
			f.appendChild(div);
		});
		const list = $("#rd-zone-list");
		list.innerHTML = zones.length
			? zones
					.map(
						(z, i) => `<li data-z="${i}"><b>${z.kind === "skip" ? "×" : i + 1}</b>
				<select data-kind="${i}"><option value="text" ${z.kind === "text" ? "selected" : ""}>read</option><option value="skip" ${z.kind === "skip" ? "selected" : ""}>skip</option></select>
				<select data-zlang="${i}" title="This part's language, when it differs from the page's" ${z.kind === "skip" ? "hidden" : ""}><option value="">page's languages</option>${Object.entries(langs.available)
					.map(([m, n]) => `<option value="${esc(m)}" ${(z.langs || [])[0] === m ? "selected" : ""}>${esc(n)}</option>`)
					.join("")}</select>
				<button type="button" data-up="${i}" title="Earlier" ${i ? "" : "disabled"}>↑</button><button type="button" data-down="${i}" title="Later" ${i < zones.length - 1 ? "" : "disabled"}>↓</button>
				<button type="button" data-del="${i}" title="Remove">✕</button></li>`
					)
					.join("")
			: `<li class="rd-muted">No zones: the whole page is read as one block. Draw a box for each column or part.</li>`;
	}

	// "Read with": the languages Tesseract reads this page in (the main one first, English added)
	function drawLangs() {
		const box = $("#rd-proof-langs");
		if (!box) return;
		const all = Object.entries(langs.available);
		box.innerHTML = all.length
			? `<span class="rd-muted">Read with:</span> ${all
					.map(([m, n]) => `<label><input type="checkbox" data-lang="${esc(m)}" ${runLangs.includes(m) ? "checked" : ""}> ${esc(n)}</label>`)
					.join(" ")}`
			: "";
	}

	function editor() {
		const box = document.createElement("div");
		box.id = "rd-proof";
		box.className = "rd-proof";
		box.innerHTML = `
			<div class="rd-proof__zones">
				<button class="rd-btn" type="button" id="rd-zone-draw">Draw a zone</button>
				<select id="rd-zone-preset"><option value="">Layout…</option>${Object.keys(presets).map((k) => `<option>${esc(k)}</option>`).join("")}</select>
				<button class="rd-btn" type="button" id="rd-zone-sort" title="Columns left to right, headings where they fall">Sort</button>
				<button class="rd-btn" type="button" id="rd-zone-clear">Clear</button>
				<button class="rd-btn rd-btn--primary" type="button" id="rd-zone-ocr">OCR the zones</button>
				<span class="rd-muted" id="rd-proof-msg"></span>
				<div class="rd-proof__langs" id="rd-proof-langs"></div>
				<ol class="rd-zone-list" id="rd-zone-list"></ol>
			</div>
			<textarea id="rd-proof-text" spellcheck="false" lang="${esc($("#rd-pages-text").getAttribute("lang") || "")}"></textarea>
			<div class="rd-proof__actions">
				<button class="rd-btn rd-btn--primary" type="button" id="rd-proof-save">Save as proofread</button>
				<button class="rd-btn" type="button" id="rd-proof-validate" hidden>Validate: it's right</button>
				<button class="rd-btn" type="button" id="rd-proof-cancel">Close</button>
				<span class="rd-muted" id="rd-proof-who"></span>
			</div>
			<details class="rd-proof__history"><summary>History of this page</summary><ol id="rd-proof-history"></ol></details>`;
		return box;
	}

	async function open() {
		on = true;
		$("#rd-proof-btn").textContent = "Close proofreading";
		$("#rd-pages-text").hidden = true;
		if (!$("#rd-proof")) $("#rd-pages-text").after(editor()); // in the text's place, beside the image
		$("#rd-proof").hidden = false;
		$("#rd-proof-text").value = original = page.text || "";
		$("#rd-proof-msg").textContent = "";
		const [h, l] = await Promise.all([
			call("pagetext", "history", { item_id: itemId, leaf: page.leaf }),
			call("reocr", "languages", { item_id: itemId }).catch(() => ({ book: [], available: {} })),
		]);
		langs = l || { book: [], available: {} };
		runLangs = langs.book.slice();
		drawLangs();
		presets = h.presets || {};
		me = h.me;
		versions = h.versions || [];
		const cur = versions.find((v) => v.is_current);
		zones = cur && cur.zones && cur.zones.length ? cur.zones : [];
		$("#rd-zone-preset").innerHTML = `<option value="">Layout…</option>${Object.keys(presets).map((k) => `<option>${esc(k)}</option>`).join("")}`;
		$("#rd-proof-validate").hidden = !(cur && cur.status === "Proofread" && cur.proofread_by !== me);
		$("#rd-proof-who").textContent = statusText(page);
		$("#rd-proof-history").innerHTML = versions.length
			? versions
					.map(
						(v) => `<li>${esc(v.creation)} · ${esc(v.status)}${v.proofread_by_name ? ` by ${esc(v.proofread_by_name)}` : ""}${v.validated_by_name ? `, validated by ${esc(v.validated_by_name)}` : ""}${v.engine ? ` · ${esc(v.engine)}` : ""} · quality ${v.quality}${
							v.is_current ? " · <b>current</b>" : ` <button type="button" class="rd-linkish" data-restore="${esc(v.name)}">Make current</button>`
						}</li>`
					)
					.join("")
			: `<li class="rd-muted">archive.org's OCR only, so far.</li>`;
		drawZones();
	}

	function close() {
		on = false;
		$("#rd-proof-btn").textContent = "Proofread";
		if ($("#rd-proof")) $("#rd-proof").hidden = true;
		$("#rd-pages-text").hidden = false;
		const f = frame();
		if (f) f.querySelectorAll(".rd-zone").forEach((z) => z.remove());
	}

	function draw() {
		const f = frame();
		if (!f) return;
		const fig = $("#rd-pages-image");
		fig.classList.add("is-marking");
		$("#rd-proof-msg").textContent = "Drag a box over one part of the page.";
		let from = null, box = null;
		const at = (e) => {
			const r = f.getBoundingClientRect();
			const p = e.touches ? e.touches[0] : e;
			return { x: ((p.clientX - r.left) / r.width) * 100, y: ((p.clientY - r.top) / r.height) * 100 };
		};
		const down = (e) => {
			e.preventDefault();
			from = at(e);
			box = document.createElement("div");
			box.className = "rd-zone is-drawing";
			f.appendChild(box);
		};
		const move = (e) => {
			if (!from) return;
			const p = at(e);
			Object.assign(box.style, { left: `${Math.min(from.x, p.x)}%`, top: `${Math.min(from.y, p.y)}%`, width: `${Math.abs(p.x - from.x)}%`, height: `${Math.abs(p.y - from.y)}%` });
		};
		const up = (e) => {
			if (!from) return;
			const p = at(e.changedTouches ? e.changedTouches[0] : e);
			const c = (v) => Math.min(100, Math.max(0, v));
			const x = c(Math.min(from.x, p.x)), y = c(Math.min(from.y, p.y));
			const w = c(Math.max(from.x, p.x)) - x, h = c(Math.max(from.y, p.y)) - y;
			stop();
			if (w >= 1 && h >= 1) zones.push({ x: +x.toFixed(2), y: +y.toFixed(2), w: +w.toFixed(2), h: +h.toFixed(2), kind: "text" });
			drawZones();
			$("#rd-proof-msg").textContent = "Draw another, or OCR the zones.";
		};
		const stop = () => {
			fig.classList.remove("is-marking");
			if (box) box.remove();
			f.removeEventListener("mousedown", down);
			window.removeEventListener("mousemove", move);
			window.removeEventListener("mouseup", up);
			f.removeEventListener("touchstart", down);
			window.removeEventListener("touchmove", move);
			window.removeEventListener("touchend", up);
		};
		f.addEventListener("mousedown", down);
		window.addEventListener("mousemove", move);
		window.addEventListener("mouseup", up);
		f.addEventListener("touchstart", down, { passive: false });
		window.addEventListener("touchmove", move);
		window.addEventListener("touchend", up);
	}

	// columns left to right, top to bottom in each; full-width zones (headings) where they fall
	function sort() {
		const wide = zones.filter((z) => z.w >= 60).sort((a, b) => a.y - b.y);
		const narrow = zones.filter((z) => z.w < 60);
		const edges = [0, ...wide.map((z) => z.y), 101];
		const out = [];
		for (let i = 0; i < edges.length - 1; i++) {
			out.push(...wide.filter((z) => z.y === edges[i] && !out.includes(z)));
			out.push(...narrow.filter((z) => z.y >= edges[i] && z.y < edges[i + 1]).sort((a, b) => Math.round(a.x / 5) - Math.round(b.x / 5) || a.y - b.y));
		}
		zones = out.concat(zones.filter((z) => !out.includes(z)));
		drawZones();
	}

	async function ocr() {
		const msg = $("#rd-proof-msg");
		msg.textContent = "Reading the page…";
		$("#rd-zone-ocr").disabled = true;
		try {
			const { key } = await call(
				"reocr",
				"ocr_page",
				{ item_id: itemId, leaf: page.leaf, zones, languages: JSON.stringify(runLangs) },
				true
			);
			let r;
			for (let i = 0; i < 120; i++) {
				await new Promise((res) => setTimeout(res, i < 5 ? 1000 : 2000));
				r = await call("reocr", "ocr_result", { key });
				if (r.status === "done" || r.status === "failed" || r.status === "gone") break;
			}
			if (!r || r.status !== "done") throw new Error((r && r.error) || "The OCR didn't finish. Try again.");
			const edited = $("#rd-proof-text").value !== original;
			if (!edited || confirm("Replace the text in the editor with the new OCR? Your changes there are lost.")) {
				$("#rd-proof-text").value = r.text;
				original = r.text;
			}
			msg.textContent = `Read with ${r.engine}: quality ${r.quality ?? "–"}. Check it against the image, then save.`;
		} catch (e) {
			msg.textContent = e.message;
		} finally {
			$("#rd-zone-ocr").disabled = false;
		}
	}

	async function save(validate) {
		const msg = $("#rd-proof-msg");
		try {
			const r = await call(
				"pagetext",
				"save_page",
				{ item_id: itemId, leaf: page.leaf, text: $("#rd-proof-text").value, zones, page_label: page.label || "", validate: validate ? 1 : 0 },
				true
			);
			msg.textContent = r.status === "Validated" ? "Validated. Thank you." : "Saved as proofread. Thank you.";
			window.rdTrack && rdTrack("Page proofread", { status: r.status });
			const leaf = page.leaf;
			close();
			window.RDPages && RDPages.go(leaf);
		} catch (e) {
			msg.textContent = e.message;
		}
	}

	function init() {
		if (!$("#rd-pages")) return;
		itemId = $("#rd-item").dataset.item;
		document.addEventListener("rd-page-shown", (e) => {
			page = e.detail;
			$("#rd-pages-status").textContent = statusText(page);
			$("#rd-pages-status").dataset.status = page.text_status || "";
			$("#rd-proof-btn").hidden = !page.can_proofread;
			if (on) open();
		});
		$("#rd-proof-btn").addEventListener("click", () => (on ? close() : open()));
		$("#rd-pages").addEventListener("click", (e) => {
			const t = e.target;
			if (t.closest("#rd-zone-draw")) draw();
			if (t.closest("#rd-zone-sort")) sort();
			if (t.closest("#rd-zone-clear")) (zones = []), drawZones();
			if (t.closest("#rd-zone-ocr")) ocr();
			if (t.closest("#rd-proof-save")) save(false);
			if (t.closest("#rd-proof-validate")) save(true);
			if (t.closest("#rd-proof-cancel")) close();
			const up = t.closest("[data-up]"), down = t.closest("[data-down]"), del = t.closest("[data-del]");
			if (up) {
				const i = +up.dataset.up;
				[zones[i - 1], zones[i]] = [zones[i], zones[i - 1]];
				drawZones();
			}
			if (down) {
				const i = +down.dataset.down;
				[zones[i + 1], zones[i]] = [zones[i], zones[i + 1]];
				drawZones();
			}
			if (del) zones.splice(+del.dataset.del, 1), drawZones();
			const rs = t.closest("[data-restore]");
			if (rs && confirm("Make this earlier version the page's text again?")) {
				call("pagetext", "restore", { name: rs.dataset.restore }, true).then(() => {
					const leaf = page.leaf;
					close();
					RDPages.go(leaf);
				});
			}
		});
		$("#rd-pages").addEventListener("change", (e) => {
			const k = e.target.closest("[data-kind]");
			if (k) (zones[+k.dataset.kind].kind = k.value), drawZones();
			const zl = e.target.closest("[data-zlang]");
			if (zl) {
				const z = zones[+zl.dataset.zlang];
				if (zl.value) z.langs = [zl.value];
				else delete z.langs;
			}
			const lg = e.target.closest("[data-lang]");
			if (lg) {
				const m = lg.dataset.lang;
				// keep the book's order (its main language first), then what was added
				runLangs = lg.checked ? [...runLangs, m] : runLangs.filter((x) => x !== m);
				if (!runLangs.length) (runLangs = [m]), (lg.checked = true);
			}
			if (e.target.id === "rd-zone-preset" && e.target.value) {
				zones = JSON.parse(JSON.stringify(presets[e.target.value] || []));
				e.target.value = "";
				drawZones();
			}
		});
	}

	document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", init) : init();
})();
