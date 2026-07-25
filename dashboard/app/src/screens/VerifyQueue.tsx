/**
 * Ported from design/exports/design_handoff_beacon/screens/Verify Queue.dc.html
 * (design/exports/design_handoff_beacon/README.md §2). Same rebuild-from-spec
 * approach as CommunityOperationsCentre.tsx — the .dc.html export is a design
 * reference, not portable code.
 *
 * Real data: candidate queue is assembled from GET /v1/events/since
 * (there's no GET-list-of-candidates endpoint), each row's full detail from
 * GET /v1/entities/{id} (state, decayed current_score, real suspicion
 * factors F1-F6, recent sightings). Flag/Dismiss/Whitelist call the real
 * POST /v1/entities/{id}/verify, gated on operator id+token per
 * server/src/auth/operators.py.
 *
 * "Checks run" (whitelist/embedding-match/plate-match pass-fail badges) has
 * no backing endpoint — the API exposes plate_text and sighting_count only,
 * not per-check pass/fail — so that panel shows what's real instead of
 * inventing badges. "Dispatch armed response" has no separate endpoint
 * either; it reuses the same real "flag" verify action (which already
 * creates a high-severity Incident+Alert) rather than a distinct dispatch
 * call that doesn't exist server-side.
 */
import { useEffect, useState } from 'react';
import { colors } from '../theme/tokens';
import { getEventsSince, getEntity, verifyEntityAction, type EntityDetail } from '../api/client';

interface QueueRow {
  entityId: string;
  waitingSinceIso: string;
}

const FACTOR_LABELS: Record<keyof EntityDetail['factors'], string> = {
  recurrence: 'Seen repeatedly in the same area',
  time_anomaly: 'Present at an unusual hour for this location',
  crime_correlation: 'Near a historically higher-risk hex',
  casing_behaviour: 'Movement pattern resembles casing (loitering/circling)',
  territory_roaming: 'Roaming across multiple hexes in a short window',
  modal_corroboration: 'Corroborated by more than one sensor modality',
};

function relativeTime(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const s = Math.max(0, Math.floor(ms / 1000));
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  return `${Math.floor(s / 3600)}h`;
}

