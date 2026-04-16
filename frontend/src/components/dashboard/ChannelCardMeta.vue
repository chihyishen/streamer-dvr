<template>
  <div class="channel-body">
    <!-- Row 1: Last file | Duration -->
    <div class="info-block">
      <div class="metric-label">Last file</div>
      <div class="primary-value mono truncate-file" :title="channel.last_recorded_filename">
        {{ channel.last_recorded_filename || 'None' }}
      </div>
    </div>
    <div class="info-block">
      <div class="metric-label">Duration</div>
      <div class="primary-value mono">{{ channel.last_recording_duration_display || '-' }}</div>
    </div>

    <!-- Row 2: Last activity | Last check -->
    <div class="info-block">
      <div class="metric-label">Last activity</div>
      <div class="primary-value">{{ displayChannelActivity(channel) }}</div>
    </div>
    <div class="info-block">
      <div class="metric-label">Last check</div>
      <div class="primary-value">{{ channel.last_checked_display }}</div>
    </div>

    <!-- Row 3 (Optional): Issue -->
    <div class="info-block full-width" v-if="channel.last_error">
      <div class="metric-label">Issue</div>
      <div class="issue-text">{{ channel.last_error }}</div>
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
  /* 左側分配 1.5 倍權重，右側 1 倍，約為 60/40 分配 */
  grid-template-columns: 1.5fr 1fr;
  column-gap: 32px;
  row-gap: 20px;
  padding-top: 24px;
  border-top: 1px solid var(--line);
}

.info-block {
  display: grid;
  gap: 6px;
  min-width: 0; /* 確保內容過長時能正確縮放 */
}

.metric-label {
  color: var(--muted);
  font-size: 11px; /* 稍微調小一點點，讓視覺更精緻 */
  font-weight: 600;
  text-transform: uppercase; /* 標籤轉大寫增加專業感 */
  letter-spacing: 0.05em;
}

.primary-value {
  line-height: 1.4;
  font-size: 14px;
  color: var(--text);
  font-weight: 500;
}

.truncate-file {
  word-break: break-all;
  display: -webkit-box;
  -webkit-line-clamp: 2; /* 最多顯示兩行 */
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.full-width {
  grid-column: 1 / -1;
  padding-top: 8px;
}

.issue-text {
  color: var(--danger);
  font-size: 13px;
  line-height: 1.5;
  word-break: break-word;
}

@media (max-width: 600px) {
  .channel-body {
    grid-template-columns: 1fr; /* 手機版改為單欄垂直排列 */
    gap: 16px;
  }
}
</style>
