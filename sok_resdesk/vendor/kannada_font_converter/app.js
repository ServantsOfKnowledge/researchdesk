// ============================================================
// FRONTEND APPLICATION - Client-side conversion for GitHub Pages
//
// ಕನ್ನಡ ಅಕ್ಷರರೂಪ ಪರಿವರ್ತಕ - Proudly built by Sanchaya with ❤ for
// Kannada. https://converter.sanchaya.net | https://sanchaya.org
// Licensed under GPL-3.0-or-later - see LICENSE. If you're running this
// from a downloaded copy or your own fork, please keep this notice and
// the footer attribution in index.html intact.
// ============================================================

let convertedText = '';
let fileText = '';
let fileName = '';

// ============================================================
// NUDI/BARAHA ASCII TO UNICODE MAPPING (Client-side)
// ============================================================

const A2U_MAP = {};

const vowelMaps = [
    ['A', 'ಂ'], ['B', 'ಃ'], ['CA', 'ಅಂ'], ['CB', 'ಅಃ'],
    ['C', 'ಅ'], ['D', 'ಆ'], ['E', 'ಇ'], ['F', 'ಈ'],
    ['G', 'ಉ'], ['H', 'ಊ'], ['IÄ', 'ಋ'], ['IÆ', 'ೠ'],
    ['J', 'ಎ'], ['K', 'ಏ'], ['L', 'ಐ'], ['M', 'ಒ'],
    ['N', 'ಓ'], ['O', 'ಔ'],
    ['x', 'ಕ್ಷ'], ['GY', 'ಜ್ಞ']
];

const consonantMaps = [
    ['Pï', 'ಕ್'], ['PÀ', 'ಕ'], ['PÁ', 'ಕಾ'], ['Q', 'ಕಿ'], ['QÃ', 'ಕೀ'],
    ['PÀÄ', 'ಕು'], ['PÀÆ', 'ಕೂ'], ['PÀÈ', 'ಕೃ'], ['PÉ', 'ಕೆ'], ['PÉÃ', 'ಕೇ'],
    ['PÉÊ', 'ಕೈ'], ['PÉÆ', 'ಕೊ'], ['PÉÆÃ', 'ಕೋ'], ['PË', 'ಕೌ'],
    ['Sï', 'ಖ್'], ['R', 'ಖ'], ['SÁ', 'ಖಾ'], ['T', 'ಖಿ'], ['TÃ', 'ಖೀ'],
    ['RÄ', 'ಖು'], ['RÆ', 'ಖೂ'], ['RÈ', 'ಖೃ'], ['SÉ', 'ಖೆ'], ['SÉÃ', 'ಖೇ'],
    ['SÉÊ', 'ಖೈ'], ['SÉÆ', 'ಖೊ'], ['SÉÆÃ', 'ಖೋ'], ['SË', 'ಖೌ'],
    ['Uï', 'ಗ್'], ['UÀ', 'ಗ'], ['UÁ', 'ಗಾ'], ['V', 'ಗಿ'], ['VÃ', 'ಗೀ'],
    ['UÀÄ', 'ಗು'], ['UÀÆ', 'ಗೂ'], ['UÀÈ', 'ಗೃ'], ['UÉ', 'ಗೆ'], ['UÉÃ', 'ಗೇ'],
    ['UÉÊ', 'ಗೈ'], ['UÉÆ', 'ಗೊ'], ['UÉÆÃ', 'ಗೋ'], ['UË', 'ಗೌ'],
    ['Wï', 'ಘ್'], ['WÀ', 'ಘ'], ['WÁ', 'ಘಾ'], ['X', 'ಘಿ'], ['XÃ', 'ಘೀ'],
    ['WÀÄ', 'ಘು'], ['WÀÆ', 'ಘೂ'], ['WÀÈ', 'ಘೃ'], ['WÉ', 'ಘೆ'], ['WÉÃ', 'ಘೇ'],
    ['WÉÊ', 'ಘೈ'], ['WÉÆ', 'ಘೊ'], ['WÉÆÃ', 'ಘೋ'], ['WË', 'ಘೌ'],
    ['Yï', 'ಙ್'], ['Y', 'ಙ'],
    ['Zï', 'ಚ್'], ['ZÀ', 'ಚ'], ['ZÁ', 'ಚಾ'], ['a', 'ಚಿ'], ['aÃ', 'ಚೀ'],
    ['ZÀÄ', 'ಚು'], ['ZÀÆ', 'ಚೂ'], ['ZÀÈ', 'ಚೃ'], ['ZÉ', 'ಚೆ'], ['ZÉÃ', 'ಚೇ'],
    ['ZÉÊ', 'ಚೈ'], ['ZÉÆ', 'ಚೊ'], ['ZÉÆÃ', 'ಚೋ'], ['ZË', 'ಚೌ'],
    ['bï', 'ಛ್'], ['bÀ', 'ಛ'], ['bÁ', 'ಛಾ'], ['c', 'ಛಿ'], ['cÃ', 'ಛೀ'],
    ['bÀÄ', 'ಛು'], ['bÀÆ', 'ಛೂ'], ['bÀÈ', 'ಛೃ'], ['bÉ', 'ಛೆ'], ['bÉÃ', 'ಛೇ'],
    ['bÉÊ', 'ಛೈ'], ['bÉÆ', 'ಛೊ'], ['bÉÆÃ', 'ಛೋ'], ['bË', 'ಛೌ'],
    ['eï', 'ಜ್'], ['d', 'ಜ'], ['eÁ', 'ಜಾ'], ['f', 'ಜಿ'], ['fÃ', 'ಜೀ'],
    ['dÄ', 'ಜು'], ['dÆ', 'ಜೂ'], ['dÈ', 'ಜೃ'], ['eÉ', 'ಜೆ'], ['eÉÃ', 'ಜೇ'],
    ['eÉÊ', 'ಜೈ'], ['eÉÆ', 'ಜೊ'], ['eÉÆÃ', 'ಜೋ'], ['eË', 'ಜೌ'],
    ['gÀhiï', 'ಝ್'], ['gÀhÄ', 'ಝ'], ['gÀhiÁ', 'ಝಾ'], ['jhÄ', 'ಝಿ'], ['jhÄÃ', 'ಝೀ'],
    ['gÀhÄÄ', 'ಝು'], ['gÀhÄÆ', 'ಝೂ'], ['gÀhÄÈ', 'ಝೃ'], ['gÉhÄ', 'ಝೆ'], ['gÉhÄÃ', 'ಝೇ'],
    ['gÉhÄÊ', 'ಝೈ'], ['gÉhÆ', 'ಝೊ'], ['gÉhÆÃ', 'ಝೋ'], ['gÀhiË', 'ಝೌ'],
    ['kï', 'ಞ್'], ['k', 'ಞ'],
    ['mï', 'ಟ್'], ['l', 'ಟ'], ['mÁ', 'ಟಾ'], ['n', 'ಟಿ'], ['nÃ', 'ಟೀ'],
    ['lÄ', 'ಟು'], ['lÆ', 'ಟೂ'], ['lÈ', 'ಟೃ'], ['mÉ', 'ಟೆ'], ['mÉÃ', 'ಟೇ'],
    ['mÉÊ', 'ಟೈ'], ['mÉÆ', 'ಟೊ'], ['mÉÆÃ', 'ಟೋ'], ['mË', 'ಟೌ'],
    ['oï', 'ಠ್'], ['oÀ', 'ಠ'], ['oÁ', 'ಠಾ'], ['p', 'ಠಿ'], ['pÃ', 'ಠೀ'],
    ['oÀÄ', 'ಠು'], ['oÀÆ', 'ಠೂ'], ['oÀÈ', 'ಠೃ'], ['oÉ', 'ಠೆ'], ['oÉÃ', 'ಠೇ'],
    ['oÉÊ', 'ಠೈ'], ['oÉÆ', 'ಠೊ'], ['oÉÆÃ', 'ಠೋ'], ['oË', 'ಠೌ'],
    ['qï', 'ಡ್'], ['qÀ', 'ಡ'], ['qÁ', 'ಡಾ'], ['r', 'ಡಿ'], ['rÃ', 'ಡೀ'],
    ['qÀÄ', 'ಡು'], ['qÀÆ', 'ಡೂ'], ['qÀÈ', 'ಡೃ'], ['qÉ', 'ಡೆ'], ['qÉÃ', 'ಡೇ'],
    ['qÉÊ', 'ಡೈ'], ['qÉÆ', 'ಡೊ'], ['qÉÆÃ', 'ಡೋ'], ['qË', 'ಡೌ'],
    ['qsï', 'ಢ್'], ['qsÀ', 'ಢ'], ['qsÁ', 'ಢಾ'], ['rü', 'ಢಿ'], ['rüÃ', 'ಢೀ'],
    ['qsÀÄ', 'ಢು'], ['qsÀÆ', 'ಢೂ'], ['qsÀÈ', 'ಢೃ'], ['qsÉ', 'ಢೆ'], ['qsÉÃ', 'ಢೇ'],
    ['qsÉÊ', 'ಢೈ'], ['qsÉÆ', 'ಢೊ'], ['qsÉÆÃ', 'ಢೋ'], ['qsË', 'ಢೌ'],
    ['uï', 'ಣ್'], ['t', 'ಣ'], ['uÁ', 'ಣಾ'], ['tÂ', 'ಣಿ'], ['tÂÃ', 'ಣೀ'],
    ['tÄ', 'ಣು'], ['tÆ', 'ಣೂ'], ['tÈ', 'ಣೃ'], ['uÉ', 'ಣೆ'], ['uÉÃ', 'ಣೇ'],
    ['uÉÊ', 'ಣೈ'], ['uÉÆ', 'ಣೊ'], ['uÉÆÃ', 'ಣೋ'], ['uË', 'ಣೌ'],
    ['vï', 'ತ್'], ['vÀ', 'ತ'], ['vÁ', 'ತಾ'], ['w', 'ತಿ'], ['wÃ', 'ತೀ'],
    ['vÀÄ', 'ತು'], ['vÀÆ', 'ತೂ'], ['vÀÈ', 'ತೃ'], ['vÉ', 'ತೆ'], ['vÉÃ', 'ತೇ'],
    ['vÉÊ', 'ತೈ'], ['vÉÆ', 'ತೊ'], ['vÉÆÃ', 'ತೋ'], ['vË', 'ತೌ'],
    ['xï', 'ಥ್'], ['xÀ', 'ಥ'], ['xÁ', 'ಥಾ'], ['y', 'ಥಿ'], ['yÃ', 'ಥೀ'],
    ['xÀÄ', 'ಥು'], ['xÀÆ', 'ಥೂ'], ['xÀÈ', 'ಥೃ'], ['xÉ', 'ಥೆ'], ['xÉÃ', 'ಥೇ'],
    ['xÉÊ', 'ಥೈ'], ['xÉÆ', 'ಥೊ'], ['xÉÆÃ', 'ಥೋ'], ['xË', 'ಥೌ'],
    ['zï', 'ದ್'], ['zÀ', 'ದ'], ['zÁ', 'ದಾ'], ['¢', 'ದಿ'], ['¢Ã', 'ದೀ'],
    ['zÀÄ', 'ದು'], ['zÀÆ', 'ದೂ'], ['zÀÈ', 'ದೃ'], ['zÉ', 'ದೆ'], ['zÉÃ', 'ದೇ'],
    ['zÉÊ', 'ದೈ'], ['zÉÆ', 'ದೊ'], ['zÉÆÃ', 'ದೋ'], ['zË', 'ದೌ'],
    ['zsï', 'ಧ್'], ['zsÀ', 'ಧ'], ['zsÁ', 'ಧಾ'], ['¢ü', 'ಧಿ'], ['¢üÃ', 'ಧೀ'],
    ['zsÀÄ', 'ಧು'], ['zsÀÆ', 'ಧೂ'], ['zsÀÈ', 'ಧೃ'], ['zsÉ', 'ಧೆ'], ['zsÉÃ', 'ಧೇ'],
    ['zsÉÊ', 'ಧೈ'], ['zsÉÆ', 'ಧೊ'], ['zsÉÆÃ', 'ಧೋ'], ['zsË', 'ಧೌ'],
    ['£ï', 'ನ್'], ['£À', 'ನ'], ['£Á', 'ನಾ'], ['¤', 'ನಿ'], ['¤Ã', 'ನೀ'],
    ['£ÀÄ', 'ನು'], ['£ÀÆ', 'ನೂ'], ['£ÀÈ', 'ನೃ'], ['£É', 'ನೆ'], ['£ÉÃ', 'ನೇ'],
    ['£ÉÊ', 'ನೈ'], ['£ÉÆ', 'ನೊ'], ['£ÉÆÃ', 'ನೋ'], ['£Ë', 'ನೌ'],
    ['¥ï', 'ಪ್'], ['¥À', 'ಪ'], ['¥Á', 'ಪಾ'], ['¦', 'ಪಿ'], ['¦Ã', 'ಪೀ'],
    // ಪ normally uses Å (not the usual Ä) for its "u" matra to avoid a
    // rendering collision in the legacy Nudi font - but real-world
    // documents (e.g. typed with other Nudi/Baraha tool versions) commonly
    // use the regular Ä byte instead, so both are accepted here. Order
    // matters: U2A_MAP (used for Unicode->ASCII, built by inverting this
    // table further down) keeps whichever ascii key was inserted LAST for
    // a given Kannada value as its canonical reverse mapping, so 'Ä' is
    // listed BEFORE 'Å' here to make sure 'Å' stays the canonical u2a
    // output - other pivot fonts (e.g. Surabhi KN) only know how to
    // reverse-map the 'Å' byte, so making 'Ä' canonical broke their u2a
    // round-trip even though the a2u direction alone was fine.
    ['¥ÀÄ', 'ಪು'], ['¥ÀÅ', 'ಪು'],
    // ಪ also substitutes Ç for the regular long-u/long-O-family Æ byte
    // (same rendering-collision reason as the Å/Ä case above) - both
    // accepted here too, Æ listed first so Ç stays canonical for u2a.
    ['¥ÀÆ', 'ಪೂ'], ['¥ÀÇ', 'ಪೂ'], ['¥ÀÈ', 'ಪೃ'], ['¥É', 'ಪೆ'], ['¥ÉÃ', 'ಪೇ'],
    ['¥ÉÊ', 'ಪೈ'], ['¥ÉÆ', 'ಪೊ'], ['¥ÉÇ', 'ಪೊ'], ['¥ÉÆÃ', 'ಪೋ'], ['¥ÉÇÃ', 'ಪೋ'], ['¥Ë', 'ಪೌ'],
    ['¥sï', 'ಫ್'], ['¥sÀ', 'ಫ'], ['¥sÁ', 'ಫಾ'], ['¦ü', 'ಫಿ'], ['¦üÃ', 'ಫೀ'],
    // Same Å/Ä and Ç/Æ dual-acceptance as ಪ above, and same ordering
    // reason (the special byte must be inserted last to stay canonical).
    ['¥sÀÄ', 'ಫು'], ['¥sÀÅ', 'ಫು'], ['¥sÀÆ', 'ಫೂ'], ['¥sÀÇ', 'ಫೂ'], ['¥sÀÈ', 'ಫೃ'], ['¥sÉ', 'ಫೆ'], ['¥sÉÃ', 'ಫೇ'],
    ['¥sÉÊ', 'ಫೈ'], ['¥sÉÆ', 'ಫೊ'], ['¥sÉÇ', 'ಫೊ'], ['¥sÉÆÃ', 'ಫೋ'], ['¥sÉÇÃ', 'ಫೋ'], ['¥sË', 'ಫೌ'],
    ['¨ï', 'ಬ್'], ['§', 'ಬ'], ['¨Á', 'ಬಾ'], ['©', 'ಬಿ'], ['©Ã', 'ಬೀ'],
    ['§Ä', 'ಬು'], ['§Æ', 'ಬೂ'], ['§È', 'ಬೃ'], ['¨É', 'ಬೆ'], ['¨ÉÃ', 'ಬೇ'],
    ['¨ÉÊ', 'ಬೈ'], ['¨ÉÆ', 'ಬೊ'], ['¨ÉÆÃ', 'ಬೋ'], ['¨Ë', 'ಬೌ'],
    ['¨sï', 'ಭ್'], ['¨sÀ', 'ಭ'], ['¨sÁ', 'ಭಾ'], ['©ü', 'ಭಿ'], ['©üÃ', 'ಭೀ'],
    ['¨sÀÄ', 'ಭು'], ['¨sÀÆ', 'ಭೂ'], ['¨sÀÈ', 'ಭೃ'], ['¨sÉ', 'ಭೆ'], ['¨sÉÃ', 'ಭೇ'],
    ['¨sÉÊ', 'ಭೈ'], ['¨sÉÆ', 'ಭೊ'], ['¨sÉÆÃ', 'ಭೋ'], ['¨sË', 'ಭೌ'],
    ['ªÀiï', 'ಮ್'], ['ªÀÄ', 'ಮ'], ['ªÀiÁ', 'ಮಾ'], ['«Ä', 'ಮಿ'], ['«ÄÃ', 'ಮೀ'],
    ['ªÀÄÄ', 'ಮು'], ['ªÀÄÆ', 'ಮೂ'], ['ªÀÄÈ', 'ಮೃ'], ['ªÉÄ', 'ಮೆ'], ['ªÉÄÃ', 'ಮೇ'],
    ['ªÉÄÊ', 'ಮೈ'], ['ªÉÆ', 'ಮೊ'], ['ªÉÆÃ', 'ಮೋ'], ['ªÀiË', 'ಮೌ'],
    ['AiÀiï', 'ಯ್'], ['AiÀÄ', 'ಯ'], ['AiÀiÁ', 'ಯಾ'], ['¬Ä', 'ಯಿ'], ['¬ÄÃ', 'ಯೀ'],
    ['AiÀÄÄ', 'ಯು'], ['AiÀÄÆ', 'ಯೂ'], ['AiÀÄÈ', 'ಯೃ'], ['AiÉÄ', 'ಯೆ'], ['AiÉÄÃ', 'ಯೇ'],
    ['AiÉÄÊ', 'ಯೈ'], ['AiÉÆ', 'ಯೊ'], ['AiÉÆÃ', 'ಯೋ'], ['AiÀiË', 'ಯೌ'],
    ['gï', 'ರ್'], ['gÀ', 'ರ'], ['gÁ', 'ರಾ'], ['j', 'ರಿ'], ['jÃ', 'ರೀ'],
    ['gÀÄ', 'ರು'], ['gÀÆ', 'ರೂ'], ['gÀÈ', 'ರೃ'], ['gÉ', 'ರೆ'], ['gÉÃ', 'ರೇ'],
    ['gÉÊ', 'ರೈ'], ['gÉÆ', 'ರೊ'], ['gÉÆÃ', 'ರೋ'], ['gË', 'ರೌ'],
    ['¯ï', 'ಲ್'], ['®', 'ಲ'], ['¯Á', 'ಲಾ'], ['°', 'ಲಿ'], ['°Ã', 'ಲೀ'],
    ['®Ä', 'ಲು'], ['®Æ', 'ಲೂ'], ['®È', 'ಲೃ'], ['¯É', 'ಲೆ'], ['¯ÉÃ', 'ಲೇ'],
    ['¯ÉÊ', 'ಲೈ'], ['¯ÉÆ', 'ಲೊ'], ['¯ÉÆÃ', 'ಲೋ'], ['¯Ë', 'ಲೌ'],
    ['ªï', 'ವ್'], ['ªÀ', 'ವ'], ['ªÁ', 'ವಾ'], ['«', 'ವಿ'], ['«Ã', 'ವೀ'],
    ['ªÀÅ', 'ವು'], ['ªÀÇ', 'ವೂ'], ['ªÀÈ', 'ವೃ'], ['ªÉ', 'ವೆ'], ['ªÉÃ', 'ವೇ'],
    ['ªÉÊ', 'ವೈ'], ['ªÉÇ', 'ವೊ'], ['ªÉÇÃ', 'ವೋ'], ['ªË', 'ವೌ'],
    ['±ï', 'ಶ್'], ['±À', 'ಶ'], ['±Á', 'ಶಾ'], ['²', 'ಶಿ'], ['²Ã', 'ಶೀ'],
    ['±ÀÄ', 'ಶು'], ['±ÀÆ', 'ಶೂ'], ['±ÀÈ', 'ಶೃ'], ['±É', 'ಶೆ'], ['±ÉÃ', 'ಶೇ'],
    ['±ÉÊ', 'ಶೈ'], ['±ÉÆ', 'ಶೊ'], ['±ÉÆÃ', 'ಶೋ'], ['±Ë', 'ಶೌ'],
    ['μï', 'ಷ್'], ['μÀ', 'ಷ'], ['μÁ', 'ಷಾ'], ['¶', 'ಷಿ'], ['¶Ã', 'ಷೀ'],
    ['μÀÄ', 'ಷು'], ['μÀÆ', 'ಷೂ'], ['μÀÈ', 'ಷೃ'], ['μÉ', 'ಷೆ'], ['μÉÃ', 'ಷೇ'],
    ['μÉÊ', 'ಷೈ'], ['μÉÆ', 'ಷೊ'], ['μÉÆÃ', 'ಷೋ'], ['μË', 'ಷೌ'],
    ['¸ï', 'ಸ್'], ['¸À', 'ಸ'], ['¸Á', 'ಸಾ'], ['¹', 'ಸಿ'], ['¹Ã', 'ಸೀ'],
    ['¸ÀÄ', 'ಸು'], ['¸ÀÆ', 'ಸೂ'], ['¸ÀÈ', 'ಸೃ'], ['¸É', 'ಸೆ'], ['¸ÉÃ', 'ಸೇ'],
    ['¸ÉÊ', 'ಸೈ'], ['¸ÉÆ', 'ಸೊ'], ['¸ÉÆÃ', 'ಸೋ'], ['¸Ë', 'ಸೌ'],
    ['ºï', 'ಹ್'], ['ºÀ', 'ಹ'], ['ºÁ', 'ಹಾ'], ['»', 'ಹಿ'], ['»Ã', 'ಹೀ'],
    ['ºÀÄ', 'ಹು'], ['ºÀÆ', 'ಹೂ'], ['ºÀÈ', 'ಹೃ'], ['ºÉ', 'ಹೆ'], ['ºÉÃ', 'ಹೇ'],
    ['ºÉÊ', 'ಹೈ'], ['ºÉÆ', 'ಹೊ'], ['ºÉÆÃ', 'ಹೋ'], ['ºË', 'ಹೌ'],
    ['¼ï', 'ಳ್'], ['¼À', 'ಳ'], ['¼Á', 'ಳಾ'], ['½', 'ಳಿ'], ['½Ã', 'ಳೀ'],
    ['¼ÀÄ', 'ಳು'], ['¼ÀÆ', 'ಳೂ'], ['¼ÀÈ', 'ಳೃ'], ['¼É', 'ಳೆ'], ['¼ÉÃ', 'ಳೇ'],
    ['¼ÉÊ', 'ಳೈ'], ['¼ÉÆ', 'ಳೊ'], ['¼ÉÆÃ', 'ಳೋ'], ['¼Ë', 'ಳೌ']
];

// ============================================================
// APPLY MAPPINGS
// ============================================================

vowelMaps.forEach(m => A2U_MAP[m[0]] = m[1]);
consonantMaps.forEach(m => A2U_MAP[m[0]] = m[1]);

const A2U_KEYS = Object.keys(A2U_MAP).sort((a, b) => b.length - a.length);

// ShreeLipi, Prakashak, Akruti, and Surabhi are handled by the pivot-based
// engine further below (ported from the KGP macro tables - see
// tools/MACRO-REVIEW.md), not by flat maps here.

