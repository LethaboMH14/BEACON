/**
 * A single question, asked plainly: does the plate model actually see number plates
 * on this camera? Not a second detection UI — Live AI Camera already has the full
 * bbox overlay, filmstrip and fused-assessment panel. This is a doorbell-style round
 * lens plus one honest readout, for someone who wants the answer in five seconds.
 *
 * Same real data as LiveAICamera.tsx (GET /v1/cameras, GET /v1/sightings), same
 * SOURCE_FRAME caveat (bbox pixels with no recorded frame size — see that file's
 * header), same refusal to draw a plate string that OCR didn't accept.
 */
import { useEffect, useMemo, useState } from 'react';
import { colors } from '../theme/tokens';
import { getCameras, getSightings, type CameraStatusEntry, type SightingDetail } from '../api/client';

const SOURCE_FRAME = { w: 1920, h: 1080 };
const STRIPE = 'repeating-linear-gradient(45deg, #182130, #182130 8px, #101725 8px, #101725 16px)';

function relativeTime(iso: string): string {
  const s = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  return `${Math.floor(s / 3600)}h ago`;
}

export default function RingCam() {
  const [cameras, setCameras] = useState<CameraStatusEntry[]>([]);
  const [selectedCameraId, setSelectedCameraId] = useState<string | null>(null);
  const [feed, setFeed] = useState<SightingDetail[]>([]);

  useEffect(() => {
    let cancelled = false;
    getCameras().then((r) => {
      if (cancelled) return;
      setCameras(r.cameras);
      setSelectedCameraId((prev) => prev ?? r.cameras[0]?.id ?? null);
    }).catch(() => {});
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!selectedCameraId) return;
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

  const camera = cameras.find((c) => c.id === selectedCameraId) ?? null;

  // Most recent moment that actually had a plate box, so the lens shows the model
  // doing the thing this screen exists to answer about.
  const lastPlateFrame = useMemo(() => {
    const plateSighting = feed.find((s) => s.modality === 'plate' && s.bbox);
    if (!plateSighting) return null;
    const t = new Date(plateSighting.ts).getTime();
    return feed.filter((s) => Math.abs(new Date(s.ts).getTime() - t) <= 2500);
  }, [feed]);

  const shown = lastPlateFrame ?? feed.slice(0, 6);
  const plateSightings = feed.filter((s) => s.modality === 'plate');
  const readable = plateSightings.filter((s) => s.plate_text);
  const latestPlate = plateSightings[0] ?? null;

  const status: { label: string; color: string; detail: string } = plateSightings.length === 0
    ? { label: 'NO PLATES SEEN', color: colors.textLo, detail: 'No plate detection on this camera yet.' }
    : readable.length === 0
      ? { label: 'SEES PLATES, CAN’T READ THEM', color: colors.watch, detail: `${plateSightings.length} plate box${plateSightings.length === 1 ? '' : 'es'} detected, 0 accepted — every read failed the confidence gate (ADR-0007).` }
      : { label: 'READING PLATES', color: colors.safe, detail: `${readable.length} of ${plateSightings.length} plate detections produced an accepted read.` };

  return (
    <div style={{ minWidth: 900, minHeight: '100vh', background: colors.bg900, color: colors.textHi, fontFamily: 'Inter, system-ui, sans-serif', padding: 24, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 18 }}>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', justifyContent: 'center' }}>
        {cameras.map((c) => (
          <button key={c.id} onClick={() => setSelectedCameraId(c.id)} style={{
            background: c.id === selectedCameraId ? colors.beaconGrad : colors.bg800,
            color: c.id === selectedCameraId ? colors.bg900 : colors.textMid,
            border: `1px solid ${colors.lineDark}`, borderRadius: 999, padding: '6px 12px', fontSize: 12, cursor: 'pointer',
          }}>
            {c.name} {c.online ? '●' : '○'}
          </button>
        ))}
        {cameras.length === 0 && <span style={{ fontSize: 12, color: colors.textLo }}>No cameras registered yet.</span>}
      </div>

      {/* the round lens */}
      <div style={{
        position: 'relative', width: 340, height: 340, borderRadius: '50%',
        background: STRIPE, overflow: 'hidden',
        border: `6px solid ${colors.bg700}`,
        boxShadow: `0 0 0 2px ${status.color}, 0 0 40px ${status.color}55`,
      }}>
        <div style={{ position: 'absolute', top: 18, left: '50%', transform: 'translateX(-50%)', display: 'flex', alignItems: 'center', gap: 6, background: 'rgba(10,15,26,0.75)', borderRadius: 999, padding: '3px 10px' }}>
          <span style={{ width: 7, height: 7, borderRadius: '50%', background: camera?.online ? colors.live : colors.stale, boxShadow: camera?.online ? `0 0 6px ${colors.live}` : 'none' }} />
          <span style={{ fontSize: 10, fontWeight: 600, letterSpacing: '0.06em' }}>{camera?.online ? 'LIVE' : 'OFFLINE'}</span>
        </div>

        {/* boxes for the shown frame, clipped to the circle by the parent's overflow:hidden */}
        {shown.filter((s) => s.bbox).map((s) => {
          const b = s.bbox!;
          const isPlate = s.modality === 'plate';
          const c = isPlate ? (s.plate_text ? colors.safe : colors.watch) : colors.textLo;
          return (
            <div key={s.id} style={{
              position: 'absolute',
              left: `${((b.x - b.w / 2) / SOURCE_FRAME.w) * 100}%`,
              top: `${((b.y - b.h / 2) / SOURCE_FRAME.h) * 100}%`,
              width: `${(b.w / SOURCE_FRAME.w) * 100}%`,
              height: `${(b.h / SOURCE_FRAME.h) * 100}%`,
              border: `2px solid ${c}`, borderRadius: 3, boxShadow: `0 0 8px ${c}55`,
              opacity: isPlate ? 1 : 0.35,
            }} />
          );
        })}

        {shown.length === 0 && (
          <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', textAlign: 'center', padding: 30, fontSize: 12, color: colors.textLo }}>
            No sightings yet on this camera
          </div>
        )}

        <div style={{ position: 'absolute', bottom: 18, left: '50%', transform: 'translateX(-50%)', fontSize: 10, color: colors.textMid, background: 'rgba(10,15,26,0.75)', borderRadius: 8, padding: '3px 8px', whiteSpace: 'nowrap' }}>
          no stored video frame
        </div>
      </div>

      {/* the one-question readout */}
      <div style={{ textAlign: 'center', maxWidth: 420 }}>
        <div style={{ fontSize: 15, fontWeight: 700, letterSpacing: '0.04em', color: status.color }}>{status.label}</div>
        <div style={{ fontSize: 12, color: colors.textMid, marginTop: 6, lineHeight: 1.5 }}>{status.detail}</div>
        {latestPlate && (
          <div style={{ marginTop: 12, fontFamily: 'ui-monospace, monospace', fontSize: latestPlate.plate_text ? 20 : 13, fontWeight: latestPlate.plate_text ? 700 : 400, letterSpacing: latestPlate.plate_text ? '0.1em' : 0, color: latestPlate.plate_text ? colors.textHi : colors.textLo }}>
            {latestPlate.plate_text ?? 'last read: refused'}
            <div style={{ fontSize: 10, color: colors.textLo, fontFamily: 'Inter, system-ui, sans-serif', fontWeight: 400, marginTop: 2 }}>
              {relativeTime(latestPlate.ts)}
              {latestPlate.plate_quality !== null && <> · confidence {(latestPlate.plate_quality * 100).toFixed(0)}%</>}
            </div>
          </div>
        )}
        {plateSightings.length > 0 && (
          <div style={{ fontSize: 10, color: colors.textLo, marginTop: 10 }}>
            A read is a lead, never an identification (ADR-0006/0007). No accuracy figure is claimed for
            plate OCR — every threshold here is a junk suppressor, measured only on illegible plates.
          </div>
        )}
      </div>
    </div>
  );
}
