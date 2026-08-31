/**
 * AI Receptionist dashboard — app shell, routing, and page rendering.
 *
 * Phase 4 redesign: every page renders ONLY real backend data (through
 * `Api` in js/api-service.js). There is no mock/preview data anywhere —
 * pages with no rows show a professional empty state instead. The former
 * Automations / Integrations preview pages were removed; Doctors and
 * Services are now real pages backed by
 * PUT /workspaces/{id}/clinic-settings (see `ClinicConfig`).
 */
(() => {
  "use strict";

  // ---------------------------------------------------------------------------
  // Icons (minimal inline SVG, stroke style, reused across sidebar/cards)
  // ---------------------------------------------------------------------------
  const ICONS = {
    overview: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/></svg>',
    liveCalls: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 16.9v3a2 2 0 01-2.2 2 19.8 19.8 0 01-8.6-3.1 19.5 19.5 0 01-6-6A19.8 19.8 0 012.1 4.2 2 2 0 014.1 2h3a2 2 0 012 1.7c.1.9.3 1.8.6 2.7a2 2 0 01-.5 2.1L8 9.7a16 16 0 006 6l1.2-1.2a2 2 0 012.1-.5c.9.3 1.8.5 2.7.6a2 2 0 011.7 2z"/></svg>',
    leads: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M16 21v-2a4 4 0 00-4-4H6a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75"/></svg>',
    patients: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>',
    appointments: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/></svg>',
    callHistory: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 3v5h5M3.05 13a9 9 0 106.4-8.36"/><path d="M12 7v5l4 2"/></svg>',
    ai: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="4" y="7" width="16" height="12" rx="3"/><path d="M9 22h6M9 3l1.5 4M15 3l-1.5 4"/><circle cx="9" cy="13" r="1.2" fill="currentColor" stroke="none"/><circle cx="15" cy="13" r="1.2" fill="currentColor" stroke="none"/></svg>',
    analytics: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 3v18h18"/><path d="M7 15l4-5 3 3 5-7"/></svg>',
    team: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75"/></svg>',
    settings: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 11-2.83 2.83l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 11-2.83-2.83l.06-.06A1.65 1.65 0 005 15a1.65 1.65 0 00-1.51-1H3.4a2 2 0 010-4h.09A1.65 1.65 0 005 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 112.83-2.83l.06.06A1.65 1.65 0 009 5a1.65 1.65 0 001-1.51V3.4a2 2 0 014 0v.09A1.65 1.65 0 0015 5a1.65 1.65 0 001.82-.33l.06-.06a2 2 0 112.83 2.83l-.06.06A1.65 1.65 0 0019.4 9c.3.14.63.22 1.51.22H21a2 2 0 010 4h-.09A1.65 1.65 0 0019.4 15z"/></svg>',
    check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M20 6L9 17l-5-5"/></svg>',
    warn: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.3 3.9L1.8 18a2 2 0 001.7 3h17a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z"/><path d="M12 9v4M12 17h.01"/></svg>',
    x: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg>',
    info: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/></svg>',
    search: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/></svg>',
    inbox: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.45 5.11L2 12v6a2 2 0 002 2h16a2 2 0 002-2v-6l-3.45-6.89A2 2 0 0016.76 4H7.24a2 2 0 00-1.79 1.11z"/></svg>',
    refresh: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M23 4v6h-6M1 20v-6h6"/><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/></svg>',
    transfer: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 1l4 4-4 4M3 11V9a4 4 0 014-4h14M7 23l-4-4 4-4M21 13v2a4 4 0 01-4 4H3"/></svg>',
    cancel: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M15 9l-6 6M9 9l6 6"/></svg>',
    plus: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14"/></svg>',
    doctor: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M8 2v4a4 4 0 008 0V2"/><path d="M6 6a6 6 0 0012 0"/><path d="M12 12v3a6 6 0 006 6 3 3 0 003-3v-1"/><circle cx="20" cy="10" r="2"/></svg>',
    service: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2l2.4 4.9 5.4.8-3.9 3.8.9 5.4L12 14.3 7.2 16.7l.9-5.4L4.2 7.7l5.4-.8z"/></svg>',
    edit: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 013 3L7 19l-4 1 1-4z"/></svg>',
    trash: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6"/></svg>',
    branches: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 21h18M5 21V7l7-4 7 4v14"/><path d="M9 21v-6h6v6M9 9h.01M15 9h.01M9 12h.01M15 12h.01"/></svg>',
  };

  // Navigation is grouped and maps ONLY to real backend-backed pages.
  // (The former Automations / Integrations pages were preview-only mock data
  //  and have been removed — Phase 4.)
  const NAV_GROUPS = [
    { label: null, items: [
      { id: "overview", label: "Dashboard", icon: ICONS.overview },
      { id: "appointments", label: "Appointments", icon: ICONS.appointments },
      { id: "patients", label: "Patients", icon: ICONS.patients },
      { id: "leads", label: "Leads", icon: ICONS.leads },
    ] },
    { label: "AI Receptionist", items: [
      { id: "ai-receptionist", label: "AI Agent", icon: ICONS.ai },
      { id: "live-calls", label: "Live Calls", icon: ICONS.liveCalls },
      { id: "call-history", label: "Call History", icon: ICONS.callHistory },
      { id: "analytics", label: "Analytics", icon: ICONS.analytics },
    ] },
    { label: "Configuration", items: [
      { id: "branches", label: "Branches", icon: ICONS.branches },
      { id: "doctors", label: "Doctors", icon: ICONS.doctor },
      { id: "services", label: "Services", icon: ICONS.service },
      { id: "team", label: "Team", icon: ICONS.team },
      { id: "settings", label: "Settings", icon: ICONS.settings },
    ] },
  ];
  // Flat lookup used by the router (page title, fallback checks).
  const PAGE_META = NAV_GROUPS.flatMap((g) => g.items);

  const ROLE_LABELS = { owner: "Owner", admin: "Admin", receptionist: "Receptionist", analyst: "Analyst", super_admin: "Super Admin" };
  function roleLabel(role) { return ROLE_LABELS[role] || (role ? role[0].toUpperCase() + role.slice(1) : "Receptionist"); }

  const state = {
    user: null,
    memberships: [],
    workspaces: [],   // every workspace (branch) the user belongs to
    workspace: null,  // the currently active one (may be null before selection)
    currentPage: "overview",
    cache: {}, // per-page fetched-data cache, invalidated on manual refresh
    // Bumped every time the active workspace changes. Any async load captures
    // it before awaiting and drops its result (no cache write, no render) if
    // the epoch moved while the request was in flight — so a slow Workspace A
    // response can never land in Workspace B's view. See loadInto().
    wsEpoch: 0,
  };

  // ---------------------------------------------------------------------------
  // Utilities
  // ---------------------------------------------------------------------------
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  function el(html) { const t = document.createElement("template"); t.innerHTML = html.trim(); return t.content.firstElementChild; }
  function escapeHtml(str) {
    return String(str ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
  function initials(name) {
    if (!name) return "?";
    const parts = name.trim().split(/\s+/);
    return ((parts[0]?.[0] || "") + (parts[1]?.[0] || "")).toUpperCase() || "?";
  }
  // All date/time rendering is done IN THE ORGANISATION'S SAVED TIMEZONE
  // (workspaces.timezone), not the browser's — see clinicTz(). Intl applies
  // the right DST offset for each instant automatically.
  function fmtDate(d, opts) {
    return TZ.formatDate(d, clinicTz(), opts || { month: "short", day: "numeric", year: "numeric" });
  }
  function fmtTime(d) {
    return TZ.formatTime(d, clinicTz(), { hour: "numeric", minute: "2-digit" });
  }
  function fmtDateTime(d) { return TZ.formatDateTime(d, clinicTz()); }
  function timeAgo(d) {
    if (!d) return "—";
    const date = d instanceof Date ? d : new Date(d);
    const sec = Math.max(0, Math.floor((Date.now() - date.getTime()) / 1000));
    if (sec < 60) return "just now";
    if (sec < 3600) return `${Math.floor(sec / 60)}m ago`;
    if (sec < 86400) return `${Math.floor(sec / 3600)}h ago`;
    return `${Math.floor(sec / 86400)}d ago`;
  }
  function fmtPct(n) { return `${n >= 0 ? "+" : ""}${Math.round(n * 100)}%`; }
  function debounce(fn, ms) { let t; return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); }; }

  // ---------------------------------------------------------------------------
  // Organisation timezone. The worldwide IANA list, labelling, search and the
  // picker component all live in js/timezone.js (window.TZ). This is just the
  // resolver every formatter/scheduler in this file goes through:
  //   saved workspace timezone  ->  browser-detected  ->  UTC
  // ---------------------------------------------------------------------------
  function clinicTz() {
    const saved = state.workspace && state.workspace.timezone;
    if (saved && window.TZ && TZ.isValid(saved)) return saved;
    return (window.TZ && TZ.detect()) || "UTC";
  }
  function tzChipHtml() {
    const tz = clinicTz();
    return `<span class="tz-chip" title="${escapeHtml(tz)}">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>
      <span>Times shown in <strong>${escapeHtml(TZ.cityLabel(tz))}</strong> (${escapeHtml(TZ.offsetLabel(tz))})</span>
    </span>`;
  }

  // ---------------------------------------------------------------------------
  // Theme
  // ---------------------------------------------------------------------------
  function initTheme() {
    const saved = localStorage.getItem("ar_theme");
    if (saved) document.documentElement.dataset.theme = saved;
    updateThemeIcon();
    $("#theme-toggle").addEventListener("click", () => {
      const current = document.documentElement.dataset.theme ||
        (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
      const next = current === "dark" ? "light" : "dark";
      document.documentElement.dataset.theme = next;
      localStorage.setItem("ar_theme", next);
      updateThemeIcon();
    });
  }
  function updateThemeIcon() {
    const current = document.documentElement.dataset.theme ||
      (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    const icon = $("#theme-icon");
    icon.innerHTML = current === "dark"
      ? '<path d="M21 12.8A9 9 0 1111.2 3a7 7 0 009.8 9.8z"/>'
      : '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>';
  }

  // ---------------------------------------------------------------------------
  // Toasts
  // ---------------------------------------------------------------------------
  function toast({ title, text, tone = "info", duration = 4200 }) {
    const root = $("#toast-root");
    const iconMap = { success: ICONS.check, error: ICONS.x, warning: ICONS.warn, info: ICONS.info };
    const toneClass = tone === "success" ? "toast--success" : tone === "error" ? "toast--error" : tone === "warning" ? "toast--warning" : "";
    const node = el(`
      <div class="toast ${toneClass}">
        <span class="toast__icon tone-${tone === "info" ? "brand" : tone}">${iconMap[tone] || ICONS.info}</span>
        <div>
          <div class="toast__title">${escapeHtml(title)}</div>
          ${text ? `<div class="toast__text">${escapeHtml(text)}</div>` : ""}
        </div>
        <button class="toast__close">${ICONS.x}</button>
      </div>`);
    root.appendChild(node);
    const remove = () => { node.classList.add("is-leaving"); setTimeout(() => node.remove(), 220); };
    node.querySelector(".toast__close").addEventListener("click", remove);
    if (duration) setTimeout(remove, duration);
  }

  // ---------------------------------------------------------------------------
  // Modal
  // ---------------------------------------------------------------------------
  let modalReturnFocus = null;
  function modalFocusables() {
    return $$('a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])', $("#modal"))
      .filter((el) => el.offsetParent !== null);
  }
  function modalKeydown(e) {
    if (!$("#modal-backdrop").classList.contains("is-open")) return;
    if (e.key !== "Tab") return;
    const f = modalFocusables();
    if (!f.length) return;
    const first = f[0], last = f[f.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  }

  function openModal({ title, bodyHtml, footerHtml, wide = false, onMount }) {
    const backdrop = $("#modal-backdrop");
    const modal = $("#modal");
    modalReturnFocus = document.activeElement;
    modal.classList.toggle("modal--wide", wide);
    modal.setAttribute("aria-labelledby", "modal-title");
    modal.innerHTML = `
      <div class="modal__header">
        <h2 class="modal__title" id="modal-title">${escapeHtml(title)}</h2>
        <button class="icon-btn modal__close" id="modal-close-btn" aria-label="Close dialog" title="Close">${ICONS.x}</button>
      </div>
      <div class="modal__body">${bodyHtml}</div>
      ${footerHtml ? `<div class="modal__footer">${footerHtml}</div>` : ""}
    `;
    backdrop.classList.add("is-open");
    $("#modal-close-btn").addEventListener("click", closeModal);
    document.addEventListener("keydown", modalKeydown, true);
    if (onMount) onMount(modal);
    // Focus the first real field (fall back to the close button).
    const f = modalFocusables();
    const target = f.find((el) => el.id !== "modal-close-btn") || f[0];
    if (target) setTimeout(() => target.focus(), 30);
  }
  function closeModal() {
    const backdrop = $("#modal-backdrop");
    if (!backdrop.classList.contains("is-open")) return;
    backdrop.classList.remove("is-open");
    document.removeEventListener("keydown", modalKeydown, true);
    if (modalReturnFocus && typeof modalReturnFocus.focus === "function") {
      try { modalReturnFocus.focus(); } catch { /* element gone */ }
    }
    modalReturnFocus = null;
  }
  $("#modal-backdrop") && $("#modal-backdrop").addEventListener("click", (e) => { if (e.target.id === "modal-backdrop") closeModal(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") { closeModal(); closeAllDropdowns(); } });

  // Small reusable confirm dialog (built on openModal) — used before a
  // destructive, immediately-persisted action.
  function confirmModal({ title = "Are you sure?", message = "", confirmLabel = "Delete", onConfirm }) {
    openModal({
      title,
      bodyHtml: `<p style="margin:0;font-size:13.5px;color:var(--text-muted);">${escapeHtml(message)}</p>`,
      footerHtml: `<button class="btn btn--secondary" id="cf-cancel">Cancel</button><button class="btn btn--danger" id="cf-ok"><span class="spinner"></span><span class="btn__label">${escapeHtml(confirmLabel)}</span></button>`,
      onMount: () => {
        $("#cf-cancel").addEventListener("click", closeModal);
        $("#cf-ok").addEventListener("click", async () => {
          const btn = $("#cf-ok"); btn.classList.add("is-loading"); btn.disabled = true;
          // onConfirm surfaces its own success/error toasts and closes the
          // modal on success; here we just guarantee the button is restored.
          try { await onConfirm(); } catch { /* already reported by onConfirm */ }
          finally { btn.classList.remove("is-loading"); btn.disabled = false; }
        });
      },
    });
  }

  function closeAllDropdowns() { $$(".dropdown.is-open").forEach((d) => d.classList.remove("is-open")); }

  // ---------------------------------------------------------------------------
  // State-block renderers (loading / empty / error) — shared by every page
  // ---------------------------------------------------------------------------
  function skeletonRows(n = 5, cols = 5) {
    return `<div>${Array.from({ length: n }).map(() => `
      <div class="skeleton-row">
        ${Array.from({ length: cols }).map((_, i) => `<div class="skeleton skeleton-line" style="width:${i === 0 ? "22%" : "14%"}"></div>`).join("")}
      </div>`).join("")}</div>`;
  }
  function skeletonCards(n = 4) {
    return `<div class="grid grid--kpi">${Array.from({ length: n }).map(() => `
      <div class="card skeleton-block"><div class="skeleton skeleton-line" style="width:38px;height:38px;border-radius:10px;margin-bottom:16px;"></div>
      <div class="skeleton skeleton-line" style="width:60%;height:22px;margin-bottom:8px;"></div>
      <div class="skeleton skeleton-line" style="width:80%;"></div></div>`).join("")}</div>`;
  }
  function emptyState({ icon = ICONS.inbox, title = "Nothing here yet", text = "", actionHtml = "" }) {
    return `<div class="state-block">
      <div class="state-block__icon tone-brand">${icon}</div>
      <div class="state-block__title">${escapeHtml(title)}</div>
      <div class="state-block__text">${escapeHtml(text)}</div>
      ${actionHtml ? `<div class="state-block__actions">${actionHtml}</div>` : ""}
    </div>`;
  }
  function errorState({ message = "Something went wrong.", retryId }) {
    return `<div class="state-block">
      <div class="state-block__icon tone-danger">${ICONS.warn}</div>
      <div class="state-block__title">Couldn't load this</div>
      <div class="state-block__text">${escapeHtml(message)}</div>
      <div class="state-block__actions">
        <button class="btn btn--secondary btn--sm" id="${retryId}">${ICONS.refresh} Retry</button>
      </div>
    </div>`;
  }

  /**
   * Generic async loader: shows a skeleton, runs `fetcher()`, then renders
   * via `render(data)` — or the shared empty/error state on failure. Every
   * connected page (leads, patients, appointments, calls, team) goes
   * through this so loading/empty/error handling is consistent and DRY.
   */
  async function loadInto(container, { skeleton, fetcher, render, emptyCheck, emptyProps, cacheKey }) {
    container.innerHTML = skeleton;
    const epoch = state.wsEpoch;
    try {
      let data;
      if (cacheKey && state.cache[cacheKey]) {
        data = state.cache[cacheKey];
      } else {
        data = await fetcher();
        // The active workspace changed while this request was in flight — the
        // data belongs to the previous workspace. Discard it entirely.
        if (epoch !== state.wsEpoch) return;
        if (cacheKey) state.cache[cacheKey] = data;
      }
      if (emptyCheck && emptyCheck(data)) {
        container.innerHTML = emptyState(emptyProps || {});
        return;
      }
      render(data, container);
    } catch (err) {
      const message = err instanceof Api.ApiError ? err.message : "Unexpected error while loading data.";
      container.innerHTML = errorState({ message, retryId: "retry-btn" });
      const retryBtn = $("#retry-btn", container);
      if (retryBtn) retryBtn.addEventListener("click", () => {
        if (cacheKey) delete state.cache[cacheKey];
        loadInto(container, { skeleton, fetcher, render, emptyCheck, emptyProps, cacheKey });
      });
    }
  }

  function badge(text, tone) { return `<span class="badge tone-${tone}">${escapeHtml(text)}</span>`; }

  const STATUS_TONE = {
    scheduled: "brand", completed: "success", cancelled: "danger", no_show: "warning",
    new: "info", qualifying: "warning", converted: "success", lost: "danger",
    connected: "success", mock: "warning", not_connected: "muted", error: "danger",
    active: "success", invited: "warning", suspended: "danger",
    in_progress: "brand", transferring: "warning",
    sent: "success", failed: "danger", pending: "warning", transferred: "success",
    booked: "success", rescheduled: "info", transferred_outcome: "warning", missed: "danger", voicemail: "muted", info_only: "info",
  };
  // `Call.status` (backend/app/models/call.py) is a free-form string, not an
  // enum — this only prettifies the values the pipeline actually sets.
  function callStatusLabel(status) {
    const known = { in_progress: "In progress", ringing: "Ringing", transferring: "Transferring", queued: "Queued" };
    if (known[status]) return known[status];
    return String(status || "In progress").replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
  }

  // ---------------------------------------------------------------------------
  // Demo note (pages without a real backend endpoint yet)
  // ---------------------------------------------------------------------------
  function demoNote(text) {
    return `<div class="demo-note">${ICONS.info}<span>${escapeHtml(text)}</span></div>`;
  }

  // ===========================================================================
  // PAGE: Overview
  // ===========================================================================
  async function renderOverview(container) {
    const clinicName = state.workspace?.name;
    container.innerHTML = `
      <div class="page-header">
        <div><div class="page-header__title">Good ${greeting()}, ${escapeHtml(firstName())}</div>
        <div class="page-header__subtitle">Here's what's happening${clinicName ? ` at ${escapeHtml(clinicName)}` : ""} today.</div></div>
        <div class="page-header__actions">${tzChipHtml()}<button class="btn btn--secondary btn--sm" id="ov-refresh">${ICONS.refresh} Refresh</button></div>
      </div>
      <div id="ov-body"></div>`;
    $("#ov-refresh").addEventListener("click", () => { delete state.cache.overview; renderOverview(container); });

    const body = $("#ov-body");
    await loadInto(body, {
      skeleton: skeletonCards(5),
      cacheKey: "overview",
      fetcher: async () => {
        const [calls, appointments, leads, clinic] = await Promise.allSettled([
          Api.calls.list(), Api.appointments.list(), Api.leads.list(), ClinicConfig.get(),
        ]);
        // Only a total wash-out is treated as an error; a single failing
        // resource degrades to an empty section, never to fake data.
        if (calls.status !== "fulfilled" && appointments.status !== "fulfilled" && leads.status !== "fulfilled") {
          throw (calls.reason || appointments.reason || leads.reason || new Error("Couldn't load overview data."));
        }
        return {
          calls: calls.status === "fulfilled" ? calls.value : [],
          appointments: appointments.status === "fulfilled" ? appointments.value : [],
          leads: leads.status === "fulfilled" ? leads.value : [],
          clinic: clinic.status === "fulfilled" ? clinic.value : null,
        };
      },
      render: (data, root) => {
        const calls = data.calls || [];
        const appts = data.appointments || [];
        const leadsList = data.leads || [];
        const cs = data.clinic;
        const today = new Date();
        const callsToday = calls.filter((c) => c.started_at && sameDay(new Date(c.started_at), today));
        const answered = callsToday.filter((c) => c.status !== "missed" && c.status !== "no_answer");
        const apptsToday = appts
          .filter((a) => a.start_time && sameDay(new Date(a.start_time), today))
          .sort((a, b) => new Date(a.start_time) - new Date(b.start_time));
        const newLeads = leadsList.filter((l) => l.status === "new");
        const avgDur = callsToday.length
          ? Math.round(callsToday.reduce((s, c) => s + (c.duration_seconds || 0), 0) / callsToday.length) : 0;
        const ready = clinicConfigComplete(cs);

        root.innerHTML = `
          <div class="grid grid--kpi">
            ${kpiCard({ icon: ICONS.liveCalls, tone: "brand", label: "Calls today", value: callsToday.length, delta: null, spark: sparkFrom(callsToday.length) })}
            ${kpiCard({ icon: ICONS.check, tone: "success", label: "Answered calls", value: answered.length, delta: null, spark: sparkFrom(answered.length) })}
            ${kpiCard({ icon: ICONS.callHistory, tone: "info", label: "Avg. call duration", value: avgDur ? fmtDurationShort(avgDur) : "—", delta: null, spark: sparkFrom(avgDur) })}
            ${kpiCard({ icon: ICONS.appointments, tone: "brand", label: "Appointments today", value: apptsToday.length, delta: null, spark: sparkFrom(apptsToday.length) })}
            ${kpiCard({ icon: ICONS.leads, tone: "warning", label: "New leads", value: newLeads.length, delta: null, spark: sparkFrom(newLeads.length) })}
          </div>

          <div class="grid grid--2">
            <div class="card">
              <div class="card__head"><div class="card__title">Today's schedule</div><a href="#/appointments" class="btn btn--ghost btn--sm">View all</a></div>
              ${apptsToday.length
                ? `<div class="mini-list">${apptsToday.slice(0, 8).map((a) => `
                    <div class="mini-list__row">
                      <span class="mini-list__time">${escapeHtml(fmtTime(a.start_time))}</span>
                      <span class="mini-list__main">${badge((a.status || "scheduled").replace(/_/g, " "), STATUS_TONE[a.status] || "muted")}
                        <span class="mini-list__sub">${a.notes ? escapeHtml(a.notes) : "Appointment"}</span></span>
                    </div>`).join("")}</div>`
                : emptyState({ icon: ICONS.appointments, title: "No appointments today", text: "New bookings made by the AI agent or staff show up here." })}
            </div>
            <div class="card">
              <div class="card__head"><div class="card__title">AI agent</div><a href="#/ai-receptionist" class="btn btn--ghost btn--sm">Open</a></div>
              ${cs
                ? `<div style="display:flex;flex-direction:column;gap:12px;">
                    <span class="status-pill ${ready ? "status-pill--ok" : "status-pill--warn"}"><span class="status-pill__dot"></span>${ready ? "Active — ready for calls" : "Setup incomplete"}</span>
                    <dl class="def-list">
                      <dt>Doctors</dt><dd>${(cs.doctors || []).length}</dd>
                      <dt>Services</dt><dd>${(cs.services || []).length}</dd>
                      <dt>Tone</dt><dd>${escapeHtml(cs.agent_tone || "Professional")}</dd>
                      <dt>Language</dt><dd>${escapeHtml(cs.preferred_language || "English")}</dd>
                    </dl>
                  </div>`
                : emptyState({ icon: ICONS.ai, title: "Agent config unavailable", text: "Couldn't load the AI knowledge base right now." })}
            </div>
          </div>

          <div class="grid grid--2" style="margin-top:18px;">
            <div class="card">
              <div class="card__head">
                <div><div class="card__title">Call volume — last 7 days</div><div class="card__subtitle">Calls the AI agent handled each day</div></div>
              </div>
              ${calls.length
                ? `<div style="height:220px;">${Charts.lineChart(callVolumeSeries(calls), { valueKey: "calls" })}</div>
                   <div class="chart-legend"><span class="chart-legend__item"><span class="chart-legend__dot" style="background:var(--chart-1)"></span>Total calls</span></div>`
                : emptyState({ icon: ICONS.callHistory, title: "No calls yet", text: "Call volume shows here once the AI agent starts taking calls." })}
            </div>
            <div class="card">
              <div class="card__head"><div class="card__title">Call outcomes</div></div>
              ${calls.length
                ? (() => { const seg = callOutcomeSegments(calls); return `
                    <div style="height:180px;display:flex;justify-content:center;">${Charts.donutChart(seg)}</div>
                    <div class="chart-legend">${seg.map((d) => `<span class="chart-legend__item"><span class="chart-legend__dot" style="background:${d.color}"></span>${escapeHtml(d.label)}</span>`).join("")}</div>`; })()
                : emptyState({ icon: ICONS.analytics, title: "Nothing to break down yet", text: "Outcomes appear once calls have been handled." })}
            </div>
          </div>

          <div class="grid grid--2" style="margin-top:18px;">
            <div class="card">
              <div class="card__head"><div class="card__title">Recent activity</div></div>
              ${recentActivityHtml(calls, appts, leadsList)}
            </div>
            <div class="card">
              <div class="card__head"><div class="card__title">Upcoming appointments</div><a href="#/appointments" class="btn btn--ghost btn--sm">View all</a></div>
              ${renderUpcomingList(appts)}
            </div>
          </div>`;
      },
    });
  }

  // Overview helpers — every series below is derived purely from the real
  // API payloads (calls / appointments / leads). No fixture data.
  function last7DayKeys() {
    // The 7 calendar days ending "today at the clinic". Buckets are keyed by
    // the clinic-timezone date so a call just before local midnight lands on
    // the right day regardless of the viewer's own timezone.
    const [Y, M, D] = TZ.todayYmd(clinicTz()).split("-").map(Number);
    const keys = [];
    for (let i = 6; i >= 0; i--) {
      const anchor = new Date(Date.UTC(Y, M - 1, D - i, 12, 0, 0)); // noon UTC dodges DST edges
      const ymd = `${anchor.getUTCFullYear()}-${String(anchor.getUTCMonth() + 1).padStart(2, "0")}-${String(anchor.getUTCDate()).padStart(2, "0")}`;
      keys.push({ label: TZ.weekdayShort(anchor, "UTC"), ymd });
    }
    return keys;
  }
  function callVolumeSeries(calls) {
    const tz = clinicTz();
    const days = last7DayKeys();
    const buckets = Object.fromEntries(days.map((k) => [k.ymd, 0]));
    calls.forEach((c) => {
      const when = c.started_at || c.created_at;
      if (!when) return;
      const ymd = TZ.ymd(when, tz);
      if (ymd in buckets) buckets[ymd] += 1;
    });
    return days.map((k) => ({ label: k.label, calls: buckets[k.ymd] }));
  }
  const OUTCOME_COLORS = {
    completed: "#10b981", scheduled: "#6366f1", in_progress: "#6366f1", booked: "#10b981",
    transferred: "#f59e0b", transferring: "#f59e0b", cancelled: "#ef4444", missed: "#94a3b8",
    no_answer: "#94a3b8", voicemail: "#94a3b8", failed: "#ef4444",
  };
  function callOutcomeSegments(calls) {
    const counts = {};
    calls.forEach((c) => { const s = c.status || "unknown"; counts[s] = (counts[s] || 0) + 1; });
    return Object.entries(counts)
      .sort((a, b) => b[1] - a[1])
      .map(([status, value]) => ({
        label: status.replace(/_/g, " ").replace(/^\w/, (m) => m.toUpperCase()),
        value,
        color: OUTCOME_COLORS[status] || "#94a3b8",
      }));
  }
  function recentActivityHtml(calls, appts, leads) {
    const items = [];
    calls.forEach((c) => items.push({
      when: new Date(c.started_at || c.created_at || 0),
      icon: c.status === "transferred" ? "transfer" : "callHistory",
      tone: c.status === "transferred" ? "warning" : c.status === "missed" ? "danger" : "info",
      text: `${c.direction === "outbound" ? "Outbound" : "Inbound"} call ${escapeHtml((c.status || "").replace(/_/g, " ") || "handled")}${c.from_number ? ` — ${escapeHtml(c.from_number)}` : ""}`,
    }));
    appts.forEach((a) => items.push({
      when: new Date(a.created_at || a.start_time || 0),
      icon: "appointments", tone: a.status === "cancelled" ? "danger" : "success",
      text: `Appointment ${escapeHtml((a.status || "scheduled").replace(/_/g, " "))} for ${fmtDateTime(a.start_time)}`,
    }));
    leads.forEach((l) => items.push({
      when: new Date(l.created_at || 0),
      icon: "leads", tone: "info",
      text: `Lead ${escapeHtml(l.status || "new")}${l.name ? `: ${escapeHtml(l.name)}` : ""}`,
    }));
    const rows = items.filter((i) => !isNaN(i.when)).sort((a, b) => b.when - a.when).slice(0, 6);
    if (!rows.length) return emptyState({ title: "No recent activity", text: "Calls, bookings and leads will show up here as they happen." });
    return `<div class="timeline">${rows.map((a) => `
      <div class="timeline-item">
        <div class="timeline-item__icon tone-${a.tone}">${ICONS[a.icon] || ICONS.info}</div>
        <div><div class="timeline-item__text">${a.text}</div><div class="timeline-item__time">${escapeHtml(timeAgo(a.when))}</div></div>
      </div>`).join("")}</div>`;
  }

  function renderUpcomingList(appts) {
    const upcoming = appts
      .map(normalizeAppointment)
      .filter((a) => a.start > new Date() && a.status === "scheduled")
      .sort((a, b) => a.start - b.start)
      .slice(0, 5);
    if (!upcoming.length) return emptyState({ title: "No upcoming appointments", text: "New bookings will show up here." });
    return `<div class="timeline">${upcoming.map((a) => `
      <div class="timeline-item">
        <div class="timeline-item__icon tone-brand">${ICONS.appointments}</div>
        <div><div class="timeline-item__text"><strong>${escapeHtml(a.patient)}</strong> — ${escapeHtml(a.service)}</div>
        <div class="timeline-item__time">${fmtDateTime(a.start)}${a.provider ? " · " + escapeHtml(a.provider) : ""}</div></div>
      </div>`).join("")}</div>`;
  }

  function kpiCard({ icon, tone, label, value, delta, spark }) {
    const up = delta >= 0;
    const deltaHtml = delta === null || delta === undefined
      ? ""
      : `<div class="kpi-card__delta kpi-card__delta--${up ? "up" : "down"}">${up ? "▲" : "▼"} ${fmtPct(delta)}</div>`;
    return `<div class="card kpi-card card--hover">
      <div class="kpi-card__icon tone-${tone}">${icon}</div>
      <div class="kpi-card__value">${value}</div>
      <div class="kpi-card__label">${escapeHtml(label)}</div>
      ${deltaHtml}
      <div class="kpi-card__spark">${Charts.sparkline(spark, { color: up ? "var(--success)" : "var(--danger)" })}</div>
    </div>`;
  }

  function greeting() { const h = TZ.hourInTz(clinicTz()); return h < 12 ? "morning" : h < 18 ? "afternoon" : "evening"; }
  function firstName() { return (state.user?.full_name || "there").split(" ")[0]; }
  // Calendar-day equality evaluated in the organisation's timezone, so
  // "today" on the dashboard means today at the clinic, not in the browser.
  function sameDay(a, b) { return TZ.sameDay(a, b, clinicTz()); }
  function fmtDurationShort(sec) { const m = Math.floor(sec / 60), s = sec % 60; return `${m}:${String(s).padStart(2, "0")}`; }

  function normalizeAppointment(a) {
    // Accepts either a real AppointmentOut (snake_case) or mock shape (already normalized).
    if (a.start instanceof Date) return a;
    return {
      id: a.id, patient: a.patient_name || a.patient || "Unknown patient",
      service: a.service_name || a.service || "Appointment",
      provider: a.provider_name || (a.provider && a.provider.name) || a.provider || "",
      start: new Date(a.start_time || a.start), status: a.status, notes: a.notes,
    };
  }

  // ===========================================================================
  // PAGE: Live Calls — real data from GET /calls, filtered to calls still in
  // progress (no `ended_at` yet). There's no REST "live" filter and no
  // WebSocket subscription wired into this dashboard yet, so this is a
  // snapshot as of page load/refresh, not a push-updated feed — call
  // duration timers still tick client-side between refreshes. Only fields
  // that actually exist on the `Call` model are shown (no fabricated
  // caller name / sentiment / intent / language — see backend/app/models/call.py).
  // ===========================================================================
  function renderLiveCalls(container) {
    container.innerHTML = `
      <div class="page-header">
        <div><div class="page-header__title">Live Calls</div><div class="page-header__subtitle">Calls currently in progress.</div></div>
        <div class="page-header__actions"><button class="btn btn--secondary btn--sm" id="lc-refresh">${ICONS.refresh} Refresh</button></div>
      </div>
      ${demoNote("This is a snapshot of in-progress calls, refreshed on demand — the dashboard doesn't yet subscribe to the live telephony WebSocket, so it won't update the instant a call starts or ends.")}
      <div id="live-calls-grid" class="grid grid--auto"></div>`;

    const grid = $("#live-calls-grid");
    let timer = null;
    const epoch = state.wsEpoch;
    onPageLeave(() => { if (timer) { clearInterval(timer); timer = null; } });

    $("#lc-refresh").addEventListener("click", load);
    load();

    async function load() {
      if (timer) { clearInterval(timer); timer = null; }
      grid.innerHTML = skeletonCards(3);
      let calls;
      try {
        calls = await Api.calls.list();
      } catch (err) {
        grid.innerHTML = errorState({ message: err.message, retryId: "lc-retry" });
        $("#lc-retry", grid)?.addEventListener("click", load);
        return;
      }
      if (epoch !== state.wsEpoch) return; // workspace switched mid-request
      const live = calls.filter((c) => !c.ended_at && c.status !== "completed" && c.status !== "cancelled");
      paint(live);
      if (live.length) {
        timer = setInterval(() => tickTimers(live), 1000);
      }
    }

    function paint(live) {
      if (!live.length) {
        grid.innerHTML = emptyState({ icon: ICONS.liveCalls, title: "No active calls", text: "Live calls will appear here the moment someone calls in." });
        return;
      }
      grid.innerHTML = live.map((c) => `
        <div class="card card--hover">
          <div class="card__head">
            <div class="cell-row-flex"><span class="live-pulse"></span><strong>${escapeHtml(c.from_number || "Unknown caller")}</strong></div>
            ${badge(callStatusLabel(c.status), STATUS_TONE[c.status] || "brand")}
          </div>
          <div class="cell-muted" style="margin-bottom:10px;">${escapeHtml(c.direction === "outbound" ? "Outbound" : "Inbound")} · to ${escapeHtml(c.to_number || "—")}</div>
          <div style="display:flex;justify-content:space-between;font-size:12.5px;color:var(--text-muted);margin-bottom:10px;">
            <span>Started ${escapeHtml(timeAgo(c.started_at || c.created_at))}</span>
            <span data-live-timer="${c.id}">${c.started_at ? fmtDurationShort(Math.floor((Date.now() - new Date(c.started_at).getTime()) / 1000)) : "—"}</span>
          </div>
          <div style="display:flex;justify-content:flex-end;">
            <button class="btn btn--secondary btn--sm" data-view="${c.id}">View details</button>
          </div>
        </div>`).join("");
      $$("[data-view]", grid).forEach((btn) => btn.addEventListener("click", () => navigate(`call-history`)));
    }

    function tickTimers(live) {
      if (!document.body.contains(grid)) { clearInterval(timer); timer = null; return; }
      live.forEach((c) => {
        if (!c.started_at) return;
        const node = $(`[data-live-timer="${c.id}"]`, grid);
        if (node) node.textContent = fmtDurationShort(Math.floor((Date.now() - new Date(c.started_at).getTime()) / 1000));
      });
    }
  }

  // ===========================================================================
  // Generic table page factory (Leads / Patients / Team share this shape)
  // ===========================================================================
  function tableToolbar({ searchPlaceholder, filters = [], count, addLabel }) {
    return `
      <div class="table-toolbar">
        <div class="table-toolbar__search">${ICONS.search}<input type="text" id="tbl-search" placeholder="${escapeHtml(searchPlaceholder)}" /></div>
        <div class="table-toolbar__filters">
          ${filters.map((f) => `<select id="filter-${f.key}"><option value="">${escapeHtml(f.label)}: All</option>${f.options.map((o) => `<option value="${o}">${escapeHtml(o)}</option>`).join("")}</select>`).join("")}
        </div>
        <div class="table-toolbar__spacer"></div>
        <span class="table-toolbar__count" id="tbl-count">${count}</span>
        ${addLabel ? `<button class="btn btn--primary btn--sm" id="tbl-add">${ICONS.plus} ${escapeHtml(addLabel)}</button>` : ""}
      </div>`;
  }

  function paginate(rows, page, perPage = 8) {
    const start = (page - 1) * perPage;
    return { pageRows: rows.slice(start, start + perPage), totalPages: Math.max(1, Math.ceil(rows.length / perPage)) };
  }
  function paginationHtml(page, totalPages) {
    if (totalPages <= 1) return "";
    let btns = "";
    for (let i = 1; i <= totalPages; i++) {
      if (i === 1 || i === totalPages || Math.abs(i - page) <= 1) btns += `<button data-page="${i}" class="${i === page ? "is-active" : ""}">${i}</button>`;
      else if (btns.slice(-3) !== "…") btns += `<span style="padding:0 4px;color:var(--text-faint);">…</span>`;
    }
    return `<div class="pagination">${btns}</div>`;
  }

  // ===========================================================================
  // PAGE: Leads
  // ===========================================================================
  function renderLeadsPage(container) {
    container.innerHTML = `
      <div class="page-header">
        <div><div class="page-header__title">Leads</div><div class="page-header__subtitle">Prospective patients captured by the AI Receptionist and other sources.</div></div>
      </div>
      <div class="table-card"><div id="leads-toolbar"></div><div id="leads-body"></div></div>`;

    const body = $("#leads-body");
    let allRows = [], page = 1, search = "", statusFilter = "";

    loadInto(body, {
      skeleton: skeletonRows(6, 5),
      cacheKey: "leads",
      fetcher: () => Api.leads.list(),
      emptyCheck: (d) => d.length === 0,
      emptyProps: { icon: ICONS.leads, title: "No leads yet", text: "Leads captured by the AI Receptionist or web form will appear here.", actionHtml: `<button class="btn btn--primary btn--sm" id="leads-add-empty">${ICONS.plus} Add lead manually</button>` },
      render: (rows) => {
        allRows = rows;
        mountLeadsUI();
      },
    });

    function mountLeadsUI() {
      $("#leads-toolbar").outerHTML = `<div id="leads-toolbar">${tableToolbar({
        searchPlaceholder: "Search leads…", count: `${allRows.length} leads`, addLabel: "Add lead",
        filters: [{ key: "status", label: "Status", options: ["new", "qualifying", "converted", "lost"] }],
      })}</div>`;
      $("#tbl-search").addEventListener("input", debounce((e) => { search = e.target.value.toLowerCase(); page = 1; paint(); }, 200));
      $("#filter-status").addEventListener("change", (e) => { statusFilter = e.target.value; page = 1; paint(); });
      $("#tbl-add").addEventListener("click", openAddLeadModal);
      paint();
    }
    const emptyAddBtn = () => $("#leads-add-empty") && $("#leads-add-empty").addEventListener("click", openAddLeadModal);

    function paint() {
      let rows = allRows.filter((l) => {
        const hay = `${l.name || ""} ${l.phone || ""} ${l.email || ""}`.toLowerCase();
        return (!search || hay.includes(search)) && (!statusFilter || l.status === statusFilter);
      });
      const { pageRows, totalPages } = paginate(rows, page);
      const tableWrap = $("#leads-table-wrap") || el("<div id=\"leads-table-wrap\"></div>");
      if (!tableWrap.parentNode) body.appendChild(tableWrap);

      if (!rows.length) {
        tableWrap.innerHTML = emptyState({ icon: ICONS.search, title: "No matching leads", text: "Try a different search term or filter." });
        return;
      }
      tableWrap.innerHTML = `
        <div class="table-scroll"><table class="data-table">
          <thead><tr><th>Name</th><th>Contact</th><th>Source</th><th>Interest</th><th>Status</th><th>Created</th></tr></thead>
          <tbody>${pageRows.map((l) => `
            <tr>
              <td class="cell-primary">${escapeHtml(l.name || "Unnamed")}</td>
              <td class="cell-muted">${escapeHtml(l.phone || l.email || "—")}</td>
              <td class="cell-muted">${escapeHtml((l.source || "—").replace(/_/g, " "))}</td>
              <td class="cell-muted">${escapeHtml(l.notes || "—")}</td>
              <td>${badge(l.status, STATUS_TONE[l.status] || "muted")}</td>
              <td class="cell-muted">${fmtDate(l.created_at)}</td>
            </tr>`).join("")}</tbody>
        </table></div>
        <div class="table-footer"><span>Page ${page} of ${totalPages}</span>${paginationHtml(page, totalPages)}</div>`;
      $$(".pagination button[data-page]", tableWrap).forEach((b) => b.addEventListener("click", () => { page = Number(b.dataset.page); paint(); }));
    }

    function openAddLeadModal() {
      openModal({
        title: "Add lead",
        bodyHtml: `
          <div class="form-grid">
            <div class="field"><label class="field__label">Full name</label><input class="input" id="f-name" placeholder="Jane Doe" /></div>
            <div class="field"><label class="field__label">Phone</label><input class="input" id="f-phone" placeholder="(415) 555-0100" /></div>
            <div class="field"><label class="field__label">Email</label><input class="input" id="f-email" placeholder="jane@example.com" /></div>
            <div class="field"><label class="field__label">Source</label>
              <select class="select" id="f-source"><option value="website_form">Website form</option><option value="referral">Referral</option><option value="google_ads">Google Ads</option><option value="walk_in">Walk-in</option></select>
            </div>
          </div>
          <div class="field"><label class="field__label">Notes</label><textarea class="textarea" id="f-notes" placeholder="Interested in..."></textarea></div>`,
        footerHtml: `<button class="btn btn--secondary" id="cancel-btn">Cancel</button><button class="btn btn--primary" id="save-btn"><span class="spinner"></span><span class="btn__label">Save lead</span></button>`,
        onMount: () => {
          $("#cancel-btn").addEventListener("click", closeModal);
          $("#save-btn").addEventListener("click", async () => {
            const payload = {
              name: $("#f-name").value.trim() || null,
              phone: $("#f-phone").value.trim() || null,
              email: $("#f-email").value.trim() || null,
              source: $("#f-source").value,
              notes: $("#f-notes").value.trim() || null,
            };
            const btn = $("#save-btn"); btn.classList.add("is-loading"); btn.disabled = true;
            try {
              const created = await Api.leads.create(payload);
              allRows.unshift(created);
              delete state.cache.leads;
              closeModal();
              toast({ title: "Lead added", text: `${payload.name || "New lead"} was saved.`, tone: "success" });
              mountLeadsUI();
            } catch (err) {
              toast({ title: "Couldn't save lead", text: err.message, tone: "error" });
              btn.classList.remove("is-loading"); btn.disabled = false;
            }
          });
        },
      });
    }
    setTimeout(emptyAddBtn, 0);
  }

  // ===========================================================================
  // PAGE: Patients
  // ===========================================================================
  function renderPatientsPage(container) {
    container.innerHTML = `
      <div class="page-header">
        <div><div class="page-header__title">Patients</div><div class="page-header__subtitle">Everyone your clinic has on file.</div></div>
      </div>
      <div class="table-card"><div id="pat-toolbar"></div><div id="pat-body"></div></div>`;

    const body = $("#pat-body");
    let allRows = [], page = 1, search = "";

    loadInto(body, {
      skeleton: skeletonRows(6, 5),
      cacheKey: "patients",
      fetcher: () => Api.patients.list(),
      emptyCheck: (d) => d.length === 0,
      emptyProps: { icon: ICONS.patients, title: "No patients yet", text: "Patients are created automatically the first time they book, or you can add one manually.", actionHtml: `<button class="btn btn--primary btn--sm" id="pat-add-empty">${ICONS.plus} Add patient</button>` },
      render: (rows) => { allRows = rows; mount(); },
    });

    function mount() {
      $("#pat-toolbar").outerHTML = `<div id="pat-toolbar">${tableToolbar({ searchPlaceholder: "Search patients…", count: `${allRows.length} patients`, addLabel: "Add patient" })}</div>`;
      $("#tbl-search").addEventListener("input", debounce((e) => { search = e.target.value.toLowerCase(); page = 1; paint(); }, 200));
      $("#tbl-add").addEventListener("click", openAddModal);
      paint();
      const emptyBtn = $("#pat-add-empty"); if (emptyBtn) emptyBtn.addEventListener("click", openAddModal);
    }

    function paint() {
      const rows = allRows.filter((p) => {
        const name = `${p.first_name} ${p.last_name}`.toLowerCase();
        const hay = `${name} ${p.phone || ""} ${p.email || ""}`.toLowerCase();
        return !search || hay.includes(search);
      });
      const { pageRows, totalPages } = paginate(rows, page);
      let wrap = $("#pat-table-wrap");
      if (!wrap) { wrap = el("<div id=\"pat-table-wrap\"></div>"); body.appendChild(wrap); }
      if (!rows.length) { wrap.innerHTML = emptyState({ icon: ICONS.search, title: "No matching patients", text: "Try a different search term." }); return; }
      wrap.innerHTML = `
        <div class="table-scroll"><table class="data-table">
          <thead><tr><th>Name</th><th>Phone</th><th>Email</th><th>Date of birth</th><th>Notes</th></tr></thead>
          <tbody>${pageRows.map((p) => `
            <tr class="pat-row" data-id="${p.id}">
              <td class="cell-row-flex"><span class="avatar" style="width:28px;height:28px;font-size:10.5px;">${initials(p.first_name + " " + p.last_name)}</span><span class="cell-primary">${escapeHtml(p.first_name)} ${escapeHtml(p.last_name)}</span></td>
              <td class="cell-muted">${escapeHtml(p.phone || "—")}</td>
              <td class="cell-muted">${escapeHtml(p.email || "—")}</td>
              <td class="cell-muted">${p.date_of_birth ? fmtDate(p.date_of_birth) : "—"}</td>
              <td class="cell-muted">${escapeHtml(p.notes || "—")}</td>
            </tr>`).join("")}</tbody>
        </table></div>
        <div class="table-footer"><span>Page ${page} of ${totalPages}</span>${paginationHtml(page, totalPages)}</div>`;
      $$(".pagination button[data-page]", wrap).forEach((b) => b.addEventListener("click", () => { page = Number(b.dataset.page); paint(); }));
      $$(".pat-row", wrap).forEach((r) => r.addEventListener("click", () => openDetail(allRows.find((p) => p.id === r.dataset.id))));
    }

    function openDetail(p) {
      openModal({
        title: `${p.first_name} ${p.last_name}`,
        bodyHtml: `
          <div class="grid" style="grid-template-columns:1fr 1fr;gap:12px;">
            <div><div class="field__label">Phone</div><div class="cell-primary">${escapeHtml(p.phone || "—")}</div></div>
            <div><div class="field__label">Email</div><div class="cell-primary">${escapeHtml(p.email || "—")}</div></div>
            <div><div class="field__label">Date of birth</div><div class="cell-primary">${p.date_of_birth ? fmtDate(p.date_of_birth) : "—"}</div></div>
            <div><div class="field__label">Patient since</div><div class="cell-primary">${fmtDate(p.created_at)}</div></div>
          </div>
          <div class="divider"></div>
          <div class="field__label">Notes</div><div>${escapeHtml(p.notes || "No notes on file.")}</div>`,
        footerHtml: `<button class="btn btn--secondary" id="cancel-btn">Close</button>`,
        onMount: () => $("#cancel-btn").addEventListener("click", closeModal),
      });
    }

    function openAddModal() {
      openModal({
        title: "Add patient",
        bodyHtml: `
          <div class="form-grid">
            <div class="field"><label class="field__label">First name</label><input class="input" id="f-first" /></div>
            <div class="field"><label class="field__label">Last name</label><input class="input" id="f-last" /></div>
            <div class="field"><label class="field__label">Phone</label><input class="input" id="f-phone" placeholder="(415) 555-0100" /></div>
            <div class="field"><label class="field__label">Email</label><input class="input" id="f-email" type="email" /></div>
            <div class="field"><label class="field__label">Date of birth</label><input class="input" id="f-dob" type="date" /></div>
          </div>
          <div class="field"><label class="field__label">Notes</label><textarea class="textarea" id="f-notes"></textarea></div>`,
        footerHtml: `<button class="btn btn--secondary" id="cancel-btn">Cancel</button><button class="btn btn--primary" id="save-btn"><span class="spinner"></span><span class="btn__label">Save patient</span></button>`,
        onMount: () => {
          $("#cancel-btn").addEventListener("click", closeModal);
          $("#save-btn").addEventListener("click", async () => {
            const first = $("#f-first").value.trim(), last = $("#f-last").value.trim();
            if (!first || !last) { toast({ title: "First and last name are required", tone: "error" }); return; }
            const payload = { first_name: first, last_name: last, phone: $("#f-phone").value.trim() || null, email: $("#f-email").value.trim() || null, date_of_birth: $("#f-dob").value || null, notes: $("#f-notes").value.trim() || null };
            const btn = $("#save-btn"); btn.classList.add("is-loading"); btn.disabled = true;
            try {
              const created = await Api.patients.create(payload);
              allRows.unshift(created); delete state.cache.patients;
              closeModal(); toast({ title: "Patient added", text: `${first} ${last} was saved.`, tone: "success" }); mount();
            } catch (err) { toast({ title: "Couldn't save patient", text: err.message, tone: "error" }); btn.classList.remove("is-loading"); btn.disabled = false; }
          });
        },
      });
    }
  }

  // ===========================================================================
  // PAGE: Appointments
  // ===========================================================================
  function renderAppointmentsPage(container) {
    container.innerHTML = `
      <div class="page-header">
        <div><div class="page-header__title">Appointments</div><div class="page-header__subtitle">Every booking, past and upcoming.</div></div>
        <div class="page-header__actions">${tzChipHtml()}</div>
      </div>
      <div class="table-card"><div id="apt-toolbar"></div><div id="apt-body"></div></div>`;
    const body = $("#apt-body");
    let allRows = [], patientsCache = [], page = 1, search = "", statusFilter = "";

    loadInto(body, {
      skeleton: skeletonRows(6, 5),
      cacheKey: "appointments",
      fetcher: () => Api.appointments.list(),
      emptyCheck: (d) => d.length === 0,
      emptyProps: { icon: ICONS.appointments, title: "No appointments yet", text: "Bookings made by the AI Receptionist or staff will show up here.", actionHtml: `<button class="btn btn--primary btn--sm" id="apt-add-empty">${ICONS.plus} New appointment</button>` },
      render: (rows) => { allRows = rows.sort((a, b) => new Date(b.start_time) - new Date(a.start_time)); mount(); },
    });

    function mount() {
      $("#apt-toolbar").outerHTML = `<div id="apt-toolbar">${tableToolbar({
        searchPlaceholder: "Search appointments…", count: `${allRows.length} appointments`, addLabel: "New appointment",
        filters: [{ key: "status", label: "Status", options: ["scheduled", "completed", "cancelled", "no_show"] }],
      })}</div>`;
      $("#tbl-search").addEventListener("input", debounce((e) => { search = e.target.value.toLowerCase(); page = 1; paint(); }, 200));
      $("#filter-status").addEventListener("change", (e) => { statusFilter = e.target.value; page = 1; paint(); });
      $("#tbl-add").addEventListener("click", openAddModal);
      const emptyBtn = $("#apt-add-empty"); if (emptyBtn) emptyBtn.addEventListener("click", openAddModal);
      paint();
    }

    function paint() {
      const rows = allRows.filter((a) => {
        const hay = `${a.notes || ""} ${a.status}`.toLowerCase();
        return (!search || hay.includes(search)) && (!statusFilter || a.status === statusFilter);
      });
      const { pageRows, totalPages } = paginate(rows, page);
      let wrap = $("#apt-table-wrap");
      if (!wrap) { wrap = el("<div id=\"apt-table-wrap\"></div>"); body.appendChild(wrap); }
      if (!rows.length) { wrap.innerHTML = emptyState({ icon: ICONS.search, title: "No matching appointments", text: "Try a different search term or filter." }); return; }
      wrap.innerHTML = `
        <div class="table-scroll"><table class="data-table">
          <thead><tr><th>Date &amp; time</th><th>Duration</th><th>Status</th><th>Notes</th></tr></thead>
          <tbody>${pageRows.map((a) => `
            <tr>
              <td class="cell-primary">${fmtDateTime(a.start_time)}</td>
              <td class="cell-muted">${Math.round((new Date(a.end_time) - new Date(a.start_time)) / 60000)} min</td>
              <td>${badge(a.status.replace("_", " "), STATUS_TONE[a.status] || "muted")}</td>
              <td class="cell-muted">${escapeHtml(a.notes || "—")}</td>
            </tr>`).join("")}</tbody>
        </table></div>
        <div class="table-footer"><span>Page ${page} of ${totalPages}</span>${paginationHtml(page, totalPages)}</div>`;
      $$(".pagination button[data-page]", wrap).forEach((b) => b.addEventListener("click", () => { page = Number(b.dataset.page); paint(); }));
    }

    async function openAddModal() {
      if (!patientsCache.length) {
        try { patientsCache = await Api.patients.list(); } catch { patientsCache = []; }
      }
      openModal({
        title: "New appointment",
        bodyHtml: `
          <div class="field"><label class="field__label">Patient</label>
            <select class="select" id="f-patient">${patientsCache.length ? patientsCache.map((p) => `<option value="${p.id}">${escapeHtml(p.first_name)} ${escapeHtml(p.last_name)}</option>`).join("") : `<option value="">No patients yet — add one first</option>`}</select>
          </div>
          <div class="form-grid">
            <div class="field"><label class="field__label">Start</label><input class="input" id="f-start" type="datetime-local" />
              <div class="field__hint">Entered as ${escapeHtml(TZ.cityLabel(clinicTz()))} time (${escapeHtml(TZ.offsetLabel(clinicTz()))}) — the workspace timezone.</div>
            </div>
            <div class="field"><label class="field__label">Duration (minutes)</label><input class="input" id="f-duration" type="number" value="30" min="15" step="15" /></div>
          </div>
          <div class="field"><label class="field__label">Notes</label><textarea class="textarea" id="f-notes" placeholder="Cleaning, checkup..."></textarea></div>`,
        footerHtml: `<button class="btn btn--secondary" id="cancel-btn">Cancel</button><button class="btn btn--primary" id="save-btn"><span class="spinner"></span><span class="btn__label">Book appointment</span></button>`,
        onMount: () => {
          $("#cancel-btn").addEventListener("click", closeModal);
          $("#save-btn").addEventListener("click", async () => {
            const patientId = $("#f-patient").value;
            const startVal = $("#f-start").value;
            if (!patientId) { toast({ title: "Add a patient first", tone: "error" }); return; }
            if (!startVal) { toast({ title: "Pick a start time", tone: "error" }); return; }
            // The datetime-local value is a naive wall-clock string — interpret
            // it in the ORGANISATION'S timezone, not the browser's, then send
            // the resulting absolute instant (UTC ISO) to the backend.
            const start = TZ.wallTimeToInstant(startVal, clinicTz());
            if (!start) { toast({ title: "Pick a valid start time", tone: "error" }); return; }
            const end = new Date(start.getTime() + Number($("#f-duration").value || 30) * 60000);
            const btn = $("#save-btn"); btn.classList.add("is-loading"); btn.disabled = true;
            try {
              const created = await Api.appointments.create({ patient_id: patientId, start_time: start.toISOString(), end_time: end.toISOString(), notes: $("#f-notes").value.trim() || null });
              allRows.unshift(created); delete state.cache.appointments;
              closeModal(); toast({ title: "Appointment booked", tone: "success" }); mount();
            } catch (err) { toast({ title: "Couldn't book appointment", text: err.message, tone: "error" }); btn.classList.remove("is-loading"); btn.disabled = false; }
          });
        },
      });
    }
  }

  // ===========================================================================
  // PAGE: Call History
  // ===========================================================================
  function renderCallHistoryPage(container) {
    container.innerHTML = `
      <div class="page-header">
        <div><div class="page-header__title">Call History</div><div class="page-header__subtitle">Every call the AI Receptionist has handled.</div></div>
      </div>
      <div class="table-card"><div id="ch-toolbar"></div><div id="ch-body"></div></div>`;
    const body = $("#ch-body");
    let allRows = [], page = 1, search = "", statusFilter = "";

    loadInto(body, {
      skeleton: skeletonRows(7, 5),
      cacheKey: "calls",
      fetcher: () => Api.calls.list(),
      emptyCheck: (d) => d.length === 0,
      emptyProps: { icon: ICONS.callHistory, title: "No calls yet", text: "Once the AI Receptionist starts taking calls, they'll be logged here." },
      render: (rows) => { allRows = rows.sort((a, b) => new Date(b.started_at || b.created_at) - new Date(a.started_at || a.created_at)); mount(); },
    });

    function mount() {
      $("#ch-toolbar").outerHTML = `<div id="ch-toolbar">${tableToolbar({
        searchPlaceholder: "Search calls…", count: `${allRows.length} calls`,
        filters: [{ key: "status", label: "Status", options: [...new Set(allRows.map((r) => r.status))] }],
      })}</div>`;
      $("#tbl-search").addEventListener("input", debounce((e) => { search = e.target.value.toLowerCase(); page = 1; paint(); }, 200));
      $("#filter-status").addEventListener("change", (e) => { statusFilter = e.target.value; page = 1; paint(); });
      paint();
    }

    function paint() {
      const rows = allRows.filter((c) => {
        const hay = `${c.from_number || ""} ${c.to_number || ""} ${c.direction}`.toLowerCase();
        return (!search || hay.includes(search)) && (!statusFilter || c.status === statusFilter);
      });
      const { pageRows, totalPages } = paginate(rows, page);
      let wrap = $("#ch-table-wrap");
      if (!wrap) { wrap = el("<div id=\"ch-table-wrap\"></div>"); body.appendChild(wrap); }
      if (!rows.length) { wrap.innerHTML = emptyState({ icon: ICONS.search, title: "No matching calls", text: "Try a different search term or filter." }); return; }
      wrap.innerHTML = `
        <div class="table-scroll"><table class="data-table">
          <thead><tr><th>Direction</th><th>From</th><th>To</th><th>Started</th><th>Duration</th><th>Status</th></tr></thead>
          <tbody>${pageRows.map((c) => `
            <tr class="ch-row" data-id="${c.id}">
              <td>${badge(c.direction, c.direction === "inbound" ? "info" : "muted")}</td>
              <td class="cell-primary">${escapeHtml(c.from_number || "—")}</td>
              <td class="cell-muted">${escapeHtml(c.to_number || "—")}</td>
              <td class="cell-muted">${fmtDateTime(c.started_at)}</td>
              <td class="cell-muted">${c.duration_seconds ? fmtDurationShort(c.duration_seconds) : "—"}</td>
              <td>${badge(c.status.replace("_", " "), STATUS_TONE[c.status] || "muted")}</td>
            </tr>`).join("")}</tbody>
        </table></div>
        <div class="table-footer"><span>Page ${page} of ${totalPages}</span>${paginationHtml(page, totalPages)}</div>`;
      $$(".pagination button[data-page]", wrap).forEach((b) => b.addEventListener("click", () => { page = Number(b.dataset.page); paint(); }));
      $$(".ch-row", wrap).forEach((r) => r.addEventListener("click", () => openTranscript(allRows.find((c) => c.id === r.dataset.id))));
    }

    async function openTranscript(call) {
      openModal({
        title: `Call with ${call.from_number || "unknown caller"}`,
        wide: true,
        bodyHtml: `<div id="transcript-loading">${skeletonRows(4, 1)}</div>`,
        footerHtml: `<button class="btn btn--secondary" id="cancel-btn">Close</button>`,
        onMount: async () => {
          $("#cancel-btn").addEventListener("click", closeModal);
          try {
            const transcripts = await Api.calls.transcripts(call.id);
            const holder = $("#transcript-loading");
            if (!transcripts.length) {
              holder.innerHTML = emptyState({ icon: ICONS.callHistory, title: "No transcript recorded", text: "This call has no stored transcript turns." });
              return;
            }
            holder.innerHTML = `<div class="transcript">${transcripts.map((t) => `
              <div class="transcript-bubble transcript-bubble--${t.speaker === "caller" ? "caller" : "assistant"}">${escapeHtml(t.content)}</div>
            `).join("")}</div>`;
          } catch (err) {
            $("#transcript-loading").innerHTML = errorState({ message: err.message, retryId: "retry-transcript" });
          }
        },
      });
    }
  }

  // ===========================================================================
  // Clinic AI knowledge base (ai_agents.config.clinic_settings) — the one
  // real read/write surface, via GET/PUT /workspaces/{id}/clinic-settings.
  // Every settings tab and the Doctors/Services pages go through this so a
  // partial edit never drops the other keys (PUT replaces the whole object).
  // ===========================================================================
  const ClinicConfig = {
    get() { return Api.clinicSettings.get(); },
    async save(patch) {
      const current = await Api.clinicSettings.get();
      const merged = { ...current, ...patch };
      delete merged.workspace_id; // ClinicSettingsUpdate forbids unknown keys
      const saved = await Api.clinicSettings.save(merged);
      delete state.cache.clinicConfig;
      delete state.cache.overview; // the dashboard bundles clinic config
      return saved;
    },
  };
  function clinicConfigComplete(cs) {
    return Boolean(cs && (cs.doctors || []).length && (cs.services || []).length && (cs.emergency_protocol || "").trim());
  }

  // ===========================================================================
  // PAGE: AI Agent — the real ai_agents.config.clinic_settings for this
  // workspace (read-only summary; every field is edited on the Settings /
  // Doctors / Services pages) plus the live "Test the AI Agent" widget wired
  // to POST /ai/sessions + /messages (app/api/ai.py — same engine as calls).
  // ===========================================================================
  function renderAiReceptionistPage(container) {
    container.innerHTML = `
      <div class="page-header">
        <div><div class="page-header__title">AI Agent</div><div class="page-header__subtitle">What your AI receptionist knows and how it sounds on calls.</div></div>
        <div class="page-header__actions"><button class="btn btn--secondary btn--sm" data-nav="settings/ai">${ICONS.edit} Edit preferences</button></div>
      </div>
      <div id="ai-summary"></div>
      <div class="section-title">Test the AI Agent</div>
      <div class="card">
        <p class="cell-muted" style="margin:-4px 0 12px;">Type as though you were a caller. This uses the same conversation engine that answers real calls.</p>
        <div id="ai-test-start-wrap"><button class="btn btn--secondary btn--sm" id="ai-test-start"><span class="spinner"></span><span class="btn__label">Start test conversation</span></button></div>
        <div class="transcript" id="ai-test-transcript" style="margin:0 0 14px;max-height:360px;overflow-y:auto;" hidden></div>
        <div class="field__error" id="ai-test-error" role="alert" hidden></div>
        <div id="ai-test-composer" style="display:none;gap:8px;">
          <input class="input" id="ai-test-input" aria-label="Message to the AI agent" placeholder="e.g. I'd like to book a check-up" disabled />
          <button class="btn btn--primary" id="ai-test-send" disabled><span class="spinner"></span><span class="btn__label">Send</span></button>
        </div>
      </div>`;

    $$('[data-nav]', container).forEach((b) => b.addEventListener("click", () => navigate(b.dataset.nav)));

    loadInto($("#ai-summary", container), {
      skeleton: skeletonCards(3),
      cacheKey: "clinicConfig",
      fetcher: () => ClinicConfig.get(),
      render: (cs, root) => {
        const doctors = cs.doctors || [];
        const services = cs.services || [];
        const ready = clinicConfigComplete(cs);
        root.innerHTML = `
          <div class="card card--row" style="margin-bottom:16px;">
            <div>
              <div class="card__title">Status</div>
              <div class="card__subtitle">${ready ? "Ready to take calls — the knowledge base is complete." : "Some knowledge-base fields are still empty."}</div>
            </div>
            <span class="status-pill ${ready ? "status-pill--ok" : "status-pill--warn"}"><span class="status-pill__dot" aria-hidden="true"></span>${ready ? "Active" : "Setup incomplete"}</span>
          </div>
          <div class="grid grid--2">
            <div class="card">
              <div class="card__head"><div class="card__title">Voice &amp; language</div>
                <button class="btn btn--ghost btn--sm" data-nav="settings/ai">${ICONS.edit} Edit</button></div>
              <dl class="def-list">
                <dt>Tone</dt><dd>${escapeHtml(cs.agent_tone || "Professional")}</dd>
                <dt>Preferred language</dt><dd>${escapeHtml(cs.preferred_language || "English")}</dd>
              </dl>
              <div class="divider"></div>
              <div class="card__head"><div class="card__title">Emergency protocol</div>
                <button class="btn btn--ghost btn--sm" data-nav="settings/emergency">${ICONS.edit} Edit</button></div>
              <p class="cell-muted" style="white-space:pre-wrap;margin:0;">${cs.emergency_protocol ? escapeHtml(cs.emergency_protocol) : "Not set — callers reporting an emergency get a safe generic response."}</p>
            </div>
            <div class="card">
              <div class="card__head"><div class="card__title">Knowledge base</div></div>
              <div class="settings-row"><div class="settings-row__label">Doctors</div>
                <span class="cell-row-flex">${badge(String(doctors.length), doctors.length ? "brand" : "muted")}<button class="btn btn--ghost btn--sm" data-nav="doctors">Manage</button></span></div>
              <div class="settings-row"><div class="settings-row__label">Services</div>
                <span class="cell-row-flex">${badge(String(services.length), services.length ? "brand" : "muted")}<button class="btn btn--ghost btn--sm" data-nav="services">Manage</button></span></div>
              <div class="settings-row"><div class="settings-row__label">Appointment slot</div>
                <span class="cell-primary">${(cs.appointment_settings || {}).default_slot_duration_minutes || 30} min</span></div>
              <div class="settings-row"><div class="settings-row__label">Clinic info</div>
                <span class="cell-row-flex">${badge((cs.general_info || {}).address ? "Set" : "Empty", (cs.general_info || {}).address ? "success" : "muted")}<button class="btn btn--ghost btn--sm" data-nav="settings/clinic">Edit</button></span></div>
            </div>
          </div>`;
        $$('[data-nav]', root).forEach((b) => b.addEventListener("click", () => navigate(b.dataset.nav)));
      },
    });

    initAiTestWidget(container);
  }

  // -- "Test the AI Receptionist" — real conversation session ------------------
  function initAiTestWidget(container) {
    const startWrap = $("#ai-test-start-wrap", container);
    const startBtn = $("#ai-test-start", container);
    const transcript = $("#ai-test-transcript", container);
    const composer = $("#ai-test-composer", container);
    const input = $("#ai-test-input", container);
    const sendBtn = $("#ai-test-send", container);
    const errBox = $("#ai-test-error", container);
    let sessionId = null;
    let sending = false;

    const showErr = (msg) => { if (!msg) { errBox.hidden = true; errBox.textContent = ""; return; } errBox.hidden = false; errBox.textContent = msg; };
    const addBubble = (role, text) => {
      transcript.insertAdjacentHTML("beforeend", `<div class="transcript-bubble transcript-bubble--${role === "caller" ? "caller" : "assistant"}">${escapeHtml(text)}</div>`);
      transcript.scrollTop = transcript.scrollHeight;
    };

    // Lazy — no /ai/sessions request until the user actually asks to test.
    async function startSession() {
      showErr("");
      startBtn.classList.add("is-loading"); startBtn.disabled = true;
      try {
        const session = await Api.ai.startSession();
        sessionId = session.session_id;
        startWrap.hidden = true;
        transcript.hidden = false;
        composer.style.display = "flex";
        addBubble("assistant", "Session started — type a message below as if you were a caller.");
        input.disabled = false;
        sendBtn.disabled = false;
        input.focus();
      } catch (err) {
        startBtn.classList.remove("is-loading"); startBtn.disabled = false;
        showErr(err instanceof Api.ApiError ? err.message : "Couldn't start a test session.");
      }
    }

    async function send() {
      const message = input.value.trim();
      if (!message || sending || !sessionId) return;
      showErr("");
      sending = true;
      sendBtn.classList.add("is-loading");
      sendBtn.disabled = true;
      input.disabled = true;
      addBubble("caller", message);
      input.value = "";
      try {
        const result = await Api.ai.sendMessage(sessionId, message);
        addBubble("assistant", result.reply);
      } catch (err) {
        showErr(err instanceof Api.ApiError ? err.message : "Couldn't reach the AI agent.");
      } finally {
        sending = false;
        sendBtn.classList.remove("is-loading");
        sendBtn.disabled = false;
        input.disabled = false;
        input.focus();
      }
    }

    startBtn.addEventListener("click", startSession);
    sendBtn.addEventListener("click", send);
    input.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); send(); } });
  }

  // ===========================================================================
  // PAGE: Analytics — backed by GET /workspaces/{id}/analytics/summary (Phase 13)
  // ===========================================================================
  const ANALYTICS_RANGES = {
    "7d": 7, "30d": 30, "90d": 90, all: null,
  };

  async function renderAnalyticsPage(container) {
    container.innerHTML = `
      <div class="page-header">
        <div><div class="page-header__title">Analytics</div><div class="page-header__subtitle">Performance across calls, leads, appointments, and the AI Receptionist.</div></div>
        <div class="page-header__actions">
          <div class="chip-toggle" id="an-range">
            <button data-range="7d" class="is-active">7 days</button>
            <button data-range="30d">30 days</button>
            <button data-range="90d">90 days</button>
            <button data-range="all">All time</button>
          </div>
        </div>
      </div>
      <div id="an-body"></div>`;
    const body = $("#an-body");
    let range = "7d";

    $$("#an-range button").forEach((b) => b.addEventListener("click", () => {
      $$("#an-range button").forEach((x) => x.classList.remove("is-active"));
      b.classList.add("is-active");
      range = b.dataset.range;
      delete state.cache[`analytics:${range}`];
      load();
    }));

    load();

    function load() {
      const days = ANALYTICS_RANGES[range];
      const since = days ? new Date(Date.now() - days * 86400000).toISOString() : undefined;
      loadInto(body, {
        skeleton: skeletonCards(4),
        cacheKey: `analytics:${range}`,
        fetcher: () => Api.analytics.summary({ since }),
        render: (summary, root) => renderAnalyticsSummary(summary, root),
      });
    }
  }

  function renderAnalyticsSummary(s, root) {
    const pct = (n) => (n === null || n === undefined ? "—" : `${Math.round(n * 100)}%`);
    const secs = (n) => (n === null || n === undefined ? "—" : fmtDurationShort(Math.round(n)));
    root.innerHTML = `
      <div class="grid grid--kpi">
        ${kpiCard({ icon: ICONS.liveCalls, tone: "brand", label: "Total calls", value: s.total_calls, delta: null, spark: sparkFrom(s.total_calls) })}
        ${kpiCard({ icon: ICONS.check, tone: "success", label: "Answered calls", value: s.answered_calls, delta: null, spark: sparkFrom(s.answered_calls) })}
        ${kpiCard({ icon: ICONS.callHistory, tone: "info", label: "Avg. call duration", value: secs(s.average_duration_seconds), delta: null, spark: sparkFrom(s.average_duration_seconds || 0) })}
        ${kpiCard({ icon: ICONS.leads, tone: "warning", label: "Qualified leads", value: s.qualified_leads, delta: null, spark: sparkFrom(s.qualified_leads) })}
        ${kpiCard({ icon: ICONS.appointments, tone: "brand", label: "Appointments", value: s.appointments, delta: null, spark: sparkFrom(s.appointments) })}
        ${kpiCard({ icon: ICONS.leads, tone: "success", label: "Conversion rate", value: pct(s.conversion_rate), delta: null, spark: sparkFrom((s.conversion_rate || 0) * 100) })}
        ${kpiCard({ icon: ICONS.ai, tone: "info", label: "AI resolution rate", value: pct(s.ai_resolution_rate), delta: null, spark: sparkFrom((s.ai_resolution_rate || 0) * 100) })}
        ${kpiCard({ icon: ICONS.transfer, tone: "warning", label: "Receptionist transfers", value: s.receptionist_transfers, delta: null, spark: sparkFrom(s.receptionist_transfers) })}
        ${kpiCard({ icon: ICONS.warn, tone: "danger", label: "Integration failures", value: s.integration_failures, delta: null, spark: sparkFrom(s.integration_failures) })}
      </div>
      ${s.total_calls === 0 && s.appointments === 0 && s.qualified_leads === 0
        ? emptyState({
            icon: ICONS.analytics, title: "No activity yet in this range",
            text: "Once calls, leads, and appointments start coming in, this dashboard fills in automatically.",
          })
        : `<div class="card">
            <div class="card__head"><div><div class="card__title">Integration health</div><div class="card__subtitle">${s.integration_attempts} attempted call${s.integration_attempts === 1 ? "" : "s"} to calendar/WhatsApp/email/telephony providers</div></div></div>
            <div class="progress" style="margin-bottom:8px;"><div class="progress__bar" style="width:${s.integration_attempts ? Math.round(((s.integration_attempts - s.integration_failures) / s.integration_attempts) * 100) : 100}%"></div></div>
            <div class="cell-muted">${s.integration_failures} failure${s.integration_failures === 1 ? "" : "s"} out of ${s.integration_attempts} attempt${s.integration_attempts === 1 ? "" : "s"}</div>
          </div>`}`;
  }

  function sparkFrom(value) {
    const base = Math.max(1, value);
    return [base * 0.6, base * 0.75, base * 0.65, base * 0.85, base * 0.78, base * 0.92, base];
  }

  // ===========================================================================
  // PAGE: Doctors — clinic_settings.doctors[] (real, editable via PUT
  // /workspaces/{id}/clinic-settings through ClinicConfig).
  // ===========================================================================
  function toNum(v) {
    const s = String(v ?? "").trim();
    if (s === "") return null;
    const n = Number(s);
    return Number.isFinite(n) ? n : NaN;
  }

  function renderDoctorsPage(container) {
    container.innerHTML = `
      <div class="page-header">
        <div><div class="page-header__title">Doctors</div><div class="page-header__subtitle">Practitioners the AI agent can tell callers about and book with.</div></div>
        <div class="page-header__actions"><button class="btn btn--primary btn--sm" id="doc-add">${ICONS.plus} Add doctor</button></div>
      </div>
      <div id="doc-body"></div>`;

    const body = $("#doc-body");
    let doctors = [];
    // Delegated so it also catches the button inside the async empty state.
    body.addEventListener("click", (e) => { if (e.target.closest("#doc-add-empty")) openDoctorModal(-1); });

    function reload() { delete state.cache.clinicConfig; load(); }
    function load() {
      loadInto(body, {
        skeleton: skeletonCards(3),
        cacheKey: "clinicConfig",
        fetcher: () => ClinicConfig.get(),
        emptyCheck: (cs) => (cs.doctors || []).length === 0,
        emptyProps: {
          icon: ICONS.doctor, title: "No doctors yet",
          text: "Add the practitioners your clinic books appointments with. The AI agent uses this list on every call.",
          actionHtml: `<button class="btn btn--primary btn--sm" id="doc-add-empty">${ICONS.plus} Add doctor</button>`,
        },
        render: (cs, root) => {
          doctors = (cs.doctors || []).map((d) => ({ ...d }));
          root.innerHTML = `<div class="entity-grid">${doctors.map((d, i) => `
            <div class="entity-card">
              <div class="entity-card__head">
                <div class="entity-card__avatar">${initials(d.name)}</div>
                <div style="min-width:0;">
                  <div class="entity-card__name">${escapeHtml(d.name || "Unnamed")}</div>
                  <div class="entity-card__sub">${escapeHtml(d.specialty || "General")}</div>
                </div>
              </div>
              <div class="entity-card__meta">
                ${d.consultation_fee != null ? `<span><strong>Fee</strong> ${escapeHtml(String(d.consultation_fee))}</span>` : ""}
                ${d.timings ? `<span><strong>Hours</strong> ${escapeHtml(d.timings)}</span>` : ""}
              </div>
              <div class="entity-card__actions">
                <button class="btn btn--secondary btn--sm" data-edit="${i}">${ICONS.edit} Edit</button>
                <button class="btn btn--ghost btn--sm" data-del="${i}" aria-label="Remove ${escapeHtml(d.name || "doctor")}" title="Remove">${ICONS.trash}</button>
              </div>
            </div>`).join("")}</div>`;
          $$("[data-edit]", root).forEach((b) => b.addEventListener("click", () => openDoctorModal(Number(b.dataset.edit))));
          $$("[data-del]", root).forEach((b) => b.addEventListener("click", () => removeDoctor(Number(b.dataset.del))));
        },
      });
    }

    async function persist(next, okMsg) {
      try {
        await ClinicConfig.save({ doctors: next });
        toast({ title: okMsg, tone: "success" });
        closeModal();
        reload();
      } catch (err) {
        toast({ title: "Couldn't save", text: err.message, tone: "error" });
        throw err;
      }
    }

    function removeDoctor(i) {
      const d = doctors[i] || {};
      confirmModal({
        title: "Remove doctor",
        message: `Remove ${d.name || "this doctor"} from the AI agent's knowledge base? This is saved immediately.`,
        confirmLabel: "Remove doctor",
        onConfirm: () => persist(doctors.filter((_, idx) => idx !== i), "Doctor removed"),
      });
    }

    function openDoctorModal(i) {
      const d = i >= 0 ? doctors[i] : { name: "", specialty: "", consultation_fee: null, timings: "" };
      openModal({
        title: i >= 0 ? "Edit doctor" : "Add doctor",
        bodyHtml: `
          <div class="form-grid">
            <div class="field"><label class="field__label" for="d-name">Name <span class="req" aria-hidden="true">*</span></label><input class="input" id="d-name" value="${escapeHtml(d.name || "")}" maxlength="255" required aria-required="true" /></div>
            <div class="field"><label class="field__label">Specialty</label><input class="input" id="d-spec" value="${escapeHtml(d.specialty || "")}" maxlength="255" placeholder="General Physician" /></div>
            <div class="field"><label class="field__label">Consultation fee</label><input class="input" id="d-fee" type="number" min="0" step="any" value="${d.consultation_fee != null ? escapeHtml(String(d.consultation_fee)) : ""}" placeholder="e.g. 2000" /></div>
            <div class="field"><label class="field__label">Working hours</label><input class="input" id="d-time" value="${escapeHtml(d.timings || "")}" maxlength="255" placeholder="Mon–Fri, 09:00–17:00" /></div>
          </div>
          <div class="field__error" id="d-err" role="alert" hidden></div>`,
        footerHtml: `<button class="btn btn--secondary" id="cancel-btn">Cancel</button><button class="btn btn--primary" id="save-btn"><span class="spinner"></span><span class="btn__label">Save</span></button>`,
        onMount: () => {
          $("#cancel-btn").addEventListener("click", closeModal);
          const err = $("#d-err");
          $("#save-btn").addEventListener("click", async () => {
            err.hidden = true;
            const name = $("#d-name").value.trim();
            if (!name) { err.textContent = "Name is required."; err.hidden = false; return; }
            const fee = toNum($("#d-fee").value);
            if (Number.isNaN(fee)) { err.textContent = "Fee must be a number."; err.hidden = false; return; }
            if (fee != null && fee < 0) { err.textContent = "Fee can't be negative."; err.hidden = false; return; }
            const rec = { name, specialty: $("#d-spec").value.trim() || null, timings: $("#d-time").value.trim() || null, consultation_fee: fee };
            const next = doctors.slice();
            if (i >= 0) next[i] = rec; else next.push(rec);
            const btn = $("#save-btn"); btn.classList.add("is-loading"); btn.disabled = true;
            try { await persist(next, i >= 0 ? "Doctor updated" : "Doctor added"); }
            catch { btn.classList.remove("is-loading"); btn.disabled = false; }
          });
        },
      });
    }

    $("#doc-add").addEventListener("click", () => openDoctorModal(-1));
    load();
  }

  // ===========================================================================
  // PAGE: Services — clinic_settings.services[] (list of strings, real).
  // ===========================================================================
  function renderServicesPage(container) {
    container.innerHTML = `
      <div class="page-header">
        <div><div class="page-header__title">Services</div><div class="page-header__subtitle">Treatments and appointment types callers can ask about and book.</div></div>
        <div class="page-header__actions"><button class="btn btn--primary btn--sm" id="svc-add">${ICONS.plus} Add service</button></div>
      </div>
      <div id="svc-body"></div>`;

    const body = $("#svc-body");
    let services = [];
    body.addEventListener("click", (e) => { if (e.target.closest("#svc-add-empty")) openServiceModal(-1); });

    function reload() { delete state.cache.clinicConfig; load(); }
    function load() {
      loadInto(body, {
        skeleton: skeletonCards(3),
        cacheKey: "clinicConfig",
        fetcher: () => ClinicConfig.get(),
        emptyCheck: (cs) => (cs.services || []).length === 0,
        emptyProps: {
          icon: ICONS.service, title: "No services yet",
          text: "List what your clinic offers so the AI agent can answer “do you do X?” and book the right thing.",
          actionHtml: `<button class="btn btn--primary btn--sm" id="svc-add-empty">${ICONS.plus} Add service</button>`,
        },
        render: (cs, root) => {
          services = (cs.services || []).slice();
          root.innerHTML = `<div class="entity-grid">${services.map((s, i) => `
            <div class="entity-card">
              <div class="entity-card__head">
                <div class="entity-card__avatar" aria-hidden="true">${ICONS.service}</div>
                <div style="min-width:0;"><div class="entity-card__name">${escapeHtml(s)}</div></div>
              </div>
              <div class="entity-card__actions">
                <button class="btn btn--secondary btn--sm" data-edit="${i}">${ICONS.edit} Edit</button>
                <button class="btn btn--ghost btn--sm" data-del="${i}" aria-label="Remove ${escapeHtml(s)}" title="Remove">${ICONS.trash}</button>
              </div>
            </div>`).join("")}</div>`;
          $$("[data-edit]", root).forEach((b) => b.addEventListener("click", () => openServiceModal(Number(b.dataset.edit))));
          $$("[data-del]", root).forEach((b) => b.addEventListener("click", () => {
            const idx = Number(b.dataset.del);
            confirmModal({
              title: "Remove service",
              message: `Remove “${services[idx]}” from the service list? This is saved immediately.`,
              confirmLabel: "Remove service",
              onConfirm: () => persist(services.filter((_, j) => j !== idx), "Service removed")
                .catch((e) => toast({ title: "Couldn't save", text: e.message, tone: "error" })),
            });
          }));
        },
      });
    }

    async function persist(next, okMsg) {
      await ClinicConfig.save({ services: next });
      toast({ title: okMsg, tone: "success" });
      closeModal();
      reload();
    }

    function openServiceModal(i) {
      openModal({
        title: i >= 0 ? "Edit service" : "Add service",
        bodyHtml: `
          <div class="field"><label class="field__label" for="s-name">Service name <span class="req" aria-hidden="true">*</span></label><input class="input" id="s-name" value="${i >= 0 ? escapeHtml(services[i]) : ""}" maxlength="255" placeholder="e.g. Dental cleaning" required aria-required="true" /></div>
          <div class="field__error" id="s-err" role="alert" hidden></div>`,
        footerHtml: `<button class="btn btn--secondary" id="cancel-btn">Cancel</button><button class="btn btn--primary" id="save-btn"><span class="spinner"></span><span class="btn__label">Save</span></button>`,
        onMount: () => {
          $("#cancel-btn").addEventListener("click", closeModal);
          const err = $("#s-err");
          $("#save-btn").addEventListener("click", async () => {
            const name = $("#s-name").value.trim();
            if (!name) { err.textContent = "Service name is required."; err.hidden = false; return; }
            const next = services.slice();
            if (i >= 0) next[i] = name; else next.push(name);
            const btn = $("#save-btn"); btn.classList.add("is-loading"); btn.disabled = true;
            try { await persist(next, i >= 0 ? "Service updated" : "Service added"); }
            catch (e2) { toast({ title: "Couldn't save", text: e2.message, tone: "error" }); btn.classList.remove("is-loading"); btn.disabled = false; }
          });
        },
      });
    }

    $("#svc-add").addEventListener("click", () => openServiceModal(-1));
    load();
  }

  // ===========================================================================
  // PAGE: Team  (shared with Settings > Team via mountTeam)
  // ===========================================================================
  function renderTeamPage(container) {
    container.innerHTML = `
      <div class="page-header">
        <div><div class="page-header__title">Team</div><div class="page-header__subtitle">People with access to this workspace.</div></div>
        <div class="page-header__actions"><button class="btn btn--primary btn--sm" id="team-invite">${ICONS.plus} Invite member</button></div>
      </div>
      <div id="team-mount"></div>`;
    mountTeam($("#team-mount", container), $("#team-invite", container));
  }

  function mountTeam(mountEl, inviteBtn) {
    mountEl.innerHTML = `<div class="table-card"><div id="team-body"></div></div>`;
    const body = $("#team-body", mountEl);
    function load() {
      loadInto(body, {
        skeleton: skeletonRows(5, 3),
        cacheKey: "team",
        fetcher: () => Api.workspaces.listMembers(),
        emptyCheck: (d) => d.length === 0,
        emptyProps: { icon: ICONS.team, title: "No team members yet", text: "Invite your receptionists and staff so they can use the dashboard." },
        render: (rows, root) => {
          root.innerHTML = `<div class="table-scroll"><table class="data-table">
            <thead><tr><th>Member</th><th>Email</th><th>Role</th></tr></thead>
            <tbody>${rows.map((m) => `
              <tr>
                <td class="cell-row-flex"><span class="avatar">${initials(m.full_name)}</span><span class="cell-primary">${escapeHtml(m.full_name)}</span></td>
                <td class="cell-muted">${escapeHtml(m.email)}</td>
                <td>${badge(roleLabel(m.role), m.role === "owner" ? "brand" : m.role === "receptionist" ? "info" : "muted")}</td>
              </tr>`).join("")}</tbody></table></div>`;
        },
      });
    }
    load();
    if (inviteBtn) inviteBtn.addEventListener("click", () => openInviteMemberModal(() => { delete state.cache.team; load(); }));
  }

  function openInviteMemberModal(onDone) {
    openModal({
      title: "Invite member",
      bodyHtml: `
        <div class="field"><label class="field__label" for="f-email">Email</label><input class="input" id="f-email" type="email" placeholder="colleague@clinic.com" required aria-required="true" /></div>
        <div class="field"><label class="field__label" for="f-phone">Phone number <span style="color:var(--text-faint);font-weight:400;">(optional)</span></label>
          <input class="input" id="f-phone" type="tel" inputmode="tel" placeholder="+1 415 555 0100" />
          <div class="field__hint">Added to the member's profile if they don't already have one on file.</div>
        </div>
        <div class="field"><label class="field__label" for="f-role">Role</label>
          <select class="select" id="f-role"><option value="receptionist">Receptionist</option><option value="admin">Admin</option><option value="analyst">Analyst</option><option value="owner">Owner</option></select>
        </div>
        <div class="field__error" id="invite-error" role="alert" hidden></div>`,
      footerHtml: `<button class="btn btn--secondary" id="cancel-btn">Cancel</button><button class="btn btn--primary" id="save-btn"><span class="spinner"></span><span class="btn__label">Send invite</span></button>`,
      onMount: () => {
        $("#cancel-btn").addEventListener("click", closeModal);
        const errBox = $("#invite-error");
        const showErr = (msg) => { if (!msg) { errBox.hidden = true; errBox.textContent = ""; return; } errBox.hidden = false; errBox.textContent = msg; };
        $("#save-btn").addEventListener("click", async () => {
          showErr("");
          const email = $("#f-email").value.trim();
          const phone = $("#f-phone").value.trim();
          if (!email) { showErr("Email is required."); return; }
          if (!isValidEmail(email)) { showErr("Enter a valid email address."); return; }
          if (phone && !isValidPhone(phone)) {
            showErr("Enter a valid phone number — digits only, optionally starting with +, 7–15 digits."); return;
          }
          const btn = $("#save-btn"); btn.classList.add("is-loading"); btn.disabled = true;
          try {
            await Api.workspaces.addMember({ email, role: $("#f-role").value, phoneNumber: phone || undefined });
            closeModal(); toast({ title: "Invite sent", text: email, tone: "success" });
            if (typeof onDone === "function") onDone();
          } catch (err) {
            showErr(err instanceof Api.ApiError ? err.message : "Couldn't send invite.");
            btn.classList.remove("is-loading"); btn.disabled = false;
          }
        });
      },
    });
  }

  function isValidEmail(v) { return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v); }
  function isValidPhone(v) {
    if (!/^\+?[\d\s().-]+$/.test(v)) return false;
    const digits = v.replace(/\D/g, "");
    return digits.length >= 7 && digits.length <= 15;
  }

  // ===========================================================================
  // PAGE: Branches — the multi-location hub. Lists every workspace the user
  // belongs to (GET /workspaces), lets them add one (POST /workspaces), see
  // each one's onboarding status, and choose which is active. Reachable even
  // when no branch is onboarded (the route guard allows it unconditionally).
  // ===========================================================================
  function branchRole(wsId) {
    if (state.user && state.user.is_super_admin) return "super_admin";
    const m = (state.memberships || []).find((x) => x.workspace_id === wsId);
    return m ? m.role : null;
  }

  function renderBranchesPage(container) {
    container.innerHTML = `
      <div class="page-header">
        <div><div class="page-header__title">Branches</div>
        <div class="page-header__subtitle">Every location is a separate clinic — its own setup, staff, calls and dashboard.</div></div>
        <div class="page-header__actions"><button class="btn btn--primary btn--sm" id="br-add">${ICONS.plus} Add branch</button></div>
      </div>
      <div id="br-body"></div>`;

    const body = $("#br-body");
    body.addEventListener("click", (e) => { if (e.target.closest("#br-add-empty")) openAddBranchModal(load); });
    $("#br-add").addEventListener("click", () => openAddBranchModal(load));
    load();

    function load() {
      loadInto(body, {
        skeleton: skeletonCards(3),
        fetcher: () => Api.workspaces.list(),
        emptyCheck: (rows) => rows.length === 0,
        emptyProps: {
          icon: ICONS.branches, title: "No branches yet",
          text: "Add your first location. You'll set up its clinic details next.",
          actionHtml: `<button class="btn btn--primary btn--sm" id="br-add-empty">${ICONS.plus} Add branch</button>`,
        },
        render: (rows, root) => {
          state.workspaces = rows;
          // keep the active-workspace pointer valid
          if (state.workspace && !rows.find((w) => w.id === state.workspace.id)) {
            const next = rows.find((w) => w.id === Api.getWorkspaceId()) || rows[0] || null;
            if (next) setActiveWorkspace(next); else { state.workspace = null; }
          } else if (!state.workspace && rows.length) {
            setActiveWorkspace(rows.find((w) => w.id === Api.getWorkspaceId()) || rows[0]);
          }
          updateWorkspaceSwitcher();

          const activeId = state.workspace ? state.workspace.id : Api.getWorkspaceId();
          const done = rows.filter((w) => w.is_onboarded).length;
          const pending = rows.length - done;

          root.innerHTML = `
            <div class="branch-summary">
              <div class="branch-summary__stat"><span class="branch-summary__num">${rows.length}</span><span class="branch-summary__label">Branch${rows.length === 1 ? "" : "es"}</span></div>
              <div class="branch-summary__stat"><span class="branch-summary__num tone-success">${done}</span><span class="branch-summary__label">Onboarded</span></div>
              <div class="branch-summary__stat"><span class="branch-summary__num ${pending ? "tone-warning" : ""}">${pending}</span><span class="branch-summary__label">Setup required</span></div>
            </div>
            <div class="entity-grid">${rows.map((w) => branchCard(w, activeId)).join("")}</div>`;

          const go = (id, route) => { setActiveWorkspace(rows.find((w) => w.id === id)); navigate(route); };
          $$("[data-open]", root).forEach((b) => b.addEventListener("click", () => go(b.dataset.open, "overview")));
          $$("[data-settings]", root).forEach((b) => b.addEventListener("click", () => go(b.dataset.settings, "settings")));
          $$("[data-setup]", root).forEach((b) => b.addEventListener("click", () => go(b.dataset.setup, "onboarding")));
          $$("[data-make-current]", root).forEach((b) => b.addEventListener("click", () => {
            setActiveWorkspace(rows.find((w) => w.id === b.dataset.makeCurrent));
            toast({ title: "Switched branch", text: state.workspace.name, tone: "info" });
            load();
          }));

          // Fill in each onboarded branch's real location (its saved clinic
          // address) without changing the active workspace. Lazy + best-effort.
          rows.filter((w) => w.is_onboarded).forEach((w) => {
            Api.clinicSettings.getFor(w.id).then((cs) => {
              const addr = (cs && cs.general_info && cs.general_info.address) || "";
              const node = $(`[data-loc="${w.id}"]`, root);
              if (node && addr) {
                node.textContent = addr.split("·")[0].trim().slice(0, 90);
                node.hidden = false;
              }
            }).catch(() => {});
          });
        },
      });
    }
  }

  function branchCard(w, activeId) {
    const current = w.id === activeId;
    const ready = !!w.is_onboarded;
    const role = branchRole(w.id);
    const tzCity = window.TZ ? TZ.cityLabel(w.timezone || "UTC") : (w.timezone || "UTC");
    const tzOff = window.TZ ? ` (${TZ.offsetLabel(w.timezone || "UTC")})` : "";
    return `<div class="entity-card branch-card${current ? " entity-card--current" : ""}">
      <div class="entity-card__head">
        <div class="entity-card__avatar" aria-hidden="true">${initials(w.name)}</div>
        <div style="min-width:0;flex:1;">
          <div class="entity-card__name">${escapeHtml(w.name)}
            ${current ? `<span class="badge tone-brand">Current</span>` : ""}
            ${role ? `<span class="badge tone-muted">${escapeHtml(roleLabel(role))}</span>` : ""}</div>
          <div class="entity-card__sub" data-loc="${w.id}" hidden></div>
        </div>
      </div>

      <div class="branch-card__status">
        <span class="status-pill ${ready ? "status-pill--ok" : "status-pill--warn"}">
          <span class="status-pill__dot" aria-hidden="true"></span>${ready ? "Onboarded" : "Setup required"}
        </span>
        <span class="branch-card__hint">${ready ? "Ready to take calls" : "Clinic details not configured yet"}</span>
      </div>

      <dl class="branch-card__meta">
        <div><dt>Timezone</dt><dd>${escapeHtml(tzCity)}${escapeHtml(tzOff)}</dd></div>
        <div><dt>Added</dt><dd>${escapeHtml(fmtDate(w.created_at))}</dd></div>
      </dl>

      <div class="entity-card__actions">
        ${ready
          ? `<button class="btn btn--primary btn--sm" data-open="${w.id}">Open dashboard</button>
             <button class="btn btn--secondary btn--sm" data-settings="${w.id}">${ICONS.settings} Settings</button>
             ${current ? "" : `<button class="btn btn--ghost btn--sm" data-make-current="${w.id}">Make current</button>`}`
          : `<button class="btn btn--primary btn--sm" data-setup="${w.id}">${ICONS.edit} Setup</button>`}
      </div>
    </div>`;
  }

  function openAddBranchModal(onDone) {
    let tzPicker = null;
    openModal({
      title: "Add branch",
      bodyHtml: `
        <div class="field"><label class="field__label" for="br-name">Branch name <span class="req" aria-hidden="true">*</span></label>
          <input class="input" id="br-name" maxlength="255" placeholder="Downtown Clinic" required aria-required="true" /></div>
        <div class="field" style="margin-top:14px;"><label class="field__label">Timezone</label><div id="br-tz"></div></div>
        <div class="field__error" id="br-err" role="alert" hidden></div>`,
      footerHtml: `<button class="btn btn--secondary" id="cancel-btn">Cancel</button><button class="btn btn--primary" id="save-btn"><span class="spinner"></span><span class="btn__label">Create branch</span></button>`,
      onMount: () => {
        $("#cancel-btn").addEventListener("click", closeModal);
        if (window.TZ) { tzPicker = TZ.createPicker({ value: TZ.detect(), detected: TZ.detect() }); $("#br-tz").appendChild(tzPicker); }
        const err = $("#br-err");
        $("#save-btn").addEventListener("click", async () => {
          err.hidden = true;
          const name = $("#br-name").value.trim();
          if (!name) { err.textContent = "Branch name is required."; err.hidden = false; return; }
          const btn = $("#save-btn"); btn.classList.add("is-loading"); btn.disabled = true;
          try {
            const created = await createWorkspace({ name, timezone: tzPicker ? tzPicker.getValue() : undefined });
            Api.setBranchModel("multi");
            state.workspaces = [...(state.workspaces || []), created];
            if (!state.workspace) setActiveWorkspace(created);
            updateWorkspaceSwitcher();
            closeModal();
            toast({ title: "Branch added", text: created.name, tone: "success" });
            if (typeof onDone === "function") onDone();
          } catch (e) {
            err.textContent = (e instanceof Api.ApiError ? e.message : (e && e.message)) || "Couldn't create the branch.";
            err.hidden = false;
            btn.classList.remove("is-loading"); btn.disabled = false;
          }
        });
      },
    });
  }

  // ===========================================================================
  // PAGE: Settings — every section maps to a real backend write:
  //   Business   -> PATCH /workspaces/{id}                 (name, timezone)
  //   Clinic Info / Scheduling / Emergency / AI  -> PUT /workspaces/{id}/clinic-settings
  //   Team       -> GET/POST /workspaces/{id}/members
  // ===========================================================================
  const SETTINGS_TABS = [
    { id: "business", label: "Business" },
    { id: "clinic", label: "Clinic info & FAQs" },
    { id: "scheduling", label: "Scheduling" },
    { id: "emergency", label: "Emergency" },
    { id: "ai", label: "AI preferences" },
    { id: "integrations", label: "Integrations" },
    { id: "team", label: "Team" },
  ];
  const AGENT_TONES = ["Professional", "Empathetic", "Friendly"];
  const AGENT_LANGUAGES = ["English", "Urdu", "Roman Urdu", "Punjabi", "Saraiki", "Sindhi", "Pashto"];
  const ADDR_SEG = " · ";
  const ADDRESS_MAX = 500;

  function parseAddr(str) {
    const parts = String(str || "").split(ADDR_SEG).map((p) => p.trim()).filter(Boolean);
    const faqs = [], rest = [];
    parts.forEach((p) => {
      const m = /^FAQ:\s*(.+)$/i.exec(p);
      if (m) { const bits = m[1].split(" — "); faqs.push({ q: (bits[0] || "").trim(), a: bits.slice(1).join(" — ").trim() }); }
      else rest.push(p);
    });
    return { base: rest.join(ADDR_SEG), faqs };
  }
  function composeAddr(base, faqs) {
    const segs = [String(base || "").trim()].filter(Boolean);
    (faqs || []).forEach((f) => { if (f.q && f.a) segs.push(`FAQ: ${f.q} — ${f.a}`); });
    return segs.join(ADDR_SEG);
  }

  function renderSettingsPage(container, sub) {
    const active = SETTINGS_TABS.some((t) => t.id === sub) ? sub : "business";
    container.innerHTML = `
      <div class="page-header"><div><div class="page-header__title">Settings</div><div class="page-header__subtitle">Manage your workspace and the AI agent's knowledge base.</div></div></div>
      <div class="settings-shell">
        <nav class="settings-nav" id="settings-nav" aria-label="Settings sections">
          ${SETTINGS_TABS.map((t) => `<button type="button" data-tab="${t.id}" class="${t.id === active ? "is-active" : ""}"${t.id === active ? ' aria-current="page"' : ""}>${escapeHtml(t.label)}</button>`).join("")}
        </nav>
        <div class="settings-panel" id="settings-panel"></div>
      </div>`;
    $$("#settings-nav button", container).forEach((b) =>
      b.addEventListener("click", () => navigate(`settings/${b.dataset.tab}`)));

    const panel = $("#settings-panel", container);
    ({
      business: settingsBusiness, clinic: settingsClinicInfo, scheduling: settingsScheduling,
      emergency: settingsEmergency, ai: settingsAi, integrations: settingsIntegrations, team: settingsTeam,
    }[active] || settingsBusiness)(panel);
  }

  function settingsCard(title, desc, inner) {
    return `<div class="card">
      <div class="settings-card__title">${escapeHtml(title)}</div>
      ${desc ? `<div class="settings-card__desc">${escapeHtml(desc)}</div>` : ""}
      ${inner}</div>`;
  }
  function saveBar(id) {
    return `<div class="field__error" id="${id}-err" role="alert" hidden></div>
      <div class="settings-actions">
        <button class="btn btn--primary" id="${id}-save"><span class="spinner"></span><span class="btn__label">Save changes</span></button>
        <span class="settings-actions__saved" id="${id}-saved" role="status">${ICONS.check} Saved</span>
      </div>`;
  }
  function wireSave(panel, id, validate, doSave) {
    const err = $(`#${id}-err`, panel);
    const btn = $(`#${id}-save`, panel);
    const saved = $(`#${id}-saved`, panel);
    const showErr = (m) => { if (!m) { err.hidden = true; err.textContent = ""; } else { err.hidden = false; err.textContent = m; } };
    btn.addEventListener("click", async () => {
      showErr("");
      if (saved) saved.classList.remove("is-visible");
      const v = validate ? validate() : null;
      if (v) { showErr(v); return; }
      btn.classList.add("is-loading"); btn.disabled = true;
      try {
        await doSave();
        toast({ title: "Saved", tone: "success" });
        if (saved) { saved.classList.add("is-visible"); setTimeout(() => saved.classList.remove("is-visible"), 2500); }
      }
      catch (e) { showErr(e instanceof Api.ApiError ? e.message : (e.message || "Couldn't save.")); toast({ title: "Couldn't save", tone: "error" }); }
      finally { btn.classList.remove("is-loading"); btn.disabled = false; }
    });
  }

  // -- Business ----------------------------------------------------------------
  function settingsBusiness(panel) {
    loadInto(panel, {
      skeleton: skeletonRows(4, 2),
      fetcher: () => Api.workspaces.get(state.workspace.id),
      render: (ws) => {
        state.workspace = ws;
        panel.innerHTML = settingsCard("Business", "Your organisation's name and operating timezone.", `
          <div class="field"><label class="field__label" for="s-ws-name">Clinic / business name</label>
            <input class="input" id="s-ws-name" value="${escapeHtml(ws.name)}" maxlength="255" /></div>
          <div class="field" style="margin-top:14px;"><label class="field__label">Timezone</label>
            <div id="s-ws-tz"></div>
            <div class="field__hint">Worldwide IANA timezone. Every appointment time, dashboard "today" and the reminder job use it; DST is automatic.</div></div>
          <div class="field" style="margin-top:14px;"><label class="field__label">Workspace slug</label>
            <input class="input" value="${escapeHtml(ws.slug)}" disabled /></div>
          ${saveBar("s-ws")}`);
        const tz = TZ.createPicker({ value: ws.timezone, detected: TZ.detect() });
        $("#s-ws-tz", panel).appendChild(tz);
        wireSave(panel, "s-ws",
          () => {
            if (!$("#s-ws-name", panel).value.trim()) return "Name can't be empty.";
            if (!TZ.isValid(tz.getValue())) return "Pick a valid timezone.";
            return null;
          },
          async () => {
            const updated = await Api.workspaces.update(ws.id, { name: $("#s-ws-name", panel).value.trim(), timezone: tz.getValue() });
            state.workspace = updated;
            tz.setValue(updated.timezone);
          });
      },
    });
  }

  // -- Clinic info & FAQs (all of general_info + composed FAQ segments) --------
  function settingsClinicInfo(panel) {
    loadInto(panel, {
      skeleton: skeletonRows(5, 2),
      cacheKey: "clinicConfig",
      fetcher: () => ClinicConfig.get(),
      render: (cs) => {
        const gi = cs.general_info || {};
        const parsed = parseAddr(gi.address || "");
        let faqs = parsed.faqs.slice();
        let pays = (gi.accepted_payment_methods || []).slice(); if (!pays.length) pays = [""];

        panel.innerHTML = settingsCard("Clinic info & FAQs", "Public details the AI agent can share with callers.", `
          <div class="field"><label class="field__label" for="s-addr">Address & contact</label>
            <textarea class="textarea" id="s-addr" maxlength="${ADDRESS_MAX}" placeholder="12 Clinic Road, City · Phone: … · Hours: Mon–Sat 9–9">${escapeHtml(parsed.base)}</textarea>
            <div class="field__hint" id="s-addr-count"></div></div>
          <div class="field" style="margin-top:14px;"><label class="field__label" for="s-maps">Google Maps link</label>
            <input class="input" id="s-maps" maxlength="500" value="${escapeHtml(gi.google_maps_link || "")}" placeholder="https://maps.google.com/…" /></div>
          <div class="field" style="margin-top:14px;"><label class="field__label" for="s-parking">Parking</label>
            <select class="select" id="s-parking">
              <option value=""${gi.parking_available == null ? " selected" : ""}>Not specified</option>
              <option value="yes"${gi.parking_available === true ? " selected" : ""}>Available on site</option>
              <option value="no"${gi.parking_available === false ? " selected" : ""}>Not available</option>
            </select></div>
          <div class="field" style="margin-top:14px;"><label class="field__label">Accepted payment methods</label>
            <div id="s-pays"></div>
            <button class="btn btn--ghost btn--sm" id="s-pay-add">${ICONS.plus} Add method</button></div>
          <div class="divider"></div>
          <div class="settings-card__title" style="font-size:13px;">FAQs</div>
          <div class="settings-card__desc">Common questions callers ask. Stored with the address text (combined limit ${ADDRESS_MAX} characters).</div>
          <div id="s-faqs"></div>
          <button class="btn btn--secondary btn--sm" id="s-faq-add">${ICONS.plus} Add FAQ</button>
          ${saveBar("s-ci")}`);

        const paint = () => {
          $("#s-pays", panel).innerHTML = pays.map((p, i) => `
            <div class="inline-row" data-pay="${i}">
              <div class="field"><input class="input" data-f value="${escapeHtml(p)}" placeholder="Cash / Card / Insurance" aria-label="Payment method ${i + 1}" /></div>
              <button class="btn btn--ghost btn--sm" data-rm aria-label="Remove payment method ${i + 1}" title="Remove">${ICONS.trash}</button>
            </div>`).join("");
          $$("#s-pays [data-pay]", panel).forEach((row) => {
            const i = Number(row.dataset.pay);
            $("[data-f]", row).addEventListener("input", (e) => { pays[i] = e.target.value; });
            $("[data-rm]", row).addEventListener("click", () => { pays.splice(i, 1); if (!pays.length) pays = [""]; paint(); updateCount(); });
          });
          $("#s-faqs", panel).innerHTML = faqs.length ? faqs.map((f, i) => `
            <div class="repeat-row" data-faq="${i}">
              <div class="repeat-row__head"><span class="repeat-row__title">FAQ ${i + 1}</span>
                <button class="btn btn--ghost btn--sm" data-rm aria-label="Delete FAQ ${i + 1}" title="Delete">${ICONS.trash}</button></div>
              <div class="field"><label class="field__label" for="s-faq-q${i}">Question</label><input class="input" id="s-faq-q${i}" data-q value="${escapeHtml(f.q)}" /></div>
              <div class="field" style="margin-top:8px;"><label class="field__label" for="s-faq-a${i}">Answer</label><textarea class="textarea" id="s-faq-a${i}" data-a>${escapeHtml(f.a)}</textarea></div>
            </div>`).join("") : `<div class="field__hint" style="margin-bottom:8px;">No FAQs yet.</div>`;
          $$("#s-faqs [data-faq]", panel).forEach((row) => {
            const i = Number(row.dataset.faq);
            $("[data-q]", row).addEventListener("input", (e) => { faqs[i].q = e.target.value; updateCount(); });
            $("[data-a]", row).addEventListener("input", (e) => { faqs[i].a = e.target.value; updateCount(); });
            $("[data-rm]", row).addEventListener("click", () => { faqs.splice(i, 1); paint(); updateCount(); });
          });
        };
        const composedNow = () => composeAddr($("#s-addr", panel).value, faqs.filter((f) => f.q.trim() && f.a.trim()));
        const updateCount = () => {
          const n = composedNow().length;
          const el = $("#s-addr-count", panel);
          el.textContent = `${n}/${ADDRESS_MAX} characters (address + FAQs, one backend field)`;
          el.style.color = n > ADDRESS_MAX ? "var(--danger)" : "";
        };
        $("#s-addr", panel).addEventListener("input", updateCount);
        $("#s-pay-add", panel).addEventListener("click", () => { pays.push(""); paint(); });
        $("#s-faq-add", panel).addEventListener("click", () => { faqs.push({ q: "", a: "" }); paint(); updateCount(); });
        paint(); updateCount();

        wireSave(panel, "s-ci",
          () => {
            if (composedNow().length > ADDRESS_MAX) return `Address + FAQ text is too long (${composedNow().length}/${ADDRESS_MAX}).`;
            for (const f of faqs) { if ((f.q.trim() && !f.a.trim()) || (!f.q.trim() && f.a.trim())) return "Every FAQ needs both a question and an answer."; }
            return null;
          },
          async () => {
            const parking = $("#s-parking", panel).value;
            await ClinicConfig.save({
              general_info: {
                address: composedNow() || null,
                google_maps_link: $("#s-maps", panel).value.trim() || null,
                parking_available: parking === "yes" ? true : parking === "no" ? false : null,
                accepted_payment_methods: pays.map((p) => p.trim()).filter(Boolean),
              },
            });
          });
      },
    });
  }

  // -- Scheduling ------------------------------------------------------------
  function settingsScheduling(panel) {
    loadInto(panel, {
      skeleton: skeletonRows(2, 2),
      cacheKey: "clinicConfig",
      fetcher: () => ClinicConfig.get(),
      render: (cs) => {
        const a = cs.appointment_settings || {};
        panel.innerHTML = settingsCard("Scheduling", "How the AI agent books appointments.", `
          <div class="form-grid">
            <div class="field"><label class="field__label" for="s-slot">Default slot duration (minutes)</label>
              <input class="input" id="s-slot" type="number" min="5" max="480" step="5" value="${escapeHtml(String(a.default_slot_duration_minutes ?? 30))}" /></div>
            <div class="field"><label class="field__label" for="s-max">Maximum daily bookings</label>
              <input class="input" id="s-max" type="number" min="1" max="1000" step="1" value="${a.max_daily_bookings != null ? escapeHtml(String(a.max_daily_bookings)) : ""}" placeholder="No limit" /></div>
          </div>
          ${saveBar("s-sc")}`);
        wireSave(panel, "s-sc",
          () => {
            const slot = toNum($("#s-slot", panel).value);
            if (slot == null || Number.isNaN(slot) || slot < 5 || slot > 480) return "Slot duration must be 5–480 minutes.";
            const max = toNum($("#s-max", panel).value);
            if (Number.isNaN(max)) return "Maximum daily bookings must be a number.";
            if (max != null && (max < 1 || max > 1000)) return "Maximum daily bookings must be 1–1000.";
            return null;
          },
          async () => {
            const max = toNum($("#s-max", panel).value);
            await ClinicConfig.save({
              appointment_settings: {
                default_slot_duration_minutes: Math.round(toNum($("#s-slot", panel).value)),
                max_daily_bookings: max == null || Number.isNaN(max) ? null : Math.round(max),
              },
            });
          });
      },
    });
  }

  // -- Emergency ----------------------------------------------------------
  function settingsEmergency(panel) {
    loadInto(panel, {
      skeleton: skeletonRows(3, 1),
      cacheKey: "clinicConfig",
      fetcher: () => ClinicConfig.get(),
      render: (cs) => {
        panel.innerHTML = settingsCard("Emergency protocol",
          "The exact instructions the AI agent follows when a caller reports a medical emergency.", `
          <div class="field"><label class="field__label" for="s-emg">Instructions</label>
            <textarea class="textarea" id="s-emg" style="min-height:150px;" maxlength="2000" required aria-required="true" placeholder="e.g. Tell the caller to call local emergency services immediately, do not book an appointment, then transfer to on-call staff.">${escapeHtml(cs.emergency_protocol || "")}</textarea></div>
          ${saveBar("s-emg")}`);
        wireSave(panel, "s-emg",
          () => (!$("#s-emg", panel).value.trim() ? "Please describe the emergency protocol." : null),
          () => ClinicConfig.save({ emergency_protocol: $("#s-emg", panel).value.trim() }));
      },
    });
  }

  // -- AI preferences ---------------------------------------------------
  function settingsAi(panel) {
    loadInto(panel, {
      skeleton: skeletonRows(2, 2),
      cacheKey: "clinicConfig",
      fetcher: () => ClinicConfig.get(),
      render: (cs) => {
        panel.innerHTML = settingsCard("AI preferences", "How the agent sounds and the language it opens with.", `
          <div class="form-grid">
            <div class="field"><label class="field__label" for="s-tone">Tone</label>
              <select class="select" id="s-tone">${AGENT_TONES.map((t) => `<option${(cs.agent_tone || "Professional") === t ? " selected" : ""}>${t}</option>`).join("")}</select></div>
            <div class="field"><label class="field__label" for="s-lang">Preferred language</label>
              <select class="select" id="s-lang">${AGENT_LANGUAGES.map((l) => `<option${(cs.preferred_language || "English") === l ? " selected" : ""}>${l}</option>`).join("")}</select></div>
          </div>
          <div class="field__hint" style="margin-top:10px;">The agent still follows a caller who clearly switches to another supported language.</div>
          ${saveBar("s-ai")}`);
        wireSave(panel, "s-ai", null,
          () => ClinicConfig.save({ agent_tone: $("#s-tone", panel).value, preferred_language: $("#s-lang", panel).value }));
      },
    });
  }

  // -- Integrations ----------------------------------------------------
  function settingsIntegrations(panel) {
    let pollTimer = null;
    let pollDeadline = 0;
    onPageLeave(() => { if (pollTimer) clearInterval(pollTimer); });

    const membership = (state.memberships || []).find((m) => m.workspace_id === state.workspace?.id);
    const canManage = Boolean(state.user?.is_super_admin || ["owner", "admin"].includes(membership?.role));

    const paint = (google) => {
      const connected = Boolean(google.connected);
      const connecting = google.status === "connecting";
      const label = connected ? "Connected" : (connecting ? "Connecting" : "Disconnected");
      const tone = connected ? "ok" : "warn";
      const calendarName = google.calendar_name || google.calendar_id || "Google Calendar";
      panel.innerHTML = settingsCard(
        "Integrations",
        "Connect this workspace to the clinic owner's Google Calendar.",
        `<div class="integration-card">
          <div class="integration-card__top">
            <div class="integration-card__icon" aria-hidden="true"><strong style="font-size:20px;color:#4285f4;">G</strong></div>
            <div class="integration-card__meta" style="flex:1;">
              <div class="integration-card__name">Google Calendar</div>
              <div class="integration-card__category">Appointment availability and event sync</div>
            </div>
            <span class="status-pill status-pill--${tone}"><span class="status-pill__dot"></span>${escapeHtml(label)}</span>
          </div>
          <div class="integration-card__detail">${connected ? `Calendar: <strong>${escapeHtml(calendarName)}</strong>${google.auth_type === "service_account" ? " · Service-account connection" : ""}` : "No Google account is connected to this workspace."}</div>
          <div style="display:flex;gap:8px;align-items:center;">
            ${canManage ? (connected
              ? `<button class="btn btn--secondary btn--sm" id="google-disconnect">Disconnect</button>${google.auth_type === "service_account" ? `<button class="btn btn--primary btn--sm" id="google-connect">Connect clinic Google account</button>` : ""}`
              : `<button class="btn btn--primary btn--sm" id="google-connect"${connecting ? " disabled" : ""}>${connecting ? "Waiting for Google…" : "Connect Google Calendar"}</button>`)
              : `<span class="field__hint">Only workspace owners and admins can change integrations.</span>`}
          </div>
        </div>`
      );

      const connect = $("#google-connect", panel);
      if (connect) connect.addEventListener("click", async () => {
        const popup = window.open("about:blank", "google-calendar-oauth", "width=560,height=720,resizable=yes,scrollbars=yes");
        connect.disabled = true;
        try {
          const result = await Api.integrations.googleConnect();
          if (!popup) throw new Error("Your browser blocked the Google sign-in popup. Allow popups and try again.");
          popup.location.href = result.authorization_url;
          pollDeadline = Date.now() + 120000;
          pollTimer = setInterval(async () => {
            if (Date.now() > pollDeadline) {
              clearInterval(pollTimer); pollTimer = null;
              toast({ title: "Connection timed out", text: "Try connecting Google Calendar again.", tone: "warning" });
              return;
            }
            try {
              const latest = await Api.integrations.googleStatus();
              if (latest.connected) {
                clearInterval(pollTimer); pollTimer = null;
                toast({ title: "Google Calendar connected", text: latest.calendar_name || "Calendar sync is active.", tone: "success" });
                paint(latest);
              }
            } catch { /* keep polling while the consent window is active */ }
          }, 1500);
        } catch (err) {
          if (popup && !popup.closed) popup.close();
          connect.disabled = false;
          toast({ title: "Couldn't connect Google Calendar", text: err.message || "Try again.", tone: "error" });
        }
      });

      const disconnect = $("#google-disconnect", panel);
      if (disconnect) disconnect.addEventListener("click", async () => {
        if (!window.confirm("Disconnect Google Calendar for this workspace? Existing appointments will remain saved.")) return;
        disconnect.disabled = true;
        try {
          await Api.integrations.googleDisconnect();
          toast({ title: "Google Calendar disconnected", tone: "info" });
          paint({ connected: false, status: "disconnected" });
        } catch (err) {
          disconnect.disabled = false;
          toast({ title: "Couldn't disconnect", text: err.message || "Try again.", tone: "error" });
        }
      });
    };

    loadInto(panel, {
      skeleton: skeletonRows(3, 1),
      fetcher: () => Api.integrations.googleStatus(),
      render: paint,
    });
  }

  // -- Team -----------------------------------------------------------
  function settingsTeam(panel) {
    panel.innerHTML = `
      <div class="card">
        <div class="settings-card__title">Team</div>
        <div class="settings-card__desc">People who can sign in to this workspace.</div>
        <div style="margin:0 0 14px;"><button class="btn btn--primary btn--sm" id="s-team-invite">${ICONS.plus} Invite member</button></div>
        <div id="s-team-mount"></div>
      </div>`;
    mountTeam($("#s-team-mount", panel), $("#s-team-invite", panel));
  }

  // ===========================================================================
  // Notifications dropdown content
  // ===========================================================================
  async function paintNotifDropdown() {
    const list = $("#notif-list");
    list.innerHTML = `<div style="padding:14px;">${skeletonRows(4, 1)}</div>`;
    const epoch = state.wsEpoch;
    let messages;
    try {
      messages = state.cache.notifications || await Api.notificationMessages.list();
      if (epoch !== state.wsEpoch) return; // switched workspace mid-fetch
      state.cache.notifications = messages;
    } catch (err) {
      list.innerHTML = `<div class="notif-item"><div class="notif-item__title">Couldn't load notifications</div><div class="notif-item__time">${escapeHtml(err.message || "")}</div></div>`;
      return;
    }
    if (!messages || !messages.length) {
      list.innerHTML = `<div class="notif-item"><div class="notif-item__title">No notifications yet</div><div class="notif-item__time">Delivery activity will appear here.</div></div>`;
      return;
    }
    const rows = messages
      .slice()
      .sort((a, b) => new Date(b.created_at || b.sent_at || 0) - new Date(a.created_at || a.sent_at || 0))
      .slice(0, 8);
    list.innerHTML = rows.map((m) => {
      const kind = (m.event_type || "notification").replace(/_/g, " ");
      const via = (m.channel || "").toUpperCase();
      const statusTone = STATUS_TONE[m.status] || "muted";
      return `<div class="notif-item">
        <div class="notif-item__title">${escapeHtml(kind)} ${badge(m.status || "pending", statusTone)}</div>
        <div class="notif-item__time">${escapeHtml(via)}${m.recipient ? ` · ${escapeHtml(m.recipient)}` : ""} · ${escapeHtml(timeAgo(m.created_at || m.sent_at))}</div>
      </div>`;
    }).join("");
  }

  // ===========================================================================
  // Router / page switching
  // ===========================================================================
  const PAGE_RENDERERS = {
    overview: renderOverview,
    appointments: renderAppointmentsPage,
    patients: renderPatientsPage,
    leads: renderLeadsPage,
    "ai-receptionist": renderAiReceptionistPage,
    "live-calls": renderLiveCalls,
    "call-history": renderCallHistoryPage,
    analytics: renderAnalyticsPage,
    doctors: renderDoctorsPage,
    services: renderServicesPage,
    branches: renderBranchesPage,
    team: renderTeamPage,
    settings: renderSettingsPage,
  };

  function buildSidebar() {
    $("#sidebar-nav").innerHTML = NAV_GROUPS.map((group) => `
      <div class="nav-group" role="group"${group.label ? ` aria-label="${escapeHtml(group.label)}"` : ""}>
        ${group.label ? `<div class="nav-group__label" aria-hidden="true">${escapeHtml(group.label)}</div>` : ""}
        ${group.items.map((p) => `
          <button type="button" class="nav-item" data-page="${p.id}">
            <span class="nav-item__icon" aria-hidden="true">${p.icon}</span>
            <span class="nav-item__label">${escapeHtml(p.label)}</span>
          </button>`).join("")}
      </div>`).join("");
    $$(".nav-item", $("#sidebar-nav")).forEach((n) => n.addEventListener("click", () => navigate(n.dataset.page)));
  }

  function parseRoute(raw) {
    const parts = String(raw || "").replace(/^#\/?/, "").split("/").filter(Boolean);
    return { page: parts[0] || "overview", sub: parts[1] || null };
  }
  function routeToHash({ page, sub }) { return `#/${page}${sub ? `/${sub}` : ""}`; }

  // ===========================================================================
  // Route guard — WORKSPACE-AWARE onboarding gate (Phase 8).
  //
  // Every route render passes through enforceGuard() FIRST. Onboarding is a
  // property of a WORKSPACE (Workspace.is_onboarded), never of the user, so the
  // guard NEVER does "if user not onboarded -> redirect to setup". Instead it
  // classifies the requested route and only forces setup for a route that
  // needs an onboarded workspace while the *selected* workspace isn't.
  //
  // Route categories:
  //   A  PUBLIC             — login / signup. The auth screen isn't a hash
  //                           route; it's the `!isAuthenticated()` branch.
  //   B  WORKSPACE MGMT     — Branch Management (#/branches) and the setup-model
  //                           selection (#/get-started). Workspace creation and
  //                           switching happen here (modal + switcher). ALWAYS
  //                           reachable once authenticated — even if every
  //                           workspace has is_onboarded === false — because the
  //                           user needs this to set pending branches up.
  //   C  WORKSPACE ONBOARDING — the setup wizard (#/onboarding), scoped to the
  //                           selected branch. Reachable only while that branch
  //                           is NOT onboarded.
  //   D  WORKSPACE APP      — #/overview, #/appointments, #/settings, … Require
  //                           the selected workspace's is_onboarded === true;
  //                           otherwise redirect to that workspace's setup.
  //
  // (This SPA carries one active workspace id in localStorage rather than a
  //  /workspaces/:id/… path segment, so ":workspaceId" in the spec maps to the
  //  currently-selected workspace — state.workspace / Api.getWorkspaceId().)
  //
  // Because this runs on boot, on every hashchange, and inside navigate(), the
  // gate holds through refresh, direct-URL entry, a new tab and session
  // restoration — a Category D DOM is never shown for a non-onboarded
  // workspace, not merely hidden.
  // ===========================================================================
  const POST_LOGIN_HASH_KEY = "ar_post_login_hash";
  const ONBOARDING_HASH = "#/onboarding";
  const GET_STARTED_HASH = "#/get-started";
  const BRANCHES_HASH = "#/branches";
  let routingInited = false;

  // Page-scoped teardown. A renderer that starts a timer / subscription
  // registers a cleanup here; renderRoute() runs and clears them all before it
  // mounts the next page, so nothing from the previous page (or previous
  // workspace) keeps ticking against the new view.
  let pageCleanups = [];
  function onPageLeave(fn) { if (typeof fn === "function") pageCleanups.push(fn); }
  function runPageCleanups() {
    const fns = pageCleanups;
    pageCleanups = [];
    fns.forEach((fn) => { try { fn(); } catch { /* ignore */ } });
  }

  // Onboarding is a property of the ACTIVE WORKSPACE, not the user
  // (Workspace.is_onboarded — see backend app/api/deps.py
  // get_current_onboarded_tenant). A user may have onboarded workspace A
  // but not a freshly-created workspace B.
  function isOnboarded() { return Boolean(state.workspace && state.workspace.is_onboarded); }
  function hasWorkspaces() { return (state.workspaces || []).length > 0; }
  // Multi-branch mode: chosen explicitly on the get-started screen, or the
  // user simply owns more than one workspace/branch.
  function isMultiBranch() {
    return Api.getBranchModel() === "multi" || (state.workspaces || []).length >= 2;
  }

  // Category B — workspace management. Never onboarding-gated.
  const ROUTE_CATEGORY_B = new Set(["branches", "get-started"]);
  // Category C — the selected workspace's onboarding wizard.
  const ROUTE_CATEGORY_C = new Set(["onboarding"]);
  // Category D — everything else that renders workspace data: requires the
  // selected workspace's is_onboarded === true.
  function routeRequiresOnboardedWorkspace(page) {
    return !ROUTE_CATEGORY_B.has(page) && !ROUTE_CATEGORY_C.has(page);
  }

  // Route guard. Order: A auth -> setup-model selection -> B workspace mgmt
  // (always reachable) -> workspace must be selected -> C per-workspace
  // onboarding -> D workspace app (needs that workspace onboarded).
  function enforceGuard(parsed) {
    const page = parsed.page;

    // ---- Category A: public -------------------------------------------------
    if (!Api.isAuthenticated()) return { auth: true };

    // Brand-new user: no workspaces yet AND hasn't picked single/multi. The
    // get-started screen is itself Category B (reachable), but it's only the
    // right destination until a choice exists.
    if (!hasWorkspaces() && !Api.getBranchModel()) {
      return page === "get-started" ? { getStarted: true } : { redirect: GET_STARTED_HASH };
    }
    if (page === "get-started") {
      return { redirect: isMultiBranch() ? BRANCHES_HASH : "#/overview" };
    }

    // ---- Category B: workspace management — ALWAYS reachable, regardless of
    // any workspace's onboarding state. The user manages pending branches here.
    if (page === "branches") return { allow: true };

    // Category C and D are meaningless without a selected workspace.
    if (!state.workspace) return { redirect: BRANCHES_HASH };

    // ---- Category C: the SELECTED workspace's onboarding wizard ------------
    if (ROUTE_CATEGORY_C.has(page)) {
      // Already onboarded -> nothing to do here. Otherwise run the wizard for
      // this specific workspace.
      return isOnboarded() ? { redirect: "#/overview" } : { onboarding: true };
    }

    // ---- Category D: workspace application --------------------------------
    // The ONLY place onboarding is forced: this route needs an onboarded
    // workspace AND the selected workspace isn't. Redirect to *that*
    // workspace's setup (multi-branch users route via Branch Management so
    // they can see/pick which branch to configure).
    if (routeRequiresOnboardedWorkspace(page) && !isOnboarded()) {
      return { redirect: isMultiBranch() ? BRANCHES_HASH : ONBOARDING_HASH };
    }

    return { allow: true };
  }

  function replaceHash(hash) {
    const u = new URL(location.href);
    u.hash = hash;
    if (u.hash !== location.hash) location.replace(u.toString());
  }

  // ===========================================================================
  // Workspace / branch helpers (reuse the EXISTING creation + active-workspace
  // APIs — no duplicate workspace logic, no fake/local workspaces).
  // ===========================================================================
  function slugify(s) {
    return String(s || "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 40) || "branch";
  }
  function randSuffix() { return Math.random().toString(36).slice(2, 7); }

  async function createWorkspace({ name, timezone }) {
    // POST /workspaces — the existing API. It creates the workspace with
    // is_onboarded=false and an owner WorkspaceMember for the caller (tenant
    // validation stays server-side). Retry once or twice on a slug clash.
    const base = slugify(name);
    let lastErr;
    for (let i = 0; i < 3; i++) {
      try {
        return await Api.workspaces.create({
          name,
          slug: `${base}-${randSuffix()}`,
          timezone: timezone || (window.TZ && TZ.detect()) || "UTC",
        });
      } catch (err) {
        lastErr = err;
        if (!(err instanceof Api.ApiError) || err.status !== 409) break;
      }
    }
    throw lastErr;
  }

  function setActiveWorkspace(w) {
    if (!w) return;
    const changed = !state.workspace || state.workspace.id !== w.id;
    state.workspace = w;
    Api.setWorkspaceId(w.id);            // existing active-workspace mechanism
    // NO CROSS-WORKSPACE LEAKAGE: every page's data is cached in state.cache
    // under plain keys (overview / leads / patients / appointments / calls /
    // clinicConfig / team / analytics:* / notifications). Wipe it all on a
    // switch so nothing from the previous branch can render for the new one —
    // the next renderRoute() refetches for w.id via Api.workspacePath().
    if (changed) { state.cache = {}; state.wsEpoch++; }
    updateWorkspaceSwitcher();
  }

  // ===========================================================================
  // Get-started: single vs multiple branch selection (new users only)
  // ===========================================================================
  let getStartedMounted = false;
  function teardownGetStarted() {
    getStartedMounted = false;
    const gs = getStartedScreenEl();
    if (gs) { gs.hidden = true; gs.innerHTML = ""; }
  }

  function showGetStartedRoute() {
    const gs = getStartedScreenEl();
    if (!gs) return;
    $("#auth-screen").hidden = true;
    $("#app-shell").hidden = true;
    const ob = onboardScreenEl(); if (ob) ob.hidden = true;
    gs.hidden = false;
    if (getStartedMounted) return;
    getStartedMounted = true;

    const first = (state.user?.full_name || "there").split(" ")[0];
    gs.innerHTML = `
      <div class="auth-card getstarted-card">
        <div class="auth-brand"><span class="auth-brand__mark">AR</span><span class="auth-brand__name">AI Receptionist</span></div>
        <h1 class="auth-title">Welcome, ${escapeHtml(first)}</h1>
        <p class="auth-subtitle">How do you want to manage your business?</p>
        <div class="auth-error" id="gs-error" role="alert"></div>
        <div class="choice-grid">
          <button type="button" class="choice-card" id="gs-single">
            <span class="choice-card__icon" aria-hidden="true">${ICONS.branches}</span>
            <span class="choice-card__title">Single Branch</span>
            <span class="choice-card__desc">Manage one location.</span>
          </button>
          <button type="button" class="choice-card" id="gs-multi">
            <span class="choice-card__icon" aria-hidden="true">${ICONS.branches}</span>
            <span class="choice-card__title">Multiple Branches</span>
            <span class="choice-card__desc">Manage multiple locations.</span>
          </button>
        </div>
        <p class="auth-footer">Wrong account? <button type="button" id="gs-signout">Sign out</button></p>
      </div>`;

    $("#gs-single", gs).addEventListener("click", chooseSingle);
    $("#gs-multi", gs).addEventListener("click", chooseMulti);
    $("#gs-signout", gs).addEventListener("click", logout);
  }

  async function chooseSingle() {
    const single = $("#gs-single"), multi = $("#gs-multi");
    if (single.classList.contains("is-loading")) return;
    const err = $("#gs-error"); err.classList.remove("is-visible");
    single.classList.add("is-loading"); multi.disabled = true;
    try {
      const name = `${(state.user?.full_name || "My").split(" ")[0]}'s Clinic`;
      const ws = await createWorkspace({ name });          // real workspace, is_onboarded=false
      Api.setBranchModel("single");
      state.workspaces = [ws];
      setActiveWorkspace(ws);
      teardownGetStarted();
      navigate("onboarding");                              // 8-step wizard, against THIS workspace
    } catch (e) {
      single.classList.remove("is-loading"); multi.disabled = false;
      err.textContent = (e && e.message) || "Couldn't create your workspace. Please try again.";
      err.classList.add("is-visible");
    }
  }

  function chooseMulti() {
    Api.setBranchModel("multi");
    teardownGetStarted();
    navigate("branches");                                  // Branch Management — NOT forced into onboarding
  }

  function showOnboardingRoute() {
    // Full-screen wizard — neither the auth screen nor the app shell.
    if (window.ClinicOnboarding && ClinicOnboarding.isActive()) { showOnboardScreen(); return; }
    if (!window.ClinicOnboarding) return;
    showOnboardScreen();
    const multi = isMultiBranch();
    ClinicOnboarding.start({
      user: state.user,
      // The branch being configured — the selected workspace, not merely
      // whatever id is in localStorage. setActiveWorkspace() keeps the two in
      // sync, but pass the object's id so the wizard is unambiguous.
      workspaceId: state.workspace ? state.workspace.id : Api.getWorkspaceId(),
      workspaceName: state.workspace ? state.workspace.name : undefined,
      workspaceOnboarded: Boolean(state.workspace && state.workspace.is_onboarded),
      // A multi-branch user can step back to pick a different branch; a
      // single-branch user's only escape from mandatory setup is signing out.
      exitLabel: multi ? "← Branches" : "Sign out",
      onComplete: () => {
        // Backend has flipped THIS WORKSPACE's is_onboarded — mirror it
        // locally (active workspace + the branch list) and release the gate.
        state.workspace = { ...(state.workspace || {}), is_onboarded: true };
        const wsId = state.workspace.id;
        state.workspaces = (state.workspaces || []).map((w) => (w.id === wsId ? { ...w, is_onboarded: true } : w));
        state.cache = {};
        updateWorkspaceSwitcher();
        toast({ title: "Setup complete", text: "This branch is ready.", tone: "success" });
        const back = sessionStorage.getItem(POST_LOGIN_HASH_KEY);
        sessionStorage.removeItem(POST_LOGIN_HASH_KEY);
        navigate(back && parseRoute(back).page !== "onboarding" ? back : "overview");
      },
      onExit: multi ? () => navigate("branches") : () => logout(),
    });
  }

  // The URL hash is the single source of truth. `navigate()` only writes the
  // hash; `renderRoute()` (driven by the hashchange event, and once on boot)
  // is the only thing that paints — so tab/page state can't desync, and
  // browser back/forward Just Works.
  const PSEUDO_ROUTES = new Set(["onboarding", "get-started"]);
  function navigate(route) {
    let { page, sub } = parseRoute(route);
    if (!PSEUDO_ROUTES.has(page) && !PAGE_RENDERERS[page]) { page = "overview"; sub = null; }
    const hash = routeToHash({ page, sub });
    if (location.hash === hash) renderRoute(hash);
    else location.hash = hash; // fires "hashchange" -> renderRoute
  }

  function renderRoute(raw) {
    let { page, sub } = parseRoute(raw);
    const verdict = enforceGuard({ page, sub });

    // Stop the outgoing page's timers/subscriptions on ANY transition (incl.
    // to the auth / onboarding / get-started screens), not just page-to-page.
    runPageCleanups();

    if (verdict.auth) {
      if (page && page !== "onboarding" && PAGE_RENDERERS[page]) {
        sessionStorage.setItem(POST_LOGIN_HASH_KEY, routeToHash({ page, sub }));
      }
      showAuthScreen();
      return;
    }
    if (verdict.redirect) {
      // Rewrite the URL without a history entry, then render synchronously —
      // don't depend on the hashchange event firing for a replace().
      if (location.hash !== verdict.redirect) replaceHash(verdict.redirect);
      renderRoute(verdict.redirect);
      return;
    }
    if (verdict.getStarted) {
      state.currentPage = "get-started";
      showGetStartedRoute();
      return;
    }
    if (verdict.onboarding) {
      state.currentPage = "onboarding";
      showOnboardingRoute();
      return;
    }

    // ---- Guarded dashboard routing --------------------------------------
    if (window.ClinicOnboarding && ClinicOnboarding.isActive()) ClinicOnboarding.teardown();
    showAppShell();
    if (!PAGE_RENDERERS[page]) { page = "overview"; sub = null; }
    state.currentPage = page;
    $$(".nav-item").forEach((n) => {
      const on = n.dataset.page === page;
      n.classList.toggle("is-active", on);
      if (on) n.setAttribute("aria-current", "page"); else n.removeAttribute("aria-current");
    });
    $$(".page").forEach((p) => p.classList.toggle("is-active", p.dataset.page === page));
    $("#page-title").textContent = PAGE_META.find((p) => p.id === page)?.label || "Overview";
    PAGE_RENDERERS[page]($(`#page-${page}`), sub);
    closeMobileDrawer();
  }

  function initRouting() {
    if (!routingInited) {
      window.addEventListener("hashchange", () => renderRoute(location.hash));
      routingInited = true;
    }
    renderRoute(location.hash || "#/overview");
  }

  // ===========================================================================
  // Sidebar collapse / mobile drawer
  // ===========================================================================
  // Mobile drawer state lives on #app-shell.is-mobile-open; body scroll is
  // locked while it's open. `MOBILE_MQ` matches the same 860px breakpoint
  // the stylesheet uses for the off-canvas sidebar.
  const MOBILE_MQ = window.matchMedia("(max-width: 860px)");
  function isMobileViewport() { return MOBILE_MQ.matches; }
  function openMobileDrawer() {
    if (!isMobileViewport()) return;
    $("#app-shell").classList.add("is-mobile-open");
    document.body.classList.add("is-drawer-open");
    $("#mobile-menu-btn")?.setAttribute("aria-expanded", "true");
  }
  function closeMobileDrawer() {
    $("#app-shell").classList.remove("is-mobile-open");
    document.body.classList.remove("is-drawer-open");
    $("#mobile-menu-btn")?.setAttribute("aria-expanded", "false");
  }
  function toggleMobileDrawer() {
    if ($("#app-shell").classList.contains("is-mobile-open")) closeMobileDrawer();
    else openMobileDrawer();
  }

  function initSidebar() {
    const shell = $("#app-shell");
    if (localStorage.getItem("ar_sidebar_collapsed") === "1") shell.classList.add("is-collapsed");

    $("#collapse-btn").addEventListener("click", () => {
      shell.classList.toggle("is-collapsed");
      localStorage.setItem("ar_sidebar_collapsed", shell.classList.contains("is-collapsed") ? "1" : "0");
    });

    const menuBtn = $("#mobile-menu-btn");
    menuBtn.setAttribute("aria-controls", "sidebar");
    menuBtn.setAttribute("aria-expanded", "false");
    menuBtn.addEventListener("click", (e) => { e.stopPropagation(); toggleMobileDrawer(); });

    // Tap the dimmed backdrop, hit Escape, or tap a nav link (handled in
    // navigate()) to dismiss.
    $("#scrim").addEventListener("click", closeMobileDrawer);
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeMobileDrawer(); });

    // Crossing the breakpoint back to desktop must clear any leftover
    // drawer/scrim state so it can't hang over the restored layout.
    const onBreakpoint = (e) => { if (!e.matches) closeMobileDrawer(); };
    if (MOBILE_MQ.addEventListener) MOBILE_MQ.addEventListener("change", onBreakpoint);
    else MOBILE_MQ.addListener(onBreakpoint); // Safari < 14
  }

  // ===========================================================================
  // Dropdown menus (user / notifications) + global search shortcut
  // ===========================================================================
  function initDropdowns() {
    $("#user-chip-btn").addEventListener("click", (e) => { e.stopPropagation(); toggleDropdown("#user-dropdown"); });
    $("#notif-btn").addEventListener("click", (e) => { e.stopPropagation(); paintNotifDropdown(); toggleDropdown("#notif-dropdown"); $("#notif-dot").style.display = "none"; });
    document.addEventListener("click", closeAllDropdowns);
    $$(".dropdown__item[data-nav]").forEach((b) => b.addEventListener("click", () => navigate(b.dataset.nav)));
    $("#logout-btn").addEventListener("click", logout);

    document.addEventListener("keydown", (e) => {
      if (e.key === "/" && document.activeElement.tagName !== "INPUT" && document.activeElement.tagName !== "TEXTAREA") {
        e.preventDefault(); $("#global-search").focus();
      }
    });
  }
  function toggleDropdown(sel) {
    const d = $(sel);
    const wasOpen = d.classList.contains("is-open");
    closeAllDropdowns();
    if (!wasOpen) d.classList.add("is-open");
  }

  // Topbar branch switcher — only shown when the user has 2+ branches.
  function updateWorkspaceSwitcher() {
    const host = $("#ws-switcher");
    if (!host) return;
    const list = state.workspaces || [];
    if (list.length < 2) { host.hidden = true; host.innerHTML = ""; return; }
    host.hidden = false;
    const active = state.workspace;
    host.innerHTML = `
      <button class="ws-chip" id="ws-chip-btn" aria-haspopup="true" aria-expanded="false" title="Switch branch">
        <span class="ws-chip__icon" aria-hidden="true">${ICONS.branches}</span>
        <span class="ws-chip__name">${escapeHtml(active ? active.name : "Select branch")}</span>
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M6 9l6 6 6-6"/></svg>
      </button>
      <div class="dropdown" id="ws-dropdown">
        <div class="dropdown__header"><strong style="font-size:12px;">Branches</strong></div>
        ${list.map((w) => `<button class="dropdown__item" data-ws="${w.id}">
          <span style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;">${escapeHtml(w.name)}</span>
          ${w.id === (active && active.id) ? `<span class="ws-chip__check" aria-hidden="true">${ICONS.check}</span>` : (w.is_onboarded ? "" : `<span class="badge tone-warning" style="font-size:9.5px;">setup</span>`)}
        </button>`).join("")}
        <div class="dropdown__divider"></div>
        <button class="dropdown__item" data-nav="branches">${ICONS.settings} Manage branches</button>
      </div>`;
    $("#ws-chip-btn", host).addEventListener("click", (e) => { e.stopPropagation(); toggleDropdown("#ws-dropdown"); });
    $$("[data-ws]", host).forEach((b) => b.addEventListener("click", async () => {
      closeAllDropdowns();
      const w = list.find((x) => x.id === b.dataset.ws);
      if (!w || (state.workspace && w.id === state.workspace.id)) return;
      // 1-2. switch active workspace + context, wipe A's cached data, bump the
      // load epoch so any in-flight A request is discarded.
      setActiveWorkspace(w);
      // 5. re-check onboarding from the backend (the list value can be stale if
      // this branch was set up in another tab). Fall back to the list value.
      let fresh = w;
      try { fresh = await Api.workspaces.get(w.id); state.workspace = fresh; } catch { /* keep list value */ }
      state.workspaces = (state.workspaces || []).map((x) => (x.id === fresh.id ? { ...x, ...fresh } : x));
      updateWorkspaceSwitcher();
      // 3-4-6. route into B: its dashboard if onboarded, else B's setup wizard.
      // renderRoute re-runs the page renderer, refetching every panel for B.
      navigate(fresh.is_onboarded ? "overview" : "onboarding");
    }));
    $$("[data-nav]", host).forEach((b) => b.addEventListener("click", () => { closeAllDropdowns(); navigate(b.dataset.nav); }));
  }

  // ===========================================================================
  // Auth flow
  // ===========================================================================
  function onboardScreenEl() { return document.getElementById("onboard-screen"); }
  function getStartedScreenEl() { return document.getElementById("getstarted-screen"); }

  function showAuthScreen() {
    if (window.ClinicOnboarding && ClinicOnboarding.isActive()) ClinicOnboarding.teardown();
    teardownGetStarted();
    const ob = onboardScreenEl(); if (ob) ob.hidden = true;
    $("#auth-screen").hidden = false;
    $("#app-shell").hidden = true;
  }
  function showAppShell() {
    teardownGetStarted();
    const ob = onboardScreenEl(); if (ob) ob.hidden = true;
    $("#auth-screen").hidden = true;
    $("#app-shell").hidden = false;
  }
  function showOnboardScreen() {
    teardownGetStarted();
    $("#auth-screen").hidden = true;
    $("#app-shell").hidden = true;
    const ob = onboardScreenEl(); if (ob) ob.hidden = false;
  }

  function setFormLoading(formPrefix, loading) {
    const btn = $(`#${formPrefix}-submit`);
    btn.classList.toggle("is-loading", loading);
    btn.disabled = loading;
  }
  function showFormError(id, message) {
    const node = $(`#${id}`);
    if (!message) { node.classList.remove("is-visible"); node.textContent = ""; return; }
    node.textContent = message;
    node.classList.add("is-visible");
  }

  // Remember a protected deep link the user hit before authenticating, so we
  // can send them there once login (and, if needed, onboarding) completes.
  function stashIntendedRoute() {
    const { page, sub } = parseRoute(location.hash);
    if (page && page !== "onboarding" && PAGE_RENDERERS[page]) {
      sessionStorage.setItem(POST_LOGIN_HASH_KEY, routeToHash({ page, sub }));
    }
  }

  async function bootSession() {
    if (!Api.isAuthenticated()) { stashIntendedRoute(); showAuthScreen(); return; }
    try {
      const me = await Api.auth.me();
      await afterLogin(me);
    } catch {
      Api.clearSession();
      stashIntendedRoute();
      showAuthScreen();
    }
  }

  async function afterLogin(me) {
    state.user = me;
    state.memberships = me.memberships || [];
    state.wsEpoch++; // invalidate any request still in flight from a prior session

    // Load every workspace (branch) the user belongs to. NO silent
    // auto-create — a brand-new user with zero workspaces is sent to the
    // get-started screen by the route guard to choose single vs multi.
    let workspaces = [];
    try { workspaces = await Api.workspaces.list(); } catch { workspaces = []; }
    state.workspaces = workspaces;

    const storedId = Api.getWorkspaceId();
    const active = workspaces.find((w) => w.id === storedId) || workspaces[0] || null;
    if (active) { state.workspace = active; Api.setWorkspaceId(active.id); }
    else { state.workspace = null; }

    const membership = state.memberships.find((m) => m.workspace_id === active?.id);
    const role = me.is_super_admin ? "super_admin" : (membership?.role || "owner");

    $("#user-avatar").textContent = initials(me.full_name);
    $("#user-name").textContent = me.full_name;
    $("#user-role").textContent = roleLabel(role);
    $("#user-dropdown-name").textContent = me.full_name;
    $("#user-dropdown-email").textContent = me.email;

    // Onboarding / setup-model routing is the route guard's job (enforceGuard).
    // This just wires the shell up.
    enterApp();
  }

  function enterApp() {
    state.cache = {};
    buildSidebar();
    updateWorkspaceSwitcher();
    initRouting(); // guarded: get-started / branches / onboarding / dashboard
  }

  async function logout() {
    closeAllDropdowns();
    await Api.auth.logout();  // also clears ar_workspace_id + ar_branch_model
    state.user = null; state.workspace = null; state.workspaces = []; state.cache = {};
    sessionStorage.removeItem(POST_LOGIN_HASH_KEY);
    if (window.ClinicOnboarding && ClinicOnboarding.isActive()) ClinicOnboarding.teardown();
    teardownGetStarted();
    toast({ title: "Signed out", tone: "info" });
    showAuthScreen();
  }

  function initAuthForms() {
    $("#show-register").addEventListener("click", () => { $("#login-panel").hidden = true; $("#register-panel").hidden = false; });
    $("#show-login").addEventListener("click", () => { $("#register-panel").hidden = true; $("#login-panel").hidden = false; });

    $("#login-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      showFormError("login-error", "");
      setFormLoading("login", true);
      try {
        await Api.auth.login({ email: $("#login-email").value.trim(), password: $("#login-password").value });
        const me = await Api.auth.me();
        toast({ title: `Welcome back, ${me.full_name.split(" ")[0]}!`, tone: "success" });
        await afterLogin(me);
      } catch (err) {
        showFormError("login-error", err.message || "Sign-in failed.");
      }
      setFormLoading("login", false);
    });

    $("#register-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      showFormError("register-error", "");
      setFormLoading("register", true);
      try {
        await Api.auth.register({
          fullName: $("#register-name").value.trim(),
          email: $("#register-email").value.trim(),
          password: $("#register-password").value,
        });
        await Api.auth.login({ email: $("#register-email").value.trim(), password: $("#register-password").value });
        const me = await Api.auth.me();
        toast({ title: `Welcome, ${me.full_name.split(" ")[0]}!`, text: "Your account is ready.", tone: "success" });
        await afterLogin(me);
      } catch (err) {
        showFormError("register-error", err.message || "Registration failed.");
      }
      setFormLoading("register", false);
    });
  }

  // Session expiry: broadcast once from api-service.js on any 401.
  window.addEventListener("ar:auth-expired", () => {
    state.user = null; state.workspace = null; state.workspaces = []; state.cache = {};
    Api.clearBranchModel();
    showAuthScreen();
    toast({ title: "Session expired", text: "Please sign in again.", tone: "warning" });
  });

  // ===========================================================================
  // Boot
  // ===========================================================================
  document.addEventListener("DOMContentLoaded", () => {
    initTheme();
    initSidebar();
    initDropdowns();
    initAuthForms();
    bootSession();
  });
})();