const VATTAKSHARA_MAP = {
    'Ì': 'ಕ್', 'Í': 'ಖ್', 'Î': 'ಗ್', 'Ï': 'ಘ್', 'Ð': 'ಙ್',
    'Ñ': 'ಚ್', 'Ò': 'ಛ್', 'Ó': 'ಜ್', 'Ô': 'ಝ್', 'Õ': 'ಞ್',
    'Ö': 'ಟ್', '×': 'ಠ್', 'Ø': 'ಡ್', 'Ù': 'ಢ್', 'Ú': 'ಣ್',
    'Û': 'ತ್', 'Ü': 'ಥ್', 'Ý': 'ದ್', 'Þ': 'ಧ್', 'ß': 'ನ್',
    'à': 'ಪ್', 'á': 'ಫ್', 'â': 'ಬ್', 'ã': 'ಭ್', 'ä': 'ಮ್',
    'å': 'ಯ್', 'æ': 'ರ್', 'è': 'ಲ್', 'é': 'ವ್', 'ê': 'ಶ್',
    'ë': 'ಷ್', 'ì': 'ಸ್', 'í': 'ಹ್', 'î': 'ಳ್',
    // 'ç' is Nudi's alternate byte for a subjoined ra-vattakshara that
    // stacks under an already-subjoined consonant (a "double vattu"), as
    // opposed to 'æ' which is ra-vattakshara directly under a base
    // consonant. Needed for common triple conjuncts like ¸ÀÛç = ಸ್ತ್ರ
    // (ಶಾಸ್ತ್ರ, ಪಾತ್ರ, ಮಂತ್ರ, ಸೂತ್ರ, ...) - same target ('ರ್') as 'æ' since
    // both mean "subjoin ra here", _fix_conjuncts's chained-marker loop
    // handles the reordering into the correct triple conjunct either way.
    'ç': 'ರ್',
    // 'ö' is the same "double vattu" pattern as 'ç' above, but for ya
    // instead of ra: the alternate byte for a subjoined ya-vattakshara
    // that stacks under an already-subjoined consonant, vs. 'å' which is
    // ya-vattakshara directly under a base consonant. Needed for triple
    // conjuncts like zÁjzÀæö = ದಾರಿದ್ರ್ಯ (ದ್ರ್ಯ - "drya").
    'ö': 'ಯ್'
};

const VATT_MARKER = '\u0001';

const OTHER_MAP = {
    'ø': 'ೃ',
    'ñ': 'ೄ',
    '„': 'ಽ',
    'ó': '಼',
    'ð': 'ರ',
    'ï': '್'
};

const KN_DIGITS = ['೦', '೧', '೨', '೩', '೪', '೫', '೬', '೭', '೮', '೯'];
const EN_DIGITS = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9'];
const ASCII_VATTAKSHARA = "ÌÍÎÏÐÑÒÓÔÕÖ×ØÙÚÛÜÝÞßàáâãäåæçèéêëìíîö";
const DEP_VOWELS = "್ಾಿೀುೂೃೆೇೈೊೋೌ";

function _encodeIdx(n) {
    let s = '';
    do { s = String.fromCharCode(97 + (n % 26)) + s; n = Math.floor(n / 26); } while (n > 0);
    return s;
}

function _decodeIdx(s) {
    let n = 0;
    for (const c of s) n = n * 26 + (c.charCodeAt(0) - 97);
    return n;
}

function _makePlaceholder(idx) {
    return '\uFF62' + _encodeIdx(idx) + '\uFF63';
}
const _placeholderRe = /\uFF62([a-z]+)\uFF63/g;

