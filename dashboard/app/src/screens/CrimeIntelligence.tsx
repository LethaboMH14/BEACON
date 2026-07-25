/**
 * Ported from design/exports/design_handoff_beacon/screens/Crime Intelligence.dc.html
 * (design/exports/design_handoff_beacon/README.md §4). Same from-scratch rebuild approach
 * as the other shipped screens — the .dc.html export is a design reference, not portable code.
 *
 * Real data: GET /v1/hotspots (top risk areas, hexes-above-threshold count, model version)
 * and GET /v1/risk (per-hour forecast line for the top hex, real top_factors for
 * "Contributing factors" — see server/src/risk/forecast.py's honesty boundary: today that's
 * claim_count + same_hour_claims from real Claim rows, "provisional" until Ndu's model lands).
 *
 * No backing endpoint exists for: forecast confidence interval, historical-baseline overlay,
 * top peril / incidents-by-peril (Claim.claim_type is a real DB column but nothing exposes it
 * over the API), or a 12-month claims trend. Each is labelled honestly instead of invented
 * (design system rule 5, design/exports/design_handoff_beacon/README.md §"Non-negotiable
 * product rules").
 */
import { useEffect, useState } from 'react';
import { colors, riskColor, type RiskLevel } from '../theme/tokens';
import { getHotspots, getRisk, type HotspotEntry, type RiskEstimate } from '../api/client';

function riskLevelFor(score: number): RiskLevel {
  if (score >= 0.75) return 'critical';
  if (score >= 0.5) return 'high';
  if (score >= 0.25) return 'watch';
  return 'safe';
}

const ABOVE_THRESHOLD = 0.5;

const FACTOR_LABELS: Record<string, string> = {
  claim_count: 'Historical claims recorded in this hex',
  same_hour_claims: 'Of those, claims at this same hour',
};

function SimTag() {
  return (
    <span style={{
      fontSize: 9, fontWeight: 700, letterSpacing: '0.04em', color: colors.textLo,
      border: `1px solid ${colors.lineDark}`, borderRadius: 4, padding: '2px 5px',
    }}>
      NO BACKEND YET
    </span>
  );
}

