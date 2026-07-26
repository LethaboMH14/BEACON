/**
 * Ported from design/exports/design_handoff_beacon/screens/Community Operations Centre.dc.html
 * (design/exports/design_handoff_beacon/README.md §1). The .dc.html export is a proprietary
 * design-tool template, not portable code — this is a from-scratch rebuild against real
 * dashboard/app/src/api/* endpoints, following the porting checklist in dashboard/app/README.md.
 *
 * Real data: cameras (GET /v1/cameras), hotspots/risk (GET /v1/hotspots, GET /v1/risk),
 * live feed seed+stream (GET /v1/events/since + /ws/ops), entity verify (POST /v1/entities/{id}/verify).
 *
 * No backing endpoint exists yet for patrol routes or a named suburb forecast list — those
 * panels are explicitly labelled SIMULATED / "no live data" rather than faked as real (design
 * system rule 5, design/exports/design_handoff_beacon/README.md §"Non-negotiable product rules").
 */
import { useEffect, useRef, useState } from 'react';
import { colors, riskColor, type RiskLevel } from '../theme/tokens';
import {
  getCameras, getHotspots, getEventsSince,
  type CameraStatusEntry, type HotspotEntry, type EventEntry,
} from '../api/client';
import { OpsSocket, type OpsEvent } from '../api/ws';
import { apiUrl } from '../api/base';

const NAV_ITEMS = ['Overview', 'Live Camera', 'Intelligence', 'Patrol', 'Investigations', 'Claims'];
const GRID_COLS = 16;
const GRID_ROWS = 9;

function hashToCell(key: string, cols: number, rows: number): { col: number; row: number } {
  let h = 0;
  for (let i = 0; i < key.length; i++) h = (h * 31 + key.charCodeAt(i)) >>> 0;
  return { col: h % cols, row: Math.floor(h / cols) % rows };
}

function riskLevelFor(score: number): RiskLevel {
  if (score >= 0.75) return 'critical';
  if (score >= 0.5) return 'high';
  if (score >= 0.25) return 'watch';
  return 'safe';
}

function relativeTime(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const s = Math.max(0, Math.floor(ms / 1000));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  return `${Math.floor(s / 3600)}h ago`;
}

const HEX_CLIP = 'polygon(25% 0%, 75% 0%, 100% 50%, 75% 100%, 25% 100%, 0% 50%)';

