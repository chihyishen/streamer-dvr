<template>
  <section class="card top-summary">
    <div class="summary-head">
      <div class="summary-copy">
        <div class="summary-title display-face">Recorder status</div>
      </div>
      <div class="toolbar top-actions">
        <div class="refresh-note" v-if="isRefreshing">Refreshing...</div>
        <button class="button" @click="$emit('add')">Add streamer</button>
        <button class="button ghost" @click="$emit('settings')">Settings</button>
      </div>
    </div>
    <div class="overview-grid">
      <article class="overview-tile primary-tile">
        <strong>{{ allChannelsCount }}</strong>
        <span class="overview-detail">Channels</span>
      </article>
      <article class="overview-tile">
        <strong>{{ statusCounts.recording }}</strong>
        <span class="overview-detail">Recording</span>
      </article>
      <article class="overview-tile">
        <strong>{{ statusCounts.offline }}</strong>
        <span class="overview-detail">Offline</span>
      </article>
      <article class="overview-tile">
        <strong>{{ statusCounts.paused }}</strong>
        <span class="overview-detail">Paused</span>
      </article>
      <article class="overview-tile">
        <strong>{{ statusCounts.error }}</strong>
        <span class="overview-detail">Error</span>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
defineProps<{
  allChannelsCount: number;
  statusCounts: { recording: number; offline: number; paused: number; error: number };
  isRefreshing?: boolean;
}>();

defineEmits<{
  add: [];
  settings: [];
}>();
</script>

<style scoped>
.top-summary {
  padding: 48px;
  background: var(--panel);
  border: 1px solid var(--line);
  color: var(--text);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow);
}

.summary-head {
  display: flex;
  justify-content: space-between;
  gap: 24px;
  align-items: flex-start;
  margin-bottom: 48px;
}

.summary-copy {
  display: grid;
  gap: 12px;
}

.summary-title {
  font-size: 32px;
  letter-spacing: -0.05em;
  line-height: 1;
  font-weight: 800;
}

.top-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.refresh-note {
  color: var(--muted);
  font-size: 13px;
  font-weight: 500;
  letter-spacing: -0.01em;
}

.overview-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 40px;
  padding-top: 48px;
  border-top: 1px solid var(--line);
}

.overview-tile {
  display: grid;
  gap: 8px;
  align-content: start;
}

.overview-tile strong {
  font-size: 36px;
  letter-spacing: -0.06em;
  line-height: 1;
  font-weight: 700;
}

.overview-detail {
  color: var(--muted);
  line-height: 1.3;
  font-size: 13px;
  font-weight: 600;
}

@media (max-width: 1000px) {
  .top-summary {
    padding: 32px;
  }
  .overview-grid {
    grid-template-columns: repeat(3, 1fr);
    gap: 32px;
    padding-top: 32px;
  }
}

@media (max-width: 600px) {
  .top-summary {
    padding: 24px;
  }
  .summary-head {
    flex-direction: column;
    align-items: stretch;
    gap: 20px;
    margin-bottom: 32px;
  }
  .summary-title {
    font-size: 24px;
    text-align: left;
  }
  .top-actions {
    display: grid;
    grid-template-columns: 1fr 1fr;
    width: 100%;
    gap: 8px;
  }
  .top-actions .button {
    width: 100%;
    padding: 10px 4px;
    font-size: 12px;
    display: flex;
    justify-content: center;
  }
  .refresh-note {
    grid-column: 1 / -1;
    text-align: center;
    margin-bottom: 4px;
  }
  .overview-grid {
    grid-template-columns: repeat(2, 1fr);
    gap: 24px;
    padding-top: 24px;
  }
  .overview-tile strong {
    font-size: 28px;
  }
}
</style>
