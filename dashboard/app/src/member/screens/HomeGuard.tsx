/**
 * Home Guard — property audio monitoring and the escalation ladder.
 *
 * SIMULATED, AND LABELLED THAT WAY THROUGHOUT
 * There is no acoustic model in this build. The glass-break detection is a
 * scripted demo trigger, not inference, so this screen carries a SIMULATED tag
 * in its header and a plain sentence at the bottom saying so. Everything else
 * about it — the escalation ladder, the two-button response, the cancel window —
 * is the real interaction design, which is what this screen is for.
 *
 * The design delivered this as three frames (resting / active detection /
 * escalation ladder). They are one screen in three states, and the state
 * advances on its own once triggered, which is the point: the ladder climbs
 * whether or not you respond, and you can stop it at any rung.
 */
import { useEffect, useRef, useState } from 'react';
import { colors } from '../../theme/tokens';
import { Button, Card, Chip, MethodNote, Screen, ScreenHeader, SimulatedTag } from '../ui';
import { createAlert } from '../../api/member';

const PROPERTY = { address: '14 Ballyclare Drive', suburb: 'Bryanston' };

/** Seconds before each rung fires, from the moment of detection. */
const LADDER = [
  { at: 0, title: 'Sound detected', detail: 'Glass-break signature at the lounge window' },
  { at: 20, title: 'You were asked to confirm', detail: 'No response yet' },
  { at: 45, title: 'Your emergency contact notified', detail: 'Sipho M. · +27 82 ••• ••41' },
  { at: 75, title: 'Armed response dispatched', detail: 'Discovery-linked provider' },
] as const;

/** Seconds you have to cancel before the ladder starts climbing. */
const CANCEL_WINDOW = 20;

type Mode = 'resting' | 'active';

