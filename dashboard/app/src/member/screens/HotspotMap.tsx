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
import { colors } from '../../theme/tokens';

export default function HotspotMap() {
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
    </div>
  );
}
