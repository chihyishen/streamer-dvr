import { computed, onMounted, onUnmounted, reactive, ref, watch } from "vue";

import { useAppStore } from "../stores/app";
import { compareChannels } from "../utils/channel";
import type { AppConfig, Channel } from "../types";

const UNAVAILABLE_STATUS_DETAILS = new Set([
  "Private show",
  "Hidden show",
  "Password protected",
]);

export function useDashboardPage() {
  const store = useAppStore();
  const selectedCategory = ref("default");
  const showAdd = ref(false);
  const showSettings = ref(false);
  const settingsDraft = ref<AppConfig | null>(null);
  const editDraft = ref<Record<string, any> | null>(null);
  const deleteDraft = ref<Channel | null>(null);

  const addForm = reactive({
    username: "",
    platform: "chaturbate",
    category: "default",
    poll_interval_seconds: 300,
    paused: false,
  });

  const filteredChannels = computed(() => {
    const activeCategory = store.categories.includes(selectedCategory.value)
      ? selectedCategory.value
      : store.categories[0];
    const visibleChannels = activeCategory
      ? store.channels.filter((channel) => channel.category === activeCategory)
      : store.channels;
    return visibleChannels.slice().sort((left, right) => compareChannels(left, right));
  });

  const summaryCounts = computed(() => ({
    channels: store.allChannelsCount,
    online: store.channels.filter((channel) => channel.status === "recording").length,
    unavailable: store.channels.filter((channel) => UNAVAILABLE_STATUS_DETAILS.has(channel.status_detail || "")).length,
    errors: store.channels.filter((channel) => channel.status === "error").length,
    paused: store.channels.filter((channel) => channel.paused).length,
  }));

  function syncCategory() {
    if (!store.categories.length) {
      selectedCategory.value = "default";
      return;
    }
    if (!store.categories.includes(selectedCategory.value)) {
      selectedCategory.value = store.categories[0];
    }
  }

  watch(
    () => [store.categories.join("|"), store.channels.length],
    () => {
      syncCategory();
    },
  );

  function openSettings() {
    if (!store.config) {
      return;
    }
    settingsDraft.value = JSON.parse(JSON.stringify(store.config)) as AppConfig;
    showSettings.value = true;
  }

  function startEdit(channel: Channel) {
    editDraft.value = {
      id: channel.id,
      username: channel.username,
      platform: channel.platform,
      category: channel.category,
      enabled: channel.enabled,
      paused: channel.paused,
      poll_interval_seconds: channel.poll_interval_seconds,
      max_resolution: channel.max_resolution,
      max_framerate: channel.max_framerate,
      filename_pattern: channel.filename_pattern,
    };
  }

  function confirmDelete(channel: Channel) {
    deleteDraft.value = channel;
  }

  async function submitAdd() {
    await store.createChannel(addForm);
    addForm.username = "";
    addForm.platform = "chaturbate";
    addForm.category = selectedCategory.value;
    addForm.poll_interval_seconds = store.config?.default_poll_interval_seconds ?? 300;
    addForm.paused = false;
    showAdd.value = false;
    syncCategory();
  }

  async function submitSettings() {
    if (!settingsDraft.value) {
      return;
    }
    await store.saveSettings(settingsDraft.value);
    showSettings.value = false;
  }

  async function submitEdit() {
    if (!editDraft.value) {
      return;
    }
    const { id, ...payload } = editDraft.value;
    await store.updateChannel(id, payload);
    editDraft.value = null;
  }

  async function submitDelete() {
    if (!deleteDraft.value) {
      return;
    }
    await store.deleteChannel(deleteDraft.value.id);
    deleteDraft.value = null;
    syncCategory();
  }

  onMounted(async () => {
    await store.refresh();
    store.connectDashboardStream();
    addForm.category = store.categories[0] ?? "default";
    addForm.poll_interval_seconds = store.config?.default_poll_interval_seconds ?? 300;
    syncCategory();
  });

  onUnmounted(() => {
    store.disconnectDashboardStream();
  });

  return {
    store,
    selectedCategory,
    showAdd,
    showSettings,
    settingsDraft,
    editDraft,
    deleteDraft,
    addForm,
    filteredChannels,
    summaryCounts,
    openSettings,
    startEdit,
    confirmDelete,
    submitAdd,
    submitSettings,
    submitEdit,
    submitDelete,
  };
}
