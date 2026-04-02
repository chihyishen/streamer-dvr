import type { EventItem, SessionSummary } from "../types";

const RECORDING_EVENTS = new Set([
  "convert_completed",
  "recording_completed",
  "recording_started",
  "recording_stopped",
]);

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

function eventFailureCategory(event: EventItem) {
  return asText(event.failure_category ?? event.metadata.failure_category);
}

export function countErrorEvents(events: EventItem[]) {
  return events.filter((event) => event.level === "ERROR").length;
}

export function countRecordingEvents(events: EventItem[]) {
  return events.filter((event) => RECORDING_EVENTS.has(event.event_type)).length;
}

export function countSourceIssueEvents(events: EventItem[]) {
  return events.filter((event) => {
    const failureCategory = eventFailureCategory(event);
    if (failureCategory && SOURCE_FAILURE_CATEGORIES.has(failureCategory)) {
      return true;
    }
    const summary = String(event.summary).toLowerCase();
    const message = String(event.message).toLowerCase();
    return summary.includes("source") || summary.includes("playlist") || message.includes("source") || message.includes("playlist");
  }).length;
}

export function countAuthIssueEvents(events: EventItem[]) {
  return events.filter((event) => {
    const failureCategory = eventFailureCategory(event);
    if (failureCategory && AUTH_FAILURE_CATEGORIES.has(failureCategory)) {
      return true;
    }
    const summary = String(event.summary).toLowerCase();
    const message = String(event.message).toLowerCase();
    return summary.includes("cookie") || summary.includes("auth") || message.includes("cookie") || message.includes("auth");
  }).length;
}

export function countSessionFailures(sessions: SessionSummary[]) {
  return sessions.filter((session) => Boolean(session.failure_category || session.last_error)).length;
}

export function countSourceIssueSessions(sessions: SessionSummary[]) {
  return sessions.filter((session) => {
    if (session.failure_category && SOURCE_FAILURE_CATEGORIES.has(session.failure_category)) {
      return true;
    }
    return session.source_status === "error" || session.source_status === "failed";
  }).length;
}

export function countAuthIssueSessions(sessions: SessionSummary[]) {
  return sessions.filter((session) => {
    return Boolean(session.failure_category && AUTH_FAILURE_CATEGORIES.has(session.failure_category));
  }).length;
}
