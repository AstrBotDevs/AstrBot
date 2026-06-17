<template>
  <div
    v-if="visible && filteredCommands.length > 0"
    class="command-suggestion-panel"
    :class="{ 'is-dark': isDark }"
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
          <span class="command-name">{{ cmd.effective_command }}</span>
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
      <span>↑↓ {{ tm("commandSuggestion.navigate") }}</span>
      <span>Enter {{ tm("commandSuggestion.select") }}</span>
      <span>Esc {{ tm("commandSuggestion.close") }}</span>
    </div>
  </div>
  <!-- Tooltip: 鼠标悬停时显示完整用途 -->
  <Teleport to="body">
    <div
      v-if="tooltip.visible"
      class="command-tooltip"
      :class="{ 'is-dark': isDark }"
      :style="tooltipStyle"
    >
      {{ tooltip.text }}
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, reactive } from "vue";
import { useModuleI18n } from "@/i18n/composables";

export interface SuggestionCommand {
  handler_full_name: string;
  effective_command: string;
  description: string;
  plugin_display_name: string | null;
  enabled: boolean;
  reserved: boolean;
}

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

const { tm } = useModuleI18n("features/chat");

const filteredCommands = computed(() => props.commands);

// Tooltip 状态：鼠标悬停在指令上时显示完整用途
const tooltip = reactive({
  visible: false,
  text: "",
  x: 0,
  y: 0,
});

const tooltipStyle = computed(() => ({
  position: "fixed" as const,
  left: `${tooltip.x + 12}px`,
  top: `${tooltip.y + 12}px`,
  zIndex: 10000,
}));

const panelStyle = computed(() => {
  if (props.caretPosition) {
    return {
      position: "absolute" as const,
      left: `${props.caretPosition.left}px`,
      bottom: `${props.caretPosition.top + 8}px`,
      zIndex: 1000,
    };
  }
  return {
    position: "absolute" as const,
    left: "18px",
    bottom: "100%",
    marginBottom: "8px",
    zIndex: 1000,
  };
});

function handleSelect(index: number) {
  const cmd = props.commands[index];
  if (cmd) {
    emit("select", cmd);
  }
}

function handleMouseEnter(index: number) {
  emit("updateSelectedIndex", index);
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
  background: #ffffff;
  border: 1px solid #e0e0e0;
  border-radius: 12px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
  max-height: 280px;
  width: 320px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.command-suggestion-panel.is-dark {
  background: #1e1e1e;
  border-color: #404040;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.4);
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

.is-dark .command-suggestion-item:hover,
.is-dark .command-suggestion-item.active {
  background-color: rgba(255, 255, 255, 0.08);
}

.command-suggestion-main {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.command-name {
  font-family: "Fira Code", "Consolas", monospace;
  font-size: 13px;
  font-weight: 600;
  color: rgb(var(--v-theme-primary));
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.command-plugin {
  font-size: 11px;
  color: #888;
  background: rgba(0, 0, 0, 0.05);
  padding: 1px 6px;
  border-radius: 4px;
  white-space: nowrap;
  flex-shrink: 0;
}

.is-dark .command-plugin {
  color: #aaa;
  background: rgba(255, 255, 255, 0.08);
}

.command-description {
  font-size: 12px;
  color: #666;
  margin-top: 2px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.is-dark .command-description {
  color: #999;
}

.command-suggestion-hint {
  display: flex;
  gap: 12px;
  padding: 6px 12px;
  border-top: 1px solid #f0f0f0;
  font-size: 11px;
  color: #aaa;
  flex-shrink: 0;
}

.is-dark .command-suggestion-hint {
  border-top-color: #333;
  color: #666;
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
  background: #ffffff;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  font-size: 13px;
  color: #333;
  line-height: 1.5;
  word-break: break-word;
  pointer-events: none;
  white-space: normal;
}

.command-tooltip.is-dark {
  background: #2d2d2d;
  border-color: #404040;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.5);
  color: #e0e0e0;
}
</style>
