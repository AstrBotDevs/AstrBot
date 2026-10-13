<template>
  <v-dialog
    :model-value="modelValue"
    max-width="880"
    height="580"
    max-height="calc(100dvh - 48px)"
    :aria-label="t('core.common.settings')"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <v-card class="chat-settings">
      <aside class="settings-sidebar">
        <div class="settings-sidebar-header">
          <v-btn
            icon="mdi-close"
            variant="text"
            size="small"
            :aria-label="t('core.common.close')"
            @click="emit('update:modelValue', false)"
          />
          <span>{{ t("core.common.settings") }}</span>
        </div>
        <nav class="settings-nav" :aria-label="t('core.common.settings')">
          <button
            v-for="section in sections"
            :key="section.id"
            type="button"
            class="settings-nav-item"
            :class="{ active: activeSection === section.id }"
            :aria-pressed="activeSection === section.id"
            @click="activeSection = section.id"
          >
            <v-icon :icon="section.icon" size="18" />
            {{ section.title }}
          </button>
        </nav>
      </aside>

      <div class="settings-main">
        <v-card-title class="text-h3 pa-4 pb-0 pl-6 settings-heading">
          {{ tm(`settings.${activeSection}`) }}
        </v-card-title>
        <v-card-text class="settings-content">
          <div v-if="activeSection === 'general'" class="settings-list">
            <div class="settings-item">
              <div class="settings-item-title">
                {{ tm("settings.appearance") }}
              </div>
              <v-select
                :model-value="customizer.themeMode"
                :items="themeOptions"
                :aria-label="tm('settings.appearance')"
                variant="outlined"
                density="compact"
                hide-details
                @update:model-value="customizer.SET_THEME_MODE($event)"
              />
            </div>
            <div class="settings-item">
              <div class="settings-item-title">
                {{ t("core.common.language") }}
              </div>
              <v-select
                :model-value="locale"
                :items="languageOptions"
                item-title="label"
                item-value="value"
                :aria-label="t('core.common.language')"
                variant="outlined"
                density="compact"
                hide-details
                @update:model-value="switchLanguage($event)"
              />
            </div>
          </div>

          <div v-else class="settings-list">
            <div class="settings-item settings-item-switch">
              <div>
                <div class="settings-item-title">
                  {{ tm("settings.streaming") }}
                </div>
                <div class="settings-item-subtitle">
                  {{ tm("settings.streamingHint") }}
                </div>
              </div>
              <v-switch
                :model-value="enableStreaming"
                :aria-label="tm('settings.streaming')"
                color="primary"
                inset
                hide-details
                density="compact"
                @update:model-value="emit('update:enableStreaming', !!$event)"
              />
            </div>
            <div class="settings-item settings-item-switch">
              <div>
                <div class="settings-item-title">
                  {{ tm("settings.reasoning") }}
                </div>
                <div class="settings-item-subtitle">
                  {{ tm("settings.reasoningHint") }}
                </div>
              </div>
              <v-switch
                :model-value="enableReasoning"
                :aria-label="tm('settings.reasoning')"
                color="primary"
                inset
                hide-details
                density="compact"
                @update:model-value="emit('update:enableReasoning', !!$event)"
              />
            </div>
            <div class="settings-item">
              <div class="settings-item-title">
                {{ tm("shortcuts.sendKey.title") }}
              </div>
              <v-select
                :model-value="sendShortcut"
                :items="shortcutOptions"
                :aria-label="tm('shortcuts.sendKey.title')"
                variant="outlined"
                density="compact"
                hide-details
                @update:model-value="emit('update:sendShortcut', $event)"
              />
            </div>
            <div class="settings-item">
              <div class="settings-item-title">{{ tm("transport.title") }}</div>
              <v-select
                :model-value="transportMode"
                :items="transportOptions"
                :aria-label="tm('transport.title')"
                variant="outlined"
                density="compact"
                hide-details
                @update:model-value="emit('update:transportMode', $event)"
              />
            </div>
          </div>
        </v-card-text>
      </div>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import {
  useI18n,
  useLanguageSwitcher,
  useModuleI18n,
} from "@/i18n/composables";
import { useCustomizerStore } from "@/stores/customizer";
import type { TransportMode } from "@/composables/useMessages";

defineProps<{
  modelValue: boolean;
  enableStreaming: boolean;
  enableReasoning: boolean;
  sendShortcut: "enter" | "shift_enter";
  transportMode: TransportMode;
}>();

