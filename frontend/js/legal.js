/**
 * Shared behaviour for the standalone public legal pages (privacy.html,
 * terms.html). These pages live OUTSIDE the SPA in index.html — no router,
 * no auth guard, no api-service — so they only need three tiny things:
 *
 *   1. honour the theme the user picked inside the app (localStorage
 *      "ar_theme", the same key js/app.js writes), falling back to the OS
 *      preference via the CSS @media query in css/dashboard.css;
 *   2. wire the header theme toggle so the pages feel like the rest of the app;
 *   3. fill in the footer year.
 *
 * Loaded with a plain <script src> (CSP: script-src 'self') — no inline JS.
 */
(function () {
  "use strict";

  function readSavedTheme() {
    try {
      var v = localStorage.getItem("ar_theme");
      return v === "dark" || v === "light" ? v : null;
    } catch (e) {
      return null;
    }
  }

  // Apply as early as possible (this file is included in <head>) to minimise
  // any flash before the stylesheet's prefers-color-scheme rules would apply.
  var saved = readSavedTheme();
  if (saved) document.documentElement.dataset.theme = saved;

  function currentTheme() {
    return (
      document.documentElement.dataset.theme ||
      (window.matchMedia &&
      window.matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light")
    );
  }

  function syncToggleIcon() {
    var sun = document.getElementById("theme-icon-sun");
    var moon = document.getElementById("theme-icon-moon");
    if (!sun || !moon) return;
    var isDark = currentTheme() === "dark";
    sun.hidden = isDark;
    moon.hidden = !isDark;
  }

  document.addEventListener("DOMContentLoaded", function () {
    var toggle = document.getElementById("theme-toggle");
    if (toggle) {
      toggle.addEventListener("click", function () {
        var next = currentTheme() === "dark" ? "light" : "dark";
        document.documentElement.dataset.theme = next;
        try {
          localStorage.setItem("ar_theme", next);
        } catch (e) {
          /* storage unavailable — the toggle still works for this page view */
        }
        syncToggleIcon();
      });
    }
    syncToggleIcon();

    var yearEl = document.getElementById("legal-year");
    if (yearEl) yearEl.textContent = String(new Date().getFullYear());
  });
})();
