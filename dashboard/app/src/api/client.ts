/**
 * REST client for the real BEACON server (server/src/main.py).
 * Dev server proxies /v1 -> http://localhost:8000 (see vite.config.ts).
 * Endpoint shapes copied from server/src/api/*.py response models — keep in sync.
 */

export interface RiskEstimate {
  hex_id: string;
  hour: number;
  risk_score: number;
  label: string;
  source: string;
  top_factors?: Record<string, unknown> | null;
  model_version?: string | null;
}

export interface HotspotEntry {
  hex_id: string;
  risk_score: number;
  label: string;
  source: string;
}

export interface HotspotsResponse {
  hour: number;
  hotspots: HotspotEntry[];
}

export interface CameraStatusEntry {
  id: string;
  name: string;
  hex_id: string | null;
  last_seen_at: string | null;
  online: boolean;
}

export interface CamerasResponse {
  cameras: CameraStatusEntry[];
}

export interface EventEntry {
  event: string;
  ts: string;
  data: Record<string, unknown>;
}

export interface EventsSinceResponse {
  since: string;
  events: EventEntry[];
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) {
    throw new Error(`${path} -> ${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

export async function getHealth(): Promise<{ status: string }> {
  return get('/health');
}

export async function getRisk(hex: string, hour?: number): Promise<RiskEstimate> {
  const params = new URLSearchParams({ hex });
  if (hour !== undefined) params.set('hour', String(hour));
  return get(`/v1/risk?${params.toString()}`);
}

export async function getHotspots(window?: number, limit = 20): Promise<HotspotsResponse> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (window !== undefined) params.set('window', String(window));
  return get(`/v1/hotspots?${params.toString()}`);
}

export async function getCameras(): Promise<CamerasResponse> {
  return get('/v1/cameras');
}

export async function getEventsSince(ts: string, limit = 200): Promise<EventsSinceResponse> {
  const params = new URLSearchParams({ ts, limit: String(limit) });
  return get(`/v1/events/since?${params.toString()}`);
}

export async function verifyEntity(entityId: string): Promise<unknown> {
  const res = await fetch(`/v1/entities/${encodeURIComponent(entityId)}/verify`, { method: 'POST' });
  if (!res.ok) throw new Error(`verify ${entityId} -> ${res.status} ${res.statusText}`);
  return res.json();
}
