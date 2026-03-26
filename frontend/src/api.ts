import { apiUrl } from "./config";
import type { AppConfig, BootstrapResponse, Channel, LogsResponse } from "./types";

async function request<T>(input: string, init?: RequestInit): Promise<T> {
  const response = await fetch(apiUrl(input), {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `${response.status} ${response.statusText}`);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

export const api = {
  bootstrap(): Promise<BootstrapResponse> {
    return request("/api/bootstrap");
  },
  createChannel(payload: { username: string; platform: string; category: string; poll_interval_seconds: number; paused: boolean }) {
    return request<Channel>("/api/channels", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
  updateChannel(channelId: string, payload: Record<string, unknown>) {
    return request<Channel>(`/api/channels/${channelId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  },
  deleteChannel(channelId: string) {
    return request<{ ok: boolean }>(`/api/channels/${channelId}`, {
      method: "DELETE",
    });
  },
  pauseChannel(channelId: string) {
    return request<Channel>(`/api/channels/${channelId}/pause`, {
      method: "POST",
    });
  },
  resumeChannel(channelId: string) {
    return request<Channel>(`/api/channels/${channelId}/resume`, {
      method: "POST",
    });
  },
  loadLogs(params: URLSearchParams) {
    return request<LogsResponse>(`/api/logs?${params.toString()}`);
  },
  loadSettings() {
    return request<AppConfig>("/api/settings");
  },
  saveSettings(payload: AppConfig) {
    return request<AppConfig>("/api/settings", {
      method: "PUT",
      body: JSON.stringify(payload),
    });
  },
};
