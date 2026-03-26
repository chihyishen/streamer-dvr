import type { Channel } from "../types";

export function displayChannelActivity(channel: Channel) {
  return channel.last_online_display !== "-" ? channel.last_online_display : channel.last_recorded_display;
}

export function platformBadge(platform: string) {
  if (platform === "chaturbate") {
    return "CB";
  }
  return platform.slice(0, 2).toUpperCase();
}

export function compareChannels(left: Channel, right: Channel) {
  const rankDiff = channelRank(left) - channelRank(right);
  if (rankDiff !== 0) {
    return rankDiff;
  }
  return normalizedSortName(left.username).localeCompare(normalizedSortName(right.username)) || left.username.localeCompare(right.username);
}

function channelRank(channel: Channel) {
  return channel.status_label === "recording" ? 0 : 1;
}

function normalizedSortName(username: string) {
  const normalized = username.toLowerCase().replace(/^[^a-z0-9]+/, "");
  return normalized || username.toLowerCase();
}
