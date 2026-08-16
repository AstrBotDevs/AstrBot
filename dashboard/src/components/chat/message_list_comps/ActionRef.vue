<template>
  <div v-if="usedRefs.length > 0" class="refs-container" @click="handleClick">
    <div class="refs-avatars">
      <div
        v-for="(ref, refIdx) in usedRefs.slice(0, 3)"
        :key="refIdx"
        class="ref-avatar"
        :style="{ zIndex: 3 - refIdx }"
      >
        <img
          v-if="ref.favicon"
          :src="ref.favicon"
          class="ref-favicon"
          @error="hideBrokenImage"
        />
        <span v-else class="ref-initial">{{ getRefInitial(ref.title) }}</span>
      </div>
      <span v-if="usedRefs.length > 3" class="refs-more">
        +{{ usedRefs.length - 3 }}
      </span>
      <span class="refs-label">
        {{ tm('refs.sources') }}
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useModuleI18n } from '@/i18n/composables';
import { computed } from 'vue';

interface RefItem {
  title?: unknown;
  favicon?: unknown;
  [key: string]: unknown;
}

interface RefCollection {
  used?: RefItem[];
  [key: string]: unknown;
}

interface DisplayRefItem {
  title: string;
  favicon?: string;
}

const props = withDefaults(
  defineProps<{
    refs?: unknown;
  }>(),
  {
    refs: undefined,
  },
);

const emit = defineEmits<{
  'open-refs': [refs: RefCollection | null];
}>();

const { tm } = useModuleI18n('features/chat');

const usedRefs = computed<DisplayRefItem[]>(() => {
  if (
    props.refs &&
    typeof props.refs === 'object' &&
    !Array.isArray(props.refs) &&
    Array.isArray((props.refs as { used?: unknown }).used)
  ) {
    return (props.refs as { used: RefItem[] }).used.map((ref) => ({
      title: typeof ref.title === 'string' ? ref.title : '',
      favicon: typeof ref.favicon === 'string' ? ref.favicon : undefined,
    }));
  }
  return [];
});

function getRefInitial(title?: unknown): string {
  if (typeof title !== 'string' || !title) {
    return '?';
  }
  return title.charAt(0).toUpperCase();
}

function hideBrokenImage(event: Event): void {
  const target = event.target;
  if (target instanceof HTMLImageElement) {
    target.style.display = 'none';
  }
}

function handleClick(): void {
  emit('open-refs', (props.refs as RefCollection | null) ?? null);
}
</script>

<style scoped>
.refs-container {
  display: flex;
  align-items: center;
  min-height: 24px;
  padding: 0 6px;
  border-radius: 8px;
  color: inherit;
  cursor: pointer;
  font-size: 12px;
  line-height: 24px;
  transition: background-color;
}

.refs-container:hover {
  background-color: rgba(103, 58, 183, 0.08);
}

.refs-avatars {
  display: flex;
  align-items: center;
  position: relative;
  min-height: 24px;
}

.ref-avatar {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  opacity: 0.9;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  position: relative;
}

.ref-avatar:not(:first-child) {
  margin-left: -8px;
}

.ref-favicon {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.ref-initial {
  font-size: 10px;
  font-weight: 600;
  color: white;
  user-select: none;
}

.refs-more {
  margin-left: 6px;
  font-size: 11px;
  color: var(--v-theme-on-surface-variant);
  opacity: 0.7;
  font-weight: 500;
}

.refs-label {
  margin-left: 6px;
  color: inherit;
  font-size: 12px;
  line-height: 24px;
}
</style>
