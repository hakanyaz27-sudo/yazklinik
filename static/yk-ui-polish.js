/* ============================================================
   YazKlinik UI Polish JS - D700 v17 2026-05-17
   Helper'lar: ykToast, ykConfirm, ykPrompt, ykTooltips
   Tum window'a expose edilir - mevcut JS'le birlikte calisir.
   ============================================================ */

(function() {
  'use strict';

  // ==========================================================
  // ykToast - Toastify wrapper
  // ==========================================================
  window.ykToast = {
    _show: function(text, type, duration) {
      if (typeof Toastify === 'undefined') {
        // Fallback - native alert
        console.log('[ykToast]', type, text);
        return;
      }
      Toastify({
        text: text,
        duration: duration || 3500,
        gravity: 'bottom',
        position: 'right',
        close: true,
        stopOnFocus: true,
        className: 'toastify-' + type,
        offset: { x: 14, y: 14 }
      }).showToast();
    },
    success: function(text, duration) { this._show(text, 'success', duration); },
    error: function(text, duration) { this._show(text, 'error', duration || 6000); },
    warning: function(text, duration) { this._show(text, 'warning', duration); },
    info: function(text, duration) { this._show(text, 'info', duration); }
  };

  // ==========================================================
  // ykConfirm - SweetAlert2 wrapper (Promise based)
  // Kullanim: const ok = await ykConfirm('Silinsin?'); if (ok) {...}
  // ==========================================================
  window.ykConfirm = function(message, opts) {
    opts = opts || {};
    if (typeof Swal === 'undefined') {
      return Promise.resolve(window.confirm(message));
    }
    return Swal.fire({
      title: opts.title || 'Onay',
      text: message,
      icon: opts.icon || 'question',
      showCancelButton: true,
      confirmButtonText: opts.confirmText || 'Evet',
      cancelButtonText: opts.cancelText || 'Iptal',
      reverseButtons: true,
      focusCancel: opts.dangerous === true
    }).then(function(result) {
      return result.isConfirmed;
    });
  };

  // ==========================================================
  // ykPrompt - SweetAlert2 input prompt
  // Kullanim: const val = await ykPrompt('Etiket ismi?'); if (val) {...}
  // ==========================================================
  window.ykPrompt = function(message, opts) {
    opts = opts || {};
    if (typeof Swal === 'undefined') {
      return Promise.resolve(window.prompt(message, opts.defaultValue || ''));
    }
    return Swal.fire({
      title: opts.title || 'Giris',
      text: message,
      input: opts.inputType || 'text',
      inputValue: opts.defaultValue || '',
      inputPlaceholder: opts.placeholder || '',
      showCancelButton: true,
      confirmButtonText: opts.confirmText || 'Tamam',
      cancelButtonText: opts.cancelText || 'Iptal',
      reverseButtons: true
    }).then(function(result) {
      return result.isConfirmed ? result.value : null;
    });
  };

  // ==========================================================
  // ykAlert - tek button modal (basit bildirim)
  // ==========================================================
  window.ykAlert = function(message, opts) {
    opts = opts || {};
    if (typeof Swal === 'undefined') {
      alert(message);
      return Promise.resolve();
    }
    return Swal.fire({
      title: opts.title || 'Bilgi',
      text: message,
      icon: opts.icon || 'info',
      confirmButtonText: opts.confirmText || 'Tamam'
    });
  };

  // ==========================================================
  // ykTooltips - tum [data-tooltip] attribute'larini tippy ile bind
  // Otomatik DOMContentLoaded'da calisir + MutationObserver ile yeni elemanlari yakalar
  // ==========================================================
  window.ykTooltips = function(selector) {
    if (typeof tippy === 'undefined') return;
    selector = selector || '[data-tooltip], [title]:not([data-tooltip-skip])';
    var els = document.querySelectorAll(selector);
    els.forEach(function(el) {
      if (el._tippyBound) return;
      var content = el.getAttribute('data-tooltip') || el.getAttribute('title') || '';
      if (!content) return;
      // title attribute kaldir (browser native tooltip cikmasin)
      if (el.hasAttribute('title')) {
        el.setAttribute('data-original-title', el.getAttribute('title'));
        el.removeAttribute('title');
      }
      tippy(el, {
        content: content,
        theme: 'yk',
        delay: [200, 0],
        placement: el.getAttribute('data-tooltip-placement') || 'top',
        animation: 'shift-away',
        arrow: true
      });
      el._tippyBound = true;
    });
  };

  // ==========================================================
  // ykInitAOS - scroll animations init
  // ==========================================================
  window.ykInitAOS = function() {
    if (typeof AOS === 'undefined') return;
    AOS.init({
      duration: 500,
      easing: 'ease-out-cubic',
      once: true,
      offset: 40,
      disable: function() { return window.innerWidth < 600; }  // mobile: kapali
    });
  };

  // ==========================================================
  // BOOTSTRAP - native alert() override (OTOMATIK)
  // Tum eski alert() cagrilari otomatik ykToast'a yonlenir.
  // Smart detection: hata/error -> toast.error, basarili/kaydedildi -> toast.success
  // confirm()/prompt() degismez (sync return gerekli, riskli).
  // ==========================================================
  window.ykOverrideNativeDialogs = function(enable) {
    if (enable === false) {
      // Disable - geri al
      if (window._ykOriginalAlert) {
        window.alert = window._ykOriginalAlert;
        delete window._ykOriginalAlert;
      }
      return;
    }
    if (window._ykOriginalAlert) return;  // already overridden
    window._ykOriginalAlert = window.alert;

    // Smart toast type detection (Turkce + Ingilizce)
    function detectType(msg) {
      var s = String(msg || '').toLowerCase();
      // Asciily fold (TR characters)
      s = s.replace(/[Ä±Ä°iI]/g, 'i').replace(/[ÅŸÅSs]/g, 's')
           .replace(/[ÄŸÄGg]/g, 'g').replace(/[Ã¼ÃœUu]/g, 'u')
           .replace(/[Ã¶Ã–Oo]/g, 'o').replace(/[Ã§Ã‡Cc]/g, 'c');
      // ERROR signals
      if (s.match(/\b(hata|error|hatali|basarisiz|fail|reddedildi|gecersiz|invalid|bulunamadi|yok|izniniz yok|yetki yok|olmamis|olmadi)\b/)) {
        return 'error';
      }
      // SUCCESS signals
      if (s.match(/\b(basarili|kaydedildi|tamam|tamamlandi|olusturuldu|guncellendi|silindi|gonderildi|eklendi|yuklendi|saved|success|done|created|deleted|updated)\b/)) {
        return 'success';
      }
      // WARNING signals
      if (s.match(/\b(dikkat|uyari|warning|emin misin|emin misiniz|onayla|gecikme|risk|alarm)\b/)) {
        return 'warning';
      }
      return 'info';
    }

    window.alert = function(msg) {
      if (typeof Toastify !== 'undefined' && typeof ykToast !== 'undefined') {
        var type = detectType(msg);
        ykToast._show(String(msg), type, type === 'error' ? 6000 : 3500);
      } else {
        window._ykOriginalAlert(msg);
      }
    };
    // confirm/prompt yerinde - sync return gerekli, native kaliyor
    console.log('[yk-polish] native alert() -> ykToast yonlendirme aktif');
  };

  // ==========================================================
  // D700 WebShell layout guard
  // Parallel UI passes can race with inline WebShell CSS. This late style keeps
  // the sidebar fixed so it cannot push the top command bar into the page body.
  // ==========================================================
  window.ykRepairWebShellLayout = function() {
    var html = document.documentElement;
    var body = document.body;
    if (!html || !body) return;
    if (html.getAttribute('data-yazklinik-webshell') !== '1' &&
        !body.classList.contains('yk-webshell-embedded')) return;
    // WebShell modunda body sinifi bazen race condition ile gec setleniyor.
    // Bu durumda ust bar sabitlenirken sidebar sabitlenmedigi icin cakisma olusuyor.
    body.classList.add('yk-webshell-embedded');
    function syncWebShellSidebarState() {
      try {
        var sidebar = document.querySelector('.sidebar');
        var rect = sidebar && sidebar.getBoundingClientRect ? sidebar.getBoundingClientRect() : null;
        var visible = !!(rect && rect.width > 120 && rect.right > 140 && rect.left < 80);
        var width = rect && rect.width ? Math.max(220, Math.min(420, Math.round(rect.width))) : 286;
        body.classList.toggle('yk-webshell-sidebar-visible', visible);
        body.classList.toggle('yk-webshell-sidebar-hidden', !visible);
        body.style.setProperty('--yk-ws-sidebar-w', width + 'px');
        html.style.setProperty('--yk-ws-sidebar-w', width + 'px');
      } catch (_) {}
    }
    syncWebShellSidebarState();
    if (!window._ykWebShellSidebarSyncBound) {
      window._ykWebShellSidebarSyncBound = true;
      window.addEventListener('resize', syncWebShellSidebarState, { passive: true });
      document.addEventListener('click', function() {
        setTimeout(syncWebShellSidebarState, 80);
        setTimeout(syncWebShellSidebarState, 280);
      }, true);
      setInterval(syncWebShellSidebarState, 1200);
    }
    if (document.getElementById('yk-webshell-layout-repair-css')) return;
    var st = document.createElement('style');
    st.id = 'yk-webshell-layout-repair-css';
    st.textContent = [
      'html[data-yazklinik-webshell="1"] body.yk-webshell-embedded .sidebar,',
      'html[data-yazklinik-webshell="1"] body.yk-webshell-embedded .sidebar.use-modern-nav{',
      'position:fixed!important;',
      'top:0!important;',
      'left:0!important;',
      'bottom:0!important;',
      'width:var(--yk-ws-sidebar-w,var(--yk-shell-sidebar-w,var(--sidebar-w,286px)))!important;',
      'height:auto!important;',
      'max-height:100vh!important;',
      'overflow-y:auto!important;',
      'z-index:1800!important;',
      '}',
      'html[data-yazklinik-webshell="1"] .top-header{',
      'display:flex!important;',
      'align-items:center!important;',
      'gap:8px!important;',
      'flex-wrap:nowrap!important;',
      'overflow:hidden!important;',
      'min-height:60px!important;',
      'height:auto!important;',
      'padding:8px 10px!important;',
      'box-sizing:border-box!important;',
      '}',
      'html[data-yazklinik-webshell="1"] body.yk-shortcuts-collapsed .top-header{',
      'left:12px!important;',
      'right:12px!important;',
      'width:auto!important;',
      '}',
      '@media (min-width:1281px){',
      'html[data-yazklinik-webshell="1"] body:not(.yk-shortcuts-collapsed) .top-header{',
      'left:calc(var(--yk-ws-sidebar-w,var(--sidebar-w,286px)) + 18px)!important;',
      'right:12px!important;',
      'width:auto!important;',
      '}',
      'html[data-yazklinik-webshell="1"] body:not(.yk-shortcuts-collapsed) .main-content{',
      'margin-left:var(--yk-ws-sidebar-w,var(--sidebar-w,286px))!important;',
      '}',
      '}',
      'html[data-yazklinik-webshell="1"] .top-header-title,',
      'html[data-yazklinik-webshell="1"] .top-header-badges{',
      'display:none!important;',
      '}',
      'html[data-yazklinik-webshell="1"] .top-header .search-box{',
      'flex:1 1 240px!important;',
      'min-width:180px!important;',
      'max-width:620px!important;',
      'width:auto!important;',
      'order:2!important;',
      '}',
      'html[data-yazklinik-webshell="1"] .top-quick-links{',
      'display:none!important;',
      'align-items:center!important;',
      'gap:7px!important;',
      'flex:0 1 auto!important;',
      'min-width:0!important;',
      'overflow:hidden!important;',
      'order:3!important;',
      '}',
      '@media (min-width:1360px){',
      'html[data-yazklinik-webshell="1"] .top-header .search-box{',
      'flex-basis:220px!important;',
      'max-width:460px!important;',
      '}',
      'html[data-yazklinik-webshell="1"] .top-quick-links{',
      'display:flex!important;',
      'max-width:min(520px,36vw)!important;',
      '}',
      'html[data-yazklinik-webshell="1"] .top-quick-links>*{',
      'flex:0 0 auto!important;',
      '}',
      '}',
      'html[data-yazklinik-webshell="1"] .header-actions{',
      'margin-left:auto!important;',
      'display:flex!important;',
      'align-items:center!important;',
      'justify-content:flex-end!important;',
      'gap:7px!important;',
      'flex:0 0 auto!important;',
      'min-width:0!important;',
      'max-width:min(560px,calc(100vw - 420px))!important;',
      'overflow:hidden!important;',
      'order:4!important;',
      '}',
      'html[data-yazklinik-webshell="1"] .header-actions>*{',
      'flex:0 0 auto!important;',
      '}',
      'html[data-yazklinik-webshell="1"] .header-actions .ai-status-badge{',
      'max-width:72px!important;',
      'min-width:56px!important;',
      'overflow:hidden!important;',
      'white-space:nowrap!important;',
      '}',
      'html[data-yazklinik-webshell="1"] .yk-mode-native-select,',
      'html[data-yazklinik-webshell="1"] .yk-theme-native-select{',
      'opacity:0!important;',
      'color:transparent!important;',
      '-webkit-text-fill-color:transparent!important;',
      '}',
      '@media (max-width:980px){',
      'html[data-yazklinik-webshell="1"] .header-actions{max-width:380px!important;}',
      'html[data-yazklinik-webshell="1"] .top-header .search-box{min-width:150px!important;}',
      '}',
      'html[data-yazklinik-webshell="1"] body.yk-webshell-sidebar-visible .top-header,',
      'html[data-yazklinik-webshell="1"] body.yk-webshell-sidebar-visible.yk-shortcuts-collapsed .top-header{',
      'left:calc(var(--yk-ws-sidebar-w,var(--sidebar-w,286px)) + 10px)!important;',
      'right:8px!important;',
      'width:auto!important;',
      '}',
      'html[data-yazklinik-webshell="1"] body.yk-webshell-sidebar-hidden .top-header{',
      'left:12px!important;',
      'right:12px!important;',
      '}',
      'html[data-yazklinik-webshell="1"] .top-header{',
      'position:fixed!important;',
      'top:10px!important;',
      'z-index:2200!important;',
      'max-height:66px!important;',
      'min-height:60px!important;',
      'flex-wrap:nowrap!important;',
      'overflow:hidden!important;',
      '}',
      'html[data-yazklinik-webshell="1"] .top-header .search-box{',
      'flex:1 1 auto!important;',
      'min-width:220px!important;',
      'max-width:none!important;',
      'overflow:hidden!important;',
      '}',
      'html[data-yazklinik-webshell="1"] .top-header .search-box input{',
      'width:100%!important;',
      'min-width:0!important;',
      'text-overflow:ellipsis!important;',
      '}',
      'html[data-yazklinik-webshell="1"] .top-quick-links{',
      'display:none!important;',
      '}',
      'html[data-yazklinik-webshell="1"] .header-actions{',
      'flex-wrap:nowrap!important;',
      'max-width:min(430px,48vw)!important;',
      'overflow:hidden!important;',
      '}',
      'html[data-yazklinik-webshell="1"] body.yk-webshell-sidebar-visible .header-actions .ai-status-badge,',
      'html[data-yazklinik-webshell="1"] body.yk-webshell-sidebar-visible .header-actions .header-icon-btn[title="Geri"],',
      'html[data-yazklinik-webshell="1"] body.yk-webshell-sidebar-visible .header-actions .header-icon-btn[title="Dogum Geri Sayim"]{',
      'display:none!important;',
      '}',
      'html[data-yazklinik-webshell="1"] body.yk-webshell-sidebar-visible .profile-chip{',
      'width:46px!important;',
      'min-width:46px!important;',
      'max-width:46px!important;',
      'height:44px!important;',
      'padding:0!important;',
      'justify-content:center!important;',
      '}',
      'html[data-yazklinik-webshell="1"] body.yk-webshell-sidebar-visible .profile-chip .profile-copy{',
      'display:none!important;',
      '}',
      'html[data-yazklinik-webshell="1"] body.yk-webshell-sidebar-visible .yk-mode-single{',
      'width:112px!important;',
      'min-width:112px!important;',
      'max-width:112px!important;',
      '}',
      'html[data-yazklinik-webshell="1"] body.yk-webshell-sidebar-visible .header-icon-btn,',
      'html[data-yazklinik-webshell="1"] body.yk-webshell-sidebar-visible .theme-picker-btn{',
      'width:44px!important;',
      'min-width:44px!important;',
      'height:44px!important;',
      '}'
    ].join('');
    document.head.appendChild(st);
  };

  // ==========================================================
  // D700 mobile sol menu toggle guard
  // Mobil ust bardaki sol menu dugmesini gorunur/aktif tutar.
  // ==========================================================
  window.ykEnsureMobileMenuToggle = function() {
    var html = document.documentElement;
    var body = document.body;
    if (!html || !body) return;
    var topHeader = document.querySelector('.top-header');
    var sidebar = document.querySelector('.sidebar');
    if (!topHeader || !sidebar) return;

    if (!document.getElementById('yk-mobile-menu-toggle-css')) {
      var st = document.createElement('style');
      st.id = 'yk-mobile-menu-toggle-css';
      st.textContent = [
        '@media (max-width:980px){',
        'html[data-yazklinik-webshell="1"] .top-header .hamburger-btn,',
        'html[data-yazklinik-webshell="1"] .top-header .yk-mobile-left-toggle{',
        'display:inline-flex!important;',
        'align-items:center!important;',
        'justify-content:center!important;',
        'width:42px!important;',
        'min-width:42px!important;',
        'height:42px!important;',
        'border-radius:12px!important;',
        'visibility:visible!important;',
        'opacity:1!important;',
        'pointer-events:auto!important;',
        'z-index:2300!important;',
        '}',
        '}'
      ].join('');
      document.head.appendChild(st);
    }

    var btn = topHeader.querySelector('.hamburger-btn');
    if (!btn) {
      btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'header-icon-btn hamburger-btn yk-mobile-left-toggle';
      btn.setAttribute('aria-label', 'Sol menuyu ac veya kapat');
      btn.setAttribute('title', 'Menu');
      btn.innerHTML = '<i class="fa-solid fa-bars"></i>';
      topHeader.insertBefore(btn, topHeader.firstChild);
    } else {
      btn.classList.add('yk-mobile-left-toggle');
    }

    function syncState() {
      try {
        var open = sidebar.classList.contains('show') || body.classList.contains('yk-webshell-sidebar-visible');
        btn.setAttribute('aria-expanded', open ? 'true' : 'false');
      } catch (_) {}
    }

    function setOpen(open) {
      var overlay = document.querySelector('.sidebar-overlay');
      sidebar.classList.toggle('show', !!open);
      if (overlay) overlay.classList.toggle('show', !!open);
      body.classList.toggle('yk-webshell-sidebar-visible', !!open);
      body.classList.toggle('yk-webshell-sidebar-hidden', !open);
      if (window.innerWidth <= 980) {
        body.style.overflow = open ? 'hidden' : '';
      } else {
        body.style.overflow = '';
      }
      syncState();
    }

    if (!btn.__ykMobileToggleBound) {
      btn.__ykMobileToggleBound = true;
      btn.addEventListener('click', function(e) {
        e.preventDefault();
        e.stopPropagation();
        try {
          if (typeof window.toggleSidebar === 'function') {
            window.toggleSidebar(e);
            setTimeout(syncState, 80);
            return;
          }
        } catch (_) {}
        var open = sidebar.classList.contains('show');
        setOpen(!open);
      });

      document.addEventListener('click', function(e) {
        if (window.innerWidth > 980) return;
        if (!sidebar.classList.contains('show')) return;
        if (sidebar.contains(e.target) || btn.contains(e.target)) return;
        setOpen(false);
      }, true);

      document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' && window.innerWidth <= 980 && sidebar.classList.contains('show')) {
          setOpen(false);
        }
      });

      window.addEventListener('resize', function() {
        if (window.innerWidth > 980) {
          body.style.overflow = '';
        }
        syncState();
      }, { passive: true });
    }

    syncState();
  };

  // ==========================================================
  // D700 sidebar contrast guard
  // Koyu tema/WebShell'de okunmayan menuleri yuksek kontrasta ceker.
  // ==========================================================
  window.ykImproveSidebarContrast = function() {
    if (document.getElementById('yk-sidebar-contrast-fix-css')) return;
    var st = document.createElement('style');
    st.id = 'yk-sidebar-contrast-fix-css';
    st.textContent = [
      'html[data-yazklinik-webshell="1"] .sidebar{',
      '--yk-sidebar-text:#e8f2ff;',
      '--yk-sidebar-muted:#a9c2dc;',
      '--yk-sidebar-strong:#ffffff;',
      '}',
      'html[data-yazklinik-webshell="1"] .sidebar a,',
      'html[data-yazklinik-webshell="1"] .sidebar button,',
      'html[data-yazklinik-webshell="1"] .sidebar .menu-item,',
      'html[data-yazklinik-webshell="1"] .sidebar .nav-link,',
      'html[data-yazklinik-webshell="1"] .sidebar .route-link,',
      'html[data-yazklinik-webshell="1"] .sidebar [role="button"]{',
      'color:var(--yk-sidebar-text)!important;',
      '}',
      'html[data-yazklinik-webshell="1"] .sidebar .section-title,',
      'html[data-yazklinik-webshell="1"] .sidebar .menu-section-title,',
      'html[data-yazklinik-webshell="1"] .sidebar .menu-caption,',
      'html[data-yazklinik-webshell="1"] .sidebar .menu-subtitle,',
      'html[data-yazklinik-webshell="1"] .sidebar small,',
      'html[data-yazklinik-webshell="1"] .sidebar .muted{',
      'color:var(--yk-sidebar-muted)!important;',
      '}',
      'html[data-yazklinik-webshell="1"] .sidebar .active,',
      'html[data-yazklinik-webshell="1"] .sidebar .menu-item.active,',
      'html[data-yazklinik-webshell="1"] .sidebar .nav-link.active,',
      'html[data-yazklinik-webshell="1"] .sidebar .menu-item.is-active{',
      'color:var(--yk-sidebar-strong)!important;',
      'font-weight:700!important;',
      '}',
      'html[data-yazklinik-webshell="1"] .sidebar i,',
      'html[data-yazklinik-webshell="1"] .sidebar svg{',
      'color:#79caff!important;',
      'fill:currentColor!important;',
      'stroke:currentColor!important;',
      'opacity:1!important;',
      '}',
      'html[data-yazklinik-webshell="1"] .sidebar .active i,',
      'html[data-yazklinik-webshell="1"] .sidebar .active svg,',
      'html[data-yazklinik-webshell="1"] .sidebar .menu-item.active i,',
      'html[data-yazklinik-webshell="1"] .sidebar .menu-item.active svg{',
      'color:#1f7cff!important;',
      '}',
      'html[data-yazklinik-webshell="1"] .sidebar .menu-chip,',
      'html[data-yazklinik-webshell="1"] .sidebar .badge{',
      'color:#0b2742!important;',
      '}',
      'html[data-yazklinik-webshell="1"] .sidebar.use-modern-nav :where(.yk-sidebar-pulse,.sidebar-orbit,.sidebar-orbit-main,[class*="pulse"],[class*="flow"],[class*="ritim"],[class*="today"],[class*="bugun"]){',
      'background:linear-gradient(180deg,rgba(9,31,54,.92),rgba(12,55,86,.86))!important;',
      'border:1px solid rgba(124,183,233,.34)!important;',
      'color:#eef6ff!important;',
      'box-shadow:inset 0 1px 0 rgba(255,255,255,.08)!important;',
      '}',
      'html[data-yazklinik-webshell="1"] .sidebar.use-modern-nav :where(.yk-sidebar-pulse,.sidebar-orbit,.sidebar-orbit-main,[class*="pulse"],[class*="flow"],[class*="ritim"],[class*="today"],[class*="bugun"]) :where(h1,h2,h3,h4,h5,strong,b,span,small,p,a,label,div){',
      'color:#eef6ff!important;',
      'opacity:1!important;',
      'text-shadow:none!important;',
      '}',
      'html[data-yazklinik-webshell="1"] .sidebar.use-modern-nav :where(.yk-sidebar-pulse,.sidebar-orbit,.sidebar-orbit-main,[class*="pulse"],[class*="flow"],[class*="ritim"],[class*="today"],[class*="bugun"]) :where(i,svg){',
      'color:#8dd6ff!important;',
      'opacity:1!important;',
      '}',
      'html[data-yazklinik-webshell="1"] .sidebar.use-modern-nav :where(.yk-sidebar-pulse,.sidebar-orbit,.sidebar-orbit-main,[class*="pulse"],[class*="flow"],[class*="ritim"],[class*="today"],[class*="bugun"]) :where(button,.btn,.keycap){',
      'background:rgba(240,248,255,.16)!important;',
      'border:1px solid rgba(197,226,255,.50)!important;',
      'color:#f7fbff!important;',
      '}',
      'html[data-yazklinik-webshell="1"] .sidebar.use-modern-nav :where(.yk-sidebar-pulse,.sidebar-orbit,.sidebar-orbit-main,[class*="pulse"],[class*="flow"],[class*="ritim"],[class*="today"],[class*="bugun"]) :where(button,.btn):hover{',
      'background:rgba(240,248,255,.24)!important;',
      'color:#ffffff!important;',
      '}'
    ].join('');
    document.head.appendChild(st);
  };

  // ==========================================================
  // D700 Alex expanded panel polish
  // GeniÅŸletilmiÅŸ sohbet panelini daha bÃ¼yÃ¼k/dikdÃ¶rtgen ve okunur yapar.
  // ==========================================================
  window.ykPolishAlexExpandedPanel = function() {
    if (document.getElementById('yk-alex-expanded-polish-css')) return;
    var st = document.createElement('style');
    st.id = 'yk-alex-expanded-polish-css';
    st.textContent = [
      '.yk-voice-agent.open .yk-voice-agent-panel{',
      'width:min(860px,calc(100vw - 110px))!important;',
      'max-width:min(860px,calc(100vw - 110px))!important;',
      'min-width:560px!important;',
      'max-height:min(70vh,720px)!important;',
      'overflow:auto!important;',
      'border-radius:12px!important;',
      'padding:14px 14px 12px!important;',
      'border:1px solid rgba(38,103,160,.28)!important;',
      'box-shadow:0 24px 60px rgba(15,42,68,.24)!important;',
      'background:linear-gradient(180deg,#ffffff 0%,#f5faff 100%)!important;',
      '}',
      '.yk-voice-agent.open .yk-voice-agent-title{',
      'padding:0 0 10px!important;',
      'margin:0 0 10px!important;',
      'border-bottom:1px solid rgba(43,96,145,.18)!important;',
      '}',
      '.yk-voice-agent.open #ykVoiceText{',
      'min-height:124px!important;',
      'height:124px!important;',
      'border-radius:10px!important;',
      'border:1px solid rgba(40,105,160,.28)!important;',
      'background:#ffffff!important;',
      'box-shadow:inset 0 1px 0 rgba(255,255,255,.7)!important;',
      'font-size:28px!important;',
      'line-height:1.45!important;',
      'padding:12px 13px!important;',
      '}',
      '.yk-voice-agent.open .yk-voice-agent-actions{',
      'display:grid!important;',
      'grid-template-columns:repeat(3,minmax(150px,1fr))!important;',
      'gap:10px!important;',
      'margin-top:12px!important;',
      'padding:12px!important;',
      'border-radius:10px!important;',
      'border:1px solid rgba(43,96,145,.18)!important;',
      'background:#eef6ff!important;',
      '}',
      '.yk-voice-agent.open .yk-voice-agent-actions button,',
      '.yk-voice-agent.open .yk-voice-agent-actions a{',
      'width:100%!important;',
      'min-height:42px!important;',
      'border-radius:10px!important;',
      'font-weight:600!important;',
      '}',
      '.yk-voice-agent.open .yk-voice-agent-status{',
      'margin-top:10px!important;',
      'padding:8px 10px!important;',
      'border-radius:8px!important;',
      'background:#e9f4ff!important;',
      'border:1px solid rgba(43,96,145,.16)!important;',
      '}',
      '@media (max-width:980px){',
      '.yk-voice-agent.open .yk-voice-agent-panel{',
      'width:calc(100vw - 20px)!important;',
      'max-width:calc(100vw - 20px)!important;',
      'min-width:0!important;',
      'max-height:64vh!important;',
      'padding:12px!important;',
      '}',
      '.yk-voice-agent.open .yk-voice-agent-actions{',
      'grid-template-columns:repeat(2,minmax(130px,1fr))!important;',
      '}',
      '.yk-voice-agent.open #ykVoiceText{',
      'min-height:104px!important;',
      'height:104px!important;',
      '}',
      '}',
      '@media (max-width:640px){',
      '.yk-voice-agent.open .yk-voice-agent-actions{',
      'grid-template-columns:1fr!important;',
      '}',
      '}'
    ].join('');
    document.head.appendChild(st);
  };

  // ==========================================================
  // D700 timeline contrast guard (hasta gecmis kartlari)
  // Koyu arka planda timeline metinlerini okunur tutar.
  // ==========================================================
  window.ykImproveTimelineContrast = function() {
    if (document.getElementById('yk-timeline-contrast-fix-css')) return;
    var st = document.createElement('style');
    st.id = 'yk-timeline-contrast-fix-css';
    st.textContent = [
      '.yk-timeline-card{',
      'background:linear-gradient(180deg,rgba(9,28,50,.96),rgba(24,47,76,.94))!important;',
      'border:1px solid rgba(138,188,234,.38)!important;',
      'box-shadow:0 14px 30px rgba(5,18,34,.32)!important;',
      '}',
      '.yk-timeline-card .yk-timeline-head{',
      'background:linear-gradient(135deg,#11355d,#1c5488)!important;',
      'color:#eef7ff!important;',
      'border-bottom:1px solid rgba(177,214,248,.38)!important;',
      '}',
      '.yk-timeline-card .yk-timeline-list{',
      'background:transparent!important;',
      '}',
      '.yk-timeline-card .yk-timeline-item{',
      'background:linear-gradient(180deg,rgba(23,43,68,.88),rgba(34,58,88,.86))!important;',
      'border-color:rgba(155,204,247,.30)!important;',
      'color:#eaf4ff!important;',
      '}',
      '.yk-timeline-card .yk-timeline-item :where(b,strong,span,small,div,p){',
      'color:#eaf4ff!important;',
      'opacity:1!important;',
      '}',
      '.yk-timeline-card .yk-timeline-item .small{',
      'color:#d8e9fb!important;',
      'font-weight:500!important;',
      '}',
      '.yk-timeline-card .yk-timeline-item .badge.bg-info{',
      'background:#0ea5e9!important;',
      'color:#ffffff!important;',
      'border:1px solid rgba(255,255,255,.45)!important;',
      '}',
      '.yk-timeline-card .yk-timeline-item .btn-outline-primary{',
      'color:#eaf6ff!important;',
      'border-color:rgba(177,214,248,.62)!important;',
      'background:rgba(17,62,103,.46)!important;',
      '}',
      '.yk-timeline-card .yk-timeline-item .btn-outline-primary:hover{',
      'background:rgba(36,129,208,.54)!important;',
      'color:#ffffff!important;',
      'border-color:rgba(220,239,255,.9)!important;',
      '}'
    ].join('');
    document.head.appendChild(st);
  };

  // ==========================================================
  // D700 dark-page contrast guard
  // Koyu tema/palette modullerinde siyah kalan yazilari acik tona ceker.
  // ==========================================================
  window.ykImproveDarkPageContrast = function() {
    if (document.getElementById('yk-dark-page-contrast-fix-css')) return;
    var st = document.createElement('style');
    st.id = 'yk-dark-page-contrast-fix-css';
    st.textContent = [
      ':root{',
      '--yk-dark-auto-text:#eaf3ff;',
      '--yk-dark-auto-muted:#b9cde2;',
      '--yk-dark-auto-strong:#ffffff;',
      '--yk-dark-auto-link:#8dd6ff;',
      '}',
      ':where(html[data-theme="dark"],html[data-palette="midnight-pro"],html[data-palette="midnight-clinic"]){',
      'color:var(--yk-dark-auto-text)!important;',
      '}',
      ':where(html[data-theme="dark"],html[data-palette="midnight-pro"],html[data-palette="midnight-clinic"]) :where(.text-dark):not(.badge):not(.btn):not(.chip):not(.pill){',
      'color:var(--yk-dark-auto-text)!important;',
      '-webkit-text-fill-color:var(--yk-dark-auto-text)!important;',
      '}',
      ':where(html[data-theme="dark"],html[data-palette="midnight-pro"],html[data-palette="midnight-clinic"]) :where(.text-muted,.muted,small,.small,.form-text,.help-text,.subtle){',
      'color:var(--yk-dark-auto-muted)!important;',
      '-webkit-text-fill-color:var(--yk-dark-auto-muted)!important;',
      '}',
      ':where(html[data-theme="dark"],html[data-palette="midnight-pro"],html[data-palette="midnight-clinic"]) :where(.card,.yk-card,.patient-card,.modal-content,.dropdown-menu,.table-responsive,.yk-panel,.yk-dashboard-card,.yk-overview-card,.yk-follow-hub,.yk-visit-followup-shell,.yk-patient-command,.yk-patient-metric,.yk-service-agent-card,.yk-know-card,.yk-bk-card,.yk-eb-card,.yk-ex-card,.yk-dicom-hero,.yk-dicom-action,.yk-dicom-stat,.yk-dicom-liveitem,.yk-dicom-flow-step,.yk-dicom-service,.yk-timeline-card,.top-header,.header-card){',
      'color:var(--yk-dark-auto-text)!important;',
      '-webkit-text-fill-color:var(--yk-dark-auto-text)!important;',
      '}',
      ':where(html[data-theme="dark"],html[data-palette="midnight-pro"],html[data-palette="midnight-clinic"]) :where(.card,.yk-card,.patient-card,.modal-content,.dropdown-menu,.table,.table-responsive,.yk-panel,.yk-dashboard-card,.yk-overview-card,.yk-follow-hub,.yk-visit-followup-shell,.yk-patient-command,.yk-patient-metric,.yk-service-agent-card,.yk-know-card,.yk-bk-card,.yk-eb-card,.yk-ex-card,.yk-dicom-hero,.yk-dicom-action,.yk-dicom-stat,.yk-dicom-liveitem,.yk-dicom-flow-step,.yk-dicom-service,.yk-timeline-card,.top-header,.header-card) :where(h1,h2,h3,h4,h5,h6,p,span,strong,b,label,li,td,th,a){',
      'color:var(--yk-dark-auto-text)!important;',
      '-webkit-text-fill-color:var(--yk-dark-auto-text)!important;',
      '}',
      ':where(html[data-theme="dark"],html[data-palette="midnight-pro"],html[data-palette="midnight-clinic"]) :where(.card,.yk-card,.patient-card,.modal-content,.dropdown-menu,.table,.table-responsive,.yk-panel,.yk-dashboard-card,.yk-overview-card,.yk-follow-hub,.yk-visit-followup-shell,.yk-patient-command,.yk-patient-metric,.yk-service-agent-card,.yk-know-card,.yk-bk-card,.yk-eb-card,.yk-ex-card,.yk-dicom-hero,.yk-dicom-action,.yk-dicom-stat,.yk-dicom-liveitem,.yk-dicom-flow-step,.yk-dicom-service,.yk-timeline-card,.top-header,.header-card) :where(a:not(.btn)){',
      'color:var(--yk-dark-auto-link)!important;',
      '-webkit-text-fill-color:var(--yk-dark-auto-link)!important;',
      '}',
      ':where(html[data-theme="dark"],html[data-palette="midnight-pro"],html[data-palette="midnight-clinic"]) :where([style*="color:#000"],[style*="color: #000"],[style*="color:black"],[style*="color:rgb(0,0,0)"],[style*="color: rgb(0, 0, 0)"],[style*="color:#111"],[style*="color: #111"],[style*="color:#0f172a"],[style*="color: #0f172a"]){',
      'color:var(--yk-dark-auto-text)!important;',
      '-webkit-text-fill-color:var(--yk-dark-auto-text)!important;',
      '}'
    ].join('');
    document.head.appendChild(st);
  };

  // ==========================================================
  // D700 mojibake guard
  // Eski Win-1252/UTF-8 karisimindan gelen gorunen Turkce bozulmalari
  // sayfa yuklenince duzeltir.
  // ==========================================================
  window.ykRepairVisibleMojibake = function(rootNode) {
    var root = rootNode && rootNode.nodeType === 1 ? rootNode : document.body;
    if (!root) return;
    var pairs = [
      [/\u00c3\u00a2\u00c5\u201c\u00e2\u20ac\u00a6\s*/g, ''],
      [/\u00e2\u0153(?:\u2026|\.{2,4})\s*/g, ''],
      [/Do\u00c3\u201e\u00c5\u00b8um/g, 'Do\u011fum'],
      [/do\u00c3\u201e\u00c5\u00b8um/g, 'do\u011fum'],
      [/Do\u00c4\u0178um/g, 'Do\u011fum'],
      [/do\u00c4\u0178um/g, 'do\u011fum'],
      [/Do\u00c4Yum/g, 'Do\u011fum'],
      [/do\u00c4yum/g, 'do\u011fum'],
      [/Do\u00c3\u201e\u00c5\u00b8uranlar/g, 'Do\u011furanlar'],
      [/Do\u00c4\u0178uranlar/g, 'Do\u011furanlar'],
      [/Do\u00c4Yuranlar/g, 'Do\u011furanlar'],
      [/kayd\u00c3\u201e\u00c2\u00b1/g, 'kayd\u0131'],
      [/kayd\u00c4\u00b1/g, 'kayd\u0131'],
      [/ba\u00c3\u2026\u00c5\u00b8ar\u00c3\u201e\u00c2\u00b1l\u00c3\u201e\u00c2\u00b1/g, 'ba\u015far\u0131l\u0131'],
      [/ba\u00c5\u0178ar\u00c4\u00b1l\u00c4\u00b1/g, 'ba\u015far\u0131l\u0131'],
      [/ba\u00c4Yar\u00c4\u00b1\u00c4\u00b1/g, 'ba\u015far\u0131l\u0131'],
      [/art\u00c3\u201e\u00c2\u00b1k/g, 'art\u0131k'],
      [/art\u00c4\u00b1k/g, 'art\u0131k'],
      [/hatas\u00c3\u201e\u00c2\u00b1/g, 'hatas\u0131'],
      [/hatas\u00c4\u00b1/g, 'hatas\u0131'],
      [/Kullan\u00c4\u00b1c\u00c4\u00b1/g, 'Kullan\u0131c\u0131'],
      [/Ye\u00c5\u0178ili/g, 'Ye\u015fili'],
      [/Geli\u00c3\u0178ler/g, 'Gelisler'],
      [/geli\u00c3\u0178ler/g, 'gelisler'],
      [/Geli\u00c3\u0178/g, 'Gelis'],
      [/geli\u00c3\u0178/g, 'gelis'],
      [/Geli\u00c5\u0178/g, 'Geli\u015f'],
      [/geli\u00c5\u0178/g, 'geli\u015f'],
      [/Do\u00c3\u0178um/g, 'Dogum'],
      [/do\u00c3\u0178um/g, 'dogum'],
      [/Do\u00c3\u0178uranlar/g, 'Doguranlar'],
      [/kayd\u00c3\u00b1/g, 'kaydi'],
      [/ba\u00c5\u0178ar\u00c4\u00b1l\u00c4\u00b1/g, 'basarili'],
      [/Ayr\u00c3\u00b1nt\u00c3\u00b1/g, 'Ayrinti'],
      [/Ayr\u00c4\u00b1nt\u00c4\u00b1/g, 'Ayr\u0131nt\u0131'],
      [/T\u00c3\u00bcm/g, 'T\u00fcm'],
      [/Henu\u00c4\u009f/g, 'Henuz']
    ];
    function fixText(value) {
      if (!value || !/[\u00c3\u00c4\u00c5\u00e2]/.test(value)) return value;
      var next = value;
      pairs.forEach(function(pair) {
        next = next.replace(pair[0], pair[1]);
      });
      return next;
    }
    function shouldSkip(node) {
      var parent = node && node.parentElement;
      if (!parent) return true;
      var tag = (parent.tagName || '').toUpperCase();
      return tag === 'SCRIPT' || tag === 'STYLE' || tag === 'NOSCRIPT' ||
             tag === 'TEXTAREA' || tag === 'CODE' || tag === 'PRE';
    }
    try {
      var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
        acceptNode: function(node) {
          return shouldSkip(node) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT;
        }
      });
      var node = walker.nextNode();
      var seen = 0;
      while (node && seen < 5000) {
        var fixed = fixText(node.nodeValue);
        if (fixed !== node.nodeValue) node.nodeValue = fixed;
        node = walker.nextNode();
        seen += 1;
      }
      root.querySelectorAll('[title],[aria-label],[placeholder]').forEach(function(el) {
        ['title', 'aria-label', 'placeholder'].forEach(function(attr) {
          var value = el.getAttribute(attr);
          var fixed = fixText(value);
          if (fixed !== value) el.setAttribute(attr, fixed);
        });
      });
    } catch (e) {
      console.warn('[yk-polish] mojibake repair:', e);
    }
  };

  // ==========================================================
  // OTOMATIK BASLAT - DOMContentLoaded
  // ==========================================================
  function init() {
    try { ykTooltips(); } catch(e) { console.warn('[yk-polish] tooltips:', e); }
    try { ykInitAOS(); } catch(e) { console.warn('[yk-polish] aos:', e); }
    // OTOMATIK: native alert() -> ykToast yonlendir (103 cagri tek seferde upgrade)
    try { ykOverrideNativeDialogs(true); } catch(e) { console.warn('[yk-polish] alert override:', e); }
    try { ykRepairWebShellLayout(); } catch(e) { console.warn('[yk-polish] webshell layout:', e); }
    try { ykImproveSidebarContrast(); } catch(e) { console.warn('[yk-polish] sidebar contrast:', e); }
    try { ykImproveTimelineContrast(); } catch(e) { console.warn('[yk-polish] timeline contrast:', e); }
    try { ykImproveDarkPageContrast(); } catch(e) { console.warn('[yk-polish] dark contrast:', e); }
    try { ykPolishAlexExpandedPanel(); } catch(e) { console.warn('[yk-polish] alex expanded panel:', e); }
    try { ykEnsureMobileMenuToggle(); } catch(e) { console.warn('[yk-polish] mobile menu toggle:', e); }
    try { ykRepairVisibleMojibake(); } catch(e) { console.warn('[yk-polish] mojibake:', e); }
    // Yeni eklenen elemanlari da yakala (10 dakikada bir scan - ucuz)
    if (window.MutationObserver) {
      var debounceTimer = null;
      var obs = new MutationObserver(function() {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(function() {
          try { ykTooltips(); } catch(e) {}
          try { ykRepairVisibleMojibake(); } catch(e) {}
        }, 500);
      });
      obs.observe(document.body, { childList: true, subtree: true });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();

