/**
 * Hotspot map — the in-app version of hotspot_pipeline/hotspot_map.html.
 *
 * The delivered design had `MAP TILES PLACEHOLDER` and a hardcoded Bryanston
 * bottom sheet. This is real Leaflet over real OSM tiles, drawing the real 709
 * geocoded suburbs from GET /v1/hotspots/geo, and the bottom sheet shows
 * whichever marker you actually tapped.
 *
 * MARKER RULES COME FROM THE SERVER, NOT FROM HERE
 * colour and radius are fields on the response, computed by hotspots_geo.py
 * from build_hotspots.py's exact thresholds (>=0.66 red / >=0.33 orange / else
 * yellow; radius 6 + severity*20). The standalone map is the artifact the client
 * approved — re-deriving those rules in TypeScript is how the two silently
 * diverge. Do not "simplify" this by inlining the thresholds.
 *
 * The design's separate "Loading" frame is a state here, not a screen.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { MapContainer, TileLayer, CircleMarker, useMap } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import { colors } from '../../theme/tokens';
import { getHotspotsGeo, type HotspotGeo, type HotspotsGeoResponse } from '../../api/member';
import { Button, Chip, MethodNote, Skeleton, ErrorState, money, hourLabel, radii } from '../ui';

// Same view the standalone map opens on — the whole of South Africa.
const SA_CENTER: [number, number] = [-28.5, 24.5];
const SA_ZOOM = 6;

const DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

/** Imperatively fly to a selected suburb without remounting the map. */
function FlyTo({ target }: { target: HotspotGeo | null }) {
  const map = useMap();
  useEffect(() => {
    if (target) map.flyTo([target.lat, target.lng], 12, { duration: 0.7 });
  }, [target, map]);
  return null;
}

export default function HotspotMap() {
  const [data, setData] = useState<HotspotsGeoResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<HotspotGeo | null>(null);

  // Filters. hour is null = "any hour" rather than defaulting to now: defaulting
  // silently hides ~95% of suburbs (each has exactly one peak hour on record)
  // and the map looks broken.
  const [hour, setHour] = useState<number | null>(null);
  const [day, setDay] = useState<string | null>(null);
  const [peril, setPeril] = useState<string | null>(null);
  const [minSeverity, setMinSeverity] = useState(0.3);

  const reqId = useRef(0);

  useEffect(() => {
    const id = ++reqId.current;
    setLoading(true);
    setError(null);
    getHotspotsGeo({
      hour: hour ?? undefined,
      day: day ?? undefined,
      peril: peril ?? undefined,
      minSeverity,
    })
      .then((res) => {
        if (id !== reqId.current) return; // a newer filter change already won
        setData(res);
        setSelected((prev) => (prev && res.hotspots.some((h) => h.hex_id === prev.hex_id) ? prev : null));
      })
      .catch((e: Error) => { if (id === reqId.current) setError(e.message); })
      .finally(() => { if (id === reqId.current) setLoading(false); });
  }, [hour, day, peril, minSeverity]);

  // Peril chips are derived from what actually came back, not a hardcoded list —
  // the claim types in the Discovery export are what they are.
  const perils = useMemo(() => {
    const seen = new Map<string, number>();
    for (const h of data?.hotspots ?? []) {
      if (h.top_claim_type) seen.set(h.top_claim_type, (seen.get(h.top_claim_type) ?? 0) + 1);
    }
    return [...seen.entries()].sort((a, b) => b[1] - a[1]).slice(0, 5).map(([k]) => k);
  }, [data]);

  const hotspots = data?.hotspots ?? [];

  return (
    <div style={{ position: 'relative', height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* ---- filter bar ---- */}
      <div style={{ padding: '6px 16px 12px', background: colors.bg50, borderBottom: `1px solid ${colors.lineLight}`, flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 10 }}>
          <h1 style={{ margin: 0, fontSize: 21, fontWeight: 700, letterSpacing: -0.4 }}>Risk map</h1>
          <span className="tabular-nums" style={{ fontSize: 11.5, color: colors.inkLo }}>
            {loading ? 'loading…' : `${hotspots.length} suburbs`}
          </span>
        </div>

        <div style={{ display: 'flex', gap: 6, overflowX: 'auto', paddingBottom: 8, scrollbarWidth: 'none' }}>
          <FilterPill active={day === null && peril === null && hour === null} onClick={() => { setDay(null); setPeril(null); setHour(null); }}>All</FilterPill>
          {DAYS.map((d) => (
            <FilterPill key={d} active={day === d} onClick={() => setDay(day === d ? null : d)}>{d.slice(0, 3)}</FilterPill>
          ))}
          {perils.map((p) => (
            <FilterPill key={p} active={peril === p} onClick={() => setPeril(peril === p ? null : p)}>{p}</FilterPill>
          ))}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <label style={{ fontSize: 11, color: colors.inkMid, whiteSpace: 'nowrap' }}>Min severity</label>
          <input
            type="range" min={0} max={0.9} step={0.05} value={minSeverity}
            onChange={(e) => setMinSeverity(Number(e.target.value))}
            style={{ flex: 1, accentColor: colors.discovery, height: 24 }}
          />
          <span className="tabular-nums" style={{ fontSize: 12, fontWeight: 650, minWidth: 30 }}>{minSeverity.toFixed(2)}</span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 6 }}>
          <label style={{ fontSize: 11, color: colors.inkMid, whiteSpace: 'nowrap' }}>Peak hour</label>
          <input
            type="range" min={-1} max={23} step={1} value={hour ?? -1}
            onChange={(e) => { const v = Number(e.target.value); setHour(v < 0 ? null : v); }}
            style={{ flex: 1, accentColor: colors.discovery, height: 24 }}
          />
          <span className="tabular-nums" style={{ fontSize: 12, fontWeight: 650, minWidth: 34 }}>{hour === null ? 'Any' : hourLabel(hour)}</span>
        </div>
      </div>

      {/* ---- map ---- */}
      <div style={{ flex: 1, position: 'relative', minHeight: 0 }}>
        {error ? (
          <div style={{ padding: 16 }}>
            <ErrorState message={error} onRetry={() => setMinSeverity((v) => v)} />
          </div>
        ) : (
          <MapContainer
            center={SA_CENTER} zoom={SA_ZOOM} scrollWheelZoom
            style={{ height: '100%', width: '100%', background: '#e8eef4' }}
            zoomControl={false}
          >
            <TileLayer
              attribution='&copy; OpenStreetMap'
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />
            <FlyTo target={selected} />
            {hotspots.map((h) => (
              <CircleMarker
                key={h.hex_id}
                center={[h.lat, h.lng]}
                // server-computed — see module header
                radius={h.radius}
                pathOptions={{
                  fillColor: h.color,
                  color: selected?.hex_id === h.hex_id ? colors.discovery : '#333',
                  weight: selected?.hex_id === h.hex_id ? 3 : 1,
                  fillOpacity: 0.7,
                }}
                eventHandlers={{ click: () => setSelected(h) }}
              />
            ))}
          </MapContainer>
        )}

        {loading && !data && (
          <div style={{ position: 'absolute', inset: 0, background: colors.bg50, padding: 20, display: 'flex', flexDirection: 'column', gap: 10 }}>
            <Skeleton h={22} w="55%" /><Skeleton h={200} /><Skeleton h={14} /><Skeleton h={14} w="70%" />
          </div>
        )}
      </div>

      {/* ---- bottom sheet: whichever marker was tapped ---- */}
      {selected ? (
        <SuburbSheet h={selected} onClose={() => setSelected(null)} />
      ) : (
        <div style={{ padding: '10px 18px 12px', background: colors.bg0, borderTop: `1px solid ${colors.lineLight}`, flexShrink: 0 }}>
          <p style={{ margin: 0, fontSize: 12.5, color: colors.inkMid }}>Tap a circle to see that suburb's claims history.</p>
          <MethodNote>
            {data
              ? `${data.total_claims_analysed.toLocaleString('en-ZA')} Discovery claims across ${data.count} suburbs. ${data.caveat}`
              : 'Loading claims data…'}
          </MethodNote>
        </div>
      )}
    </div>
  );
}

