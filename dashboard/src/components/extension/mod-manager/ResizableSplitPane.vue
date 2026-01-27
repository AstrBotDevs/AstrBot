<template>
  <div
    ref="containerRef"
    class="resizable-split-pane"
    :class="{
      'is-horizontal': isHorizontal,
      'is-dragging': isDragging,
    }"
  >
    <div class="pane-first" :style="firstPaneStyle">
      <slot name="first">
        <slot name="top" />
      </slot>
    </div>

    <div
      class="pane-divider"
      :style="dividerStyle"
      @pointerdown.prevent="onDragStart"
    >
      <div class="divider-handle" />
    </div>

    <div class="pane-second" :style="secondPaneStyle">
      <slot name="second">
        <slot name="bottom" />
      </slot>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue';

type Direction = 'vertical' | 'horizontal';

const props = withDefaults(
  defineProps<{
    modelValue: number;
    minRatio?: number;
    maxRatio?: number;
    direction?: Direction;
  }>(),
  {
    minRatio: 0.2,
    maxRatio: 0.8,
    direction: 'vertical',
  },
);

const emit = defineEmits<{
  'update:modelValue': [ratio: number];
}>();

const containerRef = ref<HTMLElement | null>(null);
const isDragging = ref(false);

const isHorizontal = computed(() => props.direction === 'horizontal');

function clampRatio(ratio: number): number {
  const min = Math.min(props.minRatio, props.maxRatio);
  const max = Math.max(props.minRatio, props.maxRatio);
  if (ratio !== ratio) return min;
  return Math.min(max, Math.max(min, ratio));
}

const clampedRatio = computed(() => clampRatio(props.modelValue));

const DIVIDER_SIZE_PX = 12;
const HALF_DIVIDER_PX = DIVIDER_SIZE_PX / 2;

const firstPaneStyle = computed<Record<string, string>>(() => {
  const ratio = clampedRatio.value;
  if (isHorizontal.value) {
    return { width: `calc(${ratio * 100}% - ${HALF_DIVIDER_PX}px)`, height: '100%' };
  }
  return { height: `calc(${ratio * 100}% - ${HALF_DIVIDER_PX}px)`, width: '100%' };
});

const secondPaneStyle = computed<Record<string, string>>(() => {
  const ratio = clampedRatio.value;
  if (isHorizontal.value) {
    return { width: `calc(${(1 - ratio) * 100}% - ${HALF_DIVIDER_PX}px)`, height: '100%' };
  }
  return { height: `calc(${(1 - ratio) * 100}% - ${HALF_DIVIDER_PX}px)`, width: '100%' };
});

const dividerStyle = computed<Record<string, string>>(() => {
  if (isHorizontal.value) {
    return {
      cursor: 'col-resize',
      width: `${DIVIDER_SIZE_PX}px`,
      height: '100%'
    };
  }

  return {
    cursor: 'row-resize',
    width: '100%',
    height: `${DIVIDER_SIZE_PX}px`
  };
});

let cleanupDocumentListeners: (() => void) | null = null;
let restoreBodyStyles: (() => void) | null = null;

let dragPointerId: number | null = null;

let rafId: number | null = null;
let pendingClientX = 0;
let pendingClientY = 0;

function scheduleRatioUpdate(): void {
  if (rafId != null) return;
  rafId = window.requestAnimationFrame(() => {
    rafId = null;
    const container = containerRef.value;
    if (!container) return;

    const rect = container.getBoundingClientRect();
    const ratio = isHorizontal.value
      ? (pendingClientX - rect.left) / rect.width
      : (pendingClientY - rect.top) / rect.height;

    emit('update:modelValue', clampRatio(ratio));
  });
}

