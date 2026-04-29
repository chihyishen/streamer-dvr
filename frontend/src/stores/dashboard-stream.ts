import { apiUrl } from "../config";
import type { BootstrapResponse } from "../types";

const RECONNECT_INITIAL_DELAY_MS = 1500;
const RECONNECT_MAX_DELAY_MS = 30000;

let dashboardStream: EventSource | null = null;
let reconnectTimer: number | null = null;
let reconnectAttempt = 0;
const listeners = new Set<(payload: BootstrapResponse) => void>();

function clearReconnectTimer() {
  if (reconnectTimer !== null) {
    window.clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
}

function nextReconnectDelay() {
  const delay = RECONNECT_INITIAL_DELAY_MS * Math.pow(2, reconnectAttempt);
  reconnectAttempt += 1;
  return Math.min(delay, RECONNECT_MAX_DELAY_MS);
}

function ensureDashboardStream() {
  if (dashboardStream) {
    return;
  }

  dashboardStream = new EventSource(apiUrl("/api/bootstrap/stream"));
  dashboardStream.onmessage = (event) => {
    reconnectAttempt = 0;
    const payload = JSON.parse(event.data) as BootstrapResponse;
    listeners.forEach((listener) => listener(payload));
  };
  dashboardStream.onerror = () => {
    dashboardStream?.close();
    dashboardStream = null;
    if (!listeners.size || reconnectTimer !== null) {
      return;
    }
    reconnectTimer = window.setTimeout(() => {
      reconnectTimer = null;
      if (listeners.size) {
        ensureDashboardStream();
      }
    }, nextReconnectDelay());
  };
}

export function connectDashboardStream(onPayload: (payload: BootstrapResponse) => void) {
  listeners.add(onPayload);
  clearReconnectTimer();
  reconnectAttempt = 0;
  ensureDashboardStream();
}

export function disconnectDashboardStream() {
  listeners.clear();
  clearReconnectTimer();
  reconnectAttempt = 0;
  if (dashboardStream) {
    dashboardStream.close();
    dashboardStream = null;
  }
}