function FilterPill({ children, active, onClick }: { children: React.ReactNode; active: boolean; onClick: () => void }) {
  return (
    <button onClick={onClick} style={{
      padding: '7px 13px', borderRadius: radii.chip, fontSize: 12, fontWeight: 600, whiteSpace: 'nowrap',
      border: `1px solid ${active ? colors.discovery : colors.lineLight}`,
      background: active ? colors.discovery : colors.bg0,
      color: active ? '#fff' : colors.inkMid, cursor: 'pointer', minHeight: 34,
    }}>{children}</button>
  );
}

function SuburbSheet({ h, onClose }: { h: HotspotGeo; onClose: () => void }) {
  const tone = h.severity_score >= 0.66 ? 'critical' : h.severity_score >= 0.33 ? 'high' : 'watch';
  return (
    <div style={{
      background: colors.bg0, borderTop: `1px solid ${colors.lineLight}`,
      borderTopLeftRadius: radii.sheet, borderTopRightRadius: radii.sheet,
      padding: '10px 18px 14px', boxShadow: '0 -8px 30px rgba(15,23,42,0.1)',
      flexShrink: 0, maxHeight: '46%', overflowY: 'auto',
    }}>
      <div style={{ width: 40, height: 4, borderRadius: 2, background: colors.lineLight, margin: '0 auto 12px' }} />

      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 10 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 19, fontWeight: 700, letterSpacing: -0.3 }}>
            {h.suburb.replace(/\b\w/g, (c) => c.toUpperCase())}
          </h2>
          <div style={{ display: 'flex', gap: 6, marginTop: 7, flexWrap: 'wrap' }}>
            <Chip tone={tone}>Severity {h.severity_score.toFixed(2)}</Chip>
            {h.incident_count != null && <Chip>{h.incident_count} claims</Chip>}
            <Chip tone="brand">Peaks {hourLabel(h.peak_hour)}</Chip>
          </div>
        </div>
        <button onClick={onClose} aria-label="Close" style={{
          background: 'transparent', border: 'none', fontSize: 22, lineHeight: 1,
          color: colors.inkLo, cursor: 'pointer', padding: '0 4px', minHeight: 44,
        }}>×</button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginTop: 14 }}>
        <Stat label="Most common" value={h.top_claim_type ?? '—'} />
        <Stat label="Busiest day" value={h.peak_day_of_week ?? '—'} />
        <Stat label="Total claimed" value={money(h.total_claim_cost)} />
        <Stat label="Average claim" value={money(h.avg_claim_cost)} />
      </div>

      <MethodNote>
        Suburb-level history from Discovery claims. One geocoded point per suburb — not street-level.
      </MethodNote>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ background: colors.bg50, borderRadius: radii.control, padding: '10px 12px' }}>
      <div style={{ fontSize: 10.5, textTransform: 'uppercase', letterSpacing: 0.5, color: colors.inkLo, fontWeight: 600 }}>{label}</div>
      <div className="tabular-nums" style={{ fontSize: 15, fontWeight: 700, marginTop: 3 }}>{value}</div>
    </div>
  );
}
