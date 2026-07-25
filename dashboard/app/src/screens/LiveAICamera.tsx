/**
 * Ported from design/exports/design_handoff_beacon/screens/Live AI Camera.dc.html
 * (design/exports/design_handoff_beacon/README.md §3). The .dc.html export is a proprietary
 * design-tool template, not portable code — this is a from-scratch rebuild against real
 * dashboard/app/src/api/* endpoints, following the same porting pattern as the Ops Centre
 * and Verify Queue screens.
 *
 * Real data: camera roster + online status (GET /v1/cameras), per-camera detection feed
 * (GET /v1/events/since filtered to sighting.new for this camera_id — no GET /v1/sightings
 * endpoint exists, sightings.py only exposes POST), fused entity assessment for a selected
 * detection's entity (GET /v1/entities/{id} — real factors F1-F6, calibrated current_score,
 * state), "Open verify queue" hands off to the real Verify Queue screen.
 *
 * No backing endpoint exists yet for: detection bounding-box overlay coordinates, plate OCR
 * text/quality, or audio-classification events (Sighting rows store bbox/plate_text/modality
 * on write via POST /v1/sightings, but no GET route in server/src/api/ ever returns those
 * fields back out — only id/camera_id/entity_id/hex_id/kind/confidence/ts survive to
 * GET /v1/events/since). Those three panels say so explicitly instead of inventing bbox
 * coordinates, a plate string, or a waveform (design system rule 5).
 */
import { useEffect, useState } from 'react';
import { colors } from '../theme/tokens';
import {
  getCameras, getEventsSince, getEntity,
  type CameraStatusEntry, type EventEntry, type EntityDetail,
} from '../api/client';

function relativeTime(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const s = Math.max(0, Math.floor(ms / 1000));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  return `${Math.floor(s / 3600)}h ago`;
}

const STRIPE = 'repeating-linear-gradient(45deg, #182130, #182130 8px, #101725 8px, #101725 16px)';

const FACTOR_LABELS: Record<keyof EntityDetail['factors'], string> = {
  recurrence: 'Recurrence (F1)',
  time_anomaly: 'Time anomaly (F2)',
  crime_correlation: 'Crime correlation (F3)',
  casing_behaviour: 'Casing behaviour (F4)',
  territory_roaming: 'Territory roaming (F5)',
  modal_corroboration: 'Modal corroboration (F6)',
};

