import { apiUrl } from "../config";
import type { BootstrapResponse } from "../types";

let dashboardStream: EventSource | null = null;
let reconnectTimer: number | null = null;
const listeners = new Set<(payload: BootstrapResponse) => void>();

function clearReconnectTimer() {
  if (reconnectTimer !== null) {
    window.clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
}

function ensureDashboardStream() {
  if (dashboardStream) {
    return;
  }

  dashboardStream = new EventSource(apiUrl("/api/bootstrap/stream"));
  dashboardStream.onmessage = (event) => {
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
    }, 1500);
  };
}

export function connectDashboardStream(onPayload: (payload: BootstrapResponse) => void) {
  listeners.add(onPayload);
  clearReconnectTimer();
  ensureDashboardStream();
}

export function disconnectDashboardStream() {
  listeners.clear();
  clearReconnectTimer();
  if (dashboardStream) {
    dashboardStream.close();
    dashboardStream = null;
  }
}
