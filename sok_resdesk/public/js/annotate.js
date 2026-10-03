// Research Desk notes in the page reader (Page & text): select words of the page text, or mark a
// region of the page image, to highlight, comment, tag, ask a question, link or report an OCR
// error. Private, shared with a research group, or public after review (annotations.py).
(function () {
	const $ = (sel, root) => (root || document).querySelector(sel);
	const esc = (s) =>
		String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
	const KINDS = ["Highlight", "Comment", "Tag", "Question", "Link", "OCR error"];
	const NEEDS = { Comment: "body", Question: "body", Tag: "tags", Link: "link" };

	let itemId, page = null, notes = [], me = { logged_in: false, can_annotate: false, groups: [] };
	let pending = null; // what the form is about: {start, end, exact} or {region}
	let editing = null; // the note being edited

	function csrf() {
		return (window.frappe && frappe.csrf_token) || (document.cookie.match(/csrf_token=([^;]+)/) || [])[1] || "";
	}

	async function call(method, args, post) {
		const url = `/api/method/sok_resdesk.annotations.${method}`;
		const opts = post
			? { method: "POST", headers: { "Content-Type": "application/json", Accept: "application/json", "X-Frappe-CSRF-Token": csrf() }, body: JSON.stringify(args) }
			: { headers: { Accept: "application/json" } };
		const r = await fetch(post ? url : `${url}?${new URLSearchParams(args)}`, opts);
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

	function showing() {
		return $("#rd-notes-show").checked;
	}

	// -- drawing the notes -------------------------------------------------------------------------

	function ranges(text, q) {
		const out = [];
		if (showing()) {
			for (const n of notes) {
				if (n.exact && !n.detached && n.pos_end > n.pos_start) out.push({ s: n.pos_start, e: n.pos_end, note: n });
			}
		}
		for (const w of (q || "").split(/\s+/).map((x) => x.replace(/[^\p{L}\p{M}\p{N}]/gu, "")).filter((x) => x.length > 1)) {
			const re = new RegExp(w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "giu");
			let m;
			while ((m = re.exec(text))) out.push({ s: m.index, e: m.index + m[0].length, q: true });
		}
		return out;
	}

	// the page text with its notes and search words marked; textContent stays exactly the page
	// text, so character positions of a selection are positions in the page text
	function renderText() {
		const box = $("#rd-pages-text");
		if (!page || !page.text) return;
		const text = page.text;
		const rs = ranges(text, page.q);
		const cuts = new Set([0, text.length]);
		rs.forEach((r) => (cuts.add(r.s), cuts.add(r.e)));
		const points = [...cuts].sort((a, b) => a - b);
		let html = "";
		for (let i = 0; i < points.length - 1; i++) {
			const a = points[i], b = points[i + 1];
			const over = rs.filter((r) => r.s <= a && r.e >= b);
			let seg = esc(text.slice(a, b));
			if (over.some((r) => r.q)) seg = `<mark>${seg}</mark>`;
			const ns = over.filter((r) => r.note).map((r) => r.note);
			if (ns.length) {
				const kind = ns[ns.length - 1].kind.replace(/\s/g, "-").toLowerCase();
				seg = `<span class="rd-hl rd-hl--${kind}" data-notes="${ns.map((n) => n.name).join(" ")}" title="${esc(ns.map((n) => n.body || n.kind).join(" · "))}">${seg}</span>`;
			}
			html += seg;
		}
		box.innerHTML = html;
	}

	function renderRegions() {
		const fig = $("#rd-pages-image");
		fig.querySelectorAll(".rd-region").forEach((r) => r.remove());
		if (!showing() || !$("img", fig)) return;
		fig.classList.add("rd-has-regions");
		for (const n of notes.filter((x) => x.region)) {
			const m = /xywh=percent:([\d.]+),([\d.]+),([\d.]+),([\d.]+)/.exec(n.region);
			if (!m) continue;
			const div = document.createElement("div");
			div.className = `rd-region rd-region--${n.kind.replace(/\s/g, "-").toLowerCase()}`;
			div.dataset.notes = n.name;
			div.title = n.body || n.kind;
			Object.assign(div.style, { left: `${m[1]}%`, top: `${m[2]}%`, width: `${m[3]}%`, height: `${m[4]}%` });
			imageFrame().appendChild(div);
		}
	}

	// the image and its regions share one box, so percent positions line up with the picture
	function imageFrame() {
		const fig = $("#rd-pages-image");
		let frame = $(".rd-image-frame", fig);
		const img = $("img", fig);
		if (!frame && img) {
			frame = document.createElement("div");
			frame.className = "rd-image-frame";
			img.replaceWith(frame);
			frame.appendChild(img);
		}
		return frame;
	}

	function who(n) {
		if (n.visibility === "Public") return n.review_status === "Pending" ? "Public, waiting for review" : "Public";
		if (n.visibility === "Group") {
			const g = me.groups.find((x) => x.name === n.research_group);
			return `Group: ${g ? g.title : n.research_group}`;
		}
		return "Only you";
	}

	function renderList() {
		const box = $("#rd-notes");
		if (!pending && !editing && (!showing() || !notes.length)) {
			box.innerHTML = "";
			return;
		}
		const items = notes
			.map(
				(n) => `<li class="rd-note${n.detached ? " is-detached" : ""}" data-note="${esc(n.name)}">
				<div class="rd-note__head"><span class="rd-note__kind rd-note__kind--${esc(n.kind.replace(/\s/g, "-").toLowerCase())}">${esc(n.kind)}</span>
					<span class="rd-muted">${esc(n.mine ? who(n) : `${n.author} · ${who(n)}`)}</span>
					${n.mine || me.manager ? `<span class="rd-note__acts"><button type="button" class="rd-linkish" data-edit="${esc(n.name)}">Edit</button> <button type="button" class="rd-linkish" data-remove="${esc(n.name)}">Delete</button></span>` : ""}</div>
				${n.exact ? `<blockquote>${esc(n.exact)}</blockquote>` : n.region ? `<p class="rd-muted">A region of the page image</p>` : ""}
				${n.detached ? `<p class="rd-muted">The words this note was on are no longer in the page text (it was corrected).</p>` : ""}
				${n.body ? `<p>${esc(n.body)}</p>` : ""}
				${n.tags && n.tags.length ? `<p>${n.tags.map((t) => `<span class="rd-chip">${esc(t)}</span>`).join(" ")}</p>` : ""}
				${n.link ? `<p><a href="${esc(n.link)}" target="_blank" rel="noopener nofollow">${esc(n.link)}</a></p>` : ""}
			</li>`
			)
			.join("");
		box.innerHTML = `${pending || editing ? form() : ""}${notes.length ? `<h3>Notes on this page (${notes.length})</h3><ul class="rd-note-list">${items}</ul>` : ""}`;
		if (pending || editing) {
			const f = $("#rd-note-form");
			setFields(f);
			const first = $("textarea, input[type=text]", f);
			if (first) first.focus();
		}
	}

	// -- the form ---------------------------------------------------------------------------------

	function form() {
		const n = editing || {};
		const kind = n.kind || (pending && pending.kind) || "Comment";
		const groups = me.groups.map((g) => `<option value="${esc(g.name)}" ${n.research_group === g.name ? "selected" : ""}>${esc(g.title)}</option>`).join("");
		const about = editing ? (n.exact ? `“${esc(n.exact)}”` : "A region of the page image") : pending.region ? "A region of the page image" : `“${esc(pending.exact)}”`;
		return `<form class="rd-note-form" id="rd-note-form">
			<p class="rd-note-form__about">${about}</p>
			<div class="rd-tabs" role="radiogroup">${KINDS.map((k) => `<label class="rd-tab${k === kind ? " is-active" : ""}"><input type="radio" name="kind" value="${k}" ${k === kind ? "checked" : ""}> ${k}</label>`).join("")}</div>
			<label data-for="body">Note<textarea name="body" rows="3">${esc(n.body || "")}</textarea></label>
			<label data-for="tags">Tags <span class="rd-muted">(commas between them)</span><input type="text" name="tags" value="${esc((n.tags || []).join(", "))}"></label>
			<label data-for="link">Link <span class="rd-muted">(e.g. a Wikidata page)</span><input type="url" name="link" placeholder="https://www.wikidata.org/wiki/Q…" value="${esc(n.link || "")}"></label>
			<label>Who can see it <select name="visibility">
				<option value="Private" ${n.visibility === "Private" || !n.visibility ? "selected" : ""}>Only me</option>
				${groups ? `<option value="Group" ${n.visibility === "Group" ? "selected" : ""}>A research group</option>` : ""}
				<option value="Public" ${n.visibility === "Public" ? "selected" : ""}>Everyone (after the library reviews it)</option>
			</select></label>
			${groups ? `<label data-for="group">Group <select name="research_group">${groups}</select></label>` : ""}
			<p class="rd-note-form__error" id="rd-note-error"></p>
			<div class="rd-actions"><button class="rd-btn rd-btn--primary" type="submit">Save</button> <button class="rd-btn" type="button" data-cancel>Cancel</button></div>
		</form>`;
	}

	function setFields(f) {
		const kind = $("input[name=kind]:checked", f).value;
		f.querySelectorAll(".rd-tab").forEach((t) => t.classList.toggle("is-active", $("input", t).checked));
		const show = { body: kind !== "Tag" && kind !== "Link" ? true : false, tags: kind === "Tag", link: kind === "Link" };
		if (kind === "Highlight") show.body = true; // a highlight may carry a short note
		Object.entries(show).forEach(([k, on]) => ($(`[data-for=${k}]`, f) || {}).hidden = !on);
		const vis = $("select[name=visibility]", f).value;
		const g = $("[data-for=group]", f);
		if (g) g.hidden = vis !== "Group";
	}

	async function save(f) {
		const data = Object.fromEntries(new FormData(f).entries());
		const need = NEEDS[data.kind];
		if (need && !String(data[need] || "").trim() && $("#rd-note-error")) {
			$("#rd-note-error").textContent = { body: "Write the note first.", tags: "Give at least one tag.", link: "Give the link." }[need];
			return;
		}
		if (data.visibility !== "Group") delete data.research_group;
		try {
			if (editing) {
				const updated = await call("edit", { name: editing.name, ...data }, true);
				Object.assign(editing, updated);
			} else {
				const target = pending.region ? { region: pending.region } : { start: pending.start, end: pending.end };
				await call("add", { item_id: itemId, leaf: page.leaf, page_label: page.label || "", ...data, ...target }, true);
			}
		} catch (e) {
			const err = $("#rd-note-error");
			if (err) err.textContent = e.message;
			else alert(e.message);
			return;
		}
		pending = editing = null;
		getSelection().removeAllRanges();
		load();
	}

	// -- selecting words and marking regions ------------------------------------------------------

	function offsetIn(box, node, offset) {
		const walker = document.createTreeWalker(box, NodeFilter.SHOW_TEXT);
		let pos = 0, n;
		while ((n = walker.nextNode())) {
			if (n === node) return pos + offset;
			pos += n.nodeValue.length;
		}
		return null;
	}

	function selectedRange() {
		const box = $("#rd-pages-text");
		const sel = getSelection();
		if (!sel.rangeCount || sel.isCollapsed) return null;
		const r = sel.getRangeAt(0);
		if (!box.contains(r.startContainer) || !box.contains(r.endContainer)) return null;
		let start = offsetIn(box, r.startContainer, r.startOffset);
		let end = offsetIn(box, r.endContainer, r.endOffset);
		if (start == null || end == null) return null;
		const text = page.text;
		while (start < end && /\s/.test(text[start])) start++; // trim the selection to its words
		while (end > start && /\s/.test(text[end - 1])) end--;
		return end > start ? { start, end, exact: text.slice(start, end), rect: r.getBoundingClientRect() } : null;
	}

	function toolbar(sel) {
		hideToolbar();
		const bar = document.createElement("div");
		bar.className = "rd-sel-bar";
		bar.id = "rd-sel-bar";
		bar.innerHTML = me.can_annotate
			? KINDS.map((k) => `<button type="button" data-new="${k}">${k}</button>`).join("")
			: `<a href="${esc(loginUrl())}">Log in to add a note</a>`;
		document.body.appendChild(bar);
		const top = window.scrollY + sel.rect.top - bar.offsetHeight - 8;
		const left = Math.max(8, Math.min(window.scrollX + sel.rect.left, window.scrollX + document.documentElement.clientWidth - bar.offsetWidth - 8));
		Object.assign(bar.style, { top: `${Math.max(window.scrollY + 8, top)}px`, left: `${left}px` });
		bar.addEventListener("mousedown", (e) => e.preventDefault()); // keep the selection
		bar.addEventListener("click", (e) => {
			const b = e.target.closest("[data-new]");
			if (!b) return;
			pending = { start: sel.start, end: sel.end, exact: sel.exact, kind: b.dataset.new };
			editing = null;
			hideToolbar();
			if (b.dataset.new === "Highlight") {
				// a plain highlight needs nothing more: saved at once, private
				const f = document.createElement("form");
				f.innerHTML = `<input name="kind" value="Highlight"><input name="visibility" value="Private"><input name="body" value="">`;
				return save(f);
			}
			renderList();
			$("#rd-notes").scrollIntoView({ block: "nearest", behavior: "smooth" });
		});
	}

	function hideToolbar() {
		const bar = $("#rd-sel-bar");
		if (bar) bar.remove();
	}

	function loginUrl() {
		return `${$("#rd-notes-bar").dataset.login}?redirect-to=${encodeURIComponent(location.pathname + location.search)}`;
	}

	function startRegion() {
		const fig = $("#rd-pages-image");
		const frame = imageFrame();
		if (!frame) return;
		fig.classList.add("is-marking");
		$("#rd-notes-hint").textContent = "Drag a box over the part of the page image.";
		let from = null, box = null;
		const at = (e) => {
			const r = frame.getBoundingClientRect();
			const p = e.touches ? e.touches[0] : e;
			return { x: ((p.clientX - r.left) / r.width) * 100, y: ((p.clientY - r.top) / r.height) * 100 };
		};
		const down = (e) => {
			e.preventDefault();
			from = at(e);
			box = document.createElement("div");
			box.className = "rd-region rd-region--drawing";
			frame.appendChild(box);
		};
		const move = (e) => {
			if (!from) return;
			const p = at(e);
			Object.assign(box.style, {
				left: `${Math.min(from.x, p.x)}%`,
				top: `${Math.min(from.y, p.y)}%`,
				width: `${Math.abs(p.x - from.x)}%`,
				height: `${Math.abs(p.y - from.y)}%`,
			});
		};
		const up = (e) => {
			if (!from) return;
			const p = at(e.changedTouches ? e.changedTouches[0] : e);
			const clip = (v) => Math.min(100, Math.max(0, v));
			const x = clip(Math.min(from.x, p.x)), y = clip(Math.min(from.y, p.y));
			const w = clip(Math.max(from.x, p.x)) - x, h = clip(Math.max(from.y, p.y)) - y;
			stop();
			if (w < 1 || h < 1) return;
			pending = { region: `${x.toFixed(2)},${y.toFixed(2)},${w.toFixed(2)},${h.toFixed(2)}`, kind: "Comment" };
			editing = null;
			renderList();
			$("#rd-notes").scrollIntoView({ block: "nearest", behavior: "smooth" });
		};
		const stop = () => {
			fig.classList.remove("is-marking");
			$("#rd-notes-hint").textContent = "";
			if (box) box.remove();
			frame.removeEventListener("mousedown", down);
			window.removeEventListener("mousemove", move);
			window.removeEventListener("mouseup", up);
			frame.removeEventListener("touchstart", down);
			window.removeEventListener("touchmove", move);
			window.removeEventListener("touchend", up);
		};
		frame.addEventListener("mousedown", down);
		window.addEventListener("mousemove", move);
		window.addEventListener("mouseup", up);
		frame.addEventListener("touchstart", down, { passive: false });
		window.addEventListener("touchmove", move);
		window.addEventListener("touchend", up);
	}

	// -- loading ----------------------------------------------------------------------------------

	async function load() {
		if (!page) return;
		const asked = page; // the page may change while its notes are on their way
		let d;
		try {
			d = await call("page_notes", { item_id: itemId, leaf: asked.leaf });
		} catch (e) {
			return;
		}
		if (!d || page !== asked) return;
		notes = d.notes || [];
		me = d.me || me;
		$("#rd-notes-region").hidden = !(me.can_annotate && page.image);
		$("#rd-notes-mine").hidden = !me.logged_in;
		$("#rd-notes-hint").innerHTML = !me.logged_in && page.text ? `<a href="${esc(loginUrl())}">Log in</a> to add notes.` : "";
		renderText();
		renderRegions();
		renderList();
	}

	function flash(name) {
		document.querySelectorAll(`[data-notes~="${CSS.escape(name)}"]`).forEach((el) => {
			el.scrollIntoView({ block: "center", behavior: "smooth" });
			el.classList.add("is-flash");
			setTimeout(() => el.classList.remove("is-flash"), 1200);
		});
	}

	function init() {
		if (!$("#rd-pages")) return;
		itemId = $("#rd-item").dataset.item;
		document.addEventListener("rd-page-shown", (e) => {
			page = e.detail;
			notes = [];
			pending = editing = null;
			hideToolbar();
			renderList();
			load();
		});
		$("#rd-pages-text").addEventListener("mouseup", () => setTimeout(() => {
			const sel = page && page.text ? selectedRange() : null;
			sel ? toolbar(sel) : hideToolbar();
		}, 0));
		document.addEventListener("mousedown", (e) => {
			if (!e.target.closest("#rd-sel-bar") && !e.target.closest("#rd-pages-text")) hideToolbar();
		});
		$("#rd-notes-show").addEventListener("change", () => (renderText(), renderRegions(), renderList()));
		$("#rd-notes-region").addEventListener("click", startRegion);
		$("#rd-notes").addEventListener("change", (e) => {
			const f = e.target.closest("#rd-note-form");
			if (f) setFields(f);
		});
		$("#rd-notes").addEventListener("submit", (e) => {
			e.preventDefault();
			save(e.target);
		});
		$("#rd-notes").addEventListener("click", async (e) => {
			if (e.target.closest("[data-cancel]")) {
				pending = editing = null;
				renderList();
			}
			const ed = e.target.closest("[data-edit]");
			if (ed) {
				editing = notes.find((n) => n.name === ed.dataset.edit);
				pending = null;
				renderList();
			}
			const rm = e.target.closest("[data-remove]");
			if (rm && confirm("Delete this note?")) {
				await call("remove", { name: rm.dataset.remove }, true);
				load();
			}
			const li = e.target.closest("[data-note]");
			if (li && !e.target.closest("button, a")) flash(li.dataset.note);
		});
		// a click on a highlight or region shows its note in the list
		const toList = (e) => {
			const el = e.target.closest("[data-notes]");
			if (!el || getSelection().toString()) return;
			const li = $(`[data-note="${CSS.escape(el.dataset.notes.split(" ")[0])}"]`);
			if (li) {
				li.scrollIntoView({ block: "nearest", behavior: "smooth" });
				li.classList.add("is-flash");
				setTimeout(() => li.classList.remove("is-flash"), 1200);
			}
		};
		$("#rd-pages-text").addEventListener("click", toList);
		$("#rd-pages-image").addEventListener("click", toList);
	}

	document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", init) : init();
})();
