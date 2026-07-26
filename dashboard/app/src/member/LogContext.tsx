/**
 * Shared log context so HomeGuard can push lines and the demo sidebar can
 * read them without prop-drilling through MemberShell.
 */
import { createContext, useContext, useRef, useState, useCallback, type ReactNode } from 'react';

export type LogKind = 'info' | 'alarm' | 'ok' | 'dim';
export type LogLine = { id: number; text: string; kind: LogKind };

interface LogCtx {
  lines: LogLine[];
  push: (text: string, kind?: LogKind) => void;
  clear: () => void;
}

const Ctx = createContext<LogCtx>({
  lines: [],
  push: () => {},
  clear: () => {},
});

export function LogProvider({ children }: { children: ReactNode }) {
  const [lines, setLines] = useState<LogLine[]>([]);
  const id = useRef(0);

  const push = useCallback((text: string, kind: LogKind = 'info') => {
    const next: LogLine = { id: ++id.current, text, kind };
    setLines((prev) => [...prev.slice(-49), next]);
  }, []);

  const clear = useCallback(() => setLines([]), []);

  return <Ctx.Provider value={{ lines, push, clear }}>{children}</Ctx.Provider>;
}

export function useLog() {
  return useContext(Ctx);
}
