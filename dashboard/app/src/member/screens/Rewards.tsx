/**
 * Vitality Points — the Discovery ecosystem hook.
 *
 * This is where BEACON stops being a safety app and starts being a Discovery
 * product: safer behaviour is measurable, and Discovery already has a currency
 * for rewarding measurable behaviour. Routes avoided, detections acknowledged,
 * home guard armed — all things the rest of this app already produces.
 *
 * The ledger is local demo state (no member accounts in this build), so the
 * screen says so. What is NOT invented: the "reduced route exposure" figure is
 * computed from the real exposure scores the safest-route endpoint returned for
 * this session's routes. If you haven't planned a route yet, the screen says
 * that instead of showing a number — the design's zero-state, as a real state.
 */
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { colors } from '../../theme/tokens';
import { Button, Card, Chip, MethodNote, Screen, ScreenHeader, radii } from '../ui';

const GOLD_AT = 4000;

interface LedgerRow { id: string; label: string; detail: string; points: number; when: string }

const LEDGER: LedgerRow[] = [
  { id: '1', label: 'Took the safer route', detail: 'Sandton CBD → Fourways', points: 150, when: 'Today' },
  { id: '2', label: 'Home guard armed all week', detail: '7 of 7 nights', points: 300, when: 'Mon' },
  { id: '3', label: 'Dashcam active on 5 trips', detail: 'Drive vision enabled', points: 250, when: 'Last week' },
  { id: '4', label: 'Reviewed a flagged detection', detail: 'Marked as false alarm', points: 40, when: 'Last week' },
];

/**
 * Session-scoped exposure record, written by the safest-route screen.
 * sessionStorage rather than a store because it must survive a tab switch but
 * must NOT look like a persisted member history — it isn't one.
 */
export interface ExposureRecord { chosen: number; alternative: number }
const EXPOSURE_KEY = 'beacon.session.exposure';

export function recordExposure(chosen: number, alternative: number) {
  try {
    const prev: ExposureRecord[] = JSON.parse(sessionStorage.getItem(EXPOSURE_KEY) ?? '[]');
    sessionStorage.setItem(EXPOSURE_KEY, JSON.stringify([...prev, { chosen, alternative }]));
  } catch { /* storage disabled — the screen just shows its zero-state */ }
}

function readExposure(): ExposureRecord[] {
  try { return JSON.parse(sessionStorage.getItem(EXPOSURE_KEY) ?? '[]'); } catch { return []; }
}

export default function Rewards() {
  const nav = useNavigate();
  const [records, setRecords] = useState<ExposureRecord[]>([]);
  useEffect(() => { setRecords(readExposure()); }, []);

  const total = LEDGER.reduce((s, r) => s + r.points, 0) + 2500;
  const toGold = Math.max(0, GOLD_AT - total);
  const pct = Math.min(100, (total / GOLD_AT) * 100);

  // Real arithmetic over real scores, or nothing.
  const reduction = records.length
    ? (() => {
        const chosen = records.reduce((s, r) => s + r.chosen, 0);
        const alt = records.reduce((s, r) => s + r.alternative, 0);
        return alt > 0 ? Math.round(((alt - chosen) / alt) * 100) : null;
      })()
    : null;

  return (
    <Screen>
      <ScreenHeader title="Vitality Points" subtitle="Safer choices, rewarded" />

      <div style={{
        borderRadius: radii.hero, padding: 20, marginBottom: 14, textAlign: 'center',
        background: `linear-gradient(150deg, ${colors.beacon} 0%, ${colors.beaconDeep} 100%)`,
        color: '#1A1206', boxShadow: '0 14px 34px rgba(242,123,33,0.28)',
      }}>
        <div style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: 0.9, fontWeight: 700, opacity: 0.7 }}>
          Points earned
        </div>
        <div className="tabular-nums" style={{ fontSize: 44, fontWeight: 800, letterSpacing: -1.4, lineHeight: 1.15 }}>
          {total.toLocaleString('en-ZA')}
        </div>
        <div style={{ fontSize: 13, fontWeight: 600, opacity: 0.8, marginBottom: 14 }}>
          {toGold > 0 ? `${toGold.toLocaleString('en-ZA')} to Gold status` : 'Gold status reached'}
        </div>
        <div style={{ height: 7, borderRadius: 4, background: 'rgba(26,18,6,0.18)', overflow: 'hidden' }}>
          <div style={{ height: '100%', width: `${pct}%`, background: '#1A1206', borderRadius: 4 }} />
        </div>
      </div>

      {/* the one figure that must be real or absent */}
      <Card style={{ padding: 15, marginBottom: 14 }}>
        {reduction != null ? (
          <>
            <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 5 }}>
              You've cut your route exposure {reduction}% this session.
            </div>
            <p style={{ margin: 0, fontSize: 12.5, color: colors.inkMid, lineHeight: 1.5 }}>
              Across {records.length} route{records.length === 1 ? '' : 's'} planned, comparing what you chose against the alternative.
            </p>
          </>
        ) : (
          <>
            <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 5 }}>No routes planned yet</div>
            <p style={{ margin: '0 0 12px', fontSize: 12.5, color: colors.inkMid, lineHeight: 1.5 }}>
              Plan a route and we'll show how much claims exposure you actually avoided — measured, not estimated.
            </p>
            <Button variant="secondary" onClick={() => nav('/route')}>Plan a route</Button>
          </>
        )}
      </Card>

      <Card style={{ padding: 0, overflow: 'hidden' }}>
        <div style={{ padding: '14px 16px 10px', fontSize: 14, fontWeight: 700 }}>Recent activity</div>
        {LEDGER.map((r, i) => (
          <div key={r.id} style={{
            display: 'flex', alignItems: 'center', gap: 12, padding: '12px 16px',
            borderTop: `1px solid ${colors.lineLight}`,
          }}>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 13.5, fontWeight: 650 }}>{r.label}</div>
              <div style={{ fontSize: 11.5, color: colors.inkLo, marginTop: 2 }}>{r.detail} · {r.when}</div>
            </div>
            <Chip tone="brand">+{r.points}</Chip>
          </div>
        ))}
      </Card>

      <MethodNote>
        Points and the activity ledger are demo values — there is no member account or Vitality
        integration in this build. The exposure reduction above is computed from real route scores.
      </MethodNote>
    </Screen>
  );
}