// Matches any non-ASCII character. Used to detect when a run of plain
// ASCII letters is directly touching a Nudi-ASCII byte (which almost
// always renders as an extended Latin-1/Windows-1252 character, e.g.
// \u00B8,\u00A5,\u00A7,\u00A9,\u00B1... in the 0x80-0xBF block, not just the 0xC0-0xFF block this
// used to check) - such a token is part of the Nudi encoding, not a
// standalone English word, regardless of what code point the adjacent
// byte happens to be.
const LATIN_EXT_RE = /[^\x00-\x7F]/;
const PURE_ASCII_WORD_RE = /^[a-zA-Z'-]+$/;
const NUDI_SINGLE_UPPER = new Set(['A','B','C','D','E','F','G','H','I','J','K','L','M','N','P','Q','R','S','T','U','V','W','X','Y','Z']);
const NUDI_SINGLE_LOWER = new Set(['a','b','c','d','f','g','h','i','j','k','l','m','n','o','p','q','r','s','t','u','v','w','x','y','z']);

// Uppercase letters that have standalone Nudi a2u mappings (not needing À/ï/É etc.)
const NUDI_A2U_STANDALONE = new Set(['A','B','C','D','E','F','G','H','J','K','L','M','N','Q','R','T','V','X','Y']);

// Common English uppercase words where every letter has a standalone Nudi a2u mapping.
// These should be retained as English rather than converted as Nudi.
const EN_UPPER_NUDI_CONFLICT = new Set([
    'AM','AN','AT','BE','BY','HE','MY',
    'AND','BAD','BAT','BED','BET','CAB','CAN','CAR','CAT','DAD',
    'EAT','ERA','FAR','FAT','FED','GAG','GAL','GET','HAD','HAT',
    'HEN','HER','JAB','JAG','JAM','JAR','JET','LAB','LAD','LAG',
    'LET','MAD','MAN','MAT','MEN','MET','NAG','NET','RAG','RAM',
    'RAN','RAT','RED','TAB','TAG','TAN','TAR','TAX','TED','TEN',
    'THE','VAN','VAT','VET','YAM','YEN','YET',
    'HTML','XML'
]);

// A decoded Kannada fragment is only plausible as a genuine standalone word
// if it contains at least one consonant (ಕ-ಹ, which also covers ಳ/ೞ within
// that codepoint range). Nudi's uppercase standalone-syllable letters (see
// NUDI_A2U_STANDALONE above) mostly map to independent vowels, anusvara, or
// visarga on their own - so an all-uppercase acronym where every letter
// happens to be in that set (e.g. "KNB" -> ಏ+ಓ+ಃ) decodes to a vowel/visarga
// string with no consonant anywhere, which real Kannada words never look
// like. Used below to stop the all-standalone-letters override from
// swallowing genuine English acronyms that happen to only use
// standalone-mapped letters.
function _hasKannadaConsonant(str) {
    return /[ಕ-ಹ]/.test(str);
}

// Real English prose capitalizes short (<=4 letter) tokens as all-lowercase,
// Title Case, or ALL-CAPS (acronyms) - never with arbitrary internal case
// changes like "MAn". Nudi's own ASCII scheme, on the other hand, relies
// heavily on case to distinguish letters (e.g. "M"=ಒ, "A"=ಂ (anusvara),
// "n"=ಟಿ, so "MAn" = ಒಂಟಿ, "alone"), so a SHORT token with non-standard
// internal casing is a strong, purely-structural signal that it's Nudi
// encoding rather than a real English word - no need to actually decode it
// (which risks false-positives, e.g. "Kannada" itself happens to decode to
// a consonant-containing string via the Nudi map, but it's perfectly
// normal Title Case so is left alone here regardless of length).
//
// Deliberately scoped to token.length <= 4 (same bound as the
// all-uppercase/NUDI_A2U_STANDALONE check above) rather than applied to
// every token: longer real English words routinely use internal
// capitalization too - compound/brand names like "InScript", "JavaScript",
// "PowerPoint", "YouTube", "GitHub", "PayPal", "iPhone", "MacBook" - none of
// which are plausible as raw Nudi ASCII (a genuine multi-letter Nudi
// sequence beyond a couple of standalone-mapped units almost always needs
// extended-Latin marks for proper consonant+matra conjuncts, which
// LATIN_EXT_RE already filters out above). An earlier version of this
// check applied to tokens of any length and wrongly Nudi-decoded every one
// of those brand names (confirmed: "InScript" -> "IಟಿSಛಿಡಿiಠಿಣ").
function _hasPlausibleEnglishCasing(token) {
    if (token.length > 4) return true;
    const segments = token.split(/[^a-zA-Z]+/).filter(Boolean);
    if (segments.length === 0) return true;
    return segments.every(seg => /^[a-z]+$/.test(seg) || /^[A-Z][a-z]*$/.test(seg) || /^[A-Z]+$/.test(seg));
}

function _isEnglishToken(token, fullText, tokenStart) {
    if (!PURE_ASCII_WORD_RE.test(token)) return false;
    if (LATIN_EXT_RE.test(token)) return false;
    // Lowercase consonant code + anusvara/visarga code (dA=ಜಂ, kB=ಞಃ, ...)
    // is Nudi encoding, not an English word.
    if (/^[a-z][AB]$/.test(token)) return false;
    if (token.length === 1) {
        if (NUDI_SINGLE_UPPER.has(token) || NUDI_SINGLE_LOWER.has(token)) return false;
        return false;
    }
    const charBefore = tokenStart > 0 ? fullText[tokenStart - 1] : '';
    const charAfter = tokenStart + token.length < fullText.length ? fullText[tokenStart + token.length] : '';
    if (LATIN_EXT_RE.test(charBefore) || LATIN_EXT_RE.test(charAfter)) return false;
    // All-uppercase short tokens where every char is a valid standalone Nudi a2u key
    // are likely Nudi ASCII encoding, not English words - but only when decoding
    // them actually produces something that looks like a real Kannada syllable
    // (has a consonant), not just a run of independent vowels/visarga (see
    // _hasKannadaConsonant above). Without this check, most 2-4 letter English
    // acronyms/initialisms get silently swallowed as "Nudi encoding" purely
    // because most letters of the alphabet happen to have a standalone mapping.
    if (token.length >= 2 && token.length <= 4 && token === token.toUpperCase()) {
        let allNudiStandalone = true;
        for (let i = 0; i < token.length; i++) {
            if (!NUDI_A2U_STANDALONE.has(token[i])) {
                allNudiStandalone = false;
                break;
            }
        }
        if (allNudiStandalone && !EN_UPPER_NUDI_CONFLICT.has(token)) {
            let decoded = '';
            for (let i = 0; i < token.length; i++) decoded += A2U_MAP[token[i]] || token[i];
            if (_hasKannadaConsonant(decoded)) return false;
        }
    }
    if (!_hasPlausibleEnglishCasing(token)) return false;
    return true;
}

function _replace_vattakshara(txt) {
    // Subjoined (vattakshara) consonants are emitted with a U+0001 marker
    // instead of a bare halant so _fix_conjuncts can reorder them into
    // proper conjuncts (base + ್ + consonant) without touching genuine
    // word-final halants like ನನ್.
    Object.entries(VATTAKSHARA_MAP).forEach(([k, v]) => {
        const baseConsonant = v.slice(0, -1);
        txt = txt.split(k).join(VATT_MARKER + baseConsonant);
    });
    Object.entries(OTHER_MAP).forEach(([k, v]) => {
        txt = txt.split(k).join(v);
    });
    return txt;
}

// 'À' only ever has meaning as the second character of a base-consonant
// "add the inherent vowel" unit (e.g. 'PÀ' -> ಕ, 'zÀ' -> ದ, and as the
// middle byte of longer forms like 'PÀÄ' -> ಕು) - every such unit already
// exists as its own key in consonantMaps/A2U_MAP, tried longest-first in
// _replace_from_map. So by the time this runs, any 'À' still sitting in
// the text literally could not have paired with anything: it's orphaned,
// structurally meaningless noise, not a different valid construct. Some
// Nudi typing tools/versions apparently emit a redundant 'À' after
// certain vowel-sign keys anyway (confirmed via a real document: "zÉÀ..."
// for ದೆ..., where 'É' alone already completes ದೆ and the following 'À'
// has nothing left to attach to) - previously this was left in place as
// literal garbage (e.g. "ಎಂದೆÀನ್ನುತ್ತಾಳೆ" instead of "ಎಂದೆನ್ನುತ್ತಾಳೆ").
// Run right after _replace_from_map, before reph/vattakshara, so a stray
// 'À' can't also block THEIR pattern matching (e.g. sitting between a
// matra and 'ð' would prevent the reph regex from matching at all).
function _strip_orphan_a_marker(txt) {
    return txt.replace(/À/g, '');
}

// Same class of bug as the orphaned 'À' above, this time for 'É' (the
// short-e/i/o vowel-sign key, e.g. 'PÉ' -> ಕೆ, 'PÉÃ' -> ಕೇ). 'É' is always
// a suffix attached to a single preceding base-consonant letter - there is
// no key anywhere in consonantMaps/A2U_MAP that contains "ÉÉ" together, so
// two 'É' in a row with no base consonant between them can only mean a
// redundant duplicate keystroke, not two independent syllables (a genuine
// second short-e syllable needs its own consonant letter in between, e.g.
// "PÉ£É" = ಕೆನೆ, not "PÉÉ"). Confirmed via a real document: "...ªÉÉÃ"
// should be "...ವೇ" (the 3-char key 'ªÉÃ' -> ವೇ can't match through the
// extra É), but came out "...ವೆೆÃ" instead - the leftover, unrecognized
// second É fell through to the generic `/É/g -> 'ೆ'` cleanup at the very
// end of the pipeline and got wrongly rendered as its own vowel sign.
// Unlike the 'À' fix (which cleans up leftover noise *after*
// _replace_from_map has had its chance), this must run *before*
// _replace_from_map: the whole problem is that the extra É stops the
// intended 3/4-char 'É'-based key (ÉÃ, ÉÊ, ÉÆ, ÉÆÃ, ...) from matching in
// the first place - collapsing on the raw text lets that key match as
// designed instead of falling back to a shorter, wrong one.
function _collapse_duplicate_e_marker(txt) {
    return txt.replace(/É{2,}/g, 'É');
}

// Nudi's documented/canonical vattakshara typing order is base-consonant +
// (vowel-sign byte(s), e.g. 'À'/'Á'/'É'/'ÉÆÃ'/...) + vattu-marker-byte - the
// vowel is typed first, then the subjoined consonant is added on top of it
// (see _fix_conjuncts' 'PÀå' -> ಕ್ಯ and 'QÌ' -> ಕ್ಕಿ examples). But some
// documents type the vattu marker BEFORE the vowel-sign byte(s) instead
// (e.g. '¥æÀ' for ಪ್ರ - '¥' pa + 'æ' ra-vattu + 'À' plain-vowel marker,
// confirmed via a real repro: "¥æÀPÁgÀzÀ°è" should be "ಪ್ರಕಾರದಲ್ಲಿ" but the
// leading '¥' was left untranslated as literal ASCII). In that order, the
// vattu byte sits between the base consonant and its vowel-sign byte(s), so
// no A2U_MAP key can ever match the base consonant at all (e.g. '¥À' is a
// valid key, but '¥æÀ' isn't, and never will be no matter how many keys
// exist) - the base consonant is left completely stranded, not just one
// syllable off like the reph case. This isn't unique to 'À': the same
// stranding happens for every vowel-sign run a consonant can take. Two
// different shapes exist (confirmed against consonantMaps' actual keys):
// direct-attach markers that need nothing else ('PÁ'->ಕಾ, 'PÉ'/'PÉÃ'/
// 'PÉÊ'/'PÉÆ'/'PÉÆÃ'->ಕೆ/ಕೇ/ಕೈ/ಕೊ/ಕೋ, 'PË'->ಕೌ), and markers that are only
// ever valid as a suffix ON TOP OF the plain-vowel 'À' ('PÀÄ'->ಕು,
// 'PÀÆ'->ಕೂ, 'PÀÈ'->ಕೃ, plus the ¥/¥s-family's alternate 'PÀÅ'/'PÀÇ' u/uu
// bytes) - there is no bare 'PÄ'/'PÆ'/'PÈ' key anywhere, only 'PÀ'+that
// byte together. Confirmed all of these strand the base consonant the same
// way '¥æÀ' did: 'PæÁ'/'PæÉ'/'PæË' (direct-attach) and 'PæÀÄ'/'PæÀÆ'/
// 'PæÀÈ' (À-suffixed) all left the base consonant and/or trailing vowel
// byte as literal ASCII before this fix. Reordering vattu+vowel-run ->
// vowel-run+vattu before _replace_from_map runs turns this into the
// already-handled canonical order, letting the base consonant match
// normally; the vattu byte itself is untouched by this swap and still
// flows through _replace_vattakshara / _fix_conjuncts exactly as it does
// for the canonical typing order. Alternatives are listed longest-first
// (e.g. ÆÃ before Æ, ÀÄ before bare À) so a whole multi-byte run moves as
// one unit instead of the vattu only jumping past the run's first byte and
// splitting it apart.
//
// A third shape turned up via a real repro - "PÀtÚÂÃgÀÄ" (should be
// "ಕಣ್ಣೀರು") came out "ಕಣ್ಣÂÃರು": the retroflex-na family ('t' -> ಣ) has
// its own dedicated short/long-i suffix byte 'Â'/'ÂÃ' ('tÂ' -> ಣಿ, 'tÂÃ' ->
// ಣೀ) that no other consonant uses, so it needs the same base+suffix
// handling as the À/É groups above.
//
// A fourth, much larger shape also turned up while checking for other such
// cases: most consonants (31 of them, confirmed via consonantMaps - Q/QÃ
// for ki/kii, T/TÃ for khi/khii, and so on through every letter except the
// 't'/ಣ family above) don't use a suffix byte for short/long-i at all -
// they use a *completely separate* base letter with no shared prefix (e.g.
// 'Q' for ಕಿ has nothing to do with 'P' for ಕ). These letters are already
// complete, standalone map keys, so a vattu directly in front of one (e.g.
// 'æQ' for ಕ್ರಿ) strands nothing - but confirmed broken anyway ('æQ' came
// out "್ರಕಿ" instead of "ಕ್ರಿ") because the vattu still needs to end up
// *after* the letter it's modifying, same as every other case here. Long-i
// forms (QÃ, TÃ, ...) don't need their own explicit entry: swapping only
// the short letter leaves the trailing 'Ã' immediately after the vattu,
// and _a2u_deerga_handle (which already exists to catch exactly this kind
// of "lengthener left behind after reordering" case) picks it up correctly
// once _fix_conjuncts moves the vowel to the end of the conjunct - verified
// directly ('QæÃ' -> "ಕ್ರೀ" via the existing pipeline, no new code needed
// for the long forms). A few of these short letters are themselves a
// prefix of a different consonant's letter (e.g. 'r' -> ಡಿ vs 'rü' -> ಢಿ),
// so those pairs are listed longest-first to avoid splitting the longer
// one apart.
function _reorder_vattu_before_a_marker(txt) {
    const VOWEL_RUN = 'É(?:ÆÃ|Æ|Ê|Ã)?|À(?:Ä|Å|Æ|Ç|È)?|Â(?:Ã)?|[ÁË]|' +
        'rü|¢ü|¦ü|©ü|jhÄ|«Ä|Q|T|V|X|a|c|f|n|p|r|w|y|¢|¦|©|j|°|«|²|¶|¹|»|½';
    const re = new RegExp('([' + ASCII_VATTAKSHARA + '])(' + VOWEL_RUN + ')', 'g');
    return txt.replace(re, '$2$1');
}

// Four consonants (¥/pha, ¨/bha, q/dda, z/dha) mark aspiration with a
// trailing 's' digraph typed right after the base letter and before any
// vowel-sign byte - the canonical/only valid key order is base+'s'+vowel
// (e.g. '¨sÀ' -> ಭ, '¨sÁ' -> ಭಾ). Confirmed via a real document (4 separate
// words, so a recurring typing habit, not a typo): "¨ÀsnÖ" (should be
// "ಭಟ್ಟಿ"), "G¨ÀsAiÀÄ" ("ಉಭಯ"), "C£ÀÄ¨Às«¸ÀvÉÆqÀVvÀÄÛ" ("ಅನುಭವಿಸತೊಡಗಿತ್ತು"),
// "¥æÀ¨ÀsÄvÀézÀ" ("ಪ್ರಭುತ್ವದ") all typed the 's' *after* the vowel-sign byte
// instead of before it ('¨ÀsAiÀÄ' instead of '¨sÀAiÀÄ'). Same shape as the
// vattu-before-vowel bug above: with 's' sitting between the base letter
// and its vowel-sign byte, no A2U_MAP key can ever match ('¨À' matches on
// its own giving a bare ಭ-less consonant, or nothing at all matches and
// '¨' is stranded, depending on what follows) - reordering vowel-run+s ->
// s+vowel-run before _replace_from_map turns it into the canonical order.
function _reorder_aspirate_marker_before_vowel(txt) {
    const VOWEL_RUN = 'É(?:ÆÃ|Æ|Ê|Ã)?|À(?:Ä|Å|Æ|Ç|È)?|[ÁË]';
    const re = new RegExp('([¥¨qz])(' + VOWEL_RUN + ')s', 'g');
    return txt.replace(re, '$1s$2');
}

// 'ð' encodes reph - the "ರ್" that precedes a following consonant cluster
// in normal reading order (ಕರ್ನಾಟಕ = ಕ + ರ್ + ನಾ + ಟಕ, ಸರ್ಕಾರ = ಸ + ರ್ +
// ಕಾ + ರ, ...). Nudi's typing convention, though, has the typist finish the
// base+matra keystrokes for the FOLLOWING syllable first and press the
// reph key afterward (matching how the legacy bitmap font's glyph was
// keyed in), so in the raw ASCII text 'ð' always arrives one syllable too
// late relative to where it belongs in Unicode. Without this fix it was
// left in place and blindly mapped to a bare 'ರ' (see OTHER_MAP below),
// producing badly out-of-order results like "ಕನಾðಟಕ" -> "ಕನಾರಟಕ" instead
// of "ಕರ್ನಾಟಕ". Fixed by moving "ರ್" to immediately before the syllable
// (one base consonant + optional dependent vowel sign) that immediately
// precedes 'ð', once _replace_from_map has already turned the surrounding
// text into real Unicode consonants - run before _replace_vattakshara so
// there's no VATT_MARKER in the text yet to complicate the lookbehind.
function _replace_reph(txt) {
    const re = new RegExp('([ಕ-ಹೞ])([' + DEP_VOWELS + ']?)ð', 'g');
    return txt.replace(re, 'ರ್$1$2');
}

function _fix_conjuncts(txt) {
    let result = txt;
    // Reorder vattakshara markers into conjuncts. In Nudi the subscript
    // consonant is typed after the base akshara (including its vowel sign):
    //   PÀå  = ಕ + [ya-vattu]      -> ಕ್ಯ
    //   QÌ   = ಕಿ + [ka-vattu]     -> ಕ್ಕಿ
    // i.e. base + matra? + C  ->  base + ್ + C + matra
    // Repeated to resolve chains (base + two vattus -> triple conjunct).
    const re = new RegExp('([ಕ-ಹೞ])([ಾಿೀುೂೃೄೆೇೈೊೋೌ]?)' + VATT_MARKER + '([ಕ-ಹೞ])');
    while (re.test(result)) {
        result = result.replace(new RegExp(re.source, 'g'), '$1್$3$2');
    }
    // Any marker left without a preceding base falls back to a plain halant
    result = result.replace(new RegExp(VATT_MARKER, 'g'), '್');
    result = result.replace(/([ಕ-ಹ])(್){2,}/g, '$1$2');
    return result;
}

// Handles a u/uu/vocalic-r vowel byte (Ä/Å/Æ/Ç/È) left stranded right after
// a vattakshara conjunct instead of attaching as a vowel. Confirmed via a
// real document: "ZÀPÀëÄ" (should be "ಚಕ್ಷು") came out "ಚಕ್ಷÄ". These bytes
// are only ever valid as the third character of a base+'À'+byte key (e.g.
// 'PÀÄ' -> ಕು - see the '¥æÀÄ'/orphaned-'À' fix above for the same "always
// needs À" rule) - but in the canonical vattu order (base+'À'+vattu, e.g.
// 'PÀë' -> ಕ್ಷ for "ksha"), the vattu byte sits exactly where a following
// u-vowel's required 'À' would have gone, and there's no second 'À' to
// spare: "PÀëÄ" only has one 'À', already spent forming the base consonant
// before the vattu. So the base+vattu conjunct forms correctly (ಕ್ಷ), but
// the trailing 'Ä' has nothing left to pair with and was left as literal
// ASCII after _fix_conjuncts, instead of attaching to the conjunct's final
// (subjoined) consonant the way Kannada script actually attaches a vowel
// to a conjunct - on its last member, not its first. Must run after
// _fix_conjuncts (so there's a real Unicode consonant immediately before
// the stray byte to attach to) and is safe for the same "orphan byte"
// reason as _strip_orphan_a_marker/_collapse_duplicate_e_marker: any of
// these five bytes still surviving as literal ASCII this late could not
// have matched any A2U_MAP key (that pass already had its chance), so
// there is nothing else they could legitimately mean.
function _a2u_attach_orphan_u_vowel(txt) {
    return txt
        .replace(/([ಕ-ಹೞ])[ÄÅ]/g, '$1ು')
        .replace(/([ಕ-ಹೞ])[ÆÇ]/g, '$1ೂ')
        .replace(/([ಕ-ಹೞ])È/g, '$1ೃ');
}

// Handles the "lengthen the preceding short vowel sign" suffix bytes that
// arrive detached from their vowel sign after vattakshara reordering. In a
// vattu conjunct (base + short vowel + subjoined consonant), _fix_conjuncts
// moves the vowel sign to the end of the cluster, but a trailing lengthen
// byte typed right after the original vowel sign stays put - so by this
// point the two are adjacent again and can be merged. Ã lengthens ಿ/ೆ/ೊ
// (short i/e/o -> long ī/ē/ō); Æ lengthens ು (short u -> long ū). Standalone
// consonant+vowel forms (QÃ -> ಕೀ, PÀÆ -> ಕೂ, ...) are already resolved
// earlier via the direct A2U_MAP lookup and never reach this function.
function _a2u_deerga_handle(txt) {
    txt = txt.replace(/([ಿೆೇೊ])Ã/g, (match, g1) => {
        const UNI_DEERGA_MAP = {'ಿ': 'ೀ', 'ೆ': 'ೇ', 'ೊ': 'ೋ'};
        return UNI_DEERGA_MAP[g1] || g1;
    });
    txt = txt.replace(/ುÆ/g, 'ೂ');
    return txt;
}

function _replace_from_map(txt) {
    let result = txt;
    A2U_KEYS.forEach(key => {
        if (key.length > 0 && key !== 'ï') {
            const regex = new RegExp(key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g');
            result = result.replace(regex, A2U_MAP[key]);
        }
    });
    return result;
}

// Resolves vowel-sign bytes (É/Æ/Ã/Ê/Á/Ë) that survive _replace_from_map
// without having been consumed as part of an atomic per-consonant key (e.g.
// 'PÉÆÃ' -> ಕೋ). This happens whenever a document was typed with a
// redundant 'À' between the base consonant and its vowel-sign keys - e.g.
// 'PÀÉÆÃ' instead of the atomic 'PÉÆÃ' - which is common in real Nudi
// documents (the typist completes the plain "ಕ" glyph first, then applies
// matra keys on top of it). _strip_orphan_a_marker already consumes that
// redundant 'À' when it's literally left over, but here it's not left
// over - 'PÀ' itself matches a valid shorter key ('ಕ') before the longer
// 'PÉÆÃ' key ever gets a chance, since À sits between P and É. What's left
// after that is the bare vowel-sign byte (É in some combination, or Á, or
// Ë) with nothing to attach it to syntactically except the plain consonant
// Unicode char immediately before it. This mirrors the same vowel forms
// already defined per-consonant in consonantMaps (ೆ/ೇ/ೈ/ೊ/ೋ/ಾ/ೌ), just
// applied generically instead of tied to one specific base letter. Á and Ë
// were confirmed broken by the exact same redundant-'À' pattern via a real
// report - "K£ÀÁzÀgÀÆ" (should be "ಏನಾದರೂ") came out "ಏನÁದರೂ" (the
// canonical key is the direct-attach '£Á' -> ನಾ, no 'À' needed at all, but
// '£À' -> ನ matches first and strands the 'Á'). Must run before
// _a2u_deerga_handle, since that function only recognizes already-
// converted Unicode matras (ಿ/ೆ/ೇ/ೊ) immediately before a literal 'Ã' - if
// a bare 'É' were left unconverted at that point (as it was here
// previously, via a fallback that ran AFTER deerga_handle), deerga_handle's
// pattern would never match and 'Æ'/'Ã' would leak through unconverted as
// literal characters.
function _a2u_post_process(txt) {
    return txt
        .replace(/ÉÆÃ/g, 'ೋ')
        .replace(/ÉÆ/g, 'ೊ')
        .replace(/ÉÊ/g, 'ೈ')
        .replace(/ÉÃ/g, 'ೇ')
        .replace(/É/g, 'ೆ')
        .replace(/Á/g, 'ಾ')
        .replace(/Ë/g, 'ೌ');
}

function _replace_a2u_anuswara_visarga(txt) {
    return txt.replace(/A/g, 'ಂ').replace(/B/g, 'ಃ');
}

// ============================================================
// PIVOT-BASED FONT MAPPINGS
// Ported from the KGP Word-macro rule tables (tools/macro-extracts/*.json;
// see tools/MACRO-REVIEW.md). Each source encoding is substituted
// byte-by-byte into Nudi ASCII fragments, then run through the existing,
// well-tested Nudi <-> Unicode engine defined in this file:
//   a2u:  X --charmap-->                Nudi ASCII --asciiToUnicode(nudi)--> Unicode
//   u2a:  Unicode --unicodeToASCII(nudi)--> Nudi ASCII --charmap(inverse)--> X
// A handful of macro rules performed true cursor-based reordering rather
// than a per-byte substitution; those byte codes are intentionally left
// out of the maps below (pass through unchanged) - see tools/pivot-maps.generated.js
// for full per-font coverage notes (regenerate with tools/generate-pivot-maps.py).
// ============================================================

// Prakashak (Praja) - 213/224 byte codes mapped (11 unresolved: 62,106,107,109,135,193,209,236,251,255,256)
const PRAKASH2_X2NUDI = {33:"C",34:"\u00c4",35:"E",36:"F",37:"G",38:"H",39:"\u00a5",40:"J",41:"K",42:"L",43:"M",44:"\u00e1",45:"\u00f6",46:"\u00d4",47:"B",48:"0",49:"1",50:"2",51:"3",52:"4",53:"5",54:"6",55:"7",56:"8",57:"9",58:"v",59:"z",60:"\u00a3",61:"\u00a5",63:"\u00af",64:"t\u00c2",65:"\u00aa",66:"\u00b1",67:"\u00b5",68:"\u00b8",69:"\u00ba",70:"e\u00d5",71:"R",72:"Y",73:"d",74:"k",75:"l",76:"t",77:"I",78:"\u00a7",79:"Ai\u00c0",80:"\u00ae",81:"d\u00d5",82:"Q",83:"T",84:"V",85:"a",86:"\u00bf",87:"f",88:"n",89:"j",90:"r",91:"\u00fe",92:"w",93:"\u00a2",94:"\u00a4",95:"\u00a6",96:"\u00c9\u00c3",97:"\u00ab",98:"\u00b0",99:"\u00b6",100:"\u00b9",101:"\u00bb",102:"\u00bd",103:"f\u00a9",104:"\u00ac",105:"\u00b2",106:"\u00c0",107:"s",108:"s",110:"\u008b",111:"\u00c1",112:"\u00c2",113:"D",114:"\u00c6",115:"h",116:"i\u00c1",117:"\u00c9",118:"\u00a9",119:"\u00f5\u00c9",120:"\u00cc",121:"\u00f1",122:"\u00cb",123:"i",124:"\u00c3",125:"\u00ef",126:"\u00f0",127:"\u007f",128:"\u0080",129:"\u0081",130:"\u0082",131:"\u0083",132:"\u00f6",133:"\u00f6",134:"\u00d8",136:"\u0088",137:"\u00db",138:"\u00dd",139:"\u00df",140:"\u00e0",141:"\u008d",142:"\u008e",143:"\u008f",144:"\u0090",145:"\u00e1",146:"\u00e2",147:"\u00f9",148:"\u00fa",149:"\u0095",150:"\u00bf",151:"\u00be",152:"\u0098",153:"\u0099",154:"\u00e8",155:"\u00eb",156:"\u00ec",157:"\u009d",158:"\u009e",159:"\u009f",160:"\u00c9\u00c6",161:"\u00cd",162:"\u00ce",163:"\u00cf",164:"\u00d0",165:"\u00d1",166:"\u00f6",167:"\u00d3",168:"\u00f6",169:"\u00d5",170:"\u00d6",171:"\u00d7",172:"\u00ad",173:"\u00ad",174:"\u00da",175:"\u00f6",176:"\u00dc",177:"\u00f9",178:"\u00fa",179:"\u00bf",180:"\u00be",181:"\u00f6",182:"\u00e4",183:"\u00db\u00e5",184:"\u00db\u00e6",185:"\u00f6",186:"\u00e9",187:"\u00ea",188:"\u00f6",189:"\u00f6",190:"\u00f6",191:"\u00ee",192:"\u00ed",194:"\u00cc\u00f8",195:"\u00e2\u00ca",196:"\u00d6\u00e6",197:"\u00db\u00c8",198:"\u00db\u00ca",199:"\u00e5",200:"\u00e7",201:"\u00e0\u00e6",202:"\u00e6\u00c8",203:"\u00ec\u00e6",204:"\u00cc\u00eb",205:"\u00cc\u00e6",206:"\u00c9",207:"A\u00c9hi",208:"\u00f6",209:"\u00c6",210:"Ai\u00c9",211:"P",212:"U",213:"W",214:"Z",215:"\u00f6",216:"e",217:"m",218:"g",219:"q",220:"u",221:"\u00f6",222:"\u00f6",223:"\u00f6",224:"A",225:"\u00b2\u00e6",226:"\u00c8",227:"\u00ca",228:",",229:".",230:"\u00a8",231:"\u00f2",232:"\u00bc",233:"\u00db\u00e6",234:"\u00db\u00e5",235:"\u00eb",237:"\u00a5s",238:"S",239:"\u00f7",240:"\u00f7",241:"\u00f7",242:"O",243:"\u00f6",244:"\u00f7",245:"\u00f6",246:"X",247:"\u00f6",248:"N",249:"P\u00c0",250:"P\u00c9",251:"\u00c4",252:"b",253:"\u00f6",254:"\u00fe"};
// Akruti Mono - 189/189 byte codes mapped (0 unresolved: none)
const AKRUTI2_X2NUDI = {32:" ",33:"!",34:"\u00cc",35:"\u00cd",36:"\u00ce",37:"C",38:"\u00cf",39:"'",40:"(",41:")",42:"\u00d0",43:"\u00d1",44:",",45:"\u00f7",46:".",47:"/",48:"0",49:"1",50:"2",51:"3",52:"4",53:"5",54:"6",55:"7",56:"8",57:"9",58:":",59:";",60:"\u00f7",61:"=",62:"\u00f7",63:"?",64:"\u00d3",65:"D",66:"\u00d4",67:"\u00d5",68:"\u00d6",69:"E",70:"\u00d7",71:"\u00d8",72:"\u00d9",73:"L",74:"\u00da",75:"\u00db",76:"\u00dc",77:"\u00dd",78:"H",79:"K",80:"\u00de",81:"\u00df",82:"\u00e0",83:"\u00e1",84:"\u00e2",85:"J",86:"\u00e3",87:"\u00e4",88:"\u00e5",89:"L",90:"\u00e6",91:"\u00e8",92:"\u00ee",93:"\u00e9",94:"\u00ea",95:"\u00eb",96:"`",97:"M",98:"\u00ec",99:"\u00ed",100:"P",101:"N",102:"S",103:"U",104:"W",105:"O",106:"Y",107:"Z",108:"b",109:"d",110:"I",111:"F",112:"g",113:"k",114:"l",115:"n",116:"o",117:"e",118:"q",119:"qs",120:"t",121:"v",122:"x",123:"z",124:"zs",125:"\u00a3",126:"\u00a5",160:"\u00a0",161:"\u00bf",162:"\u00be",163:"\u00f5",165:"\u008a",166:"\u00db\u00e5",167:"\u00db\u00c8",168:"\u00db\u00e5",169:"\u00c3",170:"0",171:"\u00a9\u00fc",172:"\u00a2",173:"\u00cc\u00c8",174:"\u00db\u00e9",175:"\u00a6",176:"\u00c4",177:"\u00a7",178:"\u00a9",179:"\u00c6",180:"W",181:"\u00b1",182:"\u00b0",183:"\u00ae",184:"\u00b6",185:"t\u00c2",186:"\u00a2\u00fc",187:"w",188:"y",189:"\u00f8",190:"\u00a4",191:"\u00f2",192:"\u00aa",193:"\u00a5s",194:"m",195:"i",196:"\u00a6",197:"\u00a8s",198:"\u00ab",199:"u",200:"\u00af",201:"\u00b8",202:"f",203:"\u00f0",204:"Ai",205:"\u00b5",206:"\u00ac",207:"\u00a8",208:"V",209:"Q",210:"\u00ef",211:"c",212:"\u00bc",213:"\u00a6\u00fc",214:"\u00c1",215:"a",216:"T",217:"R",218:"r",219:"r\u00fc",220:"X",221:"\u00ba",222:"\u00b2\u00e6",223:"\u00e0\u00e7",224:"\u00fa",225:"\u00f9",226:"\u00c0",227:"\u00f1",228:"a",229:"\u00d6\u00e7",230:"\u00e1",231:"\u00db\u00e6",232:"\u00db\u00ca",233:"|",234:"\u00c9",235:"\u00e6\u00f8",236:"\u00cc\u00c8",238:"j",239:"p",240:"\u00f4",241:"\u00cb",242:"\u00c7",243:"\u00c5",244:"\u00ca",245:"\u008a",246:"\u008a",247:"\u00e7",248:"\u00cc",249:"\u00bd",250:"\u00b2",251:"\u00b9",252:"\u00fc",253:"\u00bb",254:"\u00bb",255:"B"};
// SriLipi KAN-850 - 208/218 byte codes mapped (10 unresolved: 35,45,60,144,157,158,173,183,226,228)
const SHREE2_X2NUDI = {32:" ",33:"!",34:"`",36:" ",37:"%",38:"-",39:"'",40:"(",41:")",42:"*",43:"+",44:",",46:".",47:"/",48:"0",49:"1",50:"2",51:"3",52:"4",53:"5",54:"6",55:"7",56:"8",57:"9",58:":",59:";",61:"=",62:"\u0086",63:"?",64:"B",65:"C",66:"D",67:"E",68:"F",69:"G",70:"H",71:"J",72:"K",73:"L",74:"M",75:"N",76:"O",77:"I",78:"W\u00c9",79:"u",80:"P",81:"Q",82:"\u00cc",83:"R",84:"S",85:"T",86:"\u00cd",87:"U",88:"V",89:"\u00ce",90:"W\u00c0",91:"W",92:"X",93:"\u00b2\u00e6",94:"\u00cf",95:"Y",96:"\u00d0",97:"Z",98:"a",99:"\u00d1",100:"b",101:"c",102:"\u00d2",103:"d",104:"e",105:"f",106:"\u00d3",107:"h",108:"\u00d4",109:"k",110:"\u00d5",111:"l",112:"m",113:"n",114:"\u00d6",115:"o",116:"p",117:"\u00d7",118:"q",119:"r",120:"\u00d8",121:"qs",122:"\u00d9",123:"rs",124:"t",125:"\u00f2",126:"t\u00c2",130:"\u00f3",131:"\u00c8",132:"\u00ca",133:"\u00ef",134:"\u00e7",135:"\u0086",136:"\u0087",137:"\u0085",138:"/",139:"\u00e6",141:"*",145:"\u00bf",146:"\u00bf",147:"\u00be",148:"\u00be",149:"\u00f9",150:"\u00e1",151:"\u00a2s",152:"\u0084",153:"\u008c",154:"\u008c",155:"\u00e6",156:"\u00de",159:"\u00a7",160:"\u008c",161:"\u00da",162:"\u00cc\u00c8",163:"w",164:"\u00db",165:"x",166:"y",167:"\u00dc",168:"z",169:"\u00a2",170:"\u00dd",171:"zs",172:"_",174:"\u00a3",175:"\u00a4",176:"\u00df",177:"\u00a5",178:"\u00a6",179:"\u00e0",180:"\u00a5s",181:"\u00a6s",182:"_",184:"\u00a8",185:"\u00a9",186:"\u00e2",187:"\u00a8s",188:"\u00a9s",189:"\u00e3",190:"\u00e4",191:"Ai\u00c0",192:"\u00ac",193:"A\u00c4\u00c9",194:"\u00e5",195:"g",196:"j",197:"\u00e6",198:"\u00ae",199:"\u00af",200:"\u00b0",201:"\u00e8",202:"\u00aa",203:"\u00ab",204:"\u00e9",205:"\u00b1",206:"\u00b2",207:"\u00ea",208:"\u00b5",209:"\u00b6",210:"\u00eb",211:"\u00b8",212:"\u00b9",213:"\u00ec",214:"\u00ba",215:"\u00bb",216:"\u00ed",217:"\u00bc",218:"\u00bd",219:"\u00ee",220:"\u00c0",221:"\u00c1",222:"\u00c4\u00c1",223:"\u00c2",224:"\u00c3",225:"\u00c4",226:"\u00c5",227:"\u00c6",228:"\u00c7",229:"\u00c4",230:"\u00c9",231:"\u00ca",232:"\u00cb",233:"\u00e5",234:"\u00c8",235:"\u00f1",236:"\u00f0",237:"A",238:"\u00f5",239:"\u00f5\u00c9",240:"\u00cc\u00e6",241:"v",242:"\u00d1\u00ca",243:"\u00d6\u00e7",244:"\u00db\u00ca",245:"\u00db\u00f8",246:"\u00db\u00e5",247:"\u00db\u00e6",248:"\u00e0\u00e6",249:"\u00e6\u00ca",250:"\u00ec\u00e6",251:"P\u00eb",252:"Q\u00eb",253:"d\u00d5",254:"e\u00d5",255:"f\u00d5"};
// Surabhi KND-series - 190/224 byte codes mapped (34 unresolved: 127,128,129,130,131,132,133,134,135,136,137,138,139,140,141,142,143,144,145,146,147,148,149,150,151,152,153,154,155,156,157,158,159,173)
const SURABHI_X2NUDI = {32:" ",33:"!",34:"'",35:"#",36:"\u00b2\u00e7",37:"%",38:"&",39:"`",40:"(",41:")",42:"*",43:"+",44:",",45:"-",46:".",47:"/",48:"0",49:"1",50:"2",51:"3",52:"4",53:"5",54:"6",55:"7",56:"8",57:":",58:":",59:";",60:"<",61:"=",62:">",63:"?",64:"0",65:"1",66:"2",67:"3",68:"4",69:"5",70:"6",71:"7",72:"8",73:"9",74:"C",75:"D",76:"E",77:"F",78:"G",79:"H",80:"I",81:"J",82:"K",83:"L",84:"M",85:"N",86:"O",87:"A",88:"B",89:"P",90:"Q",91:"\u00cc",92:"\u00cc\u00e6",93:"R",94:"S",95:"T",96:"\u00cd",97:"U",98:"V",99:"\u00ce",100:"W",101:"X",102:"\u00cf",103:"Y",104:"\u00d0",105:"Z",106:"a",107:"\u00d1",108:"b",109:"c",110:"\u00d2",111:"d",112:"e",113:"f",114:"\u00d3",115:"\u00d4",116:"k",117:"\u00d5",118:"l",119:"m",120:"n",121:"\u00d6",122:"\u00d6\u00e7",123:"o",124:"p",125:"\u00d7",126:"q",160:"\u00f2",161:"r",162:"\u00d8",163:"qs",164:"rs",165:"\u00d9",166:"t",167:"u",168:"t\u00c2",169:"\u00da",170:"\u00db",171:"v",172:"w",174:"\u00db\u00f8",175:"\u00db\u00ca",176:"\u00db\u00e5",177:"\u00db\u00e7",178:"x",179:"y",180:"\u00dc",181:"z",182:"\u00a2",183:"\u00dd",184:"zs",185:"\u00a2s",186:"\u00de",187:"\u00a3",188:"\u00a4",189:"\u00df",190:"\u00a5",191:"\u00a6",192:"\u00e0",193:"\u00e0\u00e6",194:"\u00a5s",195:"\u00a6s",196:"\u00e1",197:"\u00a7",198:"\u00a8",199:"\u00a9",200:"\u00e2",201:"\u00a8s",202:"\u00a9s",203:"\u00e3",204:"\u00e4",205:"A\u00c4",206:"\u00ac",207:"\u00e5",208:"g",209:"j",210:"\u00e7",211:"\u00f0",212:"\u00ae",213:"\u00af",214:"\u00b0",215:"\u00e8",216:"\u00aa",217:"\u00ab",218:"\u00e9",219:"\u00bf",220:"\u00fa",221:"\u00b1",222:"\u00b2",223:"\u00ea",224:"\u00b5",225:"\u00b6",226:"\u00eb",227:"\u00b8",228:"\u00b9",229:"\u00ec",230:"\u00ba",231:"\u00bb",232:"\u00ed",233:"\u00bc",234:"\u00bd",235:"\u00ee",236:"\u00be",237:"\u00f9",238:"\u00fc",239:"\u00c0",240:"\u00c4",241:"\u00f5",242:"\u00c1",243:"\u00c2",244:"\u00c3",245:"\u00c4",246:"\u00c5",247:"\u00c6",248:"\u00c7",249:"\u00c8",250:"\u00f1",251:"\u00c9",252:"\u00ca",253:"\u00cb",254:"\u00ef",255:"\u0086"};
// ---- Second batch (2026-07-24): remaining 10 macro-derived encodings ----
// See tools/generate-pivot-maps.py / tools/pivot-maps.generated.js. Six of
// these target Nudi Mono directly (like the four maps above); four target
// Nudi Bi and need an extra hop through NUDIBI2MONO/NUDIMONO2BI (the
// ISM (KNTT-Nandi) - 187/191 byte codes mapped (4 unresolved: 35,226,227,230)
const ISMKNTT_X2NUDI = {32:" ",33:"!",34:"`",36:"\u00d4",37:"\u00f0",38:"\u00f2",39:"'",40:"(",41:")",42:"\u00b2\u00e6\u00c3",43:"|",44:",",45:"-",46:".",47:"/",48:"0",49:"1",50:"2",51:"3",52:"4",53:"5",54:"6",55:"7",56:"8",57:"9",58:":",59:";",60:"\u00a0",61:"\u00f7",62:"\u00f7",63:"?",64:"C",65:"D",66:"E",67:"F",68:"G",69:"H",70:"I",71:"J",72:"K",73:"L",74:"M",75:"N",76:"O",77:"A",78:"B",79:"P",80:"Q",81:"\u00cc",82:"R",83:"S",84:"T",85:"\u00cd",86:"U",87:"V",88:"\u00ce",89:"W",90:"X",91:"\u00cf",92:"Y",93:"\u00d0",94:"Z",95:"a",96:"\u00d1",97:"b",98:"c",99:"\u00d2",100:"d",101:"e",102:"f",103:"\u00d3",104:"h",105:"\u00d4",106:"k",107:"\u00d5",108:"l",109:"m",110:"n",111:"\u00d6",112:"o",113:"p",114:"\u00d7",115:"q",116:"r",117:"\u00d8",118:"qs",119:"r\u00fc",120:"\u00d9",121:"t",122:"u",123:"t\u00c2",124:"\u00da",125:"v",126:"w",160:"\u00a0",161:"\u00db",162:"x",163:"y",164:"\u00dc",165:"z",166:"\u00a2",167:"\u00dd",168:"zs",169:"\u00a2\u00fc",170:"\u00de",171:"\u00a3",172:"\u00a4",173:"\u00df",174:"\u00a5",175:"\u00a6",176:"\u00e0",177:"\u00a5s",178:"\u00a6\u00fc",179:"\u00f7",180:"\u00f7",181:"\u00e1",182:"\u00a7",183:"\u00a8",184:"\u00a9",185:"\u00e2",186:"\u00a8s",187:"\u00a9\u00fc",188:"\u00e3",189:"\u00e4",190:"Ai",191:"\u00ac",192:"\u00e5",193:"g",194:"j",195:"\u00e6",196:"\u00ae",197:"\u00af",198:"\u00b0",199:"\u00e8",200:"\u00aa",201:"\u00ab",202:"\u00e9",203:"\u00b1",204:"\u00b2",205:"\u00ea",206:"\u00b5",207:"\u00b6",208:"\u00eb",209:"\u00b8",210:"\u00b9",211:"\u00ec",212:"\u00ba",213:"\u00bb",214:"\u00ed",215:"\u00bc",216:"\u00bd",217:"\u00ee",218:"\u00c0",219:"\u00c1",220:"\u00f5",221:"\u00c2",222:"\u00c3",223:"\u00c4",224:"\u00c6",225:"i",226:"\u00c5",227:"\u00c7",228:"\u00c8",229:"\u00f1",231:"\u00ca",232:"\u00cb",233:"\u00ef",234:"\u00db\u00c8",235:"\u00db\u00ca",236:"\u00db\u00e9",237:"\u00cc\u00c8",238:"\u00e7\u00ca",239:"\u00e6",240:"\u00e6",241:"\u00e7",242:"\u00f7",243:"\u00f7",244:"\u00f7",245:"\u00f7",246:"\u00f7",247:"\u00f7",248:"\u00f7",249:"\u00f7",250:"\u00f7",251:"\u00f7",252:"\u00f7",253:"\u00f7",254:"\u00f7",255:"\u00f7"};
// Dharma ILs - 221/223 byte codes mapped (2 unresolved: 226,227)
const DHARMA_X2NUDI = {33:"!",34:"\"",35:"/",36:"$",37:"%",38:"&",39:"'",40:"(",41:")",42:"*",43:"+",44:",",45:"-",46:".",47:"/",48:"0",49:"1",50:"2",51:"3",52:"4",53:"5",54:"6",55:"7",56:"8",57:"9",58:":",59:";",60:"<",61:"=",62:">",63:"?",64:"@",65:"C",66:"D",67:"E",68:"F",69:"G",70:"H",71:"I",72:"J",73:"K",74:"L",75:"M",76:"N",77:"O",78:"A",79:"B",80:"P\u00c0",81:"P",82:"Q",83:"\u00cc",84:"R",85:"S",86:"T",87:"\u00cd",88:"U\u00c0",89:"U",90:"V",91:"[",92:"\\",93:"]",94:"\u00ce",95:"W\u00c0",96:"W",97:"X",98:"\u00cf",99:"Y",100:"\u00d0",101:"Z\u00c0",102:"Z",103:"a",104:"\u00d1",105:"b\u00c0",106:"b",107:"c",108:"\u00d2",109:"d",110:"e",111:"f",112:"\u00d3",113:"h",114:"\u00d4",115:"k",116:"\u00d5",117:"l",118:"m",119:"n",120:"\u00d6",121:"o\u00c0",122:"o",123:"{",124:"|",125:"}",126:"p",127:"\u007f",128:"\u0080",129:"\u0081",130:"q\u00c0",131:"q",132:"r",133:"\u00d8",134:"q\u00c0\u00fc",135:"\u0087\u00c0",136:"r\u00fc",137:"\u00d9",138:"t",139:"u",140:"t\u00c2",141:"\u008d",142:"\u008e",143:"\u008f",144:"\u0090",145:"\u00db",146:"x\u00c0",147:"x",148:"y",149:"\u008b",150:"z\u00c0",151:"z",152:"\u00a2",153:"\u00dd",154:"z\u00c0\u00fc",155:"z\u00fc",156:"\u00a2\u00fc",157:"\u009d",158:"\u009e",159:"\u00a3",160:"\u00a0",161:"\u00a4",162:"\u00df",163:"\u00a5\u00c0",164:"\u00a5",165:"\u00a6",166:"\u00e0",167:"\u00a5\u00c0\u00fc",168:"\u00a8\u00c0",169:"\u00a6\u00fc",170:"\u00e1",171:"\u00a7",172:"\u00a8",173:"\u00a9",174:"\u00e2",175:"\u00a8\u00c0\u00fc",176:"\u00a8\u00fc",177:"\u00a9\u00fc",178:"\u00e3",179:"\u00aa\u00c0",180:"\u00aa\u00c0i",181:"\u00ab",182:"\u00aa\u00c9",183:"\u00e4",184:"Ai\u00c0",185:"Ai\u00c0i",186:"\u00ac",187:"Ai\u00c9",188:"\u00e5",189:"g\u00c0",190:"g",191:"j",192:"\u00e6",193:"\u00e7",194:"\u00ae",195:"\u00af",196:"\u00b0",197:"\u00e8",198:"\u00aa\u00c0",199:"\u00aa",200:"\u00ab",201:"\u00e9",202:"\u00b1\u00c0",203:"\u00b1",204:"\u00b2",205:"\u00ea",206:"\u00b5\u00c0",207:"\u00b5",208:"\u00b6",209:"\u00eb",210:"\u00b8\u00c0",211:"\u00b8",212:"\u00b9",213:"\u00ec",214:"\u00ba\u00c0",215:"\u00ba",216:"\u00bb",217:"\u00ed",218:"\u00bc\u00c0",219:"\u00ed",220:"\u00bd",221:"\u00ee",222:"\u00c1",223:"i\u00c1",224:"\u00c4",225:"\u00c6",226:"\u00c5",227:"\u00c7",228:"\u00c8",229:"\u00c9",230:"\u00c3",231:"\u00ca",232:"\u00cb",233:"\u00c4\u00cb",234:"\u00ef",235:"\u00c4\u00ef",236:"\u00f0",237:"\u00f2",238:"\u00db\u00e6",239:"\u00cc\u00e6",240:"\u00e0\u00e6",241:"\u00cc\u00c8",242:"\u00ec\u00e6",243:"\u00fb",244:"\u00b2\u00e6",245:"\u00d7",246:"\u00da",247:"v\u00c0",248:"v",249:"w",250:"\u00de",251:"\u00a3\u00c0",252:"\u00e4",253:"\u00dc",254:"\u00fe",255:"\u00ff"};
// Janna Mono - 220/224 byte codes mapped (4 unresolved: 172,219,223,256)
const JANNA_X2NUDI = {33:"!",34:"C",35:"D",36:"E",37:"\u00f4",38:"F",39:"\u008b",40:"(",41:")",42:"*",43:"\u00f5\u00c9",44:",",45:"-",46:".",47:"/",48:"0",49:"1",50:"2",51:"3",52:"4",53:"5",54:"6",55:"7",56:"8",57:"9",58:":",59:";",60:"G",61:"\u00f5",62:"H",63:"?",64:"I",65:"J",66:"K",67:"L",68:"M",69:"N",70:"O",71:"A",72:"B",73:"P\u00c0",74:"R",75:"U\u00c0",76:"W\u00c0",77:"Y",78:"Z\u00c0",79:"b\u00c0",80:"d",81:"h",82:"k",83:"l",84:"q\u00c0",85:"qs\u00c0",86:"t",87:"v\u00c0",88:"x\u00c0",89:"z\u00c0",90:"zs\u00c0",91:"\u00a3\u00c0",92:"\u00a5\u00c0",93:"\u00a5s\u00c0",94:"\u00a7",95:"_",96:"`",97:"\u00a8s\u00c0",98:"Ai\u00c0",99:"g\u00c0",100:"\u00ae",101:"\u00aa\u00c0",102:"\u00b1\u00c0",103:"\u00b5\u00c0",104:"\u00b8\u00c0",105:"\u00ba\u00c0",106:"\u00bc\u00c0",107:"Q",108:"T",109:"V",110:"X",111:"a",112:"c",113:"f",114:"n",115:"r",116:"rs",117:"w",118:"y",119:"\u00a2",120:"\u00a2s",121:"\u00a4",122:"\u00a6",123:"\u00a6s",124:"\u00a9",125:"\u00a9s",126:"\u00ac",127:"j",128:"\u0080",129:"\u00af",130:"\u00ab",131:"\u00b6",132:"\u00b2",133:"\u00b9",134:"\u00bb",135:"\u00bd",136:"P",137:"S",138:"U",139:"W",140:"Z",141:"b",142:"e",143:"m",144:"q",145:"qs",146:"u",147:"v",148:"x",149:"z",150:"zs",151:"\u00a3",152:"\u00a5",153:"\u00a5s",154:"\u00a8",155:"\u00a8s",156:"g",157:"\u00b0",158:"\u00aa",159:"\u00b5",160:"\u00b1",161:"\u00b8",162:"\u00ba",163:"\u00bc",164:"\u00c4",165:"\u00c1",166:"\u00c3",167:"i\u00c1",168:"\u00ef",169:"t\u00c2",170:"\u0086",171:"\u00c6",172:"\u008b",173:"\u00c8",174:"\u00ca",175:"\u00f5\u00c1",176:"j",177:"\u00f0",178:"\u00cc",179:"\u00cd",180:"\u00ce",181:"\u00cf",182:"\u00b1",183:"\u00d1",184:"\u00d2",185:"\u00d3",186:"\u00d4",187:"\u00d5",188:"\u00d6",189:"\u00d7",190:"\u00d8",191:"\u00d9",192:"\u00da",193:"\u00db",194:"\u00dc",195:"\u00dd",196:"\u00de",197:"\u00df",198:"\u00e0",199:"\u00e1",200:"\u00e2",201:"\u00e3",202:"\u00e4",203:"\u00e5",204:"\u00e7",205:"\u00e8",206:"\u00e9",207:"\u00eb",208:"\u00ea",209:"\u00ec",210:"\u00ed",211:"\u00ee",212:"\u00db\u00e6",213:"\u00cc\u00e6",214:"\u00e0\u00e6",215:"\u00cc\u00c8",216:"\u00db\u00c8",217:"\u00db\u00ca",218:"\u00db\u00e5",219:"\u00c5",220:"\u00d1\u00ca",221:"\u00ec\u00e6",222:"\u00e7",223:"\u00c7",224:"\u00b2\u00e6",225:"C",226:"'",227:"P\u00c9",228:"S\u00c9",229:"U\u00c9",230:"W\u00c9",231:"Z\u00c9",232:"b\u00c9",233:"e\u00c9",234:"m\u00c9",235:"q\u00c9",236:"qs\u00c9",237:"u\u00c9",238:"v\u00c9",239:"x\u00c9",240:"z\u00c9",241:"zs\u00c9",242:"\u00a3\u00c9",243:"\u00a5\u00c9",244:"\u00a5s\u00c9",245:"\u00a8\u00c9",246:"\u00a8s\u00c9",247:"Ai\u00c9",248:"g\u00c9",249:"\u00af\u00c9",250:"\u00aa\u00c9",251:"\u00b5\u00c9",252:"\u00b1\u00c9",253:"\u00b8\u00c9",254:"\u00ba\u00c9",255:"\u00bc\u00c9"};
// SriLipi 850 - 201/208 byte codes mapped (7 unresolved: 60,155,156,157,158,226,228)
const SRILIPI850_X2NUDI = {32:" ",33:"!",34:"`",35:"*",36:" ",37:"%",38:"-",39:"'",40:"(",41:")",42:"*",43:"+",44:",",45:"-",46:".",47:"/",48:"0",49:"1",50:"2",51:"3",52:"4",53:"5",54:"6",55:"7",56:"8",57:"9",58:":",59:";",61:"=",62:"\u0086",63:"?",64:"B",65:"C",66:"D",67:"E",68:"F",69:"G",70:"H",71:"J",72:"K",73:"L",74:"M",75:"N",76:"O",77:"I",78:"\u00b2\u00e6",79:"\u00f2",80:"P",81:"Q",82:"\u00cc",83:"R",84:"S",85:"T",86:"\u00cd",87:"U",88:"V",89:"\u00ce",90:"W\u00c0",91:"W",92:"X",93:"W\u00c9",94:"\u00cf",95:"Y",96:"\u00d0",97:"Z",98:"a",99:"\u00d1",100:"b",101:"c",102:"\u00d2",103:"d",104:"e",105:"f",106:"\u00d3",107:"h",108:"\u00d4",109:"k",110:"\u00d5",111:"l",112:"m",113:"n",114:"\u00d6",115:"o",116:"p",117:"\u00d7",118:"q",119:"r",120:"\u00d8",121:"qs",122:"rs",123:"\u00d9",124:"t",125:"u",126:"t\u00c2",138:"/",144:"\u00f3",145:"\u00bf",146:"\u00bf",147:"\u00be",148:"\u00be",149:"\u00f9",150:"_",151:"_",152:"\u0084",153:"\u008c",154:"\u008c",159:"\u00a7",160:"\u008c",161:"\u00da",162:"v",163:"w",164:"\u00db",165:"x",166:"y",167:"\u00dc",168:"z",169:"\u00a2",170:"\u00dd",171:"zs",172:"\u00a2s",173:"\u00de",174:"\u00a3",175:"\u00a4",176:"\u00df",177:"\u00a5",178:"\u00a6",179:"\u00e0",180:"\u00a5s",181:"\u00a6s",182:"\u00e1",183:"\u00a7",184:"\u00a8",185:"\u00a9",186:"\u00e2",187:"\u00a8s",188:"\u00a9s",189:"\u00e3",190:"\u00e4",191:"Ai\u00c0",192:"\u00ac",193:"A\u00c4\u00c9",194:"\u00e5",195:"g",196:"j",197:"\u00e7",198:"\u00ae",199:"\u00af",200:"\u00b0",201:"\u00e8",202:"\u00aa",203:"\u00ab",204:"\u00e9",205:"\u00b1",206:"\u00b2",207:"\u00ea",208:"\u00b5",209:"\u00b6",210:"\u00eb",211:"\u00b8",212:"\u00b9",213:"\u00ec",214:"\u00ba",215:"\u00bb",216:"\u00ed",217:"\u00bc",218:"\u00bd",219:"\u00ee",220:"\u00c0",221:"\u00c1",222:"\u00c4\u00c1",223:"\u00c2",224:"\u00c3",225:"\u00c4",226:"\u00c5",227:"\u00c6",228:"\u00c7",229:"\u00c4",230:"\u00c9",231:"\u00ca",232:"\u00cb",233:"\u00ef",234:"\u00c8",235:"\u00f1",236:"\u00f0",237:"A",238:"\u00f5",239:"\u00f5\u00c9",240:"\u00cc\u00e6",241:"\u00cc\u00f8",242:"\u00d1\u00ca",243:"\u00d6\u00e6",244:"\u00db\u00ca",245:"\u00db\u00f8",246:"\u00db\u00e5",247:"\u00db\u00e6",248:"\u00e0\u00e6",249:"\u00e6\u00ca",250:"\u00ec\u00e6",251:"P\u00eb",252:"Q\u00eb",253:"d\u00d5",254:"e\u00d5",255:"f\u00d5"};
// Shree Deccan - 207/224 byte codes mapped (17 unresolved: 36,45,60,128,129,141,142,143,144,157,158,172,173,182,198,199,200)
const SHREEDECCAN_X2NUDI = {32:" ",33:"!",34:"`",35:"\u00bf",37:"%",38:"-",39:"'",40:"(",41:")",42:"*",43:"+",44:",",46:".",47:"/",48:"0",49:"1",50:"2",51:"3",52:"4",53:"5",54:"6",55:"7",56:"8",57:"9",58:":",59:";",61:"=",62:"\u0086",63:"?",64:"B",65:"C",66:"D",67:"E",68:"F",69:"G",70:"H",71:"J",72:"K",73:"L",74:"M",75:"N",76:"O",77:"I",78:"W\u00c9",79:"u",80:"P",81:"Q",82:"\u00cc",83:"R",84:"S",85:"T",86:"\u00cd",87:"U",88:"V",89:"\u00ce",90:"W\u00c0",91:"W",92:"X",93:"\u00b2\u00e6",94:"\u00cf",95:"Y",96:"\u00d0",97:"Z",98:"a",99:"\u00d1",100:"b",101:"c",102:"\u00d2",103:"d",104:"e",105:"f",106:"\u00d3",107:"h",108:"\u00d4",109:"k",110:"\u00d5",111:"l",112:"m",113:"n",114:"\u00d6",115:"o",116:"p",117:"\u00d7",118:"q",119:"r",120:"\u00d8",121:"qs",122:"\u00d9",123:"r\u00fc",124:"t",125:"\u00f2",126:"t\u00c2",127:"*",130:"\u00f3",131:"\u00c8",132:"\u00ca",133:"\u00ef",134:"\u00e6",135:"\u00c0",136:"\u00c9",137:"\u00e8",138:"/",139:"\u00e7",140:"\u00a0",145:"`",146:"'",147:"``",148:"''",149:"\u00f9",150:"-",151:"-",152:"\u00a2\u00fc",153:"\u00f7",154:"\u00f7",155:"\u00be",156:"\u00de",159:"\u00a7",160:"\u00f7",161:"\u00da",162:"\u00cc\u00f8",163:"w",164:"\u00db",165:"x",166:"y",167:"\u00dc",168:"z",169:"\u00a2",170:"\u00dd",171:"zs",174:"\u00a3",175:"\u00a4",176:"\u00df",177:"\u00a5",178:"\u00a6",179:"\u00e0",180:"\u00a5s",181:"\u00a6\u00fc",183:"\u008b",184:"\u00a8",185:"\u00a9",186:"\u00e2",187:"\u00a8s",188:"\u00a9\u00fc",189:"\u00e3",190:"\u00e4",191:"Ai\u00c0",192:"\u00ac",193:"Ai\u00c9",194:"\u00e5",195:"g",196:"j",197:"\u00e7",198:"\u00ae",199:"\u00af",200:"\u00b0",201:"\u00e8",202:"\u00aa",203:"\u00ab",204:"\u00e9",205:"\u00b1",206:"\u00b2",207:"\u00ea",208:"\u00b5",209:"\u00b6",210:"\u00eb",211:"\u00b8",212:"\u00b9",213:"\u00ec",214:"\u00ba",215:"\u00bb",216:"\u00ed",217:"\u00bc",218:"\u00bd",219:"\u00ee",220:"\u00dd",221:"\u00c1",222:"\u00c4\u00c1",223:"\u00f4",224:"\u00c3",225:"\u00c4",226:"\u00c5",227:"\u00c6",228:"\u00c7",229:"i",230:"\u00fa",231:"\u00ca",232:"\u00cb",233:"\u00e5",234:"\u00c8",235:"\u00f1",236:"\u00f0",237:"A",238:"\u00f5",239:"\u00f5\u00c9",240:"\u00cc\u00e7",241:"v",242:"\u00d1\u00ca",243:"\u00d6\u00e7",244:"\u00db\u00ca",245:"\u00db\u00f8",246:"\u00db\u00e5",247:"\u00db\u00e6",248:"\u00e0\u00e6",249:"\u00e7\u00f8",250:"\u00ec\u00e6",251:"P\u00eb",252:"Q\u00eb",253:"\u00e9",254:"\u00d6",255:"\u00e1"};
// Surabhi KN - 199/206 byte codes mapped (7 unresolved: 153,154,155,157,158,159,160)
const SURABHIKN_X2NUDI = {32:" ",33:"!",34:"'",35:"#",36:"\u00b2\u00e6",37:"%",38:"&",39:"`",40:"(",41:")",42:"*",43:"+",44:",",45:"-",46:".",47:"/",48:"0",49:"1",50:"2",51:"3",52:"4",53:"5",54:"6",55:"7",56:"8",57:"9",58:":",59:"_",60:"<",61:"=",62:">",63:"?",64:"@",65:"D",66:"\u00e2",67:"\u00d1",68:"\u00d8",69:"d\u00d5",70:"\u00cf",71:"\u00ce",72:"R",73:"\u00ca",74:"\u00d3",75:"\u00cc",76:"\u00e8",77:"\u00e4",78:"\u00df",79:"\u00c4\u00c1",80:"\u00e0",81:"\u00f0",82:"\u00e7",83:"\u00ec",84:"\u00d6",85:"G",86:"\u00e9",87:"\u00db",88:"\u00ee",89:"\u00c9",90:"\u00d0",91:"[",92:"\u00c9",93:"]",94:"^",95:"I",96:"\u00b5",97:"C",98:"\u00a7",99:"Z",100:"q",101:"E",102:"\u00c1",103:"U",104:"\u00ba",105:"J",106:"d",107:"P",108:"\u00ae",109:"A",110:"\u00a3",111:"M",112:"\u00a5",113:"\u00b1",114:"g",115:"\u00b8",116:"l",117:"i",118:"\u00aa",119:"v",120:"\u00bc",121:"\u00c0",122:"t",123:"{",124:"\u00ef",125:"}",126:"\u00eb",127:";",145:"`",146:"'",147:"``",148:"''",150:"-",151:"--",152:"\u00f2",156:"Ai",161:"\u00be",162:"f",163:"V",164:"F",165:"\u00d7",166:"\u00e0\u00e7",167:"\u00ec\u00e7",168:"b",169:"a",170:"\u00b6",171:"\u00f9",172:"\u00cc\u00f8",173:"\u00f5",174:"j",175:"\u00e1",176:"\u008c",177:"\u00a2\u00fc",178:"\u00a9",179:"n",180:"zs",181:"B",182:"\u00f7",183:"\u008b",184:"\u00bb",185:"\u00bf",186:"\u00fa",187:"\u00f1",188:"\u00db\u00f8",189:"\u00db\u00ca",190:"\u00db\u00e5",191:"\u00cc\u00e7",192:"T",193:"\u00cd",194:"R",195:"\u00a5s",196:"\u00ea",197:"\u00db\u00e7",198:"u",199:"\u00dd",200:"\u00de",201:"Y",202:"\u00d0",203:"\u00ab",204:"\u00bd",205:"\u00c8",206:"\u00c2",207:"c",208:"\u00d6\u00e7",209:"\u00a8",210:"\u00a8s",211:"O",212:"Q",213:"X",214:"W",215:"\u00fc",216:"\u00af",217:"\u00e1",218:"H",219:"p",220:"\u00f4",221:"o",222:"m",223:"\u00b9",224:"\u00dc",225:"\u00ed",226:"x",227:"y",228:"\u00b2",229:"w",230:"t\u00c2",231:"z",232:"\u00a2",233:"k",234:"\u00d5",235:"e",236:"\u00d4",237:"K",238:"L",239:"qs",240:"\u00d9",241:"\u00a4",242:"\u00a6\u00fc",243:"N",244:"r\u00fc",245:"r",246:"\u00a6",247:"\u008b",248:"\u00b0",249:"\u00c5",250:"\u00c6",251:"\u00c7",252:"i",253:"\u00a9\u00fc",254:"\u00e3",255:"/"};
// Shared Nudi Mono<->Bi pivot tables (used by the four Nudi-Bi-targeting
// fonts below): a2u goes X->NudiBi->(NUDIBI2MONO)->NudiMono->Unicode;
// Nudi Bi -> Mono (pivot) - 157/157 byte codes mapped (0 unresolved: none)
const NUDIBI2MONO = {32:" ",33:"!",34:"\"",35:"#",36:"$",37:"%",38:"&",39:"'",40:"(",41:")",42:"*",43:"+",44:",",45:"-",46:".",47:"/",48:"0",49:"1",50:"2",51:"3",52:"4",53:"5",54:"6",55:"7",56:"8",57:"9",58:":",59:";",60:"<",61:"=",62:">",63:"?",64:"@",129:"A",130:"B",131:"C",132:"D",133:"E",134:"F",135:"G",136:"H",137:"I",138:"J",139:"K",140:"L",141:"M",143:"N",144:"O",145:"P",146:"Q",147:"R",148:"S",149:"T",150:"U",151:"V",152:"W",153:"X",154:"Y",155:"Z",156:"a",157:"b",159:"c",161:"d",162:"e",163:"f",164:"g",165:"h",166:"i",167:"j",168:"k",169:"l",170:"m",171:"n",172:"o",173:"p",174:"q",175:"r",176:"s",177:"t",178:"u",179:"v",180:"w",181:"x",182:"y",183:"z",184:"\u00a2",185:"\u00a3",186:"\u00a4",187:"\u00a5",188:"\u00a6",189:"\u00a7",190:"\u00a8",191:"\u00a9",192:"\u00aa",193:"\u00ab",194:"\u00ac",195:"\u00ae",196:"\u00af",197:"\u00b0",198:"\u00b1",199:"\u00b2",200:"\u00b5",201:"\u00b6",202:"\u00b8",203:"\u00b9",204:"\u00ba",205:"\u00bb",206:"\u00bc",207:"\u00bd",208:"\u00c0",209:"\u00c1",210:"\u00c2",211:"\u00c3",212:"\u00c4",213:"\u00c5",214:"\u00c6",215:"\u00c7",216:"\u00c8",217:"\u00c9",218:"\u00ca",219:"\u00cb",220:"\u00cc",221:"\u00cd",222:"\u00ce",223:"\u00cf",224:"\u00d1",225:"\u00d2",226:"\u00d3",227:"\u00d4",228:"\u00d5",229:"\u00d6",230:"\u00d7",231:"\u00d8",232:"\u00d9",233:"\u00da",234:"\u00db",235:"\u00dc",236:"\u00dd",237:"\u00de",238:"\u00df",239:"\u00e0",240:"\u00e1",241:"\u00e2",242:"\u00e3",243:"\u00e4",244:"\u00e5",245:"\u00e7",246:"\u00e8",247:"\u00e9",248:"\u00ea",249:"\u00eb",250:"\u00ec",251:"\u00ed",252:"\u00ee",253:"\u00ef",254:"\u00f0",255:"\u00f6"};
// Nudi Mono -> Bi (pivot) - 171/180 byte codes mapped (9 unresolved: 132,137,139,208,242,243,245,251,253)
const NUDIMONO2BI = {32:" ",33:"!",34:"\"",35:"#",36:"$",37:"%",38:"&",39:"'",40:"(",41:")",42:"*",43:"+",44:",",45:"-",46:".",47:"/",48:"0",49:"1",50:"2",51:"3",52:"4",53:"5",54:"6",55:"7",56:"8",57:"9",58:":",59:";",60:"<",61:"=",62:">",63:"?",64:"@",65:"\u0081",66:"\u0082",67:"\u0083",68:"\u0084",69:"\u0085",70:"\u0086",71:"\u0087",72:"\u0088",73:"\u0089",74:"\u008a",75:"\u008b",76:"\u008c",77:"\u008d",78:"\u008f",79:"\u0090",80:"\u0091",81:"\u0092",82:"\u0093",83:"\u0094",84:"\u0095",85:"\u0096",86:"\u0097",87:"\u0098",88:"\u0099",89:"\u009a",90:"\u009b",97:"\u009c",98:"\u009d",99:"\u009f",100:"\u00a1",101:"\u00a2",102:"\u00a3",103:"\u00a4",104:"\u00a5",105:"\u00a6",106:"\u00a7",107:"\u00a8",108:"\u00a9",109:"\u00aa",110:"\u00ab",111:"\u00ac",112:"\u00ad",113:"\u00ae",114:"\u00af",115:"\u00b0",116:"\u00b1",117:"\u00b2",118:"\u00b3",119:"\u00b4",120:"\u00b5",121:"\u00b6",122:"\u00b7",133:"_",134:"|",135:"||",138:"--",162:"\u00b8",163:"\u00b9",164:"\u00ba",165:"\u00bb",166:"\u00bc",167:"\u00bd",168:"\u00be",169:"\u00bf",170:"\u00c0",171:"\u00c1",172:"\u00c2",174:"\u00c3",175:"\u00c4",176:"\u00c5",177:"\u00c6",178:"\u00c7",181:"\u00c8",182:"\u00c9",184:"\u00ca",185:"\u00cb",186:"\u00cc",187:"\u00cd",188:"\u00ce",189:"\u00cf",190:"\u00a4\u00d0",191:"\u00ce\u00d0",192:"\u00d0",193:"\u00d1",194:"\u00d2",195:"\u00d3",196:"\u00d4",197:"\u00d5",198:"\u00d6",199:"\u00d7",200:"\u00d8",201:"\u00d9",202:"\u00da",203:"\u00db",204:"\u00dc",205:"\u00dd",206:"\u00de",207:"\u00df",209:"\u00e0",210:"\u00e1",211:"\u00e2",212:"\u00e3",213:"\u00e4",214:"\u00e5",215:"\u00e6",216:"\u00e7",217:"\u00e8",218:"\u00e9",219:"\u00ea",220:"\u00eb",221:"\u00ec",222:"\u00ed",223:"\u00ee",224:"\u00ef",225:"\u00f0",226:"\u00f1",227:"\u00f2",228:"\u00f3",229:"\u00f4",230:"\u00f5",231:"\u00f5",232:"\u00f6",233:"\u00f7",234:"\u00f8",235:"\u00f9",236:"\u00fa",237:"\u00fb",238:"\u00fc",239:"\u00fd",240:"\u00fe",241:"\u00f5",244:"\u00d2",246:"\u00ff",247:"\u00ff",248:"\u00d8",249:"\u00f5",250:"\u00fc",252:"\u00b0"};
// Suchi Kan - 200/224 byte codes mapped (24 unresolved: 128,129,139,141,142,143,144,145,154,156,157,158,160,161,166,170,173,183,190,205,223,231,237,253)
const SUCHI_X2NUDIBI = {32:" ",33:"!",34:"'",35:"\u00a4",36:"$",37:"%",38:"&",39:"'",40:"(",41:")",42:"*",43:"+",44:",",45:"-",46:".",47:"/",48:"0",49:"1",50:"2",51:"3",52:"4",53:"5",54:"6",55:"7",56:"8",57:"9",58:":",59:";",60:"<",61:"=",62:">",63:"?",64:"@",65:"A",66:"B",67:"C",68:"D",69:"E",70:"F",71:"G",72:"H",73:"I",74:"J",75:"K",76:"L",77:"M",78:"N",79:"O",80:"P",81:"Q",82:"R",83:"S",84:"T",85:"U",86:"V",87:"W",88:"X",89:"Y",90:"Z",91:"[",92:"\\",93:"]",94:"^",95:"_",96:"`",97:"a",98:"b",99:"c",100:"d",101:"e",102:"f",103:"g",104:"h",105:"i",106:"j",107:"k",108:"l",109:"m",110:"n",111:"o",112:"p",113:"q",114:"r",115:"s",116:"t",117:"u",118:"v",119:"w",120:"x",121:"y",122:"z",123:"\u00c6",124:"\u00d0",125:"\u00ca",126:"\u00cc",127:"\u00e3",130:"\u00fe",131:"\u0098\u00d0",132:"\u009a",133:"\u0081",134:"\u0092",135:"\u00a1",136:"\u00a5",137:"\u00a8",138:"\u00a9",140:"\u0095",146:"\u00d7",147:"\u009c",148:"\u0098",149:"\u00bd",150:"\u009f",151:"\u0081\u00d4",152:"\u00a3",153:"\u00c3",155:"\u00ab",159:"\u00dd",161:"\u00b8",162:"\u00ba",163:"\u0098\u00d9",164:"\u00c0",165:"\u00c7\u00f5",166:"\u00bc",167:"\u00c4",168:"\u009b",169:"\u00d2",170:"\u00bf",171:"\u00a7",172:"\u00c2",174:"\u00c5",175:"\u00fb",176:"\u00c1",177:"\u009d",178:"\u00c7",179:"\u00d9",180:"\u00a2",181:"\u00cb",182:"\u00ce",184:"\u00cd",185:"\u00cf",186:"\u00a6",187:"\u00fd",188:"\u00aa",189:"\u0082",190:"\u00ae",191:"\u00b2",192:"\u00dc",193:"\u0094",194:"\u0096",195:"\u00df",196:"\u0097",197:"\u00e0",198:"\u00e1",199:"\u00e2",200:"\u00de",201:"\u00e4",202:"\u00e5",203:"\u00e6",204:"\u00e7",206:"\u00e9",207:"\u00ea",208:"\u00eb",209:"\u00ec",210:"\u0093",211:"\u00ee",212:"\u00ef",213:"\u0099",214:"\u00f1",215:"\u00b1",216:"\u00f4",217:"\u00f5",218:"\u00f6",219:"\u00f7",220:"\u00f8",221:"\u00f9",222:"\u00fa",223:"\u00af",224:"\u00fc",225:"\u00d1",226:"\u00b3",227:"\u00d3",228:"\u00d4",229:"\u00d6",230:"\u00d8",231:"\u00b7",232:"\u00d5",233:"\u00da",234:"\u00f3",235:"\u00b9",236:"\u00db",237:"\u00bb",238:"\u00f5",239:"\u00ff",240:"\u0083",241:"\u0084",242:"\u0085",243:"\u0086",244:"\u0087",245:"\u0088",246:"\u0089",247:"\u008a",248:"\u008b",249:"\u008c",250:"\u008d",251:"\u008f",252:"\u0090",253:"\u00be",254:"\u00b4",255:"\u0091"};
// ISM (KNB TT-Nandi) - 100/117 byte codes mapped (17 unresolved: 152,153,157,178,180,181,183,191,193,194,199,200,218,220,221,236,249)
const ISMKNBTT_X2NUDIBI = {32:" ",33:"!",34:"\"",35:"#",36:"$",37:"%",38:"&",39:"'",40:"(",41:")",42:"*",43:"+",44:",",45:"-",46:".",47:"/",48:"0",49:"1",50:"2",51:"3",52:"4",53:"5",54:"6",55:"7",56:"8",57:"9",58:":",59:";",60:"<",61:"=",62:">",63:"?",64:"@",65:"A",66:"B",67:"C",68:"D",69:"E",70:"F",71:"G",72:"H",73:"I",74:"J",75:"K",76:"L",77:"M",78:"N",79:"O",80:"P",81:"Q",82:"R",83:"S",84:"T",85:"U",86:"V",87:"W",88:"X",89:"Y",90:"Z",91:"[",92:"\\",93:"]",94:"^",95:"_",96:"`",97:"a",98:"b",99:"c",100:"d",101:"e",102:"f",103:"g",104:"h",105:"i",106:"j",107:"k",108:"l",109:"m",110:"n",111:"o",112:"p",113:"q",114:"r",115:"s",116:"t",117:"u",118:"v",119:"w",120:"x",121:"y",122:"z",123:"{",124:"|",125:"}",126:"~",127:"\u007f",128:"\u0080",129:"\u00fe",130:"\u00c7\u00f5\u00d3",131:"\u0083",132:"\u0084",133:"\u0085",134:"\u0086",135:"\u0087",136:"\u0088",137:"\u0089",138:"\u008a",139:"\u008b",140:"\u008c",141:"\u008d",143:"\u0090",144:"\u0081",145:"\u0082",146:"\u0091",147:"\u0092",148:"\u00dc",149:"\u0093",150:"\u0095",151:"\u00dd",154:"\u00de",155:"\u0098",156:"\u0099",157:"\u009d",158:"\u009e",159:"\u009a",160:"\u00a0",161:"\u009c",162:"\u00e0",163:"\u009d",164:"\u009f",165:"\u00e1",166:"\u00a1",167:"\u00a2",168:"\u00a3",169:"\u00e2",170:"\u00a5",171:"\u00e3",172:"\u00a8",173:"\u00e4",174:"\u00a9",175:"\u00aa",176:"\u00ab",177:"\u00e5",179:"\u00e6",182:"\u00e7",184:"\u00b1",185:"\u00b2",186:"\u00b1\u00d2",187:"\u00e9",188:"\u00b3",189:"\u00b4",190:"\u00ea",192:"\u00eb",195:"\u00b0",196:"\u00b9",197:"\u00ba",198:"\u00ee",201:"\u00ef",202:"\u00bd",203:"\u00bf",204:"\u00f1",205:"\u00f3",206:"\u00c2",207:"\u00f4",208:"\u00f5",209:"\u00c3",210:"\u00c5",211:"\u00f6",212:"\u00c0",213:"\u00c1",214:"\u00f7",215:"\u00c6",216:"\u00c7",217:"\u00f8",219:"\u00f9",221:"\u00d2",222:"\u00fa",223:"\u00cc",224:"\u00cd",225:"\u00fb",226:"\u00ce",227:"\u00cf",228:"\u00fc",229:"\u00d0",230:"\u00d1",231:"\u00a0",232:"\u00d2",233:"\u00d3",234:"\u00d4",235:"\u00d6",236:"\u00a6",237:"\u00d5",238:"\u00d7",239:"\u00d8",240:"\u00d9",241:"\u00da",242:"\u00db",243:"\u00fd",244:"\u009b",245:"\u008f",246:"\u00ea\u00f7",247:"\u009a",248:"\u00f5",250:"\u00ff",251:"\u00ff",252:"\u00ff",253:"\u00ff",254:"\u00ff",255:"\u00ff"};
// Akruti Bi - 116/127 byte codes mapped (11 unresolved: 152,159,207,212,239,240,241,246,248,250,254)
const AKRUTIBI_X2NUDIBI = {129:"\u0095",130:"\u0097",131:"\u0099",132:"\u009c",133:"\u009f",134:"\u00a3",135:"\u00ab",136:"\u00af",137:"\u00b4",138:"\u00b8",139:"\u00ba",140:"\u00bc",141:"\u00bf",142:"\u00c1",143:"\u00c2",144:"\u00a7",145:"\u00c5",146:"\u00cf",147:"\u00c7",148:"\u00c9",149:"\u00cb",150:"\u00cd",151:"\u00c7\u00f5",153:"\u00f5",154:"\u00ea\u00f5",155:"\u00dc\u00d8",156:"\u00e5\u00f5",157:"\u00fa\u00f5",158:"\u00fe",160:"\u00a0",161:"\u0083",162:"\u0084",163:"\u0085",164:"\u0086",165:"\u0087",166:"\u0088",167:"\u0089",168:"\u008a",169:"\u008b",170:"\u008c",171:"\u008d",172:"\u008f",173:"\u0090",174:"\u0081",175:"\u0082",176:"\u0091",177:"\u0093",178:"\u0094",179:"\u0096",180:"\u0098",181:"\u009a",182:"\u009b",183:"\u009d",184:"\u00a1",185:"\u00a2",186:"\u00a8",187:"\u00a9",188:"\u00aa",189:"\u00ae",190:"\u00b1",191:"\u00b2",192:"\u00b3",193:"\u00b7",194:"\u00b9",195:"\u00bb",196:"\u00bd",197:"\u00be",198:"\u00c0",199:"\u00a4",200:"\u00c3",201:"\u00c4",202:"\u00ce",203:"\u00c6",204:"\u00c8",205:"\u00ca",206:"\u00cc",208:"\u00dc",209:"\u00dd",210:"\u00de",211:"\u00df",213:"\u00e0",214:"\u00e1",215:"\u00e2",216:"\u00e3",217:"\u00e4",218:"\u00e5",219:"\u00e6",220:"\u00e7",221:"\u00e9",222:"\u00ea",223:"\u00eb",224:"\u00ec",225:"\u00ee",226:"\u00ef",227:"\u00f1",228:"\u00f3",229:"\u00f4",230:"\u00f5",231:"\u00f6",232:"\u00fc",233:"\u00f7",234:"\u00f8",235:"\u00f9",236:"\u00fa",237:"\u00fb",238:"\u0092",239:"\u00b0",240:"\u00d0",241:"\u00d1",242:"\u00d2",243:"\u00d3",244:"\u00d4",245:"\u00a6",246:"\u00d5",247:"\u00d6",248:"\u00d6",249:"\u00d8",250:"\u00d9",251:"\u00da",252:"\u00db",253:"\u00fd",254:"\u00b0",255:"\u00b0"};
// WinKey KanEng - 201/223 byte codes mapped (22 unresolved: 132,160,171,183,188,193,206,209,219,221,222,223,225,227,229,238,239,242,250,251,253,254)
const WINKEY_X2NUDIBI = {32:" ",33:"!",34:"\"",35:"#",36:"\u0083",37:"\u00e4",38:"\u009c",39:"'",40:"(",41:")",42:"*",43:"+",44:",",45:"-",46:".",47:"/",48:"0",49:"1",50:"2",51:"3",52:"4",53:"5",54:"6",55:"7",56:"8",57:"9",58:":",59:";",60:"\u008d",61:"=",62:"\u0090",63:"?",64:"@",65:"A",66:"B",67:"C",68:"D",69:"E",70:"F",71:"G",72:"H",73:"I",74:"J",75:"K",76:"L",77:"M",78:"N",79:"O",80:"P",81:"Q",82:"R",83:"S",84:"T",85:"U",86:"V",87:"W",88:"X",89:"Y",90:"Z",91:"\u00dd",92:"\u0095",93:"\u00de",94:"\u008c",95:"_",96:"\u008f",97:"a",98:"b",99:"c",100:"d",101:"e",102:"f",103:"g",104:"h",105:"i",106:"j",107:"k",108:"l",109:"m",110:"n",111:"o",112:"p",113:"q",114:"r",115:"s",116:"t",117:"u",118:"v",119:"w",120:"x",121:"y",122:"z",123:"\u0097",124:"\u00df",125:"\u00e0",126:"\u00dc",128:"\u0083",129:"\u0084",130:"\u0085",131:"\u0086",133:"\u0089",134:"\u008a",135:"\u008b",136:"\u008c",137:"\u008d",138:"\u008f",139:"\u0090",140:"\u0081",141:"\u0082",142:"\u00e4",143:"\u00a8",144:"\u00f3",145:"\u009a",146:"\u00dc",147:"\u0091",148:"\u0092",149:"\u00dd",150:"\u0093",151:"\u0095",152:"\u00de",153:"\u0096",154:"\u0097",155:"\u00df",156:"\u00e0",157:"\u009b",158:"\u009c",159:"\u00ae",161:"\u00e2",162:"\u00a1",163:"\u00a3",164:"\u00e5",165:"\u00a9",166:"\u00ab",167:"\u00aa",168:"\u009d",169:"\u009f",170:"\u00e7",172:"\u00af",173:"\u00e9",174:"\u00b1",175:"\u00b1\u00d2",176:"\u00b3",177:"\u00b4",178:"\u00eb",179:"\u00b2",180:"\u00b8",181:"\u00ec",182:"\u00b7",184:"\u00b9",185:"\u00ba",186:"\u00ef",187:"\u009a",189:"\u00f1",190:"\u00bd",191:"\u00bf",192:"\u00fe",194:"\u00f4",195:"\u00c2\u00d4",196:"\u00a4",197:"\u00a7",198:"\u00c3",199:"\u00c5",200:"\u00f7",201:"\u00c0",202:"\u00c1",203:"\u00c6",204:"\u00c7",205:"\u00f9",207:"\u00f8",208:"\u00fa",210:"\u00c7\u00f5",211:"\u00fb",212:"\u00cc",213:"\u00cd",214:"\u00fc",215:"\u00ce",216:"\u00cf",217:"\u00e6",218:"\u0091",220:"\u00d0",221:"\u00fd",222:"\u00d1",223:"\u00d2",224:"\u00d3",225:"\u00d4",226:"\u00d5",227:"\u00d6",228:"\u00d7",229:"\u00d9",230:"\u00da",231:"\u00db",232:"\u00ea",233:"\u00ee",234:"\u00f6",235:"\u00f5",236:"\u00f5",237:"\u00d8",240:"\u0085",241:"\u0086",243:"\u0093",244:"\u008a",245:"\u008b",246:"\u0096",247:"\u00ae",248:"\u0093",249:"o",250:"\u00b0",251:"\u00b0",252:"\u00a5",255:"\u00e3"};
function _buildNudi2XInverse(x2nudiMap) {
    const inverse = {};
    Object.keys(x2nudiMap).forEach(codeStr => {
        const frag = x2nudiMap[codeStr];
        if (frag && !(frag in inverse)) {
            inverse[frag] = String.fromCharCode(Number(codeStr));
        }
    });
    return { map: inverse, keys: Object.keys(inverse).sort((a, b) => b.length - a.length) };
}

const _nudi2xCache = new Map();
function _nudi2xFor(x2nudiMap) {
    if (!_nudi2xCache.has(x2nudiMap)) {
        _nudi2xCache.set(x2nudiMap, _buildNudi2XInverse(x2nudiMap));
    }
    return _nudi2xCache.get(x2nudiMap);
}

// Extracts Latin-letter/number runs into placeholders (same heuristic as
// the Nudi retainEnglish path) so they skip the pivot substitution and the
// downstream Nudi engine entirely.
// _isEnglishToken (above) is entirely Nudi-specific: it recognizes English
// vs. Nudi-encoded ASCII using Nudi's OWN byte conventions (mostly extended
// Latin-1 characters, which real English words never contain). That works
// fine for Nudi's own text and for the u2a direction of every pivot font
// (there the input is already clean Unicode, so a Latin run really is
// English). But on the a2u/decode side of a PIVOT font, the input text is
// in THAT FONT's own ASCII alphabet - and several pivot fonts (Surabhi KN,
// and the plain-ASCII-heavy Nudi-Bi fonts: Suchi Kan, ISM KNB TT-Nandi,
// Akruti Bi, WinKey KanEng) encode many consonants as plain lowercase
// a-z letters. A run like "ky" (Surabhi KN's \u0C95) has no extended-Latin
// hint character anywhere near it, so _isEnglishToken falls through to its
// default "yes, this is English" verdict - even though it is that font's
// own valid encoding for a real Kannada syllable. Confirmed via direct
// testing: asciiToUnicode('ky', false, 'surabhikn') correctly yields \u0C95, but
// convert('ky', 'keep', 'a2u', true, 'surabhikn') (retainEnglish=true, the
// default UI/test-harness path) left it as "ky" untouched, because
// _isEnglishToken('ky', 'ky', 0) returned true.
//
// The fix: give _extractEnglishTokens an optional decodeCheckFn - a
// font-aware "does this token actually decode to real Kannada via THIS
// font's own pivot chain" check. When _isEnglishToken says "English" but
// decodeCheckFn says "this is valid encoded Kannada", the decodeCheckFn
// verdict wins (a real font byte sequence takes precedence over a
// Nudi-tuned English heuristic that has no idea this font exists). Only
// wired up on the two a2u/decode call sites (pivotAsciiToUnicode,
// pivotAsciiToUnicodeViaBi) where the ambiguity actually exists; the u2a
// call sites already start from clean Unicode and are left untouched.
function _looksLikeEncodedKannada(token, x2nudiMap) {
    let nudi = '';
    for (let i = 0; i < token.length; i++) {
        const code = token.charCodeAt(i);
        nudi += (code in x2nudiMap) ? x2nudiMap[code] : token[i];
    }
    if (!_hasBareAByte(x2nudiMap)) nudi = _normalizeBareNudiConsonants(nudi);
    const decoded = asciiToUnicode(nudi, false, 'nudi');
    return /[\u0C80-\u0CFF]/.test(decoded) && !/[a-zA-Z]/.test(decoded);
}
function _looksLikeEncodedKannadaBi(token, x2nudibiMap) {
    const nudiBi = _substituteByMap(token, x2nudibiMap);
    const nudiMono = _substituteByMap(nudiBi, NUDIBI2MONO);
    const decoded = asciiToUnicode(nudiMono, false, 'nudi');
    return /[\u0C80-\u0CFF]/.test(decoded) && !/[a-zA-Z]/.test(decoded);
}

// This app's own direction-code shorthand ("a2u", "u2a") shows up verbatim
// in help text/notes that get typed or pasted back in for conversion (e.g.
// "(u2a)"). Each is a single-letter + digit + single-letter run, and
// single-character letter tokens are never eligible for English retention
// (see the token.length === 1 branch in _isEnglishToken above - by design,
// since a lone ASCII letter is almost always a genuine Nudi consonant/vowel
// byte). Without a dedicated check, "u2a" gets split into 'u' and 'a'
// (each decoded as a literal Nudi byte) plus a lone "2" (kept convertible
// since it sits next to letters, per the digit-run rule below), producing
// nonsense like "u2a" -> "u\u0CE8\u0C9A\u0CBF" instead of staying as-is.
// Matched at the very start of the scan position only (see call sites) so
// it never fires mid-word (e.g. "seea2u", "au2a" are left alone).
const DIRECTION_CODE_RE = /^(a2u|u2a)(?![a-zA-Z0-9])/i;
function _matchDirectionCodeAt(text, i) {
    const m = DIRECTION_CODE_RE.exec(text.slice(i, i + 4));
    return m ? m[0] : null;
}

function _extractEnglishTokens(text, decodeCheckFn) {
    const englishTexts = [];
    let out = '';
    let i = 0;
    while (i < text.length) {
        if (text[i] === '\uFF62') {
            let j = i + 1;
            while (j < text.length && text[j] !== '\uFF63') j++;
            out += text.slice(i, j + 1);
            i = j + 1;
            continue;
        }
        const dirCode = _matchDirectionCodeAt(text, i);
        if (dirCode) {
            const idx = englishTexts.length;
            englishTexts.push(dirCode);
            out += _makePlaceholder(idx);
            i += dirCode.length;
            continue;
        }
        if (/[a-zA-Z]/.test(text[i])) {
            let j = i;
            while (j < text.length && /[a-zA-Z'-]/.test(text[j])) j++;
            const token = text.slice(i, j);
            if (_isEnglishToken(token, text, i) && !(decodeCheckFn && decodeCheckFn(token))) {
                const idx = englishTexts.length;
                englishTexts.push(token);
                out += _makePlaceholder(idx);
            } else {
                out += token;
            }
            i = j;
        } else if (/[0-9]/.test(text[i])) {
            let j = i;
            while (j < text.length && /[0-9]/.test(text[j])) {
                j++;
                if (j < text.length - 1 && /[.,:]/.test(text[j]) && /[0-9]/.test(text[j + 1])) j++;
            }
            const numToken = text.slice(i, j);
            const before = i > 0 ? text[i - 1] : '';
            const after = j < text.length ? text[j] : '';
            const adjacentToCode = /[a-zA-ZÀ-ÿĀ-ſ]/.test(before) || /[a-zA-ZÀ-ÿĀ-ſ]/.test(after);
            if (!adjacentToCode) {
                const idx = englishTexts.length;
                englishTexts.push(numToken);
                out += _makePlaceholder(idx);
            } else {
                out += numToken;
            }
            i = j;
        } else {
            out += text[i];
            i++;
        }
    }
    return { text: out, englishTexts };
}

function _restoreEnglishTokens(text, englishTexts) {
    if (!englishTexts.length) return text;
    return text.replace(_placeholderRe, (_, enc) => englishTexts[_decodeIdx(enc)]);
}

// Three of the direct-to-Nudi-Mono macros (Prakashak, Dharma ILs, Janna
// Mono) emit only the *bare* base-consonant letter for ~10 consonants
// (\u0C95,\u0C97,\u0C98,\u0C9A,\u0C9B,\u0CA0,\u0CA1,\u0CA4,\u0CA6,\u0CB0 = P,U,W,Z,b,o,q,v,z,g in Nudi ASCII) instead of the
// letter + explicit inherent-vowel marker "\u00C0" that Nudi's own decoder
// actually requires. The other 6 direct-to-Mono fonts (Akruti, ShreeLipi,
// Surabhi, ISM KNTT, SriLipi 850, Shree Deccan, Surabhi KN) already have a
// dedicated byte that types "\u00C0" on its own, so they compose this
// correctly without any help - normalizing for them too would be wrong
// (their own byte-for-\u00C0 composition already produces the exact right
// string; blindly re-inserting "\u00C0" around bare letters elsewhere in a
// fully-formed string, e.g. mid-conjunct, corrupts otherwise-correct
// output). This looks like a gap in the per-byte substitution model for
// just these three: the original VBA macros likely inserted "\u00C0" via a
// separate, context-aware finalization step (not captured by our per-byte
// pivot tables) whenever the consonant wasn't immediately followed by a
// vowel sign that attaches directly. Cross-checking against Nudi's own
// consonantMaps shows the rule is consistent: "\u00C0" is needed when the bare
// letter is standalone (word/syllable-final) or followed by the
// short-u/long-u/vocalic-r matras (\u00C4/\u00C6/\u00C8) - but NOT when followed by
// long-a/e-family/au (\u00C1/\u00C9/\u00CB) or the halant marker (\u00EF), which attach
// directly to the bare letter.
const NUDI_BARE_BASE_LETTERS = new Set(['P', 'U', 'W', 'Z', 'b', 'o', 'q', 'v', 'z', 'g']);
// Per-letter "attaches directly, no \u00C0 needed" next-character set, derived
// from consonantMaps/vowelMaps (the source of truth) rather than
// hand-maintained - q and z each have one extra legitimate continuation
// ('s') beyond the common {\u00EF,\u00C0,\u00C1,\u00C9,\u00CB}, from the "consonant+s" digraph used
// for \u0CA2 ("qs") and \u0CA7 ("zs"). Missing this caused "qs"/"zs" to be wrongly
// split into "q\u00C0s"/"z\u00C0s" the first time this was tried.
const NUDI_DIRECT_ATTACH_NEXT = {
    P: new Set(['\u00EF', '\u00C0', '\u00C1', '\u00C9', '\u00CB']),
    U: new Set(['\u00EF', '\u00C0', '\u00C1', '\u00C9', '\u00CB']),
    W: new Set(['\u00EF', '\u00C0', '\u00C1', '\u00C9', '\u00CB']),
    Z: new Set(['\u00EF', '\u00C0', '\u00C1', '\u00C9', '\u00CB']),
    b: new Set(['\u00EF', '\u00C0', '\u00C1', '\u00C9', '\u00CB']),
    o: new Set(['\u00EF', '\u00C0', '\u00C1', '\u00C9', '\u00CB']),
    q: new Set(['\u00EF', '\u00C0', '\u00C1', '\u00C9', '\u00CB', 's']),
    v: new Set(['\u00EF', '\u00C0', '\u00C1', '\u00C9', '\u00CB']),
    z: new Set(['\u00EF', '\u00C0', '\u00C1', '\u00C9', '\u00CB', 's']),
    g: new Set(['\u00EF', '\u00C0', '\u00C1', '\u00C9', '\u00CB']),
};
const _hasBareABYteCache = new Map();
function _hasBareAByte(x2nudiMap) {
    if (!_hasBareABYteCache.has(x2nudiMap)) {
        _hasBareABYteCache.set(x2nudiMap, Object.values(x2nudiMap).includes('\u00C0'));
    }
    return _hasBareABYteCache.get(x2nudiMap);
}
function _normalizeBareNudiConsonants(s) {
    let out = '';
    for (let i = 0; i < s.length; i++) {
        if (s[i] === '\uFF62') {
            // Skip retained-English placeholder blocks untouched - their
            // internal index encoding isn't Nudi ASCII and must not be
            // scanned/modified here (a placeholder whose index happened to
            // contain 'b' was previously getting corrupted into "b" + "\u00C0").
            let j = i + 1;
            while (j < s.length && s[j] !== '\uFF63') j++;
            out += s.slice(i, j + 1);
            i = j;
            continue;
        }
        out += s[i];
        if (NUDI_BARE_BASE_LETTERS.has(s[i])) {
            const next = s[i + 1];
            const direct = NUDI_DIRECT_ATTACH_NEXT[s[i]];
            if (next === undefined || !direct.has(next)) {
                out += '\u00C0';
            }
        }
    }
    return out;
}

function pivotAsciiToUnicode(text, x2nudiMap, retainEnglish) {
    let source = text;
    let englishTexts = [];
    if (retainEnglish) {
        const extracted = _extractEnglishTokens(source, tok => _looksLikeEncodedKannada(tok, x2nudiMap));
        source = extracted.text;
        englishTexts = extracted.englishTexts;
    }
    let nudi = '';
    let i = 0;
    while (i < source.length) {
        if (source[i] === '\uFF62') {
            let j = i + 1;
            while (j < source.length && source[j] !== '\uFF63') j++;
            nudi += source.slice(i, j + 1);
            i = j + 1;
            continue;
        }
        const code = source.charCodeAt(i);
        nudi += (code in x2nudiMap) ? x2nudiMap[code] : source[i];
        i++;
    }
    if (!_hasBareAByte(x2nudiMap)) {
        nudi = _normalizeBareNudiConsonants(nudi);
    }
    let result = asciiToUnicode(nudi, false, 'nudi');
    if (englishTexts.length) result = _restoreEnglishTokens(result, englishTexts);
    return result;
}

// Some Nudi fragment characters needed to encode a given font (e.g. the
// standalone "i" used inside ಝ/ಮ/ಯ's halant compound, or the aspirate
// marker "ü" used for ಢಿ/ಧಿ/ಫಿ/ಭಿ) have no corresponding byte in that
// font's source macro at all - a genuine gap in the extracted data, not a
// bug we can resolve. When the greedy inverter can't find a byte for a
// leftover character, it used to fall back to passing the literal
// character through untouched. If that literal character happens to
// ALSO be some OTHER real byte in this font (pure codepoint coincidence -
// our "byte" is just a JS string character throughout), decoding it back
// reinterprets it as that unrelated byte, corrupting not just this
// syllable but potentially bleeding into whatever follows. Dropping an
// unmatched character that's "claimed" by another byte is not a fix (the
// syllable is still wrong - the data to encode it correctly doesn't
// exist), but it keeps the failure contained instead of corrupting
// adjacent, otherwise-correct text.
// A leftover character is "claimed" (dangerous to pass through literally)
// if its own character code is a real byte in this font - decoding looks
// up each output character by charCode regardless of why it's there, so
// any pass-through character whose code happens to collide with a real
// byte gets reinterpreted as that byte's (unrelated) fragment on decode.
function _isClaimedChar(x2nudiMap, ch) {
    return ch.charCodeAt(0) in x2nudiMap;
}

function pivotUnicodeToAscii(text, x2nudiMap) {
    const extracted = _extractEnglishTokens(text);
    const nudiAscii = unicodeToASCII(extracted.text, 'nudi');
    const { map: nudi2x, keys } = _nudi2xFor(x2nudiMap);
    let result = '';
    let i = 0;
    let lastWasBareBase = false;
    while (i < nudiAscii.length) {
        if (nudiAscii[i] === '\uFF62') {
            let j = i + 1;
            while (j < nudiAscii.length && nudiAscii[j] !== '\uFF63') j++;
            result += nudiAscii.slice(i, j + 1);
            i = j + 1;
            lastWasBareBase = false;
            continue;
        }
        // The mirror of _normalizeBareNudiConsonants: Nudi's own encoder
        // inserted "\u00C0" after a bare base-consonant letter (see comment
        // above pivotAsciiToUnicode); if the source font has no byte that
        // produces "\u00C0" on its own, drop it here rather than falling back
        // to a literal, meaningless pass-through character.
        if (lastWasBareBase && nudiAscii[i] === '\u00C0' && !('\u00C0' in nudi2x)) {
            i++;
            lastWasBareBase = false;
            continue;
        }
        let matched = false;
        for (const key of keys) {
            if (key.length && nudiAscii.startsWith(key, i)) {
                result += nudi2x[key];
                i += key.length;
                lastWasBareBase = NUDI_BARE_BASE_LETTERS.has(key[key.length - 1]);
                matched = true;
                break;
            }
        }
        if (matched) continue;
        // No byte in this font produces the fragment starting here (a
        // genuine gap in the source data - see _isClaimedChar above). If
        // passing this character through literally would collide with an
        // unrelated real byte on decode, drop it instead of corrupting
        // whatever follows; otherwise it's harmless to pass through as-is.
        if (!_isClaimedChar(x2nudiMap, nudiAscii[i])) {
            result += nudiAscii[i];
        }
        lastWasBareBase = NUDI_BARE_BASE_LETTERS.has(nudiAscii[i]);
        i++;
    }
    if (extracted.englishTexts.length) result = _restoreEnglishTokens(result, extracted.englishTexts);
    return result;
}

// Generic char-by-char substitution using a byteCode -> fragment map,
// preserving ｢...｣ placeholder blocks untouched (same convention
// as pivotAsciiToUnicode/pivotUnicodeToAscii above).
function _substituteByMap(text, map) {
    let out = '';
    let i = 0;
    while (i < text.length) {
        if (text[i] === '｢') {
            let j = i + 1;
            while (j < text.length && text[j] !== '｣') j++;
            out += text.slice(i, j + 1);
            i = j + 1;
            continue;
        }
        const code = text.charCodeAt(i);
        out += (code in map) ? map[code] : text[i];
        i++;
    }
    return out;
}

// The Bi-hop fonts need the same missing-implicit-vowel-marker handling
// (see _normalizeBareNudiConsonants / the drop-side of pivotUnicodeToAscii
// above) as the direct-to-Mono fonts, but "does this font have a dedicated
// byte for the bare 'À' marker" has to be answered in terms of the font's
// OWN byte -> Bi -> Mono round trip, not its raw Bi fragment. Composing
// each font byte's Bi fragment through NUDIBI2MONO once (and caching the
// result) gives a synthetic "byte -> Mono fragment" map equivalent to the
// direct fonts' x2nudiMap, so _hasBareAByte/_normalizeBareNudiConsonants
// can be reused unchanged instead of duplicating that logic for the Bi path.
const _composedX2MonoCache = new Map();
function _composedX2Mono(x2nudibiMap) {
    if (!_composedX2MonoCache.has(x2nudibiMap)) {
        const composed = {};
        for (const code in x2nudibiMap) {
            composed[code] = _substituteByMap(x2nudibiMap[code], NUDIBI2MONO);
        }
        _composedX2MonoCache.set(x2nudibiMap, composed);
    }
    return _composedX2MonoCache.get(x2nudibiMap);
}
// Mirrors the drop-side of pivotUnicodeToAscii's bare-"À" handling, but runs
// as a pre-pass on the Mono ASCII (Nudi's own encoder output) before the
// NUDIMONO2BI hop - "À" only exists as a distinct character at the Mono
// level, so the drop has to happen before it gets folded into a Bi fragment.
function _dropUnneededBareA(monoAscii, hasBareA) {
    if (hasBareA) return monoAscii;
    let out = '';
    let lastWasBareBase = false;
    let i = 0;
    while (i < monoAscii.length) {
        if (monoAscii[i] === '｢') {
            let j = i + 1;
            while (j < monoAscii.length && monoAscii[j] !== '｣') j++;
            out += monoAscii.slice(i, j + 1);
            i = j + 1;
            lastWasBareBase = false;
            continue;
        }
        if (lastWasBareBase && monoAscii[i] === 'À') {
            lastWasBareBase = false;
            i++;
            continue;
        }
        out += monoAscii[i];
        lastWasBareBase = NUDI_BARE_BASE_LETTERS.has(monoAscii[i]);
        i++;
    }
    return out;
}

// For the four fonts whose macro targets Nudi Bi rather than Nudi Mono:
//   a2u:  X --charmap--> NudiBi --NUDIBI2MONO--> NudiMono --asciiToUnicode(nudi)--> Unicode
//   u2a:  Unicode --unicodeToASCII(nudi)--> NudiMono --NUDIMONO2BI--> NudiBi --charmap(inverse)--> X
// NUDIMONO2BI/NUDIBI2MONO are the macros' own Nudi Mono<->Bi pivot tables
// (see tools/MACRO-REVIEW.md), reused as-is rather than algorithmically
// inverted, since they're already the macro authors' intended pairing.
function pivotAsciiToUnicodeViaBi(text, x2nudibiMap, retainEnglish) {
    let source = text;
    let englishTexts = [];
    if (retainEnglish) {
        const extracted = _extractEnglishTokens(source, tok => _looksLikeEncodedKannadaBi(tok, x2nudibiMap));
        source = extracted.text;
        englishTexts = extracted.englishTexts;
    }
    const nudiBi = _substituteByMap(source, x2nudibiMap);
    let nudiMono = _substituteByMap(nudiBi, NUDIBI2MONO);
    if (!_hasBareAByte(_composedX2Mono(x2nudibiMap))) {
        nudiMono = _normalizeBareNudiConsonants(nudiMono);
    }
    let result = asciiToUnicode(nudiMono, false, 'nudi');
    if (englishTexts.length) result = _restoreEnglishTokens(result, englishTexts);
    return result;
}

function pivotUnicodeToAsciiViaBi(text, x2nudibiMap) {
    const extracted = _extractEnglishTokens(text);
    let nudiMonoAscii = unicodeToASCII(extracted.text, 'nudi');
    nudiMonoAscii = _dropUnneededBareA(nudiMonoAscii, _hasBareAByte(_composedX2Mono(x2nudibiMap)));
    const nudiBiAscii = _substituteByMap(nudiMonoAscii, NUDIMONO2BI);
    const { map: nudibi2x, keys } = _nudi2xFor(x2nudibiMap);
    let result = '';
    let i = 0;
    outer:
    while (i < nudiBiAscii.length) {
        if (nudiBiAscii[i] === '｢') {
            let j = i + 1;
            while (j < nudiBiAscii.length && nudiBiAscii[j] !== '｣') j++;
            result += nudiBiAscii.slice(i, j + 1);
            i = j + 1;
            continue;
        }
        for (const key of keys) {
            if (key.length && nudiBiAscii.startsWith(key, i)) {
                result += nudibi2x[key];
                i += key.length;
                continue outer;
            }
        }
        result += nudiBiAscii[i];
        i++;
    }
    if (extracted.englishTexts.length) result = _restoreEnglishTokens(result, extracted.englishTexts);
    return result;
}

function shree2ToUnicode(text, retainEnglish = false) {
    return pivotAsciiToUnicode(text, SHREE2_X2NUDI, retainEnglish);
}
function unicodeToShree2(text) {
    return pivotUnicodeToAscii(text, SHREE2_X2NUDI);
}
function prakashak2ToUnicode(text, retainEnglish = false) {
    return pivotAsciiToUnicode(text, PRAKASH2_X2NUDI, retainEnglish);
}
function unicodeToPrakashak2(text) {
    return pivotUnicodeToAscii(text, PRAKASH2_X2NUDI);
}
function akruti2ToUnicode(text, retainEnglish = false) {
    return pivotAsciiToUnicode(text, AKRUTI2_X2NUDI, retainEnglish);
}
function unicodeToAkruti2(text) {
    return pivotUnicodeToAscii(text, AKRUTI2_X2NUDI);
}
function surabhiToUnicode(text, retainEnglish = false) {
    return pivotAsciiToUnicode(text, SURABHI_X2NUDI, retainEnglish);
}
function unicodeToSurabhi(text) {
    return pivotUnicodeToAscii(text, SURABHI_X2NUDI);
}

// ---- Second batch: direct-to-Nudi-Mono fonts ----
function ismknttToUnicode(text, retainEnglish = false) {
    return pivotAsciiToUnicode(text, ISMKNTT_X2NUDI, retainEnglish);
}
function unicodeToIsmkntt(text) {
    return pivotUnicodeToAscii(text, ISMKNTT_X2NUDI);
}
function dharmaToUnicode(text, retainEnglish = false) {
    return pivotAsciiToUnicode(text, DHARMA_X2NUDI, retainEnglish);
}
function unicodeToDharma(text) {
    return pivotUnicodeToAscii(text, DHARMA_X2NUDI);
}
function jannaToUnicode(text, retainEnglish = false) {
    return pivotAsciiToUnicode(text, JANNA_X2NUDI, retainEnglish);
}
function unicodeToJanna(text) {
    return pivotUnicodeToAscii(text, JANNA_X2NUDI);
}
function srilipi850ToUnicode(text, retainEnglish = false) {
    return pivotAsciiToUnicode(text, SRILIPI850_X2NUDI, retainEnglish);
}
function unicodeToSrilipi850(text) {
    return pivotUnicodeToAscii(text, SRILIPI850_X2NUDI);
}
function shreedeccanToUnicode(text, retainEnglish = false) {
    return pivotAsciiToUnicode(text, SHREEDECCAN_X2NUDI, retainEnglish);
}
function unicodeToShreedeccan(text) {
    return pivotUnicodeToAscii(text, SHREEDECCAN_X2NUDI);
}
function surabhiknToUnicode(text, retainEnglish = false) {
    return pivotAsciiToUnicode(text, SURABHIKN_X2NUDI, retainEnglish);
}
function unicodeToSurabhikn(text) {
    return pivotUnicodeToAscii(text, SURABHIKN_X2NUDI);
}

// ---- Second batch: via-Nudi-Bi fonts ----
function suchikanToUnicode(text, retainEnglish = false) {
    return pivotAsciiToUnicodeViaBi(text, SUCHI_X2NUDIBI, retainEnglish);
}
function unicodeToSuchikan(text) {
    return pivotUnicodeToAsciiViaBi(text, SUCHI_X2NUDIBI);
}
function ismknbttToUnicode(text, retainEnglish = false) {
    return pivotAsciiToUnicodeViaBi(text, ISMKNBTT_X2NUDIBI, retainEnglish);
}
function unicodeToIsmknbtt(text) {
    return pivotUnicodeToAsciiViaBi(text, ISMKNBTT_X2NUDIBI);
}
function akrutibiToUnicode(text, retainEnglish = false) {
    return pivotAsciiToUnicodeViaBi(text, AKRUTIBI_X2NUDIBI, retainEnglish);
}
function unicodeToAkrutibi(text) {
    return pivotUnicodeToAsciiViaBi(text, AKRUTIBI_X2NUDIBI);
}
function winkeyToUnicode(text, retainEnglish = false) {
    return pivotAsciiToUnicodeViaBi(text, WINKEY_X2NUDIBI, retainEnglish);
}
function unicodeToWinkey(text) {
    return pivotUnicodeToAsciiViaBi(text, WINKEY_X2NUDIBI);
}

function asciiToUnicode(text, retainEnglish = false, fontType = 'nudi') {
    if (fontType === 'shree') {
        return shree2ToUnicode(text, retainEnglish);
    }
    if (fontType === 'prakashak') {
        return prakashak2ToUnicode(text, retainEnglish);
    }
    if (fontType === 'akruti') {
        return akruti2ToUnicode(text, retainEnglish);
    }
    if (fontType === 'surabhi') {
        return surabhiToUnicode(text, retainEnglish);
    }
    if (fontType === 'ismkntt') {
        return ismknttToUnicode(text, retainEnglish);
    }
    if (fontType === 'dharma') {
        return dharmaToUnicode(text, retainEnglish);
    }
    if (fontType === 'janna') {
        return jannaToUnicode(text, retainEnglish);
    }
    if (fontType === 'srilipi850') {
        return srilipi850ToUnicode(text, retainEnglish);
    }
    if (fontType === 'shreedeccan') {
        return shreedeccanToUnicode(text, retainEnglish);
    }
    if (fontType === 'surabhikn') {
        return surabhiknToUnicode(text, retainEnglish);
    }
    if (fontType === 'suchikan') {
        return suchikanToUnicode(text, retainEnglish);
    }
    if (fontType === 'ismknbtt') {
        return ismknbttToUnicode(text, retainEnglish);
    }
    if (fontType === 'akrutibi') {
        return akrutibiToUnicode(text, retainEnglish);
    }
    if (fontType === 'winkey') {
        return winkeyToUnicode(text, retainEnglish);
    }

    // Nudi files decoded from windows-1252 contain MICRO SIGN (U+00B5) for ಷ,
    // while the mapping tables use GREEK SMALL MU (U+03BC). The two glyphs are
    // visually identical; normalize so both convert correctly.
    let result = text.replace(/µ/g, 'μ');
    const englishTexts = [];

    if (retainEnglish) {
        let out = '';
        let i = 0;
        while (i < result.length) {
            if (result[i] === '\uFF62') {
                let j = i + 1;
                while (j < result.length && result[j] !== '\uFF63') j++;
                out += result.slice(i, j + 1);
                i = j + 1;
                continue;
            }
            const dirCode = _matchDirectionCodeAt(result, i);
            if (dirCode) {
                const idx = englishTexts.length;
                englishTexts.push(dirCode);
                out += _makePlaceholder(idx);
                i += dirCode.length;
                continue;
            }
            if (/[a-zA-Z]/.test(result[i])) {
                let j = i;
                while (j < result.length && /[a-zA-Z'-]/.test(result[j])) j++;
                const token = result.slice(i, j);
                if (_isEnglishToken(token, result, i)) {
                    const idx = englishTexts.length;
                    englishTexts.push(token);
                    out += _makePlaceholder(idx);
                } else {
                    out += token;
                }
                i = j;
            } else if (/[0-9]/.test(result[i])) {
                // Standalone number runs (e.g. "123", "3.14") are kept as-is;
                // digits directly adjacent to encoding bytes/letters are part
                // of the ASCII encoding and stay convertible.
                let j = i;
                while (j < result.length && /[0-9]/.test(result[j])) {
                    j++;
                    if (j < result.length - 1 && /[.,:]/.test(result[j]) && /[0-9]/.test(result[j + 1])) j++;
                }
                const numToken = result.slice(i, j);
                const before = i > 0 ? result[i - 1] : '';
                const after = j < result.length ? result[j] : '';
                const adjacentToCode = /[a-zA-ZÀ-ÿĀ-ſ]/.test(before) ||
                                       /[a-zA-ZÀ-ÿĀ-ſ]/.test(after);
                if (!adjacentToCode) {
                    const idx = englishTexts.length;
                    englishTexts.push(numToken);
                    out += _makePlaceholder(idx);
                } else {
                    out += numToken;
                }
                i = j;
            } else {
                out += result[i];
                i++;
            }
        }
        result = out;
    }

    const PLACEHOLDER_SPLIT = /(\uFF62[a-z]+\uFF63)/;
    const words = result.split(' ');
    const convertedWords = words.map(word => {
        if (word.length === 0) return word;
        const parts = word.split(PLACEHOLDER_SPLIT);
        const convertedParts = parts.map(part => {
            if (part.startsWith('\uFF62') && part.endsWith('\uFF63')) return part;
            if (part.length === 0) return part;
            let converted = part;
            
            converted = converted.replace(/([ೆೇೊ])([ÌÍÎÏÐÑÒÓÔÕÖ×ØÙÚÛÜÝÞßàáâãäåæèéêëìíî])([ÌÍÎÏÐÑÒÓÔÕÖ×ØÙÚÛÜÝÞßàáâãäåæèéêëìíî])([ÌÍÎÏÐÑÒÓÔÕÖ×ØÙÚÛÜÝÞßàáâãäåæèéêëìíî])/g, '$2$3$4$1');
            converted = converted.replace(/([ೆೇೊ])([ÌÍÎÏÐÑÒÓÔÕÖ×ØÙÚÛÜÝÞßàáâãäåæèéêëìíî])([ÌÍÎÏÐÑÒÓÔÕÖ×ØÙÚÛÜÝÞßàáâãäåæèéêëìíî])/g, '$2$3$1');
            converted = converted.replace(/([ೆೇೊ])([ÌÍÎÏÐÑÒÓÔÕÖ×ØÙÚÛÜÝÞßàáâãäåæèéêëìíî])/g, '$2$1');
            
            converted = _collapse_duplicate_e_marker(converted);
            converted = _reorder_aspirate_marker_before_vowel(converted);
            converted = _reorder_vattu_before_a_marker(converted);
            converted = _replace_from_map(converted);
            converted = _strip_orphan_a_marker(converted);
            converted = _replace_reph(converted);
            converted = _replace_vattakshara(converted);
            converted = _fix_conjuncts(converted);
            converted = _a2u_attach_orphan_u_vowel(converted);
            converted = converted.replace(/[0-9]/g, (d) => KN_DIGITS[parseInt(d)]);
            converted = _replace_a2u_anuswara_visarga(converted);
            converted = _a2u_post_process(converted);
            converted = _a2u_deerga_handle(converted);
            return converted;
        });
        return convertedParts.join('');
    });
    result = convertedWords.join(' ');

    if (retainEnglish && englishTexts.length > 0) {
        result = result.replace(_placeholderRe, (_, enc) => englishTexts[_decodeIdx(enc)]);
    }
    return result;
}

function convertNumbers(text, mode) {
    if (mode === 'keep') return text;
    if (mode === 'kn') {
        EN_DIGITS.forEach((d, i) => { text = text.split(d).join(KN_DIGITS[i]); });
    } else if (mode === 'en') {
        KN_DIGITS.forEach((d, i) => { text = text.split(d).join(EN_DIGITS[i]); });
    }
    return text;
}

function convert(text, numFormat, direction, retainEnglish = false, fontType = 'nudi') {
    let result;
    if (direction === 'a2u' || direction === 'auto') {
        result = asciiToUnicode(text, retainEnglish, fontType);
    } else if (direction === 'u2a') {
        result = unicodeToASCII(text, fontType);
    } else {
        result = text;
    }
    result = convertNumbers(result, numFormat);
    return result;
}

// Unicode to ASCII conversion
function unicodeToASCII(text, fontType = 'nudi') {
    let result = text;
    
    if (fontType === 'shree') {
        return unicodeToShree2(text);
    }
    if (fontType === 'prakashak') {
        return unicodeToPrakashak2(text);
    }
    if (fontType === 'akruti') {
        return unicodeToAkruti2(text);
    }
    if (fontType === 'surabhi') {
        return unicodeToSurabhi(text);
    }
    if (fontType === 'ismkntt') {
        return unicodeToIsmkntt(text);
    }
    if (fontType === 'dharma') {
        return unicodeToDharma(text);
    }
    if (fontType === 'janna') {
        return unicodeToJanna(text);
    }
    if (fontType === 'srilipi850') {
        return unicodeToSrilipi850(text);
    }
    if (fontType === 'shreedeccan') {
        return unicodeToShreedeccan(text);
    }
    if (fontType === 'surabhikn') {
        return unicodeToSurabhikn(text);
    }
    if (fontType === 'suchikan') {
        return unicodeToSuchikan(text);
    }
    if (fontType === 'ismknbtt') {
        return unicodeToIsmknbtt(text);
    }
    if (fontType === 'akrutibi') {
        return unicodeToAkrutibi(text);
    }
    if (fontType === 'winkey') {
        return unicodeToWinkey(text);
    }

    const ASCII_DEERGA = "Ã";
    const ASCII_VATT = "ÌÍÎÏÐÑÒÓÔÕÖ×ØÙÚÛÜÝÞßàáâãäåæèéêëìíî";
    
    // Handle vowel signs with vattakshara reordering
    result = result.replace(new RegExp(`([ೆೇೊ])([${ASCII_VATT}])`, 'g'), '$2$1');
    
    // Build reverse mapping
    const U2A_MAP = {};
    Object.entries(A2U_MAP).forEach(([k, v]) => U2A_MAP[v] = k);
    
    // Sort by length (longest first) - explicit comparator needed for Unicode
    const U2A_KEYS = Object.keys(U2A_MAP).sort((a, b) => b.length - a.length);
    
    // Replace using regex to handle overlapping matches properly
    for (const key of U2A_KEYS) {
        if (key.length > 0) {
            const regex = new RegExp(key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g');
            result = result.replace(regex, U2A_MAP[key]);
        }
    }
    
    // Replace halant
    result = result.split('್').join('ï');

    // Convert numbers
    result = result.replace(/[೦-೯]/g, (c) => EN_DIGITS['೦೧೨೩೪೫೬೭೮೯'.indexOf(c)]);

    // Emit MICRO SIGN (U+00B5, valid windows-1252) instead of GREEK SMALL MU
    // (U+03BC) so the ASCII output is byte-accurate for legacy Nudi tools.
    result = result.replace(/μ/g, 'µ');

    return result;
}

// ============================================================
// TAB SWITCHING
// ============================================================
function switchTab(id, btn) {
    document.querySelectorAll('.tab-pane-custom').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.nav-tabs-custom .nav-link').forEach(b => b.classList.remove('active'));
    document.getElementById(id).classList.add('active');
    btn.classList.add('active');
    if (id === 'tab-live') {
        setTimeout(function() {
            var el = document.getElementById('live-source');
            if (!el) return;
            el.focus();
            // Apply whichever keyboard is chosen in the visible dropdown
            if (typeof window.applyLiveKeyboard === 'function') {
                window.applyLiveKeyboard();
            }
        }, 250);
    }
}

// ============================================================
// FILE HANDLING
// ============================================================
document.addEventListener('DOMContentLoaded', function() {
    const dropzone = document.getElementById('dropzone');
    const fileInput = document.getElementById('file-input');
    
    if (!dropzone || !fileInput) return;
    
    dropzone.addEventListener('click', () => fileInput.click());
    dropzone.addEventListener('dragover', (e) => { e.preventDefault(); dropzone.classList.add('dragover'); });
    dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));
    dropzone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropzone.classList.remove('dragover');
        if (e.dataTransfer.files.length > 0) handleFile(e.dataTransfer.files[0]);
    });
    fileInput.addEventListener('change', (e) => { 
        if (e.target.files.length > 0) handleFile(e.target.files[0]); 
    });
});

// ============================================================
// OPTIONAL SERVER-SIDE SUBMISSION LOGGING (self-hosted server.js only)
//
// Fire-and-forget: conversion always happens client-side first, exactly as
// it always has (this app works fully offline / on GitHub Pages, which has
// no backend at all). When this page happens to be served by the
// self-hosted server.js instead, each explicit conversion is ALSO sent to
// POST /api/log-submission in the background so it can be reviewed later
// for improving font tables/heuristics - see DEPLOYMENT.md's "Submission
// logging" section (off by default there too - SAVE_SUBMISSIONS must be
// explicitly enabled server-side for anything to actually be written).
//
// Feature-detected once per page load via a quick GET /api/health - on
// GitHub Pages (or any static host) that request just 404s/fails since no
// such route exists there, so _serverLoggingAvailable stays false and
// nothing is ever sent. Never blocks, retries, or affects the UI either
// way - failures are silently swallowed.
// ============================================================
let _serverLoggingAvailable = false;
(function _detectServerLogging() {
    if (typeof fetch !== 'function') return;
    const controller = typeof AbortController === 'function' ? new AbortController() : null;
    const timeoutId = controller ? setTimeout(() => controller.abort(), 1500) : null;
    fetch('/api/health', controller ? { signal: controller.signal } : {})
        .then(r => (r && r.ok) ? r.json() : null)
        .then(data => { if (data && data.status === 'ok') _serverLoggingAvailable = true; })
        .catch(() => {})
        .finally(() => { if (timeoutId) clearTimeout(timeoutId); });
})();

function _logSubmissionToServer(payload) {
    if (!_serverLoggingAvailable || typeof fetch !== 'function') return;
    fetch('/api/log-submission', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    }).catch(() => {});
}

// ============================================================
// TEXT CONVERSION (Client-side for GitHub Pages)
// ============================================================
function convertText() {
    try {
        const text = document.getElementById('input-text').value;
        if (!text.trim()) {
            showToast('ದಯವಿಟ್ಟು ಪಠ್ಯವನ್ನು ಅಂಟಿಸಿ', 'error');
            return;
        }

        const numFormat = document.getElementById('number-format').value;
        const retainEl = document.getElementById('retain-english');
        const retainEnglish = retainEl ? retainEl.checked : false;
        let direction = document.getElementById('convert-direction').value;
        let fontType = document.getElementById('font-type').value;

        // Auto-detect font type
        if (fontType === 'auto') {
            const textLower = text.toLowerCase();
            const shreeIndicators = ['pü', 'wü', 'ñü', '±ü', 'êüá'];
            const hasShree = shreeIndicators.some(indicator => text.includes(indicator.toLowerCase()) || text.includes(indicator));
            fontType = hasShree ? 'shree' : 'nudi';
        }

        // Auto-detect direction
        if (direction === 'auto') {
            const unicodeCount = (text.match(/[\u0C80-\u0CFF]/g) || []).length;
            const asciiKnCount = (text.match(/[À-ÿøñð]/g) || []).length;
            direction = (unicodeCount > asciiKnCount) ? 'u2a' : 'a2u';
        }

        convertedText = convert(text, numFormat, direction, retainEnglish, fontType);
        document.getElementById('output-text').value = convertedText;
        document.getElementById('out-char-count').textContent = convertedText.length + ' ಅಕ್ಷರ';
        showToast('ಪರಿವರ್ತನೆ ಯಶಸ್ವಿಯಾಗಿದೆ', 'success');
        _logSubmissionToServer({ text, result: convertedText, direction, font: fontType, numFormat, retainEnglish });
    } catch(e) {
        console.error(e);
        showToast('ದೋಷ: ' + e.message, 'error');
    }
}

// ============================================================
// DETECT INPUT TYPE
// ============================================================
var _inputTextEl = document.getElementById('input-text');
if (_inputTextEl) _inputTextEl.addEventListener('input', function() {
    const text = this.value;
    document.getElementById('char-count').textContent = text.length + ' ಅಕ್ಷರ';
    
    if (text.length > 0) {
        // Count-based, not a plain "does it contain any of these chars"
        // check - matches the auto-direction logic in convertText() below,
        // which is what actually runs when the user hits Convert. The old
        // version flagged text as ASCII the moment it contained even ONE
        // character in [À-ÿøñð], but that range also covers ordinary
        // accented letters that show up in English loanwords/proper nouns
        // (café, résumé, jalapeño, Zürich, ...) - so a Kannada Unicode
        // document with a smattering of English mixed in got mislabeled
        // "ASCII ನುಡಿ/ಬರಹ" the moment it contained a single such word,
        // even though it was overwhelmingly real Unicode Kannada.
        const unicodeCount = (text.match(/[\u0C80-\u0CFF]/g) || []).length;
        const asciiKnCount = (text.match(/[À-ÿøñð]/g) || []).length;

        const badge = document.getElementById('detect-badge');
        const textSpan = document.getElementById('detect-text');
        badge.className = 'info-badge py-1 px-2';

        if (unicodeCount === 0 && asciiKnCount === 0) {
            badge.classList.add('badge-unknown');
            textSpan.textContent = 'ಪತ್ತೆ ಆಗಿಲ್ಲ';
        } else if (unicodeCount > asciiKnCount) {
            badge.classList.add('badge-unicode');
            textSpan.textContent = 'Unicode ಕನ್ನಡ';
        } else {
            badge.classList.add('badge-ascii');
            textSpan.textContent = 'ASCII ನುಡಿ/ಬರಹ';
        }
    } else {
        document.getElementById('detect-badge').className = 'info-badge badge-unknown py-1 px-2';
        document.getElementById('detect-text').textContent = 'ಪತ್ತೆ ಆಗಿಲ್ಲ';
    }
});

function clearText() {
    document.getElementById('input-text').value = '';
    document.getElementById('output-text').value = '';
    document.getElementById('char-count').textContent = '0 ಅಕ್ಷರ';
    document.getElementById('out-char-count').textContent = '';
    convertedText = '';
    document.getElementById('detect-badge').className = 'info-badge badge-unknown py-1 px-2';
    document.getElementById('detect-text').textContent = 'ಪತ್ತೆ ಆಗಿಲ್ಲ';
}

function copyOutput() {
    if (!convertedText) { showToast('ಮೊದಲು ಪರಿವರ್ತಿಸಿ', 'error'); return; }
    navigator.clipboard.writeText(convertedText).then(() => {
        showToast('ಕ್ಲಿಪ್‌ಬೋರ್ಡ್‌ಗೆ ಕಾಪಿ ಆಗಿದೆ', 'success');
    });
}

function downloadOutput(format) {
    if (!convertedText) {
        showToast('ಮೊದಲು ಪರಿವರ್ತಿಸಿ', 'error');
        return;
    }
    
    const blob = new Blob([convertedText], { type: 'text/plain;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'converted.txt';
    a.click();
    URL.revokeObjectURL(a.href);
    showToast('ಡೌನ್ಲೋಡ್ ಶುರುವಾಗಿದೆ', 'success');
}

// ============================================================
// FILE HANDLING
// ============================================================
document.addEventListener('DOMContentLoaded', function() {
    const dropzone = document.getElementById('dropzone');
    const fileInput = document.getElementById('file-input');
    
    if (!dropzone || !fileInput) return;
    
    dropzone.addEventListener('click', () => fileInput.click());
    dropzone.addEventListener('dragover', (e) => { e.preventDefault(); dropzone.classList.add('dragover'); });
    dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));
    dropzone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropzone.classList.remove('dragover');
        if (e.dataTransfer.files.length > 0) handleFile(e.dataTransfer.files[0]);
    });
    fileInput.addEventListener('change', (e) => { 
        if (e.target.files.length > 0) handleFile(e.target.files[0]); 
    });
});

