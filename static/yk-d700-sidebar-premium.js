(function () {
  "use strict";

  var cfg = {
    bg: "linear-gradient(120deg, rgba(255,255,255,.055) 0 1px, transparent 1px 18px)," +
      "linear-gradient(180deg, #0b1d31 0%, #12314a 46%, #075b5c 100%)",
    panel: "linear-gradient(145deg, rgba(255,255,255,.145) 0%, rgba(255,255,255,.065) 100%)",
    panel2: "linear-gradient(145deg, rgba(241,250,255,.98) 0%, rgba(236,255,249,.94) 100%)",
    line: "rgba(255,255,255,.20)",
    lineStrong: "rgba(125,243,206,.42)",
    ink: "#f8fbff",
    muted: "#c6d9e6",
    darkInk: "#10243f",
    accent: "#7df3ce",
    cyan: "#38bdf8",
    amber: "#fbbf24",
    active: "linear-gradient(135deg, rgba(14,165,233,.98) 0%, rgba(13,148,136,.98) 100%)",
    danger: "linear-gradient(135deg, #fb7185 0%, #f59e0b 100%)"
  };

  var iconGradients = [
    "linear-gradient(135deg, #0ea5e9 0%, #2563eb 100%)",
    "linear-gradient(135deg, #14b8a6 0%, #0f766e 100%)",
    "linear-gradient(135deg, #f59e0b 0%, #d97706 100%)",
    "linear-gradient(135deg, #ec4899 0%, #be123c 100%)",
    "linear-gradient(135deg, #8b5cf6 0%, #2563eb 100%)"
  ];

  function each(root, selector, fn) {
    Array.prototype.forEach.call((root || document).querySelectorAll(selector), fn);
  }

  function set(el, prop, value) {
    if (!el) return;
    el.style.setProperty(prop, value, "important");
  }

  function textOf(el) {
    return (el && el.textContent ? el.textContent : "").replace(/\s+/g, " ").trim().toLowerCase();
  }

  function markCurrent(sidebar) {
    var path = window.location.pathname || "/";
    each(sidebar, ".sidebar-link, .sidebar-quick-action", function (link) {
      var href = link.getAttribute("href") || "";
      var label = textOf(link);
      var targetPath = "";
      var active = false;
      if (href && href !== "#") {
        try {
          targetPath = new URL(href, window.location.origin).pathname || "";
        } catch (err) {
          targetPath = href.charAt(0) === "/" ? href.split(/[?#]/)[0] : "";
        }
        active = targetPath === path || (targetPath.length > 1 && path.indexOf(targetPath + "/") === 0);
      }
      if (!active && (path === "/hastalar" || path === "/") && label === "hastalar") active = true;
      if (!active && path.indexOf("/randevu") === 0 && (label === "randevu" || label === "randevular")) active = true;
      if (!active && path.indexOf("/ajan") === 0 && (label === "ajanlar" || label.indexOf("ajan") === 0)) active = true;
      link.classList.toggle("yk-d700-current", !!active);
    });
  }

  function polish() {
    var sidebar = document.querySelector(".sidebar.use-modern-nav, aside#sidebar.sidebar");
    if (!sidebar) return;

    document.documentElement.setAttribute("data-d700-premium-sidebar", "1");
    sidebar.setAttribute("data-d700-premium-sidebar", "1");
    set(sidebar, "background", cfg.bg);
    set(sidebar, "color", cfg.ink);
    set(sidebar, "border-right", "1px solid rgba(110,231,183,.24)");
    set(sidebar, "box-shadow", "18px 0 48px rgba(7,25,45,.34)");
    set(sidebar, "scrollbar-color", "rgba(110,231,183,.42) rgba(255,255,255,.08)");
    set(sidebar, "padding", "14px 10px 18px");

    each(sidebar, ".sidebar-brand", function (el) {
      set(el, "background", cfg.panel);
      set(el, "border", "1px solid " + cfg.lineStrong);
      set(el, "border-radius", "18px");
      set(el, "box-shadow", "0 18px 38px rgba(3,12,22,.28), inset 0 1px 0 rgba(255,255,255,.18)");
      set(el, "color", cfg.ink);
      set(el, "min-height", "106px");
    });
    each(sidebar, ".sidebar-brand-name", function (el) {
      set(el, "color", cfg.ink);
      set(el, "-webkit-text-fill-color", cfg.ink);
      set(el, "letter-spacing", "0");
    });
    each(sidebar, ".sidebar-brand-doctor, .yk-mode-badge, .yk-version-badge", function (el) {
      set(el, "background", "rgba(236,248,255,.92)");
      set(el, "border", "1px solid rgba(110,231,183,.28)");
      set(el, "color", "#17405e");
      set(el, "-webkit-text-fill-color", "#17405e");
      set(el, "box-shadow", "0 8px 18px rgba(3,12,22,.12)");
    });
    each(sidebar, ".sidebar-brand-icon", function (el) {
      set(el, "background", "linear-gradient(135deg, #0b86b6 0%, #0b9f8c 100%)");
      set(el, "box-shadow", "0 16px 30px rgba(8,145,178,.34)");
      set(el, "border", "1px solid rgba(255,255,255,.28)");
      set(el, "width", "46px");
      set(el, "height", "46px");
    });

    each(sidebar, ".yk-sidebar-mode-tabs", function (el) {
      set(el, "background", "rgba(3,12,22,.26)");
      set(el, "border", "1px solid rgba(255,255,255,.18)");
      set(el, "border-radius", "14px");
      set(el, "box-shadow", "inset 0 1px 0 rgba(255,255,255,.12)");
      set(el, "padding", "4px");
      set(el, "gap", "4px");
    });
    each(sidebar, ".yk-sidebar-mode-tab", function (el) {
      set(el, "color", cfg.muted);
      set(el, "-webkit-text-fill-color", cfg.muted);
      set(el, "border", "1px solid transparent");
      set(el, "border-radius", "11px");
      set(el, "background", "transparent");
    });
    each(sidebar, ".yk-sidebar-mode-tab.active", function (el) {
      set(el, "background", cfg.panel2);
      set(el, "color", cfg.darkInk);
      set(el, "-webkit-text-fill-color", cfg.darkInk);
      set(el, "border-color", "rgba(110,231,183,.44)");
      set(el, "box-shadow", "0 12px 26px rgba(3,12,22,.20)");
    });

    each(sidebar, ".yk-midnight-pro-btn", function (el) {
      set(el, "display", "grid");
      set(el, "grid-template-columns", "42px minmax(0,1fr)");
      set(el, "align-items", "center");
      set(el, "gap", "10px");
      set(el, "width", "100%");
      set(el, "margin", "10px 0 12px");
      set(el, "padding", "11px 12px");
      set(el, "background", "linear-gradient(135deg, rgba(14,165,233,.18), rgba(13,148,136,.16))");
      set(el, "border", "1px solid rgba(125,243,206,.30)");
      set(el, "border-radius", "18px");
      set(el, "color", cfg.ink);
      set(el, "-webkit-text-fill-color", cfg.ink);
      set(el, "box-shadow", "0 16px 32px rgba(3,12,22,.20)");
    });
    each(sidebar, ".yk-midnight-pro-dot", function (el) {
      set(el, "display", "inline-flex");
      set(el, "align-items", "center");
      set(el, "justify-content", "center");
      set(el, "width", "36px");
      set(el, "height", "36px");
      set(el, "border-radius", "14px");
      set(el, "background", "linear-gradient(135deg, #2563eb 0%, #14b8a6 100%)");
      set(el, "color", "#ffffff");
      set(el, "-webkit-text-fill-color", "#ffffff");
      set(el, "box-shadow", "0 12px 24px rgba(14,165,233,.24)");
    });

    each(sidebar, ".sidebar-orbit, .yk-sidebar-card, .sidebar-menu-finder", function (el) {
      set(el, "background", cfg.panel);
      set(el, "border", "1px solid " + cfg.line);
      set(el, "border-top-color", cfg.lineStrong);
      set(el, "border-radius", "18px");
      set(el, "box-shadow", "0 16px 32px rgba(3,12,22,.20)");
      set(el, "color", cfg.ink);
    });
    each(sidebar, ".sidebar-menu-finder-title, .sidebar-orbit-title, .sidebar-orbit strong", function (el) {
      set(el, "color", cfg.ink);
      set(el, "-webkit-text-fill-color", cfg.ink);
    });
    each(sidebar, ".sidebar-menu-finder small, .sidebar-orbit-kicker, .sidebar-orbit small", function (el) {
      set(el, "color", cfg.muted);
      set(el, "-webkit-text-fill-color", cfg.muted);
    });
    each(sidebar, ".sidebar-menu-finder-input", function (el) {
      set(el, "background", "rgba(255,255,255,.95)");
      set(el, "border", "1px solid rgba(255,255,255,.36)");
      set(el, "color", cfg.darkInk);
      set(el, "-webkit-text-fill-color", cfg.darkInk);
      set(el, "box-shadow", "inset 0 1px 0 rgba(255,255,255,.95), 0 10px 18px rgba(3,12,22,.16)");
    });

    each(sidebar, ".sidebar-menu-shortcuts a, .sidebar-quick-action", function (el, idx) {
      var first = idx === 0;
      set(el, "background", first ? cfg.active : "rgba(255,255,255,.115)");
      set(el, "border", "1px solid " + (first ? "rgba(255,255,255,.38)" : cfg.line));
      set(el, "border-radius", "14px");
      set(el, "color", first ? "#ffffff" : cfg.ink);
      set(el, "-webkit-text-fill-color", first ? "#ffffff" : cfg.ink);
      set(el, "box-shadow", "0 12px 24px rgba(3,12,22,.20)");
    });
    each(sidebar, ".sidebar-quick-action strong, .sidebar-menu-shortcuts a strong", function (el) {
      set(el, "color", cfg.ink);
      set(el, "-webkit-text-fill-color", cfg.ink);
    });
    each(sidebar, ".sidebar-quick-action i, .sidebar-menu-shortcuts a i", function (el, idx) {
      set(el, "color", idx === 0 ? "#ffffff" : cfg.cyan);
      set(el, "-webkit-text-fill-color", idx === 0 ? "#ffffff" : cfg.cyan);
    });
    each(sidebar, ".sidebar-quick-action:first-child i, .sidebar-menu-shortcuts a:first-child i", function (el) {
      set(el, "color", "#ffffff");
      set(el, "-webkit-text-fill-color", "#ffffff");
    });
    each(sidebar, ".sidebar-quick-action span, .sidebar-menu-shortcuts a span", function (el) {
      set(el, "color", cfg.muted);
      set(el, "-webkit-text-fill-color", cfg.muted);
    });
    each(sidebar, ".sidebar-menu-shortcuts a:first-child strong, .sidebar-menu-shortcuts a:first-child span", function (el) {
      set(el, "color", "#ffffff");
      set(el, "-webkit-text-fill-color", "#ffffff");
    });
    each(sidebar, ".sidebar-orbit a, .sidebar-orbit button, .yk-sidebar-card a, .yk-sidebar-card button", function (el) {
      set(el, "background", "rgba(255,255,255,.10)");
      set(el, "border", "1px solid rgba(255,255,255,.16)");
      set(el, "color", cfg.ink);
      set(el, "-webkit-text-fill-color", cfg.ink);
      set(el, "box-shadow", "0 10px 20px rgba(3,12,22,.14)");
    });
    each(sidebar, ".sidebar-orbit .badge, .yk-sidebar-card .badge, .sidebar-orbit kbd, .yk-sidebar-card kbd", function (el) {
      set(el, "background", "rgba(236,248,255,.82)");
      set(el, "color", cfg.darkInk);
      set(el, "-webkit-text-fill-color", cfg.darkInk);
      set(el, "border", "1px solid rgba(255,255,255,.24)");
    });

    each(sidebar, ".sidebar-section", function (el) {
      if (!textOf(el)) {
        set(el, "display", "none");
        return;
      }
      set(el, "background", "linear-gradient(145deg, rgba(255,255,255,.105) 0%, rgba(255,255,255,.045) 100%)");
      set(el, "border", "1px solid rgba(255,255,255,.14)");
      set(el, "border-top-color", "rgba(110,231,183,.30)");
      set(el, "border-radius", "18px");
      set(el, "box-shadow", "0 16px 34px rgba(3,12,22,.18)");
      set(el, "color", cfg.ink);
    });
    each(sidebar, ".sidebar-section-title", function (el) {
      if (!textOf(el)) {
        set(el, "display", "none");
        return;
      }
      set(el, "color", cfg.muted);
      set(el, "-webkit-text-fill-color", cfg.muted);
      set(el, "background", "rgba(255,255,255,.055)");
      set(el, "border", "1px solid rgba(255,255,255,.10)");
      set(el, "border-left", "3px solid " + cfg.accent);
      set(el, "border-radius", "12px");
      set(el, "padding", "9px 10px");
      set(el, "letter-spacing", "0");
    });

    each(sidebar, ".sidebar-link", function (el) {
      set(el, "background", "rgba(255,255,255,.082)");
      set(el, "border", "1px solid rgba(255,255,255,.12)");
      set(el, "border-radius", "14px");
      set(el, "color", cfg.ink);
      set(el, "-webkit-text-fill-color", cfg.ink);
      set(el, "box-shadow", "0 10px 22px rgba(3,12,22,.12)");
      set(el, "min-height", "48px");
    });
    each(sidebar, ".sidebar-link-icon", function (el, idx) {
      set(el, "background", iconGradients[idx % iconGradients.length]);
      set(el, "border", "1px solid rgba(255,255,255,.18)");
      set(el, "border-radius", "12px");
      set(el, "color", "#ffffff");
      set(el, "-webkit-text-fill-color", "#ffffff");
      set(el, "box-shadow", "0 10px 20px rgba(3,12,22,.18)");
    });

    each(sidebar, ".sidebar-fold", function (el) {
      set(el, "background", "rgba(255,255,255,.055)");
      set(el, "border", "1px solid rgba(255,255,255,.10)");
      set(el, "border-radius", "16px");
      set(el, "padding", "6px");
      set(el, "box-shadow", "inset 0 1px 0 rgba(255,255,255,.08)");
    });
    each(sidebar, ".sidebar-fold summary", function (el) {
      set(el, "background", "rgba(255,255,255,.08)");
      set(el, "border", "1px solid rgba(255,255,255,.10)");
      set(el, "border-radius", "12px");
      set(el, "color", cfg.ink);
      set(el, "-webkit-text-fill-color", cfg.ink);
    });

    markCurrent(sidebar);
    each(sidebar, ".sidebar-link.active, .sidebar-link.yk-d700-current, .sidebar-quick-action.yk-d700-current", function (el) {
      set(el, "background", cfg.active);
      set(el, "border-color", "rgba(255,255,255,.34)");
      set(el, "border-left", "4px solid " + cfg.accent);
      set(el, "color", "#ffffff");
      set(el, "-webkit-text-fill-color", "#ffffff");
      set(el, "box-shadow", "0 16px 30px rgba(8,145,178,.30)");
    });
    each(sidebar, ".sidebar-link.active .sidebar-link-icon, .sidebar-link.yk-d700-current .sidebar-link-icon", function (el) {
      set(el, "background", "rgba(255,255,255,.18)");
      set(el, "color", "#ffffff");
      set(el, "-webkit-text-fill-color", "#ffffff");
      set(el, "border-color", "rgba(255,255,255,.24)");
    });
  }

  function installWrapper() {
    if (!window.setSidebarPalette || window.setSidebarPalette.__ykD500PremiumWrapped) return;
    var original = window.setSidebarPalette;
    window.setSidebarPalette = function () {
      var result = original.apply(this, arguments);
      setTimeout(polish, 0);
      setTimeout(polish, 80);
      return result;
    };
    window.setSidebarPalette.__ykD500PremiumWrapped = true;
  }

  function run() {
    installWrapper();
    polish();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", run, { once: true });
  } else {
    run();
  }
  window.addEventListener("load", function () {
    run();
    setTimeout(run, 120);
    setTimeout(run, 600);
  });
  setTimeout(run, 60);
  setTimeout(run, 350);
  setTimeout(run, 1200);

  try {
    var mo = new MutationObserver(function () {
      clearTimeout(window.__ykD500SidebarPolishTimer);
      window.__ykD500SidebarPolishTimer = setTimeout(run, 40);
    });
    mo.observe(document.documentElement, { attributes: true, childList: true, subtree: true });
  } catch (e) {}
})();

