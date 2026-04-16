<template>
  <div class="dialog-backdrop" v-if="open && draft" @click.self="$emit('close')">
    <div
      class="dialog-card"
      @touchstart="handleTouchStart"
      @touchmove="handleTouchMove"
      @touchend="handleTouchEnd"
      :style="cardStyle"
    >
      <div class="mobile-handle" @click="$emit('close')"></div>
      <div class="dialog-head">
        <div>
          <div class="dialog-title display-face">Recorder settings</div>
        </div>
        <button class="button ghost compact-close" @click="$emit('close')">Close</button>
      </div>
      <form class="grid-2" @submit.prevent="$emit('submit')">
        <div><label class="field-label">Host</label><input class="text-input" v-model="draft.host" /></div>
        <div><label class="field-label">Port</label><input class="text-input" v-model.number="draft.port" type="number" /></div>
        <div><label class="field-label">Timezone</label><input class="text-input" v-model="draft.timezone" /></div>
        <div><label class="field-label">Cookies Browser</label><input class="text-input" v-model="draft.cookies_from_browser" /></div>
        <div class="full-span"><label class="field-label">Recordings Dir</label><input class="text-input" v-model="draft.recordings_dir" /></div>
        <div class="full-span"><label class="field-label">Organized Dir</label><input class="text-input" v-model="draft.organized_dir" /></div>
        <div><label class="field-label">Default Poll Seconds</label><input class="text-input" v-model.number="draft.default_poll_interval_seconds" type="number" /></div>
        <div><label class="field-label">Max Concurrent Probes</label><input class="text-input" v-model.number="draft.max_concurrent_probes" type="number" /></div>
        <div><label class="field-label">Probe Rate Limit Seconds</label><input class="text-input" v-model.number="draft.probe_rate_limit_seconds" type="number" /></div>
        <div><label class="field-label">Probe Timeout Seconds</label><input class="text-input" v-model.number="draft.probe_timeout_seconds" type="number" /></div>
        <div><label class="field-label">Convert Timeout Seconds</label><input class="text-input" v-model.number="draft.convert_timeout_seconds" type="number" /></div>
        <div class="full-span"><label class="field-label">yt-dlp Path</label><input class="text-input" v-model="draft.yt_dlp_path" /></div>
        <div class="full-span"><label class="field-label">ffmpeg Path</label><input class="text-input" v-model="draft.ffmpeg_path" /></div>
        <div class="full-span checkbox-row">
          <label><input v-model="draft.delete_source_after_convert" type="checkbox" /> Delete Source File After Convert</label>
          <label><input v-model="draft.keep_failed_source" type="checkbox" /> Keep Failed Source Files</label>
          <label><input v-model="draft.force_audio_reencode" type="checkbox" /> Force Audio Re-encode</label>
        </div>
        <div class="full-span">
          <button class="button submit-btn" type="submit">Save Settings</button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import type { AppConfig } from "../../types";

defineProps<{
  open: boolean;
  draft: AppConfig | null;
}>();

const emit = defineEmits<{
  close: [];
  submit: [];
}>();

// Swipe down to close logic
const touchY = ref(0);
const deltaY = ref(0);
const isSwiping = ref(false);

function handleTouchStart(e: TouchEvent) {
  if (window.innerWidth > 700) return;
  touchY.value = e.touches[0].clientY;
  isSwiping.value = true;
}

function handleTouchMove(e: TouchEvent) {
  if (!isSwiping.value) return;
  const currentY = e.touches[0].clientY;
  const diff = currentY - touchY.value;
  if (diff > 0) {
    deltaY.value = diff;
  }
}

function handleTouchEnd() {
  if (deltaY.value > 120) {
    emit("close");
  }
  isSwiping.value = false;
  deltaY.value = 0;
}

const cardStyle = computed(() => {
  if (deltaY.value > 0) {
    return { transform: `translateY(${deltaY.value}px)`, transition: 'none' };
  }
  return {};
});
</script>

<style scoped>
.mobile-handle {
  display: none;
}

.compact-close {
  padding: 6px 12px;
  font-size: 12px;
}

.submit-btn {
  width: 100%;
  padding: 14px;
  font-size: 15px;
  margin-top: 8px;
}

@media (max-width: 700px) {
  .mobile-handle {
    display: block;
    width: 48px;
    height: 6px;
    background: var(--line-strong);
    border-radius: 3px;
    margin: -16px auto 24px;
    opacity: 0.4;
    cursor: pointer;
  }

  .compact-close {
    display: flex;
    padding: 4px 10px;
    font-size: 11px;
  }
}

.checkbox-row {
  display: flex;
  justify-content: flex-start;
  gap: 24px;
  align-items: center;
  flex-wrap: wrap;
}

.checkbox-row label {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--text);
  font-size: 13px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  cursor: pointer;
}

input[type="checkbox"] {
  accent-color: var(--text);
  width: 16px;
  height: 16px;
  cursor: pointer;
}
</style>
