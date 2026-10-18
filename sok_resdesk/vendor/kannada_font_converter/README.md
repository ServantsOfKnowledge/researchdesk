# Kannada font converter (vendored)

The conversion engine of the Sanchaya **Kannada Font Converter**, between legacy font encodings
(Nudi/Baraha, ShreeLipi, Prakashak, Akruti, Surabhi, ISM, Dharma, Janna, SriLipi, Shree Deccan, Suchi
Kan, WinKey) and Unicode.

- Source: https://github.com/sanchaya/kannada-font-converter, `js/app.js` at commit
  `43f422c9dd19d08a87b6d1e0f65bc5118f1d66a3` (v1.1.2), copied **unmodified**.
- Licence: **GPL-3.0-or-later** (`LICENSE`, here). `convert.js` is derived from that project's
  `server.js` and has the same licence. The rest of Research Desk is MIT; it uses this directory only by
  running `node convert.js` as a separate program (`sok_resdesk/legacy_kannada.py`) and passing text in and
  out, so the two stay separate works. If you redistribute Research Desk, keep this directory, its licence
  and the notice in `app.js` together.
- To refresh: copy `js/app.js` and `LICENSE` from the source repository, update the commit above, and run
  `pytest sok_resdesk/tests/unit_legacy_kannada.py`.
- Needs Node.js (Frappe's own build already needs it).
