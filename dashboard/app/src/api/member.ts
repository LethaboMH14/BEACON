/**
 * REST client for the member-facing endpoints.
 *
 * Split from client.ts (the ops console's client) because the two surfaces have
 * genuinely different contracts — the console asks "which hexes are hottest",
 * the member app asks "draw me this suburb and explain it". Shapes are copied
 * from server/src/api/hotspots_geo.py and safest_route.py; keep in sync.
 *
 * Every field here is server-computed, including marker colour and radius. That
 * is deliberate: the standalone hotspot_map.html the client already approved
 * uses specific colour/size rules from hotspot_pipeline/build_hotspots.py, and
 * re-deriving them in TypeScript is how the in-app map quietly stops matching
 * the artifact everyone signed off on.
 */

import { apiUrl } from './base';

async function get<T>(path: string): Promise<T> {
  const res = await fetch(apiUrl(path));
  if (!res.ok) throw new Error(`GET ${path} -> ${res.status} ${res.statusText}`);
  return res.json();
}

export interface HotspotGeo {
  hex_id: string;
  suburb: string;
  lat: number;
  lng: number;
  severity_score: number;
  incident_count: number | null;
  top_claim_type: string | null;
  peak_hour: number;
  peak_day_of_week: string | null;
  peak_month: string | null;
  total_claim_cost: number;
  avg_claim_cost: number;
  color: string;
  radius: number;
}

export interface HotspotsGeoResponse {
  count: number;
  total_claims_analysed: number;
  method: string;
  /** Must be surfaced somewhere on any screen that renders these points. */
  caveat: string;
  model_version: string;
  hotspots: HotspotGeo[];
}

export interface HotspotFilters {
  hour?: number;
  day?: string;
  peril?: string;
  minSeverity?: number;
}

export async function getHotspotsGeo(f: HotspotFilters = {}): Promise<HotspotsGeoResponse> {
  const p = new URLSearchParams();
  if (f.hour !== undefined) p.set('hour', String(f.hour));
  if (f.day) p.set('day', f.day);
  if (f.peril) p.set('peril', f.peril);
  if (f.minSeverity !== undefined) p.set('min_severity', String(f.minSeverity));
  const qs = p.toString();
  return get(`/v1/hotspots/geo${qs ? `?${qs}` : ''}`);
}

export type LatLng = [number, number];

export interface CandidateRoute {
  id: string;
  label: string;
  polyline: LatLng[];
  duration_minutes?: number;
  /** 'ors' = real road geometry. 'approx' = straight-line; the UI must say so. */
  geometry_source: 'ors' | 'approx';
}

export interface SuburbExposure {
  suburb: string;
  hex_id: string;
  severity: number;
  top_claim_type: string | null;
  incident_count: number | null;
  exposed_metres: number;
  at_peak_hour: boolean;
  contribution: number;
}

export interface ScoredRoute {
  id: string;
  label: string;
  geometry_source: string;
  distance_km: number;
  duration_minutes: number | null;
  exposure_score: number;
  recommended: boolean;
  advice: string | null;
  suburbs: SuburbExposure[];
}

export interface SafestRouteResponse {
  depart_hour: number;
  routes: ScoredRoute[];
  exposure_reduction_pct: number | null;
  hotspots_considered: number;
  method: string;
  model_version: string;
}

export async function scoreRoutes(
  routes: CandidateRoute[],
  departHour?: number,
): Promise<SafestRouteResponse> {
  const res = await fetch(apiUrl('/v1/routes/safest'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ routes, depart_hour: departHour ?? null }),
  });
  if (!res.ok) throw new Error(`POST /v1/routes/safest -> ${res.status} ${res.statusText}`);
  return res.json();
}
