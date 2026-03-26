import type { EventItem } from "../types";

const RECORDING_EVENTS = new Set([
  "recording_started",
  "recording_completed",
  "recording_stopped",
  "convert_completed",
]);

const SOURCE_ISSUE_EVENTS = new Set([
  "PAGE_FETCH_FAILED",
  "PLAYLIST_PARSE_FAILED",
  "TIMEOUT",
]);

export function countErrorEvents(events: EventItem[]) {
  return events.filter((event) => event.level === "ERROR").length;
}

export function countRecordingEvents(events: EventItem[]) {
  return events.filter((event) => RECORDING_EVENTS.has(event.event_type)).length;
}

export function countSourceIssueEvents(events: EventItem[]) {
  return events.filter((event) => {
    if (SOURCE_ISSUE_EVENTS.has(event.event_type)) {
      return true;
    }
    const summary = String(event.summary).toLowerCase();
    return summary.includes("source") || summary.includes("playlist");
  }).length;
}
