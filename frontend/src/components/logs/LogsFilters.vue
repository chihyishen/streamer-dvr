<template>
  <section class="card filter-card">
    <div class="section-head">
      <div class="header-top">
        <div class="panel-title">Filters</div>
        <button class="button ghost reset-btn" @click="$emit('reset')" :disabled="loading">Reset</button>
      </div>
      
      <div class="header-nav">
        <div class="nav-group">
          <button class="nav-btn" @click="$emit('prev')" :disabled="loading || offset === 0" title="Previous Page">
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" width="14"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M15 19l-7-7 7-7" /></svg>
          </button>
          <span class="nav-info">{{ pageSummary }}</span>
          <button class="nav-btn" @click="$emit('next')" :disabled="loading || !hasNext" title="Next Page">
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" width="14"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M9 5l7 7-7 7" /></svg>
          </button>
        </div>
      </div>
    </div>

    <div class="quick-filters">
      <button class="chip-action" :class="{ active: activeQuickFilter === 'all' }" @click="$emit('quickFilter', 'all')">All</button>
      <button class="chip-action" :class="{ active: activeQuickFilter === 'errors' }" @click="$emit('quickFilter', 'errors')">Errors</button>
      <button class="chip-action" :class="{ active: activeQuickFilter === 'recording' }" @click="$emit('quickFilter', 'recording')">Recording</button>
      <button class="chip-action" :class="{ active: activeQuickFilter === 'source' }" @click="$emit('quickFilter', 'source')">Source</button>
    </div>

    <form class="filters-form" @submit.prevent>
      <div class="field-group">
        <label class="field-label">Streamer</label>
        <select class="select-input" v-model="draft.channel_id">
          <option value="">All streamers</option>
          <option v-for="channel in channels" :key="channel.id" :value="channel.id">{{ channel.username }}</option>
        </select>
      </div>
      <div class="field-group">
        <label class="field-label">Event Type</label>
        <select class="select-input" v-model="draft.event_type">
          <option value="">All event types</option>
          <option v-for="eventType in eventTypes" :key="eventType" :value="eventType">{{ eventType }}</option>
        </select>
      </div>
      <div class="field-group">
        <label class="field-label">Level</label>
        <select class="select-input" v-model="draft.level">
          <option value="">All levels</option>
          <option value="INFO">INFO</option>
          <option value="ERROR">ERROR</option>
        </select>
      </div>
      <div class="field-group">
        <label class="field-label">Limit</label>
        <input class="text-input" v-model.number="draft.limit" type="number" min="20" max="1000" />
      </div>
      <div class="filter-status" v-if="loading">
        <div class="muted small">Refreshing logs...</div>
      </div>
    </form>
  </section>
</template>

<script setup lang="ts">
defineProps<{
  draft: { channel_id: string; event_type: string; level: string; limit: number };
  channels: Array<{ id: string; username: string }>;
  eventTypes: string[];
  total: number;
  offset: number;
  hasNext: boolean;
  loading: boolean;
  activeQuickFilter: "all" | "errors" | "recording" | "source";
  filterSummary: string;
  pageSummary: string;
}>();

defineEmits<{
  reset: [];
  prev: [];
  next: [];
  quickFilter: [mode: "all" | "errors" | "recording" | "source"];
}>();
</script>

<style scoped>
.section-head {
  display: grid;
  gap: 16px;
  margin-bottom: 24px;
}

.header-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.panel-title {
  font-size: 13px;
  letter-spacing: 0.05em;
  font-weight: 700;
  color: var(--text);
  text-transform: uppercase;
}

.reset-btn {
  padding: 4px 10px;
  font-size: 11px;
  text-transform: uppercase;
  font-weight: 700;
}

.header-nav {
  display: flex;
  width: 100%;
}

.nav-group {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--bg-2);
  padding: 2px;
  border-radius: var(--radius-md);
  border: 1px solid var(--line);
  width: 100%;
}

.nav-btn {
  border: none;
  background: transparent;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--text);
  border-radius: var(--radius-sm);
  transition: all 200ms ease;
}

.nav-btn:hover:not(:disabled) {
  background: var(--panel);
  box-shadow: var(--shadow-soft);
}

.nav-btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.nav-info {
  font-size: 11px;
  font-weight: 600;
  color: var(--muted);
  letter-spacing: -0.01em;
  padding: 0 8px;
}

.filter-card {
  display: grid;
  gap: 20px;
  position: sticky;
  top: 64px;
}

.quick-filters {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
}

.filters-form {
  display: grid;
  gap: 14px;
}

.chip-action {
  border: 1px solid var(--line);
  border-radius: var(--radius-md);
  padding: 6px 10px;
  background: var(--panel);
  color: var(--muted);
  cursor: pointer;
  font-weight: 600;
  font-size: 11px;
  transition: all 200ms ease;
}

.chip-action.active {
  background: var(--text);
  color: var(--bg);
  border-color: var(--text);
}

.chip-action:hover:not(.active) {
  border-color: var(--text);
  color: var(--text);
}

.filter-status {
  padding-top: 4px;
}

.small {
  font-size: 11px;
  color: var(--muted);
  font-weight: 500;
}

@media (max-width: 1100px) {
  .filter-card {
    position: static;
  }
}
</style>
