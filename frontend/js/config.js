/**
 * Phase 16 — runtime configuration for a deployed (Vercel/Netlify/etc.)
 * frontend. This file is deliberately separate from js/api-service.js and
 * loaded before it: since the frontend has no build step, this is the one
 * file each deployment environment edits to point at its own backend —
 * everything else stays identical between dev/staging/production.
 *
 * Local dev needs no changes here (defaults to the backend running on
 * localhost:8000, per the README's "Getting Started"). Deploying the
 * frontend for real: change API_BASE_URL below to that backend's public
 * URL before publishing (see docs/deployment.md — "Frontend deployment"),
 * and add the frontend's deployed origin to the backend's CORS_ORIGINS.
 */
window.__AI_RECEPTIONIST_CONFIG__ = {
  API_BASE_URL: "http://localhost:8000/api/v1",
};
