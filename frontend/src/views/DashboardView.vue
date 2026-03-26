<template>
  <section class="dashboard-layout" v-if="store.config">
    <div class="summary-area">
      <DashboardSummary
        :all-channels-count="store.allChannelsCount"
        :status-counts="statusCounts"
        :is-refreshing="store.loading"
        @add="showAdd = true"
        @settings="openSettings"
      />
    </div>

    <div class="activity-area">
      <RecentActivityPanel :events="compactEvents" />
    </div>

    <section class="card channels-panel">
      <div class="section-head">
        <div class="section-title display-face">Channels</div>
        <div class="tabs">
          <button
            v-for="category in store.categories"
            :key="category"
            class="tab"
            :class="{ active: selectedCategory === category }"
            @click="selectedCategory = category"
          >
            {{ category }}
          </button>
        </div>
      </div>

      <div class="channel-list" v-if="filteredChannels.length">
        <ChannelCard
          v-for="channel in filteredChannels"
          :key="channel.id"
          :channel="channel"
          @edit="startEdit"
          @delete="confirmDelete"
          @pause="store.pauseChannel"
          @resume="store.resumeChannel"
        />
      </div>

      <div class="empty" v-else>
        <div class="empty-title display-face">No channels in {{ selectedCategory }}</div>
        <p class="empty-body">Add a streamer here or switch categories to inspect another slice of the roster.</p>
      </div>
    </section>

    <ChannelFormModal
      :open="showAdd"
      title="Add Streamer"
      submit-label="Add Streamer"
      :draft="addForm"
      :categories="store.categories"
      :require-username="true"
      @close="showAdd = false"
      @submit="submitAdd"
    />

    <SettingsModal
      :open="showSettings"
      :draft="settingsDraft"
      @close="showSettings = false"
      @submit="submitSettings"
    />

    <ChannelFormModal
      :open="!!editDraft"
      title="Edit Streamer"
      submit-label="Save"
      :draft="editDraft ?? {}"
      :categories="store.categories"
      :require-username="true"
      :show-recording-options="true"
      :show-filename-pattern="true"
      :show-toggle-fields="true"
      @close="editDraft = null"
      @submit="submitEdit"
    />

    <DeleteConfirmModal
      :channel="deleteDraft"
      @close="deleteDraft = null"
      @confirm="submitDelete"
    />
  </section>
</template>

<script setup lang="ts">
import ChannelCard from "../components/dashboard/ChannelCard.vue";
import ChannelFormModal from "../components/dashboard/ChannelFormModal.vue";
import DashboardSummary from "../components/dashboard/DashboardSummary.vue";
import DeleteConfirmModal from "../components/dashboard/DeleteConfirmModal.vue";
import RecentActivityPanel from "../components/dashboard/RecentActivityPanel.vue";
import SettingsModal from "../components/dashboard/SettingsModal.vue";
import { useDashboardPage } from "../composables/useDashboardPage";

const {
  store,
  selectedCategory,
  showAdd,
  showSettings,
  settingsDraft,
  editDraft,
  deleteDraft,
  addForm,
  filteredChannels,
  compactEvents,
  statusCounts,
  openSettings,
  startEdit,
  confirmDelete,
  submitAdd,
  submitSettings,
  submitEdit,
  submitDelete,
} = useDashboardPage();
</script>

<style scoped>
.dashboard-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.7fr) 280px;
  grid-template-areas:
    "summary activity"
    "channels activity";
  gap: 48px;
  align-items: start;
}

.summary-area {
  grid-area: summary;
  min-width: 0;
}

.activity-area {
  grid-area: activity;
  min-width: 0;
}

.channels-panel {
  grid-area: channels;
  display: grid;
  gap: 32px;
  border: none;
  padding: 0;
  background: transparent;
  box-shadow: none;
}

.channels-panel .section-head {
  display: flex;
  justify-content: space-between;
  gap: 20px;
  align-items: baseline;
  flex-wrap: wrap;
}

.section-title {
  font-size: 24px;
  line-height: 1;
  letter-spacing: -0.04em;
  font-weight: 700;
}

.tabs {
  display: flex;
  justify-content: flex-start;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}

.tab {
  border: 1px solid var(--line-strong);
  border-radius: var(--radius-xl);
  padding: 6px 14px;
  background: var(--panel);
  cursor: pointer;
  font-weight: 600;
  font-size: 13px;
  letter-spacing: -0.01em;
  color: var(--muted);
  transition: all 200ms ease;
}

.tab.active {
  background: var(--text);
  color: var(--bg);
  border-color: var(--text);
}

.tab:hover:not(.active) {
  border-color: var(--text);
  color: var(--text);
}

.channel-list {
  display: grid;
  gap: 16px;
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
  .dashboard-layout {
    grid-template-columns: 100%;
    grid-template-areas:
      "summary"
      "channels";
    gap: 32px;
  }

  .activity-area {
    display: none;
  }
}
</style>
