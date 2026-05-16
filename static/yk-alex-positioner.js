/* YazKlinik D300 - Alex Bar Positioner (2026-05-16)
   Mevcut #ykVoiceAgent (Alex bar) uzerine surukleme + preset konum +
   gizle/goster + hafiza katmani ekler. HIcbir mevcut JS/CSS/HTML
   degistirilmez; sadece DOM'a 2 ek dugme ve dinleyici eklenir.

   Yetenekler:
     - Surukle (grip kolundan): bar viewport icinde herhangi bir noktaya
     - Preset menu (zar simgesi):
         Merkez Alt (varsayilan), Merkez Ust,
         Sol Alt, Sag Alt, Sol Ust, Sag Ust,
         Tam Merkez, Mini (FAB),
         Tam Gizle (Alt+A ile tekrar acilir)
     - Mini snap: koselere yakin birakilirsa otomatik snap (8px)
     - Position memory: localStorage["ykAlexPosition"] = {preset, x, y}
     - Klavye kisayollari:
         Alt+A    = bar goster/gizle
         Alt+M    = mini (FAB) moduna gec
         Alt+C    = bara odaklan (input)
     - Mobil: <600px ise drag kapali (mevcut sticky alt davranisi korunur)

   Hicbir veriyi sunucuya gondermez. Tum tercih sadece tarayicida.
*/