const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  "update:enableStreaming": [value: boolean];
  "update:enableReasoning": [value: boolean];
  "update:sendShortcut": [value: "enter" | "shift_enter"];
  "update:transportMode": [value: TransportMode];
}>();

const { t } = useI18n();
const { tm } = useModuleI18n("features/chat");
const { locale, languageOptions, switchLanguage } = useLanguageSwitcher();
const customizer = useCustomizerStore();
const activeSection = ref("general");
const sections = computed(() => [
  { id: "general", title: tm("settings.general"), icon: "mdi-cog-outline" },
  { id: "chat", title: tm("settings.chat"), icon: "mdi-message-outline" },
]);
const themeOptions = computed(() => [
  { title: tm("settings.light"), value: "light" },
  { title: tm("settings.dark"), value: "dark" },
  { title: tm("settings.system"), value: "system" },
]);
const shortcutOptions = computed(() => [
  { title: tm("shortcuts.sendKey.enterToSend"), value: "enter" },
  { title: tm("shortcuts.sendKey.shiftEnterToSend"), value: "shift_enter" },
]);
const transportOptions = computed(() => [
  { title: tm("transport.sse"), value: "sse" },
  { title: tm("transport.websocket"), value: "websocket" },
]);
</script>

<style scoped>
.chat-settings {
  --settings-border: rgba(var(--v-theme-on-surface), 0.13);
  --settings-divider: rgba(var(--v-theme-on-surface), 0.09);
  display: grid !important;
  grid-template-columns: 200px minmax(0, 1fr);
  height: 100%;
  min-height: 0;
  overflow: hidden !important;
  border: 1px solid var(--settings-border);
  border-radius: 20px !important;
  background: rgb(var(--v-theme-surface));
}

.settings-sidebar {
  padding: 16px 12px;
  border-right: 1px solid var(--settings-divider);
}

.settings-sidebar-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 24px;
  font-size: 0.9rem;
  font-weight: 700;
}

.settings-nav {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.settings-nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 42px;
  padding: 8px 12px;
  border-radius: 8px;
  color: rgb(var(--v-theme-on-surface));
  font: inherit;
  font-size: 0.88rem;
  font-weight: 680;
  text-align: left;
}

.settings-nav-item:hover {
  background: rgba(var(--v-theme-on-surface), 0.045);
}

.settings-nav-item.active {
  background: rgba(var(--v-theme-on-surface), 0.07);
  color: rgb(var(--v-theme-on-surface));
}

.settings-nav-item:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
}

.settings-main {
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.settings-heading {
  flex: 0 0 auto;
  padding-top: 28px !important;
  font-weight: 780;
}

.settings-content {
  min-height: 0;
  overflow-y: auto;
  padding: 24px !important;
}

.settings-list {
  border: 1px solid var(--settings-border);
  border-radius: 10px;
  overflow: hidden;
}

.settings-item {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(160px, 42%);
  gap: 18px;
  align-items: center;
  min-height: 76px;
  padding: 16px;
  border-bottom: 1px solid var(--settings-divider);
}

.settings-item:last-child {
  border-bottom: 0;
}

.settings-item-title {
  font-size: 0.88rem;
  font-weight: 700;
  line-height: 1.4;
}

.settings-item-subtitle {
  margin-top: 4px;
  color: rgba(var(--v-theme-on-surface), 0.64);
  font-size: 0.78rem;
  line-height: 1.5;
}

.settings-item-switch {
  grid-template-columns: minmax(0, 1fr) auto;
}

.settings-item :deep(.v-field) {
  border-radius: 10px;
  font-size: 0.86rem;
}

.settings-item :deep(.v-input) {
  min-width: 0;
}

@media (max-width: 600px) {
  .chat-settings {
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: auto minmax(0, 1fr);
  }

  .settings-sidebar {
    border-right: 0;
    border-bottom: 1px solid var(--settings-divider);
    padding: 12px;
  }

  .settings-sidebar-header {
    margin-bottom: 12px;
  }

  .settings-nav {
    flex-direction: row;
  }

  .settings-nav-item {
    flex: 1;
  }

  .settings-item:not(.settings-item-switch) {
    grid-template-columns: minmax(0, 1fr);
    gap: 10px;
  }

  .settings-content {
    padding: 16px !important;
  }
}
</style>
