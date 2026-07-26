/**
 * BEACON design tokens — TypeScript mirror of src/index.css :root.
 * Source of truth is design/PROMPT-PACK.md §1; keep these two files in sync.
 * Any ported Claude Design screen must reference these instead of hardcoded hex.
 */

export const colors = {
  // dark chrome (headers, nav, ops shell)
  bg900: '#0A0F1A',
  bg800: '#101725',
  bg700: '#182130',
  lineDark: 'rgba(255, 255, 255, 0.08)',
  textHi: '#F1F5F9',
  textMid: '#94A3B8',
  textLo: '#64748B',

  // light content (data panels, member view, exec view)
  bg50: '#F7F9FC',
  bg0: '#FFFFFF',
  lineLight: 'rgba(15, 23, 42, 0.08)',
  inkHi: '#0F172A',
  inkMid: '#475569',
  inkLo: '#94A3B8',

  // brand
  beacon: '#F5A623',
  // Deep end of the beacon ramp. Already in index.css @theme as
  // --color-beacon-deep; mirrored here so screens can compose their own
  // gradients rather than being limited to the one canned beaconGrad below.
  beaconDeep: '#F27B21',
  beaconGrad: 'linear-gradient(135deg, #F5A623 0%, #F27B21 100%)',
  discovery: '#0B5FA5',
  discoverySoft: '#E8F1F9',

  // risk ramp — ONLY for risk/severity, never decoration
  safe: '#10B981',
  watch: '#F59E0B',
  high: '#F0653A',
  critical: '#E11D48',

  // semantic
  live: '#22D3EE',
  stale: '#6B7280',

  // soft elevation — used instead of flat borders alone on cards/buttons
  shadowCard: '0 1px 2px rgba(15, 23, 42, 0.06), 0 6px 20px rgba(15, 23, 42, 0.06)',
  shadowCardDark: '0 1px 2px rgba(0, 0, 0, 0.3), 0 8px 28px rgba(0, 0, 0, 0.35)',
} as const;

export type RiskLevel = 'safe' | 'watch' | 'high' | 'critical';

export const riskColor: Record<RiskLevel, string> = {
  safe: colors.safe,
  watch: colors.watch,
  high: colors.high,
  critical: colors.critical,
};

export type Severity = 'critical' | 'high' | 'medium' | 'low';

/** Mirrors server/src/api/alerts.py CANCEL_WINDOW_SECONDS_BY_SEVERITY — keep in sync. */
export const cancelWindowSecondsBySeverity: Record<Severity, number> = {
  critical: 15,
  high: 20,
  medium: 30,
  low: 45,
};
