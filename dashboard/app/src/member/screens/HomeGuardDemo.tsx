/**
 * /demo — side-by-side view for recording demos.
 * Phone UI on the left, live backend log on the right.
 * No scrolling needed — everything visible at once on a laptop.
 */
import { useEffect, useRef } from 'react';
import { colors } from '../../theme/tokens';
import { LogProvider, useLog } from '../LogContext';
import HomeGuard from './HomeGuard';

// Reuses MemberShell's phone chrome exactly, without the router/nav overhead.
import { NavLink } from 'react-router-dom';

function PhoneChrome() {
  return (
    <div style={{
      width: 390, height: 720, borderRadius: 44, background: colors.bg50,
      color: colors.inkHi,
      boxShadow: '0 0 0 11px #0B1120, 0 0 0 12px rgba(255,255,255,0.09), 0 40px 90px rgba(15,23,42,0.34)',
      position: 'relative', overflow: 'hidden', display: 'flex', flexDirection: 'column',
      flexShrink: 0,
    }}>
      {/* dynamic-island */}
      <div style={{
        position: 'absolute', top: 11, left: '50%', transform: 'translateX(-50%)',
        width: 108, height: 30, borderRadius: 16, background: '#0B1120', zIndex: 30,
      }} />

      {/* status bar */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '10px 26px 2px', fontSize: 13, fontWeight: 600, letterSpacing: 0.2,
      }}>
        <span className="tabular-nums">
          {new Date().toLocaleTimeString('en-ZA', { hour: '2-digit', minute: '2-digit', hour12: false })}
        </span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 5, opacity: 0.9 }}>
          <svg width="17" height="11" viewBox="0 0 17 11" fill="currentColor">
            <rect x="0" y="7" width="3" height="4" rx="1" />
            <rect x="4.5" y="5" width="3" height="6" rx="1" />
            <rect x="9" y="2.5" width="3" height="8.5" rx="1" />
            <rect x="13.5" y="0" width="3" height="11" rx="1" />
          </svg>
          <svg width="25" height="12" viewBox="0 0 25 12" fill="none">
            <rect x="0.6" y="0.6" width="21" height="10.8" rx="3" stroke="currentColor" strokeOpacity="0.45" />
            <rect x="2.2" y="2.2" width="16" height="7.6" rx="1.8" fill="currentColor" />
            <path d="M23.4 4.2v3.6a2 2 0 0 0 0-3.6Z" fill="currentColor" fillOpacity="0.45" />
          </svg>
        </div>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', overflowX: 'hidden' }}>
        <HomeGuard />
      </div>

      {/* home indicator */}
      <div style={{
        position: 'absolute', bottom: 8, left: '50%', transform: 'translateX(-50%)',
        width: 134, height: 5, borderRadius: 3, background: 'rgba(15,23,42,0.26)', zIndex: 25,
      }} />
    </div>
  );
}

function LogPanel() {
  const { lines, clear } = useLog();
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [lines]);

  return (
    <div style={{
      flex: 1, display: 'flex', flexDirection: 'column',
      background: '#0d1117', borderRadius: 16,
      border: '1px solid #21262d',
      overflow: 'hidden', minWidth: 0,
    }}>
      {/* header */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '14px 20px 12px',
        borderBottom: '1px solid #21262d',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{
            width: 8, height: 8, borderRadius: '50%', background: '#3fb950', display: 'inline-block',
          }} />
          <span style={{
            fontFamily: 'ui-monospace, "Cascadia Code", monospace',
            fontSize: 12, fontWeight: 700, color: '#e6edf3', letterSpacing: 0.4,
          }}>
            BEACON SERVER — backend log
          </span>
        </div>
        {lines.length > 0 && (
          <button onClick={clear} style={{
            fontSize: 11, color: '#484f58', background: 'none', border: 'none',
            cursor: 'pointer', padding: 0, fontFamily: 'inherit',
          }}>
            clear
          </button>
        )}
      </div>

      {/* log lines */}
      <div ref={ref} style={{
        flex: 1, overflowY: 'auto', padding: '16px 20px',
        fontFamily: 'ui-monospace, "Cascadia Code", "Fira Mono", monospace',
        fontSize: 13, lineHeight: 1.7,
      }}>
        {lines.length === 0
          ? <span style={{ color: '#484f58' }}>Waiting for audio window…</span>
          : lines.map((line) => (
            <div key={line.id} style={{
              color: line.kind === 'alarm' ? '#f85149'
                   : line.kind === 'ok'    ? '#3fb950'
                   : line.kind === 'dim'   ? '#484f58'
                   : '#e6edf3',
              whiteSpace: 'pre',
            }}>
              {line.text}
            </div>
          ))
        }
      </div>
    </div>
  );
}

export default function HomeGuardDemo() {
  useEffect(() => { document.title = 'Home Guard — live demo'; }, []);

  return (
    <LogProvider>
      <div style={{
        minHeight: '100vh',
        background: `radial-gradient(1200px 600px at 50% -10%, #E8F1F9 0%, ${colors.bg50} 55%)`,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: 32, gap: 32, boxSizing: 'border-box',
      }}>
        <PhoneChrome />
        <LogPanel />
      </div>

      {/* back link */}
      <NavLink to="/home-guard" style={{
        position: 'fixed', top: 14, right: 18, fontSize: 11.5,
        color: colors.inkLo, textDecoration: 'none', opacity: 0.7,
      }}>
        ← normal view
      </NavLink>
    </LogProvider>
  );
}