export default function HomeGuard() {
  const [mode, setMode] = useState<Mode>('resting');
  const [elapsed, setElapsed] = useState(0);
  const [resolved, setResolved] = useState<'home' | 'away' | 'cancelled' | null>(null);
  const [alertError, setAlertError] = useState<string | null>(null);
  const startedAt = useRef<number>(0);

  // "I'm not home" is the one branch that should actually reach the ops
  // dashboard — a real Alert (POST /v1/alerts), so it shows up live on the
  // console with a real evidence-chain entry, not just a local UI state
  // change. This does NOT send an email (server/.env has no SENDGRID_API_KEY
  // configured) — see HomeGuard.tsx's module header for the rest of what's
  // still simulated here (the detection itself).
  async function escalate() {
    setResolved('away');
    setAlertError(null);
    try {
      await createAlert({
        alert_type: 'suspicious_activity',
        recipient_id: 'private_security_demo',
        recipient_type: 'ops',
        severity: 'critical',
        message: `Home Guard: glass-break detected at ${PROPERTY.address}, ${PROPERTY.suburb} — member confirmed not home.`,
      });
    } catch (e) {
      setAlertError(e instanceof Error ? e.message : 'Could not reach the server');
    }
  }

  useEffect(() => {
    if (mode !== 'active' || resolved) return;
    startedAt.current = Date.now();
    const id = setInterval(() => setElapsed(Math.floor((Date.now() - startedAt.current) / 1000)), 250);
    return () => clearInterval(id);
  }, [mode, resolved]);

  function reset() { setMode('resting'); setElapsed(0); setResolved(null); }

  const countdown = Math.max(0, CANCEL_WINDOW - elapsed);
  const reached = resolved ? -1 : LADDER.filter((r) => elapsed >= r.at).length;

  return (
    <Screen>
      <ScreenHeader
        title="Home guard"
        subtitle={`${PROPERTY.address} · ${PROPERTY.suburb}`}
        right={<SimulatedTag />}
      />

      {/* ---- listening surface ---- */}
      <Card style={{ padding: 18, marginBottom: 14 }} accent={mode === 'active' && !resolved ? `color-mix(in srgb, ${colors.critical} 45%, transparent)` : undefined}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{
              width: 9, height: 9, borderRadius: 5,
              background: mode === 'active' && !resolved ? colors.critical : colors.safe,
              animation: 'beacon-pulse 1.8s ease-in-out infinite',
            }} />
            <span style={{ fontSize: 14, fontWeight: 700 }}>
              {resolved ? 'Stood down' : mode === 'active' ? 'Sound detected' : 'Listening'}
            </span>
          </div>
          <Chip tone={mode === 'active' && !resolved ? 'critical' : 'safe'}>
            {mode === 'active' && !resolved ? 'Responding' : 'Armed'}
          </Chip>
        </div>

        <Waveform active={mode === 'active' && !resolved} />

        <div style={{ display: 'flex', gap: 6, marginTop: 14, flexWrap: 'wrap' }}>
          <Chip>Glass break</Chip>
          <Chip>Forced entry</Chip>
          <Chip>Raised voices</Chip>
        </div>

        <MethodNote>
          Audio is analysed on the device. Nothing is recorded or stored.
        </MethodNote>
      </Card>

      {/* ---- active detection ---- */}
      {mode === 'active' && !resolved && (
        <Card style={{ marginBottom: 14, padding: 16 }} accent={`color-mix(in srgb, ${colors.critical} 45%, transparent)`}>
          <div style={{ fontSize: 15.5, fontWeight: 700, marginBottom: 6 }}>
            We detected the sound of breaking glass at your property.
          </div>
          <p style={{ margin: '0 0 14px', fontSize: 13, lineHeight: 1.5, color: colors.inkMid }}>
            Nothing has been sent to anyone yet.{' '}
            {countdown > 0
              ? <>You have <strong className="tabular-nums">{countdown}s</strong> to stop this.</>
              : <>Escalation has started.</>}
          </p>

          {countdown > 0 && (
            <div style={{ height: 4, borderRadius: 2, background: colors.lineLight, marginBottom: 14, overflow: 'hidden' }}>
              <div style={{
                height: '100%', width: `${(countdown / CANCEL_WINDOW) * 100}%`,
                background: colors.critical, transition: 'width 0.25s linear',
              }} />
            </div>
          )}

          <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
            <Button variant="secondary" onClick={() => setResolved('home')}>I'm home</Button>
            <Button variant="danger" onClick={escalate}>I'm not home</Button>
          </div>
          <Button variant="ghost" onClick={() => setResolved('cancelled')}>Cancel — false alarm</Button>
        </Card>
      )}

      {resolved && (
        <Card style={{ marginBottom: 14, padding: 16 }}>
          <div style={{ fontSize: 14.5, fontWeight: 700, marginBottom: 5 }}>
            {resolved === 'home' && 'Stood down — you confirmed you\'re home'}
            {resolved === 'away' && 'Escalated — armed response notified'}
            {resolved === 'cancelled' && 'Cancelled as a false alarm'}
          </div>
          <p style={{ margin: '0 0 12px', fontSize: 12.5, color: colors.inkMid, lineHeight: 1.5 }}>
            {resolved === 'away'
              ? (alertError
                  ? `Could not reach the response provider: ${alertError}`
                  : 'A real alert was raised on the ops console with the address and detection time.')
              : 'Nothing was sent. The detection stays in your log only.'}
          </p>
          <Button variant="secondary" onClick={reset}>Reset demo</Button>
        </Card>
      )}

      {/* ---- escalation ladder ---- */}
      <Card style={{ padding: 16 }}>
        <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 4 }}>What happens if you don't respond</div>
        <p style={{ margin: '0 0 14px', fontSize: 12, color: colors.inkMid, lineHeight: 1.45 }}>
          Every rung is reversible until the one after it fires.
        </p>

        {LADDER.map((rung, i) => {
          const done = mode === 'active' && !resolved && i < reached;
          const current = mode === 'active' && !resolved && i === reached - 1;
          return (
            <div key={rung.title} style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', flexShrink: 0 }}>
                <span style={{
                  width: 20, height: 20, borderRadius: 10, display: 'grid', placeItems: 'center',
                  fontSize: 10, fontWeight: 700,
                  background: done ? colors.critical : colors.bg50,
                  color: done ? '#fff' : colors.inkLo,
                  border: `1px solid ${done ? colors.critical : colors.lineLight}`,
                  boxShadow: current ? `0 0 0 4px color-mix(in srgb, ${colors.critical} 18%, transparent)` : undefined,
                }}>{i + 1}</span>
                {i < LADDER.length - 1 && <span style={{ width: 1, flex: 1, minHeight: 26, background: done ? colors.critical : colors.lineLight }} />}
              </div>
              <div style={{ paddingBottom: 14, flex: 1 }}>
                <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 8 }}>
                  <span style={{ fontSize: 13.5, fontWeight: 650, color: done ? colors.inkHi : colors.inkMid }}>{rung.title}</span>
                  <span className="tabular-nums" style={{ fontSize: 11, color: colors.inkLo, flexShrink: 0 }}>
                    {rung.at === 0 ? 'immediately' : `+${rung.at}s`}
                  </span>
                </div>
                <div style={{ fontSize: 11.5, color: colors.inkLo, marginTop: 2 }}>{rung.detail}</div>
              </div>
            </div>
          );
        })}
      </Card>

      {mode === 'resting' && (
        <div style={{ marginTop: 14 }}>
          <Button variant="secondary" onClick={() => { setElapsed(0); setResolved(null); setMode('active'); }}>
            Run the detection demo
          </Button>
        </div>
      )}

      <MethodNote>
        Detection here is a scripted demo trigger, not an acoustic model — there is no
        audio classifier in this build. The response flow and timings are real.
      </MethodNote>
    </Screen>
  );
}

function Waveform({ active }: { active: boolean }) {
  // Deterministic bar heights: a random() waveform reshuffles on every render
  // and reads as noise rather than a signal.
  const bars = Array.from({ length: 34 }, (_, i) => 0.25 + Math.abs(Math.sin(i * 0.9)) * 0.75);
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 3, height: 46 }}>
      {bars.map((h, i) => (
        <span key={i} style={{
          flex: 1, height: `${(active ? h : h * 0.4) * 100}%`, borderRadius: 2,
          background: active ? colors.critical : colors.discovery,
          opacity: active ? 0.85 : 0.35,
          transition: `height 0.3s ease ${i * 8}ms, opacity 0.3s ease`,
        }} />
      ))}
    </div>
  );
}
