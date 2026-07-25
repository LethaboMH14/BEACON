/**
 * Ported from design/exports/design_handoff_beacon/screens/Live AI Camera.dc.html
 * (design/exports/design_handoff_beacon/README.md §3). The .dc.html export is a proprietary
 * design-tool template, not portable code — this is a from-scratch rebuild against real
 * dashboard/app/src/api/* endpoints, following the same porting pattern as the Ops Centre
 * and Verify Queue screens.
 *
 * Real data: camera roster + online status (GET /v1/cameras), per-camera detection feed with
 * bounding boxes, modality and plate reads (GET /v1/sightings — added in ADR-0006), fused
 * entity assessment for a selected detection's entity (GET /v1/entities/{id} — real factors
 * F1-F6, calibrated current_score, state), "Open verify queue" hands off to the real Verify
 * Queue screen.
 *
 * This screen previously carried three "no backing endpoint" placeholders for bbox overlay,
 * plate OCR and modality. Sighting rows had always stored those fields on POST, but no GET
 * route returned them. GET /v1/sightings now does, so all three draw real data.
 *
 * REMAINING HONEST GAP: the API returns bbox in source-frame pixels but does not record the
 * frame dimensions they were measured in, so the overlay has to assume SOURCE_FRAME below.
 * Boxes from a camera of a different resolution will be misplaced. Fixing it properly means
 * storing frame width/height per sighting, not guessing harder here.
 */
import { useEffect, useMemo, useState } from 'react';
import { colors } from '../theme/tokens';
import {
  getCameras, getSightings, getEntity,
  type CameraStatusEntry, type SightingDetail, type EntityDetail,
} from '../api/client';

function relativeTime(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const s = Math.max(0, Math.floor(ms / 1000));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  return `${Math.floor(s / 3600)}h ago`;
}

const STRIPE = 'repeating-linear-gradient(45deg, #182130, #182130 8px, #101725 8px, #101725 16px)';

/**
 * Assumed source-frame size for scaling bboxes into the lens viewport.
 * The API returns pixel coordinates without the dimensions they were measured
 * against — see the file header. 1920x1080 matches what scripts/vision_lens_demo.py
 * feeds the detectors; a camera at another resolution will render boxes offset.
 */
const SOURCE_FRAME = { w: 1920, h: 1080 };

/** Detections from one moment are shown together as a "frame". */
const FRAME_GROUP_MS = 2500;

const MODALITY_COLOR: Record<string, string> = {
  yolo: colors.critical,
  face: colors.beacon,
  plate: colors.discovery,
  audio: colors.watch,
};

function modalityColor(modality: string): string {
  return MODALITY_COLOR[modality] ?? colors.textMid;
}

