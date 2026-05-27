<template>
  <div class="dialog-backdrop" v-if="open" @click.self="$emit('close')">
    <div class="dialog-card missav-card">
      <div class="dialog-head">
        <div>
          <div class="dialog-title display-face">MissAV recording</div>
        </div>
        <button class="button ghost compact-close" @click="$emit('close')" :disabled="submitting">Close</button>
      </div>

      <form class="missav-form" @submit.prevent="$emit('submit')">
        <div>
          <label class="field-label">URL</label>
          <input
            class="text-input"
            v-model.trim="draft.url"
            type="url"
            required
            placeholder="https://missav.ai/..."
            autocomplete="off"
          />
        </div>
        <button class="button submit-btn" type="submit" :disabled="submitting">
          {{ submitting ? "Starting..." : "Start recording" }}
        </button>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  open: boolean;
  draft: { url: string };
  submitting?: boolean;
}>();

defineEmits<{
  close: [];
  submit: [];
}>();
</script>

<style scoped>
.missav-card {
  width: min(560px, 100%);
}

.missav-form {
  display: grid;
  gap: 20px;
}

.submit-btn {
  justify-self: start;
}

@media (max-width: 700px) {
  .submit-btn {
    width: 100%;
    justify-self: stretch;
  }
}
</style>