function handleFile(f) {
    fileName = f.name;
    const ext = f.name.split('.').pop().toLowerCase();
    
    if (!['txt', 'docx'].includes(ext)) {
        showToast('TXT ಅಥವಾ DOCX ಫೈಲ್ ಮಾತ್ರ ಬೆಂಬಲಿತ', 'error');
        return;
    }
    
    document.getElementById('file-name').textContent = f.name;
    document.getElementById('file-size').textContent = formatBytes(f.size);
    
    if (ext === 'docx') {
        const reader = new FileReader();
        reader.onload = function(e) {
            const mammothLib = typeof mammoth !== 'undefined' ? mammoth : (typeof window.mammoth !== 'undefined' ? window.mammoth : null);
            if (!mammothLib) {
                showToast('DOCX library not loaded. Please refresh the page.', 'error');
                return;
            }
            if (typeof mammothLib.convertToMarkdown !== 'function') {
                console.error('convertToMarkdown not found. Available methods:', Object.keys(mammothLib));
                showToast('DOCX library invalid. Please try TXT files or refresh.', 'error');
                return;
            }
            // convertToMarkdown (not extractRawText) so that Word's
            // paragraph-level formatting - bullets, numbered lists, headings,
            // bold - survives as plain-text-safe markdown syntax ("- ", "1. ",
            // "# ", "__..__"). extractRawText discards all of that because
            // Word stores it as numPr/style XML properties, not literal
            // characters, so there was nothing left to preserve. The
            // resulting markdown punctuation passes through the Kannada
            // conversion pipeline untouched, same as any other ASCII text.
            mammothLib.convertToMarkdown({ arrayBuffer: e.target.result })
                .then(function(result) {
                    fileText = _stripMarkdownEscapes(result.value);
                    showFileInfo();
                })
                .catch(function(err) {
                    console.error(err);
                    showToast('DOCX ಓದುವುದು ವಿಫಲ: ' + err.message, 'error');
                });
        };
        reader.readAsArrayBuffer(f);
    } else {
        const reader = new FileReader();
        reader.onload = function(e) {
            // Unicode .txt files decode cleanly as strict UTF-8; legacy
            // Nudi/ASCII files are typically saved as Windows-1252 and
            // contain high-byte sequences that aren't valid UTF-8 - forcing
            // those through a plain UTF-8 decode (as this used to do via
            // reader.readAsText(f, 'utf-8')) doesn't error, it silently
            // mangles the bytes into unrelated characters (e.g. legacy
            // Nudi ASCII bytes coming out as stray real Kannada Unicode
            // letters mixed with Latin-1 supplement junk like "ಪÄ" - byte
            // corruption, not a conversion-logic bug). Same fallback the
            // Live Keyboard file loader already uses below.
            let text;
            try {
                text = new TextDecoder('utf-8', { fatal: true }).decode(e.target.result);
            } catch (err) {
                text = new TextDecoder('windows-1252').decode(e.target.result);
            }
            fileText = text;
            showFileInfo();
        };
        reader.readAsArrayBuffer(f);
    }
}

