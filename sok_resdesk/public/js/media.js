// A recording's page: the player and its transcript, in step. The transcript follows the recording
// (and can be turned off), a click on a segment plays from there, ?page=<segment> opens at it, and
// proofreaders correct a segment in place. Transcript segments are the book's "pages"
// (api.transcript); corrections are saved as page text (pagetext.save_page).
(function () {
	const __ = window.rdT || ((s) => s);
	const root = document.getElementById("rd-media");
	if (!root) return;
	const player = document.getElementById("rd-player");
	const list = document.getElementById("rd-media-transcript");
	const status = document.getElementById("rd-media-status");
	const follow = document.getElementById("rd-media-follow");
	const itemId = root.dataset.item;
	const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
	const csrf = () => (window.frappe && frappe.csrf_token) || "";
	const clock = (s) => { s = Math.max(0, Math.floor(s)); const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60); return (h ? h + ":" + String(m).padStart(2, "0") : m) + ":" + String(s % 60).padStart(2, "0"); };
	let segs = [], following = true, current = -1, canProof = false;

	for (const id of ["rd-media-length", "rd-meta-length"]) {
		const len = document.getElementById(id);
		if (len) len.textContent = clock(Number(len.dataset.seconds));
	}

	async function post(method, args) {
		const r = await fetch(`/api/method/${method}`, { method: "POST", headers: { "Content-Type": "application/json", Accept: "application/json", "X-Frappe-CSRF-Token": csrf() }, body: JSON.stringify(args) });
		const j = await r.json();
		if (!r.ok) { let m = j.exception || "Error"; try { m = JSON.parse(JSON.parse(j._server_messages)[0]).message; } catch (e) {} throw new Error(String(m).replace(/<[^>]+>/g, "")); }
		return j.message;
	}

	function render() {
		if (!segs.length) {
			list.innerHTML = `<li class="rd-muted">${esc(__("This recording has no transcript yet."))}</li>`;
			return;
		}
		list.innerHTML = segs.map((s, i) => `<li data-i="${i}" class="rd-seg${s.text ? "" : " is-empty"}">
			<button type="button" class="rd-seg__time" data-seek="${i}" aria-label="${esc(__("Play from {0}", [s.label]))}">${esc(s.label)}</button>
			<span class="rd-seg__text">${s.text ? esc(s.text) : `<span class="rd-muted">${esc(__("Not transcribed yet."))}</span>`}</span>
			${canProof ? `<button type="button" class="rd-btn rd-btn--plain" data-edit="${i}">${esc(__("Edit"))}</button>` : ""}</li>`).join("");
	}

	function seek(i, play) {
		const s = segs[i];
		if (!s || !player) return;
		player.currentTime = s.start;
		if (play) player.play().catch(() => {});
	}

	function mark(t) {
		let i = segs.findIndex((s) => t >= s.start && t < s.end);
		if (i < 0 || i === current) return;
		const old = list.querySelector(".is-now");
		if (old) { old.classList.remove("is-now"); old.removeAttribute("aria-current"); }
		const li = list.querySelector(`[data-i="${i}"]`);
		if (li) {
			li.classList.add("is-now");
			li.setAttribute("aria-current", "true");
			if (following) li.scrollIntoView({ block: "nearest", behavior: "smooth" });
		}
		current = i;
	}

	function edit(i) {
		const li = list.querySelector(`[data-i="${i}"]`);
		const s = segs[i];
		li.innerHTML = `<label class="rd-seg__label">${esc(s.label)}<textarea rows="3" style="width:100%">${esc(s.text)}</textarea></label>
			<button type="button" class="rd-btn rd-btn--primary" data-save="${i}">${esc(__("Save"))}</button>
			<button type="button" class="rd-btn" data-cancel="${i}">${esc(__("Cancel"))}</button>`;
		li.querySelector("textarea").focus();
	}

	list.addEventListener("click", async (e) => {
		const b = e.target.closest("button");
		if (!b) return;
		if (b.dataset.seek !== undefined) seek(Number(b.dataset.seek), true);
		else if (b.dataset.edit !== undefined) edit(Number(b.dataset.edit));
		else if (b.dataset.cancel !== undefined) render();
		else if (b.dataset.save !== undefined) {
			const i = Number(b.dataset.save);
			const text = list.querySelector(`[data-i="${i}"] textarea`).value;
			try {
				await post("sok_resdesk.pagetext.save_page", { item_id: itemId, leaf: segs[i].leaf, text });
				segs[i].text = text;
				status.textContent = __("Saved. A second person validates it.");
			} catch (err) { status.textContent = err.message; return; }
			render();
			current = -1;
		}
	});

	follow.addEventListener("click", () => {
		following = !following;
		follow.setAttribute("aria-pressed", String(following));
	});
	if (player) player.addEventListener("timeupdate", () => mark(player.currentTime));

	fetch(`/api/method/sok_resdesk.api.transcript?item_id=${encodeURIComponent(itemId)}`, { headers: { Accept: "application/json" } })
		.then((r) => r.json())
		.then((j) => {
			const d = j.message || {};
			segs = d.segments || [];
			canProof = !!d.can_proofread;
			render();
			const start = Number(root.dataset.start || 0);
			if (new URLSearchParams(location.search).has("page") && segs[start]) {
				const set = () => { seek(start, false); mark(segs[start].start); };
				if (player.readyState >= 1) set(); else player.addEventListener("loadedmetadata", set, { once: true });
			}
		})
		.catch(() => { list.innerHTML = `<li class="rd-muted">${esc(__("The transcript could not be loaded."))}</li>`; });
})();
