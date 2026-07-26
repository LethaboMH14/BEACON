/**
 * Safest route — pick a destination, get route options ranked by claims exposure.
 *
 * WHAT IS REAL AND WHAT IS APPROXIMATE (read before changing any copy here)
 * Real: the exposure scores, the suburbs named, the claim counts, the advice
 * line. All of it comes from POST /v1/routes/safest scoring the corridor against
 * all 709 geocoded suburbs from Ndu's pipeline.
 * Approximate: the corridor geometry. Real road geometry needs a routing
 * provider (OpenRouteService); no key is in this repo. So candidates are built
 * as corridors between origin and destination with a lateral offset, tagged
 * geometry_source:'approx', and the screen SAYS SO on the card. When a provider
 * is wired in, buildCandidates() is the only thing that changes.
 *
 * The design's separate "empty state" frame is the no-destination-yet state here.
 */
import { useEffect, useMemo, useState } from 'react';
import { MapContainer, TileLayer, Polyline, CircleMarker } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import { colors } from '../../theme/tokens';
import { scoreRoutes, type CandidateRoute, type LatLng, type ScoredRoute, type SafestRouteResponse } from '../../api/member';
import { Button, Card, Chip, MethodNote, Screen, ScreenHeader, Skeleton, ErrorState, radii } from '../ui';
import { recordExposure } from './Rewards';

interface Place { name: string; sub: string; at: LatLng }

// The design's Saved places, with real coordinates so they route for real.
const SAVED: Place[] = [
  { name: 'Home', sub: 'Rivonia', at: [-26.0553, 28.0606] },
  { name: 'Work', sub: 'Sandton CBD', at: [-26.1076, 28.0567] },
  { name: 'School run', sub: 'Fourways', at: [-26.0170, 28.0100] },
  { name: 'Gym', sub: 'Bryanston', at: [-26.0514, 28.0281] },
];

/**
 * Two candidate corridors between A and B.
 *
 * Both are polylines through interpolated waypoints; one bows left of the direct
 * line, one bows right, by ~1.5 km at the midpoint. That is enough separation to
 * pass either side of a hotspot cluster, which is the whole point of offering a
 * choice. It is NOT a road network and is labelled as such.
 */
function buildCandidates(from: LatLng, to: LatLng): CandidateRoute[] {
  const [aLat, aLng] = from;
  const [bLat, bLng] = to;
  const dLat = bLat - aLat;
  const dLng = bLng - aLng;
  const len = Math.hypot(dLat, dLng) || 1e-9;
  // perpendicular unit vector in degrees; ~0.0135deg ≈ 1.5 km
  const pLat = -dLng / len;
  const pLng = dLat / len;
  const bow = 0.0135;

  const STEPS = 8;
  const make = (sign: number): LatLng[] =>
    Array.from({ length: STEPS + 1 }, (_, i) => {
      const t = i / STEPS;
      // sine bow: zero at both ends, maximum in the middle
      const k = Math.sin(Math.PI * t) * bow * sign;
      return [aLat + dLat * t + pLat * k, aLng + dLng * t + pLng * k] as LatLng;
    });

  // Straight-line distance in km, used only for a plausible duration estimate.
  const km = Math.hypot(dLat * 111, dLng * 96);
  return [
    { id: 'west', label: 'Western corridor', polyline: make(1), duration_minutes: Math.round(km * 1.9), geometry_source: 'approx' },
    { id: 'east', label: 'Eastern corridor', polyline: make(-1), duration_minutes: Math.round(km * 1.75), geometry_source: 'approx' },
  ];
}

