/**
 * Live Drive — the member's in-car view of what the dashcam model is seeing.
 *
 * The delivered design showed this as five separate frames: a lens with a
 * `dashcam frame placeholder`, then Weapon/Critical, Face/Watch, Plate/No-read
 * and Idle/Clear notification states side by side with captions. Those are the
 * same screen at five moments. Here it is one screen, and which of those five it
 * looks like is decided by the detections actually on screen at the current
 * video timestamp.
 *
 * RECORDED, NOT SIMULATED, AND NOT LIVE
 * The video is a real clip; the boxes come from scripts/vision_lens_demo.py
 * --dry-run running the real plate / weapon / face detectors over it offline.
 * The inference is genuine, the camera feed is not live. The badge says
 * RECORDED for exactly that reason — "LIVE" would be a lie, "SIMULATED" would
 * undersell real model output. Same rule as screens/RingCam.tsx.
 *
 * Video files are gitignored (*.mp4) — copyrighted broadcast footage, local
 * only. Detection tracks are bbox/label/confidence JSON with no imagery, so
 * they are committed.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { colors } from '../../theme/tokens';
import { Chip, radii } from '../ui';
import type { DemoTrack, DemoFrame, DemoDetection } from '../../screens/RingCam';
import { reportVisionIncident } from '../../api/member';

const CLIPS = [
  { id: 'hijack', label: 'Hijack attempt', video: '/demo-clips/ring-demo-hijack.mp4', track: '/demo-clips/ring-demo-hijack-detections.json' },
  { id: 'lens', label: 'Plate lens', video: '/demo-clips/ring-demo.mp4', track: '/demo-clips/ring-demo-detections.json' },
  { id: 'drivinghome', label: 'Driving home', video: '/demo-clips/ring-demo-drivinghome.mp4', track: '/demo-clips/ring-demo-drivinghome-detections.json' },
] as const;
type ClipId = typeof CLIPS[number]['id'];

/** The four alert states the design drew, derived rather than hardcoded. */
type Level = 'critical' | 'watch' | 'info' | 'clear';

function levelFor(frame: DemoFrame | null, corroborated: boolean): { level: Level; title: string; body: string } {
  const dets = frame?.detections ?? [];
  const weapon = dets.find((d) => d.kind === 'weapon');
  // A single sampled frame flagging "weapon" is exactly as likely to be one
  // noisy inference (a road sign, a mirror, a hand) as a real threat — the
  // hijack clip's genuine weapon shows up on many consecutive sampled frames,
  // not one. Require at least one neighbouring sampled frame to agree before
  // this counts as critical; an uncorroborated hit is shown as a low-key
  // review item instead of a false "weapon in view" alarm.
  if (weapon && corroborated) {
    return {
      level: 'critical',
      title: 'Possible weapon in view',
      // The model's own sub-type label (pistol/sword/etc.) is unreliable —
      // measured misclassifying real weapons across clips — so only the
      // presence + confidence is shown, not a specific (possibly wrong) type.
      body: `The camera model flagged a possible weapon at ${Math.round(weapon.confidence * 100)}% confidence across multiple frames. Nothing has been reported yet — you decide.`,
    };
  }
  if (weapon) {
    return {
      level: 'watch',
      title: 'Possible object flagged, unconfirmed',
      body: `A single frame briefly flagged a possible weapon at ${Math.round(weapon.confidence * 100)}% confidence, with no agreement from frames around it — most likely a misread, not shown as a weapon alert.`,
    };
  }
  const face = dets.find((d) => d.modality === 'face');
  if (face) {
    return {
      level: 'watch',
      title: 'Person detected near the vehicle',
      body: 'A face was detected. It has not been matched to anyone — a read is a lead, never an identification.',
    };
  }
  const plate = dets.find((d) => d.modality === 'plate');
  if (plate) {
    return plate.ocr_text
      ? { level: 'info', title: `Plate read: ${plate.ocr_text}`, body: 'Recorded to your drive log. Not shared with anyone.' }
      : { level: 'info', title: 'Plate seen, not readable', body: "We saw a plate but couldn't read it clearly enough to be sure, so nothing was recorded." };
  }
  return { level: 'clear', title: 'All clear', body: 'Nothing of interest in view.' };
}

const LEVEL_COLOR: Record<Level, string> = {
  critical: colors.critical, watch: colors.watch, info: colors.live, clear: colors.safe,
};