function showFileInfo() {
    const hasUnicode = /[\u0C80-\u0CFF]/.test(fileText);
    const format = hasUnicode ? 'Unicode' : 'ASCII';
    
    document.getElementById('file-info').style.display = 'block';
    document.getElementById('stat-chars').textContent = fileText.length;
    document.getElementById('stat-words').textContent = fileText.trim().split(/\s+/).length;
    document.getElementById('stat-format').textContent = format;
    document.getElementById('dropzone').style.display = 'none';
}

function clearFile() {
    fileText = '';
    fileName = '';
    document.getElementById('file-info').style.display = 'none';
    document.getElementById('dropzone').style.display = 'block';
    fileInput.value = '';
}

function convertFile() {
    try {
        if (!fileText) {
            showToast('ಮೊದಲು ಫೈಲ್ ಆಯ್ಕೆ ಮಾಡಿ', 'error');
            return;
        }

        const numFormat = document.getElementById('number-format').value;
        // Own checkbox for the file tab (previously this silently read the
        // main text tab's hidden 'retain-english' checkbox instead, which
        // the user had no visible control over while on the file tab -
        // effectively always off since that one defaults unchecked).
        const retainEl = document.getElementById('file-retain-english');
        const retainEnglish = retainEl ? retainEl.checked : false;
        let direction = document.getElementById('convert-direction').value;

        if (direction === 'auto') {
            const unicodeCount = (fileText.match(/[\u0C80-\u0CFF]/g) || []).length;
            const asciiKnCount = (fileText.match(/[À-ÿøñð]/g) || []).length;
            direction = (unicodeCount > asciiKnCount) ? 'u2a' : 'a2u';
        }

        convertedText = convert(fileText, numFormat, direction, retainEnglish);
        document.getElementById('file-output').textContent = convertedText;
        showToast('ಪರಿವರ್ತನೆ ಯಶಸ್ವಿಯಾಗಿದೆ', 'success');
        _logSubmissionToServer({ text: fileText, result: convertedText, direction, font: 'nudi', numFormat, retainEnglish });
    } catch(e) {
        console.error(e);
        showToast('ದೋಷ: ' + e.message, 'error');
    }
}

