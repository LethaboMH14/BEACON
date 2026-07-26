/**
 * Home Guard — property audio monitoring and the escalation ladder.
 *
 * WHAT IS REAL HERE
 * Arming the mic runs a real acoustic transient detector on live microphone
 * audio (member/audio/glassBreak.ts) — real DSP, not a scripted trigger. It is
 * a detector rather than a trained classifier, so it fires on sharp
 * high-frequency transients generally; the footnote says exactly that. The
 * scripted trigger is kept as a fallback button so the ladder can still be
 * demonstrated in a loud room or with the mic blocked.
 *
 * The escalation ladder, the two-button response and the cancel window are the
 * real interaction design, which is what this screen is for.
 *
 * The design delivered this as three frames (resting / active detection /
 * escalation ladder). They are one screen in three states, and the state
 * advances on its own once triggered, which is the point: the ladder climbs
 * whether or not you respond, and you can stop it at any rung.
 */
import { useEffect, useRef, useState } from 'react';
import { colors } from '../../theme/tokens';
import { Button, Card, Chip, MethodNote, Screen, ScreenHeader, SimulatedTag, radii } from '../ui';
import { createAlert } from '../../api/member';
import { startGlassBreakDetector, THRESHOLDS, type AudioFrame, type DetectorHandle, type Sensitivity } from '../audio/glassBreak';

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

  const [micState, setMicState] = useState<'off' | 'starting' | 'live' | 'denied'>('off');
  const [micError, setMicError] = useState<string | null>(null);
  const [audio, setAudio] = useState<AudioFrame | null>(null);
  const [triggeredBy, setTriggeredBy] = useState<'mic' | 'demo' | null>(null);
  const [sensitivity, setSensitivity] = useState<Sensitivity>('normal');
  // Peak-hold. A transient is over in ~30ms; without holding the loudest recent
  // frame you cannot read off the screen how close a near-miss actually got.
  const [peak, setPeak] = useState<AudioFrame | null>(null);
  const detector = useRef<DetectorHandle | null>(null);
  // The detector callback fires at frame rate; without this it would re-enter
  // trigger() on every frame for as long as the transient lasts.
  const armed = useRef(false);

  function trip(source: 'mic' | 'demo') {
    setTriggeredBy(source);
    setElapsed(0);
    setResolved(null);
    setMode('active');
  }

  async function armMic() {
    setMicError(null);
    setMicState('starting');
    try {
      armed.current = true;
      setPeak(null);
      detector.current = await startGlassBreakDetector((frame) => {
        setAudio(frame);
        // Rank by onset, since that is what a transient is; a loud steady room
        // would otherwise permanently own the peak slot and tell you nothing.
        setPeak((p) => (!p || frame.onsetDb > p.onsetDb ? frame : p));
        if (frame.detected && armed.current) {
          armed.current = false;
          trip('mic');
        }
      }, sensitivity);
      setMicState('live');
    } catch (e) {
      setMicState('denied');
      setMicError(e instanceof Error ? e.message : 'Microphone unavailable');
    }
  }

  function disarmMic() {
    detector.current?.stop();
    detector.current = null;
    armed.current = false;
    setMicState('off');
    setAudio(null);
  }

  useEffect(() => () => detector.current?.stop(), []);

  // "I'm not home" is the one branch that should actually reach the ops
  // dashboard — a real Alert (POST /v1/alerts), so it shows up live on the
  // console with a real evidence-chain entry, not just a local UI state
  // change.
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
        right={micState === 'live' ? <Chip tone="safe">Mic live</Chip> : <SimulatedTag />}
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
              {resolved ? 'Stood down'
                : mode === 'active' ? 'Sound detected'
                : micState === 'live' ? 'Listening to your microphone'
                : micState === 'starting' ? 'Starting microphone…'
                : 'Not listening'}
            </span>
          </div>
          <Chip tone={mode === 'active' && !resolved ? 'critical' : micState === 'live' ? 'safe' : 'neutral'}>
            {mode === 'active' && !resolved ? 'Responding' : micState === 'live' ? 'Armed' : 'Disarmed'}
          </Chip>
        </div>

        <Waveform active={mode === 'active' && !resolved} level={audio?.levelDb ?? null} />

        {micState === 'live' && audio && (
          <div style={{ marginTop: 12, padding: 10, borderRadius: radii.chip, background: colors.bg50 }}>
            <div style={{ fontSize: 10.5, fontWeight: 700, color: colors.inkMid, marginBottom: 7, letterSpacing: 0.3 }}>
              ALL THREE MUST PASS AT ONCE
            </div>
            <Condition
              label="Loud enough"
              now={`${audio.levelDb.toFixed(0)} dB`}
              need={`> ${THRESHOLDS[sensitivity].levelFloorDb} dB`}
              ok={audio.passed.loud}
            />
            <Condition
              label="High-frequency"
              now={`${(audio.hfRatio * 100).toFixed(0)}%`}
              need={`> ${(THRESHOLDS[sensitivity].hfRatioMin * 100).toFixed(0)}%`}
              ok={audio.passed.highFreq}
            />
            <Condition
              label="Sudden onset"
              now={`${audio.onsetDb > 0 ? '+' : ''}${audio.onsetDb.toFixed(0)} dB`}
              need={`> +${THRESHOLDS[sensitivity].onsetDb} dB`}
              ok={audio.passed.onset}
            />
            {peak && (
              <div className="tabular-nums" style={{ marginTop: 8, paddingTop: 8, borderTop: `1px solid ${colors.lineLight}`, fontSize: 10.5, color: colors.inkLo }}>
                Loudest so far: {(peak.hfRatio * 100).toFixed(0)}% high-freq, +{peak.onsetDb.toFixed(0)} dB onset
              </div>
            )}
          </div>
        )}

        <div style={{ display: 'flex', gap: 8, marginTop: 14, alignItems: 'center', flexWrap: 'wrap' }}>
          {micState === 'live'
            ? <Button variant="secondary" onClick={disarmMic}>Stop listening</Button>
            : <Button onClick={armMic} disabled={micState === 'starting'}>
                {micState === 'starting' ? 'Starting…' : 'Arm microphone'}
              </Button>}
          {micState !== 'live' && (
            <button
              onClick={() => setSensitivity((s) => (s === 'normal' ? 'high' : 'normal'))}
              style={{
                minHeight: 44, padding: '0 13px', borderRadius: radii.control, cursor: 'pointer',
                border: `1px solid ${colors.lineLight}`, background: colors.bg0,
                fontSize: 12.5, color: colors.inkMid, fontFamily: 'inherit',
              }}
            >
              Sensitivity: {sensitivity === 'high' ? 'high' : 'normal'}
            </button>
          )}
        </div>

        {micState !== 'live' && sensitivity === 'high' && (
          <p style={{ margin: '8px 0 0', fontSize: 11, color: colors.inkLo, lineHeight: 1.45 }}>
            High sensitivity is for testing with a sound played through speakers — small
            drivers lose the top octaves and soften the attack, so real thresholds would
            unfairly reject a genuine recording.
          </p>
        )}

        {micError && (
          <p style={{ margin: '10px 0 0', fontSize: 11.5, color: colors.critical, lineHeight: 1.45 }}>
            Microphone unavailable: {micError}. The scripted demo trigger below still works.
          </p>
        )}

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
          <Button variant="secondary" onClick={() => trip('demo')}>
            Run the detection demo instead
          </Button>
        </div>
      )}

      <MethodNote>
        {triggeredBy === 'demo'
          ? 'This run was started by the scripted demo button, not by the microphone.'
          : 'Arming the microphone runs real signal processing on live audio: it fires on a sharp broadband onset with most of its energy above 3.2 kHz, confirmed across consecutive frames. It is a transient detector, not a trained classifier — it cannot tell breaking glass from another sharp high-frequency sound like a dropped plate. Audio is analysed and discarded; nothing is recorded or uploaded.'}
      </MethodNote>
    </Screen>
  );
}