(function() {
  'use strict';

  if (window.__ykAlexPositionerLoaded) return;
  window.__ykAlexPositionerLoaded = true;

  var STORAGE_KEY = 'ykAlexPosition';
  var BAR_ID = 'ykVoiceAgent';
  var SNAP_PX = 8;
  var MIN_VIEWPORT_PX = 600;

  // --- Inject minimal CSS (sadece bizim ek elementler) ---
  if (!document.getElementById('yk-alex-positioner-css')) {
    var style = document.createElement('style');
    style.id = 'yk-alex-positioner-css';
    style.textContent = [
      '.yk-alex-grip {',
      '  display: inline-flex !important;',
      '  align-items: center !important;',
      '  justify-content: center !important;',
      '  width: 22px !important;',
      '  height: 32px !important;',
      '  cursor: grab !important;',
      '  color: #5e7185 !important;',
      '  font-size: 14px !important;',
      '  user-select: none !important;',
      '  touch-action: none !important;',
      '  border-radius: 6px !important;',
      '  transition: background 140ms ease, color 140ms ease !important;',
      '}',
      '.yk-alex-grip:hover { background: rgba(23, 105, 170, 0.10) !important; color: #1769aa !important; }',
      '.yk-alex-grip.is-dragging { cursor: grabbing !important; background: rgba(23, 105, 170, 0.16) !important; }',
      '.yk-alex-pos-btn {',
      '  display: inline-flex !important;',
      '  align-items: center !important;',
      '  justify-content: center !important;',
      '  width: 28px !important;',
      '  height: 32px !important;',
      '  background: transparent !important;',
      '  border: 0 !important;',
      '  color: #5e7185 !important;',
      '  cursor: pointer !important;',
      '  border-radius: 6px !important;',
      '  font-size: 14px !important;',
      '  transition: background 140ms ease, color 140ms ease !important;',
      '}',
      '.yk-alex-pos-btn:hover { background: rgba(23, 105, 170, 0.10) !important; color: #1769aa !important; }',
      '.yk-alex-pos-menu {',
      '  position: fixed !important;',
      '  z-index: 2147483647 !important;',
      '  background: #ffffff !important;',
      '  border: 1px solid rgba(94, 113, 133, 0.22) !important;',
      '  border-radius: 12px !important;',
      '  padding: 6px !important;',
      '  box-shadow: 0 16px 36px rgba(15, 30, 50, 0.18) !important;',
      '  min-width: 220px !important;',
      '  font-family: "Segoe UI", system-ui, sans-serif !important;',
      '  font-size: 13px !important;',
      '  display: none !important;',
      '}',
      '.yk-alex-pos-menu.is-open { display: block !important; }',
      '.yk-alex-pos-menu button {',
      '  display: flex !important;',
      '  align-items: center !important;',
      '  gap: 10px !important;',
      '  width: 100% !important;',
      '  text-align: left !important;',
      '  background: transparent !important;',
      '  border: 0 !important;',
      '  padding: 8px 12px !important;',
      '  border-radius: 8px !important;',
      '  color: #122236 !important;',
      '  cursor: pointer !important;',
      '  font-size: 13px !important;',
      '}',
      '.yk-alex-pos-menu button:hover { background: rgba(23, 105, 170, 0.10) !important; color: #1769aa !important; }',
      '.yk-alex-pos-menu button.is-active { background: rgba(12, 116, 136, 0.12) !important; color: #0c7488 !important; font-weight: 600 !important; }',
      '.yk-alex-pos-menu .yk-alex-pos-sep { height: 1px !important; background: rgba(94, 113, 133, 0.18) !important; margin: 4px 6px !important; }',
      '.yk-alex-pos-menu .yk-alex-pos-hint { font-size: 11px !important; color: #5e7185 !important; padding: 4px 12px 6px !important; }',
      '.yk-alex-pos-icon { width: 20px !important; display: inline-flex !important; justify-content: center !important; opacity: 0.85 !important; }',
      '@media (max-width: ' + MIN_VIEWPORT_PX + 'px) {',
      '  .yk-alex-grip, .yk-alex-pos-btn { display: none !important; }',
      '}'
    ].join('\n');
    document.head.appendChild(style);
  }

  // --- Storage helpers ---
  function loadPosition() {
    try {
      var raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return null;
      var obj = JSON.parse(raw);
      if (!obj || typeof obj !== 'object') return null;
      return obj;
    } catch (e) { return null; }
  }
  function savePosition(obj) {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(obj)); } catch (e) {}
  }

  // --- Preset positions ---
  var PRESETS = {
    'bottom-center': { label: 'Merkez Alt (varsayilan)', icon: '↓' },
    'top-center':    { label: 'Merkez Ust',              icon: '↑' },
    'bottom-left':   { label: 'Sol Alt',                 icon: '↙' },
    'bottom-right':  { label: 'Sag Alt',                 icon: '↘' },
    'top-left':      { label: 'Sol Ust',                 icon: '↖' },
    'top-right':     { label: 'Sag Ust',                 icon: '↗' },
    'center':        { label: 'Tam Merkez',              icon: '✕' },
    'mini':          { label: 'Mini (sadece FAB)',       icon: '○' },
    'hidden':        { label: 'Tam Gizle (Alt+A acar)',  icon: '∅' }
  };

  function applyPreset(bar, preset) {
    if (!bar) return;
    // Onceki style override'lari temizle
    bar.style.left = '';
    bar.style.right = '';
    bar.style.top = '';
    bar.style.bottom = '';
    bar.style.transform = '';
    bar.style.display = '';

    var fab = document.getElementById('ykVoiceFab');

    if (preset === 'hidden') {
      bar.setAttribute('data-bar', 'hidden');
      bar.classList.remove('open');
      bar.style.display = 'none';
      try { localStorage.setItem('ykVoiceBarModeD200', 'hidden'); } catch (e) {}
      return;
    }
    if (preset === 'mini') {
      // Mini: bar gizle, FAB goster (mevcut FAB davranisi)
      bar.setAttribute('data-bar', 'hidden');
      bar.classList.remove('open');
      bar.style.display = 'none';
      if (fab) fab.style.display = '';
      try { localStorage.setItem('ykVoiceBarModeD200', 'hidden'); } catch (e) {}
      return;
    }
    // Bar gorunur
    bar.setAttribute('data-bar', 'visible');
    bar.style.display = '';
    try { localStorage.setItem('ykVoiceBarModeD200', 'visible'); } catch (e) {}

    var margin = 18;
    switch (preset) {
      case 'bottom-center':
        bar.style.left = '50%';
        bar.style.bottom = margin + 'px';
        bar.style.transform = 'translateX(-50%)';
        break;
      case 'top-center':
        bar.style.left = '50%';
        bar.style.top = margin + 'px';
        bar.style.transform = 'translateX(-50%)';
        break;
      case 'bottom-left':
        bar.style.left = margin + 'px';
        bar.style.bottom = margin + 'px';
        break;
      case 'bottom-right':
        bar.style.right = margin + 'px';
        bar.style.bottom = margin + 'px';
        break;
      case 'top-left':
        bar.style.left = margin + 'px';
        bar.style.top = margin + 'px';
        break;
      case 'top-right':
        bar.style.right = margin + 'px';
        bar.style.top = margin + 'px';
        break;
      case 'center':
        bar.style.left = '50%';
        bar.style.top = '50%';
        bar.style.transform = 'translate(-50%, -50%)';
        break;
    }
  }

  function applyFreePosition(bar, x, y) {
    if (!bar) return;
    bar.style.left = x + 'px';
    bar.style.top = y + 'px';
    bar.style.right = '';
    bar.style.bottom = '';
    bar.style.transform = '';
    bar.style.display = '';
    bar.setAttribute('data-bar', 'visible');
  }

  function clamp(v, min, max) { return Math.max(min, Math.min(max, v)); }

  function maybeSnap(x, y, w, h) {
    var vw = window.innerWidth, vh = window.innerHeight;
    var snap = SNAP_PX * 4;
    var preset = null;
    var nearLeft   = x < snap;
    var nearRight  = (vw - (x + w)) < snap;
    var nearTop    = y < snap;
    var nearBottom = (vh - (y + h)) < snap;
    if (nearTop && nearLeft) preset = 'top-left';
    else if (nearTop && nearRight) preset = 'top-right';
    else if (nearBottom && nearLeft) preset = 'bottom-left';
    else if (nearBottom && nearRight) preset = 'bottom-right';
    else if (nearBottom && Math.abs((vw / 2) - (x + w / 2)) < snap * 2) preset = 'bottom-center';
    else if (nearTop && Math.abs((vw / 2) - (x + w / 2)) < snap * 2) preset = 'top-center';
    return preset;
  }

  // --- Bar hazirlandiginda kur ---
  function setupBar() {
    var bar = document.getElementById(BAR_ID);
    if (!bar || bar.__ykPositionerWired) return false;
    var quickbar = bar.querySelector('.yk-voice-agent-quickbar');
    if (!quickbar) return false;

    bar.__ykPositionerWired = true;

    // 1) Grip kolu (en sola)
    var grip = document.createElement('span');
    grip.className = 'yk-alex-grip';
    grip.setAttribute('title', 'Suruklemek icin tut, cift tikla varsayilan konuma don');
    grip.setAttribute('aria-label', 'Bari surukle');
    grip.innerHTML = '⋮⋮'; // dikey ucnokta x2
    quickbar.insertBefore(grip, quickbar.firstChild);

    // 2) Konum menusu butonu (kapat butonundan once)
    var posBtn = document.createElement('button');
    posBtn.type = 'button';
    posBtn.className = 'yk-alex-pos-btn';
    posBtn.setAttribute('title', 'Konum ayarlari');
    posBtn.setAttribute('aria-label', 'Konum ayarlari');
    posBtn.innerHTML = '☰'; // hamburger
    var closeBtn = document.getElementById('ykVoiceQuickClose');
    if (closeBtn && closeBtn.parentNode) {
      closeBtn.parentNode.insertBefore(posBtn, closeBtn);
    } else {
      quickbar.appendChild(posBtn);
    }

    // 3) Konum menusunu olustur
    var menu = document.createElement('div');
    menu.className = 'yk-alex-pos-menu';
    menu.setAttribute('role', 'menu');
    var hint = document.createElement('div');
    hint.className = 'yk-alex-pos-hint';
    hint.textContent = 'Alex bar konumu';
    menu.appendChild(hint);
    Object.keys(PRESETS).forEach(function(key) {
      if (key === 'hidden' || key === 'mini') return; // ayri grup
      var p = PRESETS[key];
      var b = document.createElement('button');
      b.type = 'button';
      b.dataset.preset = key;
      b.innerHTML = '<span class="yk-alex-pos-icon">' + p.icon + '</span><span>' + p.label + '</span>';
      menu.appendChild(b);
    });
    var sep = document.createElement('div');
    sep.className = 'yk-alex-pos-sep';
    menu.appendChild(sep);
    ['mini', 'hidden'].forEach(function(key) {
      var p = PRESETS[key];
      var b = document.createElement('button');
      b.type = 'button';
      b.dataset.preset = key;
      b.innerHTML = '<span class="yk-alex-pos-icon">' + p.icon + '</span><span>' + p.label + '</span>';
      menu.appendChild(b);
    });
    document.body.appendChild(menu);

    function markActive(currentPreset) {
      menu.querySelectorAll('button[data-preset]').forEach(function(b) {
        b.classList.toggle('is-active', b.dataset.preset === currentPreset);
      });
    }

    function openMenu() {
      var rect = posBtn.getBoundingClientRect();
      var menuRect = { w: 240, h: 380 };
      var x = rect.right - menuRect.w;
      var y = rect.top - menuRect.h - 8;
      if (y < 12) y = rect.bottom + 8;
      x = clamp(x, 12, window.innerWidth - menuRect.w - 12);
      menu.style.left = x + 'px';
      menu.style.top = y + 'px';
      menu.classList.add('is-open');
      var saved = loadPosition() || {};
      markActive(saved.preset || 'bottom-center');
    }
    function closeMenu() {
      menu.classList.remove('is-open');
    }

    posBtn.addEventListener('click', function(e) {
      e.preventDefault();
      e.stopPropagation();
      if (menu.classList.contains('is-open')) closeMenu();
      else openMenu();
    });

    document.addEventListener('click', function(e) {
      if (!menu.classList.contains('is-open')) return;
      if (menu.contains(e.target) || posBtn.contains(e.target)) return;
      closeMenu();
    });

    menu.addEventListener('click', function(e) {
      var btn = e.target.closest('button[data-preset]');
      if (!btn) return;
      var preset = btn.dataset.preset;
      applyPreset(bar, preset);
      savePosition({ preset: preset });
      markActive(preset);
      closeMenu();
    });

    // 4) Surukle mantigi
    var dragState = null;
    grip.addEventListener('pointerdown', function(e) {
      if (window.innerWidth < MIN_VIEWPORT_PX) return;
      e.preventDefault();
      var rect = bar.getBoundingClientRect();
      dragState = {
        offsetX: e.clientX - rect.left,
        offsetY: e.clientY - rect.top,
        width: rect.width,
        height: rect.height,
        pointerId: e.pointerId
      };
      grip.classList.add('is-dragging');
      try { grip.setPointerCapture(e.pointerId); } catch (er) {}
    });

    grip.addEventListener('pointermove', function(e) {
      if (!dragState) return;
      var newX = clamp(e.clientX - dragState.offsetX, 4, window.innerWidth - dragState.width - 4);
      var newY = clamp(e.clientY - dragState.offsetY, 4, window.innerHeight - dragState.height - 4);
      applyFreePosition(bar, newX, newY);
    });

    function endDrag(e) {
      if (!dragState) return;
      try { grip.releasePointerCapture(dragState.pointerId); } catch (er) {}
      grip.classList.remove('is-dragging');
      var rect = bar.getBoundingClientRect();
      var snapPreset = maybeSnap(rect.left, rect.top, dragState.width, dragState.height);
      if (snapPreset) {
        applyPreset(bar, snapPreset);
        savePosition({ preset: snapPreset });
      } else {
        savePosition({ preset: 'free', x: Math.round(rect.left), y: Math.round(rect.top) });
      }
      dragState = null;
    }
    grip.addEventListener('pointerup', endDrag);
    grip.addEventListener('pointercancel', endDrag);
    grip.addEventListener('lostpointercapture', endDrag);

    // 5) Cift tik = varsayilan konuma don
    grip.addEventListener('dblclick', function() {
      applyPreset(bar, 'bottom-center');
      savePosition({ preset: 'bottom-center' });
    });

    // 6) Onceki konumu uygula
    var saved = loadPosition();
    if (saved) {
      if (saved.preset === 'free' && typeof saved.x === 'number') {
        applyFreePosition(bar, saved.x, saved.y);
      } else if (saved.preset && PRESETS[saved.preset]) {
        applyPreset(bar, saved.preset);
      }
    }

    return true;
  }

  // --- Klavye kisayollari (her zaman, bar olmasa bile FAB icin) ---
  document.addEventListener('keydown', function(e) {
    if (!e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return;
    var bar = document.getElementById(BAR_ID);
    if (!bar) return;
    var key = (e.key || '').toLowerCase();
    if (key === 'a') {
      e.preventDefault();
      var hidden = bar.getAttribute('data-bar') === 'hidden';
      if (hidden) {
        var saved = loadPosition();
        var preset = (saved && saved.preset && saved.preset !== 'hidden' && saved.preset !== 'mini')
          ? saved.preset : 'bottom-center';
        applyPreset(bar, preset);
      } else {
        applyPreset(bar, 'hidden');
        savePosition({ preset: 'hidden' });
      }
    } else if (key === 'm') {
      e.preventDefault();
      applyPreset(bar, 'mini');
      savePosition({ preset: 'mini' });
    } else if (key === 'c') {
      e.preventDefault();
      var input = document.getElementById('ykVoiceQuickText') || document.getElementById('ykVoiceText');
      if (input) {
        if (bar.getAttribute('data-bar') === 'hidden') {
          var savedC = loadPosition();
          applyPreset(bar, (savedC && savedC.preset && savedC.preset !== 'hidden' && savedC.preset !== 'mini')
                            ? savedC.preset : 'bottom-center');
        }
        try { input.focus(); } catch (er) {}
      }
    }
  });

  // --- DOM hazirsa kur, degilse poll (bar lazy yuklenebilir) ---
  function ensureSetup() {
    if (setupBar()) return;
    var tries = 0;
    var iv = setInterval(function() {
      tries += 1;
      if (setupBar() || tries > 40) clearInterval(iv); // ~20 sn
    }, 500);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', ensureSetup);
  } else {
    ensureSetup();
  }

  // Public API (test/debug)
  window.ykAlexPositioner = {
    apply: function(preset) {
      var bar = document.getElementById(BAR_ID);
      if (bar && PRESETS[preset]) {
        applyPreset(bar, preset);
        savePosition({ preset: preset });
      }
    },
    presets: PRESETS,
    load: loadPosition,
    save: savePosition,
    version: '2026.05.16-alex-positioner'
  };
})();
