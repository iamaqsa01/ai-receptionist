/**
 * Phase 2 — Mandatory multi-step clinic onboarding wizard.
 *
 * A full-screen, pre-dashboard experience the user cannot skip or dismiss.
 * app.js's route guard (see `enforceGuard`) mounts this whenever the ACTIVE
 * WORKSPACE has `is_onboarded === false`, and blocks every protected route
 * until the backend confirms that workspace's onboarding is complete.
 * (Onboarding is per-workspace — a user with several branches onboards each.)
 *
 * Persistence uses ONLY the existing backend contract discovered in Phase 1:
 *   - PATCH /workspaces/{id}                → clinic name + timezone
 *   - PUT   /workspaces/{id}/clinic-settings→ ClinicSettingsUpdate (the AI
 *                                             knowledge base; flips
 *                                             workspaces.is_onboarded server-side)
 *
 * `ClinicSettingsUpdate` forbids unknown top-level keys, so this wizard
 * never sends a field the schema doesn't define. A few UI fields the schema
 * has no dedicated column for (clinic phone / email / website / display
 * hours / free FAQs / general notes) are folded into the one free-text
 * `general_info.address` field — the only public-clinic-info string the
 * contract exposes — clearly delimited with " · " and parsed back out on
 * reload. Structured `business_hours` separately drives availability. The
 * Review step shows the exact payload that will be sent.
 *
 * No framework, no build step. Reuses the existing design-system classes
 * plus css/onboarding.css.
 */
