/**
 * Phase 12 — reusable JavaScript API service layer for the FastAPI backend.
 *
 * Every call goes through `request()`, which:
 *   - attaches the stored bearer token (unless `auth:false` is passed)
 *   - serializes/parses JSON
 *   - normalizes every failure into an `ApiError` with a `.status` and a
 *     human-readable `.message`
 *   - on a 401, clears the stored session and broadcasts a
 *     `window "ar:auth-expired"` event exactly once per expiry, so the app
 *     shell can drop the user back to the login screen without every
 *     caller having to special-case 401 itself
 *
 * Nothing here renders UI — this module only talks to the network. app.js
 * owns loading/empty/error rendering around these calls.
 */
const Api = (() => {
  // See js/config.js — the one file a deployment edits to point this
  // static frontend at its own backend. Falls back to localhost so local
  // dev keeps working even if config.js is ever missing.
  const BASE_URL = window.__AI_RECEPTIONIST_CONFIG__?.API_BASE_URL || "http://localhost:8000/api/v1";

  const STORAGE_KEYS = {
    token: "ar_access_token",
    expiresAt: "ar_token_expires_at",
    workspaceId: "ar_workspace_id",
    // "single" | "multi" — the setup model a brand-new user picks on the
    // get-started screen. A routing hint only; the real state is the set of
    // workspaces the backend returns for this user.
    branchModel: "ar_branch_model",
  };

  class ApiError extends Error {
    constructor(message, status, details) {
      super(message);
      this.name = "ApiError";
      this.status = status; // null => network/offline failure, not an HTTP status
      this.details = details;
    }
  }

  // -- session storage ---------------------------------------------------------

  function getToken() {
    return localStorage.getItem(STORAGE_KEYS.token);
  }

  function getTokenExpiry() {
    const raw = localStorage.getItem(STORAGE_KEYS.expiresAt);
    return raw ? new Date(raw) : null;
  }

  function isTokenExpired() {
    const expiry = getTokenExpiry();
    if (!expiry) return false; // unknown expiry — let the server be the judge
    return expiry.getTime() <= Date.now();
  }

  function setSession({ access_token, expires_at }) {
    localStorage.setItem(STORAGE_KEYS.token, access_token);
    localStorage.setItem(STORAGE_KEYS.expiresAt, expires_at);
  }

  function clearSession() {
    localStorage.removeItem(STORAGE_KEYS.token);
    localStorage.removeItem(STORAGE_KEYS.expiresAt);
  }

  function getWorkspaceId() {
    return localStorage.getItem(STORAGE_KEYS.workspaceId);
  }

  function setWorkspaceId(id) {
    if (id) localStorage.setItem(STORAGE_KEYS.workspaceId, id);
  }

  function clearWorkspaceId() {
    localStorage.removeItem(STORAGE_KEYS.workspaceId);
  }

  function getBranchModel() {
    return localStorage.getItem(STORAGE_KEYS.branchModel); // "single" | "multi" | null
  }
  function setBranchModel(model) {
    if (model === "single" || model === "multi") localStorage.setItem(STORAGE_KEYS.branchModel, model);
  }
  function clearBranchModel() {
    localStorage.removeItem(STORAGE_KEYS.branchModel);
  }

  function isAuthenticated() {
    return Boolean(getToken()) && !isTokenExpired();
  }

  let expiryBroadcast = false;

  function broadcastAuthExpired() {
    if (expiryBroadcast) return;
    expiryBroadcast = true;
    clearSession();
    window.dispatchEvent(new CustomEvent("ar:auth-expired"));
    // Re-arm shortly after so a *future* expiry (next login session) can
    // broadcast again — this only guards against firing twice for the
    // same expiry when several requests 401 back-to-back.
    setTimeout(() => { expiryBroadcast = false; }, 2000);
  }

  // -- core request ------------------------------------------------------------

  async function request(path, { method = "GET", body, auth = true, query } = {}) {
    if (auth && !getToken()) {
      throw new ApiError("Not signed in.", 401);
    }
    if (auth && isTokenExpired()) {
      broadcastAuthExpired();
      throw new ApiError("Your session has expired. Please sign in again.", 401);
    }

    let url = `${BASE_URL}${path}`;
    if (query && Object.keys(query).length) {
      const params = new URLSearchParams();
      Object.entries(query).forEach(([k, v]) => {
        if (v !== undefined && v !== null && v !== "") params.set(k, v);
      });
      const qs = params.toString();
      if (qs) url += `?${qs}`;
    }

    const headers = { "Content-Type": "application/json" };
    if (auth) headers.Authorization = `Bearer ${getToken()}`;

    let response;
    try {
      response = await fetch(url, {
        method,
        headers,
        body: body !== undefined ? JSON.stringify(body) : undefined,
      });
    } catch (networkError) {
      throw new ApiError(
        "Could not reach the server. Check your connection and that the backend is running.",
        null,
        networkError
      );
    }

    if (response.status === 401) {
      broadcastAuthExpired();
      throw new ApiError("Your session has expired. Please sign in again.", 401);
    }

    if (response.status === 204) return null;

    let payload = null;
    const text = await response.text();
    if (text) {
      try {
        payload = JSON.parse(text);
      } catch {
        payload = text;
      }
    }

    if (!response.ok) {
      const message = extractErrorMessage(payload, response.status);
      throw new ApiError(message, response.status, payload);
    }

    return payload;
  }

  function extractErrorMessage(payload, status) {
    if (payload && typeof payload === "object") {
      if (typeof payload.detail === "string") return payload.detail;
      if (Array.isArray(payload.detail)) {
        return payload.detail.map((d) => d.msg || JSON.stringify(d)).join("; ");
      }
    }
    if (status === 403) return "You don't have permission to do that.";
    if (status === 404) return "Not found.";
    if (status >= 500) return "The server ran into a problem. Please try again.";
    return "Something went wrong with that request.";
  }

  function workspacePath(sub) {
    const wsId = getWorkspaceId();
    if (!wsId) throw new ApiError("No workspace selected.", null);
    return `/workspaces/${wsId}${sub}`;
  }

  // -- Auth ----------------------------------------------------------------------
  const auth = {
    async register({ email, password, fullName }) {
      return request("/auth/register", {
        auth: false,
        method: "POST",
        body: { email, password, full_name: fullName },
      });
    },
    async login({ email, password }) {
      const data = await request("/auth/login", { auth: false, method: "POST", body: { email, password } });
      setSession(data);
      return data;
    },
    async logout() {
      try {
        await request("/auth/logout", { method: "POST" });
      } catch {
        // Best-effort — the client-side session is cleared regardless.
      }
      clearSession();
      clearWorkspaceId();
      clearBranchModel();
    },
    async me() {
      return request("/auth/me");
    },
  };

  // -- Workspaces ------------------------------------------------------------------
  const workspaces = {
    async list() {
      return request("/workspaces");
    },
    async create({ name, slug, timezone = "UTC" }) {
      return request("/workspaces", { method: "POST", body: { name, slug, timezone } });
    },
    async get(workspaceId) {
      return request(`/workspaces/${workspaceId}`);
    },
    async update(workspaceId, patch) {
      return request(`/workspaces/${workspaceId}`, { method: "PATCH", body: patch });
    },
    async listMembers() {
      return request(workspacePath("/members"));
    },
    async addMember({ email, role, phoneNumber }) {
      // `phone_number` is optional and maps onto the backend `User.phone`
      // column (see app/schemas/workspace.py MemberInvite). Omitted from
      // the payload entirely when not provided.
      const body = { email, role };
      if (phoneNumber) body.phone_number = phoneNumber;
      return request(workspacePath("/members"), { method: "POST", body });
    },
  };

  // -- Clinic settings / AI knowledge base (onboarding /setup) ----------------
  const clinicSettings = {
    async get() {
      return request(workspacePath("/clinic-settings"));
    },
    // Read a SPECIFIC workspace's settings (Branch Management shows each
    // branch's location without switching the active workspace). Same
    // endpoint + auth (settings:read → membership); not onboarding-gated.
    async getFor(workspaceId) {
      return request(`/workspaces/${workspaceId}/clinic-settings`);
    },
    async save(payload) {
      return request(workspacePath("/clinic-settings"), { method: "PUT", body: payload });
    },
    // Write a SPECIFIC workspace's settings. The onboarding wizard always
    // targets the branch it was opened for (ctx.workspaceId) — never whichever
    // workspace happens to be "active" — so it must not go through
    // workspacePath(). A successful PUT flips that workspace's is_onboarded
    // server-side (and only that workspace's).
    async saveFor(workspaceId, payload) {
      return request(`/workspaces/${workspaceId}/clinic-settings`, { method: "PUT", body: payload });
    },
  };

  // -- Leads -------------------------------------------------------------------
  const leads = {
    async list() {
      return request(workspacePath("/leads"));
    },
    async get(id) {
      return request(workspacePath(`/leads/${id}`));
    },
    async create(payload) {
      return request(workspacePath("/leads"), { method: "POST", body: payload });
    },
  };

  // -- Patients ----------------------------------------------------------------
  const patients = {
    async list() {
      return request(workspacePath("/patients"));
    },
    async get(id) {
      return request(workspacePath(`/patients/${id}`));
    },
    async create(payload) {
      return request(workspacePath("/patients"), { method: "POST", body: payload });
    },
  };

  // -- Appointments --------------------------------------------------------------
  const appointments = {
    async list() {
      return request(workspacePath("/appointments"));
    },
    async get(id) {
      return request(workspacePath(`/appointments/${id}`));
    },
    async create(payload) {
      return request(workspacePath("/appointments"), { method: "POST", body: payload });
    },
  };

  // -- Scheduling resources ------------------------------------------------------
  const providers = {
    async list() {
      return request(workspacePath("/providers"));
    },
  };

  const services = {
    async list() {
      return request(workspacePath("/services"));
    },
  };

  // -- Calls + transcripts --------------------------------------------------------
  const calls = {
    async list() {
      return request(workspacePath("/calls"));
    },
    async get(id) {
      return request(workspacePath(`/calls/${id}`));
    },
    async transcripts(id) {
      return request(workspacePath(`/calls/${id}/transcripts`));
    },
  };

  // -- Human handoffs (Receptionist escalations) ------------------------------------
  const handoffs = {
    async list() {
      return request(workspacePath("/human-handoffs"));
    },
  };

  // -- Notification messages (WhatsApp / email delivery log) -----------------------
  const notificationMessages = {
    async list() {
      return request(workspacePath("/notification-messages"));
    },
  };

  // -- Analytics (Phase 13) ---------------------------------------------------------
  const analytics = {
    async summary({ since, until } = {}) {
      return request(workspacePath("/analytics/summary"), {
        query: { since: since || undefined, until: until || undefined },
      });
    },
  };

  // -- Workspace integrations ----------------------------------------------------
  const integrations = {
    async googleStatus() {
      return request("/integrations/google/status", { query: { workspace_id: getWorkspaceId() } });
    },
    async googleConnect() {
      return request("/integrations/google/connect", { query: { workspace_id: getWorkspaceId() } });
    },
    async googleDisconnect() {
      return request("/integrations/google/disconnect", {
        method: "POST",
        query: { workspace_id: getWorkspaceId() },
      });
    },
  };

  // -- AI Receptionist conversation (test-drive widget) -----------------------------
  const ai = {
    async startSession() {
      return request(workspacePath("/ai/sessions"), { method: "POST" });
    },
    async sendMessage(sessionId, message) {
      return request(workspacePath(`/ai/sessions/${sessionId}/messages`), { method: "POST", body: { message } });
    },
    async getSession(sessionId) {
      return request(workspacePath(`/ai/sessions/${sessionId}`));
    },
  };

  const health = {
    async check() {
      return request("/health", { auth: false });
    },
  };

  return {
    ApiError,
    request,
    getToken, isTokenExpired, isAuthenticated, clearSession,
    getWorkspaceId, setWorkspaceId, clearWorkspaceId,
    getBranchModel, setBranchModel, clearBranchModel,
    auth, workspaces, clinicSettings, leads, patients, appointments, providers, services,
    calls, handoffs, notificationMessages, ai, health, analytics, integrations,
  };
})();
