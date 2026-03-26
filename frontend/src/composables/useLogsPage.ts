import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";

import { api } from "../api";
import { countErrorEvents, countRecordingEvents, countSourceIssueEvents } from "../utils/logs";
import type { EventItem } from "../types";

export function useLogsPage() {
  const loading = ref(false);
  const events = ref<EventItem[]>([]);
  const eventTypes = ref<string[]>([]);
  const channels = ref<Array<{ id: string; username: string }>>([]);
  const activeQuickFilter = ref<"all" | "errors" | "recording" | "source">("all");
  const total = ref(0);
  const offset = ref(0);
  const hasNext = ref(false);

  const filters = reactive({
    channel_id: "",
    event_type: "",
    level: "",
    limit: 20,
  });

  const errorCount = computed(() => countErrorEvents(events.value));
  const recordingCount = computed(() => countRecordingEvents(events.value));
  const sourceIssueCount = computed(() => countSourceIssueEvents(events.value));
  const filterSummary = computed(() => {
    const parts: string[] = [];
    if (filters.channel_id) {
      const channel = channels.value.find((item) => item.id === filters.channel_id);
      parts.push(channel ? channel.username : "selected streamer");
    }
    if (filters.event_type) {
      parts.push(filters.event_type);
    }
    if (filters.level) {
      parts.push(filters.level);
    }
    if (!parts.length) {
      return "Showing the full event stream.";
    }
    return `Filtered by ${parts.join(" / ")}.`;
  });
  const pageSummary = computed(() => {
    if (!events.value.length) {
      return "No rows loaded.";
    }
    const start = offset.value + 1;
    const end = offset.value + events.value.length;
    return `Showing ${start}-${end} of ${total.value}.`;
  });

  async function loadLogs() {
    loading.value = true;
    try {
      const params = new URLSearchParams();
      if (filters.channel_id) params.set("channel_id", filters.channel_id);
      if (filters.event_type) params.set("event_type", filters.event_type);
      if (filters.level) params.set("level", filters.level);
      params.set("limit", String(filters.limit));
      params.set("offset", String(offset.value));
      const payload = await api.loadLogs(params);
      events.value = payload.items;
      eventTypes.value = payload.event_types;
      channels.value = payload.channels;
      total.value = payload.total;
      offset.value = payload.offset;
      hasNext.value = payload.has_next;
    } finally {
      loading.value = false;
    }
  }

  function applyFilters() {
    offset.value = 0;
    void loadLogs();
  }

  function resetFilters() {
    offset.value = 0;
    filters.channel_id = "";
    filters.event_type = "";
    filters.level = "";
    filters.limit = 300;
    activeQuickFilter.value = "all";
    void loadLogs();
  }

  function applyQuickFilter(mode: "all" | "errors" | "recording" | "source") {
    activeQuickFilter.value = mode;
    offset.value = 0;
    filters.event_type = "";
    if (mode === "all") {
      filters.level = "";
    } else if (mode === "errors") {
      filters.level = "ERROR";
    } else if (mode === "recording") {
      filters.level = "";
      filters.event_type = "recording_started";
    } else if (mode === "source") {
      filters.level = "ERROR";
      filters.event_type = "PAGE_FETCH_FAILED";
    }
    void loadLogs();
  }

  function nextPage() {
    if (!hasNext.value) {
      return;
    }
    offset.value += filters.limit;
    void loadLogs();
  }

  function prevPage() {
    if (offset.value === 0) {
      return;
    }
    offset.value = Math.max(0, offset.value - filters.limit);
    void loadLogs();
  }

  let filterTimer: number | undefined;

  watch(
    () => [filters.channel_id, filters.event_type, filters.level, filters.limit],
    () => {
      window.clearTimeout(filterTimer);
      filterTimer = window.setTimeout(() => {
        applyFilters();
      }, 180);
    },
  );

  onMounted(() => {
    void loadLogs();
  });

  onBeforeUnmount(() => {
    window.clearTimeout(filterTimer);
  });

  return {
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
  };
}
