<template>
  <transition name="slide-left">
    <aside v-if="modelValue" class="group-panel">
      <div class="group-panel-header">
        <div class="group-panel-title">{{ tm("group.panelTitle") }}</div>
        <v-btn icon="mdi-close" size="small" variant="text" @click="close" />
      </div>

      <section class="group-profile">
        <v-avatar class="group-avatar" size="86" rounded="lg">
          <img :src="groupAvatar" alt="" />
        </v-avatar>
        <div class="group-name">{{ groupName }}</div>
        <p v-if="groupDescription" class="group-description">
          {{ groupDescription }}
        </p>
      </section>

      <section class="group-bots-section">
        <div class="group-bots-header">
          <div class="group-bots-title">{{ tm("group.members") }}</div>
          <v-btn
            size="small"
            variant="tonal"
            prepend-icon="mdi-robot-outline"
            @click="$emit('addBot')"
          >
            {{ tm("group.addBot") }}
          </v-btn>
        </div>

        <div v-if="!bots.length" class="group-empty">
          {{ tm("group.addBotHint") }}
        </div>

        <div v-else class="group-bot-list">
          <div v-for="bot in bots" :key="bot.bot_id" class="group-bot-row">
            <v-avatar size="34" rounded="lg">
              <img :src="bot.avatar || defaultGroupAvatar" alt="" />
            </v-avatar>
            <div class="group-bot-meta">
              <div class="group-bot-name-line">
                <div class="group-bot-name">@{{ bot.name }}</div>
                <v-chip class="group-bot-chip" size="x-small" variant="tonal">
                  {{ tm("group.botBadge") }}
                </v-chip>
              </div>
              <div class="group-bot-config">{{ bot.conf_id }}</div>
            </div>
            <v-btn
              icon="mdi-delete-outline"
              size="x-small"
              variant="text"
              color="error"
              @click="$emit('deleteBot', bot)"
            />
          </div>
        </div>
      </section>
    </aside>
  </transition>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useModuleI18n } from "@/i18n/composables";
import type { GroupBot, GroupProfile } from "@/composables/useMessages";
import defaultGroupAvatar from "@/assets/images/chatui-group-default-avatar.png";

const props = defineProps<{
  modelValue: boolean;
  group: GroupProfile | null;
  bots: GroupBot[];
  fallbackName: string;
}>();

const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  addBot: [];
  deleteBot: [bot: GroupBot];
}>();

const { tm } = useModuleI18n("features/chat");

const groupName = computed(() => props.group?.name || props.fallbackName);
const groupAvatar = computed(() => props.group?.avatar || defaultGroupAvatar);
const groupDescription = computed(() => props.group?.description || "");

function close() {
  emit("update:modelValue", false);
}
</script>

<style scoped>
.group-panel {
  width: 360px;
  height: 100%;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  border-left: 1px solid rgba(var(--v-border-color), 0.16);
  background: rgb(var(--v-theme-surface));
  color: rgb(var(--v-theme-on-surface));
}

.slide-left-enter-active,
.slide-left-leave-active {
  transition: all 0.3s ease;
}

.slide-left-enter-from,
.slide-left-leave-to {
  transform: translateX(100%);
  opacity: 0;
}

.group-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
  padding: 14px 16px 8px;
}

.group-panel-title,
.group-bots-title {
  color: rgb(var(--v-theme-on-surface));
  font-size: 16px;
  font-weight: 600;
  line-height: 1.4;
}

.group-bots-title {
  font-size: 14px;
}

.group-profile {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 24px 22px 22px;
  text-align: center;
}

.group-avatar img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.group-name {
  max-width: 100%;
  margin-top: 12px;
  font-size: 18px;
  font-weight: 800;
  overflow-wrap: anywhere;
}

.group-description {
  margin: 8px 0 0;
  color: rgba(var(--v-theme-on-surface), 0.62);
  font-size: 13px;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.group-bots-section {
  flex: 1;
  min-height: 0;
  padding: 0 16px 18px;
  overflow-y: auto;
}

.group-bots-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 12px;
}

.group-empty {
  color: rgba(var(--v-theme-on-surface), 0.62);
  font-size: 13px;
}

.group-bot-list {
  display: grid;
  gap: 8px;
}

.group-bot-row {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 50px;
  padding: 8px 10px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.1);
  border-radius: 8px;
}

.group-bot-row img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.group-bot-meta {
  min-width: 0;
  flex: 1;
}

.group-bot-name-line,
.group-bot-config {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.group-bot-name-line {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.group-bot-name {
  min-width: 0;
  font-size: 14px;
  font-weight: 650;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.group-bot-chip {
  flex-shrink: 0;
  height: 18px;
  font-size: 11px;
  font-weight: 500;
}

.group-bot-config {
  color: rgba(var(--v-theme-on-surface), 0.62);
  font-size: 12px;
}

@media (max-width: 760px) {
  .group-panel {
    position: fixed;
    inset: 0;
    z-index: 1300;
    width: 100vw;
    height: 100dvh;
    border-left: 0;
  }

  .group-panel-header {
    min-height: 52px;
    padding: calc(10px + env(safe-area-inset-top)) 12px 8px;
    border-bottom: 1px solid rgba(var(--v-border-color), 0.12);
  }

  .group-profile {
    padding: 22px 18px 20px;
  }

  .group-bots-section {
    padding: 0 12px calc(14px + env(safe-area-inset-bottom));
  }
}
</style>
