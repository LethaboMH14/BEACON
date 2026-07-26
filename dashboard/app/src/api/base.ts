/**
 * API base URL resolution.
 *
 * Local dev: VITE_API_BASE unset, calls stay relative ("/v1/...") and hit
 * vite's dev proxy to localhost:8000 (see vite.config.ts) — unchanged
 * behaviour, nothing to configure.
 *
 * Deployed (e.g. Vercel): there is no dev proxy, so relative paths would hit
 * the frontend's own origin instead of the API. Set VITE_API_BASE to the
 * deployed API's origin (e.g. https://beacon-api.<...>.azurecontainerapps.io)
 * at build time and every call below picks it up automatically.
 */
const API_BASE = (import.meta.env.VITE_API_BASE ?? '').replace(/\/$/, '');

export function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
}

export function wsUrl(path: string): string {
  if (!API_BASE) {
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${proto}//${window.location.host}${path}`;
  }
  return `${API_BASE.replace(/^http/, 'ws')}${path}`;
}
