import { defineStore } from "pinia";

import { api } from "../api";
import { connectDashboardStream, disconnectDashboardStream } from "./dashboard-stream";
import { createInitialState, type AppState } from "./app.types";
import { createToast, formatApiError } from "./toast-manager";
import type { AppConfig, BootstrapResponse, Channel, SessionOverview, SessionSummary } from "../types";
import { deriveSessionOverview, deriveSessionsFromChannels, normalizeSessions, sortSessions } from "../utils/sessions";

function emptySessionOverview(): SessionOverview {
  return {
    total_count: 0,
    active_count: 0,
    recent_count: 0,
    source_issue_count: 0,
    auth_issue_count: 0,
  };
}

export const useAppStore = defineStore("app", {
  state: (): AppState => createInitialState(),
  getters: {
    channelMap(state): Record<string, Channel> {
      return Object.fromEntries(state.channels.map((channel) => [channel.id, channel]));
    },
    sessionMap(state): Record<string, SessionSummary> {
      return Object.fromEntries(state.sessions.map((session) => [session.channel_id, session]));
    },
  },
  actions: {
    pushToast(tone: "success" | "error", message: string) {
      const toast = createToast(tone, message);
      this.toasts.push(toast);
      window.setTimeout(() => {
        this.dismissToast(toast.id);
      }, 2600);
    },
    dismissToast(id: number) {
      this.toasts = this.toasts.filter((toast) => toast.id !== id);
    },
    formatError(error: unknown) {
      return formatApiError(error);
    },
    applyBootstrap(payload: BootstrapResponse) {
      this.channels = payload.channels;
      this.categories = payload.categories;
      this.config = payload.config;
      this.recentEvents = payload.recent_events;
      this.allChannelsCount = payload.all_channels_count;

      const normalizedSessions = normalizeSessions(
        payload.sessions.length ? payload.sessions : [...payload.active_sessions, ...payload.recent_sessions],
        payload.channels,
        payload.recent_events,
      );
      this.sessions = normalizedSessions;
      this.activeSessions = sortSessions(payload.active_sessions.length ? payload.active_sessions : normalizedSessions.filter((session) => session.is_active));
      this.recentSessions = sortSessions(payload.recent_sessions.length ? payload.recent_sessions : normalizedSessions.slice(0, 8));
      this.sessionOverview = payload.session_overview.total_count
        ? payload.session_overview
        : deriveSessionOverview(normalizedSessions, this.recentSessions);
      this.loaded = true;
    },
    async refresh() {
      this.loading = true;
      try {
        const payload: BootstrapResponse = await api.bootstrap();
        this.applyBootstrap(payload);
      } finally {
        this.loading = false;
      }
    },
    connectDashboardStream() {
      connectDashboardStream((payload) => {
        this.applyBootstrap(payload);
      });
    },
    disconnectDashboardStream() {
      disconnectDashboardStream();
    },
    async createChannel(payload: { username: string; platform: string; category: string; poll_interval_seconds: number; paused: boolean }) {
      try {
        await api.createChannel(payload);
        await this.refresh();
        this.pushToast("success", "Streamer added");
      } catch (error) {
        this.pushToast("error", this.formatError(error));
        throw error;
      }
    },
    async updateChannel(channelId: string, payload: Record<string, unknown>) {
      try {
        await api.updateChannel(channelId, payload);
        await this.refresh();
        this.pushToast("success", "Streamer updated");
      } catch (error) {
        this.pushToast("error", this.formatError(error));
        throw error;
      }
    },
    async deleteChannel(channelId: string) {
      try {
        await api.deleteChannel(channelId);
        await this.refresh();
        this.pushToast("success", "Streamer removed");
      } catch (error) {
        this.pushToast("error", this.formatError(error));
        throw error;
      }
    },
    async pauseChannel(channelId: string) {
      try {
        await api.pauseChannel(channelId);
        await this.refresh();
        this.pushToast("success", "Paused");
      } catch (error) {
        this.pushToast("error", this.formatError(error));
        throw error;
      }
    },
    async resumeChannel(channelId: string) {
      try {
        await api.resumeChannel(channelId);
        await this.refresh();
        this.pushToast("success", "Resumed");
      } catch (error) {
        this.pushToast("error", this.formatError(error));
        throw error;
      }
    },
    async saveSettings(payload: AppConfig) {
      try {
        this.config = await api.saveSettings(payload);
        await this.refresh();
        this.pushToast("success", "Settings saved");
      } catch (error) {
        this.pushToast("error", this.formatError(error));
        throw error;
      }
    },
  },
});