export default function CrimeIntelligence() {
  const [hotspots, setHotspots] = useState<HotspotEntry[]>([]);
  const [curve, setCurve] = useState<RiskEstimate[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    getHotspots(undefined, 20).then(async (res) => {
      if (cancelled) return;
      setHotspots(res.hotspots);
      const topHex = res.hotspots[0]?.hex_id;
      if (!topHex) { setLoading(false); return; }
      const hours = Array.from({ length: 24 }, (_, h) => h);
      const estimates = await Promise.all(hours.map((h) => getRisk(topHex, h).catch(() => null)));
      if (!cancelled) setCurve(estimates.filter((e): e is RiskEstimate => e !== null));
      setLoading(false);
    }).catch(() => setLoading(false));
    return () => { cancelled = true; };
  }, []);

  const avgRisk = hotspots.length ? hotspots.reduce((s, h) => s + h.risk_score, 0) / hotspots.length : 0;
  const aboveThreshold = hotspots.filter((h) => h.risk_score >= ABOVE_THRESHOLD).length;
  const topHotspot = hotspots[0];
  const modelVersion = topHotspot?.source === 'model' ? topHotspot.label.replace('model:', '') : null;
  const topFactorsHex = curve.find((c) => c.top_factors)?.top_factors as Record<string, number> | undefined;

  const maxCurve = Math.max(0.01, ...curve.map((c) => c.risk_score));

  return (
    <div style={{ minWidth: 1360, minHeight: '100vh', background: colors.bg900, color: colors.textHi, fontFamily: 'Inter, system-ui, sans-serif' }}>
      <div style={{ height: 60, display: 'flex', alignItems: 'center', gap: 8, padding: '0 20px', borderBottom: `1px solid ${colors.lineDark}` }}>
        <span style={{ fontWeight: 700, fontSize: 15 }}>BEACON</span>
        <span style={{ fontSize: 11, color: colors.textLo }}>Crime Intelligence</span>
        {loading && <span style={{ fontSize: 11, color: colors.textLo, marginLeft: 8 }}>loading live risk data…</span>}
      </div>

      <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 14 }}>
        {/* HERO ROW */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
          <div style={{ background: colors.bg800, border: `1px solid ${colors.lineDark}`, borderRadius: 12, padding: 14 }}>
            <div style={{ fontSize: 11, color: colors.textLo, marginBottom: 6 }}>Avg. forecast risk, top hexes <SimTag /></div>
            <div style={{ fontSize: 28, fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}>{(avgRisk * 100).toFixed(0)}%</div>
            <div style={{ fontSize: 10, color: colors.textLo, marginTop: 4 }}>Live mean of GET /v1/hotspots — no confidence interval available yet.</div>
          </div>
          <div style={{ background: colors.bg800, border: `1px solid ${colors.lineDark}`, borderRadius: 12, padding: 14 }}>
            <div style={{ fontSize: 11, color: colors.textLo, marginBottom: 6 }}>Top peril <SimTag /></div>
            <div style={{ fontSize: 16, fontWeight: 600, color: colors.textLo }}>—</div>
            <div style={{ fontSize: 10, color: colors.textLo, marginTop: 4 }}>Claim.claim_type exists in the DB but no endpoint exposes it yet.</div>
          </div>
          <div style={{ background: colors.bg800, border: `1px solid ${colors.lineDark}`, borderRadius: 12, padding: 14 }}>
            <div style={{ fontSize: 11, color: colors.textLo, marginBottom: 6 }}>Hexes ≥ {Math.round(ABOVE_THRESHOLD * 100)}% risk</div>
            <div style={{ fontSize: 28, fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}>{aboveThreshold}</div>
            <div style={{ fontSize: 10, color: colors.textLo, marginTop: 4 }}>of {hotspots.length} ranked hexes, live.</div>
          </div>
          <div style={{ background: colors.bg800, border: `1px solid ${colors.lineDark}`, borderRadius: 12, padding: 14 }}>
            <div style={{ fontSize: 11, color: colors.textLo, marginBottom: 6 }}>Model version</div>
            <div style={{ fontSize: 16, fontWeight: 600 }}>{modelVersion ?? 'claims_fallback'}</div>
            <div style={{ fontSize: 10, color: colors.textLo, marginTop: 4 }}>
              {modelVersion ? 'Real RiskCell row from Ndu\'s pipeline.' : 'Provisional — derived from raw historical claim counts, not a calibrated model yet.'}
            </div>
          </div>
        </div>

        {/* MAIN CHART ROW */}
        <div style={{ display: 'flex', gap: 12 }}>
          <div style={{ flex: '0 0 30%', background: colors.bg800, border: `1px solid ${colors.lineDark}`, borderRadius: 12, padding: 14, maxHeight: 380, overflowY: 'auto' }}>
            <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 4 }}>Top risk areas</div>
            <div style={{ fontSize: 10, color: colors.textLo, marginBottom: 10 }}>Real GET /v1/hotspots ranking — hex IDs shown, no suburb-name mapping table exists yet.</div>
            {hotspots.length === 0 && !loading && <div style={{ fontSize: 12, color: colors.textLo }}>No hotspots yet.</div>}
            {hotspots.map((h) => {
              const level = riskLevelFor(h.risk_score);
              return (
                <div key={h.hex_id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '6px 0', borderBottom: `1px solid ${colors.lineDark}` }}>
                  <span style={{ fontFamily: 'monospace', fontSize: 11, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 140 }}>{h.hex_id}</span>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div style={{ width: 40, height: 4, background: colors.lineDark, borderRadius: 2 }}>
                      <div style={{ width: `${h.risk_score * 100}%`, height: '100%', background: riskColor[level], borderRadius: 2 }} />
                    </div>
                    <span style={{ fontSize: 11, fontWeight: 600, color: riskColor[level], fontVariantNumeric: 'tabular-nums' }}>{(h.risk_score * 100).toFixed(0)}%</span>
                  </div>
                </div>
              );
            })}
          </div>

          <div style={{ flex: 1, background: colors.bg800, border: `1px solid ${colors.lineDark}`, borderRadius: 12, padding: 14 }}>
            <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 4 }}>
              24h forecast — {topHotspot?.hex_id ?? '—'}
            </div>
            <div style={{ fontSize: 10, color: colors.textLo, marginBottom: 10 }}>
              Live GET /v1/risk per hour for the top-ranked hex. No uncertainty band or historical-baseline overlay available yet <SimTag />.
            </div>
            <svg viewBox="0 0 720 180" style={{ width: '100%', height: 180 }}>
              {curve.length > 1 && (
                <polyline
                  fill="none" stroke={colors.beacon} strokeWidth={2}
                  points={curve.map((c, i) => `${(i / (curve.length - 1)) * 700 + 10},${170 - (c.risk_score / maxCurve) * 150}`).join(' ')}
                />
              )}
              {curve.map((c, i) => (
                <circle key={c.hour} cx={(i / Math.max(1, curve.length - 1)) * 700 + 10} cy={170 - (c.risk_score / maxCurve) * 150} r={2} fill={colors.beacon} />
              ))}
            </svg>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 9, color: colors.textLo }}>
              <span>00:00</span><span>06:00</span><span>12:00</span><span>18:00</span><span>23:00</span>
            </div>
          </div>
        </div>

        {/* TWO CHARTS BELOW */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <div style={{ background: colors.bg800, border: `1px solid ${colors.lineDark}`, borderRadius: 12, padding: 14, minHeight: 120 }}>
            <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 4 }}>Incidents by peril <SimTag /></div>
            <div style={{ fontSize: 11, color: colors.textLo }}>Claim.claim_type (Theft, Burglary, Hijack, ...) exists in the DB but no endpoint aggregates it — showing nothing rather than a fake chart.</div>
          </div>
          <div style={{ background: colors.bg800, border: `1px solid ${colors.lineDark}`, borderRadius: 12, padding: 14, minHeight: 120 }}>
            <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 4 }}>12-month claims trend <SimTag /></div>
            <div style={{ fontSize: 11, color: colors.textLo }}>No time-series claims endpoint exists yet — only the current per-hex forecast is live.</div>
          </div>
        </div>

        {/* RIGHT RAIL merged into a bottom panel for layout simplicity */}
        <div style={{ background: colors.bg800, border: `1px solid ${colors.lineDark}`, borderRadius: 12, padding: 14 }}>
          <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 4 }}>Contributing factors — {topHotspot?.hex_id ?? '—'}</div>
          <div style={{ fontSize: 11, color: colors.textLo, marginBottom: 10 }}>
            Contributions are model attributions, not causes. Real fields returned today (claim_count,
            same_hour_claims) — the richer factor set (near-repeat contagion, payday proximity,
            load-reduction stage, weather, historical density) arrives once Ndu's forecast model lands.
          </div>
          {!topFactorsHex && <div style={{ fontSize: 12, color: colors.textLo }}>No factors returned for this hex.</div>}
          {topFactorsHex && Object.entries(topFactorsHex).map(([key, value]) => {
            const pct = key === 'same_hour_claims' && topFactorsHex.claim_count
              ? Math.round((Number(value) / Number(topFactorsHex.claim_count)) * 100)
              : Math.min(100, Math.round(Number(value)));
            return (
              <div key={key} style={{ marginBottom: 8 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: colors.textMid }}>
                  <span>{FACTOR_LABELS[key] ?? key}</span>
                  <span style={{ fontVariantNumeric: 'tabular-nums' }}>{value}</span>
                </div>
                <div style={{ height: 4, background: colors.lineDark, borderRadius: 2 }}>
                  <div style={{ width: `${pct}%`, height: '100%', background: colors.discovery, borderRadius: 2 }} />
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
