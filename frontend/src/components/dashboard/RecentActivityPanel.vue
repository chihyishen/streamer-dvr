<template>
  <section class="card activity-card">
    <div class="section-head">
      <div class="section-title activity-title display-face">Activity</div>
    </div>
    <div class="event-list">
      <article class="event-card" v-for="event in events" :key="`${event.timestamp}-${event.event_type}-${event.channel_id}`">
        <div class="event-top">
          <span class="muted small">{{ event.timestamp_display }}</span>
        </div>
        <div class="event-channel">{{ event.channel_name || "-" }}</div>
        <div class="event-summary">{{ event.summary }}</div>
      </article>
      <div class="activity-empty" v-if="!events.length">
        <div class="event-channel">No recent events yet</div>
        <div class="event-summary">Once probes and recording state changes start coming in, they will appear here in chronological order.</div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import type { EventItem } from "../../types";

defineProps<{
  events: EventItem[];
}>();
</script>

<style scoped>
.activity-card {
  padding: 0;
  position: sticky;
  top: 64px;
  background: transparent;
  max-height: calc(100vh - 160px);
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  border: none;
}

.section-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: baseline;
  margin-bottom: 24px;
}

.activity-title {
  font-size: 18px;
  line-height: 1;
  letter-spacing: -0.02em;
  font-weight: 700;
  color: var(--text);
}

.event-list {
  display: grid;
  gap: 20px;
  overflow: auto;
  align-content: start;
  padding-right: 8px;
}

.event-card {
  display: grid;
  gap: 4px;
  padding-bottom: 20px;
  border-bottom: 1px solid var(--line);
}

.event-card:last-child {
  border-bottom: none;
}

.activity-empty {
  padding: 32px 0;
  color: var(--muted);
  font-size: 14px;
  line-height: 1.5;
}

.event-top {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}

.event-summary {
  line-height: 1.4;
  font-size: 14px;
  color: var(--text);
  font-weight: 500;
}

.event-channel {
  font-size: 12px;
  font-weight: 600;
  color: var(--muted);
}

.muted.small {
  font-size: 11px;
  font-weight: 500;
}

@media (max-width: 1100px) {
  .activity-card {
    position: static;
    max-height: none;
    grid-template-rows: auto;
  }

  .event-list {
    overflow: visible;
    padding-right: 0;
  }
}
</style>