export default function LiveAICamera({ onOpenVerifyQueue }: { onOpenVerifyQueue: (entityId: string) => void }) {
  const [cameras, setCameras] = useState<CameraStatusEntry[]>([]);
  const [selectedCameraId, setSelectedCameraId] = useState<string | null>(null);
  const [feed, setFeed] = useState<EventEntry[]>([]);
  const [selectedEntityId, setSelectedEntityId] = useState<string | null>(null);
  const [entity, setEntity] = useState<EntityDetail | null>(null);

  useEffect(() => {
    let cancelled = false;
    getCameras().then((r) => {
      if (cancelled) return;
      setCameras(r.cameras);
      setSelectedCameraId((prev) => prev ?? r.cameras[0]?.id ?? null);
    }).catch(() => {});
    const id = setInterval(() => getCameras().then((r) => !cancelled && setCameras(r.cameras)).catch(() => {}), 15000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  useEffect(() => {
    if (!selectedCameraId) return;
    let cancelled = false;
    function poll() {
      const since = new Date(Date.now() - 6 * 3600 * 1000).toISOString();
      getEventsSince(since, 200).then((r) => {
        if (cancelled) return;
        const forCamera = r.events.filter((ev) => ev.event === 'sighting.new' && (ev.data as Record<string, unknown>).camera_id === selectedCameraId);
        setFeed(forCamera.slice().reverse());
      }).catch(() => {});
    }
    poll();
    const id = setInterval(poll, 5000);
    return () => { cancelled = true; clearInterval(id); };
  }, [selectedCameraId]);

  useEffect(() => {
    if (!selectedEntityId) { setEntity(null); return; }
    let cancelled = false;
    getEntity(selectedEntityId).then((e) => !cancelled && setEntity(e)).catch(() => !cancelled && setEntity(null));
    return () => { cancelled = true; };
  }, [selectedEntityId]);

  const camera = cameras.find((c) => c.id === selectedCameraId) ?? null;
  const latestFilmstrip = feed.slice(0, 6);

  return (
    <div style={{ minWidth: 1360, minHeight: '100vh', background: colors.bg900, color: colors.textHi, fontFamily: 'Inter, system-ui, sans-serif', padding: 14, display: 'flex', gap: 14 }}>
      {/* LEFT: camera frame */}
      <div style={{ flex: '1 1 65%', display: 'flex', flexDirection: 'column', gap: 10 }}>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {cameras.map((c) => (
            <button key={c.id} onClick={() => setSelectedCameraId(c.id)} style={{
              background: c.id === selectedCameraId ? colors.beaconGrad : colors.bg800,
              color: c.id === selectedCameraId ? colors.bg900 : colors.textMid,
              border: `1px solid ${colors.lineDark}`, borderRadius: 999, padding: '6px 12px', fontSize: 12, cursor: 'pointer',
            }}>
              {c.name} {c.online ? '●' : '○'}
            </button>
          ))}
          {cameras.length === 0 && <span style={{ fontSize: 12, color: colors.textLo }}>No cameras registered yet (auto-register on first POST /v1/sightings).</span>}
        </div>

        <div style={{ position: 'relative', flex: 1, borderRadius: 12, border: `1px solid ${colors.lineDark}`, background: STRIPE, overflow: 'hidden', minHeight: 420 }}>
          {/* corner brackets */}
          {[
            { top: 12, left: 12, borderTop: true, borderLeft: true },
            { top: 12, right: 12, borderTop: true, borderRight: true },
            { bottom: 12, left: 12, borderBottom: true, borderLeft: true },
            { bottom: 12, right: 12, borderBottom: true, borderRight: true },
          ].map((pos, i) => (
            <div key={i} style={{
              position: 'absolute', width: 24, height: 24, ...pos,
              borderTop: pos.borderTop ? `2px solid ${colors.textLo}` : undefined,
              borderLeft: pos.borderLeft ? `2px solid ${colors.textLo}` : undefined,
              borderBottom: pos.borderBottom ? `2px solid ${colors.textLo}` : undefined,
              borderRight: pos.borderRight ? `2px solid ${colors.textLo}` : undefined,
            }} />
          ))}

          <div style={{ position: 'absolute', top: 16, left: 16, display: 'flex', alignItems: 'center', gap: 8, background: 'rgba(10,15,26,0.7)', borderRadius: 999, padding: '4px 10px' }}>
            <span style={{
              width: 8, height: 8, borderRadius: '50%',
              background: camera?.online ? colors.live : colors.stale,
              boxShadow: camera?.online ? `0 0 6px ${colors.live}` : 'none',
            }} />
            <span style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.06em' }}>{camera?.online ? 'LIVE' : 'OFFLINE'}</span>
          </div>

          <div style={{ position: 'absolute', bottom: 16, left: 16, fontSize: 12, color: colors.textMid, background: 'rgba(10,15,26,0.7)', borderRadius: 8, padding: '6px 10px' }}>
            {camera ? (
              <>
                <div style={{ color: colors.textHi, fontWeight: 600 }}>{camera.name}</div>
                <div>{camera.hex_id ?? 'no hex assigned'} · {camera.last_seen_at ? `last seen ${relativeTime(camera.last_seen_at)}` : 'never seen'}</div>
              </>
            ) : 'No camera selected'}
          </div>

          <div style={{ position: 'absolute', top: 16, right: 16, fontSize: 10, color: colors.watch, background: 'rgba(10,15,26,0.8)', border: `1px solid ${colors.lineDark}`, borderRadius: 8, padding: '6px 10px', maxWidth: 220, textAlign: 'right' }}>
            No detection-box overlay endpoint yet — bbox is captured on POST /v1/sightings but never returned by a GET route.
          </div>
        </div>

        {/* filmstrip — real recent sightings for this camera */}
        <div style={{ display: 'flex', gap: 6 }}>
          {latestFilmstrip.length === 0 && <div style={{ fontSize: 11, color: colors.textLo }}>No sightings for this camera in the last 6h.</div>}
          {latestFilmstrip.map((ev, i) => {
            const d = ev.data as Record<string, unknown>;
            return (
              <div key={`${ev.ts}-${i}`} title={`${d.kind} · ${((d.confidence as number) * 100).toFixed(0)}% · ${relativeTime(ev.ts)}`} style={{
                width: 72, height: 48, borderRadius: 6, background: STRIPE,
                border: i === 0 ? `2px solid ${colors.beacon}` : `1px solid ${colors.lineDark}`,
                flexShrink: 0,
              }} />
            );
          })}
        </div>
      </div>

      {/* RIGHT: stacked panels */}
      <div style={{ flex: '1 1 35%', display: 'flex', flexDirection: 'column', gap: 12, overflowY: 'auto' }}>
        <div style={{ background: colors.bg50, color: colors.inkHi, borderRadius: 12, padding: 14 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6 }}>Plate recognition</div>
          <div style={{ fontSize: 11, color: colors.inkLo }}>
            No live plate/OCR read endpoint — Sighting.plate_text and plate_quality are written on
            POST /v1/sightings but no GET route returns them. Watchlist state (below) is still real,
            driven by the entity's flagged state.
          </div>
        </div>

        <div style={{ background: colors.bg50, color: colors.inkHi, borderRadius: 12, padding: 14, flex: '0 1 auto' }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>Detections this frame</div>
          <div style={{ fontSize: 10, color: colors.inkLo, marginBottom: 8 }}>
            Real sighting.new events for {camera?.name ?? 'this camera'} via GET /v1/events/since. Modality
            (face/plate/yolo/audio) is stored but not exposed by that endpoint yet — only kind + confidence.
          </div>
          {feed.length === 0 && <div style={{ fontSize: 12, color: colors.inkLo }}>No detections yet.</div>}
          <div style={{ display: 'grid', gap: 6, maxHeight: 180, overflowY: 'auto' }}>
            {feed.slice(0, 12).map((ev, i) => {
              const d = ev.data as Record<string, unknown>;
              const eid = d.entity_id as string | undefined;
              return (
                <div key={`${ev.ts}-${i}`} onClick={() => eid && setSelectedEntityId(eid)} style={{
                  display: 'flex', justifyContent: 'space-between', fontSize: 12, padding: '6px 8px',
                  borderRadius: 8, cursor: eid ? 'pointer' : 'default',
                  background: eid && eid === selectedEntityId ? colors.discoverySoft : 'transparent',
                  border: `1px solid ${colors.lineLight}`,
                }}>
                  <span>{String(d.kind)}{eid ? ` · ${eid.slice(0, 12)}…` : ''}</span>
                  <span style={{ fontVariantNumeric: 'tabular-nums', color: colors.discovery }}>{((d.confidence as number) * 100).toFixed(0)}%</span>
                </div>
              );
            })}
          </div>
        </div>

        <div style={{ background: colors.bg50, color: colors.inkHi, borderRadius: 12, padding: 14 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6 }}>Audio</div>
          <div style={{ fontSize: 11, color: colors.inkLo }}>
            No live audio-classification endpoint — audio sightings share the same POST /v1/sightings
            path (modality="audio") but, like plate/bbox above, aren't distinguishable through any GET
            route today.
          </div>
        </div>

        <div style={{ background: colors.bg50, color: colors.inkHi, borderRadius: 12, padding: 14, flex: 1 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>Fused assessment</div>
          {!entity && <div style={{ fontSize: 12, color: colors.inkLo }}>Click a detection above with an entity to see its real calibrated score and factors.</div>}
          {entity && (
            <>
              <div style={{ fontSize: 32, fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}>{(entity.current_score * 100).toFixed(0)}%</div>
              <div style={{ display: 'inline-block', fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em', padding: '3px 8px', borderRadius: 999, background: colors.discoverySoft, color: colors.discovery, marginBottom: 8 }}>
                {entity.state}
              </div>
              <div style={{ display: 'grid', gap: 6, margin: '8px 0' }}>
                {(Object.keys(FACTOR_LABELS) as (keyof EntityDetail['factors'])[])
                  .filter((k) => entity.factors[k] !== null && entity.factors[k] !== undefined)
                  .map((k) => (
                    <div key={k} style={{ fontSize: 11 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', color: colors.inkMid }}>
                        <span>{FACTOR_LABELS[k]}</span>
                        <span>{((entity.factors[k] as number) * 100).toFixed(0)}%</span>
                      </div>
                      <div style={{ height: 4, background: colors.lineLight, borderRadius: 2 }}>
                        <div style={{ width: `${(entity.factors[k] as number) * 100}%`, height: '100%', background: colors.discovery, borderRadius: 2 }} />
                      </div>
                    </div>
                  ))}
              </div>
              <div style={{ fontSize: 11, color: colors.inkLo, marginBottom: 10 }}>
                Machine ceiling reached — human verification required to escalate.
              </div>
              <button onClick={() => onOpenVerifyQueue(entity.id)} style={{
                width: '100%', background: colors.beaconGrad, border: 'none', borderRadius: 10, padding: '10px 0',
                fontSize: 13, fontWeight: 700, cursor: 'pointer',
              }}>
                Open verify queue
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
