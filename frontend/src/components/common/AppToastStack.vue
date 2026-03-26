<template>
  <div class="toast-stack" v-if="toasts.length">
    <div v-for="toast in toasts" :key="toast.id" class="toast" :class="toast.tone">
      <div class="toast-message">{{ toast.message }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { ToastItem } from "../../types";

defineProps<{
  toasts: ToastItem[];
}>();
</script>

<style scoped>
.toast-stack {
  position: fixed;
  top: 32px;
  right: 32px;
  display: grid;
  gap: 12px;
  z-index: 30;
}

.toast {
  min-width: 280px;
  max-width: 400px;
  padding: 16px 20px;
  border-radius: var(--radius-lg);
  background: var(--text);
  color: var(--bg);
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.15);
  display: flex;
  align-items: center;
  gap: 12px;
  animation: slide-in 400ms cubic-bezier(0.16, 1, 0.3, 1);
}

.toast.error {
  background: var(--danger);
}

.toast-message {
  line-height: 1.4;
  font-size: 14px;
  font-weight: 600;
  letter-spacing: -0.01em;
}

@keyframes slide-in {
  from {
    opacity: 0;
    transform: translateX(20px);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}

@media (max-width: 640px) {
  .toast-stack {
    left: 24px;
    right: 24px;
    top: 24px;
  }

  .toast {
    min-width: 0;
    max-width: none;
  }
}
</style>
