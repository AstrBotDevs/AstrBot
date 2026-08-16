<template>
  <div
    v-if="visible && filteredCommands.length > 0"
    class="command-suggestion-panel"
    :style="panelStyle"
  >
    <div class="command-suggestion-list">
      <div
        v-for="(cmd, index) in filteredCommands"
        :key="`${cmd.handler_full_name}:${cmd.effective_command}`"
        class="command-suggestion-item"
        :class="{ active: index === selectedIndex }"
        @click="handleSelect(index)"
        @mouseenter="handleMouseEnter(index)"
        @mousemove="handleMouseMove"
        @mouseleave="handleMouseLeave"
      >
        <div class="command-suggestion-main">
          <span class="command-name">{{
            cmd.display_signature || cmd.effective_command
          }}</span>
          <span v-if="cmd.plugin_display_name" class="command-plugin">
            {{ cmd.plugin_display_name }}
          </span>
        </div>
        <div v-if="cmd.description" class="command-description">
          {{ cmd.description }}
        </div>
      </div>
    </div>
    <div class="command-suggestion-hint">
      <span>↑↓ {{ tm('commandSuggestion.navigate') }}</span>
      <span>Enter {{ tm('commandSuggestion.select') }}</span>
      <span>Esc {{ tm('commandSuggestion.close') }}</span>
    </div>
  </div>
  <!-- Tooltip: 鼠标悬停时显示完整用途 -->
  <Teleport to="body">
    <div v-if="tooltip.visible" class="command-tooltip" :style="tooltipStyle">
      {{ tooltip.text }}
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, reactive, watch } from 'vue';
import { useModuleI18n } from '@/i18n/composables';
import type { SuggestionCommand } from './commandSuggestion';

interface Props {
  visible: boolean;
  commands: SuggestionCommand[];
  selectedIndex: number;
  isDark: boolean;
  caretPosition?: { left: number; top: number } | null;
}

const props = withDefaults(defineProps<Props>(), {
  caretPosition: null,
});

const emit = defineEmits<{
  select: [command: SuggestionCommand];
  updateSelectedIndex: [index: number];
}>();

const { tm } = useModuleI18n('features/chat');

const filteredCommands = computed(() => props.commands);

// Tooltip 状态：鼠标悬停在指令上时显示完整用途
const tooltip = reactive({
  visible: false,
  text: '',
  x: 0,
  y: 0,
});

watch(
  () => props.visible,
  (visible) => {
    if (!visible) {
      tooltip.visible = false;
    }
  },
);

const tooltipStyle = computed(() => ({
  position: 'fixed' as const,
  left: `${tooltip.x + 12}px`,
  top: `${tooltip.y + 12}px`,
  zIndex: 10000,
}));

const panelStyle = computed(() => {
  if (props.caretPosition) {
    return {
      position: 'absolute' as const,
      left: `${props.caretPosition.left}px`,
      bottom: `${props.caretPosition.top + 8}px`,
      zIndex: 1000,
    };
  }
  return {
    position: 'absolute' as const,
    left: '18px',
    bottom: '100%',
    marginBottom: '8px',
    zIndex: 1000,
  };
});

function handleSelect(index: number) {
  const cmd = props.commands[index];
  if (cmd) {
    emit('select', cmd);
  }
}

function handleMouseEnter(index: number) {
  emit('updateSelectedIndex', index);
  // 显示 tooltip
  const cmd = props.commands[index];
  if (cmd?.description) {
    tooltip.text = cmd.description;
    tooltip.visible = true;
  }
}

function handleMouseMove(e: MouseEvent) {
  tooltip.x = e.clientX;
  tooltip.y = e.clientY;
}

function handleMouseLeave() {
  tooltip.visible = false;
}
</script>

<style scoped>
.command-suggestion-panel {
  background: rgb(var(--v-theme-surface));
  border: 1px solid rgb(var(--v-theme-outline-variant));
  border-radius: 8px;
  box-shadow: 0 8px 24px rgb(24 33 43 / 16%);
  max-height: 280px;
  width: 320px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.command-suggestion-list {
  overflow-y: auto;
  flex: 1;
  padding: 4px;
}

.command-suggestion-item {
  padding: 8px 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: background-color 0.15s ease;
}

.command-suggestion-item:hover,
.command-suggestion-item.active {
  background-color: rgba(var(--v-theme-primary), 0.1);
}

.command-suggestion-main {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.command-name {
  font-family: var(--astrbot-font-mono);
  font-size: 13px;
  font-weight: 600;
  color: rgb(var(--v-theme-primary));
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.command-plugin {
  font-size: 11px;
  color: rgb(var(--v-theme-on-surface-variant));
  background: rgb(var(--v-theme-surface-variant));
  padding: 1px 6px;
  border-radius: 4px;
  white-space: nowrap;
  flex-shrink: 0;
}

.command-description {
  font-size: 12px;
  color: rgb(var(--v-theme-on-surface-variant));
  margin-top: 2px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.command-suggestion-hint {
  display: flex;
  gap: 12px;
  padding: 6px 12px;
  border-top: 1px solid rgb(var(--v-theme-outline-variant));
  font-size: 11px;
  color: rgb(var(--v-theme-on-surface-variant));
  flex-shrink: 0;
}

.command-suggestion-hint span {
  white-space: nowrap;
}
</style>

<!-- 非 scoped 样式：tooltip 通过 Teleport 渲染到 body，scoped 无法生效 -->
<style>
.command-tooltip {
  max-width: 360px;
  padding: 8px 12px;
  background: rgb(var(--v-theme-surface));
  border: 1px solid rgb(var(--v-theme-outline-variant));
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  font-size: 13px;
  color: rgb(var(--v-theme-on-surface));
  line-height: 18px;
  word-break: break-word;
  pointer-events: none;
  white-space: normal;
}
</style>
