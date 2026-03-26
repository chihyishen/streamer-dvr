<template>
  <div class="channel-body">
    <div class="channel-primary">
      <div class="info-block">
        <div class="metric-label">Last file</div>
        <div class="primary-value mono">{{ channel.last_recorded_filename }}</div>
      </div>
    </div>
    <div class="channel-secondary">
      <div class="info-inline">
        <span class="metric-label">Last activity</span>
        <span>{{ displayChannelActivity(channel) }}</span>
      </div>
      <div class="info-inline">
        <span class="metric-label">Last check</span>
        <span>{{ channel.last_checked_display }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { Channel } from "../../types";
import { displayChannelActivity } from "../../utils/channel";

defineProps<{
  channel: Channel;
}>();
</script>

<style scoped>
.channel-body {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(200px, 0.8fr);
  gap: 32px;
  padding-top: 24px;
  border-top: 1px solid var(--line);
}

.channel-primary,
.channel-secondary {
  display: grid;
  gap: 16px;
}

.info-block {
  display: grid;
  gap: 6px;
}

.primary-value {
  line-height: 1.4;
  word-break: break-word;
  font-size: 14px;
  color: var(--text);
  font-weight: 500;
}

.info-inline {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 12px;
  font-size: 13px;
}

.metric-label {
  color: var(--muted);
  font-size: 12px;
  font-weight: 600;
}

@media (max-width: 1100px) {
  .channel-body {
    grid-template-columns: 1fr;
    gap: 24px;
  }
}
</style>
