/* YazKlinik D700 - Runtime text normalize (mojibake guard)
   Klinik ekranda kalan bozuk UTF-8/CP1252 goruntulerini
   tarayici tarafinda otomatik duzeltir.
*/
(function () {
  'use strict';
  if (window.__ykTextNormalizeLoaded) return;
  window.__ykTextNormalizeLoaded = true;

  var MOJIBAKE_RE = /Ãƒ|Ã‚|Ã¢|Ã…|Ã„|ï¿½/;
  var C1_MAP = {
    0x80: 0x20AC, 0x82: 0x201A, 0x83: 0x0192, 0x84: 0x201E, 0x85: 0x2026,
    0x86: 0x2020, 0x87: 0x2021, 0x88: 0x02C6, 0x89: 0x2030, 0x8A: 0x0160,
    0x8B: 0x2039, 0x8C: 0x0152, 0x8E: 0x017D, 0x91: 0x2018, 0x92: 0x2019,
    0x93: 0x201C, 0x94: 0x201D, 0x95: 0x2022, 0x96: 0x2013, 0x97: 0x2014,
    0x98: 0x02DC, 0x99: 0x2122, 0x9A: 0x0161, 0x9B: 0x203A, 0x9C: 0x0153,
    0x9E: 0x017E, 0x9F: 0x0178
  };

  function cp1252Char(code) {
    var mapped = C1_MAP[code];
    return String.fromCodePoint(mapped || code);
  }

  function tryLatinToUtf8(input) {
    try {
      var s = String(input || '');
      if (!s) return s;
      var chars = [];
      for (var i = 0; i < s.length; i++) {
        var cc = s.charCodeAt(i);
        if (cc > 255) return s;
        chars.push(cp1252Char(cc));
      }
      // encode to bytes via charCode <=255 representation
      var bytes = new Uint8Array(chars.length);
      for (var j = 0; j < chars.length; j++) {
        bytes[j] = chars[j].charCodeAt(0) & 0xFF;
      }
      var out = new TextDecoder('utf-8', { fatal: false }).decode(bytes);
      return out || s;
    } catch (_e) {
      return String(input || '');
    }
  }

  function normalizeText(raw) {
    var s = String(raw || '');
    if (!s || !MOJIBAKE_RE.test(s)) return s;
    var prev = s;
    for (var i = 0; i < 3; i++) {
      var next = tryLatinToUtf8(prev);
      if (!next || next === prev) break;
      prev = next;
      if (!MOJIBAKE_RE.test(prev)) break;
    }
    // Last-mile replacements frequently seen in D700 UI
    return prev
      .replace(/ÃƒÆ’Ã¢â‚¬â€œnce/g, 'Ã–nce')
      .replace(/ÃƒÆ’Ã¢â‚¬â€œ/g, 'Ã–')
      .replace(/Ãƒâ€Ã‚Â°/g, 'Ä°')
      .replace(/Ãƒâ€Ã‚Â±/g, 'Ä±')
      .replace(/Ãƒâ€Ã…Â¸/g, 'ÄŸ')
      .replace(/Ãƒâ€¦Ã…Â¸/g, 'ÅŸ')
      .replace(/Ãƒâ€¦Ã…/g, 'Å')
      .replace(/ÃƒÆ’Ã‚Â¼/g, 'Ã¼')
      .replace(/ÃƒÆ’Ã…/g, 'Ãœ')
      .replace(/ÃƒÆ’Ã‚Â¶/g, 'Ã¶')
      .replace(/ÃƒÆ’Ã‚Â§/g, 'Ã§')
      .replace(/ÃƒÆ’Ã¢â‚¬Â¡/g, 'Ã‡')
      .replace(/Ã¢â‚¬â„¢/g, "'")
      .replace(/Ã¢â‚¬Å“/g, '"')
      .replace(/Ã¢â‚¬/g, '"')
      .replace(/Ã¢â‚¬â€œ/g, '-')
      .replace(/Ã¢â‚¬â€/g, '-');
  }

  function shouldSkipNode(node) {
    if (!node || !node.parentNode) return true;
    var p = node.parentNode;
    var tn = (p.nodeName || '').toLowerCase();
    return tn === 'script' || tn === 'style' || tn === 'noscript' ||
      tn === 'textarea' || tn === 'input' || tn === 'code' || tn === 'pre';
  }

  function normalizeTextNode(node) {
    if (!node || node.nodeType !== 3 || shouldSkipNode(node)) return;
    var oldText = node.nodeValue || '';
    if (!oldText || !MOJIBAKE_RE.test(oldText)) return;
    var fixed = normalizeText(oldText);
    if (fixed && fixed !== oldText) node.nodeValue = fixed;
  }

  function normalizeTree(root) {
    if (!root) return;
    try {
      var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null);
      var n;
      while ((n = walker.nextNode())) normalizeTextNode(n);
    } catch (_e) {}
  }

  function normalizeAttrs(root) {
    if (!root || !root.querySelectorAll) return;
    var nodes = root.querySelectorAll('[title],[aria-label],[placeholder]');
    for (var i = 0; i < nodes.length; i++) {
      var el = nodes[i];
      ['title', 'aria-label', 'placeholder'].forEach(function (k) {
        try {
          var v = el.getAttribute(k);
          if (v && MOJIBAKE_RE.test(v)) {
            var fixed = normalizeText(v);
            if (fixed && fixed !== v) el.setAttribute(k, fixed);
          }
        } catch (_e) {}
      });
    }
  }

  function runNormalize(root) {
    normalizeTree(root || document.body);
    normalizeAttrs(root || document.body);
  }

  function boot() {
    runNormalize(document.body);
    try {
      var obs = new MutationObserver(function (list) {
        for (var i = 0; i < list.length; i++) {
          var m = list[i];
          if (m.type === 'characterData') {
            normalizeTextNode(m.target);
            continue;
          }
          for (var j = 0; j < m.addedNodes.length; j++) {
            var n = m.addedNodes[j];
            if (!n) continue;
            if (n.nodeType === 3) normalizeTextNode(n);
            else if (n.nodeType === 1) runNormalize(n);
          }
        }
      });
      obs.observe(document.body, {
        childList: true,
        subtree: true,
        characterData: true
      });
      window.__ykTextNormalizeObserver = obs;
    } catch (_e) {}
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot, { once: true });
  } else {
    boot();
  }
})();