/** One of the three detector conditions, with its live value and its threshold. */
function Condition({ label, now, need, ok }: { label: string; now: string; need: string; ok: boolean }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '3px 0', fontSize: 11.5 }}>
      <span style={{
        width: 14, height: 14, borderRadius: 7, flexShrink: 0, display: 'grid', placeItems: 'center',
        fontSize: 9, fontWeight: 700, color: '#fff',
        background: ok ? colors.safe : colors.lineLight,
      }}>{ok ? '✓' : ''}</span>
      <span style={{ color: ok ? colors.inkHi : colors.inkMid, fontWeight: ok ? 650 : 400 }}>{label}</span>
      <span className="tabular-nums" style={{ marginLeft: 'auto', color: colors.inkHi, fontWeight: 650 }}>{now}</span>
      <span className="tabular-nums" style={{ color: colors.inkLo, minWidth: 62, textAlign: 'right' }}>needs {need}</span>
    </div>
  );
}

function Waveform({ active, level }: { active: boolean; level: number | null }) {
  // Deterministic bar shape: a random() waveform reshuffles on every render and
  // reads as noise rather than a signal. When the mic is live the shape is
  // scaled by the real measured level, so the bars move with the actual room.
  const bars = Array.from({ length: 34 }, (_, i) => 0.25 + Math.abs(Math.sin(i * 0.9)) * 0.75);
  // -60 dB (near silence) to -10 dB (loud) mapped onto 0..1.
  const gain = level === null ? null : Math.min(1, Math.max(0.05, (level + 60) / 50));
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 3, height: 46 }}>
      {bars.map((h, i) => (
        <span key={i} style={{
          flex: 1,
          height: `${(gain !== null ? h * gain : active ? h : h * 0.4) * 100}%`,
          borderRadius: 2,
          background: active ? colors.critical : colors.discovery,
          opacity: active ? 0.85 : gain !== null ? 0.7 : 0.35,
          // No transition while live — smoothing would hide the transient the
          // detector is firing on, and the meter should show what it saw.
          transition: gain !== null ? 'none' : `height 0.3s ease ${i * 8}ms, opacity 0.3s ease`,
        }} />
      ))}
    </div>
  );
}