function boxColor(d: DemoDetection): string {
  if (d.kind === 'weapon') return colors.critical;
  if (d.modality === 'face') return colors.beacon;
  if (d.modality === 'plate') return d.ocr_text ? colors.safe : colors.watch;
  return colors.textLo;
}

function boxLabel(d: DemoDetection): string {
  if (d.modality === 'plate') return d.ocr_text ? `Plate · ${d.ocr_text}` : 'Plate · not read';
  if (d.modality === 'face') return 'Face · review';
  if (d.kind === 'weapon') return `Weapon · ${Math.round(d.confidence * 100)}%`;
  return `${d.kind || d.modality} · ${Math.round(d.confidence * 100)}%`;
}

export default function LiveDrive() {
  const [clipId, setClipId] = useState<ClipId>('hijack');
  const [tracks, setTracks] = useState<Partial<Record<ClipId, DemoTrack>>>({});
  const [t, setT] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [dismissed, setDismissed] = useState<string | null>(null);
  const [reportState, setReportState] = useState<Record<string, 'sending' | 'sent' | 'failed'>>({});
  const [reportDetail, setReportDetail] = useState<string | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);

  const clip = CLIPS.find((c) => c.id === clipId)!;
  const track = tracks[clipId] ?? null;

  useEffect(() => {
    let cancelled = false;
    Promise.all(CLIPS.map((c) =>
      fetch(c.track).then((r) => r.json()).then((tr: DemoTrack) => [c.id, tr] as const).catch(() => null),
    )).then((rows) => {
      if (cancelled) return;
      const next: Partial<Record<ClipId, DemoTrack>> = {};
      for (const r of rows) if (r) next[r[0]] = r[1];
      setTracks(next);
    });
    return () => { cancelled = true; };
  }, []);

  // The track is sampled roughly once a second, not per video frame, so this is
  // "nearest measurement", and it expires rather than holding a stale box.
  const frame = useMemo(() => {
    if (!track?.frames.length) return null;
    let best = track.frames[0];
    let bestD = Math.abs(best.t - t);
    for (const f of track.frames) {
      const d = Math.abs(f.t - t);
      if (d < bestD) { best = f; bestD = d; }
    }
    return bestD <= 1.2 ? best : null;
  }, [track, t]);

  // A weapon reading is corroborated if an adjacent sampled frame (within
  // ~2 sample intervals either side) also saw one — the same "is this a
  // persistent signal or one noisy frame" check used across the pipeline.
  const weaponCorroborated = useMemo(() => {
    if (!frame || !track?.frames.length) return false;
    if (!frame.detections.some((d) => d.kind === 'weapon')) return false;
    const span = ((track as { interval_s?: number }).interval_s ?? 1) * 2.5;
    return track.frames.some(
      (f) => f !== frame && Math.abs(f.t - frame.t) <= span && f.detections.some((d) => d.kind === 'weapon'),
    );
  }, [frame, track]);

  const alert = levelFor(frame, weaponCorroborated);
  const alertKey = `${clipId}:${alert.level}:${alert.title}`;
  const showAlert = alert.level !== 'clear' && dismissed !== alertKey && playing;
  const accent = LEVEL_COLOR[alert.level];

  // A member reporting a critical detection is the named-human decision this
  // pipeline requires before anything leaves BEACON — same rule as the ops
  // console's escalate endpoint (server/src/api/vision_jobs.py), just for a
  // recorded clip instead of a live jobs.py run. See POST /v1/vision/report.
  async function report() {
    if (!frame) return;
    const weapon = frame.detections.find((d) => d.kind === 'weapon');
    setReportState((s) => ({ ...s, [alertKey]: 'sending' }));
    setReportDetail(null);
    try {
      const res = await reportVisionIncident({
        clip_label: clip.label,
        level: alert.level,
        title: alert.title,
        detail: alert.body,
        confidence: weapon?.confidence,
        timestamp_s: frame.t,
      });
      setReportState((s) => ({ ...s, [alertKey]: res.ok ? 'sent' : 'failed' }));
      setReportDetail(res.ok ? `Sent to ${res.to.join(', ')} via ${res.provider}.` : res.detail);
    } catch (e) {
      setReportState((s) => ({ ...s, [alertKey]: 'failed' }));
      setReportDetail(e instanceof Error ? e.message : 'Could not reach the server');
    }
  }

  const counts = track?.counts ?? {};
  const peakWeapon = useMemo(() => {
    const confs = (track?.frames ?? []).flatMap((f) => f.detections.filter((d) => d.kind === 'weapon').map((d) => d.confidence));
    return confs.length ? Math.max(...confs) : 0;
  }, [track]);

  return (
    <div style={{ padding: '4px 16px 16px', color: colors.textHi }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700, letterSpacing: -0.4 }}>Cam</h1>
          <p style={{ margin: '3px 0 0', fontSize: 12.5, color: colors.textMid }}>Dashcam vision, on this trip</p>
        </div>
        <span style={{
          display: 'inline-flex', alignItems: 'center', gap: 6, padding: '5px 10px', borderRadius: radii.chip,
          fontSize: 10, fontWeight: 700, letterSpacing: 0.7, color: colors.beacon,
          background: 'rgba(245,166,35,0.12)', border: '1px solid rgba(245,166,35,0.3)',
        }}>
          <span style={{ width: 6, height: 6, borderRadius: 3, background: colors.beacon }} />
          RECORDED
        </span>
      </div>

      {/* clip picker */}
      <div style={{ display: 'flex', gap: 6, marginBottom: 12 }}>
        {CLIPS.map((c) => (
          <button key={c.id} onClick={() => { setClipId(c.id); setT(0); setDismissed(null); }} style={{
            flex: 1, minHeight: 36, borderRadius: radii.chip, fontSize: 12, fontWeight: 600, cursor: 'pointer',
            background: c.id === clipId ? colors.bg700 : 'transparent',
            color: c.id === clipId ? colors.textHi : colors.textLo,
            border: `1px solid ${c.id === clipId ? colors.beacon : colors.lineDark}`,
          }}>{c.label}</button>
        ))}
      </div>

      {/* ---- the lens ---- */}
      <div style={{
        position: 'relative', width: '100%', aspectRatio: '1 / 1', borderRadius: '50%',
        overflow: 'hidden', background: colors.bg800,
        // Ring tints to the current alert level — the design's four coloured
        // states, on one element, driven by the detections.
        boxShadow: `0 0 0 3px ${accent}, 0 0 44px color-mix(in srgb, ${accent} 45%, transparent)`,
        transition: 'box-shadow 0.35s ease', marginBottom: 14,
      }}>
        <video
          ref={videoRef}
          src={clip.video}
          playsInline
          onTimeUpdate={(e) => setT(e.currentTarget.currentTime)}
          onPlay={() => setPlaying(true)}
          onPause={() => setPlaying(false)}
          onEnded={() => setPlaying(false)}
          style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
        />

        {/* boxes, in source-frame percentage space so they scale with the circle */}
        {frame && frame.detections.map((d, i) => {
          if (!d.bbox) return null;
          const left = ((d.bbox.x - d.bbox.w / 2) / frame.width) * 100;
          const top = ((d.bbox.y - d.bbox.h / 2) / frame.height) * 100;
          const w = (d.bbox.w / frame.width) * 100;
          const h = (d.bbox.h / frame.height) * 100;
          const c = boxColor(d);
          return (
            <div key={i} style={{
              position: 'absolute', left: `${left}%`, top: `${top}%`, width: `${w}%`, height: `${h}%`,
              border: `2px solid ${c}`, borderRadius: 6, boxShadow: `0 0 12px color-mix(in srgb, ${c} 55%, transparent)`,
            }}>
              <span style={{
                position: 'absolute', top: -20, left: -2, whiteSpace: 'nowrap',
                fontSize: 9.5, fontWeight: 700, padding: '2px 6px', borderRadius: 5,
                background: c, color: '#0A0F1A',
              }}>{boxLabel(d)}</span>
            </div>
          );
        })}

        {!playing && (
          <button
            onClick={() => videoRef.current?.play()}
            aria-label="Play"
            style={{
              position: 'absolute', inset: 0, display: 'grid', placeItems: 'center',
              background: 'rgba(10,15,26,0.42)', border: 'none', cursor: 'pointer', color: colors.textHi,
            }}
          >
            <span style={{
              width: 62, height: 62, borderRadius: '50%', background: colors.beacon, color: colors.bg900,
              display: 'grid', placeItems: 'center', fontSize: 24, paddingLeft: 5,
              boxShadow: '0 10px 30px rgba(245,166,35,0.4)',
            }}>▶</span>
          </button>
        )}
      </div>

      {/* ---- counter strip: the run's real totals ---- */}
      <div style={{
        display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8, marginBottom: 14,
      }}>
        <Counter label="Plates" value={counts.plate ?? 0} sub={`${counts.plate_read ?? 0} read`} />
        {/* The design's caption here was "9 weapon · 1 above gate". There is no
            weapon confidence gate in this pipeline to be above — inventing one
            to make the caption true would be backwards. Peak confidence is a
            real number from the track and says the same useful thing. */}
        <Counter label="Weapon" value={counts.weapon ?? 0} sub={peakWeapon ? `peak ${Math.round(peakWeapon * 100)}%` : 'none seen'} tone={colors.critical} />
        <Counter label="Faces" value={counts.face ?? 0} sub="held for review" tone={colors.beacon} />
      </div>

      {/* ---- notification: the design's four frames, as one live element ---- */}
      {showAlert && (
        <div style={{
          borderRadius: radii.card, padding: 14, background: colors.bg800,
          border: `1px solid color-mix(in srgb, ${accent} 40%, transparent)`,
          boxShadow: colors.shadowCardDark,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 7 }}>
            <span style={{ width: 8, height: 8, borderRadius: 4, background: accent, flexShrink: 0 }} />
            <span style={{ fontSize: 14.5, fontWeight: 700 }}>{alert.title}</span>
          </div>
          <p style={{ margin: 0, fontSize: 12.5, lineHeight: 1.55, color: colors.textMid }}>{alert.body}</p>

          {alert.level === 'critical' && (
            <>
              <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
                <button
                  onClick={report}
                  disabled={reportState[alertKey] === 'sending' || reportState[alertKey] === 'sent'}
                  style={{ ...btn(colors.critical, '#fff'), opacity: reportState[alertKey] === 'sending' ? 0.7 : 1 }}
                >
                  {reportState[alertKey] === 'sending' ? 'Reporting…'
                    : reportState[alertKey] === 'sent' ? 'Reported ✓'
                    : 'Report to security'}
                </button>
                <button onClick={() => setDismissed(alertKey)} style={btn(colors.bg700, colors.textHi)}>I'm fine</button>
              </div>
              {reportState[alertKey] && reportDetail && (
                <p style={{
                  margin: '9px 0 0', fontSize: 11.5, lineHeight: 1.5,
                  color: reportState[alertKey] === 'sent' ? colors.safe : colors.critical,
                }}>
                  {reportState[alertKey] === 'sent' ? reportDetail : `Not sent: ${reportDetail}`}
                </p>
              )}
            </>
          )}
          {alert.level !== 'critical' && (
            <button onClick={() => setDismissed(alertKey)} style={{ ...btn(colors.bg700, colors.textMid), marginTop: 11, width: '100%' }}>Dismiss</button>
          )}
        </div>
      )}

      {!showAlert && (
        <div style={{
          borderRadius: radii.card, padding: 14, background: colors.bg800,
          border: `1px solid ${colors.lineDark}`, display: 'flex', alignItems: 'center', gap: 10,
        }}>
          <span style={{ width: 8, height: 8, borderRadius: 4, background: colors.safe }} />
          <span style={{ fontSize: 13.5, fontWeight: 600 }}>{playing ? 'All clear' : 'Tap play to run the clip'}</span>
        </div>
      )}

      <div style={{ display: 'flex', gap: 6, marginTop: 12, flexWrap: 'wrap' }}>
        <Chip dark>On-device inference</Chip>
        <Chip dark>No footage uploaded</Chip>
      </div>

      <p style={{ margin: '12px 2px 0', fontSize: 11, lineHeight: 1.5, color: colors.textLo }}>
        Boxes are real output from the plate, weapon and face detectors run over this clip offline —
        real inference, recorded footage, not a live camera. Nothing here has been reported to anyone.
      </p>
    </div>
  );
}

function btn(bg: string, fg: string) {
  return {
    flex: 1, minHeight: 44, borderRadius: radii.control, border: 'none',
    background: bg, color: fg, fontSize: 13.5, fontWeight: 650, cursor: 'pointer',
  } as const;
}

function Counter({ label, value, sub, tone }: { label: string; value: number; sub: string; tone?: string }) {
  return (
    <div style={{
      background: colors.bg800, border: `1px solid ${colors.lineDark}`,
      borderRadius: radii.control, padding: '10px 11px',
    }}>
      <div style={{ fontSize: 9.5, textTransform: 'uppercase', letterSpacing: 0.6, color: colors.textLo, fontWeight: 700 }}>{label}</div>
      <div className="tabular-nums" style={{ fontSize: 20, fontWeight: 700, color: tone ?? colors.textHi, lineHeight: 1.2 }}>{value}</div>
      <div style={{ fontSize: 10, color: colors.textLo }}>{sub}</div>
    </div>
  );
}
