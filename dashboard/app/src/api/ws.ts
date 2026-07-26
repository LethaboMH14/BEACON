/**
 * WS client for /ws/ops (server/src/ws/router.py). Dev server proxies
 * /ws -> ws://localhost:8000 (see vite.config.ts).
 *
 * Real event names emitted by the server today (grep server/src for
 * ws_manager.broadcast_ops / "event":): connected, sighting.new,
 * sighting.batch, entity.candidate, entity.flagged, alert.new,
 * alert.acked, alert.cancelled. route.updated / forecast.updated are
 * documented in router.py's docstring but not wired yet — treat them
 * as coming soon, not live.
 */

import { wsUrl } from './base';

export type OpsEventName =
  | 'connected'
  | 'sighting.new'
  | 'sighting.batch'
  | 'entity.candidate'
  | 'entity.flagged'
  | 'alert.new'
  | 'alert.acked'
  | 'alert.cancelled'
  | 'route.updated'
  | 'forecast.updated'
  | 'echo';

export interface OpsEvent<T = unknown> {
  event: OpsEventName;
  data: T;
}

type Listener = (event: OpsEvent) => void;

export class OpsSocket {
  private socket: WebSocket | null = null;
  private listeners = new Set<Listener>();
  private reconnectMs = 1000;
  private closedByUser = false;

  connect(): void {
    this.closedByUser = false;
    this.socket = new WebSocket(wsUrl('/ws/ops'));

    this.socket.onmessage = (raw) => {
      let parsed: OpsEvent;
      try {
        parsed = JSON.parse(raw.data);
      } catch {
        return;
      }
      this.listeners.forEach((fn) => fn(parsed));
    };

    this.socket.onclose = () => {
      if (this.closedByUser) return;
      setTimeout(() => this.connect(), this.reconnectMs);
    };
  }

  on(fn: Listener): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  close(): void {
    this.closedByUser = true;
    this.socket?.close();
  }
}
