import type { AppConfig, Channel, EventItem, ToastItem } from "../types";

export interface AppState {
  loaded: boolean;
  loading: boolean;
  channels: Channel[];
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
    categories: [],
    config: null,
    recentEvents: [],
    allChannelsCount: 0,
    toasts: [],
  };
}
