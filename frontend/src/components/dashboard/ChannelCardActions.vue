<template>
  <div class="toolbar channel-actions">
    <button
      class="button"
      :class="channel.paused ? '' : 'secondary'"
      @click="handleToggle()"
    >
      {{ channel.paused ? "Resume" : "Pause" }}
    </button>
    <button class="button ghost" @click="$emit('edit', channel)">Edit</button>
    <button class="button danger" @click="$emit('delete', channel)">Delete</button>
  </div>
</template>

<script setup lang="ts">
import type { Channel } from "../../types";

const props = defineProps<{
  channel: Channel;
}>();

const emit = defineEmits<{
  edit: [channel: Channel];
  delete: [channel: Channel];
  pause: [channelId: string];
  resume: [channelId: string];
}>();

function handleToggle() {
  const { channel } = props;
  if (channel.paused) {
    emit("resume", channel.id);
    return;
  }
  emit("pause", channel.id);
}
</script>

<style scoped>
.channel-actions {
  justify-content: flex-end;
  align-items: center;
  gap: 8px;
}

@media (max-width: 800px) {
  .channel-actions {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    width: 100%;
    justify-content: stretch;
  }

  .button {
    padding: 10px 4px;
    font-size: 12px;
    text-align: center;
    justify-content: center;
    display: flex;
  }
}
</style>
