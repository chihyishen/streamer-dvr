<template>
  <div class="dialog-backdrop" v-if="open" @click.self="$emit('close')">
    <div
      class="dialog-card"
      :style="cardStyle"
    >
      <!-- Fixed Header / Swipe Zone -->
      <div 
        class="swipe-zone"
        @touchstart="handleTouchStart"
        @touchmove="handleTouchMove"
        @touchend="handleTouchEnd"
      >
        <div class="mobile-handle"></div>
        <div class="dialog-head">
          <div>
            <div class="dialog-title display-face">{{ title }}</div>
          </div>
          <button class="button ghost compact-close" @click="$emit('close')">Close</button>
        </div>
      </div>

      <!-- Scrollable Form Content -->
      <div class="modal-body">
        <form class="grid-3" @submit.prevent="$emit('submit')">
          <div class="full-span">
            <label class="field-label">Platform</label>
            <select class="select-input" v-model="draft.platform">
              <option value="chaturbate">chaturbate</option>
            </select>
          </div>

          <div class="full-span">
            <label class="field-label">Streamer</label>
            <div class="unified-input-group">
              <span class="input-prefix desktop-only">{{ platformBaseUrl(String(draft.platform)) }}</span>
              <input 
                class="group-input" 
                v-model.trim="draft.username" 
                :required="requireUsername" 
                placeholder="Enter username"
                type="text"
                autocomplete="off"
              />
            </div>
          </div>

          <div class="full-span form-pair">
            <div class="combobox-container">
              <label class="field-label">Category</label>
              <div class="combobox-wrapper" ref="comboboxWrapper">
                <input
                  type="text"
                  class="text-input combobox-input"
                  v-model.trim="draft.category"
                  placeholder="Select or type..."
                  @focus="openCategories"
                  @blur="hideCategoriesWithDelay"
                />
                <div class="combobox-arrow"></div>
                <ul class="combobox-dropdown" v-if="showCategories && filteredCategories.length">
                  <li 
                    v-for="cat in filteredCategories" 
                    :key="cat" 
                    @mousedown="selectCategory(cat)"
                  >
                    {{ cat }}
                  </li>
                </ul>
              </div>
            </div>
            <div>
              <label class="field-label">Poll Seconds</label>
              <input class="text-input" v-model.number="draft.poll_interval_seconds" type="number" min="30" />
            </div>
          </div>

          <div class="full-span form-pair" v-if="showRecordingOptions">
            <div>
              <label class="field-label">Max Resolution</label>
              <select class="select-input" v-model="draft.max_resolution">
                <option :value="null">Auto</option>
                <option :value="720">720p</option>
                <option :value="1080">1080p</option>
                <option :value="1440">2K</option>
                <option :value="2160">4K</option>
              </select>
            </div>
            <div>
              <label class="field-label">Max FPS</label>
              <select class="select-input" v-model="draft.max_framerate">
                <option :value="null">Auto</option>
                <option :value="30">30</option>
                <option :value="60">60</option>
              </select>
            </div>
          </div>

          <div class="full-span" v-if="showFilenamePattern">
            <label class="field-label">Filename Pattern</label>
            <input class="text-input" v-model="draft.filename_pattern" />
          </div>

          <div class="full-span checkbox-row" v-if="showToggleFields">
            <label><input v-model="draft.enabled" type="checkbox" /> Enabled</label>
            <label><input v-model="draft.paused" type="checkbox" /> Paused</label>
          </div>
          <div class="full-span single-checkbox" v-else>
            <label><input v-model="draft.paused" type="checkbox" /> Create as paused</label>
          </div>

          <div class="full-span">
            <button class="button submit-btn" type="submit">{{ submitLabel }}</button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref } from "vue";

const props = defineProps<{
  open: boolean;
  title: string;
  submitLabel: string;
  draft: Record<string, any>;
  categories: string[];
  requireUsername?: boolean;
  showRecordingOptions?: boolean;
  showFilenamePattern?: boolean;
  showToggleFields?: boolean;
}>();

const emit = defineEmits<{
  close: [];
  submit: [];
}>();

// Custom Combobox logic
const showCategories = ref(false);
const comboboxWrapper = ref<HTMLElement | null>(null);
const filteredCategories = computed(() => {
  const query = (props.draft.category || "").toLowerCase();
  return props.categories.filter(c => c.toLowerCase().includes(query));
});