// ============================================================
// MIXED TEXT DETECTION
// ============================================================
function detectMixed() {
    const text = document.getElementById('detect-input').value;
    if (!text.trim()) {
        showToast('ದಯವಿಟ್ಟು ಪಠ್ಯವನ್ನು ಅಂಟಿಸಿ', 'error');
        return;
    }
    
    const resultsDiv = document.getElementById('detect-results');
    const alertDiv = document.getElementById('detect-alert');
    const highlightedDiv = document.getElementById('detect-highlighted');
    
    resultsDiv.style.display = 'block';
    
    let html = '';
    let mixedCount = 0;
    
    for (let i = 0; i < text.length; i++) {
        const ch = text[i];
        
        if (/[\u0C80-\u0CFF]/.test(ch)) {
            html += '<span style="background: rgba(40, 167, 69, 0.2); padding: 0 2px;">' + escapeHtml(ch) + '</span>';
            mixedCount++;
        } else if (/[A-Za-zÀ-ÿøñð]/.test(ch)) {
            html += '<span style="background: rgba(230, 126, 34, 0.2); padding: 0 2px;">' + escapeHtml(ch) + '</span>';
            mixedCount++;
        } else {
            html += escapeHtml(ch);
        }
    }
    
    highlightedDiv.innerHTML = '<div style="font-family: Anek Kannada, sans-serif; line-height: 2; word-break: break-word;">' + html + '</div>';
    
    if (mixedCount > 0) {
        alertDiv.className = 'alert alert-warning';
        alertDiv.textContent = mixedCount + ' ಮಿಶ್ರಿತ ಪಠ್ಯ ಕಂಡುಬಂದಿದೆ';
    } else {
        alertDiv.className = 'alert alert-success';
        alertDiv.textContent = 'ಮಿಶ್ರಿತ ಪಠ್ಯ ಇಲ್ಲ';
    }
}

