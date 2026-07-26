/**
 * The other half of the Ring Cam demo: what Thabang would actually see on his
 * phone at the moment of detection, not the raw bbox feed operators get.
 *
 * Driven by the SAME demo track as RingCam.tsx (same t, same detections) — this
 * is a companion view, not a separate data source. Two things stay honest on
 * purpose:
 *  - Weapon copy ("Potential weapon detected") is a direct, unhedged read of a
 *    real object-detection hit, because that's what it is.
 *  - Face copy is deliberately NOT "High-risk individual identified" — this
 *    pipeline runs a generic face detector, not identity matching against a
 *    watchlist, and BEACON's own scoring machine (server/src/suspicion/scorer.py,
 *    ADR-0002) can only ever reach "candidate", never "flagged", without a human
 *    verify call. So the phone shows "Possible match — flagged for review",
 *    which is what the system can honestly claim.
 */
import { colors } from '../theme/tokens';
import type { DemoDetection, DemoFrame } from '../screens/RingCam';

function alertFor(detections: DemoDetection[]): { title: string; body: string; color: string; icon: string } | null {
  const weapon = detections.find((d) => d.kind === 'weapon');
  if (weapon) {
    return {
      title: 'Potential weapon detected',
      body: `${weapon.label || 'Object'} · ${(weapon.confidence * 100).toFixed(0)}% confidence — tap to view the clip`,
      color: colors.critical,
      icon: '⚠',
    };
  }
  const face = detections.find((d) => d.modality === 'face');
  if (face) {
    return {
      title: 'Possible match — flagged for review',
      body: `Face detected, ${(face.confidence * 100).toFixed(0)}% confidence — not an identification, held for a human check`,
      color: colors.watch,
      icon: '👤',
    };
  }
  const plate = detections.find((d) => d.modality === 'plate');
  if (plate) {
    return {
      title: plate.ocr_text ? `Plate read: ${plate.ocr_text}` : 'Plate seen, not read',
      body: plate.ocr_text ? 'Logged against recent sightings' : 'Below the confidence gate — no read recorded',
      color: colors.textMid,
      icon: '🚗',
    };
  }
  return null;
}

function clock(t: number): string {
  const m = Math.floor(t / 60).toString().padStart(2, '0');
  const s = Math.floor(t % 60).toString().padStart(2, '0');
  return `${m}:${s}`;
}

export default function PhoneAlert({ activeFrame, demoTime, counts }: {
  activeFrame: DemoFrame | null;
  demoTime: number;
  counts: Record<string, number>;
}) {
  const alert = activeFrame ? alertFor(activeFrame.detections) : null;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10 }}>
      <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.08em', color: colors.textLo }}>
        USER'S PHONE (DEMO — mirrors this clip's playback)
      </div>

      <div style={{
        width: 200, height: 410, borderRadius: 32, background: colors.bg700,
        border: `6px solid ${colors.bg800}`, boxShadow: colors.shadowCardDark,
        position: 'relative', overflow: 'hidden',
      }}>
        {/* notch */}
        <div style={{ position: 'absolute', top: 0, left: '50%', transform: 'translateX(-50%)', width: 70, height: 18, background: colors.bg800, borderRadius: '0 0 10px 10px', zIndex: 3 }} />

        {/* status bar */}
        <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 14px 0', fontSize: 10, color: colors.textHi, fontVariantNumeric: 'tabular-nums' }}>
          <span>{clock(demoTime)}</span>
          <span>●●● 🔋</span>
        </div>

        {/* lock screen background */}
        <div style={{
          position: 'absolute', inset: 0,
          background: alert
            ? `linear-gradient(160deg, ${alert.color}33 0%, ${colors.bg900} 60%)`
            : `linear-gradient(160deg, ${colors.bg800} 0%, ${colors.bg900} 60%)`,
          transition: 'background 300ms ease',
        }} />

        <div style={{ position: 'relative', paddingTop: 40, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
          <div style={{ fontSize: 30, fontWeight: 200, color: colors.textHi, fontVariantNumeric: 'tabular-nums' }}>{clock(demoTime)}</div>
          <div style={{ fontSize: 11, color: colors.textMid }}>Beacon is connected to your dashcam</div>
        </div>

        {/* notification card */}
        <div style={{ position: 'relative', margin: '26px 10px 0', minHeight: 74 }}>
          {alert ? (
            <div style={{
              background: 'rgba(16,23,37,0.92)', border: `1px solid ${alert.color}66`,
              borderRadius: 14, padding: '10px 12px', boxShadow: `0 0 20px ${alert.color}33`,
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                <span style={{
                  width: 18, height: 18, borderRadius: 5, background: alert.color, display: 'flex',
                  alignItems: 'center', justifyContent: 'center', fontSize: 10,
                }}>{alert.icon}</span>
                <span style={{ fontSize: 9, fontWeight: 700, letterSpacing: '0.06em', color: colors.textLo }}>BEACON · NOW</span>
              </div>
              <div style={{ fontSize: 12, fontWeight: 700, color: colors.textHi }}>{alert.title}</div>
              <div style={{ fontSize: 10, color: colors.textMid, marginTop: 2, lineHeight: 1.4 }}>{alert.body}</div>
            </div>
          ) : (
            <div style={{
              background: 'rgba(16,23,37,0.6)', border: `1px solid ${colors.lineDark}`,
              borderRadius: 14, padding: '10px 12px', textAlign: 'center',
            }}>
              <div style={{ fontSize: 11, color: colors.textLo }}>No detection requiring attention right now</div>
            </div>
          )}
        </div>

        {/* swipe hint */}
        <div style={{ position: 'absolute', bottom: 14, left: '50%', transform: 'translateX(-50%)', fontSize: 9, color: colors.textLo }}>
          swipe up to open Beacon
        </div>
      </div>

      <div style={{ fontSize: 10, color: colors.textLo, maxWidth: 200, textAlign: 'center', lineHeight: 1.4 }}>
        Across this clip: {counts.weapon ?? 0} weapon alert{counts.weapon === 1 ? '' : 's'}, {counts.face ?? 0} review flag{counts.face === 1 ? '' : 's'}.
        Raw detections are filtered down to only what needs a decision — not every box the model drew.
      </div>
    </div>
  );
}