export default function CommunityOperationsCentre() {
  const [cameras, setCameras] = useState<CameraStatusEntry[]>([]);
  const [currentHour] = useState(() => new Date().getUTCHours());
  const [selectedHour, setSelectedHour] = useState(currentHour);
  const [hotspots, setHotspots] = useState<HotspotEntry[]>([]);
  const [hourlyAvg, setHourlyAvg] = useState<number[]>([]); // 24 real avg risk scores
  const [feed, setFeed] = useState<EventEntry[]>([]);
  const [layers, setLayers] = useState({ forecast: true, cameras: true, patrolRoutes: false });
  const [operatorId, setOperatorId] = useState(() => localStorage.getItem('beacon_operator_id') ?? '');
  const [operatorToken, setOperatorToken] = useState(() => localStorage.getItem('beacon_operator_token') ?? '');
  const socketRef = useRef<OpsSocket | null>(null);

  useEffect(() => {
    let cancelled = false;
    getCameras().then((r) => !cancelled && setCameras(r.cameras)).catch(() => {});
    const id = setInterval(() => getCameras().then((r) => !cancelled && setCameras(r.cameras)).catch(() => {}), 15000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  useEffect(() => {
    let cancelled = false;
    getHotspots(selectedHour, 40).then((r) => !cancelled && setHotspots(r.hotspots)).catch(() => {});
    return () => { cancelled = true; };
  }, [selectedHour]);

  // Real 24-bar time scrubber: average risk_score across top hotspots per hour.
  useEffect(() => {
    let cancelled = false;
    Promise.all(
      Array.from({ length: 24 }, (_, h) => getHotspots(h, 10).catch(() => null))
    ).then((results) => {
      if (cancelled) return;
      setHourlyAvg(results.map((r) => {
        if (!r || r.hotspots.length === 0) return 0;
        return r.hotspots.reduce((sum, h) => sum + h.risk_score, 0) / r.hotspots.length;
      }));
    });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    const since = new Date(Date.now() - 24 * 3600 * 1000).toISOString();
    getEventsSince(since, 100).then((r) => setFeed(r.events.slice().reverse())).catch(() => {});

    const socket = new OpsSocket();
    socketRef.current = socket;
    const unsub = socket.on((ev: OpsEvent) => {
      if (ev.event === 'sighting.new' || ev.event === 'entity.candidate' || ev.event === 'alert.new') {
        setFeed((prev) => [{ event: ev.event, ts: new Date().toISOString(), data: ev.data as Record<string, unknown> }, ...prev].slice(0, 100));
      }
    });
    socket.connect();
    return () => { unsub(); socket.close(); };
  }, []);

  const camerasOnline = cameras.filter((c) => c.online).length;
  const camerasOffline = cameras.length - camerasOnline;

  const activeAlerts = feed.filter((e) => e.event === 'alert.new').length;
  const awaitingVerification = feed.filter((e) => e.event === 'entity.candidate').length;

  async function handleVerify(entityId: string, action: 'flag' | 'dismiss' | 'whitelist') {
    if (!operatorId || !operatorToken) {
      alert('Set an operator ID + token above first (server/src/auth/operators.py OPERATOR_TOKENS).');
      return;
    }
    localStorage.setItem('beacon_operator_id', operatorId);
    localStorage.setItem('beacon_operator_token', operatorToken);
    try {
      await fetch(apiUrl(`/v1/entities/${encodeURIComponent(entityId)}/verify`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Operator-Token': operatorToken },
        body: JSON.stringify({ operator_id: operatorId, action }),
      }).then((res) => { if (!res.ok) throw new Error(`${res.status} ${res.statusText}`); });
    } catch (e) {
      alert(`Verify failed: ${(e as Error).message}`);
    }
  }

  return (
    <div style={{ minWidth: 1360, height: '100vh', background: colors.bg900, color: colors.textHi, fontFamily: 'Inter, system-ui, sans-serif', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      {/* TOP BAR */}
      <div style={{ height: 60, flex: '0 0 60px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 20px', borderBottom: `1px solid ${colors.lineDark}` }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
          <span style={{ fontWeight: 700, fontSize: 15, letterSpacing: '0.02em' }}>BEACON</span>
          <span style={{ fontSize: 11, color: colors.textLo }}>by Discovery</span>
        </div>
        <div style={{ display: 'flex', gap: 4 }}>
          {NAV_ITEMS.map((item, i) => (
            <div key={item} style={{
              padding: '8px 14px', borderRadius: 999, fontSize: 13,
              background: i === 0 ? colors.beaconGrad : 'transparent',
              color: i === 0 ? colors.bg900 : colors.textMid,
              fontWeight: i === 0 ? 600 : 400,
            }}>{item}</div>
          ))}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16, fontSize: 12 }}>
          <span style={{ fontVariantNumeric: 'tabular-nums', color: colors.textMid }}>
            {new Date().toISOString().slice(11, 16)} UTC
          </span>
          <span style={{ color: colors.safe }}>{camerasOnline} online</span>
          <span style={{ color: colors.textLo }}>{camerasOffline} offline</span>
          <input
            placeholder="operator id" value={operatorId} onChange={(e) => setOperatorId(e.target.value)}
            style={{ width: 90, background: colors.bg700, border: `1px solid ${colors.lineDark}`, borderRadius: 6, color: colors.textHi, fontSize: 11, padding: '4px 6px' }}
          />
          <input
            placeholder="token" type="password" value={operatorToken} onChange={(e) => setOperatorToken(e.target.value)}
            style={{ width: 80, background: colors.bg700, border: `1px solid ${colors.lineDark}`, borderRadius: 6, color: colors.textHi, fontSize: 11, padding: '4px 6px' }}
          />
        </div>
      </div>

      {/* BODY */}
      <div style={{ flex: 1, display: 'flex', gap: 14, padding: 14, minHeight: 0 }}>
        {/* LEFT: MAP */}
        <div style={{ flex: '1 1 55%', position: 'relative', background: colors.bg800, borderRadius: 16, border: `1px solid ${colors.lineDark}`, overflow: 'hidden', boxShadow: colors.shadowCardDark }}>
          <div style={{ position: 'absolute', inset: 0, display: 'grid', gridTemplateColumns: `repeat(${GRID_COLS}, 1fr)`, gridTemplateRows: `repeat(${GRID_ROWS}, 1fr)`, padding: 12, gap: 2 }}>
            {Array.from({ length: GRID_COLS * GRID_ROWS }, (_, i) => {
              const col = i % GRID_COLS;
              const row = Math.floor(i / GRID_COLS);
              const scored = hotspots.find((h) => {
                const c = hashToCell(h.hex_id, GRID_COLS, GRID_ROWS);
                return c.col === col && c.row === row;
              });
              return (
                <div key={i} title={scored ? `${scored.hex_id} — ${scored.label} (${(scored.risk_score * 100).toFixed(0)}%)` : 'no risk score'} style={{
                  clipPath: HEX_CLIP,
                  background: scored ? riskColor[riskLevelFor(scored.risk_score)] : colors.bg700,
                  opacity: scored ? 0.55 : 0.25,
                }} />
              );
            })}
          </div>

          {/* camera pins */}
          {layers.cameras && cameras.map((cam) => {
            const cell = hashToCell(cam.hex_id ?? cam.id, GRID_COLS, GRID_ROWS);
            return (
              <div key={cam.id} title={`${cam.name} — ${cam.online ? 'online' : 'offline'}`} style={{
                position: 'absolute',
                left: `${((cell.col + 0.5) / GRID_COLS) * 100}%`,
                top: `${((cell.row + 0.5) / GRID_ROWS) * 100}%`,
                width: 8, height: 8, borderRadius: '50%', transform: 'translate(-50%, -50%)',
                background: cam.online ? colors.safe : colors.textLo,
                boxShadow: cam.online ? `0 0 6px ${colors.safe}` : 'none',
              }} />
            );
          })}

          {/* patrol routes — no backing endpoint: honest SIMULATED placeholder, not real data */}
          {layers.patrolRoutes && (
            <div style={{ position: 'absolute', top: 12, right: 12, background: colors.bg700, border: `1px solid ${colors.lineDark}`, borderRadius: 8, padding: '4px 8px', fontSize: 10, color: colors.watch }}>
              SIMULATED — no live patrol-route endpoint yet
            </div>
          )}

          {/* layer toggles */}
          <div style={{ position: 'absolute', top: 16, left: 16, background: colors.bg800, border: `1px solid ${colors.lineDark}`, borderRadius: 12, padding: 12, fontSize: 12 }}>
            <div style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.06em', color: colors.textLo, marginBottom: 8 }}>Map layers</div>
            {([
              ['cameras', 'Cameras'],
              ['forecast', 'Forecast'],
              ['patrolRoutes', 'Patrol routes (sim)'],
            ] as const).map(([key, label]) => (
              <label key={key} style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4, cursor: 'pointer' }}>
                <input type="checkbox" checked={layers[key]} onChange={(e) => setLayers((l) => ({ ...l, [key]: e.target.checked }))} />
                {label}
              </label>
            ))}
          </div>

          {/* risk legend */}
          <div style={{ position: 'absolute', top: 16, right: 12, display: 'flex', gap: 8, background: colors.bg800, border: `1px solid ${colors.lineDark}`, borderRadius: 8, padding: '6px 10px', fontSize: 10 }}>
            {(['safe', 'watch', 'high', 'critical'] as RiskLevel[]).map((lvl) => (
              <span key={lvl} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <span style={{ width: 8, height: 8, borderRadius: '50%', background: riskColor[lvl], display: 'inline-block' }} />
                {lvl}
              </span>
            ))}
          </div>

          {/* time scrubber — real avg hotspot risk per hour */}
          <div style={{ position: 'absolute', bottom: 12, left: 12, right: 12, background: colors.bg800, border: `1px solid ${colors.lineDark}`, borderRadius: 10, padding: 10 }}>
            <div style={{ display: 'flex', alignItems: 'flex-end', gap: 3, height: 40 }}>
              {(hourlyAvg.length ? hourlyAvg : Array(24).fill(0)).map((v, h) => (
                <div key={h} onClick={() => setSelectedHour(h)} title={`${h}:00 — avg risk ${(v * 100).toFixed(0)}%`} style={{
                  flex: 1, height: `${Math.max(4, v * 100)}%`, cursor: 'pointer', borderRadius: 2,
                  background: h === selectedHour ? colors.beacon : h === 0 ? colors.critical : colors.bg700,
                }} />
              ))}
            </div>
            <div style={{ fontSize: 10, color: colors.textLo, marginTop: 6 }}>
              Hour {selectedHour}:00 UTC — bars are real avg hotspot risk_score from GET /v1/hotspots per hour
            </div>
          </div>
        </div>

        {/* RIGHT COLUMN */}
        <div style={{ flex: '1 1 45%', display: 'flex', flexDirection: 'column', gap: 14, minHeight: 0 }}>
          {/* LIVE FEED */}
          <div style={{ flex: '1 1 60%', background: colors.bg50, borderRadius: 16, padding: 14, overflowY: 'auto', color: colors.inkHi, boxShadow: colors.shadowCard }}>
            <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 10 }}>Live feed</div>
            {feed.length === 0 && <div style={{ fontSize: 12, color: colors.inkLo }}>No events in the last 24h.</div>}
            {feed.map((ev, i) => {
              const d = ev.data as Record<string, unknown>;
              const entityId = (d.entity_id ?? d.id) as string | undefined;
              const confidence = typeof d.confidence === 'number' ? d.confidence : typeof d.base_score === 'number' ? d.base_score : null;
              return (
                <div key={`${ev.ts}-${i}`} style={{ border: `1px solid ${colors.lineLight}`, borderRadius: 10, padding: 10, marginBottom: 8 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
                    <span style={{ fontWeight: 600 }}>{ev.event}</span>
                    <span style={{ color: colors.inkLo }}>{relativeTime(ev.ts)}</span>
                  </div>
                  <div style={{ fontSize: 11, color: colors.inkMid, marginTop: 4 }}>
                    {String(d.hex_id ?? d.camera_id ?? entityId ?? '')} {d.kind ? `· ${d.kind}` : ''}
                  </div>
                  {confidence !== null && (
                    <div style={{ marginTop: 6 }}>
                      <div style={{ fontSize: 11, color: colors.inkMid }}>{(confidence * 100).toFixed(0)}% confidence</div>
                      <div style={{ height: 4, background: colors.lineLight, borderRadius: 2, marginTop: 2 }}>
                        <div style={{ width: `${confidence * 100}%`, height: '100%', background: colors.discovery, borderRadius: 2 }} />
                      </div>
                    </div>
                  )}
                  {ev.event === 'entity.candidate' && entityId && (
                    <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                      <button onClick={() => handleVerify(entityId, 'flag')} style={{ background: colors.beaconGrad, border: 'none', borderRadius: 999, padding: '6px 14px', fontSize: 12, fontWeight: 600, cursor: 'pointer', boxShadow: colors.shadowCard }}>Verify</button>
                      <button onClick={() => handleVerify(entityId, 'dismiss')} style={{ background: 'transparent', border: `1px solid ${colors.lineLight}`, borderRadius: 999, padding: '6px 14px', fontSize: 12, cursor: 'pointer' }}>Dismiss</button>
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* STATS + FORECAST */}
          <div style={{ flex: '1 1 40%', display: 'flex', flexDirection: 'column', gap: 10, minHeight: 0 }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8 }}>
              {[
                ['Active alerts', activeAlerts],
                ['Awaiting verification', awaitingVerification],
                ['Units deployed', '—'],
              ].map(([label, value]) => (
                <div key={label as string} style={{ background: colors.bg800, border: `1px solid ${colors.lineDark}`, borderRadius: 14, padding: 10, boxShadow: colors.shadowCardDark }}>
                  <div style={{ fontSize: 20, fontVariantNumeric: 'tabular-nums', fontWeight: 700 }}>{value}</div>
                  <div style={{ fontSize: 10, color: colors.textLo, textTransform: 'uppercase', letterSpacing: '0.06em' }}>{label}</div>
                  {label === 'Units deployed' && <div style={{ fontSize: 9, color: colors.watch, marginTop: 2 }}>no patrol endpoint yet</div>}
                </div>
              ))}
            </div>

            <div style={{ flex: 1, background: colors.bg800, border: `1px solid ${colors.lineDark}`, borderRadius: 14, padding: 12, overflowY: 'auto', boxShadow: colors.shadowCardDark }}>
              <div style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: '0.06em', color: colors.textLo, marginBottom: 8 }}>
                This hour's top hexes
              </div>
              <div style={{ fontSize: 10, color: colors.textLo, marginBottom: 6 }}>
                Real GET /v1/hotspots ranking — hex IDs shown, no suburb-name mapping table exists yet.
              </div>
              {hotspots.slice(0, 5).map((h) => (
                <div key={h.hex_id} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, padding: '6px 0', borderBottom: `1px solid ${colors.lineDark}` }}>
                  <span style={{ fontFamily: 'monospace', fontSize: 11 }}>{h.hex_id}</span>
                  <span style={{ color: riskColor[riskLevelFor(h.risk_score)], fontVariantNumeric: 'tabular-nums' }}>{(h.risk_score * 100).toFixed(0)}%</span>
                </div>
              ))}
              {hotspots.length === 0 && <div style={{ fontSize: 12, color: colors.textLo }}>No scored hexes for this hour.</div>}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
