// Command-line wrapper around the Sanchaya Kannada font converter's engine (app.js, unmodified).
// Reads {"items": [text...], "font": "nudi", "direction": "a2u", "digits": "keep", "retainEnglish": true}
// as JSON on standard input and writes {"items": [converted...]} on standard output.
//
// It loads app.js into a sandbox and calls the same convert() the converter's own server.js calls, so
// every fix to the engine applies here. Derived from server.js of
// https://github.com/sanchaya/kannada-font-converter (Sanchaya, GPL-3.0-or-later).
// Licensed under GPL-3.0-or-later, like the rest of this directory: see LICENSE.
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const stubEl = new Proxy({}, {
	get(target, prop) {
		if (prop === 'addEventListener') return () => {};
		if (prop === 'style') return { setProperty() {} };
		if (prop === 'classList') return { add() {}, remove() {}, toggle() {} };
		if (prop === 'value') return '';
		return () => {};
	},
});
const sandbox = {
	document: {
		addEventListener() {},
		getElementById() { return stubEl; },
		querySelector() { return null; },
		querySelectorAll() { return []; },
	},
	navigator: { userAgent: 'researchdesk' },
	console,
};
sandbox.window = sandbox;
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(path.join(__dirname, 'app.js'), 'utf8'), sandbox, { filename: 'app.js' });
if (typeof sandbox.convert !== 'function') {
	console.error('app.js did not expose convert()');
	process.exit(2);
}

const FONTS = new Set(['nudi', 'shree', 'prakashak', 'akruti', 'surabhi', 'ismkntt', 'dharma', 'janna',
	'srilipi850', 'shreedeccan', 'surabhikn', 'suchikan', 'ismknbtt', 'akrutibi', 'winkey']);

let raw = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', (c) => { raw += c; });
process.stdin.on('end', () => {
	try {
		const req = JSON.parse(raw);
		const font = FONTS.has(req.font) ? req.font : 'nudi';
		const direction = req.direction === 'u2a' ? 'u2a' : 'a2u';
		const digits = ['keep', 'kn', 'en'].includes(req.digits) ? req.digits : 'keep';
		const items = (req.items || []).map((t) =>
			typeof t === 'string' && t ? sandbox.convert(t, digits, direction, !!req.retainEnglish, font) : '');
		process.stdout.write(JSON.stringify({ items }));
	} catch (e) {
		console.error(String(e && e.message || e));
		process.exit(1);
	}
});
