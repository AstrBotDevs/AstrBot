<script setup>
import { ref, onMounted, onUnmounted, nextTick, watch } from 'vue';

const props = defineProps({
  // Minimum thumb height in pixels
  minThumbSize: {
    type: Number,
    default: 32
  },
  // Hide the thumb automatically after scrolling stops
  autoHide: {
    type: Boolean,
    default: true
  },
  // Delay (ms) before auto hiding after the pointer leaves / scroll stops
  hideDelay: {
    type: Number,
    default: 800
  }
});

const viewport = ref(null); // scrollable element
const thumb = ref(null);
const trackVisible = ref(false); // pointer is over the area
const scrolling = ref(false); // recently scrolled
const dragging = ref(false);

const thumbHeight = ref(0);
const thumbTop = ref(0);
const hasOverflow = ref(false);

let hideTimer = null;
let dragStartY = 0;
let dragStartScrollTop = 0;
let resizeObserver = null;
let mutationObserver = null;

function updateThumb() {
  const el = viewport.value;
  if (!el) return;
  const { scrollHeight, clientHeight, scrollTop } = el;
  hasOverflow.value = scrollHeight > clientHeight + 1;
  if (!hasOverflow.value) {
    thumbHeight.value = 0;
    return;
  }
  const ratio = clientHeight / scrollHeight;
  const rawHeight = Math.max(clientHeight * ratio, props.minThumbSize);
  thumbHeight.value = rawHeight;
  const maxThumbTop = clientHeight - rawHeight;
  const maxScrollTop = scrollHeight - clientHeight;
  thumbTop.value = maxScrollTop > 0 ? (scrollTop / maxScrollTop) * maxThumbTop : 0;
}

function flagScrolling() {
  scrolling.value = true;
  if (!props.autoHide) return;
  if (hideTimer) clearTimeout(hideTimer);
  hideTimer = setTimeout(() => {
    if (!dragging.value && !trackVisible.value) {
      scrolling.value = false;
    }
  }, props.hideDelay);
}

function onScroll() {
  updateThumb();
  flagScrolling();
}

function onPointerEnter() {
  trackVisible.value = true;
}

function onPointerLeave() {
  trackVisible.value = false;
  if (props.autoHide && !dragging.value) {
    if (hideTimer) clearTimeout(hideTimer);
    hideTimer = setTimeout(() => {
      scrolling.value = false;
    }, props.hideDelay);
  }
}

function onThumbPointerDown(event) {
  if (!hasOverflow.value) return;
  event.preventDefault();
  event.stopPropagation();
  dragging.value = true;
  dragStartY = event.clientY;
  dragStartScrollTop = viewport.value.scrollTop;
  document.body.style.userSelect = 'none';
  window.addEventListener('pointermove', onThumbPointerMove);
  window.addEventListener('pointerup', onThumbPointerUp);
}

function onThumbPointerMove(event) {
  if (!dragging.value) return;
  const el = viewport.value;
  const { scrollHeight, clientHeight } = el;
  const maxThumbTop = clientHeight - thumbHeight.value;
  const maxScrollTop = scrollHeight - clientHeight;
  const deltaY = event.clientY - dragStartY;
  const scrollPerPixel = maxThumbTop > 0 ? maxScrollTop / maxThumbTop : 0;
  el.scrollTop = dragStartScrollTop + deltaY * scrollPerPixel;
}

function onThumbPointerUp() {
  dragging.value = false;
  document.body.style.userSelect = '';
  window.removeEventListener('pointermove', onThumbPointerMove);
  window.removeEventListener('pointerup', onThumbPointerUp);
  if (props.autoHide && !trackVisible.value) {
    scrolling.value = false;
  }
}

// Click on the track jumps the thumb toward the click position
function onTrackPointerDown(event) {
  if (!hasOverflow.value || event.target === thumb.value) return;
  const el = viewport.value;
  const rect = el.getBoundingClientRect();
  const clickY = event.clientY - rect.top;
  const targetThumbTop = clickY - thumbHeight.value / 2;
  const maxThumbTop = el.clientHeight - thumbHeight.value;
  const maxScrollTop = el.scrollHeight - el.clientHeight;
  const clamped = Math.min(Math.max(targetThumbTop, 0), maxThumbTop);
  el.scrollTop = maxThumbTop > 0 ? (clamped / maxThumbTop) * maxScrollTop : 0;
}

onMounted(() => {
  nextTick(updateThumb);
  if (window.ResizeObserver) {
    resizeObserver = new ResizeObserver(() => updateThumb());
    resizeObserver.observe(viewport.value);
    if (viewport.value.firstElementChild) {
      resizeObserver.observe(viewport.value.firstElementChild);
    }
  }
  // Watch for content changes (e.g. groups expanding/collapsing)
  mutationObserver = new MutationObserver(() => updateThumb());
  mutationObserver.observe(viewport.value, { childList: true, subtree: true });
});

onUnmounted(() => {
  if (hideTimer) clearTimeout(hideTimer);
  if (resizeObserver) resizeObserver.disconnect();
  if (mutationObserver) mutationObserver.disconnect();
  window.removeEventListener('pointermove', onThumbPointerMove);
  window.removeEventListener('pointerup', onThumbPointerUp);
});

// Allow parent to trigger recomputation
defineExpose({ updateThumb, viewport });
</script>

<template>
  <div class="overlay-scrollbar" @pointerenter="onPointerEnter" @pointerleave="onPointerLeave">
    <div ref="viewport" class="overlay-scrollbar__viewport" @scroll="onScroll">
      <slot />
    </div>
    <div
      class="overlay-scrollbar__track"
      :class="{ 'is-visible': hasOverflow && (trackVisible || scrolling || dragging) }"
      @pointerdown="onTrackPointerDown"
    >
      <div
        ref="thumb"
        class="overlay-scrollbar__thumb"
        :class="{ 'is-dragging': dragging }"
        :style="{ height: thumbHeight + 'px', transform: `translateY(${thumbTop}px)` }"
        @pointerdown="onThumbPointerDown"
      ></div>
    </div>
  </div>
</template>

<style scoped>
.overlay-scrollbar {
  position: relative;
  height: 100%;
  width: 100%;
}

.overlay-scrollbar__viewport {
  height: 100%;
  width: 100%;
  overflow-y: auto;
  overflow-x: hidden;
  /* Hide native scrollbar without reserving layout space */
  scrollbar-width: none;
  -ms-overflow-style: none;
}

.overlay-scrollbar__viewport::-webkit-scrollbar {
  width: 0;
  height: 0;
  display: none;
}

.overlay-scrollbar__track {
  position: absolute;
  top: 2px;
  right: 2px;
  bottom: 2px;
  width: 10px;
  border-radius: 5px;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.2s ease;
  z-index: 5;
}

.overlay-scrollbar__track.is-visible {
  opacity: 1;
  pointer-events: auto;
}

.overlay-scrollbar__thumb {
  position: absolute;
  top: 0;
  right: 0;
  width: 6px;
  margin-right: 2px;
  border-radius: 4px;
  background: rgba(var(--v-theme-primary), 0.45);
  cursor: pointer;
  transition: width 0.15s ease, background-color 0.15s ease;
  will-change: transform;
}

.overlay-scrollbar__track:hover .overlay-scrollbar__thumb,
.overlay-scrollbar__thumb.is-dragging {
  width: 8px;
  background: rgba(var(--v-theme-primary), 0.7);
}
</style>
