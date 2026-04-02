<template>
  <article class="channel-card">
    <div class="channel-top">
      <div class="channel-identity">
        <div class="channel-name-row">
          <a class="channel-name channel-link-anchor" :href="channel.url" target="_blank" rel="noreferrer">
            {{ channel.username }}
          </a>
          <div class="badge-row">
            <span class="platform-badge" :title="channel.platform">{{ platformBadge(channel.platform) }}</span>
            <span class="status-pill" :class="channel.status_tone || channel.status_label">
              {{ channel.status_detail || channel.status_label }}
            </span>
          </div>
        </div>
      </div>
      <div class="desktop-actions">
        <ChannelCardActions
          :channel="channel"
          @edit="$emit('edit', channel)"
          @delete="$emit('delete', channel)"
          @pause="$emit('pause', channel.id)"
          @resume="$emit('resume', channel.id)"
        />
      </div>
    </div>

    <ChannelCardMeta :channel="channel" />

    <div class="mobile-actions">
      <ChannelCardActions
        :channel="channel"
        @edit="$emit('edit', channel)"
        @delete="$emit('delete', channel)"
        @pause="$emit('pause', channel.id)"
        @resume="$emit('resume', channel.id)"
      />
    </div>
  </article>
</template>

<script setup lang="ts">
import type { Channel } from "../../types";
import { platformBadge } from "../../utils/channel";
import ChannelCardActions from "./ChannelCardActions.vue";
import ChannelCardMeta from "./ChannelCardMeta.vue";

defineProps<{
  channel: Channel;
}>();

defineEmits<{
  edit: [channel: Channel];
  delete: [channel: Channel];
  pause: [channelId: string];
  resume: [channelId: string];
}>();
</script>

<style scoped>
.channel-card {
  border: 1px solid var(--line);
  padding: 32px;
  display: grid;
  gap: 24px;
  min-width: 0;
  background: var(--panel);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-soft);
  transition: all 300ms cubic-bezier(0.16, 1, 0.3, 1);
}

.channel-card:hover {
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.06);
  transform: translateY(-2px);
}

.channel-top {
  display: flex;
  justify-content: space-between;
  gap: 24px;
  align-items: center;
}

.channel-identity {
  display: grid;
  gap: 8px;
  min-width: 0;
}

.channel-name-row {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}

.badge-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.channel-name {
  font-size: 24px;
  font-weight: 700;
  letter-spacing: -0.04em;
  line-height: 1;
  word-break: break-all;
}

.mobile-actions {
  display: none;
}

@media (max-width: 800px) {
  .channel-card {
    padding: 24px;
    gap: 20px;
  }

  .channel-top {
    flex-direction: column;
    align-items: flex-start;
    gap: 16px;
  }

  .desktop-actions {
    display: none;
  }

  .mobile-actions {
    display: block;
    padding-top: 12px;
    border-top: 1px solid var(--line);
  }

  .channel-name {
    font-size: 20px;
  }
}

.channel-link-anchor {
  color: inherit;
  text-decoration: none;
}

.channel-link-anchor:hover {
  opacity: 0.7;
}

.platform-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 4px 8px;
  border-radius: var(--radius-sm);
  background: var(--bg-2);
  color: var(--muted);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.05em;
  border: 1px solid var(--line);
}

</style>