export default function SafestRoute() {
  const [from, setFrom] = useState<Place>(SAVED[1]);
  const [to, setTo] = useState<Place | null>(null);
  const [departHour, setDepartHour] = useState<number>(() => new Date().getHours());
  const [res, setRes] = useState<SafestRouteResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [startedId, setStartedId] = useState<string | null>(null);

  const candidates = useMemo(() => (to ? buildCandidates(from.at, to.at) : []), [from, to]);

  useEffect(() => {
    if (!candidates.length) { setRes(null); return; }
    let cancelled = false;
    setLoading(true); setError(null);
    scoreRoutes(candidates, departHour)
      .then((r) => { if (!cancelled) setRes(r); })
      .catch((e: Error) => { if (!cancelled) setError(e.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [candidates, departHour]);

  const byId = useMemo(() => new Map(candidates.map((c) => [c.id, c])), [candidates]);

  return (
    <Screen>
      <ScreenHeader title="Safer route" subtitle="Ranked by local crime reports history along the way" />

      {/* origin / destination */}
      <Card style={{ padding: 14, marginBottom: 14 }}>
        <PlaceRow label="From" place={from} places={SAVED} onPick={setFrom} />
        <div style={{ height: 1, background: colors.lineLight, margin: '10px 0' }} />
        <PlaceRow label="To" place={to} places={SAVED} onPick={setTo} placeholder="Choose a destination" />
      </Card>

      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14, padding: '0 2px' }}>
        <label style={{ fontSize: 12, color: colors.inkMid, whiteSpace: 'nowrap' }}>Leaving at</label>
        <input
          type="range" min={0} max={23} value={departHour}
          onChange={(e) => setDepartHour(Number(e.target.value))}
          style={{ flex: 1, accentColor: colors.discovery, height: 24 }}
        />
        <span className="tabular-nums" style={{ fontSize: 13, fontWeight: 700, minWidth: 44 }}>
          {String(departHour).padStart(2, '0')}:00
        </span>
      </div>

      {!to && (
        <Card style={{ textAlign: 'center', padding: '28px 18px' }}>
          <div style={{ fontSize: 15, fontWeight: 650, marginBottom: 6 }}>Where are you heading?</div>
          <p style={{ margin: 0, fontSize: 13, color: colors.inkMid, lineHeight: 1.5 }}>
            Pick a destination and we'll compare route options against 15,712 local crime reports.
          </p>
        </Card>
      )}

      {error && <ErrorState message={error} onRetry={() => setDepartHour((h) => h)} />}

      {to && loading && !res && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <Skeleton h={150} /><Skeleton h={110} />
        </div>
      )}

      {res && to && (
        <>
          <div style={{
            height: 190, borderRadius: radii.card, overflow: 'hidden',
            border: `1px solid ${colors.lineLight}`, marginBottom: 14, boxShadow: colors.shadowCard,
          }}>
            <MapContainer
              key={`${from.name}-${to.name}`}
              bounds={[from.at, to.at]} boundsOptions={{ padding: [28, 28] }}
              style={{ height: '100%', width: '100%' }} zoomControl={false} scrollWheelZoom={false}
            >
              <TileLayer attribution="&copy; OpenStreetMap" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
              {res.routes.map((r) => {
                const c = byId.get(r.id);
                if (!c) return null;
                return (
                  <Polyline
                    key={r.id} positions={c.polyline}
                    pathOptions={{
                      color: r.recommended ? colors.safe : colors.inkLo,
                      weight: r.recommended ? 5 : 3,
                      opacity: r.recommended ? 0.95 : 0.5,
                      dashArray: r.recommended ? undefined : '6 6',
                    }}
                  />
                );
              })}
              <CircleMarker center={from.at} radius={7} pathOptions={{ fillColor: colors.discovery, color: '#fff', weight: 2, fillOpacity: 1 }} />
              <CircleMarker center={to.at} radius={7} pathOptions={{ fillColor: colors.beacon, color: '#fff', weight: 2, fillOpacity: 1 }} />
            </MapContainer>
          </div>

          {res.exposure_reduction_pct != null && (
            <div style={{
              display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12, padding: '11px 14px',
              borderRadius: radii.control, background: colors.discoverySoft,
              border: `1px solid color-mix(in srgb, ${colors.discovery} 18%, transparent)`,
            }}>
              <span style={{ fontSize: 20 }}>🛡️</span>
              <span style={{ fontSize: 13, color: colors.inkHi, lineHeight: 1.4 }}>
                The recommended route has <strong>{res.exposure_reduction_pct}% less</strong> claims exposure than the alternative.
              </span>
            </div>
          )}

          {res.routes.map((r) => (
            <RouteCard
              key={r.id}
              r={r}
              started={startedId === r.id}
              onStart={() => {
                const alt = res.routes.find((o) => o.id !== r.id);
                if (alt) recordExposure(r.exposure_score, alt.exposure_score);
                setStartedId(r.id);
              }}
            />
          ))}

          <MethodNote>{res.method} Scored against {res.hotspots_considered} suburbs · {res.model_version}.</MethodNote>
        </>
      )}
    </Screen>
  );
}

function RouteCard({ r, started, onStart }: { r: ScoredRoute; started: boolean; onStart: () => void }) {
  const worst = r.suburbs[0];
  return (
    <Card
      style={{ marginBottom: 10 }}
      accent={r.recommended ? `color-mix(in srgb, ${colors.safe} 45%, transparent)` : undefined}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 10 }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 5 }}>
            <span style={{ fontSize: 15.5, fontWeight: 700 }}>{r.label}</span>
            {r.recommended && <Chip tone="safe">Recommended</Chip>}
          </div>
          <div className="tabular-nums" style={{ fontSize: 13, color: colors.inkMid }}>
            {r.duration_minutes != null && <>{r.duration_minutes} min · </>}{r.distance_km.toFixed(1)} km
          </div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontSize: 10, textTransform: 'uppercase', letterSpacing: 0.5, color: colors.inkLo, fontWeight: 600 }}>Exposure</div>
          <div className="tabular-nums" style={{ fontSize: 19, fontWeight: 700, color: r.recommended ? colors.safe : colors.high }}>
            {r.exposure_score.toFixed(1)}
          </div>
        </div>
      </div>

      {r.advice && (
        <p style={{ margin: '11px 0 0', fontSize: 13, lineHeight: 1.5, color: colors.inkMid }}>{r.advice}</p>
      )}

      {worst && (
        <div style={{ display: 'flex', gap: 6, marginTop: 10, flexWrap: 'wrap' }}>
          {r.suburbs.slice(0, 3).map((s) => (
            <Chip key={s.hex_id} tone={s.severity >= 0.66 ? 'critical' : s.severity >= 0.33 ? 'high' : 'watch'}>
              {s.suburb.replace(/\b\w/g, (c) => c.toUpperCase())} {s.severity.toFixed(2)}
              {s.at_peak_hour && ' · peak'}
            </Chip>
          ))}
        </div>
      )}

      {r.recommended && (
        <div style={{ marginTop: 12 }}>
          {/* Starting the route is what makes the Vitality figure real: it
              records the exposure you actually accepted against the one you
              declined, so Rewards computes a measured reduction rather than a
              marketing number. */}
          <Button onClick={onStart}>{started ? 'Route started' : 'Start this route'}</Button>
        </div>
      )}

      {r.geometry_source === 'approx' && (
        <MethodNote>
          Corridor is an approximation, not turn-by-turn road geometry. The claims exposure along it is real.
        </MethodNote>
      )}
    </Card>
  );
}

