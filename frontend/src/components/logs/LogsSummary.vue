<template>
  <section class="card logs-header">
    <div class="section-head">
      <div class="title-block">
        <div class="title display-face">Logs</div>
      </div>
    </div>

    <div class="overview-grid">
      <article class="overview-card">
        <div class="overview-label">Loaded</div>
        <div class="overview-value">{{ eventsLength }}</div>
      </article>
      <article class="overview-card">
        <div class="overview-label">Errors</div>
        <div class="overview-value">{{ errorCount }}</div>
      </article>
      <article class="overview-card">
        <div class="overview-label">Recording</div>
        <div class="overview-value">{{ recordingCount }}</div>
      </article>
      <article class="overview-card">
        <div class="overview-label">Source Issues</div>
        <div class="overview-value">{{ sourceIssueCount }}</div>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { RouterLink } from "vue-router";

defineProps<{
  eventsLength: number;
  errorCount: number;
  recordingCount: number;
  sourceIssueCount: number;
}>();
</script>

<style scoped>
.section-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-end;
  flex-wrap: wrap;
}

.title-block {
  display: grid;
  gap: 4px;
}

.title {
  font-size: clamp(2.2rem, 3.1vw, 3.4rem);
  letter-spacing: -0.06em;
  font-weight: 800;
  line-height: 1;
  text-transform: uppercase;
}

.logs-header {
  display: grid;
  gap: 32px;
  background: transparent;
  border: none;
  padding: 0;
}

.overview-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0;
  border-top: 1px solid var(--line-strong);
  border-left: 1px solid var(--line-strong);
}

.overview-card {
  border-right: 1px solid var(--line-strong);
  border-bottom: 1px solid var(--line-strong);
  background: var(--panel);
  padding: 24px;
  min-height: 120px;
  display: grid;
  align-content: end;
}

.overview-label {
  color: var(--muted);
  font-size: 11px;
  letter-spacing: 0.05em;
  font-weight: 700;
  text-transform: uppercase;
}

.overview-value {
  margin: 8px 0 0;
  font-size: clamp(2.4rem, 3vw, 3.2rem);
  font-weight: 800;
  letter-spacing: -0.06em;
  line-height: 1;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

@media (max-width: 900px) {
  .overview-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .overview-grid {
    grid-template-columns: 1fr;
  }
}
</style>
