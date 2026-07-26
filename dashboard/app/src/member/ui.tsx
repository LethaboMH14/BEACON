/**
 * Shared primitives for the member screens.
 *
 * These exist because the six delivered design screens each re-drew the same
 * card, the same chip, the same provenance footnote with slightly different
 * padding and radii. That drift is invisible in a spec sheet viewed one screen
 * at a time and glaring in an app you swipe through. One definition each.
 *
 * Radii follow design/PROMPT-PACK.md §6.1: 12 (chip) / 16 (control) / 20 (card)
 * / 28 (sheet) / 32 (hero).
 */
import type { CSSProperties, ReactNode } from 'react';
import { colors } from '../theme/tokens';

export const radii = { chip: 12, control: 16, card: 20, sheet: 28, hero: 32 } as const;

export function Screen({ children, pad = 20 }: { children: ReactNode; pad?: number }) {
  return <div style={{ padding: `4px ${pad}px 16px` }}>{children}</div>;
}

export function ScreenHeader({ title, subtitle, right, dark }: {
  title: string; subtitle?: string; right?: ReactNode; dark?: boolean;
}) {
  return (
    <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12, marginBottom: 16 }}>
      <div>
        <h1 style={{ margin: 0, fontSize: 25, fontWeight: 700, letterSpacing: -0.5, color: dark ? colors.textHi : colors.inkHi }}>{title}</h1>
        {subtitle && <p style={{ margin: '4px 0 0', fontSize: 13.5, color: dark ? colors.textMid : colors.inkMid }}>{subtitle}</p>}
      </div>
      {right}
    </div>
  );
}

export function Card({ children, style, onClick, dark, accent }: {
  children: ReactNode; style?: CSSProperties; onClick?: () => void; dark?: boolean; accent?: string;
}) {
  const Tag = onClick ? 'button' : 'div';
  return (
    <Tag
      onClick={onClick}
      style={{
        display: 'block', width: '100%', textAlign: 'left', font: 'inherit', color: 'inherit',
        background: dark ? colors.bg800 : colors.bg0,
        border: `1px solid ${accent ?? (dark ? colors.lineDark : colors.lineLight)}`,
        borderRadius: radii.card, padding: 16,
        boxShadow: dark ? colors.shadowCardDark : colors.shadowCard,
        cursor: onClick ? 'pointer' : undefined,
        ...style,
      }}
    >
      {children}
    </Tag>
  );
}

export function Chip({ children, tone = 'neutral', dark }: {
  children: ReactNode; tone?: 'neutral' | 'safe' | 'watch' | 'high' | 'critical' | 'brand' | 'live'; dark?: boolean;
}) {
  const map: Record<string, string> = {
    neutral: dark ? colors.textMid : colors.inkMid,
    safe: colors.safe, watch: colors.watch, high: colors.high,
    critical: colors.critical, brand: colors.discovery, live: colors.live,
  };
  const c = map[tone];
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 5,
      padding: '5px 10px', borderRadius: radii.chip, fontSize: 11.5, fontWeight: 600,
      color: c, background: `color-mix(in srgb, ${c} 12%, transparent)`,
      border: `1px solid color-mix(in srgb, ${c} 26%, transparent)`, whiteSpace: 'nowrap',
    }}>{children}</span>
  );
}

export function Button({ children, onClick, variant = 'primary', disabled, dark, style }: {
  children: ReactNode; onClick?: () => void;
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
  disabled?: boolean; dark?: boolean; style?: CSSProperties;
}) {
  const base: CSSProperties = {
    // 48 px tall per PROMPT-PACK §6.1 — thumb-reachable, not a desktop button.
    minHeight: 48, width: '100%', borderRadius: radii.control,
    fontSize: 15, fontWeight: 650, cursor: disabled ? 'not-allowed' : 'pointer',
    opacity: disabled ? 0.5 : 1, border: '1px solid transparent', padding: '0 18px',
  };
  const variants: Record<string, CSSProperties> = {
    primary: { background: colors.discovery, color: '#fff', boxShadow: '0 6px 18px rgba(11,95,165,0.28)' },
    secondary: {
      background: dark ? colors.bg700 : colors.bg0, color: dark ? colors.textHi : colors.inkHi,
      border: `1px solid ${dark ? colors.lineDark : colors.lineLight}`, boxShadow: dark ? undefined : colors.shadowCard,
    },
    ghost: { background: 'transparent', color: dark ? colors.textMid : colors.inkMid },
    danger: { background: colors.critical, color: '#fff', boxShadow: '0 6px 18px rgba(225,29,72,0.3)' },
  };
  return <button disabled={disabled} onClick={onClick} style={{ ...base, ...variants[variant], ...style }}>{children}</button>;
}

/**
 * Provenance / method footnote.
 *
 * Not decoration and not optional. Every number this app shows is derived from
 * suburb-level historical claims, and a member who reads a severity score as a
 * street-level prediction has been misled by us, not by themselves. The server
 * ships the caveat text with the data (see hotspots_geo.py) precisely so this
 * component can render the server's words rather than a copywriter's.
 */
export function MethodNote({ children, dark }: { children: ReactNode; dark?: boolean }) {
  return (
    <p style={{
      margin: '12px 2px 0', fontSize: 11.5, lineHeight: 1.5,
      color: dark ? colors.textLo : colors.inkLo,
    }}>{children}</p>
  );
}

/** For anything not backed by a live model yet. Never used on real detections. */
export function SimulatedTag() {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 5, padding: '4px 9px',
      borderRadius: radii.chip, fontSize: 10, fontWeight: 700, letterSpacing: 0.6,
      textTransform: 'uppercase', color: colors.stale,
      background: 'rgba(107,114,128,0.12)', border: '1px dashed rgba(107,114,128,0.4)',
    }}>Simulated</span>
  );
}

export function Skeleton({ h = 16, w = '100%', dark }: { h?: number; w?: number | string; dark?: boolean }) {
  return (
    <div style={{
      height: h, width: w, borderRadius: 8,
      background: dark ? 'rgba(255,255,255,0.06)' : 'rgba(15,23,42,0.06)',
      animation: 'beacon-pulse 1.4s ease-in-out infinite',
    }} />
  );
}

export function ErrorState({ message, onRetry, dark }: { message: string; onRetry?: () => void; dark?: boolean }) {
  return (
    <Card dark={dark} accent={`color-mix(in srgb, ${colors.critical} 30%, transparent)`}>
      <div style={{ fontSize: 14, fontWeight: 650, marginBottom: 4 }}>Couldn't load this</div>
      <div style={{ fontSize: 12.5, color: dark ? colors.textMid : colors.inkMid, marginBottom: onRetry ? 12 : 0 }}>{message}</div>
      {onRetry && <Button variant="secondary" dark={dark} onClick={onRetry}>Try again</Button>}
    </Card>
  );
}

export function money(v: number): string {
  return `R${Math.round(v).toLocaleString('en-ZA')}`;
}

export function hourLabel(h: number): string {
  return `${String(h).padStart(2, '0')}:00`;
}