function PlaceRow({ label, place, places, onPick, placeholder }: {
  label: string; place: Place | null; places: Place[]; onPick: (p: Place) => void; placeholder?: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button
        onClick={() => setOpen((o) => !o)}
        style={{
          display: 'flex', alignItems: 'center', gap: 12, width: '100%', minHeight: 44,
          background: 'transparent', border: 'none', padding: 0, cursor: 'pointer', textAlign: 'left',
        }}
      >
        <span style={{
          width: 30, height: 30, borderRadius: 10, background: colors.discoverySoft, color: colors.discovery,
          display: 'grid', placeItems: 'center', fontSize: 11, fontWeight: 700, flexShrink: 0,
        }}>{label[0]}</span>
        <span style={{ flex: 1 }}>
          <span style={{ display: 'block', fontSize: 10.5, textTransform: 'uppercase', letterSpacing: 0.5, color: colors.inkLo, fontWeight: 600 }}>{label}</span>
          <span style={{ display: 'block', fontSize: 14.5, fontWeight: 650, color: place ? colors.inkHi : colors.inkLo }}>
            {place ? `${place.name} · ${place.sub}` : placeholder}
          </span>
        </span>
        <span style={{ color: colors.inkLo, fontSize: 12 }}>{open ? '▲' : '▼'}</span>
      </button>

      {open && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2, marginTop: 8 }}>
          {places.map((p) => (
            <button key={p.name} onClick={() => { onPick(p); setOpen(false); }} style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 42,
              padding: '0 12px', borderRadius: radii.chip, fontSize: 13.5, cursor: 'pointer',
              border: `1px solid ${place?.name === p.name ? colors.discovery : 'transparent'}`,
              background: place?.name === p.name ? colors.discoverySoft : colors.bg50, color: colors.inkHi,
            }}>
              <span style={{ fontWeight: 600 }}>{p.name}</span>
              <span style={{ color: colors.inkLo, fontSize: 12 }}>{p.sub}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
