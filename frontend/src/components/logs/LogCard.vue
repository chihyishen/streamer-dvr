<template>
  <article class="log-card" :class="event.tone">
    <div class="log-top">
      <div class="log-meta">
        <span class="level-pill" :class="event.level.toLowerCase()">{{ event.level }}</span>
        <span class="channel-pill">{{ event.channel_name || "-" }}</span>
      </div>
      <span class="muted">{{ event.timestamp_display }}</span>
    </div>

    <div class="summary">{{ event.summary }}</div>
    <div class="message" v-if="event.message !== event.summary">{{ event.message }}</div>

    <div class="metadata-row">
      <span class="meta-chip" v-if="event.failure_category">{{ event.failure_category }}</span>
      <span class="meta-chip" v-if="event.source_status">{{ event.source_status }}</span>
      <span class="meta-chip" v-if="event.source_candidate_id">{{ event.source_candidate_id }}</span>
      <span class="meta-chip" v-if="event.source_path_tail">{{ event.source_path_tail }}</span>
      <span class="meta-chip" v-if="event.metadata.return_code">code {{ event.metadata.return_code }}</span>
    </div>

    <details class="raw-output" v-if="event.metadata.raw_output || event.metadata.output">
      <summary>Raw Output</summary>
      <pre>{{ String(event.metadata.raw_output ?? event.metadata.output ?? "") }}</pre>
    </details>
  </article>
</template>

<script setup lang="ts">
import type { EventItem } from "../../types";

defineProps<{
  event: EventItem;
}>();
</script>

<style scoped>
.log-card {
  border: 1px solid var(--line);
  background: var(--panel);
  padding: 24px;
  display: grid;
  gap: 16px;
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-soft);
}

.log-card.bad {
  border-left: 4px solid var(--danger);
}

.log-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.log-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.level-pill,
.channel-pill,
.meta-chip {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  background: var(--bg-2);
  font-size: 11px;
  color: var(--text);
  font-weight: 600;
}

.level-pill.error {
  color: var(--danger);
  background: #fef2f2;
}

.summary {
  font-size: 16px;
  font-weight: 600;
  line-height: 1.4;
  color: var(--text);
  letter-spacing: -0.01em;
}

.message {
  color: var(--muted);
  line-height: 1.5;
  font-size: 14px;
}

.metadata-row {
  display: flex;
  gap: 8px;
}

.raw-output {
  border-top: 1px solid var(--line);
  padding-top: 16px;
}

.raw-output summary {
  cursor: pointer;
  color: var(--text);
  font-size: 12px;
  font-weight: 600;
}

.raw-output pre {
  margin: 12px 0 0;
  padding: 16px;
  border-radius: var(--radius-md);
  background: #171717;
  color: #fafafa;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 12px;
  line-height: 1.6;
  font-family: var(--mono);
}
</style>
