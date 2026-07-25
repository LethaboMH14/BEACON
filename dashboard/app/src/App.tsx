import { useEffect, useState } from 'react';
import { colors, type RiskLevel, riskColor } from './theme/tokens';
import { getHealth, getHotspots, type HotspotEntry } from './api/client';
import { OpsSocket, type OpsEvent } from './api/ws';
import CommunityOperationsCentre from './screens/CommunityOperationsCentre';
import VerifyQueue from './screens/VerifyQueue';
import LiveAICamera from './screens/LiveAICamera';
import CrimeIntelligence from './screens/CrimeIntelligence';

function riskLevelFor(score: number): RiskLevel {
  if (score >= 0.75) return 'critical';
  if (score >= 0.5) return 'high';
  if (score >= 0.25) return 'watch';
  return 'safe';
}

function App() {
  const [screen, setScreen] = useState<'scaffold' | 'ops-centre' | 'verify-queue' | 'live-camera' | 'crime-intel'>('ops-centre');
  const [handoffEntityId, setHandoffEntityId] = useState<string | null>(null);
  const [health, setHealth] = useState<'checking' | 'up' | 'down'>('checking');
  const [hotspots, setHotspots] = useState<HotspotEntry[]>([]);
  const [events, setEvents] = useState<OpsEvent[]>([]);

  useEffect(() => {
    getHealth()
      .then(() => setHealth('up'))
      .catch(() => setHealth('down'));

    getHotspots(undefined, 8)
      .then((res) => setHotspots(res.hotspots))
      .catch(() => setHotspots([]));

    const socket = new OpsSocket();
    const unsubscribe = socket.on((event) => {
      setEvents((prev) => [event, ...prev].slice(0, 20));
    });
    socket.connect();

    return () => {
      unsubscribe();
      socket.close();
    };
  }, []);

  const toggle = (
    <div style={{ position: 'fixed', top: 8, right: 8, zIndex: 1000, display: 'flex', gap: 6 }}>
      {([
        ['scaffold', 'Wiring scaffold'],
        ['ops-centre', 'Ops Centre'],
        ['verify-queue', 'Verify Queue'],
        ['live-camera', 'Live AI Camera'],
        ['crime-intel', 'Crime Intelligence'],
      ] as const).map(([key, label]) => (
        <button key={key} onClick={() => setScreen(key)} style={{
          background: screen === key ? colors.beacon : colors.bg700,
          color: screen === key ? colors.bg900 : colors.textHi,
          border: `1px solid ${colors.lineDark}`, borderRadius: 8, padding: '6px 10px', fontSize: 11, cursor: 'pointer',
          fontWeight: screen === key ? 700 : 400,
        }}>
          {label}
        </button>
      ))}
    </div>
  );

  if (screen === 'ops-centre') {
    return (
      <>
        {toggle}
        <CommunityOperationsCentre />
      </>
    );
  }

  if (screen === 'verify-queue') {
    return (
      <>
        {toggle}
        <VerifyQueue initialEntityId={handoffEntityId} />
      </>
    );
  }

  if (screen === 'live-camera') {
    return (
      <>
        {toggle}
        <LiveAICamera onOpenVerifyQueue={(entityId) => { setHandoffEntityId(entityId); setScreen('verify-queue'); }} />
      </>
    );
  }

  if (screen === 'crime-intel') {
    return (
      <>
        {toggle}
        <CrimeIntelligence />
      </>
    );
  }

  return (
    <div
      style={{
        minHeight: '100vh',
        background: colors.bg50,
        color: colors.inkHi,
        fontFamily: 'inherit',
      }}
    >
      {toggle}
      <header
        style={{
          background: colors.bg900,
          color: colors.textHi,
          padding: '16px 24px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span
            style={{
              width: 10,
              height: 10,
              borderRadius: '50%',
              display: 'inline-block',
              background: health === 'up' ? colors.live : colors.critical,
            }}
          />
          <strong>BEACON — dashboard scaffold</strong>
        </div>
        <span className="tabular-nums" style={{ color: colors.textMid, fontSize: 13 }}>
          server: {health}
        </span>
      </header>

      <main style={{ padding: 24, display: 'grid', gap: 24, gridTemplateColumns: '1fr 1fr' }}>
        <section
          style={{
            background: colors.bg0,
            border: `1px solid ${colors.lineLight}`,
            borderRadius: 12,
            padding: 16,
          }}
        >
          <h2 style={{ marginTop: 0, fontSize: 15, color: colors.inkMid }}>
            Hotspots (GET /v1/hotspots)
          </h2>
          {hotspots.length === 0 && (
            <p style={{ color: colors.inkLo }}>No hotspots yet — waiting on real risk-cell data.</p>
          )}
          <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'grid', gap: 8 }}>
            {hotspots.map((h) => {
              const level = riskLevelFor(h.risk_score);
              return (
                <li
                  key={h.hex_id}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    padding: '8px 12px',
                    borderRadius: 8,
                    background: colors.bg50,
                  }}
                >
                  <span className="tabular-nums" style={{ fontSize: 13 }}>{h.hex_id}</span>
                  <span
                    className="tabular-nums"
                    style={{
                      color: riskColor[level],
                      fontWeight: 600,
                      fontSize: 13,
                    }}
                  >
                    {h.risk_score.toFixed(2)} · {h.label}
                  </span>
                </li>
              );
            })}
          </ul>
        </section>

        <section
          style={{
            background: colors.bg0,
            border: `1px solid ${colors.lineLight}`,
            borderRadius: 12,
            padding: 16,
          }}
        >
          <h2 style={{ marginTop: 0, fontSize: 15, color: colors.inkMid }}>
            Live events (/ws/ops)
          </h2>
          {events.length === 0 && (
            <p style={{ color: colors.inkLo }}>Waiting for events…</p>
          )}
          <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'grid', gap: 6 }}>
            {events.map((e, i) => (
              <li key={i} style={{ fontSize: 12, color: colors.inkMid }}>
                <code>{e.event}</code>
              </li>
            ))}
          </ul>
        </section>
      </main>
    </div>
  );
}

export default App;
