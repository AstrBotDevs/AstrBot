<script setup lang="ts">
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ChevronDown } from "@lucide/vue";
import StyledMenu from "@/components/shared/StyledMenu.vue";
import { useModuleI18n } from "@/i18n/composables";
import ChatUILogo from "@/components/chat/ChatUILogo.vue";
import ProviderModelMenu from "@/components/chat/ProviderModelMenu.vue";
import { useChatHeaderStore } from "@/stores/chatHeader";

const route = useRoute();
const router = useRouter();
const { tm } = useModuleI18n("features/provider");
const isProviderWorkspace = computed(() => route.params.conversationId === "models");
const isOnboardingWorkspace = computed(() => route.params.conversationId === "onboarding");
const providerTypes = computed(() => [
  { value: "chat_completion", label: tm("providers.tabs.chatCompletion") },
  { value: "speech_to_text", label: tm("providers.tabs.speechToText") },
  { value: "text_to_speech", label: tm("providers.tabs.textToSpeech") },
]);
const selectedType = computed(() =>
  providerTypes.value.find((type) => type.value === route.query.type) || providerTypes.value[0],
);
const chatHeader = useChatHeaderStore();
const title = computed(() => {
  const t = chatHeader.title.trim();
  const s = chatHeader.subtitle.trim();
  if (t && s) return `${s} / ${t}`;
  return t || s;
});
</script>

<template>
  <div
    class="chat-toolbar-context"
    :class="{ 'chat-toolbar-context--onboarding': isOnboardingWorkspace }"
  >
    <div v-if="isOnboardingWorkspace" class="chat-onboarding-brand Outfit">
      <ChatUILogo class="chat-onboarding-brand-logo" />
      <span class="chat-onboarding-brand-copy">
        <span class="chat-onboarding-brand-name">AstrBot</span>
        <span class="chat-onboarding-brand-mode">ChatUI</span>
      </span>
    </div>
    <StyledMenu v-else-if="isProviderWorkspace" location="bottom start" :offset="8">
      <template #activator="{ props }">
        <button v-bind="props" type="button" class="provider-type-trigger">
          {{ selectedType.label }}
          <ChevronDown :size="16" :stroke-width="1.75" />
        </button>
      </template>
      <v-list-item
        v-for="type in providerTypes"
        :key="type.value"
        class="styled-menu-item"
        :active="selectedType.value === type.value"
        @click="router.push({ path: route.path, query: { ...route.query, type: type.value } })"
      >
        <v-list-item-title>{{ type.label }}</v-list-item-title>
      </v-list-item>
    </StyledMenu>
    <ProviderModelMenu v-else variant="header" />
    <span v-if="title" class="chat-toolbar-context-title" :title="title">{{
      title
    }}</span>
  </div>
</template>

<style scoped>
.chat-onboarding-brand {
  min-width: 0;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: rgb(var(--v-theme-on-surface));
  line-height: 1.05;
  user-select: none;
}

.chat-onboarding-brand-logo {
  width: 22px;
  height: 22px;
  flex: 0 0 22px;
  display: block;
}

.chat-onboarding-brand-copy {
  min-width: 0;
  display: inline-flex;
  align-items: baseline;
  gap: 5px;
}

.chat-onboarding-brand-name {
  font-size: 18px;
  font-weight: 800;
}

.chat-onboarding-brand-mode {
  color: rgba(var(--v-theme-on-surface), 0.62);
  font-size: 18px;
  font-weight: 500;
}

.provider-type-trigger {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  height: 20px;
  color: rgb(var(--v-theme-on-surface));
  font-size: 0.8125rem;
  font-weight: 600;
  white-space: nowrap;
}

.chat-toolbar-context {
  display: flex;
  min-width: 0;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
}

/* Keep the selector compact enough to stack with the title on narrow screens. */
.chat-toolbar-context :deep(.provider-select-menu) {
  height: 20px;
  display: flex;
}

.chat-toolbar-context :deep(.provider-trigger--header) {
  height: 20px;
}

.chat-toolbar-context :deep(.provider-trigger--header .provider-trigger-title) {
  font-size: 0.8125rem;
  line-height: 20px;
}

.chat-toolbar-context
  :deep(.provider-trigger--header .provider-trigger-chevron) {
  font-size: 16px;
}

.chat-toolbar-context-title {
  max-width: 32vw;
  color: rgba(var(--v-theme-on-surface), 0.62);
  font-size: 0.6875rem;
  font-weight: 500;
  line-height: 1.2;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

@media (max-width: 959.98px) {
  .chat-toolbar-context--onboarding {
    flex-direction: row;
    align-items: center;
    gap: 10px;
  }

  .chat-toolbar-context--onboarding .chat-onboarding-brand {
    flex-shrink: 0;
    gap: 6px;
  }

  .chat-toolbar-context--onboarding .chat-onboarding-brand-logo {
    width: 19px;
    height: 19px;
    flex: 0 0 19px;
  }

  .chat-toolbar-context--onboarding .chat-onboarding-brand-name,
  .chat-toolbar-context--onboarding .chat-onboarding-brand-mode {
    font-size: 15px;
  }

  .chat-toolbar-context--onboarding .chat-toolbar-context-title {
    max-width: 44vw;
    padding-left: 10px;
    border-left: 1px solid rgba(var(--v-theme-on-surface), 0.16);
    font-size: 0.8125rem;
    line-height: 1.2;
  }
}

@media (max-width: 599.98px) {
  .chat-toolbar-context--onboarding .chat-onboarding-brand-mode {
    display: none;
  }
}

@media (min-width: 960px) {
  .chat-toolbar-context {
    max-width: min(
      300px,
      calc((100vw - var(--astrbot-chat-sidebar-width, 0px)) * 0.3 - 32px)
    );
    flex-direction: row;
    align-items: center;
  }

  /* Center over the chat pane, independently of the model and action widths. */
  .chat-toolbar-context-title {
    position: absolute;
    top: 50%;
    left: calc(50% + (var(--astrbot-chat-sidebar-width, 0px) - var(--astrbot-active-workbench-width, 0px)) / 2);
    width: max(
      0px,
      min(
        calc((100% - var(--astrbot-chat-sidebar-width, 0px) - var(--astrbot-active-workbench-width, 0px)) * 0.4),
        calc(100% - var(--astrbot-chat-sidebar-width, 0px) - var(--astrbot-active-workbench-width, 0px) - 440px)
      )
    );
    max-width: none;
    transform: translate(-50%, -50%);
    font-size: 0.8125rem;
    text-align: center;
  }
}
</style>
