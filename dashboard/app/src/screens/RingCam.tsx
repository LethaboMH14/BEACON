/**
 * A single question, asked plainly: does the plate model actually see number plates
 * on this camera? Not a second detection UI — Live AI Camera already has the full
 * bbox overlay, filmstrip and fused-assessment panel. This is a doorbell-style round
 * lens plus one honest readout, for someone who wants the answer in five seconds.
 *
 * Same real data as LiveAICamera.tsx (GET /v1/cameras, GET /v1/sightings), same
 * SOURCE_FRAME caveat (bbox pixels with no recorded frame size — see that file's
 * header), same refusal to draw a plate string that OCR didn't accept.
 *
 * RECORDED DEMO MODE: alongside the live-camera picker, a set of extra entries
 * (DEMO_CLIPS below) each play a locally-stored source clip (never committed —
 * see dashboard/app/public/demo-clips, covered by repo-wide *.mp4 in
 * .gitignore; it's copyrighted broadcast footage) with its bounding boxes
 * drawn in sync from a real offline run of scripts/vision_lens_demo.py
 * --dry-run (plate/weapon/face detectors, real inference, just not a live
 * camera feed — labelled RECORDED, not LIVE, and never SIMULATED, because
 * nothing about the detections themselves is fake). Each detection track
 * (scripts/detections_ringcam*.json, mirrored into public/demo-clips for the
 * dev server) has no images in it, just bbox/label/confidence JSON, so it's
 * safe to commit — same pattern as scripts/detections_hijack.json.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { colors } from '../theme/tokens';
import { getCameras, getSightings, type CameraStatusEntry, type SightingDetail } from '../api/client';
import PhoneAlert from '../components/PhoneAlert';

const SOURCE_FRAME = { w: 1920, h: 1080 };
const STRIPE = 'repeating-linear-gradient(45deg, #182130, #182130 8px, #101725 8px, #101725 16px)';

// Two scenario slots for the 5-minute demo: "lens" answers the plate-OCR
// question, "hijack" is the weapon-in-frame moment. A third clip ("cam lens
// demo", per the user) is expected to land in this list later.
const DEMO_CLIPS = [
  { id: 'lens', label: '▶ Demo: plate lens', video: '/demo-clips/ring-demo.mp4', track: '/demo-clips/ring-demo-detections.json' },
  { id: 'hijack', label: '▶ Demo: cam hijack', video: '/demo-clips/ring-demo-hijack.mp4', track: '/demo-clips/ring-demo-hijack-detections.json' },
  { id: 'drivinghome', label: '▶ Demo: driving home', video: '/demo-clips/ring-demo-drivinghome.mp4', track: '/demo-clips/ring-demo-drivinghome-detections.json' },
] as const;
type DemoClipId = typeof DEMO_CLIPS[number]['id'];

export type DemoDetection = {
  modality: string;
  kind: string;
  label: string;
  confidence: number;
  bbox: { x: number; y: number; w: number; h: number } | null;
  ocr_text?: string | null;
  ocr_reason?: string | null;
};
export type DemoFrame = { t: number; width: number; height: number; detections: DemoDetection[] };
export type DemoTrack = {
  video: string;
  counts: Record<string, number>;
  frames: DemoFrame[];
};

function demoDetectionLabel(d: DemoDetection): string {
  if (d.modality === 'plate') return d.ocr_text ? `PLATE ${d.ocr_text}` : 'PLATE (unreadable)';
  if (d.modality === 'face') return 'FACE';
  if (d.kind === 'weapon') return 'WEAPON';
  return (d.kind || d.label || d.modality).toUpperCase();
}

function demoDetectionColor(d: DemoDetection): string {
  if (d.kind === 'weapon') return colors.critical;
  if (d.modality === 'face') return colors.beacon;
  if (d.modality === 'plate') return d.ocr_text ? colors.safe : colors.watch;
  return colors.textLo;
}

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
  const [demoClipId, setDemoClipId] = useState<DemoClipId | null>(null);
  const [demoTracks, setDemoTracks] = useState<Partial<Record<DemoClipId, DemoTrack>>>({});
  const [demoTime, setDemoTime] = useState(0);
  const [demoPlaying, setDemoPlaying] = useState(false);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const demoMode = demoClipId !== null;
  const activeClip = DEMO_CLIPS.find((c) => c.id === demoClipId) ?? null;
  const demoTrack = demoClipId ? demoTracks[demoClipId] ?? null : null;

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

  // Fetch every clip's track up front (small JSON, no images) so the picker
  // buttons can enable immediately rather than one at a time as each is clicked.
  useEffect(() => {
    let cancelled = false;
    Promise.all(DEMO_CLIPS.map((c) => fetch(c.track).then((r) => r.json()).then((t: DemoTrack) => [c.id, t] as const).catch(() => null)))
      .then((results) => {
        if (cancelled) return;
        const next: Partial<Record<DemoClipId, DemoTrack>> = {};
        for (const r of results) if (r) next[r[0]] = r[1];
        setDemoTracks(next);
      });
    return () => { cancelled = true; };
  }, []);

  const camera = cameras.find((c) => c.id === selectedCameraId) ?? null;

  // Nearest sampled frame to wherever the video currently is — the track is sampled
  // every ~1s, not every video frame, so this is "closest we measured", not exact.
  const demoActiveFrame = useMemo(() => {
    if (!demoTrack || demoTrack.frames.length === 0) return null;
    let closest = demoTrack.frames[0];
    let bestDelta = Math.abs(closest.t - demoTime);
    for (const f of demoTrack.frames) {
      const delta = Math.abs(f.t - demoTime);
      if (delta < bestDelta) { closest = f; bestDelta = delta; }
    }
    // Don't hold a stale box on screen once the video has moved well past it.
    return bestDelta <= 1.2 ? closest : null;
  }, [demoTrack, demoTime]);

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

  const demoCounts = demoTrack?.counts ?? {};
  const demoStatusColor = demoActiveFrame && demoActiveFrame.detections.some((d) => d.kind === 'weapon')
    ? colors.critical
    : colors.beacon;

  return (
    <div style={{ minWidth: 900, minHeight: '100vh', background: colors.bg900, color: colors.textHi, fontFamily: 'Inter, system-ui, sans-serif', padding: 24, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 18 }}>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', justifyContent: 'center' }}>
        {cameras.map((c) => (
          <button key={c.id} onClick={() => { setDemoClipId(null); setSelectedCameraId(c.id); }} style={{
            background: !demoMode && c.id === selectedCameraId ? colors.beaconGrad : colors.bg800,
            color: !demoMode && c.id === selectedCameraId ? colors.bg900 : colors.textMid,
            border: `1px solid ${colors.lineDark}`, borderRadius: 999, padding: '6px 12px', fontSize: 12, cursor: 'pointer',
          }}>
            {c.name} {c.online ? '●' : '○'}
          </button>
        ))}
        {cameras.length === 0 && <span style={{ fontSize: 12, color: colors.textLo }}>No cameras registered yet.</span>}
        {DEMO_CLIPS.map((c) => {
          const ready = !!demoTracks[c.id];
          return (
            <button key={c.id} onClick={() => { setDemoClipId(c.id); setDemoTime(0); }} disabled={!ready} style={{
              background: demoClipId === c.id ? colors.beaconGrad : colors.bg800,
              color: demoClipId === c.id ? colors.bg900 : colors.textMid,
              border: `1px solid ${colors.lineDark}`, borderRadius: 999, padding: '6px 12px', fontSize: 12,
              cursor: ready ? 'pointer' : 'not-allowed', opacity: ready ? 1 : 0.5,
            }}>
              {c.label}
            </button>
          );
        })}
      </div>

      <div style={{ display: 'flex', gap: 28, alignItems: 'flex-start', justifyContent: 'center', flexWrap: 'wrap' }}>
      {/* the round lens */}
      <div style={{
        position: 'relative', width: 340, height: 340, borderRadius: '50%',
        background: STRIPE, overflow: 'hidden',
        border: `6px solid ${colors.bg700}`,
        boxShadow: `0 0 0 2px ${demoMode ? demoStatusColor : status.color}, 0 0 40px ${(demoMode ? demoStatusColor : status.color)}55`,
      }}>
        {demoMode && activeClip && (
          <video
            key={activeClip.id}
            ref={videoRef}
            src={activeClip.video}
            muted
            autoPlay
            loop
            playsInline
            onPlay={() => setDemoPlaying(true)}
            onPause={() => setDemoPlaying(false)}
            onTimeUpdate={(e) => setDemoTime(e.currentTarget.currentTime)}
            style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover' }}
          />
        )}

        <div style={{ position: 'absolute', top: 18, left: '50%', transform: 'translateX(-50%)', display: 'flex', alignItems: 'center', gap: 6, background: 'rgba(10,15,26,0.75)', borderRadius: 999, padding: '3px 10px' }}>
          {demoMode ? (
            <>
              <span style={{ width: 7, height: 7, borderRadius: '50%', background: demoPlaying ? colors.beacon : colors.stale, boxShadow: demoPlaying ? `0 0 6px ${colors.beacon}` : 'none' }} />
              <span style={{ fontSize: 10, fontWeight: 600, letterSpacing: '0.06em' }}>RECORDED DEMO</span>
            </>
          ) : (
            <>
              <span style={{ width: 7, height: 7, borderRadius: '50%', background: camera?.online ? colors.live : colors.stale, boxShadow: camera?.online ? `0 0 6px ${colors.live}` : 'none' }} />
              <span style={{ fontSize: 10, fontWeight: 600, letterSpacing: '0.06em' }}>{camera?.online ? 'LIVE' : 'OFFLINE'}</span>
            </>
          )}
        </div>

        {/* demo mode: boxes for the nearest sampled frame, scaled to that frame's own recorded size */}
        {demoMode && demoActiveFrame?.detections.filter((d) => d.bbox).map((d, i) => {
          const b = d.bbox!;
          const c = demoDetectionColor(d);
          return (
            <div key={i} style={{
              position: 'absolute',
              left: `${((b.x - b.w / 2) / demoActiveFrame.width) * 100}%`,
              top: `${((b.y - b.h / 2) / demoActiveFrame.height) * 100}%`,
              width: `${(b.w / demoActiveFrame.width) * 100}%`,
              height: `${(b.h / demoActiveFrame.height) * 100}%`,
              border: `2px solid ${c}`, borderRadius: 3, boxShadow: `0 0 8px ${c}88`,
            }}>
              <div style={{
                position: 'absolute', bottom: '100%', left: -2, whiteSpace: 'nowrap',
                background: c, color: colors.bg900, fontSize: 8, fontWeight: 700,
                letterSpacing: '0.03em', padding: '1px 4px', borderRadius: '3px 3px 0 0',
              }}>
                {demoDetectionLabel(d)}
              </div>
            </div>
          );
        })}

        {/* live mode: boxes for the shown frame, clipped to the circle by the parent's overflow:hidden */}
        {!demoMode && shown.filter((s) => s.bbox).map((s) => {
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

        {!demoMode && shown.length === 0 && (
          <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', textAlign: 'center', padding: 30, fontSize: 12, color: colors.textLo }}>
            No sightings yet on this camera
          </div>
        )}

        <div style={{ position: 'absolute', bottom: 18, left: '50%', transform: 'translateX(-50%)', fontSize: 10, color: colors.textMid, background: 'rgba(10,15,26,0.75)', borderRadius: 8, padding: '3px 8px', whiteSpace: 'nowrap' }}>
          {demoMode
            ? (demoActiveFrame ? `${demoActiveFrame.detections.length} box${demoActiveFrame.detections.length === 1 ? '' : 'es'} at t=${demoTime.toFixed(1)}s` : `t=${demoTime.toFixed(1)}s — no detection this close`)
            : 'no stored video frame'}
        </div>
      </div>

      {demoMode && (
        <PhoneAlert activeFrame={demoActiveFrame} demoTime={demoTime} counts={demoCounts} />
      )}
      </div>

      {/* the one-question readout */}
      {demoMode ? (
        <div style={{ textAlign: 'center', maxWidth: 460 }}>
          <div style={{ fontSize: 15, fontWeight: 700, letterSpacing: '0.04em', color: demoStatusColor }}>
            {demoActiveFrame && demoActiveFrame.detections.some((d) => d.kind === 'weapon') ? 'WEAPON DETECTED RIGHT NOW' : 'PLAYING BACK REAL DETECTIONS'}
          </div>
          <div style={{ fontSize: 12, color: colors.textMid, marginTop: 6, lineHeight: 1.5 }}>
            Across this clip: {demoCounts.weapon ?? 0} weapon detection{demoCounts.weapon === 1 ? '' : 's'}, {demoCounts.plate ?? 0} plate
            box{demoCounts.plate === 1 ? '' : 'es'} ({demoCounts.plate_read ?? 0} read), {demoCounts.face ?? 0} face detection{demoCounts.face === 1 ? '' : 's'}
            — every number here came from a real, local, offline run of the same plate/weapon/face pipeline against this clip
            (<code style={{ fontSize: 10 }}>scripts/vision_lens_demo.py --dry-run</code>), not a live camera.
          </div>
          {demoActiveFrame && demoActiveFrame.detections.length > 0 && (
            <div style={{ display: 'grid', gap: 4, marginTop: 12, textAlign: 'left' }}>
              {demoActiveFrame.detections.map((d, i) => (
                <div key={i} style={{
                  display: 'flex', justifyContent: 'space-between', fontSize: 11, padding: '4px 8px',
                  borderRadius: 6, border: `1px solid ${colors.lineDark}`, borderLeft: `3px solid ${demoDetectionColor(d)}`,
                }}>
                  <span>{demoDetectionLabel(d)}</span>
                  <span style={{ color: colors.textMid, fontVariantNumeric: 'tabular-nums' }}>{(d.confidence * 100).toFixed(0)}%</span>
                </div>
              ))}
            </div>
          )}
          <div style={{ fontSize: 10, color: colors.textLo, marginTop: 10 }}>
            A read is a lead, never an identification (ADR-0006/0007). Source clip kept local only — never
            committed to the repo (copyrighted footage; see file header).
          </div>
        </div>
      ) : (
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
      )}
    </div>
  );
}
