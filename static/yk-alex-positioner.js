/* YazKlinik D700 - Alex Bar Positioner (2026-05-16)
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
  var MOBILE_COMPACT_KEY = 'ykAlexMobileCompact';
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
      '.yk-alex-pos-btn.yk-alex-compact-btn { display: none !important; width: 44px !important; font-size: 12px !important; font-weight: 600 !important; }',
      '.yk-voice-agent.yk-alex-mobile-top-right .yk-alex-pos-btn.yk-alex-compact-btn { display: inline-flex !important; }',
      '.yk-voice-agent.yk-alex-mobile-top-right {',
      '  position: fixed !important;',
      '  top: calc(var(--header-h, 76px) + env(safe-area-inset-top, 0px) + 8px) !important;',
      '  right: max(8px, env(safe-area-inset-right, 0px)) !important;',
      '  left: auto !important;',
      '  bottom: auto !important;',
      '  transform: none !important;',
      '  z-index: 1905 !important;',
      '  width: min(96vw, 700px) !important;',
      '  max-width: min(96vw, 700px) !important;',
      '}',
      '.yk-voice-agent.yk-alex-mobile-top-right.yk-alex-mobile-compact {',
      '  width: min(88vw, 360px) !important;',
      '  max-width: min(88vw, 360px) !important;',
      '}',
      '.yk-voice-agent.yk-alex-mobile-top-right.yk-alex-mobile-compact #ykVoiceQuickText,',
      '.yk-voice-agent.yk-alex-mobile-top-right.yk-alex-mobile-compact #ykVoiceQuickSend,',
      '.yk-voice-agent.yk-alex-mobile-top-right.yk-alex-mobile-compact #ykVoiceQuickExpand {',
      '  display: none !important;',
      '}',
      '.yk-voice-agent.yk-alex-mobile-top-right.yk-alex-mobile-compact .yk-voice-agent-quickbar {',
      '  gap: 4px !important;',
      '  padding: 6px !important;',
      '}',
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
      '  .yk-alex-grip { display: none !important; }',
      '  .yk-alex-pos-btn { display: inline-flex !important; width: 30px !important; height: 30px !important; }',
      '  .yk-alex-pos-btn.yk-alex-compact-btn { width: 42px !important; }',
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
  function savePosition(obj, userPlaced) {
    try {
      var next = obj && typeof obj === 'object' ? obj : {};
      next.userPlaced = userPlaced !== false;
      next.version = '2026.05.25-mobile-safari-top-right';
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    } catch (e) {}
  }
  function loadMobileCompact() {
    try {
      var raw = localStorage.getItem(MOBILE_COMPACT_KEY);
      if (raw === null || raw === undefined || raw === '') return true;
      return String(raw) !== '0';
    } catch (e) {
      return true;
    }
  }
  function saveMobileCompact(compact) {
    try {
      localStorage.setItem(MOBILE_COMPACT_KEY, compact ? '1' : '0');
    } catch (e) {}
  }
  function isMobileViewport() {
    return !!(window.matchMedia && window.matchMedia('(max-width: 900px)').matches);
  }
  function isIOSLike() {
    var ua = (navigator.userAgent || '').toLowerCase();
    var platform = navigator.platform || '';
    return /iphone|ipad|ipod/.test(ua)
      || (platform === 'MacIntel' && navigator.maxTouchPoints > 1)
      || document.documentElement.classList.contains('yk-ios');
  }
  function isSafariLike() {
    var ua = (navigator.userAgent || '').toLowerCase();
    var looksSafari = /safari/.test(ua) && !/chrome|chromium|crios|fxios|android|edg\//.test(ua);
    return looksSafari || document.documentElement.classList.contains('yk-safari');
  }
  function isMobileSafariContext() {
    if (!isMobileViewport()) return false;
    if (isIOSLike()) return true;
    return !!(isSafariLike() && (navigator.maxTouchPoints || 0) > 0);
  }
  function forceStyle(el, name, value) {
    try { el.style.setProperty(name, value, 'important'); } catch (e) {}
  }
  function clearStyle(el, name) {
    try { el.style.removeProperty(name); } catch (e) {}
  }
  function applyMobileTopRightStyle(bar) {
    if (!bar) return;
    if (!isMobileSafariContext()) {
      bar.classList.remove('yk-alex-mobile-top-right');
      return;
    }
    bar.classList.add('yk-alex-mobile-top-right');
    forceStyle(bar, 'left', 'auto');
    forceStyle(bar, 'right', 'max(8px, env(safe-area-inset-right, 0px))');
    forceStyle(bar, 'top', 'calc(var(--header-h, 76px) + env(safe-area-inset-top, 0px) + 8px)');
    forceStyle(bar, 'bottom', 'auto');
    forceStyle(bar, 'transform', 'none');
    forceStyle(bar, 'z-index', '1905');
  }
  function applyCompactState(bar, compact, persist) {
    if (!bar) return;
    if (!isMobileSafariContext()) {
      bar.classList.remove('yk-alex-mobile-compact');
      return;
    }
    var nextCompact = compact !== false;
    bar.classList.toggle('yk-alex-mobile-compact', nextCompact);
    var compactBtn = document.getElementById('ykVoiceQuickCompact');
    if (compactBtn) {
      compactBtn.textContent = nextCompact ? 'Tam' : 'Mini';
      compactBtn.setAttribute(
        'title',
        nextCompact ? 'Tam boyuta getir' : 'Kucuk moda gec'
      );
      compactBtn.setAttribute(
        'aria-label',
        nextCompact ? 'Tam boyuta getir' : 'Kucuk moda gec'
      );
    }
    if (persist !== false) saveMobileCompact(nextCompact);
  }
  function forgetLegacyPosition(obj) {
    try {
      if (!obj || obj.userPlaced === true) return;
      localStorage.removeItem(STORAGE_KEY);
    } catch (e) {}
  }
  function setDefaultCenterStyle(bar) {
    if (!bar) return;
    if (isMobileSafariContext()) {
      applyPreset(bar, 'top-right');
      return;
    }
    clearStyle(bar, 'left');
    clearStyle(bar, 'right');
    clearStyle(bar, 'top');
    clearStyle(bar, 'bottom');
    clearStyle(bar, 'transform');
    bar.style.left = '50%';
    bar.style.right = 'auto';
    bar.style.top = '';
    bar.style.bottom = '18px';
    bar.style.transform = 'translateX(-50%)';
  }

  function normalizeSavedPosition(saved) {
    if (!saved || typeof saved !== 'object') return saved;
    var preset = String(saved.preset || '').trim().toLowerCase();
    var mobileSafari = isMobileSafariContext();
    // Mobil Safari'de bar ust-sag kalmali.
    if (mobileSafari && preset !== 'hidden' && preset !== 'mini') {
      return {
        preset: 'top-right',
        userPlaced: true,
        version: '2026.05.25-mobile-safari-top-right',
        migratedFromPreset: preset
      };
    }
    // Klinik default: Alex bar alt-merkez. Eski center/free kayitlarini
    // zorla alta tasiyoruz ki bar sayfa ortasinda kalmasin.
    if (preset === 'center' || preset === 'free') {
      return {
        preset: 'bottom-center',
        userPlaced: true,
        version: '2026.05.25-bottom-center-enforced',
        migratedFromPreset: preset
      };
    }
    return saved;
  }

  // --- Preset positions ---
  var PRESETS = {
    'bottom-center': { label: 'Merkez Alt (varsayilan)', icon: 'â†“' },
    'top-center':    { label: 'Merkez Ust',              icon: 'â†‘' },
    'bottom-left':   { label: 'Sol Alt',                 icon: 'â†™' },
    'bottom-right':  { label: 'Sag Alt',                 icon: 'â†˜' },
    'top-left':      { label: 'Sol Ust',                 icon: 'â†–' },
    'top-right':     { label: 'Sag Ust',                 icon: 'â†—' },
    'center':        { label: 'Tam Merkez',              icon: 'âœ•' },
    'mini':          { label: 'Mini (sadece FAB)',       icon: 'â—‹' },
    'hidden':        { label: 'Tam Gizle (Alt+A acar)',  icon: 'âˆ…' }
  };

  function applyPreset(bar, preset) {
    if (!bar) return;
    var mobileSafari = isMobileSafariContext();
    if (mobileSafari && preset !== 'hidden' && preset !== 'mini') {
      preset = 'top-right';
    }
    // Onceki style override'lari temizle
    clearStyle(bar, 'left');
    clearStyle(bar, 'right');
    clearStyle(bar, 'top');
    clearStyle(bar, 'bottom');
    clearStyle(bar, 'transform');
    clearStyle(bar, 'z-index');
    clearStyle(bar, 'width');
    clearStyle(bar, 'max-width');
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

    var edge = 18;
    var topEdge = mobileSafari ? 84 : ((window.matchMedia && window.matchMedia('(max-width: 768px)').matches) ? 74 : edge);
    switch (preset) {
      case 'bottom-center':
        bar.style.left = '50%';
        bar.style.bottom = edge + 'px';
        bar.style.transform = 'translateX(-50%)';
        break;
      case 'top-center':
        bar.style.left = '50%';
        bar.style.top = topEdge + 'px';
        bar.style.transform = 'translateX(-50%)';
        break;
      case 'bottom-left':
        bar.style.left = edge + 'px';
        bar.style.bottom = edge + 'px';
        break;
      case 'bottom-right':
        bar.style.right = edge + 'px';
        bar.style.bottom = edge + 'px';
        break;
      case 'top-left':
        bar.style.left = edge + 'px';
        bar.style.top = topEdge + 'px';
        break;
      case 'top-right':
        bar.style.right = edge + 'px';
        bar.style.top = topEdge + 'px';
        break;
      case 'center':
        bar.style.left = '50%';
        bar.style.top = '50%';
        bar.style.transform = 'translate(-50%, -50%)';
        break;
    }
    if (mobileSafari) {
      applyMobileTopRightStyle(bar);
      applyCompactState(bar, loadMobileCompact(), false);
    } else {
      bar.classList.remove('yk-alex-mobile-top-right');
      bar.classList.remove('yk-alex-mobile-compact');
    }
  }

  function applyFreePosition(bar, x, y) {
    if (!bar) return;
    if (isMobileSafariContext()) {
      applyPreset(bar, 'top-right');
      return;
    }
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
    grip.innerHTML = 'â‹®â‹®'; // dikey ucnokta x2
    quickbar.insertBefore(grip, quickbar.firstChild);

    // 2) Konum menusu butonu (kapat butonundan once)
    var posBtn = document.createElement('button');
    posBtn.type = 'button';
    posBtn.className = 'yk-alex-pos-btn';
    posBtn.setAttribute('title', 'Konum ayarlari');
    posBtn.setAttribute('aria-label', 'Konum ayarlari');
    posBtn.innerHTML = 'â˜°'; // hamburger
    var closeBtn = document.getElementById('ykVoiceQuickClose');
    if (closeBtn && closeBtn.parentNode) {
      closeBtn.parentNode.insertBefore(posBtn, closeBtn);
    } else {
      quickbar.appendChild(posBtn);
    }
    var compactBtn = document.createElement('button');
    compactBtn.type = 'button';
    compactBtn.id = 'ykVoiceQuickCompact';
    compactBtn.className = 'yk-alex-pos-btn yk-alex-compact-btn';
    compactBtn.setAttribute('title', 'Kucuk moda gec');
    compactBtn.setAttribute('aria-label', 'Kucuk moda gec');
    compactBtn.textContent = 'Mini';
    if (closeBtn && closeBtn.parentNode) {
      closeBtn.parentNode.insertBefore(compactBtn, closeBtn);
    } else {
      quickbar.appendChild(compactBtn);
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
      markActive(saved.preset || (isMobileSafariContext() ? 'top-right' : 'bottom-center'));
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
      var savePreset = (isMobileSafariContext() && preset !== 'hidden' && preset !== 'mini')
        ? 'top-right'
        : preset;
      var savePayload = { preset: savePreset };
      if (savePreset === 'center') savePayload.allowCenterManual = true;
      savePosition(savePayload, true);
      markActive(savePreset);
      closeMenu();
    });
    compactBtn.addEventListener('click', function(e) {
      e.preventDefault();
      e.stopPropagation();
      applyCompactState(bar, !bar.classList.contains('yk-alex-mobile-compact'), true);
      if (!bar.classList.contains('yk-alex-mobile-top-right')) {
        applyPreset(bar, 'top-right');
        savePosition({ preset: 'top-right' }, true);
      }
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
        savePosition({ preset: snapPreset }, true);
      } else {
        savePosition({ preset: 'free', x: Math.round(rect.left), y: Math.round(rect.top) }, true);
      }
      dragState = null;
    }
    grip.addEventListener('pointerup', endDrag);
    grip.addEventListener('pointercancel', endDrag);
    grip.addEventListener('lostpointercapture', endDrag);

    // 5) Cift tik = varsayilan konuma don
    grip.addEventListener('dblclick', function() {
      var fallback = isMobileSafariContext() ? 'top-right' : 'bottom-center';
      applyPreset(bar, fallback);
      savePosition({ preset: fallback }, true);
    });

    // 6) Onceki konumu uygula
    var saved = loadPosition();
    saved = normalizeSavedPosition(saved);
    if (saved && saved.migratedFromPreset) {
      savePosition(saved, true);
    }
    if (saved && saved.userPlaced === true) {
      if (saved.preset === 'free' && typeof saved.x === 'number') {
        applyFreePosition(bar, saved.x, saved.y);
      } else if (saved.preset && PRESETS[saved.preset]) {
        applyPreset(bar, saved.preset);
      }
    } else {
      forgetLegacyPosition(saved);
      setDefaultCenterStyle(bar);
    }
    applyCompactState(bar, loadMobileCompact(), false);
    applyMobileTopRightStyle(bar);

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
        var saved = normalizeSavedPosition(loadPosition());
        var preset = (saved && saved.preset && saved.preset !== 'hidden' && saved.preset !== 'mini')
          ? saved.preset : (isMobileSafariContext() ? 'top-right' : 'bottom-center');
        applyPreset(bar, preset);
      } else {
        applyPreset(bar, 'hidden');
        savePosition({ preset: 'hidden' }, true);
      }
    } else if (key === 'm') {
      e.preventDefault();
      applyPreset(bar, 'mini');
      savePosition({ preset: 'mini' }, true);
    } else if (key === 'c') {
      e.preventDefault();
      var input = document.getElementById('ykVoiceQuickText') || document.getElementById('ykVoiceText');
      if (input) {
        if (bar.getAttribute('data-bar') === 'hidden') {
          var savedC = normalizeSavedPosition(loadPosition());
          applyPreset(bar, (savedC && savedC.preset && savedC.preset !== 'hidden' && savedC.preset !== 'mini')
                            ? savedC.preset : (isMobileSafariContext() ? 'top-right' : 'bottom-center'));
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

  function refreshMobilePlacement() {
    var bar = document.getElementById(BAR_ID);
    if (!bar) return;
    if (bar.getAttribute('data-bar') === 'hidden' || bar.style.display === 'none') return;
    if (isMobileSafariContext()) {
      applyMobileTopRightStyle(bar);
      applyCompactState(bar, loadMobileCompact(), false);
    } else {
      bar.classList.remove('yk-alex-mobile-top-right');
      bar.classList.remove('yk-alex-mobile-compact');
    }
  }

  window.addEventListener('resize', function() {
    window.setTimeout(refreshMobilePlacement, 60);
  }, { passive: true });
  window.addEventListener('orientationchange', function() {
    window.setTimeout(refreshMobilePlacement, 180);
  }, { passive: true });
  window.addEventListener('yk:safari-bfcache-restore', function() {
    window.setTimeout(refreshMobilePlacement, 40);
  });

  // Runtime rescue: if inline Alex handlers break, these keep send flow alive.
  function bindAlexRuntimeRescue() {
    if (window.__ykAlexRuntimeRescueBound) return;
    window.__ykAlexRuntimeRescueBound = true;

    function setStatus(text) {
      try {
        var st = document.getElementById('ykVoiceStatus');
        if (st) st.textContent = String(text || '');
      } catch (e) {}
    }

    function flashBanner(text, kind) {
      try {
        var b = document.getElementById('ykVoiceBanner');
        if (!b) return;
        var clean = String(text || '').replace(/\s+/g, ' ').trim();
        if (!clean) return;
        var prefix = kind === 'user' ? 'Siz: ' : (kind === 'system' ? '' : 'Alex: ');
        b.textContent = (prefix + clean).slice(0, 520);
        b.classList.add('show');
        window.setTimeout(function() {
          try { b.classList.remove('show'); } catch (e2) {}
        }, kind === 'system' ? 3600 : 9000);
      } catch (e) {}
    }

    function getText(id) {
      try {
        var el = document.getElementById(id);
        return el ? String(el.value || '').trim() : '';
      } catch (e) {
        return '';
      }
    }

    function clearText(id) {
      try {
        var el = document.getElementById(id);
        if (el) el.value = '';
      } catch (e) {}
    }

    function ensureBarVisible(preferVoice) {
      try {
        var bar = document.getElementById('ykVoiceAgent');
        if (!bar) return;
        if (bar.getAttribute('data-bar') === 'hidden' || bar.style.display === 'none') {
          var saved = normalizeSavedPosition(loadPosition());
          var preset = (saved && saved.preset && saved.preset !== 'hidden' && saved.preset !== 'mini')
            ? saved.preset
            : (isMobileSafariContext() ? 'top-right' : 'bottom-center');
          applyPreset(bar, preset);
        }
        if (preferVoice) {
          bar.setAttribute('data-voice-mode', 'voice');
          try { localStorage.setItem('ykVoiceBarModeD200', 'voice'); } catch (_e) {}
        } else {
          try {
            if (!bar.getAttribute('data-voice-mode')) bar.setAttribute('data-voice-mode', 'silent');
          } catch (_e2) {}
        }
      } catch (_e3) {}
    }

    function runtimeVoiceAction(action, ev) {
      var safeAction = String(action || '').toLowerCase();
      var delegated = false;

      try {
        if (window.ykVoiceQuickAction && typeof window.ykVoiceQuickAction === 'function') {
          window.ykVoiceQuickAction(safeAction, ev);
          delegated = true;
        }
      } catch (_eQ) {}
      if (!delegated) {
        try {
          if (window.ykVoicePanelAction && typeof window.ykVoicePanelAction === 'function') {
            window.ykVoicePanelAction(
              safeAction === 'mic' ? 'quick-mic' : safeAction,
              ev
            );
            delegated = true;
          }
        } catch (_eP) {}
      }
      if (delegated) return true;

      var agent = window.ykVoiceAgent || {};
      if (safeAction === 'mic') {
        ensureBarVisible(true);
        setStatus('Sesli sohbet baslatiliyor...');
        try { localStorage.setItem('ykVoiceAlexAlwaysOnD200', 'active'); } catch (_eL) {}
        if (typeof agent.listenOnce === 'function') {
          try { agent.listenOnce(); return true; } catch (_eAA) {}
        }
        if (typeof agent.listen === 'function') {
          try { agent.listen(); return true; } catch (_eA) {}
        }
        if (typeof agent.alexOn === 'function') {
          try { agent.alexOn(); return true; } catch (_eB) {}
        }
        if (typeof agent.open === 'function') {
          try { agent.open(); } catch (_eC) {}
        }
        return true;
      }
      if (safeAction === 'alex') {
        ensureBarVisible(false);
        try {
          if (typeof agent.open === 'function') agent.open();
          else if (typeof agent.showSilent === 'function') agent.showSilent();
        } catch (_eD) {}
        try {
          var input = document.getElementById('ykVoiceQuickText') || document.getElementById('ykVoiceText');
          if (input) input.focus();
        } catch (_eE) {}
        setStatus('Alex hazir. Komut yazabilir veya sesli moda gecebilirsiniz.');
        return true;
      }
      if (safeAction === 'stop') {
        try {
          if (typeof agent.stop === 'function') {
            agent.stop();
            setStatus('Alex durduruldu. Yazili mod hazir.');
            return true;
          }
        } catch (_eF) {}
        try {
          if (typeof agent.alexOff === 'function') {
            agent.alexOff();
            setStatus('Alex beklemeye alindi.');
            return true;
          }
        } catch (_eG) {}
        setStatus('Durdur komutu uygulandi.');
        return true;
      }
      return false;
    }

    function sendAlex(rawMessage, sourceTag, forceSpeak) {
      var msg = String(rawMessage || '').trim();
      if (!msg) {
        setStatus('Once komut veya soru yazin.');
        flashBanner('Once komut veya soru yazin.', 'system');
        return Promise.resolve({ ok: false, error: 'empty_message' });
      }
      function speakNativeFallback(text) {
        try {
          if (!('speechSynthesis' in window)) return;
          var utter = new SpeechSynthesisUtterance(String(text || '').slice(0, 900));
          utter.lang = 'tr-TR';
          utter.rate = 0.95;
          try { window.speechSynthesis.cancel(); } catch (_e1) {}
          window.speechSynthesis.speak(utter);
        } catch (_e2) {}
      }
      var doSpeak = !!forceSpeak;
      try {
        if (!doSpeak) {
          var bar = document.getElementById('ykVoiceAgent');
          var mode = bar ? String(bar.getAttribute('data-voice-mode') || '').toLowerCase() : '';
          doSpeak = mode === 'voice';
        }
      } catch (eMode) {}
      setStatus('Alex cevabi hazirlaniyor...');
      flashBanner(msg, 'user');
      function parseResponse(resp) {
        return resp.json().catch(function() { return {}; }).then(function(data) {
          data = data || {};
          data._http_ok = !!resp.ok;
          data._http_status = resp.status || 0;
          return data;
        });
      }
      function detectPatientKeyFromPath() {
        try {
          var path = String(window.location.pathname || '');
          var m = path.match(/^\/hasta\/([^\/?#]+)/i);
          if (!m || !m[1]) return '';
          return decodeURIComponent(m[1]).trim();
        } catch (_e) {
          return '';
        }
      }
      var currentPath = String(window.location.pathname || '') + String(window.location.search || '');
      var payload = {
        message: msg,
        text: msg,
        command: msg,
        speak: doSpeak ? 1 : 0,
        current_path: currentPath,
        page_title: document.title || '',
        patient_key: detectPatientKeyFromPath(),
        voice: doSpeak ? 1 : 0,
        alex_mode: doSpeak ? 1 : 0,
        client_context: {
          current_path: currentPath,
          page_title: document.title || '',
          voice: !!doSpeak,
          alex_mode: !!doSpeak
        },
        source: sourceTag || 'runtime-rescue'
      };
      function postJson(url) {
        return fetch(url, {
          method: 'POST',
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        }).then(parseResponse);
      }
      function postForm(url) {
        return fetch(url, {
          method: 'POST',
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8' },
          body:
            'message=' + encodeURIComponent(msg) +
            '&text=' + encodeURIComponent(msg) +
            '&command=' + encodeURIComponent(msg) +
            '&speak=' + (doSpeak ? '1' : '0') +
            '&source=' + encodeURIComponent(sourceTag || 'runtime-rescue-form')
        }).then(parseResponse);
      }
      function hasReply(data) {
        return !!(data && (data.answer || data.result || data.message || data.error));
      }
      function foldActionText(value) {
        return String(value || '')
          .toLocaleLowerCase('tr-TR')
          .normalize('NFD')
          .replace(/[\u0300-\u036f]/g, '')
          .replace(/[\u0131\u0130]/g, 'i')
          .replace(/[\u015f\u015e]/g, 's')
          .replace(/[\u011f\u011e]/g, 'g')
          .replace(/[\u00fc\u00dc]/g, 'u')
          .replace(/[\u00f6\u00d6]/g, 'o')
          .replace(/[\u00e7\u00c7]/g, 'c')
          .replace(/[^a-z0-9]+/g, ' ')
          .trim();
      }
      function wantsImmediateAction(text) {
        var t = ' ' + foldActionText(text) + ' ';
        if (/\s(ac|open|goster|git|getir|baslat|calistir|uygula|yap|kontrol|hazirla|olustur|yazdir|ekle)\s/.test(t)) {
          return true;
        }
        var phrases = [
          'acar misin', 'acabilir misin', 'acmani istiyorum',
          'gosterir misin', 'gosterebilir misin',
          'getirir misin', 'getirebilir misin',
          'baslatir misin', 'baslatabilir misin',
          'calistirir misin', 'calistirabilir misin',
          'yapar misin', 'yapabilir misin', 'yapmani istiyorum'
        ];
        return phrases.some(function(p) { return t.indexOf(' ' + p + ' ') >= 0; });
      }
      function isSafeRoute(route) {
        var r = String(route || '').trim();
        if (!r || r[0] !== '/' || r.indexOf('//') === 0) return false;
        if (/[\r\n\t]/.test(r) || r.indexOf('..') >= 0) return false;
        try {
          var u = new URL(r, window.location.origin);
          return u.origin === window.location.origin;
        } catch (_e) {
          return false;
        }
      }
      function parseActionFromAnswer(answerText) {
        var text = String(answerText || '');
        var m = text.match(/ACTION:\s*(\{[\s\S]*?\})/i);
        if (!m) return null;
        try {
          return JSON.parse(m[1]);
        } catch (_e) {
          return null;
        }
      }
      function pickAction(data, answerText) {
        if (data && data.action && typeof data.action === 'object') return data.action;
        if (data && data.action_result && data.action_result.action &&
            typeof data.action_result.action === 'object') {
          return data.action_result.action;
        }
        return parseActionFromAnswer(answerText);
      }
      function runWindowsAction(action) {
        var cmd = String((action || {}).command || '').trim().toLowerCase();
        if (!cmd || ['open_app', 'open_folder', 'open_url', 'list_apps'].indexOf(cmd) < 0) {
          return Promise.resolve({ ok: false, error: 'desteklenmeyen_komut' });
        }
        return fetch('/api/akilli-dialog/win-exec', {
          method: 'POST',
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(Object.assign({ confirmed: true }, action))
        }).then(parseResponse);
      }
      function applyAction(data, action, originalMessage) {
        if (!action || typeof action !== 'object') return Promise.resolve(false);
        if (data && data.needs_confirm) {
          setStatus('Bu islem icin onay gerekiyor. "evet uygula" yazabilirsiniz.');
          return Promise.resolve(false);
        }
        var route = String(action.route || '').trim();
        var cmd = String(action.command || '').trim().toLowerCase();
        var autoRun = !!action.auto_open || wantsImmediateAction(originalMessage);
        if (route && isSafeRoute(route)) {
          if (autoRun) {
            setStatus('Sayfa aciliyor: ' + route);
            window.setTimeout(function() { window.location.assign(route); }, 180);
            return Promise.resolve(true);
          }
          setStatus('Hazir rota: ' + route + ' (ac demeniz yeterli).');
          return Promise.resolve(true);
        }
        if (cmd) {
          if (!autoRun) {
            var target = action.app || action.path || action.url || cmd;
            setStatus('Windows komutu hazir: ' + target + ' (ac demeniz yeterli).');
            return Promise.resolve(true);
          }
          setStatus('Windows komutu calistiriliyor...');
          return runWindowsAction(action).then(function(execData) {
            if (execData && execData.ok) {
              setStatus(execData.message || 'Windows komutu calisti.');
              return true;
            }
            setStatus((execData && (execData.error || execData.message)) || 'Windows komutu calisamadi.');
            return false;
          }).catch(function(err) {
            setStatus('Windows komutu hatasi: ' + (err && err.message ? err.message : err));
            return false;
          });
        }
        return Promise.resolve(false);
      }
      function sendViaNativeAgent() {
        var agent = window.ykVoiceAgent || {};
        if (!agent || typeof agent.send !== 'function') return Promise.resolve(null);
        return Promise.resolve(agent.send(msg, {
          voice: !!doSpeak,
          silent: !doSpeak,
          openPanel: true
        })).then(function(data) {
          if (data && (data.ok || hasReply(data))) return data;
          return null;
        }).catch(function() {
          return null;
        });
      }
      function sendViaHttpChain() {
        return postJson('/api/akilli-dialog/soyle')
          .then(function(data) {
            var errText = String((data && data.error) || '').toLowerCase();
            if (data && data.ok === false && errText.indexOf('message gerekli') >= 0) {
              return postForm('/api/akilli-dialog/soyle');
            }
            if (!hasReply(data) || (data && data.ok === false && (data.status === 'unmatched' || data.status === 'empty_reply'))) {
              return postJson('/api/komut-merkezi/soyle').catch(function() { return data; });
            }
            return data;
          })
          .catch(function() {
            return postJson('/api/komut-merkezi/soyle');
          });
      }
      return sendViaNativeAgent()
        .then(function(nativeData) {
          if (nativeData) return nativeData;
          return sendViaHttpChain();
        })
        .then(function(data) {
          var reply = data && (data.answer || data.result || data.message || data.error);
          if (!reply) {
            reply = (data && data.ok) ? 'Tamam.' : 'Alex yanit veremedi.';
          }
          var action = pickAction(data, reply);
          setStatus(reply);
          flashBanner(reply, data.ok === false ? 'system' : 'assistant');
          if (doSpeak && data.ok !== false && window.ykSpeak) {
            try {
              localStorage.setItem('ykSpeechSilent', '0');
              Promise.resolve(window.ykSpeak(reply, {
                force: true,
                requireGesture: false
              })).then(function(r) {
                if (!r || r.ok === false) speakNativeFallback(reply);
              }).catch(function() {
                speakNativeFallback(reply);
              });
            } catch (eSpeak) {}
          } else if (doSpeak && data.ok !== false) {
            speakNativeFallback(reply);
          }
          return applyAction(data, action, msg).then(function() {
            return data;
          });
        })
        .catch(function(err) {
          var msgErr = 'Baglanti hatasi: ' + (err && err.message ? err.message : err);
          setStatus(msgErr);
          flashBanner(msgErr, 'system');
          return { ok: false, error: String(err && err.message ? err.message : err) };
        });
    }

    document.addEventListener('click', function(ev) {
      try {
        var t = ev.target;
        if (!t || !t.closest) return;

        var voiceBtn = t.closest('#ykVoiceQuickMic, #ykVoiceMic, #ykVoiceQuickAlex, #ykVoiceAlex, #ykVoiceQuickStop, #ykVoiceStop');
        if (voiceBtn) {
          var map = {
            ykVoiceQuickMic: 'mic',
            ykVoiceMic: 'mic',
            ykVoiceQuickAlex: 'alex',
            ykVoiceAlex: 'alex',
            ykVoiceQuickStop: 'stop',
            ykVoiceStop: 'stop'
          };
          var act = map[voiceBtn.id];
          if (act && runtimeVoiceAction(act, ev)) {
            ev.preventDefault();
            ev.stopPropagation();
            if (ev.stopImmediatePropagation) ev.stopImmediatePropagation();
            return;
          }
        }

        var btn = t.closest('#ykVoiceQuickSend, #ykVoiceSend');
        if (!btn) return;
        ev.preventDefault();
        ev.stopPropagation();
        if (ev.stopImmediatePropagation) ev.stopImmediatePropagation();

        if (btn.id === 'ykVoiceQuickSend') {
          var quickText = getText('ykVoiceQuickText');
          clearText('ykVoiceQuickText');
          sendAlex(quickText, 'quickbar-runtime-rescue');
          return;
        }
        if (btn.id === 'ykVoiceSend') {
          sendAlex(getText('ykVoiceText'), 'panel-runtime-rescue');
        }
      } catch (e) {}
    }, true);

    function foldText(v) {
      return String(v || '')
        .toLowerCase()
        .replace(/[\u0131\u00ee]/g, 'i')
        .replace(/[\u015f]/g, 's')
        .replace(/[\u00e7]/g, 'c')
        .replace(/[\u011f]/g, 'g')
        .replace(/[\u00fc]/g, 'u')
        .replace(/[\u00f6]/g, 'o')
        .replace(/\s+/g, ' ')
        .trim();
    }

    function resolveVoiceActionFromButton(btn) {
      if (!btn) return '';
      var id = String(btn.id || '').toLowerCase();
      if (id.indexOf('quicksend') >= 0 || id === 'ykvoicesend') return 'send';
      if (id.indexOf('quickmic') >= 0 || id === 'ykvoicemic') return 'mic';
      if (id.indexOf('quickstop') >= 0 || id === 'ykvoicestop') return 'stop';
      if (id.indexOf('quickalex') >= 0 || id === 'ykvoicealex') return 'alex';
      var txt = foldText(btn.textContent || '');
      if (!txt) return '';
      if (txt.indexOf('gonder') >= 0) return 'send';
      if (txt.indexOf('sesli sohbet') >= 0 || txt === 'sesli mod' || txt.indexOf('mikrofon') >= 0) return 'mic';
      if (txt.indexOf('durdur') >= 0 || txt.indexOf('stop') >= 0) return 'stop';
      if (txt === 'alex' || txt.indexOf("alex'le") >= 0 || txt.indexOf('alex ile') >= 0) return 'alex';
      return '';
    }

    document.addEventListener('click', function(ev) {
      try {
        var t = ev.target;
        if (!t || !t.closest) return;
        var bar = t.closest('#ykVoiceAgent');
        if (!bar) return;
        var btn = t.closest('button');
        if (!btn) return;
        var action = resolveVoiceActionFromButton(btn);
        if (!action) return;

        ev.preventDefault();
        ev.stopPropagation();
        if (ev.stopImmediatePropagation) ev.stopImmediatePropagation();

        if (action === 'send') {
          var text = getText('ykVoiceQuickText') || getText('ykVoiceText');
          clearText('ykVoiceQuickText');
          sendAlex(text, 'button-text-runtime-rescue');
          return;
        }
        runtimeVoiceAction(action, ev);
      } catch (_e) {}
    }, true);

    document.addEventListener('keydown', function(ev) {
      try {
        if (ev.key !== 'Enter' || ev.shiftKey) return;
        var t = ev.target;
        if (!t || !t.id) return;
        if (t.id !== 'ykVoiceQuickText' && t.id !== 'ykVoiceText') return;
        ev.preventDefault();
        ev.stopPropagation();
        if (ev.stopImmediatePropagation) ev.stopImmediatePropagation();

        if (t.id === 'ykVoiceQuickText') {
          var q = getText('ykVoiceQuickText');
          clearText('ykVoiceQuickText');
          sendAlex(q, 'quickbar-enter-runtime-rescue');
        } else {
          sendAlex(getText('ykVoiceText'), 'panel-enter-runtime-rescue');
        }
      } catch (e) {}
    }, true);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bindAlexRuntimeRescue);
  } else {
    bindAlexRuntimeRescue();
  }

  // Public API (test/debug)
  window.ykAlexPositioner = {
    apply: function(preset) {
      var bar = document.getElementById(BAR_ID);
      if (bar && PRESETS[preset]) {
        applyPreset(bar, preset);
        var savePayload = { preset: preset };
        if (preset === 'center') savePayload.allowCenterManual = true;
        savePosition(savePayload, true);
      }
    },
    presets: PRESETS,
    load: loadPosition,
    save: savePosition,
    version: '2026.05.25-mobile-safari-top-right'
  };
})();