function detectionLabel(s: SightingDetail): string {
  if (s.modality === 'plate') return s.plate_text ? `PLATE ${s.plate_text}` : 'PLATE (unreadable)';
  if (s.modality === 'face') return s.entity_id ? 'FACE (matched)' : 'FACE';
  if (s.kind === 'weapon') return 'WEAPON';
  return s.kind.toUpperCase();
}

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
  const [feed, setFeed] = useState<SightingDetail[]>([]);
  const [selectedFrameTs, setSelectedFrameTs] = useState<string | null>(null);
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
    setSelectedFrameTs(null); // a pinned frame belongs to the camera it came from
    let cancelled = false;
    function poll() {
      getSightings({ cameraId: selectedCameraId!, limit: 100 })
        .then((rows) => { if (!cancelled) setFeed(rows); })
        .catch(() => {});
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

  /**
   * Detections arrive as independent rows, one per box, but the three detectors
   * are run over the same sampled frames — so rows within FRAME_GROUP_MS of each
   * other describe one moment and belong on one overlay together.
   */
  const frames = useMemo(() => {
    const groups: { ts: string; items: SightingDetail[] }[] = [];
    for (const s of feed) {
      const t = new Date(s.ts).getTime();
      const last = groups[groups.length - 1];
      if (last && Math.abs(new Date(last.ts).getTime() - t) <= FRAME_GROUP_MS) {
        last.items.push(s);
      } else {
        groups.push({ ts: s.ts, items: [s] });
      }
    }
    return groups;
  }, [feed]);

  const activeFrame = frames.find((f) => f.ts === selectedFrameTs) ?? frames[0] ?? null;
  const latestFilmstrip = frames.slice(0, 6);
  // Readable reads first — they're the actionable ones — but unreadable boxes stay
  // in the list rather than being filtered out, so the panel doesn't imply OCR
  // succeeds more often than it does.
  const plateReads = feed
    .filter((s) => s.modality === 'plate')
    .slice()
    .sort((a, b) => Number(Boolean(b.plate_text)) - Number(Boolean(a.plate_text)));
  const audioSightings = feed.filter((s) => s.modality === 'audio');

  return (
    <div style={{ minWidth: 1360, height: '100vh', background: colors.bg900, color: colors.textHi, fontFamily: 'Inter, system-ui, sans-serif', padding: 14, display: 'flex', gap: 14, overflow: 'hidden' }}>
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

          {/* detection boxes — real bbox from GET /v1/sightings, scaled by SOURCE_FRAME */}
          {activeFrame?.items.filter((s) => s.bbox).map((s) => {
            const b = s.bbox!;
            const c = modalityColor(s.modality);
            return (
              <div
                key={s.id}
                onClick={() => s.entity_id && setSelectedEntityId(s.entity_id)}
                style={{
                  position: 'absolute',
                  left: `${((b.x - b.w / 2) / SOURCE_FRAME.w) * 100}%`,
                  top: `${((b.y - b.h / 2) / SOURCE_FRAME.h) * 100}%`,
                  width: `${(b.w / SOURCE_FRAME.w) * 100}%`,
                  height: `${(b.h / SOURCE_FRAME.h) * 100}%`,
                  border: `2px solid ${c}`,
                  borderRadius: 3,
                  boxShadow: `0 0 10px ${c}55`,
                  cursor: s.entity_id ? 'pointer' : 'default',
                }}
              >
                <div style={{
                  position: 'absolute', bottom: '100%', left: -2, whiteSpace: 'nowrap',
                  background: c, color: colors.bg900, fontSize: 9, fontWeight: 700,
                  letterSpacing: '0.04em', padding: '1px 4px', borderRadius: '3px 3px 0 0',
                }}>
                  {detectionLabel(s)} {(s.confidence * 100).toFixed(0)}%
                </div>
              </div>
            );
          })}

          <div style={{ position: 'absolute', top: 16, right: 16, fontSize: 10, color: colors.textMid, background: 'rgba(10,15,26,0.8)', border: `1px solid ${colors.lineDark}`, borderRadius: 8, padding: '6px 10px', maxWidth: 230, textAlign: 'right' }}>
            {activeFrame
              ? <>Boxes: {activeFrame.items.filter((s) => s.bbox).length} at {relativeTime(activeFrame.ts)}<div style={{ color: colors.watch, marginTop: 3 }}>No video frame stored — boxes are drawn over the placeholder at an assumed {SOURCE_FRAME.w}×{SOURCE_FRAME.h} source.</div></>
              : 'No detections to overlay.'}
          </div>
        </div>

        {/* filmstrip — real recent sightings for this camera */}
        <div style={{ display: 'flex', gap: 6 }}>
          {latestFilmstrip.length === 0 && <div style={{ fontSize: 11, color: colors.textLo }}>No sightings recorded for this camera.</div>}
          {latestFilmstrip.map((f) => (
            <div
              key={f.ts}
              onClick={() => setSelectedFrameTs(f.ts)}
              title={`${f.items.map(detectionLabel).join(', ')} · ${relativeTime(f.ts)}`}
              style={{
                position: 'relative', width: 72, height: 48, borderRadius: 6, background: STRIPE,
                border: f.ts === activeFrame?.ts ? `2px solid ${colors.beacon}` : `1px solid ${colors.lineDark}`,
                flexShrink: 0, cursor: 'pointer', overflow: 'hidden',
              }}
            >
              {/* thumbnail of where the boxes fell in the frame */}
              {f.items.filter((s) => s.bbox).map((s) => {
                const b = s.bbox!;
                return (
                  <div key={s.id} style={{
                    position: 'absolute',
                    left: `${((b.x - b.w / 2) / SOURCE_FRAME.w) * 100}%`,
                    top: `${((b.y - b.h / 2) / SOURCE_FRAME.h) * 100}%`,
                    width: `${(b.w / SOURCE_FRAME.w) * 100}%`,
                    height: `${(b.h / SOURCE_FRAME.h) * 100}%`,
                    minWidth: 3, minHeight: 3,
                    border: `1px solid ${modalityColor(s.modality)}`,
                  }} />
                );
              })}
              <div style={{ position: 'absolute', bottom: 1, right: 3, fontSize: 8, color: colors.textLo }}>{relativeTime(f.ts)}</div>
            </div>
          ))}
        </div>
      </div>

      {/* RIGHT: stacked panels */}
      <div style={{ flex: '1 1 35%', display: 'flex', flexDirection: 'column', gap: 12, overflowY: 'auto' }}>
        <div style={{ background: colors.bg50, color: colors.inkHi, borderRadius: 12, padding: 14 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6 }}>Plate recognition</div>
          {plateReads.length === 0 && (
            <div style={{ fontSize: 11, color: colors.inkLo }}>
              No plate sightings for this camera.
            </div>
          )}
          <div style={{ display: 'grid', gap: 6 }}>
            {plateReads.slice(0, 4).map((s) => (
              <div key={s.id} onClick={() => s.entity_id && setSelectedEntityId(s.entity_id)} style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                border: `1px solid ${colors.lineLight}`, borderRadius: 8, padding: '6px 10px',
                cursor: s.entity_id ? 'pointer' : 'default',
                background: s.entity_id && s.entity_id === selectedEntityId ? colors.discoverySoft : 'transparent',
              }}>
                <span style={{
                  fontFamily: 'ui-monospace, monospace', fontSize: s.plate_text ? 15 : 11,
                  fontWeight: s.plate_text ? 700 : 400, letterSpacing: s.plate_text ? '0.08em' : 0,
                  color: s.plate_text ? undefined : colors.inkLo,
                }}>
                  {/* A plate box with no text is a real detection whose OCR failed the
                      plausibility filter. Showing the box and admitting the read failed is
                      honest; hiding the row would overstate how often OCR works. */}
                  {s.plate_text ?? 'plate detected · unreadable'}
                </span>
                <span style={{ fontSize: 10, color: colors.inkLo, textAlign: 'right' }}>
                  {relativeTime(s.ts)}
                  {s.plate_quality !== null && <> · q {(s.plate_quality * 100).toFixed(0)}%</>}
                </span>
              </div>
            ))}
          </div>
          {plateReads.length > 0 && (
            <div style={{ fontSize: 10, color: colors.inkLo, marginTop: 8 }}>
              A read is a lead, not an identification — plate text is syntactically plausible, never verified
              against a registration database.
            </div>
          )}
        </div>

        <div style={{ background: colors.bg50, color: colors.inkHi, borderRadius: 12, padding: 14, flex: '0 1 auto' }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>Detections this frame</div>
          <div style={{ fontSize: 10, color: colors.inkLo, marginBottom: 8 }}>
            {activeFrame
              ? <>Frame at {relativeTime(activeFrame.ts)} on {camera?.name ?? 'this camera'} — click a filmstrip cell to pin another.</>
              : <>Real sightings for {camera?.name ?? 'this camera'} via GET /v1/sightings.</>}
          </div>
          {!activeFrame && <div style={{ fontSize: 12, color: colors.inkLo }}>No detections yet.</div>}
          <div style={{ display: 'grid', gap: 6, maxHeight: 180, overflowY: 'auto' }}>
            {activeFrame?.items.map((s) => (
              <div key={s.id} onClick={() => s.entity_id && setSelectedEntityId(s.entity_id)} style={{
                display: 'flex', justifyContent: 'space-between', gap: 8, fontSize: 12, padding: '6px 8px',
                borderRadius: 8, cursor: s.entity_id ? 'pointer' : 'default',
                background: s.entity_id && s.entity_id === selectedEntityId ? colors.discoverySoft : 'transparent',
                border: `1px solid ${colors.lineLight}`, borderLeft: `3px solid ${modalityColor(s.modality)}`,
              }}>
                <span>
                  {detectionLabel(s)}
                  {s.entity_id && <span style={{ color: colors.inkLo }}> · {s.entity_id.slice(0, 12)}…</span>}
                </span>
                <span style={{ fontVariantNumeric: 'tabular-nums', color: colors.discovery }}>{(s.confidence * 100).toFixed(0)}%</span>
              </div>
            ))}
          </div>
        </div>

        <div style={{ background: colors.bg50, color: colors.inkHi, borderRadius: 12, padding: 14 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6 }}>Audio</div>
          {audioSightings.length === 0 ? (
            <div style={{ fontSize: 11, color: colors.inkLo }}>
              No audio sightings on this camera. GET /v1/sightings can return them (modality="audio"),
              but nothing in the pipeline posts audio yet — the vision analyzer runs image models only.
              This panel stays empty rather than inventing a waveform.
            </div>
          ) : (
            <div style={{ display: 'grid', gap: 6 }}>
              {audioSightings.slice(0, 4).map((s) => (
                <div key={s.id} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
                  <span>{s.kind}</span>
                  <span style={{ color: colors.inkLo }}>{relativeTime(s.ts)} · {(s.confidence * 100).toFixed(0)}%</span>
                </div>
              ))}
            </div>
          )}
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
