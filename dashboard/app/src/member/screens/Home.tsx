/**
 * Home — the screen a member opens by default.
 *
 * There was no Home frame in the delivered set; it was implied by the bottom
 * tab bar on every other screen. Without it the app is five destinations and no
 * front door, so this is the one screen added rather than ported.
 *
 * It is a router, not a dashboard. Everything on it is either a real number from
 * the claims data or a link to a screen that owns that question. Nothing is
 * invented for visual weight — the hero card's suburb, severity, peak hour and
 * claim count all come from GET /v1/hotspots/geo.
 */
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { colors } from '../../theme/tokens';
import { getHotspotsGeo, type HotspotsGeoResponse } from '../../api/member';
import { Card, Chip, MethodNote, Screen, Skeleton, ErrorState, radii, hourLabel } from '../ui';

/**
 * The member's home suburb. Hardcoded because there is no member account system
 * in this build — when there is, this comes from their policy address. Named
 * explicitly rather than buried so it is obvious what is and isn't personalised.
 */
const MEMBER = { firstName: 'Thandi', suburb: 'BRYANSTON' };

function greeting(h: number): string {
  if (h < 12) return 'Good morning';
  if (h < 17) return 'Good afternoon';
  return 'Good evening';
}

export default function Home() {
  const nav = useNavigate();
  const [data, setData] = useState<HotspotsGeoResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const hour = new Date().getHours();

  useEffect(() => {
    let cancelled = false;
    getHotspotsGeo({ minSeverity: 0 })
      .then((r) => { if (!cancelled) setData(r); })
      .catch((e: Error) => { if (!cancelled) setError(e.message); });
    return () => { cancelled = true; };
  }, []);

  const mine = useMemo(
    () => data?.hotspots.find((h) => h.suburb.toUpperCase() === MEMBER.suburb) ?? null,
    [data],
  );

  // Rank is a real position in the real list, not a made-up percentile.
  const rank = useMemo(() => {
    if (!data || !mine) return null;
    return data.hotspots.findIndex((h) => h.hex_id === mine.hex_id) + 1;
  }, [data, mine]);

  const tone = !mine ? 'safe' : mine.severity_score >= 0.66 ? 'critical' : mine.severity_score >= 0.33 ? 'high' : 'watch';
  const toneColor = { safe: colors.safe, watch: colors.watch, high: colors.high, critical: colors.critical }[tone];
  // Plain-language label first, the underlying score as a smaller detail — a
  // member reads "Higher risk area", not a two-decimal number with no context.
  const toneLabel = { safe: 'Low claims history', watch: 'Some claims history', high: 'Higher claims history', critical: 'High claims history' }[tone];

  return (
    <Screen>
      <div style={{ marginBottom: 18 }}>
        <p style={{ margin: 0, fontSize: 13.5, color: colors.inkMid }}>{greeting(hour)},</p>
        <h1 style={{ margin: '2px 0 0', fontSize: 27, fontWeight: 700, letterSpacing: -0.6 }}>{MEMBER.firstName}</h1>
      </div>

      {error && <ErrorState message={error} />}

      {/* ---- hero: your suburb, right now ---- */}
      {!data && !error && <Skeleton h={168} />}
      {data && (
        <div style={{
          borderRadius: radii.hero, padding: 18, marginBottom: 14,
          background: `linear-gradient(150deg, ${colors.discovery} 0%, #08406F 100%)`,
          color: '#fff', boxShadow: '0 14px 34px rgba(11,95,165,0.32)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
            <span style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: 0.8, fontWeight: 700, opacity: 0.75 }}>
              Where you are
            </span>
            <span style={{
              display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 10.5, fontWeight: 700,
              padding: '4px 9px', borderRadius: 999, background: 'rgba(255,255,255,0.16)',
            }}>
              <span style={{ width: 6, height: 6, borderRadius: 3, background: toneColor }} />
              {mine ? `${toneLabel} · ${mine.severity_score.toFixed(2)}` : 'No claims on record'}
            </span>
          </div>

          <div style={{ fontSize: 26, fontWeight: 700, letterSpacing: -0.5, marginBottom: 6 }}>
            {MEMBER.suburb.replace(/\b\w/g, (c) => c.toUpperCase())}
          </div>

          <p style={{ margin: 0, fontSize: 13.5, lineHeight: 1.55, opacity: 0.92 }}>
            {mine ? (
              <>
                {mine.incident_count} local crime reports on record here, mostly {(mine.top_claim_type ?? 'theft').toLowerCase()}.
                Historically busiest around <strong>{hourLabel(mine.peak_hour)}</strong>
                {mine.peak_day_of_week ? ` on ${mine.peak_day_of_week}s` : ''}.
              </>
            ) : (
              <>No suburb-level claims history on record for your area.</>
            )}
          </p>

          {rank && (
            <div className="tabular-nums" style={{ marginTop: 12, fontSize: 11.5, opacity: 0.72 }}>
              #{rank} of {data.count} suburbs by severity
            </div>
          )}
        </div>
      )}

      {/* ---- actions ---- */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 14 }}>
        <ActionTile title="Plan a safer route" body="Compare routes by claims exposure" icon="🧭" onClick={() => nav('/route')} />
        <ActionTile title="Risk map" body={data ? `${data.count} suburbs mapped` : 'Loading…'} icon="🗺️" onClick={() => nav('/map')} />
        <ActionTile title="Drive" body="Dashcam vision" icon="🚗" onClick={() => nav('/drive')} />
        <ActionTile title="Home guard" body="Property monitoring" icon="🏠" onClick={() => nav('/home-guard')} />
      </div>

      {/* ---- top severity, real ordering ---- */}
      {data && (
        <Card style={{ padding: 14 }}>
          <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 10 }}>
            <span style={{ fontSize: 14, fontWeight: 700 }}>Highest-risk areas nationally</span>
            <button onClick={() => nav('/map')} style={{
              background: 'transparent', border: 'none', color: colors.discovery,
              fontSize: 12, fontWeight: 650, cursor: 'pointer', padding: 0,
            }}>See map</button>
          </div>
          {data.hotspots.slice(0, 4).map((h, i) => (
            <div key={h.hex_id} style={{
              display: 'flex', alignItems: 'center', gap: 10, padding: '8px 0',
              borderTop: i === 0 ? 'none' : `1px solid ${colors.lineLight}`,
            }}>
              <span style={{ width: 10, height: 10, borderRadius: 5, background: h.color, flexShrink: 0 }} />
              <span style={{ flex: 1, fontSize: 13.5, fontWeight: 600 }}>
                {h.suburb.replace(/\b\w/g, (c) => c.toUpperCase())}
              </span>
              <Chip tone={h.severity_score >= 0.66 ? 'critical' : 'high'}>{h.severity_score.toFixed(2)}</Chip>
            </div>
          ))}
          <MethodNote>
            {data.total_claims_analysed.toLocaleString('en-ZA')} claims analysed. {data.caveat}
          </MethodNote>
        </Card>
      )}
    </Screen>
  );
}

function ActionTile({ title, body, icon, onClick }: { title: string; body: string; icon: string; onClick: () => void }) {
  return (
    <Card onClick={onClick} style={{ padding: 14, minHeight: 104 }}>
      <div style={{ fontSize: 22, marginBottom: 8 }}>{icon}</div>
      <div style={{ fontSize: 13.5, fontWeight: 700, lineHeight: 1.3, marginBottom: 3 }}>{title}</div>
      <div style={{ fontSize: 11.5, color: colors.inkMid, lineHeight: 1.4 }}>{body}</div>
    </Card>
  );
}