// ============================================================
// UTILITIES
// ============================================================
function escapeHtml(text) {
    return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// mammoth's convertToMarkdown() (used for DOCX uploads to preserve bullets/
// headings/bold - see convertFile/Live Keyboard file loader) escapes any
// literal CommonMark-special character it finds in ordinary paragraph text
// by prefixing a backslash, e.g. "-" becomes "\-", "." becomes "\.", "(" ")"
// "!" "#" etc. all get the same treatment. This is correct behavior for a
// real markdown renderer, but here the "markdown" is just an intermediate
// carrier for plain text passed straight into the Kannada conversion engine
// - so every ordinary hyphen, period, exclamation mark, or parenthesis in
// the source document was showing up as a spurious "\" in the output. The
// bullet/numbered-list/heading/bold markers mammoth itself generates
// ("- ", "1. ", "# ", "__..__") are NOT escaped (no backslash prefix), so
// stripping "\" immediately before one of these characters removes only
// mammoth's defensive escaping and never touches the real structure markers.
function _stripMarkdownEscapes(text) {
    return text.replace(/\\([\\`*_{}\[\]()#+\-.!])/g, '$1');
}

function formatBytes(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / 1048576).toFixed(1) + ' MB';
}

function showToast(message, type) {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.className = 'toast-custom toast-' + type + ' show';
    setTimeout(() => toast.classList.remove('show'), 3000);
}

// Hide history section on static pages
document.addEventListener('DOMContentLoaded', function() {
    const historySection = document.getElementById('history');
    if (historySection) {
        historySection.style.display = 'none';
    }
});

// ============================================================
// URL FETCH AND CONVERT
// ============================================================
function detectFontsFromCSS(cssText) {
    const fonts = new Set();
    const fontFamilyRegex = /font-family:\s*['"]?([^'";]+)['"]?/gi;
    const fontFaceRegex = /@font-face\s*\{[^}]*font-family:\s*['"]?([^'";]+)['"]?/gi;
    
    let match;
    while ((match = fontFamilyRegex.exec(cssText)) !== null) {
        if (match[1] && !match[1].includes('inherit') && !match[1].includes('system')) {
            fonts.add(match[1].trim());
        }
    }
    while ((match = fontFaceRegex.exec(cssText)) !== null) {
        if (match[1]) {
            fonts.add(match[1].trim());
        }
    }
    
    return Array.from(fonts);
}

function extractTextFromHTML(html) {
    // Parsed via DOMParser rather than assigning to a live element's
    // innerHTML: a DOMParser document has no browsing context, so it never
    // fetches images/stylesheets or fires inline event-handler attributes
    // (onerror, onload, ...) - unlike a real (even detached) element, whose
    // resource-loading tags execute as soon as they're parsed in. Mirrors
    // the same approach already used in extractTextWithFontInfo below.
    const doc = new DOMParser().parseFromString(html, 'text/html');

    const scriptsAndStyles = doc.querySelectorAll('script, style, noscript');
    scriptsAndStyles.forEach(el => el.remove());

    let text = doc.body ? (doc.body.textContent || doc.body.innerText || '') : '';
    text = text.replace(/\s+/g, ' ').trim();

    return text;
}

function extractTextWithFontInfo(html, maxWords = 800) {
    if (!html.trim().startsWith('<')) {
        const text = html.replace(/\s+/g, ' ').trim();
        const wordCount = text.split(/\s+/).length;
        const isTruncated = wordCount > maxWords;
        const truncatedText = isTruncated ? text.split(/\s+/).slice(0, maxWords).join(' ') : text;
        return { text: truncatedText, fonts: [], isTruncated, totalWords: wordCount };
    }
    
    const parser = new DOMParser();
    const doc = parser.parseFromString(html, 'text/html');
    
    const scriptsAndStyles = doc.querySelectorAll('script, style, noscript');
    scriptsAndStyles.forEach(el => el.remove());
    
    const styles = doc.querySelectorAll('style');
    let allCSS = '';
    styles.forEach(style => {
        allCSS += style.textContent || '';
    });
    
    const detectedFonts = detectFontsFromCSS(allCSS);
    
    let text = doc.body.textContent || doc.body.innerText || '';
    text = text.replace(/\s+/g, ' ').trim();
    
    const wordCount = text.split(/\s+/).length;
    const isTruncated = wordCount > maxWords;
    
    if (isTruncated) {
        const words = text.split(/\s+/);
        text = words.slice(0, maxWords).join(' ');
    }
    
    return { text, fonts: detectedFonts, isTruncated, totalWords: wordCount };
}

async function fetchAndConvertUrl() {
    const urlInput = document.getElementById('url-input');
    const url = urlInput.value.trim();
    
    if (!url) {
        showToast('ದಯವಿಟ್ಟು URL ನ್ನು ನಮೂದಿಸಿ', 'error');
        return;
    }
    
    const loadingEl = document.getElementById('url-loading');
    const infoEl = document.getElementById('url-info');
    const fetchBtn = document.getElementById('url-fetch-btn');
    
    loadingEl.style.display = 'flex';
    infoEl.style.display = 'none';
    fetchBtn.disabled = true;
    
    const maxWords = 800;
    
    async function tryFetchWithProxy(proxyUrl) {
        const response = await fetch(proxyUrl);
        if (!response.ok) throw new Error('Fetch failed');
        return response.text();
    }
    
    async function tryFetchDirect(url) {
        try {
            return await fetch(url);
        } catch (e) {
            return null;
        }
    }
    
    try {
        let html = '';
        let success = false;
        
        const corsProxies = [
            { url: url => `https://r.jina.ai/http://${url.replace(/^https?:\/\//, '')}`, name: 'jina.ai' },
            { url: url => `https://api.allorigins.win/raw?url=${encodeURIComponent(url)}`, name: 'allorigins' },
            { url: url => `https://corsproxy.io/?${encodeURIComponent(url)}`, name: 'corsproxy.io' }
        ];
        
        for (const proxy of corsProxies) {
            try {
                const response = await fetch(proxy.url(url));
                if (response.ok) {
                    html = await response.text();
                    success = true;
                    break;
                }
            } catch (e) {
                console.log(`Proxy ${proxy.name} failed:`, e.message);
            }
        }
        
        if (!success) {
            showToast('URL ಪಡೆಯಲಾಗಲಿಲ್ಲ. ದಯವಿಟ್ಟು ಬೇರೆ URL ಪ್ರಯತ್ನಿಸಿ', 'error');
            loadingEl.style.display = 'none';
            fetchBtn.disabled = false;
            return;
        }
        
        const { text, fonts, isTruncated, totalWords } = extractTextWithFontInfo(html);
        
        document.getElementById('url-source-text').value = text;
        document.getElementById('detected-fonts').textContent = fonts.length > 0 ? fonts.join(', ') : 'ಯಾವುದೇ ಫಾಂಟ್ ಪತ್ತೆ ಆಗಿಲ್ಲ';
        
        if (isTruncated) {
            showToast(`ಟಿಪ್ಪಣಿ: ${totalWords} ಪದಗಳಲ್ಲಿ ${maxWords} ಪದಗಳು ಮಾತ್ರ ತೋರಿಸಲಾಗಿದೆ`, 'info');
        }
        
        const numFormat = document.getElementById('number-format').value;
        const retainEl = document.getElementById('url-retain-english');
        const retainEnglish = retainEl ? retainEl.checked : true;
        let direction = document.getElementById('url-convert-direction').value;
        let fontType = document.getElementById('url-font-type').value;
        
        if (direction === 'auto') {
            const unicodeCount = (text.match(/[\u0C80-\u0CFF]/g) || []).length;
            const asciiKnCount = (text.match(/[À-ÿøñð]/g) || []).length;
            direction = (unicodeCount > asciiKnCount) ? 'u2a' : 'a2u';
        }
        
        const converted = convert(text, numFormat, direction, retainEnglish, fontType);
        document.getElementById('url-output-text').value = converted;
        
        loadingEl.style.display = 'none';
        infoEl.style.display = 'block';
        
        showToast('URL ಪರಿವರ್ತನೆ ಯಶಸ್ವಿಯಾಗಿದೆ', 'success');
    } catch (error) {
        console.error(error);
        loadingEl.style.display = 'none';
        showToast('ದೋಷ: ' + error.message, 'error');
    } finally {
        fetchBtn.disabled = false;
    }
}

function copyUrlOutput() {
    const output = document.getElementById('url-output-text').value;
    if (!output) {
        showToast('ಮೊದಲು URL ಪರಿವರ್ತಿಸಿ', 'error');
        return;
    }
    navigator.clipboard.writeText(output).then(() => {
        showToast('ಕ್ಲಿಪ್‌ಬೋರ್ಡ್‌ಗೆ ಕಾಪಿ ಆಗಿದೆ', 'success');
    });
}

function downloadUrlOutput(format) {
    const output = document.getElementById('url-output-text').value;
    if (!output) {
        showToast('ಮೊದಲು URL ಪರಿವರ್ತಿಸಿ', 'error');
        return;
    }
    
    const blob = new Blob([output], { type: 'text/plain;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'converted.txt';
    a.click();
    URL.revokeObjectURL(a.href);
    showToast('ಡೌನ್ಲೋಡ್ ಶುರುವಾಗಿದೆ', 'success');
}

// ============================================================
// LIVE EDITOR - Two directions
// a2u (ASCII simulator): left pane always shows ASCII encoding
//   (Unicode typed via IME is auto-converted to ASCII in place),
//   right pane shows Unicode. A preview box shows how the ASCII
//   text looks in a legacy (Nudi-style) editor.
// u2a: left pane keeps Unicode as typed (IME friendly),
//   right pane shows the ASCII encoding for the selected font.
// English/Latin text passes through unchanged in both directions.
// ============================================================
document.addEventListener('DOMContentLoaded', function() {
    const source = document.getElementById('live-source');
    const result = document.getElementById('live-result');
    const fontType = document.getElementById('live-font-type');
    const retainEnglish = document.getElementById('live-retain-english');
    const directionEl = document.getElementById('live-direction');
    const previewWrap = document.getElementById('live-ascii-preview-wrap');
    const previewBox = document.getElementById('live-ascii-preview');
    if (!source) return;

    var composing = false;
    var converting = false;

    function currentDirection() {
        return directionEl ? directionEl.value : 'a2u';
    }

    function applyDirectionUI() {
        var dir = currentDirection();
        var srcLabel = document.getElementById('live-source-label');
        var resLabel = document.getElementById('live-result-label');
        var help = document.getElementById('live-help-text');
        if (dir === 'u2a') {
            if (srcLabel) srcLabel.innerHTML = '<i class="fas fa-file-import me-1"></i> Unicode ಮೂಲ';
            if (resLabel) resLabel.innerHTML = '<i class="fas fa-file-export me-1"></i> ASCII ಫಲಿತಾಂಶ <small class="text-muted">(ಸಂಪಾದಿಸಬಹುದು)</small>';
            if (help) help.innerHTML = 'ಎಡಭಾಗದಲ್ಲಿ Unicode ಕನ್ನಡ ಟೈಪ್ ಮಾಡಿ — ಮೇಲಿನ <strong>ಕೀಬೋರ್ಡ್</strong> ಆಯ್ಕೆಯಿಂದ KGP, InScript, ಅಥವಾ ಲಿಪ್ಯಂತರಣ ಆರಿಸಿ. ಆಯ್ದ ಫಾಂಟ್‌ನ ASCII ಎನ್ಕೋಡಿಂಗ್ ಬಲಭಾಗದಲ್ಲಿ ಲೈವ್ ಆಗಿ ಕಾಣಿಸುತ್ತದೆ. ಇಂಗ್ಲಿಷ್ ಪಠ್ಯ ಇದ್ದಂತೆಯೇ ಉಳಿಯುತ್ತದೆ.';
            source.placeholder = 'ಇಲ್ಲಿ Unicode ಕನ್ನಡ ಟೈಪ್ ಮಾಡಿ...';
            if (previewWrap) previewWrap.style.display = 'none';
            if (retainEnglish) retainEnglish.disabled = true;
        } else {
            if (srcLabel) srcLabel.innerHTML = '<i class="fas fa-file-import me-1"></i> ASCII ಮೂಲ';
            if (resLabel) resLabel.innerHTML = '<i class="fas fa-file-export me-1"></i> Unicode ಫಲಿತಾಂಶ <small class="text-muted">(ಸಂಪಾದಿಸಬಹುದು)</small>';
            if (help) help.innerHTML = 'ಎಡಭಾಗದಲ್ಲಿ ಟೈಪ್ ಮಾಡಿ — ಅದರ ASCII ಎನ್ಕೋಡಿಂಗ್ ಎಡಭಾಗದಲ್ಲಿ ಕಾಣಿಸುತ್ತದೆ ಮತ್ತು Unicode ಪರಿವರ್ತನೆ ಬಲಭಾಗದಲ್ಲಿ ಲೈವ್ ಆಗಿ ಕಾಣಿಸುತ್ತದೆ. ಕನ್ನಡ ಟೈಪ್ ಮಾಡಲು ಮೇಲಿನ <strong>ಕೀಬೋರ್ಡ್</strong> ಆಯ್ಕೆಯಿಂದ KGP, InScript, ಅಥವಾ ಲಿಪ್ಯಂತರಣ ಆರಿಸಿ. ಇಂಗ್ಲಿಷ್ ಪಠ್ಯ ಇದ್ದಂತೆಯೇ ಉಳಿಯುತ್ತದೆ.';
            source.placeholder = 'ಇಲ್ಲಿ ಟೈಪ್ ಮಾಡಿ — ASCII ಎನ್ಕೋಡಿಂಗ್ ಸ್ವಯಂಚಾಲಿತವಾಗಿ ತೋರಿಸಲ್ಪಡುತ್ತದೆ...';
            if (previewWrap) previewWrap.style.display = '';
            if (retainEnglish) retainEnglish.disabled = false;
        }
        if (typeof liveApplyEditorFont === 'function') liveApplyEditorFont();
        if (typeof window.applyLiveKeyboard === 'function') window.applyLiveKeyboard();
    }

    function toAscii(text, font) {
        if (!text) return text;
        var hasUnicode = /[\u0C80-\u0CFF]/.test(text);
        if (!hasUnicode) return text;
        return unicodeToASCII(text, font);
    }

    function update() {
        if (composing || converting) return;
        var text = source.value;
        var font = fontType.value;
        var retain = retainEnglish.checked;
        var dir = currentDirection();
        document.getElementById('live-source-count').textContent = text.length + ' ಅಕ್ಷರ';

        if (!text.trim()) {
            result.value = '';
            if (previewBox) previewBox.textContent = '';
            document.getElementById('live-result-count').textContent = '0 ಅಕ್ಷರ';
            return;
        }

        try {
            if (dir === 'u2a') {
                // Left pane keeps Unicode as typed; right pane shows ASCII.
                // Latin/English text passes through the u2a maps untouched.
                var ascii = convert(text, 'keep', 'u2a', true, font);
                result.value = ascii;
                document.getElementById('live-result-count').textContent = ascii.length + ' ಅಕ್ಷರ';
            } else {
                // ASCII simulator: normalize Unicode typed via IME into ASCII in place
                var asciiText = toAscii(text, font);
                if (asciiText !== text) {
                    var pos = source.selectionStart + (asciiText.length - text.length);
                    converting = true;
                    source.value = asciiText;
                    try { source.setSelectionRange(pos, pos); } catch(e2) {}
                    converting = false;
                    text = asciiText;
                    document.getElementById('live-source-count').textContent = text.length + ' ಅಕ್ಷರ';
                }
                var converted = convert(text, 'keep', 'a2u', retain, font);
                result.value = converted;
                document.getElementById('live-result-count').textContent = converted.length + ' ಅಕ್ಷರ';
                // Preview: how this ASCII text renders inside a legacy-font editor
                if (previewBox) previewBox.textContent = converted;
            }
        } catch(e) {
            result.value = 'ದೋಷ: ' + e.message;
        }
    }

    function onDirectionChange() {
        var dir = currentDirection();
        // Carry the text across the mode switch so nothing is lost
        var text = source.value;
        if (text.trim()) {
            try {
                converting = true;
                if (dir === 'u2a') {
                    // Coming from ASCII mode: left pane becomes Unicode
                    if (!/[ಀ-೿]/.test(text)) {
                        source.value = convert(text, 'keep', 'a2u', true, fontType.value);
                    }
                } else {
                    // Coming from Unicode mode: left pane becomes ASCII
                    source.value = toAscii(text, fontType.value);
                }
                converting = false;
            } catch(e) { converting = false; }
        }
        applyDirectionUI();
        update();
    }

    // Reverse editing: typing in the result pane updates the source pane
    function updateFromResult() {
        if (composing || converting) return;
        var text = result.value;
        var font = fontType.value;
        var dir = currentDirection();
        document.getElementById('live-result-count').textContent = text.length + ' ಅಕ್ಷರ';

        try {
            converting = true;
            if (!text.trim()) {
                source.value = '';
                if (previewBox) previewBox.textContent = '';
            } else if (dir === 'u2a') {
                // Right pane holds ASCII -> left pane gets Unicode
                source.value = convert(text, 'keep', 'a2u', true, font);
            } else {
                // Right pane holds Unicode -> left pane gets ASCII
                source.value = convert(text, 'keep', 'u2a', true, font);
                if (previewBox) previewBox.textContent = text;
            }
            document.getElementById('live-source-count').textContent = source.value.length + ' ಅಕ್ಷರ';
            converting = false;
        } catch(e) {
            converting = false;
        }
    }

    source.addEventListener('compositionstart', function() { composing = true; });
    source.addEventListener('compositionend', function() { composing = false; update(); });
    source.addEventListener('input', update);
    result.addEventListener('compositionstart', function() { composing = true; });
    result.addEventListener('compositionend', function() { composing = false; updateFromResult(); });
    result.addEventListener('input', updateFromResult);
    fontType.addEventListener('change', update);
    retainEnglish.addEventListener('change', update);
    if (directionEl) directionEl.addEventListener('change', onDirectionChange);

    applyDirectionUI();
    if (source.value.trim()) update();
});

// ============================================================
// LIVE EDITOR TOOLBARS - both panes: file open, font, copy,
// download, expand, clear
// ============================================================
var liveEditorPrefs = {
    source: { size: 0 },  // 0 = use pane default
    result: { size: 0 }
};
var liveFileTarget = 'source';

// Editor font registry. To embed a legacy ASCII font later:
// 1. add @font-face in css/style.css, 2. add an entry + <option> here.
var LIVE_EDITOR_FONTS = {
    mono: "'Courier New', 'IBM Plex Mono', 'Menlo', monospace",
    plex: "'IBM Plex Sans', sans-serif",
    anek: "'Anek Kannada', sans-serif"
};

// Which format a pane currently holds ('unicode' or 'ascii')
function livePaneFormat(side) {
    var dirEl = document.getElementById('live-direction');
    var isU2a = dirEl && dirEl.value === 'u2a';
    var holdsUnicode = (side === 'source') ? isU2a : !isU2a;
    return holdsUnicode ? 'unicode' : 'ascii';
}

function liveApplyEditorFont(side) {
    (side ? [side] : ['source', 'result']).forEach(function(s) {
        var el = document.getElementById('live-' + s);
        if (!el) return;
        var sel = document.getElementById('live-editor-font-' + s);
        var choice = sel ? sel.value : 'auto';
        var holdsUnicode = livePaneFormat(s) === 'unicode';
        var family, size;
        if (choice === 'auto') {
            family = holdsUnicode ? LIVE_EDITOR_FONTS.anek : LIVE_EDITOR_FONTS.mono;
            size = liveEditorPrefs[s].size || (holdsUnicode ? 17 : 13);
        } else {
            family = LIVE_EDITOR_FONTS[choice] || LIVE_EDITOR_FONTS.mono;
            size = liveEditorPrefs[s].size || (choice === 'anek' ? 17 : 13);
        }
        el.style.setProperty('font-family', family, 'important');
        el.style.setProperty('font-size', size + 'px', 'important');
    });
}

function liveFontSizeFor(side, delta) {
    var el = document.getElementById('live-' + side);
    var current = liveEditorPrefs[side].size ||
        (el ? parseInt(getComputedStyle(el).fontSize, 10) : 13) || 13;
    liveEditorPrefs[side].size = Math.min(28, Math.max(10, current + delta));
    liveApplyEditorFont(side);
}

function liveCopy(side) {
    var el = document.getElementById('live-' + side);
    if (!el || !el.value) { showToast('ಪಠ್ಯ ಖಾಲಿ ಇದೆ', 'error'); return; }
    navigator.clipboard.writeText(el.value).then(function() {
        showToast('ಕ್ಲಿಪ್‌ಬೋರ್ಡ್‌ಗೆ ಕಾಪಿ ಆಗಿದೆ', 'success');
    });
}

function liveDownload(side) {
    var el = document.getElementById('live-' + side);
    if (!el || !el.value) { showToast('ಪಠ್ಯ ಖಾಲಿ ಇದೆ', 'error'); return; }
    downloadBlob(el.value, 'kannada-' + livePaneFormat(side) + '.txt');
    showToast('ಡೌನ್‌ಲೋಡ್ ಶುರುವಾಗಿದೆ', 'success');
}

// Format-based downloads (ascii / unicode / both), independent of which
// pane currently holds which format
function liveFormats() {
    var dirEl = document.getElementById('live-direction');
    var isU2a = dirEl && dirEl.value === 'u2a';
    var src = document.getElementById('live-source');
    var res = document.getElementById('live-result');
    return {
        ascii: (isU2a ? res : src) ? (isU2a ? res.value : src.value) : '',
        unicode: (isU2a ? src : res) ? (isU2a ? src.value : res.value) : ''
    };
}

function liveDownloadFormat(fmt) {
    var f = liveFormats();
    if (fmt === 'ascii') {
        if (!f.ascii) { showToast('ASCII ಪಠ್ಯ ಖಾಲಿ ಇದೆ', 'error'); return; }
        downloadBlob(f.ascii, 'kannada-ascii.txt');
    } else if (fmt === 'unicode') {
        if (!f.unicode) { showToast('Unicode ಪಠ್ಯ ಖಾಲಿ ಇದೆ', 'error'); return; }
        downloadBlob(f.unicode, 'kannada-unicode.txt');
    } else {
        if (!f.ascii && !f.unicode) { showToast('ಪಠ್ಯ ಖಾಲಿ ಇದೆ', 'error'); return; }
        var font = document.getElementById('live-font-type');
        var label = font && font.value !== 'nudi'
            ? font.value.charAt(0).toUpperCase() + font.value.slice(1)
            : 'Nudi / Baraha';
        downloadBlob(
            '=== ASCII (' + label + ') ===\n' + f.ascii + '\n\n=== Unicode ===\n' + f.unicode,
            'kannada-both.txt'
        );
    }
    showToast('ಡೌನ್‌ಲೋಡ್ ಶುರುವಾಗಿದೆ', 'success');
}

function liveExpand(side) {
    var el = document.getElementById('live-' + side);
    if (el) el.classList.toggle('pane-expanded');
}

function liveClearPane(side) {
    var el = document.getElementById('live-' + side);
    if (!el) return;
    el.value = '';
    el.dispatchEvent(new Event('input'));
    el.focus();
}

function liveOpenFileFor(side) {
    liveFileTarget = side || 'source';
    var inp = document.getElementById('live-file-input');
    if (inp) inp.click();
}

document.addEventListener('DOMContentLoaded', function() {
    var inp = document.getElementById('live-file-input');
    if (!inp) return;

    function loadIntoEditor(text, name, note) {
        var side = liveFileTarget;
        var el = document.getElementById('live-' + side);
        var dirSel = document.getElementById('live-direction');
        if (!el) return;
        if (!text || !text.trim()) {
            showToast('ಫೈಲ್‌ನಲ್ಲಿ ಪಠ್ಯ ಸಿಗಲಿಲ್ಲ' + (note ? ' (' + note + ')' : ''), 'error');
            return;
        }
        // Pick the direction that makes this pane match the file's format:
        // source holds Unicode in u2a; result holds Unicode in a2u.
        var isUnicode = /[ಀ-೿]/.test(text);
        var wanted = (side === 'source')
            ? (isUnicode ? 'u2a' : 'a2u')
            : (isUnicode ? 'a2u' : 'u2a');
        if (dirSel && dirSel.value !== wanted) {
            dirSel.value = wanted;
            dirSel.dispatchEvent(new Event('change'));
        }
        el.value = text;
        el.dispatchEvent(new Event('input'));
        showToast('ಫೈಲ್ ಲೋಡ್ ಆಗಿದೆ: ' + name + (note ? ' — ' + note : ''), 'success');
    }

    // DOCX is a zip; embedded images live under word/media/. A latin1 decode
    // of the raw bytes lets us check for that path cheaply without unzipping.
    function docxHasImages(arrayBuffer) {
        try {
            return new TextDecoder('latin1').decode(arrayBuffer).indexOf('word/media/') !== -1;
        } catch (e) { return false; }
    }

    inp.addEventListener('change', function() {
        var f = inp.files[0];
        if (!f) return;
        var ext = f.name.split('.').pop().toLowerCase();
        if (ext === 'docx') {
            var r = new FileReader();
            r.onload = function(e) {
                var m = (typeof mammoth !== 'undefined') ? mammoth : window.mammoth;
                if (!m || typeof m.convertToMarkdown !== 'function') {
                    showToast('DOCX ಲೈಬ್ರರಿ ಲಭ್ಯವಿಲ್ಲ — ಪುಟ ರಿಫ್ರೆಶ್ ಮಾಡಿ', 'error');
                    return;
                }
                var note = docxHasImages(e.target.result)
                    ? 'ಚಿತ್ರಗಳನ್ನು ಬಿಡಲಾಗಿದೆ (ಪಠ್ಯ ಮಾತ್ರ)'
                    : '';
                // convertToMarkdown preserves bullets/numbering/headings/bold
                // as markdown syntax; extractRawText discarded all of it.
                m.convertToMarkdown({ arrayBuffer: e.target.result })
                    .then(function(res) { loadIntoEditor(_stripMarkdownEscapes(res.value), f.name, note); })
                    .catch(function(err) { showToast('DOCX ಓದುವುದು ವಿಫಲ: ' + err.message, 'error'); });
            };
            r.readAsArrayBuffer(f);
        } else {
            var r2 = new FileReader();
            r2.onload = function(e) {
                var text;
                try {
                    // Unicode files decode cleanly as UTF-8; legacy Nudi/ASCII
                    // files contain high-bytes that fail strict UTF-8 and are
                    // decoded as windows-1252 instead.
                    text = new TextDecoder('utf-8', { fatal: true }).decode(e.target.result);
                } catch (err) {
                    text = new TextDecoder('windows-1252').decode(e.target.result);
                }
                loadIntoEditor(text, f.name);
            };
            r2.readAsArrayBuffer(f);
        }
        inp.value = '';
    });
});

// ============================================================
// BUG REPORTING - opens the GitHub issue form prefilled with
// the current conversion state (text, output, font, direction)
// ============================================================
function reportBug() {
    var REPO = 'https://github.com/sanchaya/kannada-font-converter/issues/new';
    var LIMIT = 400; // keep the URL well under browser/GitHub limits
    function clip(s) {
        s = (s || '').trim();
        return s.length > LIMIT ? s.slice(0, LIMIT) + '\n... (truncated)' : s;
    }
    function val(id) {
        var el = document.getElementById(id);
        return el ? el.value : '';
    }

    var active = document.querySelector('.tab-pane-custom.active');
    var tab = active ? active.id : 'tab-text';
    var input = '', output = '', section = 'ಪಠ್ಯ (Text)', font = '', dir = '';

    if (tab === 'tab-live') {
        section = 'ಲೈವ್ ಸಂಪಾದಕ (Live editor)';
        var d = val('live-direction');
        dir = d === 'u2a' ? 'Unicode → ASCII' : 'ASCII → Unicode';
        input = val('live-source');
        output = val('live-result');
        font = val('live-font-type');
    } else if (tab === 'tab-url') {
        section = 'URL';
        input = val('url-source-text') || val('url-input');
        output = val('url-output-text');
        font = val('url-font-type');
        dir = val('url-convert-direction') === 'u2a' ? 'Unicode → ASCII' : 'ASCII → Unicode';
    } else if (tab === 'tab-detect') {
        section = 'ಮಿಶ್ರಿತ ಪಠ್ಯ ಪತ್ತೆ (Mixed-text detection)';
        input = val('detect-input');
    } else if (tab === 'tab-file') {
        section = 'ಫೈಲ್ (File)';
        input = typeof fileText === 'string' ? fileText : '';
        var out = document.getElementById('file-output');
        output = out ? out.textContent : '';
        font = val('font-type');
    } else {
        input = val('input-text');
        output = val('output-text');
        font = val('font-type');
        var cd = val('convert-direction');
        dir = cd === 'u2a' ? 'Unicode → ASCII' : (cd === 'a2u' ? 'ASCII → Unicode' : '');
    }

    var FONT_LABELS = {
        nudi: 'Nudi / Baraha', shree: 'ShreeLipi',
        prakashak: 'Prakashak', akruti: 'Akruti', surabhi: 'Surabhi (KND)',
        auto: 'ಸ್ವಯಂಚಾಲಿತ / Auto'
    };

    var params = new URLSearchParams();
    params.set('template', 'bug_report.yml');
    params.set('section', section);
    if (input) params.set('input-text', clip(input));
    if (output) params.set('actual', clip(output));
    if (FONT_LABELS[font]) params.set('font', FONT_LABELS[font]);
    if (dir) params.set('direction', dir);
    params.set('browser', navigator.userAgent);

    window.open(REPO + '?' + params.toString(), '_blank', 'noopener');
}

function downloadBlob(content, filename) {
    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    a.click();
    URL.revokeObjectURL(a.href);
}