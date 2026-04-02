<template>
  <section class="card activity-card">
    <div class="section-head">
      <div class="section-title activity-title display-face">Sessions</div>
      <div class="muted small">{{ props.sessions.length }} active/issues</div>
    </div>

    <div class="session-list">
      <article class="session-card" v-for="session in visibleSessions" :key="session.id">
        <div class="session-top">
          <div class="session-channel">{{ session.channel_name }}</div>
          <span class="session-state" :class="sessionTone(session)">{{ session.phase }}</span>
        </div>
        <div class="session-label">{{ compactSessionLabel(session) }}</div>
        <div class="session-summary">{{ session.summary }}</div>
        <div class="session-meta">
          <span class="meta-chip" v-if="session.status">{{ session.status }}</span>
          <span class="meta-chip" v-if="session.failure_category">{{ session.failure_category }}</span>
          <span class="meta-chip" v-if="session.source_status">{{ session.source_status }}</span>
          <span class="meta-chip" v-if="session.last_event_at">{{ session.last_event_at }}</span>
        </div>
      </article>
      <div class="activity-empty" v-if="!visibleSessions.length">
        <div class="event-channel">No sessions yet</div>
        <div class="event-summary">Once a streamer is probed or starts recording, the active and recent session snapshots will appear here.</div>
      </div>
    </div>

    <div class="events-head">
      <div class="section-title activity-title display-face">Recent events</div>
    </div>
    <div class="event-list">
      <article class="event-card" v-for="event in props.events" :key="`${event.timestamp}-${event.event_type}-${event.channel_id}`">
        <div class="event-top">
          <span class="muted small">{{ event.timestamp_display }}</span>
          <span class="event-phase" v-if="event.failure_category">{{ event.failure_category }}</span>
        </div>
        <div class="event-channel">{{ event.channel_name || "-" }}</div>
        <div class="event-summary">{{ event.summary }}</div>
        <div class="session-meta">
          <span class="meta-chip" v-if="event.source_status">{{ event.source_status }}</span>
          <span class="meta-chip" v-if="event.metadata.return_code">code {{ event.metadata.return_code }}</span>
        </div>
      </article>
      <div class="activity-empty" v-if="!props.events.length">
        <div class="event-channel">No recent errors</div>
        <div class="event-summary">Only refined errors are shown here. Expected unavailable states and internal session transitions are hidden.</div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { EventItem, SessionSummary } from "../../types";
import { compactSessionLabel, sessionTone } from "../../utils/sessions";

const props = defineProps<{
  sessions: SessionSummary[];
  events: EventItem[];
}>();

const visibleSessions = computed(() => props.sessions.slice(0, 6));
</script>

<style scoped>
.activity-card {
  padding: 0;
  position: sticky;
  top: 64px;
  background: transparent;
  max-height: calc(100vh - 160px);
  display: grid;
  grid-template-rows: auto auto minmax(0, 1fr);
  border: none;
  gap: 24px;
}

.section-head,
.events-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: baseline;
}

.activity-title {
  font-size: 18px;
  line-height: 1;
  letter-spacing: -0.02em;
  font-weight: 700;
  color: var(--text);
}

.session-list,
.event-list {
  display: grid;
  gap: 16px;
  overflow: auto;
  align-content: start;
  padding-right: 8px;
}

.session-card,
.event-card {
  display: grid;
  gap: 8px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--line);
}

.session-card {
  padding: 16px;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-soft);
}

.session-card:last-child,
.event-card:last-child {
  border-bottom: none;
}

.activity-empty {
  padding: 24px 0;
  color: var(--muted);
  font-size: 14px;
  line-height: 1.5;
}

.session-top,
.event-top {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 12px;
}

.session-channel,
.event-channel {
  font-size: 12px;
  font-weight: 600;
  color: var(--muted);
}

.session-summary,
.event-summary {
  line-height: 1.4;
  font-size: 14px;
  color: var(--text);
  font-weight: 500;
}

.session-label {
  font-size: 12px;
  color: var(--muted);
  font-weight: 600;
  line-height: 1.4;
  text-transform: capitalize;
}

.session-state,
.meta-chip,
.event-phase {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  background: var(--bg-2);
  color: var(--text);
  font-size: 11px;
  font-weight: 600;
  text-transform: capitalize;
}

.session-state.good {
  background: #ecfdf3;
  color: #166534;
}

.session-state.bad {
  background: #fef2f2;
  color: var(--danger);
}

.session-state.neutral {
  background: var(--bg-2);
  color: var(--muted);
}

.session-meta {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
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

  .session-list,
  .event-list {
    overflow: visible;
    padding-right: 0;
  }
}
</style>
