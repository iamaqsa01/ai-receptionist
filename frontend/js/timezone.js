/**
 * Phase 3 — Worldwide IANA timezone system (frontend, no build step).
 *
 * `window.TZ` is the single place the app resolves, lists, labels, searches
 * and formats timezones. The full zone list comes from the browser's own
 * IANA database via `Intl.supportedValuesOf('timeZone')` (≈450 zones,
 * every continent) — never a hardcoded short list. All formatting goes
 * through `Intl.DateTimeFormat({ timeZone })`, so DST is applied
 * automatically for the correct instant.
 *
 * The organisation's timezone is stored on the existing backend field
 * `workspaces.timezone` (String(64)) via the existing
 * `PATCH /workspaces/{id}` contract — no schema/API change.
 */
window.TZ = (() => {
  "use strict";

  // Only used by browsers too old to expose Intl.supportedValuesOf (pre-2022
  // Chrome/Firefox/Safari). Deliberately broad and worldwide — NOT a
  // country-limited shortlist. Modern browsers never touch this.
  const FALLBACK_ZONES = [
    "UTC",
    "Africa/Abidjan", "Africa/Accra", "Africa/Addis_Ababa", "Africa/Algiers", "Africa/Cairo",
    "Africa/Casablanca", "Africa/Johannesburg", "Africa/Lagos", "Africa/Nairobi", "Africa/Tunis",
    "America/Anchorage", "America/Argentina/Buenos_Aires", "America/Bogota", "America/Chicago",
    "America/Denver", "America/Halifax", "America/Lima", "America/Los_Angeles", "America/Mexico_City",
    "America/New_York", "America/Phoenix", "America/Santiago", "America/Sao_Paulo", "America/Toronto",
    "America/Vancouver",
    "Antarctica/Palmer",
    "Asia/Almaty", "Asia/Baghdad", "Asia/Bangkok", "Asia/Colombo", "Asia/Dhaka", "Asia/Dubai",
    "Asia/Hong_Kong", "Asia/Jakarta", "Asia/Jerusalem", "Asia/Kabul", "Asia/Karachi", "Asia/Kathmandu",
    "Asia/Kolkata", "Asia/Manila", "Asia/Riyadh", "Asia/Seoul", "Asia/Shanghai", "Asia/Singapore",
    "Asia/Tehran", "Asia/Tokyo", "Asia/Yangon",
    "Atlantic/Azores", "Atlantic/Cape_Verde", "Atlantic/Reykjavik",
    "Australia/Adelaide", "Australia/Brisbane", "Australia/Darwin", "Australia/Perth", "Australia/Sydney",
    "Europe/Amsterdam", "Europe/Athens", "Europe/Berlin", "Europe/Brussels", "Europe/Bucharest",
    "Europe/Dublin", "Europe/Helsinki", "Europe/Istanbul", "Europe/Lisbon", "Europe/London",
    "Europe/Madrid", "Europe/Moscow", "Europe/Paris", "Europe/Rome", "Europe/Warsaw", "Europe/Zurich",
    "Indian/Maldives", "Indian/Mauritius",
    "Pacific/Auckland", "Pacific/Fiji", "Pacific/Honolulu", "Pacific/Port_Moresby", "Pacific/Tongatapu",
  ];

  const REGION_LABELS = {
    UTC: "UTC", Africa: "Africa", America: "Americas", Antarctica: "Antarctica", Arctic: "Arctic",
    Asia: "Asia", Atlantic: "Atlantic", Australia: "Australia", Europe: "Europe",
    Indian: "Indian Ocean", Pacific: "Pacific", Etc: "Other", Other: "Other",
  };
  const KNOWN_REGIONS = ["Africa", "America", "Antarctica", "Arctic", "Asia", "Atlantic", "Australia", "Europe", "Indian", "Pacific"];

  let _all = null;
  const _offsetCache = new Map();

  // -------------------------------------------------------------------------
  function all() {
    if (_all) return _all;
    let zones = [];
    try {
      if (typeof Intl.supportedValuesOf === "function") {
        const z = Intl.supportedValuesOf("timeZone");
        if (Array.isArray(z) && z.length) zones = z.slice();
      }
    } catch { /* fall through */ }
    if (!zones.length) zones = FALLBACK_ZONES.slice();
    if (!zones.includes("UTC")) zones.unshift("UTC");
    _all = zones;
    return _all;
  }

  function isValid(tz) {
    if (!tz || typeof tz !== "string") return false;
    try { new Intl.DateTimeFormat("en-US", { timeZone: tz }); return true; } catch { return false; }
  }

  function detect() {
    try {
      const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
      if (tz && isValid(tz)) return tz;
    } catch { /* ignore */ }
    return "UTC";
  }

  // -- offset (DST-aware for the given instant) ----------------------------
  const _offMinCache = new Map(); // tz -> minutes, for "now" only (the picker
                                  // sorts ~450 zones on every keystroke)
  function offsetMinutes(tz, date) {
    const now = date === undefined || Math.abs(date.getTime() - Date.now()) < 60000;
    if (now && _offMinCache.has(tz)) return _offMinCache.get(tz);
    const when = date || new Date();
    let m = 0;
    try {
      const parts = new Intl.DateTimeFormat("en-US", {
        timeZone: tz, hourCycle: "h23",
        year: "numeric", month: "2-digit", day: "2-digit",
        hour: "2-digit", minute: "2-digit", second: "2-digit",
      }).formatToParts(when).reduce((a, p) => (a[p.type] = p.value, a), {});
      const asUTC = Date.UTC(+parts.year, +parts.month - 1, +parts.day, +parts.hour, +parts.minute, +parts.second);
      m = Math.round((asUTC - when.getTime()) / 60000);
    } catch { m = 0; }
    if (now) _offMinCache.set(tz, m);
    return m;
  }

  function offsetLabel(tz, date = new Date()) {
    // Cache the "now" label per zone — cheap and it only shifts on DST
    // boundaries, which a page session won't usually cross.
    if (date === undefined || Math.abs(date.getTime() - Date.now()) < 60000) {
      if (_offsetCache.has(tz)) return _offsetCache.get(tz);
    }
    const m = offsetMinutes(tz, date);
    const sign = m < 0 ? "-" : "+";
    const abs = Math.abs(m);
    const s = `UTC${sign}${String(Math.floor(abs / 60)).padStart(2, "0")}:${String(abs % 60).padStart(2, "0")}`;
    _offsetCache.set(tz, s);
    return s;
  }

  function abbrev(tz, date = new Date()) {
    try {
      const p = new Intl.DateTimeFormat("en-US", { timeZone: tz, timeZoneName: "short" })
        .formatToParts(date).find((x) => x.type === "timeZoneName");
      if (p && p.value) return p.value.replace(/^GMT/, "UTC");
    } catch { /* ignore */ }
    return offsetLabel(tz, date);
  }

  // -- labels / grouping --------------------------------------------------
  function regionKey(tz) {
    if (tz === "UTC" || tz === "Etc/UTC") return "UTC";
    const head = String(tz).split("/")[0];
    if (KNOWN_REGIONS.includes(head)) return head;
    return "Other";
  }
  function regionLabel(tz) { return REGION_LABELS[regionKey(tz)] || "Other"; }

  function cityLabel(tz) {
    if (tz === "UTC" || tz === "Etc/UTC") return "UTC";
    const segs = tz.split("/");
    return segs.slice(1).join(" / ").replace(/_/g, " ") || tz;
  }

  // "Karachi — Asia (UTC+05:00)"   /   "UTC (UTC+00:00)"
  function label(tz, date) {
    if (!isValid(tz)) return tz || "—";
    if (tz === "UTC" || tz === "Etc/UTC") return `UTC (${offsetLabel("UTC", date)})`;
    return `${cityLabel(tz)} — ${regionLabel(tz)} (${offsetLabel(tz, date)})`;
  }

  // -- formatting in a tz ------------------------------------------------
  function _toDate(instant) {
    if (instant === null || instant === undefined || instant === "") return null;
    const d = instant instanceof Date ? instant : new Date(instant);
    return isNaN(d.getTime()) ? null : d;
  }
  function _fmt(instant, tz, opts) {
    const d = _toDate(instant);
    if (!d) return "—";
    try { return new Intl.DateTimeFormat("en-US", { timeZone: tz || "UTC", ...opts }).format(d); }
    catch { return new Intl.DateTimeFormat("en-US", opts).format(d); }
  }
  function formatDate(instant, tz, opts) {
    return _fmt(instant, tz, opts || { year: "numeric", month: "short", day: "numeric" });
  }
  function formatTime(instant, tz, opts) {
    return _fmt(instant, tz, opts || { hour: "numeric", minute: "2-digit" });
  }
  function formatDateTime(instant, tz) {
    const d = _toDate(instant);
    if (!d) return "—";
    return `${formatDate(d, tz)} · ${formatTime(d, tz)}`;
  }

  // -- calendar-day math in a tz --------------------------------------
  function ymd(instant, tz) {
    const d = _toDate(instant);
    if (!d) return "";
    try {
      const p = new Intl.DateTimeFormat("en-CA", {
        timeZone: tz || "UTC", year: "numeric", month: "2-digit", day: "2-digit",
      }).formatToParts(d).reduce((a, x) => (a[x.type] = x.value, a), {});
      return `${p.year}-${p.month}-${p.day}`;
    } catch { return d.toISOString().slice(0, 10); }
  }
  function sameDay(a, b, tz) {
    const A = ymd(a, tz), B = ymd(b, tz);
    return Boolean(A) && A === B;
  }
  function todayYmd(tz) { return ymd(new Date(), tz); }
  function weekdayShort(instant, tz) { return _fmt(instant, tz, { weekday: "short" }); }
  function hourInTz(tz, date = new Date()) {
    try {
      const p = new Intl.DateTimeFormat("en-US", { timeZone: tz, hourCycle: "h23", hour: "2-digit" })
        .formatToParts(date).find((x) => x.type === "hour");
      if (p) return parseInt(p.value, 10) % 24;
    } catch { /* ignore */ }
    return date.getHours();
  }

  // Interpret a wall-clock string ("YYYY-MM-DDTHH:mm", e.g. from an
  // <input type="datetime-local">) as a local time IN `tz`, and return the
  // matching absolute instant (a Date / real UTC point).
  function wallTimeToInstant(localStr, tz) {
    const m = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/.exec(String(localStr || ""));
    if (!m) return null;
    const Y = +m[1], Mo = +m[2], D = +m[3], H = +m[4], Mi = +m[5];
    let guess = Date.UTC(Y, Mo - 1, D, H, Mi);
    for (let i = 0; i < 3; i++) {
      const off = offsetMinutes(tz, new Date(guess));
      const corrected = Date.UTC(Y, Mo - 1, D, H, Mi) - off * 60000;
      if (corrected === guess) break;
      guess = corrected;
    }
    return new Date(guess);
  }

  // Inverse: an instant -> the "YYYY-MM-DDTHH:mm" wall-clock string in `tz`,
  // for pre-filling a datetime-local input.
  function instantToWallString(instant, tz) {
    const d = _toDate(instant);
    if (!d) return "";
    try {
      const p = new Intl.DateTimeFormat("en-CA", {
        timeZone: tz || "UTC", hourCycle: "h23",
        year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
      }).formatToParts(d).reduce((a, x) => (a[x.type] = x.value, a), {});
      return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}`;
    } catch { return ""; }
  }

  // =====================================================================
  // Searchable, region-grouped timezone picker component.
  //
  //   const picker = TZ.createPicker({ value, detected, onChange });
  //   container.appendChild(picker);
  //   picker.getValue();            // current IANA id
  //   picker.setValue("Asia/Tokyo");
  // =====================================================================
  function createPicker(opts = {}) {
    const detected = opts.detected || detect();
    let value = isValid(opts.value) ? opts.value : detected;
    let open = false;
    let activeIdx = -1;
    let filtered = [];

    const root = document.createElement("div");
    root.className = "tz-picker";
    root.innerHTML = `
      <button type="button" class="tz-picker__button" aria-haspopup="listbox" aria-expanded="false" aria-label="Timezone">
        <span class="tz-picker__value"></span>
        <svg class="tz-picker__chev" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M6 9l6 6 6-6"/></svg>
      </button>
      <div class="tz-picker__panel" hidden>
        <div class="tz-picker__searchwrap">
          <input type="text" class="tz-picker__search" placeholder="Search city, region or UTC offset…" autocomplete="off" spellcheck="false" aria-label="Search timezones" />
        </div>
        <div class="tz-picker__detected" hidden></div>
        <div class="tz-picker__list" role="listbox" tabindex="-1" aria-label="Timezones"></div>
        <div class="tz-picker__empty" hidden>No matching timezone.</div>
      </div>`;

    const btn = root.querySelector(".tz-picker__button");
    const valueEl = root.querySelector(".tz-picker__value");
    const panel = root.querySelector(".tz-picker__panel");
    const search = root.querySelector(".tz-picker__search");
    const listEl = root.querySelector(".tz-picker__list");
    const emptyEl = root.querySelector(".tz-picker__empty");
    const detectedEl = root.querySelector(".tz-picker__detected");

    function paintButton() {
      valueEl.textContent = label(value);
      root.dataset.tz = value;
      btn.setAttribute("aria-label", "Timezone: " + label(value));
    }

    function zoneMatches(tz, q) {
      if (!q) return true;
      const hay = `${tz} ${cityLabel(tz)} ${regionLabel(tz)} ${offsetLabel(tz)} ${abbrev(tz)}`.toLowerCase();
      // support "utc+5", "gmt+05", "+5"
      const norm = q.replace(/\s+/g, "").replace(/^gmt/, "utc");
      if (hay.includes(q)) return true;
      if (/^[+-]?\d/.test(norm) || norm.startsWith("utc")) {
        const off = offsetLabel(tz).toLowerCase().replace(":", "");
        const short = off.replace(/utc([+-])0?(\d+)00/, "utc$1$2");
        return off.includes(norm) || short.includes(norm) || offsetLabel(tz).toLowerCase().includes(norm);
      }
      return false;
    }

    function computeFiltered(q) {
      const query = (q || "").trim().toLowerCase();
      const zones = all().filter((tz) => zoneMatches(tz, query));
      // group by region, UTC first, then alpha region; inside region sort by
      // offset then city.
      const groups = {};
      zones.forEach((tz) => {
        const k = regionLabel(tz);
        (groups[k] = groups[k] || []).push(tz);
      });
      const order = Object.keys(groups).sort((a, b) => (a === "UTC" ? -1 : b === "UTC" ? 1 : a.localeCompare(b)));
      const flat = [];
      order.forEach((region) => {
        groups[region].sort((a, b) => (offsetMinutes(a) - offsetMinutes(b)) || cityLabel(a).localeCompare(cityLabel(b)));
        flat.push({ header: region });
        groups[region].forEach((tz) => flat.push({ tz }));
      });
      return flat;
    }

    function paintList() {
      const rows = filtered;
      const optRows = rows.filter((r) => r.tz);
      emptyEl.hidden = optRows.length > 0;
      listEl.hidden = optRows.length === 0;
      listEl.innerHTML = rows.map((r) => {
        if (r.header) return `<div class="tz-picker__group">${escapeHtmlLocal(r.header)}</div>`;
        const sel = r.tz === value ? " is-selected" : "";
        return `<div class="tz-picker__opt${sel}" role="option" data-tz="${escapeHtmlLocal(r.tz)}" aria-selected="${r.tz === value}">
          <span class="tz-picker__opt-city">${escapeHtmlLocal(cityLabel(r.tz))}</span>
          <span class="tz-picker__opt-meta">${escapeHtmlLocal(regionLabel(r.tz))} · ${escapeHtmlLocal(offsetLabel(r.tz))}</span>
        </div>`;
      }).join("");
      // reset keyboard highlight
      activeIdx = -1;
    }

    function optionEls() { return Array.from(listEl.querySelectorAll(".tz-picker__opt")); }

    function refilter() {
      filtered = computeFiltered(search.value);
      paintList();
    }

    // Outside-click closes the panel. The listener only exists WHILE the
    // panel is open, so a picker whose DOM gets replaced (e.g. Settings tab
    // re-render, wizard step revisit) leaves nothing behind on `document`.
    function onDocClick(e) { if (!root.contains(e.target)) closePanel(); }

    function openPanel() {
      if (open) return;
      open = true;
      panel.hidden = false;
      btn.setAttribute("aria-expanded", "true");
      root.classList.add("is-open");
      search.value = "";
      refilter();
      detectedEl.hidden = detected === value;
      if (detected !== value) {
        detectedEl.innerHTML = `Detected on this device: <button type="button" class="tz-picker__use-detected">${escapeHtmlLocal(label(detected))}</button>`;
        detectedEl.querySelector(".tz-picker__use-detected").addEventListener("click", () => pick(detected));
      }
      setTimeout(() => { search.focus(); document.addEventListener("click", onDocClick); }, 0);
      const sel = listEl.querySelector(".tz-picker__opt.is-selected");
      if (sel) sel.scrollIntoView({ block: "center" });
    }
    function closePanel() {
      if (!open) return;
      open = false;
      panel.hidden = true;
      btn.setAttribute("aria-expanded", "false");
      root.classList.remove("is-open");
      document.removeEventListener("click", onDocClick);
    }
    function pick(tz) {
      if (!isValid(tz)) return;
      value = tz;
      paintButton();
      closePanel();
      btn.focus();
      if (typeof opts.onChange === "function") opts.onChange(value);
    }

    function moveActive(delta) {
      const els = optionEls();
      if (!els.length) return;
      activeIdx = (activeIdx + delta + els.length) % els.length;
      els.forEach((e, i) => e.classList.toggle("is-active", i === activeIdx));
      els[activeIdx].scrollIntoView({ block: "nearest" });
    }

    // events
    btn.addEventListener("click", () => (open ? closePanel() : openPanel()));
    search.addEventListener("input", refilter);
    search.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown") { e.preventDefault(); moveActive(1); }
      else if (e.key === "ArrowUp") { e.preventDefault(); moveActive(-1); }
      else if (e.key === "Enter") {
        e.preventDefault();
        const els = optionEls();
        if (activeIdx >= 0 && els[activeIdx]) pick(els[activeIdx].dataset.tz);
        else if (els.length === 1) pick(els[0].dataset.tz);
      } else if (e.key === "Escape") { e.preventDefault(); closePanel(); btn.focus(); }
    });
    listEl.addEventListener("click", (e) => {
      const opt = e.target.closest(".tz-picker__opt");
      if (opt) pick(opt.dataset.tz);
    });

    // public
    root.getValue = () => value;
    root.setValue = (tz) => { if (isValid(tz)) { value = tz; paintButton(); if (open) refilter(); } };

    paintButton();
    return root;
  }

  function escapeHtmlLocal(s) {
    return String(s ?? "").replace(/[&<>"']/g, (c) => (
      { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
    ));
  }

  return {
    all, isValid, detect, regionKey, regionLabel, cityLabel, label,
    offsetMinutes, offsetLabel, abbrev,
    formatDate, formatTime, formatDateTime, weekdayShort,
    ymd, sameDay, todayYmd, hourInTz,
    wallTimeToInstant, instantToWallString,
    createPicker,
  };
})();