function addDocumentListeners(): void {
  const onPointerMove = (event: PointerEvent) => {
    if (dragPointerId != null && event.pointerId !== dragPointerId) return;
    pendingClientX = event.clientX;
    pendingClientY = event.clientY;
    scheduleRatioUpdate();
  };

  const onPointerUpOrCancel = (event: PointerEvent) => {
    if (dragPointerId != null && event.pointerId !== dragPointerId) return;
    onDragEnd();
  };

  document.addEventListener('pointermove', onPointerMove);
  document.addEventListener('pointerup', onPointerUpOrCancel);
  document.addEventListener('pointercancel', onPointerUpOrCancel);

  cleanupDocumentListeners = () => {
    document.removeEventListener('pointermove', onPointerMove);
    document.removeEventListener('pointerup', onPointerUpOrCancel);
    document.removeEventListener('pointercancel', onPointerUpOrCancel);
    cleanupDocumentListeners = null;
  };
}

function applyDraggingBodyStyle(): void {
  const body = document.body;

  const prevUserSelect = body.style.userSelect;
  const prevCursor = body.style.cursor;

  body.style.userSelect = 'none';
  body.style.cursor = isHorizontal.value ? 'col-resize' : 'row-resize';

  restoreBodyStyles = () => {
    body.style.userSelect = prevUserSelect;
    body.style.cursor = prevCursor;
    restoreBodyStyles = null;
  };
}

function onDragStart(event: PointerEvent): void {
  // 仅在鼠标左键时开始；触摸/触控笔不检查 button
  if (event.pointerType === 'mouse' && event.button !== 0) return;
  if (!containerRef.value) return;

  dragPointerId = event.pointerId;

  const target = event.currentTarget as HTMLElement | null;
  target?.setPointerCapture?.(event.pointerId);

  isDragging.value = true;
  applyDraggingBodyStyle();
  addDocumentListeners();

  pendingClientX = event.clientX;
  pendingClientY = event.clientY;
  scheduleRatioUpdate();
}

function onDragEnd(): void {
  if (!isDragging.value) return;

  isDragging.value = false;
  dragPointerId = null;

  if (rafId != null) {
    window.cancelAnimationFrame(rafId);
    rafId = null;
  }

  cleanupDocumentListeners?.();
  restoreBodyStyles?.();
}

onBeforeUnmount(() => {
  onDragEnd();
});
</script>

<style scoped>
.resizable-split-pane {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  width: 100%;
  min-width: 0;
  position: relative;
  isolation: isolate;
  align-items: stretch;
}

.resizable-split-pane.is-horizontal {
  flex-direction: row;
}

.pane-first,
.pane-second {
  overflow: hidden;
  min-height: 0;
  min-width: 0;
  flex: 0 0 auto;
  display: flex;
  flex-direction: column;
  position: relative;
  z-index: 0;
}

/* 让 slot 的根节点跟随 pane 伸缩，否则会出现大量空白（pane 高度变化但内容不填充） */
:deep(.pane-first > *),
:deep(.pane-second > *) {
  flex: 1 1 auto;
  min-height: 0;
  min-width: 0;
}

.pane-divider {
  flex: 0 0 auto;
  background: rgba(var(--v-theme-on-surface), 0.06);
  position: relative;
  user-select: none;
  align-self: stretch;
  z-index: 20;
  pointer-events: auto;
  touch-action: none;
}

.resizable-split-pane.is-horizontal .pane-divider {
  height: 100%;
}

.resizable-split-pane.is-horizontal .pane-first,
.resizable-split-pane.is-horizontal .pane-second {
  height: 100%;
}

.divider-handle {
  position: absolute;
  left: 12px;
  right: 12px;
  top: 50%;
  height: 2px;
  transform: translateY(-50%);
  background: rgba(var(--v-theme-on-surface), 0.38);
  border-radius: 999px;
  pointer-events: none;
}

.resizable-split-pane.is-horizontal .divider-handle {
  top: 12px;
  bottom: 12px;
  left: 50%;
  right: auto;
  width: 2px;
  height: auto;
  transform: translateX(-50%);
}

.pane-divider:hover {
  background: rgba(var(--v-theme-on-surface), 0.10);
}

.pane-divider:hover .divider-handle,
.resizable-split-pane.is-dragging .divider-handle {
  background: rgba(var(--v-theme-on-surface), 0.62);
  box-shadow: 0 0 0 2px rgba(var(--v-theme-on-surface), 0.14);
}

.resizable-split-pane.is-dragging {
  user-select: none;
}
</style>