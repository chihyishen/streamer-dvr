<template>
  <div class="dialog-backdrop" v-if="channel" @click.self="$emit('close')">
    <div class="dialog-card dialog-compact">
      <div class="dialog-head">
        <div>
          <div class="section-kicker">Confirm</div>
          <div class="dialog-title display-face">Delete streamer</div>
        </div>
      </div>
      <div class="confirm-copy">
        <p>Remove <strong>{{ channel.username }}</strong> from monitoring?</p>
        <p class="muted">This only removes the channel from the app. Existing recordings stay on disk.</p>
      </div>
      <div class="toolbar confirm-actions">
        <button class="button ghost" @click="$emit('close')">Cancel</button>
        <button class="button danger" @click="$emit('confirm')">Delete</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { Channel } from "../../types";

defineProps<{
  channel: Channel | null;
}>();

defineEmits<{
  close: [];
  confirm: [];
}>();
</script>

<style scoped>
.dialog-compact {
  width: min(520px, 100%);
}

.confirm-copy {
  display: grid;
  gap: 12px;
  margin-bottom: 24px;
}

.confirm-copy p {
  margin: 0;
  line-height: 1.5;
  font-size: 14px;
}

.confirm-actions {
  justify-content: flex-end;
}
</style>
