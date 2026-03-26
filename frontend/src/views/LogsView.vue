<template>
  <section class="logs-page">
    <LogsSummary
      :events-length="events.length"
      :error-count="errorCount"
      :recording-count="recordingCount"
      :source-issue-count="sourceIssueCount"
    />

    <div class="logs-content">
      <aside class="filters-column">
        <LogsFilters
          :draft="filters"
          :channels="channels"
          :event-types="eventTypes"
          :total="total"
          :offset="offset"
          :has-next="hasNext"
          :loading="loading"
          :active-quick-filter="activeQuickFilter"
          :filter-summary="filterSummary"
          :page-summary="pageSummary"
          @reset="resetFilters"
          @prev="prevPage"
          @next="nextPage"
          @quick-filter="applyQuickFilter"
        />
      </aside>

      <section class="log-list">
        <LogCard
          v-for="event in events"
          :key="`${event.timestamp}-${event.event_type}-${event.channel_id}`"
          :event="event"
        />
        <div class="empty" v-if="!events.length && !loading">
          <div class="empty-title display-face">Nothing matched this filter set</div>
          <p class="empty-body">Try resetting the filters or switching to a broader quick filter to restore the full event stream.</p>
        </div>
      </section>
    </div>
  </section>
</template>

<script setup lang="ts">
import LogCard from "../components/logs/LogCard.vue";
import LogsFilters from "../components/logs/LogsFilters.vue";
import LogsSummary from "../components/logs/LogsSummary.vue";
import { useLogsPage } from "../composables/useLogsPage";

const {
  loading,
  events,
  eventTypes,
  channels,
  activeQuickFilter,
  total,
  offset,
  hasNext,
  filters,
  errorCount,
  recordingCount,
  sourceIssueCount,
  filterSummary,
  pageSummary,
  resetFilters,
  applyQuickFilter,
  nextPage,
  prevPage,
} = useLogsPage();
</script>

<style scoped>
.logs-page {
  display: grid;
  gap: 48px;
}

.logs-content {
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr);
  gap: 64px;
  align-items: start;
}

.filters-column {
  min-width: 0;
}

.log-list {
  display: grid;
  gap: 16px;
  min-width: 0;
}

.empty {
  border: 1px solid var(--line);
  padding: 64px 32px;
  text-align: center;
  border-radius: var(--radius-xl);
  background: var(--panel);
  display: grid;
  justify-items: center;
}

.empty-title {
  font-size: 20px;
  line-height: 1.2;
  color: var(--text);
  font-weight: 700;
}

.empty-body {
  margin: 12px 0 0;
  max-width: 40ch;
  line-height: 1.6;
  font-size: 15px;
  color: var(--muted);
}

@media (max-width: 1100px) {
  .logs-content {
    grid-template-columns: 1fr;
    gap: 48px;
  }
}
</style>