window.ClinicOnboarding = (() => {
  "use strict";

  // -- constants kept in sync with the backend -------------------------------
  // app/schemas/clinic_settings.py :: AgentTone
  const TONES = ["Professional", "Empathetic", "Friendly"];
  // app/schemas/clinic_settings.py :: PreferredLanguage — the languages the
  // live-voice pipeline actually supports (app/ai/language/pakistan.py) plus
  // English and Roman Urdu for written channels. Do not add values here that
  // the backend enum does not accept.
  const LANGUAGES = ["English", "Urdu", "Roman Urdu", "Punjabi", "Saraiki", "Sindhi", "Pashto"];
  const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  const DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
  const ADDRESS_MAX = 500;   // GeneralInfo.address max_length
  const EMERGENCY_MAX = 2000; // ClinicSettingsUpdate.emergency_protocol max_length
  const SEG = " · ";          // delimiter used inside the composed address string

  // -- tiny helpers (self-contained; not shared with app.js) -----------------
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  function esc(str) {
    return String(str ?? "").replace(/[&<>"']/g, (c) => (
      { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
    ));
  }
  const trim = (v) => String(v ?? "").trim();
  function toNumberOrNull(v) {
    const s = trim(v);
    if (s === "") return null;
    const n = Number(s);
    return Number.isFinite(n) ? n : NaN;
  }
  // Worldwide IANA timezones, labelling, search and the picker component all
  // live in js/timezone.js (window.TZ). This wizard just uses them.
  function browserTimezone() { return (window.TZ && window.TZ.detect()) || "UTC"; }
  function tzIsValid(tz) { return window.TZ ? window.TZ.isValid(tz) : Boolean(tz); }

  // -- module state ---------------------------------------------------------
  let screenEl = null;
  let mounted = false;
  let currentStep = 0;
  const visited = new Set([0]);
  let cbs = { onComplete: () => {}, onExit: () => {} };
  let ctx = { workspaceId: null, workspaceName: "", exitLabel: "Sign out" };

  // The single source of truth for everything the user has entered. Never
  // cleared on a failed submit — retry reuses it verbatim. IS wiped when the
  // wizard is (re)opened for a branch, so one branch's entries can never bleed
  // into another's — see resetModel() in start().
  let model = freshModel();
  function resetModel() { model = freshModel(); }

  function freshModel() {
    return {
      business: {
        clinicName: "", phone: "", email: "", website: "",
        street: "", city: "", state: "", postal: "", country: "",
        googleMapsLink: "", timezone: browserTimezone(),
      },
      doctors: [newDoctor()],
      services: [""],
      appointment: { slotMinutes: 30, maxDaily: "" },
      businessHours: DAY_NAMES.map((_, day) => ({
        dayOfWeek: day,
        openTime: day < 5 ? "09:00" : "",
        closeTime: day < 5 ? "17:00" : "",
        isClosed: day >= 5,
      })),
      general: { parking: "", paymentMethods: [""], openingHours: "", generalNotes: "", faqs: [] },
      emergency: "",
      ai: { tone: "Professional", language: "English" },
    };
  }
  function newDoctor() {
    return { name: "", specialty: "", fee: "", days: [], startTime: "", endTime: "", availability: "" };
  }

  // =======================================================================
  // Public API
  // =======================================================================
  async function start({ user, workspaceId, workspaceName, workspaceOnboarded, exitLabel, onComplete, onExit } = {}) {
    // Defensive: an already-onboarded WORKSPACE must never be held here.
    // (Onboarding is per-workspace — see Workspace.is_onboarded.)
    if (workspaceOnboarded) { (onComplete || (() => {}))(); return; }

    const targetWsId = workspaceId || (window.Api && Api.getWorkspaceId && Api.getWorkspaceId()) || null;
    // Already showing the wizard for THIS branch — just re-reveal it and keep
    // the user's progress. For a DIFFERENT branch, tear down and start clean so
    // no entries carry over (Phase 7: never mix branch data).
    if (mounted) {
      if (targetWsId && ctx.workspaceId && targetWsId === ctx.workspaceId) { show(); return; }
      teardown();
    }
    resetModel();

    cbs.onComplete = typeof onComplete === "function" ? onComplete : () => {};
    // The caller owns what "exit" does (sign out for a single-branch user;
    // step back to Branch Management for a multi-branch user).
    cbs.onExit = typeof onExit === "function" ? onExit : () => {};
    ctx.exitLabel = exitLabel || "Sign out";
    ctx.workspaceId = targetWsId;
    ctx.workspaceName = workspaceName || "";

    mounted = true;
    currentStep = 0;
    visited.clear(); visited.add(0);

    screenEl = document.getElementById("onboard-screen");
    if (!screenEl) {
      screenEl = document.createElement("div");
      screenEl.id = "onboard-screen";
      screenEl.className = "onboard-screen";
      document.body.appendChild(screenEl);
    }
    screenEl.hidden = false;
    screenEl.innerHTML = `<div class="onboard-loading">
      <span class="spinner spinner--dark" style="width:24px;height:24px;"></span>
      <div>Loading your workspace…</div></div>`;

    // Prefill from whatever the backend already has (defaults for a brand-new
    // account; real data if an onboarded user ever re-enters the wizard).
    if (workspaceName) model.business.clinicName = workspaceName;
    try {
      // Everything is read for THIS branch (ctx.workspaceId) explicitly — never
      // the globally-active workspace. A wizard opened for Branch B must show
      // Branch B's data even if Branch A is currently active.
      const [ws, settings] = await Promise.all([
        ctx.workspaceId ? safe(() => Api.workspaces.get(ctx.workspaceId)) : Promise.resolve(null),
        ctx.workspaceId ? safe(() => Api.clinicSettings.getFor(ctx.workspaceId)) : Promise.resolve(null),
      ]);
      if (ws) {
        if (ws.name) ctx.workspaceName = ws.name;
        if (ws.name && !model.business.clinicName) model.business.clinicName = ws.name;
        if (ws.name && workspaceName === undefined) model.business.clinicName = ws.name;
        // A brand-new workspace is created server-side with timezone "UTC" as
        // a placeholder — in that case keep the browser-detected suggestion
        // (freshModel seeded it). Honour any real, non-default saved value.
        if (ws.timezone && ws.timezone !== "UTC" && tzIsValid(ws.timezone)) {
          model.business.timezone = ws.timezone;
        }
      }
      if (settings) hydrateFromSettings(settings);
    } catch { /* non-fatal — fall through to an empty form */ }

    renderShell();
    renderStep();
  }

  function isActive() { return mounted; }
  function show() { if (screenEl) screenEl.hidden = false; }
  function teardown() {
    mounted = false;
    if (screenEl) { screenEl.hidden = true; screenEl.innerHTML = ""; }
  }

  // If the session expires mid-onboarding, drop the wizard so app.js's
  // shared handler can show the login screen cleanly.
  window.addEventListener("ar:auth-expired", () => { if (mounted) teardown(); });

  function safe(fn) { return Promise.resolve().then(fn).catch(() => null); }

  // =======================================================================
  // Steps
  // =======================================================================
  const STEPS = [
    { id: "business", label: "Business Information", render: renderBusiness, collect: collectBusiness },
    { id: "doctors", label: "Doctors", render: renderDoctors, collect: collectDoctors },
    { id: "services", label: "Services", render: renderServices, collect: collectServices },
    { id: "appointment", label: "Appointment Settings", render: renderAppointment, collect: collectAppointment },
    { id: "general", label: "General Information / FAQs", render: renderGeneral, collect: collectGeneral },
    { id: "emergency", label: "Emergency Protocol", render: renderEmergency, collect: collectEmergency },
    { id: "ai", label: "AI Preferences", render: renderAi, collect: collectAi },
    { id: "review", label: "Review & Confirm", render: renderReview, collect: () => ({ ok: true }) },
  ];

  // =======================================================================
  // Shell / navigation
  // =======================================================================
  function renderShell() {
    screenEl.innerHTML = `
      <div class="onboard-topbar">
        <div class="onboard-brand">
          <span class="onboard-brand__mark">AR</span>
          <span class="onboard-brand__name">AI Receptionist</span>
          ${ctx.workspaceName ? `<span class="onboard-brand__ws" title="You are setting up this branch">${esc(ctx.workspaceName)}</span>` : ""}
        </div>
        <div class="onboard-topbar__meta">
          <span class="onboard-topbar__step" id="ob-stepcount"></span>
          <span class="onboard-topbar__progress" id="ob-progressbar" role="progressbar" aria-label="Onboarding progress" aria-valuemin="1" aria-valuemax="${STEPS.length}"><span id="ob-progress"></span></span>
          <button class="btn btn--ghost btn--sm" id="ob-signout" type="button">${esc(ctx.exitLabel)}</button>
        </div>
      </div>
      <div class="onboard-body">
        <nav class="onboard-rail" id="ob-rail" aria-label="Setup steps">
          <div class="onboard-rail__title" aria-hidden="true">Setup steps</div>
        </nav>
        <div class="onboard-content">
          <div class="onboard-content__inner">
            <div class="onboard-error" id="ob-error" role="alert"></div>
            <div id="ob-step" tabindex="-1"></div>
          </div>
        </div>
      </div>
      <div class="onboard-footer">
        <button class="btn btn--secondary" id="ob-back" type="button">Back</button>
        <div class="onboard-footer__spacer"></div>
        <button class="btn btn--primary" id="ob-next" type="button">
          <span class="spinner"></span><span class="btn__label">Continue</span>
        </button>
      </div>`;

    $("#ob-signout", screenEl).addEventListener("click", () => {
      // The caller decides what exit means (sign out, or back to Branch
      // Management). It no longer hard-codes a logout here.
      teardown();
      cbs.onExit();
    });
    $("#ob-back", screenEl).addEventListener("click", goBack);
    $("#ob-next", screenEl).addEventListener("click", goNext);
    buildRail();
  }

  function buildRail() {
    const rail = $("#ob-rail", screenEl);
    // wipe everything after the title
    $$(".onboard-step-btn", rail).forEach((n) => n.remove());
    STEPS.forEach((s, i) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "onboard-step-btn";
      btn.dataset.idx = String(i);
      btn.setAttribute("aria-label", `Step ${i + 1} of ${STEPS.length}: ${s.label}`);
      btn.innerHTML = `<span class="onboard-step-btn__num" aria-hidden="true">${i + 1}</span><span class="onboard-step-btn__label">${esc(s.label)}</span>`;
      btn.disabled = !visited.has(i);
      btn.addEventListener("click", () => jumpTo(i));
      rail.appendChild(btn);
    });
    syncRail();
  }

  function syncRail() {
    $$(".onboard-step-btn", screenEl).forEach((btn) => {
      const i = Number(btn.dataset.idx);
      const active = i === currentStep;
      btn.classList.toggle("is-active", active);
      btn.classList.toggle("is-done", visited.has(i) && i < currentStep);
      btn.disabled = !visited.has(i);
      if (active) btn.setAttribute("aria-current", "step"); else btn.removeAttribute("aria-current");
    });
    $("#ob-stepcount", screenEl).textContent = `Step ${currentStep + 1} of ${STEPS.length} — ${STEPS[currentStep].label}`;
    $("#ob-progress", screenEl).style.width = `${((currentStep + 1) / STEPS.length) * 100}%`;
    const pb = $("#ob-progressbar", screenEl);
    if (pb) { pb.setAttribute("aria-valuenow", String(currentStep + 1)); pb.setAttribute("aria-valuetext", `Step ${currentStep + 1} of ${STEPS.length}: ${STEPS[currentStep].label}`); }
    const backBtn = $("#ob-back", screenEl);
    backBtn.style.visibility = currentStep === 0 ? "hidden" : "visible";
    const nextLabel = $("#ob-next .btn__label", screenEl);
    nextLabel.textContent = currentStep === STEPS.length - 1 ? "Complete Setup" : "Continue";
  }

  function renderStep() {
    showError("");
    const host = $("#ob-step", screenEl);
    host.innerHTML = "";
    STEPS[currentStep].render(host);
    syncRail();
    // Reset the scroll of the step pane and move focus into it for screen
    // readers / keyboard users (each step is a fresh view).
    const content = $(".onboard-content", screenEl);
    if (content) content.scrollTop = 0;
    host.focus({ preventScroll: true });
  }

  function goBack() { if (currentStep > 0) { currentStep--; visited.add(currentStep); renderStep(); } }

  function goNext() {
    const res = STEPS[currentStep].collect();
    if (res && res.error) { showError(res.error); return; }
    if (currentStep === STEPS.length - 1) { submit(); return; }
    currentStep++;
    visited.add(currentStep);
    renderStep();
  }

  function jumpTo(i) {
    if (!visited.has(i)) return;
    // Save whatever's on the current step (best-effort) before leaving it,
    // but don't block navigation to an already-visited step on validation.
    try { STEPS[currentStep].collect(); } catch { /* ignore */ }
    currentStep = i;
    renderStep();
  }

  function showError(msg) {
    const box = $("#ob-error", screenEl);
    if (!box) return;
    if (!msg) { box.classList.remove("is-visible"); box.textContent = ""; return; }
    box.textContent = msg;
    box.classList.add("is-visible");
    box.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  // =======================================================================
  // STEP 1 — Business / Clinic Information
  // =======================================================================
  function renderBusiness(host) {
    const b = model.business;
    host.innerHTML = `
      ${stepHead("Step 1", "Business information", "Tell us about your clinic. The AI receptionist uses this to answer callers.")}
      <div class="onboard-fieldset">
        <div class="onboard-fieldset__legend">Organisation</div>
        <div class="onboard-grid">
          <div class="field span-2">
            <label class="field__label" for="b-name">Clinic / business name *</label>
            <input class="input" id="b-name" value="${esc(b.clinicName)}" placeholder="Your clinic's name" maxlength="255" required aria-required="true" />
          </div>
          <div class="field">
            <label class="field__label" for="b-phone">Phone</label>
            <input class="input" id="b-phone" value="${esc(b.phone)}" placeholder="+92 300 0000000" />
          </div>
          <div class="field">
            <label class="field__label" for="b-email">Email</label>
            <input class="input" id="b-email" type="email" value="${esc(b.email)}" placeholder="reception@clinic.com" />
          </div>
          <div class="field span-2">
            <label class="field__label" for="b-website">Website</label>
            <input class="input" id="b-website" value="${esc(b.website)}" placeholder="https://clinic.com" />
          </div>
        </div>
      </div>

      <div class="onboard-fieldset">
        <div class="onboard-fieldset__legend">Location</div>
        <div class="onboard-grid">
          <div class="field span-2">
            <label class="field__label" for="b-street">Street address</label>
            <input class="input" id="b-street" value="${esc(b.street)}" placeholder="12 Clinic Road" />
          </div>
          <div class="field">
            <label class="field__label" for="b-city">City</label>
            <input class="input" id="b-city" value="${esc(b.city)}" placeholder="Lahore" />
          </div>
          <div class="field">
            <label class="field__label" for="b-state">State / province</label>
            <input class="input" id="b-state" value="${esc(b.state)}" placeholder="Punjab" />
          </div>
          <div class="field">
            <label class="field__label" for="b-postal">Postal / ZIP code</label>
            <input class="input" id="b-postal" value="${esc(b.postal)}" placeholder="54000" />
          </div>
          <div class="field">
            <label class="field__label" for="b-country">Country</label>
            <input class="input" id="b-country" value="${esc(b.country)}" placeholder="Pakistan" />
          </div>
          <div class="field span-2">
            <label class="field__label" for="b-maps">Google Maps link</label>
            <input class="input" id="b-maps" value="${esc(b.googleMapsLink)}" placeholder="https://maps.google.com/…" maxlength="500" />
          </div>
          <div class="field span-2">
            <label class="field__label">Timezone *</label>
            <div id="b-tz-mount"></div>
            <div class="onboard-hint">Worldwide IANA timezone — used for every appointment time, dashboard "today" and the day-of reminder job. DST is applied automatically.</div>
          </div>
        </div>
        <div class="onboard-hint" id="b-addrcount"></div>
      </div>`;

    const bind = (id, key) => $(`#${id}`, host).addEventListener("input", (e) => { model.business[key] = e.target.value; updateAddrCount(); });
    bind("b-name", "clinicName"); bind("b-phone", "phone"); bind("b-email", "email"); bind("b-website", "website");
    bind("b-street", "street"); bind("b-city", "city"); bind("b-state", "state"); bind("b-postal", "postal");
    bind("b-country", "country"); bind("b-maps", "googleMapsLink");

    if (window.TZ && typeof TZ.createPicker === "function") {
      const picker = TZ.createPicker({
        value: b.timezone, detected: TZ.detect(),
        onChange: (tz) => { model.business.timezone = tz; },
      });
      $("#b-tz-mount", host).appendChild(picker);
    } else {
      // Extremely old browser with no Intl support at all — plain input.
      const mount = $("#b-tz-mount", host);
      mount.innerHTML = `<input class="input" id="b-tz" value="${esc(b.timezone)}" placeholder="e.g. Asia/Karachi" />`;
      $("#b-tz", host).addEventListener("input", (e) => { model.business.timezone = e.target.value.trim(); });
    }
    updateAddrCount();

    function updateAddrCount() {
      const composed = composeAddress();
      const node = $("#b-addrcount", host);
      node.textContent = `Address, contact, hours & FAQ are stored together in one backend field — ${composed.length}/${ADDRESS_MAX} characters used.`;
      node.classList.toggle("is-over", composed.length > ADDRESS_MAX);
    }
  }

  function collectBusiness() {
    const b = model.business;
    b.clinicName = trim(b.clinicName);
    if (!b.clinicName) return { error: "Clinic / business name is required." };
    if (b.clinicName.length > 255) return { error: "Clinic name must be 255 characters or fewer." };
    if (!trim(b.timezone) || !tzIsValid(b.timezone)) return { error: "Please choose a valid timezone." };
    if (b.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(trim(b.email))) return { error: "Enter a valid clinic email address." };
    if (b.googleMapsLink && b.googleMapsLink.length > 500) return { error: "Google Maps link is too long (max 500 characters)." };
    if (composeAddress().length > ADDRESS_MAX) {
      return { error: `The combined address / contact / hours / FAQ text is ${composeAddress().length} characters — the backend stores it in one field limited to ${ADDRESS_MAX}. Shorten the address, opening hours, or FAQs.` };
    }
    return { ok: true };
  }

  // =======================================================================
  // STEP 2 — Doctors (dynamic add / edit / remove)
  // =======================================================================
  function renderDoctors(host) {
    host.innerHTML = `
      ${stepHead("Step 2", "Doctors", "Add every doctor callers can book with. You can add as many as you need.")}
      <div id="ob-doctors"></div>
      <button class="btn btn--secondary btn--sm onboard-add-btn" id="ob-add-doctor" type="button">+ Add doctor</button>`;
    paintDoctors(host);
    $("#ob-add-doctor", host).addEventListener("click", () => { model.doctors.push(newDoctor()); paintDoctors(host); });
  }

  function paintDoctors(host) {
    const wrap = $("#ob-doctors", host);
    wrap.innerHTML = model.doctors.map((d, i) => `
      <div class="onboard-repeat-card" data-doc="${i}">
        <div class="onboard-repeat-card__head">
          <span class="onboard-repeat-card__title">Doctor ${i + 1}</span>
          <button class="btn btn--ghost btn--sm" type="button" data-remove-doc="${i}">Remove</button>
        </div>
        <div class="onboard-grid">
          <div class="field">
            <label class="field__label" for="ob-doc-name-${i}">Name <span class="req" aria-hidden="true">*</span></label>
            <input class="input" id="ob-doc-name-${i}" data-f="name" value="${esc(d.name)}" placeholder="Dr. Jane Doe" maxlength="255" required aria-required="true" />
          </div>
          <div class="field">
            <label class="field__label" for="ob-doc-spec-${i}">Specialty</label>
            <input class="input" id="ob-doc-spec-${i}" data-f="specialty" value="${esc(d.specialty)}" placeholder="General Physician" maxlength="255" />
          </div>
          <div class="field">
            <label class="field__label" for="ob-doc-fee-${i}">Consultation fee</label>
            <input class="input" id="ob-doc-fee-${i}" data-f="fee" type="number" min="0" step="any" value="${esc(d.fee)}" placeholder="e.g. 2000" />
          </div>
          <div class="field">
            <label class="field__label" for="ob-doc-start-${i}">Working hours</label>
            <div class="onboard-inline-row" style="margin:0;">
              <div class="field" style="margin:0;"><input class="input" id="ob-doc-start-${i}" data-f="startTime" type="time" value="${esc(d.startTime)}" aria-label="Start time" /></div>
              <span style="align-self:center;color:var(--text-faint);">to</span>
              <div class="field" style="margin:0;"><input class="input" data-f="endTime" type="time" value="${esc(d.endTime)}" aria-label="End time" /></div>
            </div>
          </div>
          <div class="field span-2" role="group" aria-label="Working days">
            <span class="field__label">Working days</span>
            <div class="onboard-daypick" data-days>
              ${DAYS.map((day) => `<label><input type="checkbox" value="${day}"${d.days.includes(day) ? " checked" : ""} /> ${day}</label>`).join("")}
            </div>
          </div>
          <div class="field span-2">
            <label class="field__label" for="ob-doc-avail-${i}">Availability notes</label>
            <input class="input" id="ob-doc-avail-${i}" data-f="availability" value="${esc(d.availability)}" placeholder="e.g. Walk-ins welcome; on leave last week of month" maxlength="255" />
          </div>
        </div>
      </div>`).join("");

    $$("[data-doc]", wrap).forEach((card) => {
      const i = Number(card.dataset.doc);
      $$("[data-f]", card).forEach((inp) => inp.addEventListener("input", (e) => { model.doctors[i][e.target.dataset.f] = e.target.value; }));
      $$("[data-days] input", card).forEach((cb) => cb.addEventListener("change", () => {
        model.doctors[i].days = $$("[data-days] input", card).filter((x) => x.checked).map((x) => x.value);
      }));
      $("[data-remove-doc]", card).addEventListener("click", () => {
        if (model.doctors.length === 1) { showError("Add at least one doctor."); return; }
        model.doctors.splice(i, 1);
        paintDoctors(host);
      });
    });
  }

  function collectDoctors() {
    const cleaned = [];
    for (const d of model.doctors) {
      const name = trim(d.name);
      const hasAny = name || trim(d.specialty) || trim(d.fee) || d.days.length || trim(d.startTime) || trim(d.endTime) || trim(d.availability);
      if (!hasAny) continue;
      if (!name) return { error: "Every doctor needs a name (or clear that row)." };
      const fee = toNumberOrNull(d.fee);
      if (Number.isNaN(fee)) return { error: `Consultation fee for “${name}” must be a number.` };
      if (fee !== null && fee < 0) return { error: `Consultation fee for “${name}” can't be negative.` };
      if (d.startTime && d.endTime && d.endTime <= d.startTime) return { error: `Working hours for “${name}” must end after they start.` };
      cleaned.push({ ...d, name, fee });
    }
    if (!cleaned.length) return { error: "Add at least one doctor." };
    const doctorKeys = cleaned.map((d) => d.name.toLocaleLowerCase());
    if (new Set(doctorKeys).size !== doctorKeys.length) return { error: "Doctor names must be unique." };
    // keep the UI list normalised so re-visiting shows what will be saved
    model.doctors = cleaned.map((d) => ({
      name: d.name, specialty: trim(d.specialty), fee: d.fee === null ? "" : String(d.fee),
      days: d.days, startTime: d.startTime, endTime: d.endTime, availability: trim(d.availability),
    }));
    if (!model.doctors.length) model.doctors = [newDoctor()];
    return { ok: true };
  }

  // =======================================================================
  // STEP 3 — Services (dynamic add / edit / delete)
  // =======================================================================
  function renderServices(host) {
    host.innerHTML = `
      ${stepHead("Step 3", "Services", "List the services or procedures your clinic offers. Callers can ask about and book these.")}
      <div id="ob-services"></div>
      <button class="btn btn--secondary btn--sm onboard-add-btn" id="ob-add-service" type="button">+ Add service</button>`;
    paintServices(host);
    $("#ob-add-service", host).addEventListener("click", () => { model.services.push(""); paintServices(host); });
  }

  function paintServices(host) {
    const wrap = $("#ob-services", host);
    wrap.innerHTML = model.services.map((s, i) => `
      <div class="onboard-inline-row" data-svc="${i}">
        <div class="field">
          <label class="field__label" for="ob-svc-${i}">Service ${i + 1} <span class="req" aria-hidden="true">*</span></label>
          <input class="input" id="ob-svc-${i}" data-f="service" value="${esc(s)}" placeholder="e.g. Dental cleaning" maxlength="255" required aria-required="true" />
        </div>
        <button class="btn btn--ghost btn--sm" type="button" data-remove-svc="${i}" aria-label="Remove service ${i + 1}">Remove</button>
      </div>`).join("");
    $$("[data-svc]", wrap).forEach((row) => {
      const i = Number(row.dataset.svc);
      $("[data-f]", row).addEventListener("input", (e) => { model.services[i] = e.target.value; });
      $("[data-remove-svc]", row).addEventListener("click", () => {
        if (model.services.length === 1) { showError("Add at least one service."); return; }
        model.services.splice(i, 1);
        paintServices(host);
      });
    });
  }

  function collectServices() {
    const cleaned = model.services.map(trim).filter(Boolean);
    if (!cleaned.length) return { error: "Add at least one service." };
    const serviceKeys = cleaned.map((name) => name.toLocaleLowerCase());
    if (new Set(serviceKeys).size !== serviceKeys.length) return { error: "Service names must be unique." };
    model.services = cleaned;
    return { ok: true };
  }

  // =======================================================================
  // STEP 4 — Appointment settings
  // =======================================================================
  function renderAppointment(host) {
    const a = model.appointment;
    host.innerHTML = `
      ${stepHead("Step 4", "Appointment settings", "How the AI receptionist schedules bookings.")}
      <div class="onboard-grid">
        <div class="field">
          <label class="field__label" for="a-slot">Default slot duration (minutes) *</label>
          <input class="input" id="a-slot" type="number" min="5" max="480" step="5" value="${esc(a.slotMinutes)}" />
        </div>
        <div class="field">
          <label class="field__label" for="a-max">Maximum daily bookings</label>
          <input class="input" id="a-max" type="number" min="1" max="1000" step="1" value="${esc(a.maxDaily)}" placeholder="Optional — leave blank for no limit" />
        </div>
      </div>
      <div class="onboard-fieldset" style="margin-top:18px;">
        <div class="onboard-fieldset__legend">Clinic business hours</div>
        <div class="onboard-hint" style="margin-bottom:12px;">These hours control when the booking engine offers appointments.</div>
        <div id="ob-business-hours"></div>
      </div>`;
    $("#a-slot", host).addEventListener("input", (e) => { model.appointment.slotMinutes = e.target.value; });
    $("#a-max", host).addEventListener("input", (e) => { model.appointment.maxDaily = e.target.value; });
    paintBusinessHours(host);
  }

  function paintBusinessHours(host) {
    const wrap = $("#ob-business-hours", host);
    wrap.innerHTML = model.businessHours.map((hours, day) => `
      <div class="onboard-inline-row" data-business-day="${day}" style="align-items:center;">
        <div class="field" style="min-width:120px;margin:0;"><span class="field__label">${DAY_NAMES[day]}</span></div>
        <label style="display:flex;align-items:center;gap:7px;min-width:82px;">
          <input type="checkbox" data-f="isClosed"${hours.isClosed ? " checked" : ""} /> Closed
        </label>
        <div class="field" style="margin:0;"><input class="input" data-f="openTime" type="time" value="${esc(hours.openTime)}" aria-label="${DAY_NAMES[day]} opening time"${hours.isClosed ? " disabled" : ""} /></div>
        <span style="color:var(--text-faint);">to</span>
        <div class="field" style="margin:0;"><input class="input" data-f="closeTime" type="time" value="${esc(hours.closeTime)}" aria-label="${DAY_NAMES[day]} closing time"${hours.isClosed ? " disabled" : ""} /></div>
      </div>`).join("");

    $$('[data-business-day]', wrap).forEach((row) => {
      const day = Number(row.dataset.businessDay);
      $('[data-f="isClosed"]', row).addEventListener("change", (e) => {
        model.businessHours[day].isClosed = e.target.checked;
        if (!e.target.checked) {
          model.businessHours[day].openTime ||= "09:00";
          model.businessHours[day].closeTime ||= "17:00";
        }
        paintBusinessHours(host);
      });
      $('[data-f="openTime"]', row).addEventListener("input", (e) => { model.businessHours[day].openTime = e.target.value; });
      $('[data-f="closeTime"]', row).addEventListener("input", (e) => { model.businessHours[day].closeTime = e.target.value; });
    });
  }

  function collectAppointment() {
    const slot = toNumberOrNull(model.appointment.slotMinutes);
    if (slot === null || Number.isNaN(slot) || slot < 5 || slot > 480) {
      return { error: "Default slot duration must be a number between 5 and 480 minutes." };
    }
    const max = toNumberOrNull(model.appointment.maxDaily);
    if (Number.isNaN(max)) return { error: "Maximum daily bookings must be a number." };
    if (max !== null && (max < 1 || max > 1000)) return { error: "Maximum daily bookings must be between 1 and 1000." };
    model.appointment.slotMinutes = Math.round(slot);
    model.appointment.maxDaily = max === null ? "" : String(Math.round(max));
    for (const hours of model.businessHours) {
      if (hours.isClosed) continue;
      if (!hours.openTime || !hours.closeTime) {
        return { error: `${DAY_NAMES[hours.dayOfWeek]} needs both an opening and closing time.` };
      }
      if (hours.closeTime <= hours.openTime) {
        return { error: `${DAY_NAMES[hours.dayOfWeek]}'s closing time must be after its opening time.` };
      }
    }
    return { ok: true };
  }

  // =======================================================================
  // STEP 5 — General information / FAQs
  // =======================================================================
  function renderGeneral(host) {
    const g = model.general;
    host.innerHTML = `
      ${stepHead("Step 5", "General information & FAQs", "Extra details the AI receptionist can share with callers.")}
      <div class="onboard-fieldset">
        <div class="onboard-fieldset__legend">Practical details</div>
        <div class="onboard-grid">
          <div class="field">
            <label class="field__label" for="g-parking">Parking availability</label>
            <select class="select" id="g-parking">
              <option value=""${g.parking === "" ? " selected" : ""}>Not specified</option>
              <option value="yes"${g.parking === "yes" ? " selected" : ""}>Available on site</option>
              <option value="no"${g.parking === "no" ? " selected" : ""}>Not available</option>
            </select>
          </div>
          <div class="field">
            <label class="field__label" for="g-hours">Opening hours</label>
            <input class="input" id="g-hours" value="${esc(g.openingHours)}" placeholder="Mon–Sat 9am–9pm, Sun closed" />
          </div>
        </div>
        <div class="field span-2" style="margin-top:14px;">
          <label class="field__label">Accepted payment methods</label>
          <div id="ob-payments"></div>
          <button class="btn btn--ghost btn--sm" id="ob-add-payment" type="button">+ Add payment method</button>
        </div>
        <div class="field" style="margin-top:14px;">
          <label class="field__label" for="g-notes">General information</label>
          <textarea class="textarea" id="g-notes" placeholder="Anything else callers often ask about — insurance partners, wheelchair access, languages spoken…">${esc(g.generalNotes)}</textarea>
        </div>
      </div>

      <div class="onboard-fieldset">
        <div class="onboard-fieldset__legend">FAQs</div>
        <div id="ob-faqs"></div>
        <button class="btn btn--secondary btn--sm onboard-add-btn" id="ob-add-faq" type="button">+ Add FAQ</button>
      </div>
      <div class="onboard-hint" id="g-count"></div>`;

    $("#g-parking", host).addEventListener("change", (e) => { model.general.parking = e.target.value; updateCount(); });
    $("#g-hours", host).addEventListener("input", (e) => { model.general.openingHours = e.target.value; updateCount(); });
    $("#g-notes", host).addEventListener("input", (e) => { model.general.generalNotes = e.target.value; updateCount(); });

    paintPayments(host, updateCount);
    paintFaqs(host, updateCount);
    $("#ob-add-payment", host).addEventListener("click", () => { model.general.paymentMethods.push(""); paintPayments(host, updateCount); });
    $("#ob-add-faq", host).addEventListener("click", () => { model.general.faqs.push({ q: "", a: "" }); paintFaqs(host, updateCount); });
    updateCount();

    function updateCount() {
      const composed = composeAddress();
      const node = $("#g-count", host);
      node.textContent = `Combined address / contact / hours / FAQ text: ${composed.length}/${ADDRESS_MAX} characters (stored in one backend field).`;
      node.classList.toggle("is-over", composed.length > ADDRESS_MAX);
    }
  }

  function paintPayments(host, after) {
    const wrap = $("#ob-payments", host);
    if (!model.general.paymentMethods.length) model.general.paymentMethods = [""];
    wrap.innerHTML = model.general.paymentMethods.map((p, i) => `
      <div class="onboard-inline-row" data-pay="${i}">
        <div class="field"><input class="input" data-f="pay" value="${esc(p)}" placeholder="Cash / Credit card / Insurance" aria-label="Payment method ${i + 1}" /></div>
        <button class="btn btn--ghost btn--sm" type="button" data-remove-pay="${i}" aria-label="Remove payment method ${i + 1}">Remove</button>
      </div>`).join("");
    $$("[data-pay]", wrap).forEach((row) => {
      const i = Number(row.dataset.pay);
      $("[data-f]", row).addEventListener("input", (e) => { model.general.paymentMethods[i] = e.target.value; after && after(); });
      $("[data-remove-pay]", row).addEventListener("click", () => {
        model.general.paymentMethods.splice(i, 1);
        if (!model.general.paymentMethods.length) model.general.paymentMethods = [""];
        paintPayments(host, after); after && after();
      });
    });
  }

  function paintFaqs(host, after) {
    const wrap = $("#ob-faqs", host);
    if (!model.general.faqs.length) {
      wrap.innerHTML = `<div class="onboard-hint" style="margin-bottom:10px;">No FAQs yet. Add common questions callers ask.</div>`;
      return;
    }
    wrap.innerHTML = model.general.faqs.map((f, i) => `
      <div class="onboard-repeat-card" data-faq="${i}">
        <div class="onboard-repeat-card__head">
          <span class="onboard-repeat-card__title">FAQ ${i + 1}</span>
          <button class="btn btn--ghost btn--sm" type="button" data-remove-faq="${i}" aria-label="Delete FAQ ${i + 1}">Delete</button>
        </div>
        <div class="field">
          <label class="field__label" for="ob-faq-q-${i}">Question</label>
          <input class="input" id="ob-faq-q-${i}" data-f="q" value="${esc(f.q)}" placeholder="Do you accept new patients?" />
        </div>
        <div class="field" style="margin-top:10px;">
          <label class="field__label" for="ob-faq-a-${i}">Answer</label>
          <textarea class="textarea" id="ob-faq-a-${i}" data-f="a" placeholder="Yes — call during opening hours to register.">${esc(f.a)}</textarea>
        </div>
      </div>`).join("");
    $$("[data-faq]", wrap).forEach((card) => {
      const i = Number(card.dataset.faq);
      $$("[data-f]", card).forEach((inp) => inp.addEventListener("input", (e) => { model.general.faqs[i][e.target.dataset.f] = e.target.value; after && after(); }));
      $("[data-remove-faq]", card).addEventListener("click", () => { model.general.faqs.splice(i, 1); paintFaqs(host, after); after && after(); });
    });
  }

  function collectGeneral() {
    model.general.paymentMethods = model.general.paymentMethods.map(trim).filter(Boolean);
    model.general.faqs = model.general.faqs
      .map((f) => ({ q: trim(f.q), a: trim(f.a) }))
      .filter((f) => f.q || f.a);
    for (const f of model.general.faqs) {
      if (!f.q || !f.a) return { error: "Every FAQ needs both a question and an answer (or delete it)." };
    }
    if (composeAddress().length > ADDRESS_MAX) {
      return { error: `The combined address / contact / hours / FAQ text is ${composeAddress().length} characters; the backend limit for that field is ${ADDRESS_MAX}. Trim the opening hours, general information, or FAQs.` };
    }
    return { ok: true };
  }

  // =======================================================================
  // STEP 6 — Emergency protocol
  // =======================================================================
  function renderEmergency(host) {
    host.innerHTML = `
      ${stepHead("Step 6", "Emergency protocol", "The exact operational instructions the AI receptionist must follow when a caller reports a medical emergency.")}
      <div class="field">
        <label class="field__label" for="e-text">Emergency instructions *</label>
        <textarea class="textarea" id="e-text" style="min-height:150px;" maxlength="${EMERGENCY_MAX}" required aria-required="true"
          placeholder="e.g. Tell the caller to call 1122 / local emergency services immediately, do not attempt to book an appointment, then transfer the call to on-call staff.">${esc(model.emergency)}</textarea>
        <div class="onboard-hint" id="e-count"></div>
      </div>`;
    const ta = $("#e-text", host);
    const upd = () => { $("#e-count", host).textContent = `${ta.value.length}/${EMERGENCY_MAX} characters`; };
    ta.addEventListener("input", (e) => { model.emergency = e.target.value; upd(); });
    upd();
  }

  function collectEmergency() {
    model.emergency = trim(model.emergency);
    if (!model.emergency) return { error: "Please describe what the AI should do on an emergency call." };
    if (model.emergency.length > EMERGENCY_MAX) return { error: `Emergency instructions must be ${EMERGENCY_MAX} characters or fewer.` };
    return { ok: true };
  }

  // =======================================================================
  // STEP 7 — AI preferences
  // =======================================================================
  function renderAi(host) {
    host.innerHTML = `
      ${stepHead("Step 7", "AI preferences", "How your AI receptionist sounds and which language it speaks by default.")}
      <div class="onboard-grid">
        <div class="field">
          <label class="field__label" for="ai-tone">Tone</label>
          <select class="select" id="ai-tone">
            ${TONES.map((t) => `<option value="${t}"${model.ai.tone === t ? " selected" : ""}>${t}</option>`).join("")}
          </select>
        </div>
        <div class="field">
          <label class="field__label" for="ai-lang">Preferred language</label>
          <select class="select" id="ai-lang">
            ${LANGUAGES.map((l) => `<option value="${l}"${model.ai.language === l ? " selected" : ""}>${l}</option>`).join("")}
          </select>
        </div>
      </div>
      <div class="onboard-hint" style="margin-top:14px;">
        The receptionist still automatically follows a caller who clearly switches to another
        supported language — this only sets the default it opens with.
      </div>`;
    $("#ai-tone", host).addEventListener("change", (e) => { model.ai.tone = e.target.value; });
    $("#ai-lang", host).addEventListener("change", (e) => { model.ai.language = e.target.value; });
  }

  function collectAi() {
    if (!TONES.includes(model.ai.tone)) return { error: "Choose a valid tone." };
    if (!LANGUAGES.includes(model.ai.language)) return { error: "Choose a valid language." };
    return { ok: true };
  }

  // =======================================================================
  // STEP 8 — Review & Confirm
  // =======================================================================
  function renderReview(host) {
    const b = model.business;
    const g = model.general;
    const payload = buildClinicPayload();
    const row = (label, value) => `
      <div class="onboard-review-row"><dt>${esc(label)}</dt>
      <dd class="${value ? "" : "is-empty"}">${value ? esc(value) : "—"}</dd></div>`;

    host.innerHTML = `
      ${stepHead("Step 8", "Review & confirm", `Check everything below${ctx.workspaceName ? ` for “${ctx.workspaceName}”` : ""}. Use Edit on any section to go back and change it.`)}

      ${reviewSection("Business information", 0, `
        ${row("Clinic name", b.clinicName)}
        ${row("Phone", b.phone)}
        ${row("Email", b.email)}
        ${row("Website", b.website)}
        ${row("Address", [b.street, b.city, [b.state, b.postal].filter(Boolean).join(" "), b.country].filter(Boolean).join(", "))}
        ${row("Google Maps", b.googleMapsLink)}
      `)}

      ${reviewSection("Timezone", 0, row("Timezone", window.TZ ? TZ.label(b.timezone) : b.timezone))}

      ${reviewSection("Doctors", 1, model.doctors.map((d, i) => `
        <div class="onboard-review-row"><dt>Doctor ${i + 1}</dt><dd>${esc(d.name || "—")}${d.specialty ? " · " + esc(d.specialty) : ""}${d.fee !== "" ? " · fee " + esc(d.fee) : ""}${composeTimings(d) ? " · " + esc(composeTimings(d)) : ""}</dd></div>`).join(""))}

      ${reviewSection("Services", 2, `<ul class="onboard-review-list">${model.services.map((s) => `<li>${esc(s)}</li>`).join("") || "<li>—</li>"}</ul>`)}

      ${reviewSection("Appointment settings", 3, `
        ${row("Slot duration", model.appointment.slotMinutes + " minutes")}
        ${row("Max daily bookings", model.appointment.maxDaily || "No limit")}
      `)}

      ${reviewSection("General information", 4, `
        ${row("Parking", g.parking === "yes" ? "Available on site" : g.parking === "no" ? "Not available" : "")}
        ${row("Opening hours", g.openingHours)}
        ${row("Payment methods", g.paymentMethods.join(", "))}
        ${row("General notes", g.generalNotes)}
      `)}

      ${reviewSection("FAQs", 4, g.faqs.length
        ? `<ul class="onboard-review-list">${g.faqs.map((f) => `<li><strong>${esc(f.q)}</strong> — ${esc(f.a)}</li>`).join("")}</ul>`
        : row("FAQs", ""))}

      ${reviewSection("Emergency protocol", 5, row("Instructions", model.emergency))}

      ${reviewSection("AI preferences", 6, `
        ${row("Tone", model.ai.tone)}
        ${row("Preferred language", model.ai.language)}
      `)}

      <details class="onboard-payload">
        <summary>Show the exact data that will be sent to the backend</summary>
        <pre>PATCH /workspaces/${esc(ctx.workspaceId || "{id}")}
${esc(JSON.stringify({ name: b.clinicName, timezone: b.timezone }, null, 2))}

PUT /workspaces/${esc(ctx.workspaceId || "{id}")}/clinic-settings
${esc(JSON.stringify(payload, null, 2))}</pre>
      </details>`;

    $$("[data-edit-step]", host).forEach((btn) => btn.addEventListener("click", () => jumpTo(Number(btn.dataset.editStep))));
  }

  function reviewSection(title, stepIdx, bodyHtml) {
    return `
      <div class="onboard-review-section">
        <div class="onboard-review-section__head">
          <span class="onboard-review-section__title">${esc(title)}</span>
          <button class="btn btn--secondary btn--sm" type="button" data-edit-step="${stepIdx}">Edit</button>
        </div>
        <div class="onboard-review-section__body"><dl style="margin:0;">${bodyHtml}</dl></div>
      </div>`;
  }

  // =======================================================================
  // Compose / hydrate — bridge the wizard model <-> backend contract
  // =======================================================================
  function composeTimings(d) {
    const parts = [];
    const dayLabel = compressDays(d.days);
    if (dayLabel) parts.push(dayLabel);
    if (d.startTime && d.endTime) parts.push(`${d.startTime}–${d.endTime}`);
    if (trim(d.availability)) parts.push(trim(d.availability));
    return parts.join(", ");
  }

  function compressDays(days) {
    if (!days || !days.length) return "";
    const idx = days.map((d) => DAYS.indexOf(d)).filter((i) => i >= 0).sort((a, b) => a - b);
    if (!idx.length) return "";
    let contiguous = idx.every((v, i) => i === 0 || v === idx[i - 1] + 1);
    if (contiguous && idx.length > 2) return `${DAYS[idx[0]]}–${DAYS[idx[idx.length - 1]]}`;
    return idx.map((i) => DAYS[i]).join(", ");
  }

  function composeAddress() {
    const b = model.business;
    const g = model.general;
    const base = [
      trim(b.street),
      trim(b.city),
      [trim(b.state), trim(b.postal)].filter(Boolean).join(" "),
      trim(b.country),
    ].filter(Boolean).join(", ");

    const segs = [];
    if (trim(b.phone)) segs.push(`Phone: ${trim(b.phone)}`);
    if (trim(b.email)) segs.push(`Email: ${trim(b.email)}`);
    if (trim(b.website)) segs.push(`Web: ${trim(b.website)}`);
    if (trim(g.openingHours)) segs.push(`Hours: ${trim(g.openingHours)}`);
    if (trim(g.generalNotes)) segs.push(`Note: ${trim(g.generalNotes)}`);
    (g.faqs || []).forEach((f) => {
      if (trim(f.q) && trim(f.a)) segs.push(`FAQ: ${trim(f.q)} — ${trim(f.a)}`);
    });

    return [base].concat(segs).filter(Boolean).join(SEG);
  }

  function buildClinicPayload() {
    const b = model.business;
    const g = model.general;
    const doctors = model.doctors
      .filter((d) => trim(d.name))
      .map((d) => {
        const timings = composeTimings(d);
        const fee = toNumberOrNull(d.fee);
        return {
          name: trim(d.name),
          specialty: trim(d.specialty) || null,
          timings: timings || null,
          consultation_fee: fee === null || Number.isNaN(fee) ? null : fee,
        };
      });

    const address = composeAddress();
    const maxDaily = toNumberOrNull(model.appointment.maxDaily);

    return {
      doctors,
      services: model.services.map(trim).filter(Boolean),
      business_hours: model.businessHours.map((hours) => ({
        day_of_week: hours.dayOfWeek,
        open_time: hours.isClosed ? null : hours.openTime,
        close_time: hours.isClosed ? null : hours.closeTime,
        is_closed: hours.isClosed,
      })),
      appointment_settings: {
        default_slot_duration_minutes: Math.round(Number(model.appointment.slotMinutes) || 30),
        max_daily_bookings: maxDaily === null || Number.isNaN(maxDaily) ? null : Math.round(maxDaily),
      },
      general_info: {
        address: address || null,
        google_maps_link: trim(b.googleMapsLink) || null,
        parking_available: g.parking === "yes" ? true : g.parking === "no" ? false : null,
        accepted_payment_methods: g.paymentMethods.map(trim).filter(Boolean),
      },
      emergency_protocol: trim(model.emergency) || null,
      agent_tone: model.ai.tone,
      preferred_language: model.ai.language,
    };
  }

  // Parse a previously-saved ClinicSettingsOut back into the wizard model so
  // an onboarded user re-entering the wizard sees their real data.
  function hydrateFromSettings(s) {
    if (Array.isArray(s.doctors) && s.doctors.length) {
      model.doctors = s.doctors.map((d) => ({
        name: d.name || "", specialty: d.specialty || "",
        fee: d.consultation_fee === null || d.consultation_fee === undefined ? "" : String(d.consultation_fee),
        days: [], startTime: "", endTime: "", availability: d.timings || "",
      }));
    }
    if (Array.isArray(s.services) && s.services.length) model.services = s.services.slice();
    if (Array.isArray(s.business_hours) && s.business_hours.length) {
      const byDay = new Map(s.business_hours.map((hours) => [hours.day_of_week, hours]));
      model.businessHours = DAY_NAMES.map((_, day) => {
        const hours = byDay.get(day);
        if (!hours) return { dayOfWeek: day, openTime: "", closeTime: "", isClosed: true };
        return {
          dayOfWeek: day,
          openTime: hours.open_time ? String(hours.open_time).slice(0, 5) : "",
          closeTime: hours.close_time ? String(hours.close_time).slice(0, 5) : "",
          isClosed: Boolean(hours.is_closed),
        };
      });
    }

    const appt = s.appointment_settings || {};
    if (appt.default_slot_duration_minutes) model.appointment.slotMinutes = appt.default_slot_duration_minutes;
    if (appt.max_daily_bookings !== null && appt.max_daily_bookings !== undefined) {
      model.appointment.maxDaily = String(appt.max_daily_bookings);
    }

    const gi = s.general_info || {};
    if (gi.google_maps_link) model.business.googleMapsLink = gi.google_maps_link;
    if (gi.parking_available === true) model.general.parking = "yes";
    else if (gi.parking_available === false) model.general.parking = "no";
    if (Array.isArray(gi.accepted_payment_methods) && gi.accepted_payment_methods.length) {
      model.general.paymentMethods = gi.accepted_payment_methods.slice();
    }
    if (gi.address) parseComposedAddress(gi.address);

    if (s.emergency_protocol) model.emergency = s.emergency_protocol;
    if (s.agent_tone && TONES.includes(s.agent_tone)) model.ai.tone = s.agent_tone;
    if (s.preferred_language && LANGUAGES.includes(s.preferred_language)) model.ai.language = s.preferred_language;
  }

  function parseComposedAddress(str) {
    const parts = String(str).split(SEG).map((p) => p.trim()).filter(Boolean);
    const faqs = [];
    let addrChunk = "";
    parts.forEach((p, i) => {
      if (/^Phone:\s*/i.test(p)) model.business.phone = p.replace(/^Phone:\s*/i, "");
      else if (/^Email:\s*/i.test(p)) model.business.email = p.replace(/^Email:\s*/i, "");
      else if (/^Web:\s*/i.test(p)) model.business.website = p.replace(/^Web:\s*/i, "");
      else if (/^Hours:\s*/i.test(p)) model.general.openingHours = p.replace(/^Hours:\s*/i, "");
      else if (/^Note:\s*/i.test(p)) model.general.generalNotes = p.replace(/^Note:\s*/i, "");
      else if (/^FAQ:\s*/i.test(p)) {
        const body = p.replace(/^FAQ:\s*/i, "");
        const m = body.split(" — ");
        faqs.push({ q: (m[0] || "").trim(), a: (m.slice(1).join(" — ") || "").trim() });
      } else if (i === 0) addrChunk = p;
      else addrChunk = addrChunk ? `${addrChunk}${SEG}${p}` : p;
    });
    if (faqs.length) model.general.faqs = faqs;
    // Best-effort: the plain address chunk goes into the street field; the
    // user can re-split it across city/state/etc. if they choose.
    if (addrChunk) model.business.street = addrChunk;
  }

  // =======================================================================
  // Submit
  // =======================================================================
  async function submit() {
    showError("");

    // Full validation of every step before we touch the network.
    for (let i = 0; i < STEPS.length - 1; i++) {
      const res = STEPS[i].collect();
      if (res && res.error) {
        currentStep = i;
        visited.add(i);
        renderStep();
        showError(res.error);
        return;
      }
    }

    const wsId = ctx.workspaceId || (Api.getWorkspaceId && Api.getWorkspaceId());
    if (!wsId) {
      showError("No workspace is selected for your account. Please sign out and sign in again.");
      return;
    }

    const btn = $("#ob-next", screenEl);
    const backBtn = $("#ob-back", screenEl);
    btn.classList.add("is-loading");
    btn.disabled = true;
    backBtn.disabled = true;

    try {
      // Both writes target `wsId` (= ctx.workspaceId) explicitly. The PUT
      // below flips is_onboarded for THIS workspace only — never globally,
      // and there is no longer any User-level onboarding flag to touch.
      await Api.workspaces.update(wsId, {
        name: trim(model.business.clinicName),
        timezone: trim(model.business.timezone),
      });
      await Api.clinicSettings.saveFor(wsId, buildClinicPayload());
      // Success — the backend has flipped this workspace's is_onboarded. Hand
      // back to app.js, which refreshes state and routes into the dashboard.
      teardown();
      cbs.onComplete();
    } catch (err) {
      const msg = (err && err.message) || "Couldn't save your setup. Please check your connection and try again.";
      showError(msg + " Your entries have been kept — press Complete Setup to retry.");
      btn.classList.remove("is-loading");
      btn.disabled = false;
      backBtn.disabled = false;
    }
  }

  // =======================================================================
  function stepHead(eyebrow, title, sub) {
    return `<div class="onboard-step-head">
      <div class="onboard-step-head__eyebrow">${esc(eyebrow)}</div>
      <h1 class="onboard-step-head__title">${esc(title)}</h1>
      <div class="onboard-step-head__sub">${esc(sub)}</div>
    </div>`;
  }

  return { start, isActive, teardown };
})();

// Backwards-compatible alias — app.js historically called `ClinicSetup.start`.
window.ClinicSetup = window.ClinicOnboarding;
