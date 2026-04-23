<template>
  <transition name="slide-left">
    <aside v-if="modelValue" class="reasoning-sidebar">
      <div class="reasoning-sidebar-header">
        <div class="reasoning-sidebar-title">{{ tm("reasoning.thinking") }}</div>
        <v-btn icon="mdi-close" size="small" variant="text" @click="close" />
      </div>

      <div class="reasoning-sidebar-body">
        <ReasoningTimeline
          v-if="parts.length || reasoning"
          :parts="parts"
          :reasoning="reasoning"
          :is-dark="isDark"
        />
        <div v-else class="reasoning-sidebar-empty">
          {{ tm("reasoning.thinking") }}
        </div>
      </div>
    </aside>
  </transition>
</template>

<script setup lang="ts">
import type { MessagePart } from "@/composables/useMessages";
import { useModuleI18n } from "@/i18n/composables";
import ReasoningTimeline from "@/components/chat/message_list_comps/ReasoningTimeline.vue";

defineProps<{
  modelValue: boolean;
  parts: MessagePart[];
  reasoning?: string;
  isDark?: boolean;
}>();

const emit = defineEmits<{
  "update:modelValue": [value: boolean];
}>();

const { tm } = useModuleI18n("features/chat");

function close() {
  emit("update:modelValue", false);
}
</script>

<style scoped>
.reasoning-sidebar {
  width: 380px;
  height: 100%;
  border-left: 1px solid rgba(var(--v-theme-on-surface), 0.1);
  background: rgb(var(--v-theme-surface));
  color: rgb(var(--v-theme-on-surface));
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}

.slide-left-enter-active,
.slide-left-leave-active {
  transition: all 0.2s ease;
}

.slide-left-enter-from,
.slide-left-leave-to {
  transform: translateX(100%);
  opacity: 0;
}

.reasoning-sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px 8px;
}

.reasoning-sidebar-title {
  font-size: 16px;
  font-weight: 600;
  line-height: 1.4;
  color: rgb(var(--v-theme-on-surface));
}

.reasoning-sidebar-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 0 14px 12px;
  font-size: 14.5px;
  line-height: 1.62;
}

.reasoning-sidebar-empty {
  padding: 12px 2px;
  color: rgba(var(--v-theme-on-surface), 0.54);
  font-size: 13px;
}

@media (max-width: 760px) {
  .reasoning-sidebar {
    position: fixed;
    inset: 0;
    z-index: 1300;
    width: 100vw;
    height: 100dvh;
    border-left: 0;
  }

  .reasoning-sidebar-header {
    min-height: 52px;
    padding: calc(10px + env(safe-area-inset-top)) 12px 8px;
    border-bottom: 1px solid rgba(var(--v-border-color), 0.12);
  }

  .reasoning-sidebar-body {
    padding: 0 12px calc(12px + env(safe-area-inset-bottom));
  }
}
</style>
