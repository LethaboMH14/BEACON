/**
 * The member app's chrome: device frame, status bar, bottom tab bar.
 *
 * WHY A DEVICE FRAME IN A WEB APP
 * BEACON's member surface is a phone product being demoed on a laptop. Without
 * a frame, a 390 px column floating in a 1440 px browser reads as a broken
 * desktop site. With one, the same column reads as what it is. The frame is
 * presentation only — everything inside is a normal responsive layout, so this
 * ports to React Native or a real mobile browser by deleting this file.
 *
 * The delivered Claude Design screens were desktop showcase pages: each one laid
 * 2-4 phone frames side by side to display a screen's different states, with a
 * caption under each. That is the correct format for a design spec and the wrong
 * format for an app. Each ported screen here collapses its state frames into ONE
 * live screen whose state comes from data.
 */
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { colors } from '../theme/tokens';

const TABS = [
  { to: '/home', label: 'Home', icon: 'home' },
  { to: '/vision', label: 'Cam', icon: 'drive' },
  { to: '/map', label: 'Map', icon: 'map' },
  { to: '/assistant', label: 'Ask', icon: 'chat' },
  { to: '/rewards', label: 'Points', icon: 'star' },
] as const;

/** Inline so the shell has no asset dependency and no icon-font flash. */
function TabIcon({ name, active }: { name: string; active: boolean }) {
  const s = { width: 22, height: 22, fill: 'none', stroke: 'currentColor', strokeWidth: active ? 2.2 : 1.8, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const };
  switch (name) {
    case 'home': return <svg viewBox="0 0 24 24" {...s}><path d="M3 10.5 12 3l9 7.5" /><path d="M5 9.5V20a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V9.5" /></svg>;
    case 'drive': return <svg viewBox="0 0 24 24" {...s}><path d="M5 17h14M6.5 17V9.8L8 6h8l1.5 3.8V17" /><circle cx="8" cy="17" r="1.6" /><circle cx="16" cy="17" r="1.6" /></svg>;
    case 'map': return <svg viewBox="0 0 24 24" {...s}><path d="M9 4 3 6.5v13L9 17l6 2.5 6-2.5v-13L15 6.5 9 4Z" /><path d="M9 4v13M15 6.5v13" /></svg>;
    case 'chat': return <svg viewBox="0 0 24 24" {...s}><path d="M20 12a7.5 7.5 0 0 1-10.9 6.7L4 20l1.4-4.6A7.5 7.5 0 1 1 20 12Z" /></svg>;
    case 'star': return <svg viewBox="0 0 24 24" {...s}><path d="m12 4 2.4 5 5.6.7-4 3.9 1 5.4-5-2.7-5 2.7 1-5.4-4-3.9 5.6-.7L12 4Z" /></svg>;
    default: return null;
  }
}

function StatusBar() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    // The status-bar clock in the design was a {{ clock }} template hole. It is
    // a real clock here — a frozen 09:41 on a live demo is the kind of detail a
    // judge notices, and the fix costs one interval.
    const id = setInterval(() => setNow(new Date()), 15_000);
    return () => clearInterval(id);
  }, []);
  const time = now.toLocaleTimeString('en-ZA', { hour: '2-digit', minute: '2-digit', hour12: false });

  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: '10px 26px 2px', fontSize: 13, fontWeight: 600,
      color: 'inherit', letterSpacing: 0.2,
    }}>
      <span className="tabular-nums">{time}</span>
      <div style={{ display: 'flex', alignItems: 'center', gap: 5, opacity: 0.9 }}>
        <svg width="17" height="11" viewBox="0 0 17 11" fill="currentColor"><rect x="0" y="7" width="3" height="4" rx="1" /><rect x="4.5" y="5" width="3" height="6" rx="1" /><rect x="9" y="2.5" width="3" height="8.5" rx="1" /><rect x="13.5" y="0" width="3" height="11" rx="1" /></svg>
        <svg width="16" height="12" viewBox="0 0 16 12" fill="currentColor"><path d="M8 10.5 1 4.2a10 10 0 0 1 14 0L8 10.5Z" /></svg>
        <svg width="25" height="12" viewBox="0 0 25 12" fill="none"><rect x="0.6" y="0.6" width="21" height="10.8" rx="3" stroke="currentColor" strokeOpacity="0.45" /><rect x="2.2" y="2.2" width="16" height="7.6" rx="1.8" fill="currentColor" /><path d="M23.4 4.2v3.6a2 2 0 0 0 0-3.6Z" fill="currentColor" fillOpacity="0.45" /></svg>
      </div>
    </div>
  );
}