export default function VerifyQueue() {
  const [queue, setQueue] = useState<QueueRow[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<EntityDetail | null>(null);
  const [reason, setReason] = useState('');
  const [dispatchExpanded, setDispatchExpanded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [operatorId, setOperatorId] = useState(() => localStorage.getItem('beacon_operator_id') ?? '');
  const [operatorToken, setOperatorToken] = useState(() => localStorage.getItem('beacon_operator_token') ?? '');

  useEffect(() => {
    const since = new Date(Date.now() - 24 * 3600 * 1000).toISOString();
    getEventsSince(since, 200).then((r) => {
      const seen = new Map<string, string>();
      for (const ev of r.events) {
        if (ev.event !== 'entity.candidate') continue;
        const id = String((ev.data as Record<string, unknown>).entity_id ?? '');
        if (!id) continue;
        if (!seen.has(id)) seen.set(id, ev.ts);
      }
      setQueue(Array.from(seen, ([entityId, waitingSinceIso]) => ({ entityId, waitingSinceIso })));
    }).catch(() => {});
  }, []);

  useEffect(() => {
    if (!selectedId) { setDetail(null); return; }
    let cancelled = false;
    getEntity(selectedId).then((d) => !cancelled && setDetail(d)).catch(() => !cancelled && setDetail(null));
    return () => { cancelled = true; };
  }, [selectedId]);

  useEffect(() => {
    if (!selectedId && queue.length > 0) setSelectedId(queue[0].entityId);
  }, [queue, selectedId]);

  function persistOperator() {
    localStorage.setItem('beacon_operator_id', operatorId);
    localStorage.setItem('beacon_operator_token', operatorToken);
  }

  async function act(action: 'flag' | 'dismiss' | 'whitelist') {
    if (!detail) return;
    if (!operatorId || !operatorToken) {
      alert('Set an operator ID + token first (server/src/auth/operators.py OPERATOR_TOKENS).');
      return;
    }
    if (!reason.trim()) {
      alert('Reason for decision is required.');
      return;
    }
    persistOperator();
    const hexId = detail.recent_sightings[0]?.hex_id ?? undefined;
    setBusy(true);
    try {
      await verifyEntityAction(detail.id, action, operatorId, operatorToken, reason, action === 'whitelist' ? hexId : undefined);
      setQueue((q) => q.filter((r) => r.entityId !== detail.id));
      setSelectedId(null);
      setReason('');
      setDispatchExpanded(false);
    } catch (e) {
      alert((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const confidencePct = detail ? Math.round(detail.current_score * 100) : 0;

  return (
    <div style={{ minWidth: 1360, minHeight: '100vh', background: colors.bg900, color: colors.textHi, fontFamily: 'Inter, system-ui, sans-serif', display: 'flex', flexDirection: 'column' }}>
      <div style={{ height: 60, flex: '0 0 60px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 20px', borderBottom: `1px solid ${colors.lineDark}` }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
          <span style={{ fontWeight: 700, fontSize: 15 }}>BEACON</span>
          <span style={{ fontSize: 11, color: colors.textLo }}>Verify Queue</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 12 }}>
          <input placeholder="operator id" value={operatorId} onChange={(e) => setOperatorId(e.target.value)}
            style={{ width: 90, background: colors.bg700, border: `1px solid ${colors.lineDark}`, borderRadius: 6, color: colors.textHi, fontSize: 11, padding: '4px 6px' }} />
          <input placeholder="token" type="password" value={operatorToken} onChange={(e) => setOperatorToken(e.target.value)}
            style={{ width: 80, background: colors.bg700, border: `1px solid ${colors.lineDark}`, borderRadius: 6, color: colors.textHi, fontSize: 11, padding: '4px 6px' }} />
        </div>
      </div>

      <div style={{ flex: 1, display: 'flex', gap: 14, padding: 14, minHeight: 0 }}>
        {/* LEFT RAIL — queue */}
        <div style={{ flex: '0 0 22%', background: colors.bg800, border: `1px solid ${colors.lineDark}`, borderRadius: 12, overflowY: 'auto', padding: 8 }}>
          <div style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.06em', color: colors.textLo, padding: '6px 8px' }}>
            Candidates ({queue.length})
          </div>
          {queue.length === 0 && <div style={{ fontSize: 12, color: colors.textLo, padding: 8 }}>No candidates in the last 24h.</div>}
          {queue.map((row) => {
            const selected = row.entityId === selectedId;
            return (
              <div key={row.entityId} onClick={() => setSelectedId(row.entityId)} style={{
                display: 'flex', alignItems: 'center', gap: 8, padding: 8, borderRadius: 8, cursor: 'pointer', marginBottom: 4,
                background: selected ? colors.bg0 : 'transparent',
                borderLeft: selected ? `3px solid ${colors.beacon}` : '3px solid transparent',
              }}>
                <div style={{ width: 36, height: 36, borderRadius: 6, flexShrink: 0, background: 'repeating-linear-gradient(45deg, #1a2333, #1a2333 4px, #101725 4px, #101725 8px)' }} />
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: 12, fontWeight: 600, color: selected ? colors.inkHi : colors.textHi, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{row.entityId}</div>
                  <div style={{ fontSize: 10, color: selected ? colors.inkLo : colors.textLo }}>waiting {relativeTime(row.waitingSinceIso)}</div>
                </div>
              </div>
            );
          })}
        </div>

        {/* CENTRE */}
        <div style={{ flex: '1 1 50%', background: colors.bg50, borderRadius: 12, padding: 16, overflowY: 'auto', color: colors.inkHi }}>
          {!detail && <div style={{ color: colors.inkLo, fontSize: 13 }}>Select a candidate from the queue.</div>}
          {detail && (
            <>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
                <div style={{ fontSize: 20, fontWeight: 700 }}>{detail.id}</div>
                <span style={{ background: colors.watch, color: colors.bg900, fontSize: 11, fontWeight: 600, padding: '3px 10px', borderRadius: 999 }}>
                  Watch candidate
                </span>
              </div>
              <div style={{ marginBottom: 4, fontSize: 32, fontVariantNumeric: 'tabular-nums', fontWeight: 700 }}>{confidencePct}%</div>
              <div style={{ height: 6, background: colors.lineLight, borderRadius: 3, marginBottom: 4 }}>
                <div style={{ width: `${confidencePct}%`, height: '100%', background: colors.discovery, borderRadius: 3 }} />
              </div>
              <div style={{ fontSize: 11, color: colors.inkLo, marginBottom: 20 }}>
                calibrated confidence, decayed from base score {(detail.base_score * 100).toFixed(0)}% ({detail.sighting_count} sightings, first seen {new Date(detail.first_seen).toLocaleString()})
              </div>

              <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>Sighting timeline</div>
              <div style={{ display: 'flex', gap: 12, marginBottom: 20, overflowX: 'auto' }}>
                {detail.recent_sightings.length === 0 && <div style={{ fontSize: 12, color: colors.inkLo }}>No sightings recorded.</div>}
                {detail.recent_sightings.slice(0, 3).map((s) => (
                  <div key={s.id} style={{ flex: '0 0 140px' }}>
                    <div style={{ width: '100%', height: 70, borderRadius: 8, background: 'repeating-linear-gradient(45deg, #e5e9f0, #e5e9f0 4px, #f2f4f8 4px, #f2f4f8 8px)', marginBottom: 4 }} />
                    <div style={{ fontSize: 11, fontWeight: 600 }}>{s.camera_id}</div>
                    <div style={{ fontSize: 10, color: colors.inkLo }}>{new Date(s.ts).toLocaleTimeString()} · {(s.confidence * 100).toFixed(0)}%</div>
                  </div>
                ))}
              </div>

              <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>Why this was raised</div>
              <div style={{ marginBottom: 20 }}>
                {(Object.keys(FACTOR_LABELS) as (keyof EntityDetail['factors'])[]).map((key) => {
                  const value = detail.factors[key];
                  if (value === null || value === undefined) return null;
                  const pct = Math.round(value * 100);
                  return (
                    <div key={key} style={{ marginBottom: 8 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: colors.inkMid }}>
                        <span>{key.replace(/_/g, ' ')}</span>
                        <span style={{ fontVariantNumeric: 'tabular-nums' }}>{pct}%</span>
                      </div>
                      <div style={{ height: 4, background: colors.lineLight, borderRadius: 2, marginBottom: 3 }}>
                        <div style={{ width: `${pct}%`, height: '100%', background: colors.discovery, borderRadius: 2 }} />
                      </div>
                      <div style={{ fontSize: 11, color: colors.inkLo }}>{FACTOR_LABELS[key]}</div>
                    </div>
                  );
                })}
                {Object.values(detail.factors).every((v) => v === null || v === undefined) && (
                  <div style={{ fontSize: 12, color: colors.inkLo }}>Scorer produced no factors for this entity yet.</div>
                )}
              </div>

              <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>Checks run</div>
              <div style={{ fontSize: 11, color: colors.inkLo, marginBottom: 6 }}>
                Per-check pass/fail (whitelist / embedding-match / plate-match) isn't exposed by the API yet — showing what real data exists instead of inventing badges.
              </div>
              <div style={{ display: 'flex', gap: 16, fontSize: 12 }}>
                <span>plate: {detail.plate_text ?? 'none captured'}</span>
                <span>state: {detail.state}</span>
              </div>
            </>
          )}
        </div>

        {/* RIGHT — decision column */}
        <div style={{ flex: '0 0 28%', display: 'flex', flexDirection: 'column', gap: 10 }}>
          <button disabled={!detail || busy} onClick={() => act('flag')} style={{
            width: '100%', background: colors.beaconGrad, border: 'none', borderRadius: 10, padding: '14px', fontSize: 14, fontWeight: 700, cursor: detail ? 'pointer' : 'default',
            opacity: detail ? 1 : 0.5,
          }}>
            Flag for response
          </button>
          <div style={{ display: 'flex', gap: 8 }}>
            <button disabled={!detail || busy} onClick={() => act('dismiss')} style={{ flex: 1, background: 'transparent', border: `1px solid ${colors.lineDark}`, borderRadius: 10, padding: '10px', fontSize: 12, color: colors.textHi, cursor: detail ? 'pointer' : 'default' }}>
              Dismiss — no action
            </button>
            <button disabled={!detail || busy} onClick={() => act('whitelist')} style={{ flex: 1, background: 'transparent', border: `1px solid ${colors.lineDark}`, borderRadius: 10, padding: '10px', fontSize: 12, color: colors.textHi, cursor: detail ? 'pointer' : 'default' }}>
              Add to whitelist
            </button>
          </div>
          <textarea
            required value={reason} onChange={(e) => setReason(e.target.value)}
            placeholder="Reason for decision (required)"
            style={{ minHeight: 80, background: colors.bg800, border: `1px solid ${colors.lineDark}`, borderRadius: 10, color: colors.textHi, fontSize: 12, padding: 10, resize: 'vertical' }}
          />
          <div style={{ fontSize: 10, color: colors.textLo, display: 'flex', alignItems: 'center', gap: 6 }}>
            <span>🔗</span> Signed and recorded to the hash-chained evidence log
          </div>

          <div style={{ flex: 1 }} />

          {!dispatchExpanded ? (
            <div onClick={() => setDispatchExpanded(true)} style={{ fontSize: 11, color: colors.textLo, textDecoration: 'underline', cursor: 'pointer', textAlign: 'right' }}>
              Dispatch armed response
            </div>
          ) : (
            <div style={{ border: `1px solid ${colors.critical}`, borderRadius: 8, padding: 10 }}>
              <div style={{ fontSize: 11, color: colors.textMid, marginBottom: 8 }}>
                Uses the same real "flag" action below — there's no separate dispatch endpoint on the server yet.
              </div>
              <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                <button onClick={() => setDispatchExpanded(false)} style={{ background: 'transparent', border: `1px solid ${colors.lineDark}`, borderRadius: 6, padding: '4px 10px', fontSize: 11, color: colors.textHi, cursor: 'pointer' }}>Cancel</button>
                <button disabled={busy} onClick={() => act('flag')} style={{ background: colors.critical, border: 'none', borderRadius: 6, padding: '4px 10px', fontSize: 11, color: '#fff', cursor: 'pointer' }}>Confirm</button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
