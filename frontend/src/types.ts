export interface Channel {
  id: string;
  username: string;
  platform: string;
  url: string;
  category: string;
  enabled: boolean;
  paused: boolean;
  poll_interval_seconds: number;
  next_check_at: string | null;
  max_resolution: number | null;
  max_framerate: number | null;
  filename_pattern: string;
  created_at: number;
  last_checked_at: string | null;
  last_online_at: string | null;
  last_recorded_file: string | null;
  last_recorded_at: string | null;
  last_error: string | null;
  active_pid: number | null;
  status: string;
  status_label: string;
  last_recorded_filename: string;
  last_checked_display: string;
  last_online_display: string;
  last_recorded_display: string;
}

export interface AppConfig {
  host: string;
  port: number;
  timezone: string;
  recordings_dir: string;
  organized_dir: string;
  default_poll_interval_seconds: number;
  max_concurrent_probes: number;
  probe_rate_limit_seconds: number;
  probe_timeout_seconds: number;
  cookies_from_browser: string;
  yt_dlp_path: string;
  ffmpeg_path: string;
  delete_source_after_convert: boolean;
  keep_failed_source: boolean;
}

export interface EventItem {
  timestamp: string;
  timestamp_display: string;
  level: string;
  event_type: string;
  channel_id: string | null;
  channel_name: string | null;
  message: string;
  summary: string;
  tone: string;
  metadata: Record<string, unknown>;
}

export interface LogsResponse {
  items: EventItem[];
  event_types: string[];
  channels: Array<{ id: string; username: string }>;
  total: number;
  limit: number;
  offset: number;
  has_next: boolean;
}

export interface BootstrapResponse {
  channels: Channel[];
  categories: string[];
  all_channels_count: number;
  config: AppConfig;
  recent_events: EventItem[];
}

export interface ToastItem {
  id: number;
  tone: "success" | "error";
  message: string;
}
