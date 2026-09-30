// First-visit tips for readers on the library home page. Shown once per browser (or with
// ?tips=1, linked from the help page); "Got it" hides them for good.
(function () {
	const box = document.getElementById("rd-tips");
	if (!box) return;
	const KEY = "rd-tips-seen";
	const store = {
		get() {
			try {
				return window.localStorage.getItem(KEY);
			} catch (e) {
				return "1"; // no storage (private window): don't nag on every visit
			}
		},
		set() {
			try {
				window.localStorage.setItem(KEY, "1");
			} catch (e) {
				/* ignore */
			}
		},
	};
	const forced = new URLSearchParams(window.location.search).get("tips") === "1";
	if (store.get() && !forced) return;

	const tips = Array.from(box.querySelectorAll(".rd-tips__list li"));
	const count = box.querySelector(".rd-tips__count");
	let i = 0;
	function show() {
		tips.forEach((t, n) => (t.hidden = n !== i));
		count.textContent = `${i + 1} / ${tips.length}`;
		box.querySelector(".rd-tips__next").hidden = i === tips.length - 1;
	}
	box.querySelector(".rd-tips__next").addEventListener("click", () => {
		i = Math.min(i + 1, tips.length - 1);
		show();
	});
	box.querySelector(".rd-tips__done").addEventListener("click", () => {
		store.set();
		box.hidden = true;
	});
	box.hidden = false;
	show();
})();
