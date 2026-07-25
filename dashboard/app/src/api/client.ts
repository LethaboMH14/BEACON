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

export interface SightingBrief {
  id: number;
  camera_id: string;
  ts: string;
  hex_id: string | null;
  kind: string;
  confidence: number;
}

export interface EntityFactors {
  recurrence: number | null;
  time_anomaly: number | null;
  crime_correlation: number | null;
  casing_behaviour: number | null;
  territory_roaming: number | null;
  modal_corroboration: number | null;
}

export interface EntityDetail {
  id: string;
  kind: string;
  plate_text: string | null;
  state: string;
  base_score: number;
  current_score: number;
  last_updated: string;
  first_seen: string;
  last_seen: string;
  sighting_count: number;
  factors: EntityFactors;
  recent_sightings: SightingBrief[];
}

export type VerifyActionKind = 'flag' | 'dismiss' | 'whitelist';

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

export async function getEntity(entityId: string): Promise<EntityDetail> {
  return get(`/v1/entities/${encodeURIComponent(entityId)}`);
}

export async function verifyEntityAction(
  entityId: string,
  action: VerifyActionKind,
  operatorId: string,
  operatorToken: string,
  note?: string,
  hexId?: string,
): Promise<{ status: string; entity_id: string; incident_id?: string; alert_id?: string; hex_id?: string }> {
  const res = await fetch(`/v1/entities/${encodeURIComponent(entityId)}/verify`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Operator-Token': operatorToken },
    body: JSON.stringify({ action, operator_id: operatorId, note: note || null, hex_id: hexId || null }),
  });
  if (!res.ok) throw new Error(`verify ${entityId} (${action}) -> ${res.status} ${res.statusText}`);
  return res.json();
}

export interface DetectionBox {
  x: number; // centre-x in source-frame pixels
  y: number; // centre-y in source-frame pixels
  w: number;
  h: number;
}

/**
 * Full sighting record from GET /v1/sightings.
 *
 * bbox / plate_text / plate_quality / modality have been written on POST since
 * migration 001, but until ADR-0006 no GET route returned them — which is why
 * this screen previously carried three "no backing endpoint" placeholders.
 */
export interface SightingDetail extends SightingBrief {
  entity_id: string | null;
  modality: string;
  created_at: string;
  bbox: DetectionBox | null;
  plate_text: string | null;
  plate_quality: number | null;
  clip_ref: string | null;
  embedding_ref: string | null;
}

export async function getSightings(opts: {
  cameraId?: string;
  entityId?: string;
  modality?: string;
  since?: string;
  limit?: number;
} = {}): Promise<SightingDetail[]> {
  const params = new URLSearchParams();
  if (opts.cameraId) params.set('camera_id', opts.cameraId);
  if (opts.entityId) params.set('entity_id', opts.entityId);
  if (opts.modality) params.set('modality', opts.modality);
  if (opts.since) params.set('since', opts.since);
  params.set('limit', String(opts.limit ?? 100));
  return get(`/v1/sightings?${params.toString()}`);
}
