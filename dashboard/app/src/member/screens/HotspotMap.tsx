/**
 * Hotspot map — now the SAPS-enhanced reference map directly, not the live
 * Leaflet re-derivation.
 *
 * Per direct instruction (2026-07-26): this screen must show ONLY the
 * SAPS-enhanced map (hotspot_pipeline/combined_hotspot_map.html, served
 * statically from public/) — green rings = SAPS-verified suburbs, blue
 * square markers = SAPS-only precincts with no matching crime-report
 * history. The previous live Leaflet view (GET /v1/hotspots/geo,
 * client-side filters, tap-to-see-suburb sheet) is removed entirely rather
 * than kept as a second view — this IS the risk map now.
 */
import { useEffect, useState } from 'react';
import { colors } from '../../theme/tokens';
import { radii } from '../ui';
import { awardPoints } from './Rewards';

/** Seconds on this tab before the reroute prompt appears. */
const PROMPT_DELAY_S = 20;
const REROUTE_POINTS = 150;

export default function HotspotMap() {
  const [showPrompt, setShowPrompt] = useState(false);
  const [claimed, setClaimed] = useState(false);

  useEffect(() => {
    // A per-tab-visit timer, not a real geofence — there's no live GPS feed
    // driving this map (it's the static SAPS-enhanced iframe), so "approaching
    // a high-risk area" is a scripted demo prompt, same honesty pattern as
    // Home Guard's detection trigger. It reflects a real capability (the
    // safest-route screen genuinely scores routes against real hotspot data)
    // without claiming this specific popup came from a live location check.
    const id = setTimeout(() => setShowPrompt(true), PROMPT_DELAY_S * 1000);
    return () => clearTimeout(id);
  }, []);

  function takeSaferRoute() {
    awardPoints('Chose the safer route', 'Avoided today\'s risk-map hotspots', REROUTE_POINTS);
    setClaimed(true);
    setTimeout(() => setShowPrompt(false), 1800);
  }

  return (
    <div style={{ position: 'relative', height: '100%', display: 'flex', flexDirection: 'column' }}>
      <div style={{ padding: '6px 16px 10px', background: colors.bg50, borderBottom: `1px solid ${colors.lineLight}`, flexShrink: 0 }}>
        <h1 style={{ margin: 0, fontSize: 21, fontWeight: 700, letterSpacing: -0.4 }}>Risk map</h1>
      </div>
      <iframe
        title="SAPS-enhanced risk map"
        src="/combined_hotspot_map.html"
        style={{ flex: 1, width: '100%', border: 'none' }}
      />

      {/* ---- reroute prompt: slides down from the top ---- */}
      <div style={{
        position: 'absolute', left: 12, right: 12, top: showPrompt ? 12 : -140,
        transition: 'top 0.35s ease', zIndex: 40,
        borderRadius: radii.card, padding: 14, background: colors.bg50,
        border: `1px solid ${colors.lineLight}`, boxShadow: '0 14px 34px rgba(15,23,42,0.22)',
      }}>
        {!claimed ? (
          <>
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
              <span style={{ fontSize: 18, lineHeight: 1 }}>⚠️</span>
              <p style={{ margin: 0, fontSize: 13, lineHeight: 1.5, fontWeight: 600, color: colors.inkHi }}>
                You're approaching a high-risk area. An alternative route is available that avoids today's hotspots.
              </p>
            </div>
            <div style={{ display: 'flex', gap: 8, marginTop: 11 }}>
              <button onClick={takeSaferRoute} style={{
                flex: 1, minHeight: 38, borderRadius: radii.control, border: 'none', cursor: 'pointer',
                background: colors.discovery, color: '#fff', fontSize: 12.5, fontWeight: 650,
              }}>Use safer route</button>
              <button onClick={() => setShowPrompt(false)} style={{
                minHeight: 38, padding: '0 14px', borderRadius: radii.control, cursor: 'pointer',
                background: 'transparent', border: `1px solid ${colors.lineLight}`, color: colors.inkMid,
                fontSize: 12.5, fontWeight: 600,
              }}>Dismiss</button>
            </div>
          </>
        ) : (
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ fontSize: 18, lineHeight: 1 }}>✅</span>
            <p style={{ margin: 0, fontSize: 13, fontWeight: 650, color: colors.inkHi }}>
              Safer route chosen — Discovery awarded +{REROUTE_POINTS} Vitality Points.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