/**
 * Screens declare their own chrome colour rather than the shell guessing.
 * Live Drive is dark (it's a camera surface, and a light UI around a night-time
 * dashcam frame is unreadable); everything else is the light Discovery theme.
 */
const DARK_ROUTES = ['/drive', '/vision'];

/**
 * index.html carries the neutral product title because one build serves both the
 * member app and the ops console. The tab should still say which screen you're
 * on — a demo with six identically-titled tabs open is its own small disaster.
 */
const TITLES: Record<string, string> = {
  '/home': 'BEACON',
  '/drive': 'Cam · BEACON',
  '/vision': 'Vision lens · BEACON',
  '/map': 'Risk map · BEACON',
  '/route': 'Safest route · BEACON',
  '/home-guard': 'Home guard · BEACON',
  '/assistant': 'Ask BEACON',
  '/rewards': 'Vitality points · BEACON',
};

// Design size of the phone frame — a plain, fixed iPhone-sized column. No
// auto-scaling, no per-screen measurement: those were tried (2026-07-26) to
// solve short-screen whitespace and long-screen scrolling at once, but the
// scale-to-fit transform silently overrode native browser/OS zoom (pinch or
// Ctrl+scroll no longer changed anything visible), which is worse than either
// original problem during a live demo. Reverted to this on direct instruction.
const FRAME_W = 390;
const FRAME_H = 844;

export default function MemberShell() {
  const { pathname } = useLocation();
  const dark = DARK_ROUTES.some((r) => pathname.startsWith(r));

  useEffect(() => {
    document.title = TITLES[pathname] ?? 'BEACON';
  }, [pathname]);

  const frameBg = dark ? colors.bg900 : colors.bg50;
  const barBg = dark ? 'rgba(16,23,37,0.92)' : 'rgba(255,255,255,0.92)';
  const barLine = dark ? colors.lineDark : colors.lineLight;
  const idle = dark ? colors.textLo : colors.inkLo;
  const activeC = dark ? colors.beacon : colors.discovery;

  return (
    <div style={{
      minHeight: '100vh', background: `radial-gradient(1200px 600px at 50% -10%, #E8F1F9 0%, ${colors.bg50} 55%)`,
      display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '28px 16px',
    }}>
      <div style={{
        width: FRAME_W, height: FRAME_H, borderRadius: 44, background: frameBg,
        color: dark ? colors.textHi : colors.inkHi,
        boxShadow: '0 0 0 11px #0B1120, 0 0 0 12px rgba(255,255,255,0.09), 0 40px 90px rgba(15,23,42,0.34)',
        position: 'relative', overflow: 'hidden', display: 'flex', flexDirection: 'column',
        transition: 'background 0.25s ease, color 0.25s ease',
      }}>
        {/* dynamic-island notch */}
        <div style={{
          position: 'absolute', top: 11, left: '50%', transform: 'translateX(-50%)',
          width: 108, height: 30, borderRadius: 16, background: '#0B1120', zIndex: 30,
        }} />

        <StatusBar />

        <div style={{ flex: 1, overflowY: 'auto', overflowX: 'hidden', WebkitOverflowScrolling: 'touch' }}>
          <Outlet />
        </div>

        <nav style={{
          display: 'grid', gridTemplateColumns: `repeat(${TABS.length}, 1fr)`,
          background: barBg, backdropFilter: 'blur(18px)',
          borderTop: `1px solid ${barLine}`, padding: '8px 6px 22px', flexShrink: 0, zIndex: 20,
        }}>
          {TABS.map((t) => (
            <NavLink key={t.to} to={t.to} style={({ isActive }) => ({
              display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4,
              // 44 px is the accessible minimum touch target; the visual icon is
              // smaller but the tappable box must not be.
              minHeight: 44, justifyContent: 'center',
              textDecoration: 'none', fontSize: 10.5, fontWeight: isActive ? 700 : 500,
              color: isActive ? activeC : idle, transition: 'color 0.15s ease',
            })}>
              {({ isActive }) => (<><TabIcon name={t.icon} active={isActive} />{t.label}</>)}
            </NavLink>
          ))}
        </nav>

        {/* home indicator */}
        <div style={{
          position: 'absolute', bottom: 8, left: '50%', transform: 'translateX(-50%)',
          width: 134, height: 5, borderRadius: 3,
          background: dark ? 'rgba(255,255,255,0.32)' : 'rgba(15,23,42,0.26)', zIndex: 25,
        }} />
      </div>
    </div>
  );
}
