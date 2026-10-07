// Research Desk proofreading in the page reader (Page & text → Proofread), for proofreaders and
// staff: correct the page text beside its image, and read parts of the page again with OCR.
//
// Zones: draw as many boxes on the page image as the page has parts (columns, a heading, side
// notes), in reading order; each is read on its own and their texts are joined in that order,
// so columns don't run into each other. A zone can be "skip" (a picture, a stamp). Presets give
// the common layouts in one click.
(function () {
	const __ = window.rdT || ((s) => s);
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
			let msg = __("Something went wrong.");
			try {
				msg = JSON.parse(JSON.parse(body._server_messages)[0]).message;
			} catch (e) {}
			throw new Error(msg);
		}
		return body.message;
	}

	function statusText(d) {
		if (d.text_status === "Validated") return __("Validated by {0} · proofread by {1}", [d.validated_by, d.proofread_by]);
		if (d.text_status === "Proofread") return __("Proofread by {0}", [d.proofread_by]);
		if (d.text_status === "Machine") return __("Read again by OCR, not proofread yet");
		return d.text ? __("OCR from archive.org, not proofread yet") : "";
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
						(z, i) => `<li data-z="${i}" tabindex="0" aria-label="${esc(__("Zone {0}: {1}% from the left, {2}% from the top, {3}% wide, {4}% high. Arrow keys move it; Shift and the arrow keys change its size.", [i + 1, Math.round(z.x), Math.round(z.y), Math.round(z.w), Math.round(z.h)]))}"><b>${z.kind === "skip" ? "×" : i + 1}</b>
				<select data-kind="${i}" aria-label="${esc(__("Read or skip zone {0}", [i + 1]))}"><option value="text" ${z.kind === "text" ? "selected" : ""}>${__("read")}</option><option value="skip" ${z.kind === "skip" ? "selected" : ""}>${__("skip")}</option></select>
				<input data-zlang="${i}" list="rd-proof-langlist" size="8" autocomplete="off" spellcheck="false" value="${esc((z.langs || [])[0] || "")}" placeholder="${esc(__("page's languages"))}" aria-label="${esc(__("Language of zone {0}: a code such as kan, or part of the name; empty for the page's languages", [i + 1]))}" title="${esc(__("This part's language, when it differs from the page's"))}" ${z.kind === "skip" ? "hidden" : ""}>
				<button type="button" data-up="${i}" title="${__("Earlier")}" ${i ? "" : "disabled"}>↑</button><button type="button" data-down="${i}" title="${__("Later")}" ${i < zones.length - 1 ? "" : "disabled"}>↓</button>
				<button type="button" data-del="${i}" title="${__("Remove")}">✕</button></li>`
					)
					.join("")
			: `<li class="rd-muted">${__("No zones: the whole page is read as one block. Draw a box for each column or part.")}</li>`;
	}

	// "Read with": the languages Tesseract reads this page in (the main one first, English added).
	// A short row of chips and a box to type a code or a bit of a name into, not a list of every
	// language installed: the suggestions come as you type.
	function drawLangs() {
		const box = $("#rd-proof-langs");
		if (!box) return;
		const L = window.rdLang;
		if (L) L.datalist("rd-proof-langlist", Object.fromEntries(Object.entries(langs.available).map(([m, n]) => [m, n])));
		if (!Object.keys(langs.available).length) return (box.innerHTML = "");
		box.innerHTML = `<span class="rd-muted" id="rd-proof-langs-l">${__("Read with:")}</span>
			<ul class="rd-chips" aria-labelledby="rd-proof-langs-l">${runLangs
				.map((m) => `<li><button type="button" class="rd-chip" data-lang-remove="${esc(m)}" aria-label="${esc(__("Remove {0}", [langs.available[m] || m]))}">${esc(langs.available[m] || m)} <span aria-hidden="true">✕</span></button></li>`)
				.join("")}</ul>
			<input type="text" size="12" list="rd-proof-langlist" id="rd-proof-lang-add" autocomplete="off" spellcheck="false" placeholder="${esc(__("add: kan, eng…"))}" aria-label="${esc(__("Add a language: type a code such as kan, or part of its name"))}">`;
	}

	// a language typed into a box → its code; says so when none or several fit
	function pickLang(input) {
		const r = window.rdLang ? window.rdLang.resolve(input.value, langs.available) : { code: input.value.trim(), matches: [] };
		if (r.code === null || (r.code && !langs.available[r.code])) {
			$("#rd-proof-msg").textContent = r.matches && r.matches.length > 1 ? __("Several languages fit: keep typing the code.") : __("No language matches “{0}”.", [input.value]);
			return null;
		}
		$("#rd-proof-msg").textContent = "";
		return r.code;
	}

	function editor() {
		const box = document.createElement("div");
		box.id = "rd-proof";
		box.className = "rd-proof";
		box.innerHTML = `
			<div class="rd-proof__zones">
				<button class="rd-btn" type="button" id="rd-zone-draw">${__("Draw a zone")}</button>
				<button class="rd-btn" type="button" id="rd-zone-add" title="${__("A zone in the middle of the page, to move and size with the arrow keys")}">${__("Add a zone")}</button>
				<select id="rd-zone-preset" aria-label="${__("Layout")}"><option value="">${__("Layout…")}</option>${Object.keys(presets).map((k) => `<option>${esc(k)}</option>`).join("")}</select>
				<button class="rd-btn" type="button" id="rd-zone-sort" title="${__("Columns left to right, headings where they fall")}">${__("Sort")}</button>
				<button class="rd-btn" type="button" id="rd-zone-clear">${__("Clear")}</button>
				<button class="rd-btn rd-btn--primary" type="button" id="rd-zone-ocr">${__("OCR the zones")}</button>
				<span class="rd-muted" id="rd-proof-msg" role="status"></span>
				<div class="rd-proof__langs" id="rd-proof-langs"></div>
				<ol class="rd-zone-list" id="rd-zone-list"></ol>
			</div>
			<textarea id="rd-proof-text" aria-label="${__("The page's text, to correct")}" spellcheck="false" lang="${esc($("#rd-pages-text").getAttribute("lang") || "")}"></textarea>
			<div class="rd-proof__actions">
				<button class="rd-btn rd-btn--primary" type="button" id="rd-proof-save">${__("Save as proofread")}</button>
				<button class="rd-btn" type="button" id="rd-proof-validate" hidden>${__("Validate: it's right")}</button>
				<button class="rd-btn" type="button" id="rd-proof-cancel">${__("Close")}</button>
				<span class="rd-muted" id="rd-proof-who"></span>
			</div>
			<details class="rd-proof__history"><summary>${__("History of this page")}</summary><ol id="rd-proof-history"></ol></details>`;
		return box;
	}

	async function open() {
		on = true;
		$("#rd-proof-btn").textContent = __("Close proofreading");
		$("#rd-pages-text").hidden = true;
		if (!$("#rd-proof")) {
			$("#rd-pages-text").after(editor()); // in the text's place, beside the image
			if (window.rdIme) window.rdIme.attach($("#rd-proof-text")); // type in the book's language on any keyboard
		}
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
		$("#rd-zone-preset").innerHTML = `<option value="">${__("Layout…")}</option>${Object.keys(presets).map((k) => `<option>${esc(k)}</option>`).join("")}`;
		$("#rd-proof-validate").hidden = !(cur && cur.status === "Proofread" && cur.proofread_by !== me);
		$("#rd-proof-who").textContent = statusText(page);
		$("#rd-proof-history").innerHTML = versions.length
			? versions
					.map(
						(v) => `<li>${esc(v.creation)} · ${esc(v.status)}${v.proofread_by_name ? ` ${__("by {0}", [esc(v.proofread_by_name)])}` : ""}${v.validated_by_name ? `, ${__("validated by {0}", [esc(v.validated_by_name)])}` : ""}${v.engine ? ` · ${esc(v.engine)}` : ""} · ${__("quality {0}", [v.quality])}${
							v.is_current ? ` · <b>${__("current")}</b>` : ` <button type="button" class="rd-linkish" data-restore="${esc(v.name)}">${__("Make current")}</button>`
						}</li>`
					)
					.join("")
			: `<li class="rd-muted">${__("archive.org's OCR only, so far.")}</li>`;
		drawZones();
	}

	function close() {
		on = false;
		$("#rd-proof-btn").textContent = __("Proofread");
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
		$("#rd-proof-msg").textContent = __("Drag a box over one part of the page.");
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
			$("#rd-proof-msg").textContent = __("Draw another, or OCR the zones.");
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
		msg.textContent = __("Reading the page…");
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
			if (!r || r.status !== "done") throw new Error((r && r.error) || __("The OCR didn't finish. Try again."));
			const edited = $("#rd-proof-text").value !== original;
			if (!edited || confirm(__("Replace the text in the editor with the new OCR? Your changes there are lost."))) {
				$("#rd-proof-text").value = r.text;
				original = r.text;
			}
			msg.textContent = __("Read with {0}: quality {1}. Check it against the image, then save.", [r.engine, r.quality ?? "–"]);
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
			msg.textContent = r.status === "Validated" ? __("Validated. Thank you.") : __("Saved as proofread. Thank you.");
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
			if (t.closest("#rd-zone-add")) {
				zones.push({ x: 30, y: 30, w: 40, h: 30, kind: "text" });
				drawZones();
				const li = $(`#rd-zone-list [data-z="${zones.length - 1}"]`);
				if (li) li.focus();
			}
			const chip = t.closest("[data-lang-remove]");
			if (chip && runLangs.length > 1) {
				runLangs = runLangs.filter((x) => x !== chip.dataset.langRemove);
				drawLangs();
				const again = $("#rd-proof-lang-add");
				if (again) again.focus();
			} else if (chip) $("#rd-proof-msg").textContent = __("Keep at least one language.");
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
			if (rs && confirm(__("Make this earlier version the page's text again?"))) {
				call("pagetext", "restore", { name: rs.dataset.restore }, true).then(() => {
					const leaf = page.leaf;
					close();
					RDPages.go(leaf);
				});
			}
		});
		// zones from the keyboard: on a zone in the list, arrows move it by 1% of the page and
		// Shift with the arrows changes its size (the same rectangle the mouse draws)
		$("#rd-pages").addEventListener("keydown", (e) => {
			const li = e.target.closest && e.target.closest("#rd-zone-list [data-z]");
			const step = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[e.key];
			if (!li || e.target !== li || !step) return;
			e.preventDefault();
			const i = +li.dataset.z, z = zones[i];
			const clip = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
			if (e.shiftKey) {
				z.w = clip(z.w + step[0], 1, 100 - z.x);
				z.h = clip(z.h + step[1], 1, 100 - z.y);
			} else {
				z.x = clip(z.x + step[0], 0, 100 - z.w);
				z.y = clip(z.y + step[1], 0, 100 - z.h);
			}
			drawZones();
			const again = $(`#rd-zone-list [data-z="${i}"]`);
			if (again) again.focus();
		});
		$("#rd-pages").addEventListener("change", (e) => {
			const k = e.target.closest("[data-kind]");
			if (k) (zones[+k.dataset.kind].kind = k.value), drawZones();
			const zl = e.target.closest("[data-zlang]");
			if (zl) {
				const z = zones[+zl.dataset.zlang];
				const m = pickLang(zl);
				if (m) (z.langs = [m]), (zl.value = m);
				else if (m === "") delete z.langs;
				else zl.value = (z.langs || [])[0] || "";
			}
			if (e.target.id === "rd-proof-lang-add") {
				const m = pickLang(e.target);
				if (m && !runLangs.includes(m)) runLangs = [...runLangs, m];
				if (m !== null) {
					drawLangs();
					const again = $("#rd-proof-lang-add");
					if (again) again.focus();
				}
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
