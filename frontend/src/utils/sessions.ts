import type { Channel, EventItem, SessionOverview, SessionSummary } from "../types";

const SOURCE_FAILURE_CATEGORIES = new Set([
  "source_unstable",
  "source_resolve_failed",
  "source_url_expired",
  "playlist_parse_failed",
]);

const AUTH_FAILURE_CATEGORIES = new Set([
  "auth_invalid",
  "auth_or_cookie_failed",
]);

type SessionChannel = {
  id: string;
  username: string;
  status?: string;
  active_pid?: number | null;
  last_checked_at?: string | null;
  last_online_at?: string | null;
  last_recorded_at?: string | null;
  last_recorded_filename?: string | null;
  last_error?: string | null;
  status_label?: string;
};

function asText(value: unknown): string | null {
  if (value === null || value === undefined) {
    return null;
  }
  if (typeof value === "string") {
    const trimmed = value.trim();
    return trimmed || null;
  }
  return String(value);
}

function metadataFromEvent(event: EventItem | undefined): Record<string, unknown> {
  return (event?.metadata ?? {}) as Record<string, unknown>;
}

function inferFailureCategory(
  event: EventItem | undefined,
  metadata: Record<string, unknown>,
): string | null {
  const explicit = asText(metadata.failure_category ?? event?.failure_category);
  if (explicit) {
    return explicit;
  }
  return event?.failure_category ?? null;
}

function inferPhase(
  channel: SessionChannel,
  event: EventItem | undefined,
  metadata: Record<string, unknown>,
): string {
  const explicit = asText(metadata.phase ?? metadata.session_phase ?? event?.phase ?? event?.session_phase);
  if (explicit) {
    return explicit;
  }
  if (channel.status === "recording") {
    return "recording";
  }
  if (channel.status === "paused") {
    return "paused";
  }
  if (channel.status === "error") {
    return "failed";
  }
  return "idle";
}

function inferStatus(channel: SessionChannel, event: EventItem | undefined, metadata: Record<string, unknown>): string {
  const explicit = asText(metadata.session_status ?? event?.session_status);
  if (explicit) {
    return explicit;
  }
  if (channel.status === "recording" || channel.active_pid) {
    return "recording";
  }
  if (channel.status === "error") {
    return "failed";
  }
  if (channel.status === "paused") {
    return "paused";
  }
  return "idle";
}

function isActiveSession(channel: SessionChannel, metadata: Record<string, unknown>): boolean {
  const explicit = metadata.is_active;
  if (typeof explicit === "boolean") {
    return explicit;
  }
  return channel.status === "recording" || channel.active_pid !== null;
}

function buildSessionId(channel: SessionChannel, event: EventItem | undefined, metadata: Record<string, unknown>): string {
  return (
    asText(metadata.session_id ?? metadata.recording_session_id ?? event?.session_id) ??
    `${channel.id}:${channel.active_pid ?? channel.last_recorded_at ?? channel.status}`
  );
}

function buildSessionFromChannel(channel: SessionChannel, event?: EventItem): SessionSummary {
  const metadata = metadataFromEvent(event);
  const failureCategory = inferFailureCategory(event, metadata);
  const phase = inferPhase(channel, event, metadata);
  const status = inferStatus(channel, event, metadata);
  const startedAt =
    asText(metadata.started_at ?? metadata.session_started_at) ??
    (event?.event_type === "recording_started" ? event.timestamp : null) ??
    channel.last_recorded_at ??
    channel.last_online_at ??
    null;
  const updatedAt =
    asText(metadata.updated_at ?? metadata.session_updated_at) ??
    event?.timestamp ??
    channel.last_checked_at ??
    null;
  const sourceStatus = asText(metadata.source_status ?? metadata.room_status);
  const sourceUrl = asText(metadata.source_url ?? metadata.resolved_source);
  const sourceCandidateId = asText(metadata.source_candidate_id ?? metadata.candidate_id);
  const sourcePathTail = asText(metadata.source_path_tail);
  const failureMessage =
    asText(metadata.failure_message ?? channel.last_error) ??
    (failureCategory ? event?.message ?? channel.last_error : null) ??
    null;
  const summary = event?.summary || failureMessage || channel.status_label || channel.status || "idle";
  const lastRecordedFilename = channel.last_recorded_filename === "-" ? null : channel.last_recorded_filename;

  return {
    id: buildSessionId(channel, event, metadata),
    channel_id: channel.id,
    channel_name: channel.username,
    status,
    phase,
    is_active: isActiveSession(channel, metadata),
    started_at: startedAt,
    updated_at: updatedAt,
    last_event_at: event?.timestamp ?? null,
    summary,
    failure_category: failureCategory,
    failure_message: failureMessage,
    source_status: sourceStatus,
    source_url: sourceUrl,
    source_candidate_id: sourceCandidateId,
    source_path_tail: sourcePathTail,
    active_pid: channel.active_pid ?? null,
    last_recorded_filename: lastRecordedFilename ?? null,
    last_error: channel.last_error ?? null,
    event_count: event ? 1 : 0,
  };
}

export function normalizeSessions(
  sessions: SessionSummary[] | undefined,
  channels: SessionChannel[],
  recentEvents: EventItem[],
): SessionSummary[] {
  if (sessions?.length) {
    return sortSessions(sessions);
  }
  return deriveSessionsFromChannels(channels, recentEvents);
}

export function deriveSessionsFromChannels(channels: SessionChannel[], recentEvents: EventItem[]): SessionSummary[] {
  const latestEvents = new Map<string, EventItem>();
  for (const event of recentEvents) {
    if (event.channel_id && !latestEvents.has(event.channel_id)) {
      latestEvents.set(event.channel_id, event);
    }
  }

  return sortSessions(channels.map((channel) => buildSessionFromChannel(channel, latestEvents.get(channel.id))));
}

export function deriveSessionOverview(sessions: SessionSummary[], recentSessions: SessionSummary[]): SessionOverview {
  return {
    total_count: sessions.length,
    active_count: sessions.filter((session) => session.is_active).length,
    recent_count: recentSessions.length,
    source_issue_count: sessions.filter((session) => {
      return Boolean(
        session.failure_category && SOURCE_FAILURE_CATEGORIES.has(session.failure_category) ||
          session.source_status === "error" ||
          session.source_status === "failed",
      );
    }).length,
    auth_issue_count: sessions.filter((session) => {
      return Boolean(session.failure_category && AUTH_FAILURE_CATEGORIES.has(session.failure_category));
    }).length,
  };
}

export function sortSessions(sessions: SessionSummary[]): SessionSummary[] {
  return [...sessions].sort((left, right) => {
    if (left.is_active !== right.is_active) {
      return left.is_active ? -1 : 1;
    }
    const updatedDiff = (right.updated_at ?? "").localeCompare(left.updated_at ?? "");
    if (updatedDiff !== 0) {
      return updatedDiff;
    }
    return (left.channel_name ?? "").localeCompare(right.channel_name ?? "");
  });
}

export function compactSessionLabel(session: SessionSummary): string {
  const bits = [session.phase];
  if (session.failure_category) {
    bits.push(session.failure_category.replaceAll("_", " "));
  } else if (session.source_status && session.source_status !== "public") {
    bits.push(session.source_status);
  }
  return bits.filter(Boolean).join(" · ");
}

export function sessionTone(session: SessionSummary): "good" | "neutral" | "bad" {
  if (session.is_active) {
    return "good";
  }
  if (session.failure_category || session.last_error) {
    return "bad";
  }
  return "neutral";
}
