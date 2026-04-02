import type { AppConfig, Channel, EventItem, SessionOverview, SessionSummary, ToastItem } from "../types";

export interface AppState {
  loaded: boolean;
  loading: boolean;
  channels: Channel[];
  sessions: SessionSummary[];
  activeSessions: SessionSummary[];
  recentSessions: SessionSummary[];
  sessionOverview: SessionOverview;
  categories: string[];
  config: AppConfig | null;
  recentEvents: EventItem[];
  allChannelsCount: number;
  toasts: ToastItem[];
}

export function createInitialState(): AppState {
  return {
    loaded: false,
    loading: false,
    channels: [],
    sessions: [],
    activeSessions: [],
    recentSessions: [],
    sessionOverview: {
      total_count: 0,
      active_count: 0,
      recent_count: 0,
      source_issue_count: 0,
      auth_issue_count: 0,
    },
    categories: [],
    config: null,
    recentEvents: [],
    allChannelsCount: 0,
    toasts: [],
  };
}