async function openCategories() {
  showCategories.value = true;
  // The dropdown is absolute-positioned and can be clipped by the dialog-card's
  // overflow boundary when the Category field sits near the bottom of the modal.
  // Wait for the dropdown to render, then ensure the wrapper is scrolled into
  // a position that leaves room for the full dropdown (+ a small margin).
  await nextTick();
  const wrapper = comboboxWrapper.value;
  if (!wrapper) return;
  const card = wrapper.closest(".dialog-card") as HTMLElement | null;
  const dropdown = wrapper.querySelector(".combobox-dropdown") as HTMLElement | null;
  if (!card || !dropdown) return;
  const cardRect = card.getBoundingClientRect();
  const dropdownRect = dropdown.getBoundingClientRect();
  const overflow = dropdownRect.bottom - cardRect.bottom;
  if (overflow > 0) {
    card.scrollBy({ top: overflow + 16, behavior: "smooth" });
  }
}

function selectCategory(cat: string) {
  props.draft.category = cat;
  showCategories.value = false;
}

function hideCategoriesWithDelay() {
  setTimeout(() => {
    showCategories.value = false;
  }, 200);
}

// Swipe down logic
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
    if (e.cancelable) e.preventDefault();
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

function platformBaseUrl(platform: string) {
  if (platform === "chaturbate") {
    return "https://chaturbate.com/";
  }
  return "";
}
</script>

<style scoped>
.swipe-zone {
  margin: -40px -40px 32px;
  padding: 24px 40px 0;
  cursor: grab;
  position: relative;
  z-index: 10;
}

.mobile-handle {
  display: block;
  width: 48px;
  height: 6px;
  background: var(--line-strong);
  border-radius: 3px;
  margin: 0 auto 24px;
  opacity: 0.4;
}

.modal-body {
  position: relative;
  z-index: 1;
}

/* Combobox Styling */
.combobox-wrapper {
  position: relative;
}

.combobox-arrow {
  position: absolute;
  right: 14px;
  top: 50%;
  transform: translateY(-50%);
  width: 16px;
  height: 16px;
  pointer-events: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 24 24' stroke='%23737373' stroke-width='2'%3E%3Cpath stroke-linecap='round' stroke-linejoin='round' d='M19 9l-7 7-7-7'%3E%3C/path%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-size: contain;
  opacity: 0.6;
}

.combobox-input {
  padding-right: 40px !important;
}

.combobox-dropdown {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  right: 0;
  background: var(--panel);
  border: 1px solid var(--line-strong);
  border-radius: var(--radius-md);
  box-shadow: 0 10px 25px rgba(0,0,0,0.1);
  z-index: 100;
  list-style: none;
  margin: 0;
  padding: 6px;
  max-height: 200px;
  overflow-y: auto;
}

.combobox-dropdown li {
  padding: 10px 12px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  border-radius: var(--radius-sm);
}

.combobox-dropdown li:hover {
  background: var(--bg-2);
}

/* Unified Input Group */
.unified-input-group {
  display: flex;
  align-items: center;
  border: 1px solid var(--line-strong);
  border-radius: var(--radius-md);
  background: var(--bg);
  padding: 0 14px;
  transition: all 200ms ease;
  min-height: 46px;
}

.unified-input-group:focus-within {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px rgba(0, 0, 0, 0.05);
}

.input-prefix {
  color: var(--muted);
  font-size: 14px;
  white-space: nowrap;
  padding-right: 4px;
  user-select: none;
}

.group-input {
  flex: 1;
  border: none !important;
  background: transparent !important;
  padding: 10px 0 !important;
  color: var(--text);
  font-family: inherit;
  font-size: 14px;
  outline: none !important;
  min-width: 0;
  height: 100%;
}

.compact-close {
  padding: 6px 12px;
  font-size: 12px;
}

.submit-btn {
  width: 100%;
  padding: 14px;
  font-size: 15px;
  margin-top: 16px;
}

@media (max-width: 700px) {
  .dialog-card {
    min-height: 60vh;
    padding: 32px 24px 48px;
  }

  .swipe-zone {
    margin: -32px -24px 20px;
    padding: 16px 24px 0;
  }

  .desktop-only {
    display: none;
  }

  .group-input {
    font-size: 16px !important;
  }

  .text-input, .select-input, .combobox-input {
    font-size: 16px !important;
  }
}

.field-hint {
  margin-top: 6px;
  color: var(--muted);
  font-size: 11px;
  line-height: 1.45;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.form-pair {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.checkbox-row {
  display: flex;
  justify-content: flex-start;
  gap: 24px;
  align-items: center;
  flex-wrap: wrap;
}

.checkbox-row label,
.single-checkbox label {
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

@media (max-width: 800px) {
  .form-pair {
    grid-template-columns: 1fr;
  }
}
</style>
