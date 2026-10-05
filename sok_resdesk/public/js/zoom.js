// Zoom: a page image full screen, to look at closely (a palm leaf's lines, a faint colophon).
// Wheel or pinch to zoom, drag to move, + − 0 and the arrow keys from the keyboard.
// Reader (reader.js) puts a button with data-zoom="<whole image address>" on every page image.
(function () {
	const __ = window.rdT || ((s) => s);
	let dlg, img, state;

	function build() {
		dlg = document.createElement("dialog");
		dlg.className = "rd-zoom";
		dlg.setAttribute("aria-label", __("Zoom"));
		dlg.innerHTML = `
			<div class="rd-zoom__bar">
				<button type="button" class="rd-btn" data-z="in" aria-label="${__("Zoom in")}">+</button>
				<button type="button" class="rd-btn" data-z="out" aria-label="${__("Zoom out")}">−</button>
				<button type="button" class="rd-btn" data-z="fit">${__("Fit")}</button>
				<button type="button" class="rd-btn" data-z="turn" aria-label="${__("Turn a quarter")}">↻</button>
				<button type="button" class="rd-btn rd-btn--primary" data-z="close">${__("Close")}</button>
			</div>
			<div class="rd-zoom__stage" tabindex="0"><img alt="" draggable="false"></div>`;
		document.body.appendChild(dlg);
		img = dlg.querySelector("img");
		const stage = dlg.querySelector(".rd-zoom__stage");
		dlg.addEventListener("click", (e) => {
			const b = e.target.closest("[data-z]");
			if (!b) return;
			const a = b.dataset.z;
			if (a === "close") dlg.close();
			else if (a === "fit") fit();
			else if (a === "turn") { state.turn = (state.turn + 90) % 360; fit(); }
			else zoom(a === "in" ? 1.4 : 1 / 1.4);
		});
		stage.addEventListener("wheel", (e) => { e.preventDefault(); zoom(e.deltaY < 0 ? 1.2 : 1 / 1.2, e.clientX, e.clientY); }, { passive: false });
		let drag = null;
		stage.addEventListener("pointerdown", (e) => { drag = { x: e.clientX, y: e.clientY, tx: state.x, ty: state.y }; stage.setPointerCapture(e.pointerId); });
		stage.addEventListener("pointermove", (e) => { if (drag) { state.x = drag.tx + e.clientX - drag.x; state.y = drag.ty + e.clientY - drag.y; draw(); } });
		stage.addEventListener("pointerup", () => (drag = null));
		stage.addEventListener("dblclick", (e) => zoom(2, e.clientX, e.clientY));
		dlg.addEventListener("keydown", (e) => {
			const step = 60;
			if (e.key === "+" || e.key === "=") zoom(1.4);
			else if (e.key === "-") zoom(1 / 1.4);
			else if (e.key === "0") fit();
			else if (e.key === "ArrowLeft") { state.x += step; draw(); }
			else if (e.key === "ArrowRight") { state.x -= step; draw(); }
			else if (e.key === "ArrowUp") { state.y += step; draw(); }
			else if (e.key === "ArrowDown") { state.y -= step; draw(); }
			else return;
			e.preventDefault();
		});
	}

	function size() {
		const swap = state.turn % 180 !== 0;
		return { w: swap ? img.naturalHeight : img.naturalWidth, h: swap ? img.naturalWidth : img.naturalHeight };
	}
	function draw() {
		const { w, h } = size();
		// the image is turned about its middle, then placed, then scaled
		img.style.transform = `translate(${state.x}px, ${state.y}px) scale(${state.k}) translate(${w / 2}px, ${h / 2}px) rotate(${state.turn}deg) translate(${-img.naturalWidth / 2}px, ${-img.naturalHeight / 2}px)`;
	}
	function fit() {
		const stage = dlg.querySelector(".rd-zoom__stage");
		const { w, h } = size();
		state.k = Math.min(stage.clientWidth / w, stage.clientHeight / h, 1) || 1;
		state.x = (stage.clientWidth - w * state.k) / 2;
		state.y = (stage.clientHeight - h * state.k) / 2;
		draw();
	}
	function zoom(f, cx, cy) {
		const stage = dlg.querySelector(".rd-zoom__stage").getBoundingClientRect();
		const px = (cx ?? stage.left + stage.width / 2) - stage.left, py = (cy ?? stage.top + stage.height / 2) - stage.top;
		const k = Math.min(8, Math.max(0.05, state.k * f));
		state.x = px - (px - state.x) * (k / state.k);
		state.y = py - (py - state.y) * (k / state.k);
		state.k = k;
		draw();
	}

	document.addEventListener("click", (e) => {
		const b = e.target.closest("[data-zoom]");
		if (!b) return;
		if (!dlg) build();
		state = { k: 1, x: 0, y: 0, turn: 0 };
		img.onload = fit;
		img.removeAttribute("src");
		img.src = b.dataset.zoom;
		img.alt = b.dataset.alt || "";
		dlg.showModal();
		dlg.querySelector(".rd-zoom__stage").focus();
	});
})();
