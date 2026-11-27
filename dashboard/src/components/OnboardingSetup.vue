<template>
  <section class="onboarding-chat conversation-stack">
    <div v-if="!ready" class="onboarding-loading">
      <v-progress-circular indeterminate size="32" width="3" color="primary" />
    </div>

    <template v-else>
      <section
        ref="scrollContainer"
        class="messages-panel onboarding-stream"
        tabindex="0"
        @scroll.passive="handleStreamScroll"
      >
        <div ref="streamFeed" class="messages-list-shell stream-feed">
          <template v-for="entry in timeline" :key="entry.id">
            <!-- Real LLM chat segment rendered with native ChatMessageList -->
            <div v-if="entry.kind === 'chat'" class="stream-chat-segment">
              <ChatMessageList
                :messages="entry.records"
                :is-dark="isDark"
                :is-message-streaming="isChatRecordStreaming"
                @button-click="handleButtonClick"
                @configure-models="reopenWidget('model')"
              />
            </div>

            <!-- Guide User turn -->
            <div
              v-else-if="entry.role === 'user' && entry.revealed !== false"
              class="message-row from-user"
            >
              <div class="message-stack">
                <div class="message-bubble user">
                  <div class="plain-content">{{ resolveDisplayedText(entry) }}</div>
                </div>
              </div>
            </div>

            <!-- Guide Assistant turn + optional interactive Widget -->
            <div
              v-else-if="entry.role === 'assistant' && entry.revealed !== false"
              class="message-row from-bot"
            >
              <v-avatar class="bot-avatar" :size="32">
                <span class="bot-avatar-symbol" aria-hidden="true">✦</span>
              </v-avatar>

              <div class="message-stack">
                <div v-if="resolveEntryText(entry)" class="message-bubble bot">
                  <p class="agent-copy">{{ resolveDisplayedText(entry) }}</p>
                </div>

                <!-- Inline Widget: Usage Notice -->
                <div
                  v-if="entry.widget === 'notice' && entry.typingDone !== false"
                  class="widget-card"
                  :class="`widget-card--${entry.widgetStatus}`"
                >
                  <Transition name="widget-fold" mode="out-in">
                    <div
                      v-if="entry.widgetStatus === 'active'"
                      key="active"
                      class="widget-card__pane"
                    >
                      <div class="widget-card__header">
                        <div class="widget-card__title">
                          <v-icon icon="mdi-shield-check-outline" size="18" color="primary" />
                          <h2>{{ tm('guide.notice') }}</h2>
                        </div>
                        <span class="widget-badge widget-badge--active">
                          {{ tm('guide.statusConfirm') }}
                        </span>
                      </div>
                      <div class="widget-card__body widget-card__body--notice">
                        <ReadmeDialog embedded :show="true" mode="first-notice" />
                      </div>
                      <div class="widget-card__footer">
                        <v-btn
                          variant="text"
                          :disabled="busy"
                          @click="close"
                        >
                          {{ tm('guide.skipAll') }}
                        </v-btn>
                        <v-btn
                          variant="tonal"
                          color="primary"
                          append-icon="mdi-arrow-right"
                          :disabled="busy"
                          @click="confirmNotice"
                        >
                          {{ tm('guide.confirmContinue') }}
                        </v-btn>
                      </div>
                    </div>
                    <div v-else key="receipt" class="widget-card__pane">
                      <div class="widget-receipt">
                        <div class="widget-receipt__info">
                          <v-icon
                            class="widget-receipt__icon"
                            icon="mdi-check-circle"
                            size="18"
                            color="success"
                          />
                          <span>{{ tm('guide.summaryNoticeDone') }}</span>
                        </div>
                        <v-btn
                          size="small"
                          variant="text"
                          @click="toggleNoticeExpanded(entry)"
                        >
                          {{ tm(entry.expanded ? 'guide.collapse' : 'guide.view') }}
                        </v-btn>
                      </div>
                      <div
                        class="notice-expand-grid"
                        :class="{ 'notice-expand-grid--open': entry.expanded }"
                      >
                        <div class="notice-expand-grid__inner">
                          <div
                            v-if="entry.expandedMounted"
                            class="widget-card__body widget-card__body--notice widget-card__body--reopened"
                          >
                            <ReadmeDialog embedded :show="true" mode="first-notice" />
                          </div>
                        </div>
                      </div>
                    </div>
                  </Transition>
                </div>

                <!-- Inline Widget: AI Model Configuration -->
                <div
                  v-else-if="entry.widget === 'model' && entry.typingDone !== false"
                  class="widget-card"
                  :class="`widget-card--${entry.widgetStatus}`"
                >
                  <Transition name="widget-fold" mode="out-in">
                    <div
                      v-if="entry.widgetStatus === 'active'"
                      key="active"
                      class="widget-card__pane"
                    >
                      <div class="widget-card__header">
                        <div class="widget-card__title">
                          <v-icon icon="mdi-creation-outline" size="18" color="primary" />
                          <h2>{{ tm('guide.modelTitle') }}</h2>
                        </div>
                        <span class="widget-badge widget-badge--active">
                          {{ tm('guide.statusPending') }}
                        </span>
                      </div>
                      <div class="widget-card__body">
                        <v-alert
                          v-if="configError"
                          type="error"
                          variant="tonal"
                          class="mb-4"
                          role="alert"
                        >
                          {{ configError }}
                        </v-alert>
                        <OnboardingModel
                          :ref="(el) => setModelFormRef(entry.id, el)"
                          :disabled="busy"
                          @update:busy="busy = $event"
                        />
                      </div>
                      <div class="widget-card__footer widget-card__footer--split">
                        <v-btn
                          variant="text"
                          :disabled="busy"
                          @click="skipModel"
                        >
                          {{ tm('guide.skipStep') }}
                        </v-btn>
                        <div class="widget-card__actions">
                          <v-btn
                            variant="tonal"
                            prepend-icon="mdi-connection"
                            :loading="Boolean(modelForm?.testing)"
                            :disabled="busy || !modelForm?.ready"
                            @click="testModel"
                          >
                            {{ tm('guide.testConnection') }}
                          </v-btn>
                          <v-btn
                            variant="tonal"
                            color="primary"
                            append-icon="mdi-arrow-right"
                            :loading="busy && !modelForm?.testing"
                            :disabled="busy || !modelForm?.ready"
                            @click="saveModel"
                          >
                            {{ tm('guide.saveContinue') }}
                          </v-btn>
                        </div>
                      </div>
                    </div>
                    <div v-else key="receipt" class="widget-receipt">
                      <div class="widget-receipt__info">
                        <v-icon
                          class="widget-receipt__icon"
                          :icon="entry.widgetStatus === 'done' ? 'mdi-check-circle' : 'mdi-arrow-right-circle-outline'"
                          size="18"
                          :color="entry.widgetStatus === 'done' ? 'success' : undefined"
                        />
                        <span>{{ resolveSummaryText(entry) }}</span>
                      </div>
                      <v-btn
                        size="small"
                        variant="text"
                        :disabled="busy || platformLoading || isChatRunning"
                        @click="reopenWidget('model')"
                      >
                        {{ tm(entry.widgetStatus === 'done' ? 'guide.edit' : 'guide.configure') }}
                      </v-btn>
                    </div>
                  </Transition>
                </div>

                <!-- Inline Widget: Try Model -->
                <div
                  v-else-if="entry.widget === 'trial' && entry.typingDone !== false"
                  class="widget-card"
                  :class="`widget-card--${entry.widgetStatus}`"
                >
                  <Transition name="widget-fold" mode="out-in">
                    <div
                      v-if="entry.widgetStatus === 'active'"
                      key="active"
                      class="widget-card__pane"
                    >
                      <div class="widget-card__header">
                        <div class="widget-card__title">
                          <v-icon icon="mdi-chat-processing-outline" size="18" color="primary" />
                          <h2>{{ tm('guide.trialTitle') }}</h2>
                        </div>
                        <span class="widget-badge widget-badge--ready" :title="selectedModel">
                          <span class="status-dot" aria-hidden="true" />
                          <span class="widget-badge__label">{{ selectedModel }}</span>
                        </span>
                      </div>
                      <div class="widget-card__body widget-card__body--trial">
                        <p class="trial-hint">{{ tm('guide.trialHint') }}</p>
                        <div class="starter-prompts">
                          <button
                            v-for="(promptKey, chipIndex) in starterPromptKeys"
                            :key="promptKey"
                            type="button"
                            class="starter-chip"
                            :style="{ '--chip-index': chipIndex }"
                            :disabled="busy || isChatRunning || chatInitializing"
                            @click="sendLiveMessage(tm(promptKey))"
                          >
                            <v-icon icon="mdi-star-four-points-outline" size="15" />
                            <span>{{ tm(promptKey) }}</span>
                          </button>
                        </div>
                      </div>
                      <div class="widget-card__footer">
                        <v-btn
                          variant="text"
                          :disabled="busy || isChatRunning"
                          @click="reopenWidget('model')"
                        >
                          {{ tm('guide.changeModel') }}
                        </v-btn>
                        <v-btn
                          variant="tonal"
                          color="primary"
                          append-icon="mdi-arrow-right"
                          :disabled="busy || isChatRunning"
                          @click="openPlatformStep()"
                        >
                          {{ tm('guide.continuePlatform') }}
                        </v-btn>
                      </div>
                    </div>
                    <div v-else key="receipt" class="widget-receipt">
                      <div class="widget-receipt__info">
                        <v-icon
                          class="widget-receipt__icon"
                          :icon="entry.widgetStatus === 'done' ? 'mdi-check-circle' : 'mdi-arrow-right-circle-outline'"
                          size="18"
                          :color="entry.widgetStatus === 'done' ? 'success' : undefined"
                        />
                        <span>{{ resolveSummaryText(entry) }}</span>
                      </div>
                    </div>
                  </Transition>
                </div>

                <!-- Inline Widget: Messaging Platform Adapter -->
                <div
                  v-else-if="entry.widget === 'platform' && entry.typingDone !== false"
                  class="widget-card"
                  :class="`widget-card--${entry.widgetStatus}`"
                >
                  <Transition name="widget-fold" mode="out-in">
                    <div
                      v-if="entry.widgetStatus === 'active'"
                      key="active"
                      class="widget-card__pane"
                    >
                      <div class="widget-card__header">
                        <div class="widget-card__title">
                          <v-icon icon="mdi-robot-outline" size="18" color="primary" />
                          <h2>{{ tm('guide.platform') }}</h2>
                        </div>
                        <span class="widget-badge widget-badge--active">
                          {{ tm('guide.statusPending') }}
                        </span>
                      </div>
                      <div class="widget-card__body">
                        <v-alert
                          v-if="configError"
                          type="error"
                          variant="tonal"
                          class="mb-4"
                          role="alert"
                        >
                          {{ configError }}
                        </v-alert>
                        <v-alert
                          v-if="platformError"
                          type="error"
                          variant="tonal"
                          class="mb-4"
                          role="alert"
                        >
                          {{ platformError }}
                        </v-alert>
                        <v-progress-linear
                          v-if="platformLoading"
                          indeterminate
                          color="primary"
                          class="mb-4"
                        />
                        <template v-else-if="!configError">
                          <v-select
                            v-if="configuredPlatforms.length"
                            :model-value="selectedPlatformId"
                            :items="platformChoices"
                            :label="tm('guide.adapter')"
                            variant="outlined"
                            density="compact"
                            hide-details
                            class="mb-4"
                            :disabled="busy"
                            @update:model-value="selectPlatform"
                          />
                          <div v-if="platformDraft" :inert="busy">
                            <AddNewPlatform
                              :key="selectedPlatformId"
                              :ref="(el) => setPlatformFormRef(entry.id, el)"
                              embedded
                              :show="true"
                              updating-mode
                              :updating-platform-config="platformDraft"
                              :metadata="existingPlatformMetadata"
                              :config_data="platformConfig"
                              @show-toast="platformError = $event.type === 'error' ? $event.message : ''"
                            />
                          </div>
                          <AddNewPlatform
                            v-else
                            :ref="(el) => setPlatformFormRef(entry.id, el)"
                            embedded
                            :show="true"
                            :metadata="platformMetadata"
                            :config_data="platformConfig"
                            @refresh-config="loadPlatforms"
                            @update:busy="busy = $event"
                            @show-toast="platformError = $event.type === 'error' ? $event.message : ''"
                          />
                        </template>
                        <v-btn v-else variant="text" @click="loadPlatforms()">
                          {{ tm('guide.retry') }}
                        </v-btn>
                      </div>
                      <div class="widget-card__footer widget-card__footer--platform">
                        <span id="guide-adapter-skip-hint" class="widget-card__hint">
                          {{ tm('guide.adapterSkipHint') }}
                        </span>
                        <div class="widget-card__actions">
                          <v-btn
                            variant="text"
                            :disabled="busy || platformLoading"
                            aria-describedby="guide-adapter-skip-hint"
                            @click="skipPlatform"
                          >
                            {{ tm('guide.skipStep') }}
                          </v-btn>
                          <v-btn
                            variant="tonal"
                            color="primary"
                            append-icon="mdi-arrow-right"
                            :loading="busy"
                            :disabled="platformSaveDisabled"
                            @click="savePlatform"
                          >
                            {{ tm('guide.saveContinue') }}
                          </v-btn>
                        </div>
                      </div>
                    </div>
                    <div v-else key="receipt" class="widget-receipt">
                      <div class="widget-receipt__info">
                        <v-icon
                          class="widget-receipt__icon"
                          :icon="entry.widgetStatus === 'done' ? 'mdi-check-circle' : 'mdi-arrow-right-circle-outline'"
                          size="18"
                          :color="entry.widgetStatus === 'done' ? 'success' : undefined"
                        />
                        <span>{{ resolveSummaryText(entry) }}</span>
                      </div>
                      <v-btn
                        size="small"
                        variant="text"
                        :disabled="busy || platformLoading || isChatRunning"
                        @click="reopenWidget('platform')"
                      >
                        {{ tm(entry.widgetStatus === 'done' ? 'guide.edit' : 'guide.configure') }}
                      </v-btn>
                    </div>
                  </Transition>
                </div>

                <!-- Inline Widget: Welcome Celebration -->
                <div
                  v-else-if="entry.widget === 'welcome' && entry.typingDone !== false"
                  class="widget-card widget-card--welcome"
                >
                  <OnboardingWelcome />
                  <div class="widget-welcome-actions">
                    <v-btn
                      v-if="modelReady"
                      variant="text"
                      prepend-icon="mdi-chat-outline"
                      :disabled="busy || isChatRunning"
                      @click="openChatPage"
                    >
                      {{ tm('guide.enterChat') }}
                    </v-btn>
                    <v-btn
                      variant="tonal"
                      color="primary"
                      append-icon="mdi-arrow-right"
                      :disabled="busy || isChatRunning"
                      @click="close"
                    >
                      {{ tm('guide.start') }}
                    </v-btn>
                  </div>
                </div>
              </div>
            </div>
          </template>
        </div>
      </section>

      <!-- Floating ChatUI Composer Shell -->
      <section
        v-if="stage !== 'done' || modelReady"
        ref="composerShell"
        class="composer-shell onboarding-composer"
      >
        <Transition name="float-pop">
          <button
            v-if="isAwayFromBottom && !shouldStickToBottom"
            class="scroll-to-bottom"
            type="button"
            :aria-label="chatTm('actions.scrollToBottom')"
            :title="chatTm('actions.scrollToBottom')"
            @click="scrollToBottom(true)"
          >
            <ArrowDown :size="20" :stroke-width="1.75" aria-hidden="true" />
          </button>
        </Transition>

        <Transition name="float-pop">
          <div
            v-if="showQuickBar"
            class="onboarding-quickbar"
          >
            <div class="composer-status">
              <v-btn
                v-if="stage !== 'notice' && stage !== 'done'"
                size="small"
                variant="text"
                :disabled="busy || platformLoading || isChatRunning"
                @click="close"
              >
                {{ tm('guide.skipAll') }}
              </v-btn>
            </div>

            <div v-if="stage === 'chat' && hasLiveChat" class="composer-shortcuts">
              <v-btn
                size="small"
                variant="text"
                prepend-icon="mdi-tune-variant"
                :disabled="busy || isChatRunning"
                @click="reopenWidget('model')"
              >
                {{ tm('guide.changeModel') }}
              </v-btn>
              <v-btn
                size="small"
                variant="tonal"
                color="primary"
                append-icon="mdi-arrow-right"
                :disabled="busy || isChatRunning"
                @click="openPlatformStep()"
              >
                {{ tm('guide.continuePlatform') }}
              </v-btn>
            </div>
          </div>
        </Transition>

        <ChatInput
          ref="inputRef"
          v-model:prompt="draft"
          :staged-images-url="[]"
          staged-audio-url=""
          :staged-files="[]"
          :disabled="busy || platformLoading"
          minimal
          :show-settings="false"
          :show-provider-selector="false"
          :is-recording="false"
          :is-running="isChatRunning"
          :session-id="currSessionId || null"
          :current-session="currentSession"
          config-id="default"
          send-shortcut="enter"
          :placeholder="composerPlaceholder"
          @send="handleComposerSend"
          @stop="stopCurrentSession"
        />
      </section>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router';
import { ArrowDown } from '@lucide/vue';
import { authApi, botApi, chatApi, configProfileApi, configRouteApi, providerApi, systemConfigApi } from '@/api/v1';
import { useModuleI18n } from '@/i18n/composables';
import { useAuthStore } from '@/stores/auth';
import { useCustomizerStore } from '@/stores/customizer';
import { useMessages, type ChatRecord } from '@/composables/useMessages';
import type { Session } from '@/composables/useSessions';
import { buildWebchatUmoDetails } from '@/utils/chatConfigBinding';
import { getPluginInstallReturnUrl } from '@/utils/pluginInstallLink.mjs';
import OnboardingModel from '@/components/OnboardingModel.vue';
import OnboardingWelcome from '@/components/OnboardingWelcome.vue';
import AddNewPlatform from '@/components/platform/AddNewPlatform.vue';
import ReadmeDialog from '@/components/shared/ReadmeDialog.vue';
import ChatMessageList from '@/components/chat/ChatMessageList.vue';
import ChatInput from '@/components/chat/ChatInput.vue';

type OnboardingStage = 'notice' | 'model' | 'chat' | 'platform' | 'done';
type WidgetKind = 'notice' | 'model' | 'trial' | 'platform' | 'welcome';
type WidgetStatus = 'active' | 'done' | 'skipped';

interface GuideStreamEntry {
  kind: 'guide';
  id: string;
  role: 'assistant' | 'user';
  textKey?: string;
  textParams?: Record<string, string>;
  rawText?: string;
  widget?: WidgetKind;
  widgetStatus?: WidgetStatus;
  summaryKey?: string;
  summaryParams?: Record<string, string>;
  expanded?: boolean;
  expandedMounted?: boolean;
  revealed?: boolean;
  typedLength?: number;
  typingDone?: boolean;
}

interface ChatStreamEntry {
  kind: 'chat';
  id: string;
  records: ChatRecord[];
}

type StreamEntry = GuideStreamEntry | ChatStreamEntry;

const emit = defineEmits<{
  (event: 'model-saved', payload: { providerId: string; modelName: string }): void;
  (event: 'session-created', sessionId: string): void;
  (event: 'open-session', sessionId?: string): void;
}>();

const FIRST_NOTICE_SEEN_KEY = 'astrbot:first_notice_seen:v1';

const { tm } = useModuleI18n('features/welcome');
const { tm: chatTm } = useModuleI18n('features/chat');
const authStore = useAuthStore();
const router = useRouter();
const route = useRoute();
const customizer = useCustomizerStore();
const isDark = computed(() => customizer.uiTheme === 'PurpleThemeDark');

const ready = ref(false);
const scrollContainer = ref<HTMLElement>();
const streamFeed = ref<HTMLElement>();
const composerShell = ref<HTMLElement>();
const inputRef = ref<InstanceType<typeof ChatInput>>();
const modelForm = ref<InstanceType<typeof OnboardingModel>>();
const platformForm = ref<InstanceType<typeof AddNewPlatform>>();
const activeWidgetId = ref('guide-notice-1');
const shouldStickToBottom = ref(true);
const isAwayFromBottom = ref(false);

let entryCounter = 1;
const nextEntryId = (prefix: string) => `${prefix}-${++entryCounter}`;

const stage = ref<OnboardingStage>('notice');
const completed = ref(false);
const busy = ref(false);
const configError = ref('');

const modelReady = ref(false);
const selectedModel = ref('');
const selectedModelName = ref('');
const hasLiveChat = ref(false);

const selectedPlatformId = ref('');
const platformDraft = ref<Record<string, any> | null>(null);
const platformReady = computed(
  () => Boolean(selectedPlatformId.value) && platformDraft.value?.id === selectedPlatformId.value,
);
const platformLoading = ref(false);
const platformError = ref('');
const platformMetadata = ref<Record<string, any>>({});
const existingPlatformMetadata = computed(() => {
  const metadata = platformMetadata.value.platform_group?.metadata || {};
  const platform = metadata.platform || {};
  return {
    ...platformMetadata.value,
    platform_group: {
      ...platformMetadata.value.platform_group,
      metadata: {
        ...metadata,
        platform: {
          ...platform,
          items: {
            ...platform.items,
            id: { ...platform.items?.id, invisible: true },
          },
        },
      },
    },
  };
});
const platformConfig = ref<Record<string, any>>({});
const configuredPlatforms = computed(() =>
  Array.isArray(platformConfig.value.platform)
    ? (platformConfig.value.platform.filter(
        (platform: any) => typeof platform?.id === 'string' && platform.id,
      ) as Record<string, any>[])
    : [],
);
const platformChoices = computed(() => [
  ...configuredPlatforms.value.map((platform) => ({
    title: `${platform.id} (${platform.type || ''})`,
    value: platform.id,
  })),
  { title: tm('guide.newAdapter'), value: '' },
]);
const platformSaveDisabled = computed(
  () =>
    platformLoading.value ||
    (platformDraft.value
      ? !platformReady.value || !platformForm.value?.initialPlatformRoutes
      : !platformForm.value?.canSave),
);

const starterPromptKeys = ['guide.starterIntro', 'guide.starterTest'] as const;

const timeline = ref<StreamEntry[]>([
  {
    kind: 'guide',
    id: activeWidgetId.value,
    role: 'assistant',
    textKey: 'guide.agentGreeting',
    widget: 'notice',
    widgetStatus: 'active',
  },
]);

const draft = ref('');
const currSessionId = ref('');
const currentSession = ref<Session | null>(null);
const chatInitializing = ref(false);

const {
  activeMessages,
  isSessionRunning,
  isMessageStreaming,
  createLocalExchange,
  sendMessageStream,
  sendButtonInteraction,
  stopSession,
} = useMessages({
  currentSessionId: currSessionId,
  onStreamUpdate: () => {
    if (shouldStickToBottom.value) {
      scrollToBottom();
    }
  },
});

const isChatRunning = computed(() =>
  Boolean(currSessionId.value && isSessionRunning(currSessionId.value)),
);

const showQuickBar = computed(
  () => stage.value !== 'notice' && stage.value !== 'done',
);

const composerPlaceholder = computed(() => {
  if (stage.value === 'done') return tm('guide.placeholderDone');
  if (modelReady.value) return tm('guide.placeholderChat');
  return tm('guide.placeholderSetup');
});

function setModelFormRef(entryId: string, el: unknown) {
  if (entryId !== activeWidgetId.value) return;
  modelForm.value = (el as InstanceType<typeof OnboardingModel> | null) || undefined;
}

function setPlatformFormRef(entryId: string, el: unknown) {
  if (entryId !== activeWidgetId.value) return;
  platformForm.value = (el as InstanceType<typeof AddNewPlatform> | null) || undefined;
}

function resolveEntryText(entry: GuideStreamEntry): string {
  if (entry.rawText !== undefined) return entry.rawText;
  if (!entry.textKey) return '';
  return tm(entry.textKey, entry.textParams);
}

function resolveDisplayedText(entry: GuideStreamEntry): string {
  const full = resolveEntryText(entry);
  if (entry.typingDone !== false || entry.typedLength === undefined) return full;
  return Array.from(full).slice(0, entry.typedLength).join('');
}

function resolveSummaryText(entry: GuideStreamEntry): string {
  if (!entry.summaryKey) return '';
  return tm(entry.summaryKey, entry.summaryParams);
}

function toggleNoticeExpanded(entry: GuideStreamEntry) {
  if (!entry.expanded) {
    entry.expandedMounted = true;
    entry.expanded = true;
  } else {
    entry.expanded = false;
  }
}

let activeTypingTimer: number | null = null;
const typingQueue: string[] = [];

function shouldAnimateTyping(): boolean {
  if (typeof window === 'undefined') return false;
  return !window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
}

function flushTypingQueue() {
  if (activeTypingTimer !== null && typeof window !== 'undefined') {
    window.clearTimeout(activeTypingTimer);
    activeTypingTimer = null;
  }
  typingQueue.length = 0;
  for (const item of timeline.value) {
    if (item.kind === 'guide') {
      item.revealed = true;
      item.typedLength = undefined;
      item.typingDone = true;
    }
  }
}

function runNextQueuedTyping() {
  if (activeTypingTimer !== null || !typingQueue.length) return;
  const nextId = typingQueue[0];
  const entry = timeline.value.find(
    (item): item is GuideStreamEntry => item.kind === 'guide' && item.id === nextId,
  );
  if (!entry) {
    typingQueue.shift();
    runNextQueuedTyping();
    return;
  }
  entry.revealed = true;
  const chars = Array.from(resolveEntryText(entry));
  if (!shouldAnimateTyping() || !chars.length) {
    entry.typedLength = undefined;
    entry.typingDone = true;
    typingQueue.shift();
    scrollToBottom(true);
    runNextQueuedTyping();
    return;
  }
  const budgetMs = entry.role === 'user' ? 240 : 620;
  const stepMs = Math.max(12, Math.min(26, Math.round(budgetMs / chars.length)));
  const tick = () => {
    activeTypingTimer = null;
    if (!mounted) return;
    const nextLength = (entry.typedLength ?? 0) + 1;
    if (nextLength >= chars.length) {
      entry.typedLength = undefined;
      entry.typingDone = true;
      typingQueue.shift();
      scrollToBottom();
      if (typingQueue.length) {
        activeTypingTimer = window.setTimeout(() => {
          activeTypingTimer = null;
          runNextQueuedTyping();
        }, 90);
      }
      return;
    }
    entry.typedLength = nextLength;
    scrollToBottom();
    activeTypingTimer = window.setTimeout(tick, stepMs);
  };
  scrollToBottom(true);
  activeTypingTimer = window.setTimeout(tick, stepMs);
}

function isChatRecordStreaming(record: ChatRecord): boolean {
  const index = activeMessages.value.indexOf(record);
  if (index < 0) return false;
  return isMessageStreaming(record, index);
}

function handleStreamScroll() {
  const container = scrollContainer.value;
  if (!container) return;
  const distanceToBottom = container.scrollHeight - container.scrollTop - container.clientHeight;
  shouldStickToBottom.value = distanceToBottom < 72;
  isAwayFromBottom.value = distanceToBottom > 12;
}

function scrollToBottom(force = false) {
  void nextTick(() => {
    const container = scrollContainer.value;
    if (!container) return;
    if (force) shouldStickToBottom.value = true;
    container.scrollTop = container.scrollHeight;
    isAwayFromBottom.value = false;
  });
}

let mounted = true;
let layoutObserver: ResizeObserver | undefined;

async function checkAccess() {
  ready.value = false;
  const redirect = getPluginInstallReturnUrl(router, route.query.redirect);
  if (!authStore.has_token()) {
    void router.replace({ path: '/auth/login', query: { redirect } });
    return;
  }
  try {
    const setupStatus = await authApi.setupStatus();
    if (!mounted) return;
    if (setupStatus.data.status !== 'ok') {
      throw new Error('Unable to check setup status');
    }
    if (setupStatus.data?.data?.setup_required) {
      void router.replace({ path: '/auth/setup', query: { redirect } });
      return;
    }
    ready.value = true;
    const initial = timeline.value[0];
    if (initial?.kind === 'guide' && shouldAnimateTyping()) {
      initial.revealed = true;
      initial.typedLength = 0;
      initial.typingDone = false;
      typingQueue.push(initial.id);
      runNextQueuedTyping();
    }
  } catch {
    if (mounted) {
      void router.replace({ path: '/auth/login', query: { redirect } });
    }
  }
}

onMounted(() => {
  if (typeof ResizeObserver !== 'undefined') {
    layoutObserver = new ResizeObserver((entries) => {
      const container = scrollContainer.value;
      if (!container) return;
      for (const entry of entries) {
        if (entry.target === composerShell.value) {
          const height = Math.ceil(entry.target.getBoundingClientRect().height);
          container.style.setProperty('--chat-composer-height', `${height}px`);
        }
      }
      if (shouldStickToBottom.value) {
        container.scrollTop = container.scrollHeight;
        isAwayFromBottom.value = false;
      } else {
        isAwayFromBottom.value =
          container.scrollHeight - container.scrollTop - container.clientHeight > 12;
      }
    });
    if (streamFeed.value) layoutObserver.observe(streamFeed.value);
    if (composerShell.value) layoutObserver.observe(composerShell.value);
  }
  void checkAccess();
});

watch(
  [streamFeed, composerShell],
  (elements, previousElements) => {
    if (!layoutObserver) return;
    for (const element of previousElements) {
      if (element) layoutObserver.unobserve(element);
    }
    for (const element of elements) {
      if (element) layoutObserver.observe(element);
    }
    if (composerShell.value && scrollContainer.value) {
      const height = Math.ceil(composerShell.value.getBoundingClientRect().height);
      scrollContainer.value.style.setProperty('--chat-composer-height', `${height}px`);
    }
  },
  { flush: 'post' },
);

onBeforeUnmount(() => {
  mounted = false;
  flushTypingQueue();
  layoutObserver?.disconnect();
});

function findActiveWidget(kind?: WidgetKind): GuideStreamEntry | undefined {
  for (let i = timeline.value.length - 1; i >= 0; i--) {
    const item = timeline.value[i];
    if (item.kind === 'guide' && item.widget && item.widgetStatus === 'active') {
      if (!kind || item.widget === kind) return item;
    }
  }
  return undefined;
}

function deactivateActiveFormWidgets(reason: 'skipped' | 'done' = 'skipped') {
  for (const item of timeline.value) {
    if (
      item.kind === 'guide' &&
      item.widget &&
      item.widget !== 'welcome' &&
      item.widgetStatus === 'active'
    ) {
      item.widgetStatus =
        item.widget === 'trial' && hasLiveChat.value ? 'done' : reason;
      if (!item.summaryKey) {
        if (item.widget === 'notice') item.summaryKey = 'guide.summaryNoticeDone';
        else if (item.widget === 'model') item.summaryKey = 'guide.summaryModelSkipped';
        else if (item.widget === 'trial') {
          item.summaryKey = hasLiveChat.value
            ? 'guide.summaryTrialDone'
            : 'guide.summaryTrialSkipped';
        } else if (item.widget === 'platform') {
          item.summaryKey = 'guide.summaryPlatformSkipped';
        }
      }
    }
  }
  modelForm.value = undefined;
  platformForm.value = undefined;
}

function pushGuideMessage(entry: Omit<GuideStreamEntry, 'kind' | 'id'>, idPrefix = 'guide') {
  const id = nextEntryId(idPrefix);
  if (entry.widget && entry.widgetStatus === 'active') {
    activeWidgetId.value = id;
  }
  const animate = shouldAnimateTyping() && (entry.role === 'assistant' || entry.rawText === undefined);
  const queued = animate && typingQueue.length > 0;
  timeline.value.push({
    kind: 'guide',
    id,
    ...entry,
    revealed: !queued,
    typedLength: animate ? 0 : undefined,
    typingDone: !animate,
  });
  if (animate) {
    typingQueue.push(id);
    runNextQueuedTyping();
  } else {
    scrollToBottom(true);
  }
}

function confirmNotice() {
  if (busy.value || stage.value !== 'notice') return;
  flushTypingQueue();
  const active = findActiveWidget('notice');
  if (active) {
    active.widgetStatus = 'done';
    active.summaryKey = 'guide.summaryNoticeDone';
  }
  try {
    localStorage.setItem(FIRST_NOTICE_SEEN_KEY, '1');
  } catch {
    // Ignore storage restrictions.
  }
  configError.value = '';
  pushGuideMessage({ role: 'user', textKey: 'guide.userConfirmedNotice' }, 'user');
  stage.value = 'model';
  pushGuideMessage(
    {
      role: 'assistant',
      textKey: 'guide.agentAskModel',
      widget: 'model',
      widgetStatus: 'active',
    },
    'widget-model',
  );
}

async function testModel() {
  if (busy.value || platformLoading.value || isChatRunning.value) return;
  configError.value = '';
  await modelForm.value?.test();
}

async function saveModel() {
  if (busy.value || platformLoading.value || isChatRunning.value) return;
  const active = findActiveWidget('model');
  if (!active) return;

  busy.value = true;
  configError.value = '';
  try {
    const savedId = await modelForm.value?.save();
    if (modelForm.value && !savedId) return;
    const response = await providerApi.schema();
    if (response.data.status !== 'ok') {
      throw new Error(response.data.message || tm('onboard.providerLoadFailed'));
    }
    const { providers = [], provider_sources = [] } = response.data.data || {};
    const sources = new Map(provider_sources.map((source) => [source.id, source.provider_type]));
    const provider = providers.find((p) => {
      const type =
        p.provider_type ||
        sources.get(p.provider_source_id) ||
        (String(p.type || '').includes('chat_completion') ? 'chat_completion' : '');
      return p.id && (!savedId || p.id === savedId) && p.enable !== false && type === 'chat_completion';
    });
    if (!provider) throw new Error(tm('guide.modelPending'));

    const profile = await configProfileApi.get('default');
    if (profile.data.status !== 'ok') {
      throw new Error(profile.data.message || tm('onboard.providerLoadFailed'));
    }
    const config = profile.data.data?.config as Record<string, any> | undefined;
    const model = config?.agent_runner?.config?.model;
    if (config?.agent_runner?.runner_type === 'local' && model && !model.provider_id) {
      model.provider_id = provider.id;
      const result = await configProfileApi.update('default', config);
      if (result.data.status !== 'ok') {
        throw new Error(result.data.message || tm('onboard.providerUpdateFailed'));
      }
    }

    const wasReady = modelReady.value;
    modelReady.value = true;
    selectedModel.value = String(savedId || model?.provider_id || provider.id);
    selectedModelName.value = String(provider.model || '');
    emit('model-saved', {
      providerId: selectedModel.value,
      modelName: selectedModelName.value,
    });

    active.widgetStatus = 'done';
    active.summaryKey = 'guide.summaryModelDone';
    active.summaryParams = { model: selectedModel.value };
    modelForm.value = undefined;
    flushTypingQueue();

    pushGuideMessage(
      {
        role: 'user',
        textKey: 'guide.userConfiguredModel',
        textParams: { model: selectedModel.value },
      },
      'user',
    );

    if (completed.value) {
      stage.value = 'done';
      pushGuideMessage(
        {
          role: 'assistant',
          textKey: 'guide.agentModelUpdated',
          textParams: { model: selectedModel.value },
        },
        'guide',
      );
    } else {
      stage.value = 'chat';
      pushGuideMessage(
        {
          role: 'assistant',
          textKey: wasReady ? 'guide.agentModelUpdated' : 'guide.agentModelReady',
          textParams: { model: selectedModel.value },
          widget: 'trial',
          widgetStatus: 'active',
        },
        'widget-trial',
      );
      void ensureChatSession().catch(() => undefined);
    }
    void nextTick(() => inputRef.value?.focusInput());
  } catch (error: any) {
    configError.value =
      error?.response?.data?.message || error?.message || tm('onboard.providerLoadFailed');
  } finally {
    busy.value = false;
  }
}

function skipModel() {
  if (busy.value || platformLoading.value || isChatRunning.value) return;
  flushTypingQueue();
  const active = findActiveWidget('model');
  if (active) {
    active.widgetStatus = 'skipped';
    active.summaryKey = 'guide.summaryModelSkipped';
  }
  modelForm.value = undefined;
  configError.value = '';
  pushGuideMessage({ role: 'user', textKey: 'guide.userSkippedModel' }, 'user');
  if (completed.value) {
    stage.value = 'done';
    return;
  }
  openPlatformStep(false, 'guide.agentAskPlatformAfterModelSkip');
}

function openPlatformStep(
  emitUserTurn = true,
  promptKey: 'guide.agentAskPlatform' | 'guide.agentAskPlatformAfterModelSkip' = 'guide.agentAskPlatform',
) {
  if (busy.value || platformLoading.value || isChatRunning.value) return;
  if (stage.value === 'platform' && findActiveWidget('platform')) {
    scrollToBottom(true);
    return;
  }
  const activeTrial = findActiveWidget('trial');
  if (activeTrial) {
    activeTrial.widgetStatus = hasLiveChat.value ? 'done' : 'skipped';
    activeTrial.summaryKey = hasLiveChat.value
      ? 'guide.summaryTrialDone'
      : 'guide.summaryTrialSkipped';
  }
  configError.value = '';
  platformError.value = '';
  if (emitUserTurn) {
    flushTypingQueue();
    pushGuideMessage({ role: 'user', textKey: 'guide.userOpenPlatform' }, 'user');
  }
  stage.value = 'platform';
  pushGuideMessage(
    {
      role: 'assistant',
      textKey: promptKey,
      widget: 'platform',
      widgetStatus: 'active',
    },
    'widget-platform',
  );
  void loadPlatforms();
}

async function loadPlatforms(savedId?: string) {
  busy.value = false;
  platformError.value = '';
  platformLoading.value = true;
  platformDraft.value = null;
  configError.value = '';
  try {
    const result = await systemConfigApi.runtime();
    if (result.data.status !== 'ok') {
      throw new Error(result.data.message || tm('onboard.platformLoadFailed'));
    }
    platformConfig.value = result.data.data?.config || {};
    platformMetadata.value = result.data.data?.metadata || {};
    selectPlatform(
      configuredPlatforms.value.find((platform) => platform.id === savedId)?.id ||
        configuredPlatforms.value.find((platform) => platform.enable !== false)?.id ||
        configuredPlatforms.value[0]?.id ||
        '',
    );
    if (savedId && configuredPlatforms.value.some((platform) => platform.id === savedId)) {
      completePlatformStep(savedId);
    }
  } catch (error: any) {
    configError.value =
      error?.response?.data?.message || error?.message || tm('onboard.platformLoadFailed');
  } finally {
    platformLoading.value = false;
  }
}

function selectPlatform(id: string) {
  selectedPlatformId.value = id;
  platformError.value = '';
  const platform = configuredPlatforms.value.find((item) => item.id === id);
  platformDraft.value = platform ? JSON.parse(JSON.stringify(platform)) : null;
}

async function savePlatform() {
  if (busy.value || platformLoading.value || isChatRunning.value) return;
  if (!platformDraft.value) {
    await platformForm.value?.newPlatform();
    return;
  }
  if (!platformReady.value || !platformForm.value?.initialPlatformRoutes) return;
  const original = configuredPlatforms.value.find((item) => item.id === selectedPlatformId.value);
  const adapterChanged = JSON.stringify(original) !== JSON.stringify(platformDraft.value);
  const routesChanged = platformForm.value.routesChanged;
  if (!adapterChanged && !routesChanged) {
    completePlatformStep(selectedPlatformId.value);
    return;
  }
  busy.value = true;
  platformError.value = '';
  try {
    const draftCopy = JSON.parse(JSON.stringify(platformDraft.value));
    if (adapterChanged) {
      const result = await botApi.update(selectedPlatformId.value, draftCopy);
      if (result.data.status !== 'ok') {
        throw new Error(result.data.message || tm('guide.adapterSaveFailed'));
      }
    }
    if (routesChanged) await platformForm.value.saveRoutesInternal();
    await loadPlatforms(draftCopy.id);
  } catch (error: any) {
    platformError.value =
      error?.response?.data?.message || error?.message || tm('guide.adapterSaveFailed');
  } finally {
    busy.value = false;
  }
}

function completePlatformStep(savedId: string) {
  flushTypingQueue();
  const active = findActiveWidget('platform');
  if (active) {
    active.widgetStatus = 'done';
    active.summaryKey = 'guide.summaryPlatformDone';
    active.summaryParams = { platform: savedId };
  }
  platformForm.value = undefined;
  platformError.value = '';
  configError.value = '';
  pushGuideMessage(
    {
      role: 'user',
      textKey: 'guide.userConfiguredPlatform',
      textParams: { platform: savedId },
    },
    'user',
  );
  showWelcome();
}

function skipPlatform() {
  if (busy.value || platformLoading.value || isChatRunning.value) return;
  flushTypingQueue();
  const active = findActiveWidget('platform');
  if (active) {
    active.widgetStatus = 'skipped';
    active.summaryKey = 'guide.summaryPlatformSkipped';
  }
  platformForm.value = undefined;
  platformDraft.value = null;
  platformError.value = '';
  configError.value = '';
  pushGuideMessage({ role: 'user', textKey: 'guide.userSkippedPlatform' }, 'user');
  showWelcome();
}

function showWelcome() {
  stage.value = 'done';
  if (completed.value) {
    scrollToBottom(true);
    return;
  }
  completed.value = true;
  pushGuideMessage(
    {
      role: 'assistant',
      textKey: 'guide.agentAllDone',
      widget: 'welcome',
      widgetStatus: 'active',
    },
    'widget-welcome',
  );
}

function reopenWidget(kind: 'model' | 'platform') {
  if (busy.value || platformLoading.value || isChatRunning.value) return;
  flushTypingQueue();
  deactivateActiveFormWidgets('skipped');
  configError.value = '';
  platformError.value = '';
  if (kind === 'model') {
    stage.value = 'model';
    pushGuideMessage({ role: 'user', textKey: 'guide.userReopenModel' }, 'user');
    pushGuideMessage(
      {
        role: 'assistant',
        textKey: 'guide.agentAskModel',
        widget: 'model',
        widgetStatus: 'active',
      },
      'widget-model',
    );
  } else {
    pushGuideMessage({ role: 'user', textKey: 'guide.userReopenPlatform' }, 'user');
    openPlatformStep(false);
  }
}

let pendingSessionPromise: Promise<string> | null = null;

async function ensureChatSession(): Promise<string> {
  if (currSessionId.value) return currSessionId.value;
  if (pendingSessionPromise) return pendingSessionPromise;
  chatInitializing.value = true;
  pendingSessionPromise = (async () => {
    try {
      const response = await chatApi.createSession();
      const session = response.data?.data as Session;
      currSessionId.value = session.session_id;
      currentSession.value = session;
      const umo = buildWebchatUmoDetails(session.session_id, false).umo;
      await configRouteApi.upsert(umo, { config_id: 'default' });
      emit('session-created', session.session_id);
      return session.session_id;
    } finally {
      chatInitializing.value = false;
      pendingSessionPromise = null;
    }
  })();
  return pendingSessionPromise;
}

async function sendLiveMessage(text: string) {
  const trimmed = text.trim();
  if (!trimmed || busy.value || platformLoading.value || !modelReady.value) {
    return;
  }
  flushTypingQueue();
  try {
    const sessionId = await ensureChatSession();
    const parts = [{ type: 'plain', text: trimmed }];
    const messageId = crypto.randomUUID?.() || `${Date.now()}-${Math.random()}`;
    const { userRecord, botRecord } = createLocalExchange({
      sessionId,
      messageId,
      parts,
    });
    hasLiveChat.value = true;
    const lastEntry = timeline.value[timeline.value.length - 1];
    if (lastEntry && lastEntry.kind === 'chat') {
      lastEntry.records.push(userRecord, botRecord);
    } else {
      timeline.value.push({
        kind: 'chat',
        id: nextEntryId('chat'),
        records: [userRecord, botRecord],
      });
    }
    scrollToBottom(true);

    sendMessageStream({
      sessionId,
      messageId,
      parts,
      transport: 'sse',
      enableStreaming: true,
      enableReasoning: true,
      selectedProvider: selectedModel.value || '',
      selectedModel: selectedModelName.value || '',
      userRecord,
      botRecord,
    });
  } catch {
    pushGuideMessage({ role: 'assistant', textKey: 'guide.agentChatFailed' }, 'guide');
  }
}

function handleButtonClick(payload: { message: ChatRecord; callbackData: string }) {
  if (!currSessionId.value) return;
  sendButtonInteraction({
    sessionId: currSessionId.value,
    sourceMessageId: payload.message.id,
    callbackData: payload.callbackData,
  });
}

async function stopCurrentSession() {
  if (!currSessionId.value) return;
  try {
    await stopSession(currSessionId.value);
  } catch (error) {
    console.error('Failed to stop onboarding chat session:', error);
  }
}

async function handleComposerSend() {
  const text = draft.value.trim();
  if (!text || busy.value || platformLoading.value || isChatRunning.value) return;
  draft.value = '';
  const normalized = text.toLowerCase();

  if (stage.value === 'notice') {
    if (/^(跳过|跳过引导|skip|skip setup|スキップ|пропустить)$/i.test(normalized)) {
      close();
      return;
    }
    if (/^(继续|确认|同意|已阅读|我已阅读|ok|yes|continue|next|続行|はい|同意|далее|продолжить|да)$/i.test(normalized)) {
      confirmNotice();
      return;
    }
    flushTypingQueue();
    pushGuideMessage({ role: 'user', rawText: text }, 'user');
    pushGuideMessage({ role: 'assistant', textKey: 'guide.agentHintNotice' }, 'guide');
    return;
  }

  if (stage.value === 'model') {
    if (/^(跳过|跳过此步|跳过模型|skip|スキップ|пропустить)$/i.test(normalized)) {
      skipModel();
      return;
    }
    if (!modelReady.value) {
      flushTypingQueue();
      pushGuideMessage({ role: 'user', rawText: text }, 'user');
      pushGuideMessage({ role: 'assistant', textKey: 'guide.agentHintModel' }, 'guide');
      return;
    }
  }

  if (stage.value === 'chat') {
    if (/^(下一步|继续|连接平台|连接消息平台|平台|next|continue|platform|次へ|続行|プラットフォーム|далее|продолжить|платформ[ау]?)$/i.test(normalized)) {
      openPlatformStep();
      return;
    }
  }

  if (stage.value === 'platform') {
    if (/^(跳过|跳过此步|跳过平台|skip|スキップ|пропустить)$/i.test(normalized)) {
      skipPlatform();
      return;
    }
    if (!modelReady.value) {
      flushTypingQueue();
      pushGuideMessage({ role: 'user', rawText: text }, 'user');
      pushGuideMessage({ role: 'assistant', textKey: 'guide.agentAskPlatform' }, 'guide');
      return;
    }
  }

  if (modelReady.value) {
    await sendLiveMessage(text);
  }
}

function close() {
  if (busy.value || platformLoading.value || isChatRunning.value) return;
  const redirect = getPluginInstallReturnUrl(router, route.query.redirect);
  void router.push(redirect || '/welcome');
}

function openChatPage() {
  if (busy.value || platformLoading.value || isChatRunning.value) return;
  emit('open-session', currSessionId.value || undefined);
}

onBeforeRouteLeave(() => !busy.value && !platformLoading.value && !isChatRunning.value);

defineExpose({
  ready,
  stage,
  timeline,
  completed,
  busy,
  configError,
  modelReady,
  selectedModel,
  selectedModelName,
  hasLiveChat,
  selectedPlatformId,
  platformDraft,
  platformReady,
  platformLoading,
  platformError,
  configuredPlatforms,
  platformChoices,
  modelForm,
  platformForm,
  draft,
  checkAccess,
  confirmNotice,
  testModel,
  saveModel,
  skipModel,
  openPlatformStep,
  loadPlatforms,
  selectPlatform,
  savePlatform,
  skipPlatform,
  reopenWidget,
  sendLiveMessage,
  handleComposerSend,
  close,
  openChatPage,
});
</script>

<style scoped>
.onboarding-chat {
  flex: 1;
  min-height: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
  position: relative;
  min-width: 0;
  width: 100%;
}

.onboarding-loading {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

.messages-panel {
  flex: 1;
  min-height: 0;
  overflow-x: hidden;
  overflow-y: auto;
  overscroll-behavior-y: contain;
  overflow-anchor: auto;
  padding: 24px 0 calc(var(--chat-composer-height, 108px) + 34px);
  scroll-padding-bottom: calc(var(--chat-composer-height, 108px) + 34px);
}

.messages-list-shell {
  width: var(--chat-content-width, 76%);
  max-width: var(--chat-content-max-width, 760px);
  margin: 0 auto;
}

.stream-feed {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.stream-chat-segment {
  animation: message-spring-up 320ms cubic-bezier(0.22, 1, 0.36, 1) both;
}

.stream-chat-segment :deep(.chat-message-list) {
  padding: 0;
}

.stream-chat-segment :deep(.messages-list) {
  gap: 20px;
}

.message-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  width: 100%;
}

.message-row.from-user {
  justify-content: flex-end;
  transform-origin: right bottom;
  animation: message-spring-up 300ms cubic-bezier(0.22, 1, 0.36, 1) both;
}

.message-row.from-bot {
  transform-origin: left bottom;
  animation: message-spring-up 340ms cubic-bezier(0.22, 1, 0.36, 1) both;
}

.message-row.from-bot .bot-avatar-symbol {
  animation: star-pop 420ms cubic-bezier(0.22, 1, 0.36, 1) both;
}

.message-stack {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
  flex: 1;
}

.message-row.from-user .message-stack {
  flex: 0 1 auto;
  max-width: min(76%, 560px);
  align-items: flex-end;
}

.bot-avatar {
  flex-shrink: 0;
  margin-top: 2px;
  color: rgb(var(--v-theme-primary));
  user-select: none;
}

.bot-avatar-symbol {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 30px;
  margin-top: -2px;
  line-height: 0;
  pointer-events: none;
}

.message-bubble {
  border-radius: 8px;
  padding: 10px 14px;
  line-height: 1.65;
  overflow-wrap: anywhere;
}

.message-bubble.user {
  padding: 12px 18px;
  font-size: 15px;
  border-radius: 16px;
  background: rgba(var(--v-theme-primary), 0.16);
  color: var(--v-theme-primaryText);
}

.message-bubble.bot {
  padding: 6px 0 0;
  background: transparent;
}

.agent-copy {
  margin: 0;
  font-size: 15px;
  line-height: 1.65;
  color: rgb(var(--v-theme-on-surface));
}

.plain-content {
  white-space: pre-wrap;
}

.widget-card {
  width: 100%;
  max-width: 100%;
  min-width: 0;
  border: 1px solid rgba(var(--v-theme-borderLight), 0.42);
  border-radius: var(--astrbot-radius-card);
  background: rgb(var(--v-theme-surface));
  overflow: hidden;
  transform-origin: center top;
  animation: widget-spring-up 380ms cubic-bezier(0.22, 1, 0.36, 1) both;
  transition: border-color 0.2s ease, box-shadow 0.2s ease, background-color 0.2s ease;
}

.widget-card__pane {
  width: 100%;
  min-width: 0;
}

.widget-card--active {
  border-color: rgba(var(--v-theme-primary), 0.18);
  box-shadow: 0 3px 16px rgba(var(--v-theme-primary), 0.035);
}

.widget-card--done,
.widget-card--skipped {
  background: rgba(var(--v-theme-on-surface), 0.025);
}

.widget-card--welcome {
  border-color: rgba(var(--v-theme-primary), 0.18);
  background: linear-gradient(
    180deg,
    rgba(var(--v-theme-primary), 0.04) 0%,
    rgb(var(--v-theme-surface)) 56%
  );
}

.widget-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 20px;
  border-bottom: 1px solid rgba(var(--v-theme-borderLight), 0.32);
}

.widget-card__title {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex-shrink: 0;
}

.widget-card__title h2 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  line-height: 1.4;
}

.widget-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  flex-shrink: 1;
  padding: 2px 10px;
  border-radius: var(--astrbot-radius-pill);
  font-size: 12px;
  font-weight: 500;
  max-width: min(240px, 58%);
  overflow: hidden;
  white-space: nowrap;
}

.widget-badge__label {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.widget-badge--active {
  background: rgba(var(--v-theme-primary), 0.11);
  color: rgb(var(--v-theme-primary));
}

.widget-badge--ready {
  background: rgba(var(--v-theme-success), 0.12);
  color: rgb(var(--v-theme-on-surface));
}

.widget-card__body {
  padding: 18px 20px;
  min-width: 0;
}

.widget-card__body :deep(.property-hint) {
  overflow-wrap: anywhere;
}

.widget-card__body :deep(.v-field) {
  border-radius: var(--astrbot-radius-control);
  background: rgba(var(--v-theme-on-surface), 0.025);
  --v-field-border-opacity: 0.2;
}

.widget-card__body--notice {
  max-height: 360px;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding-block: 14px;
}

.widget-card__body--notice :deep(.markdown-body) {
  padding: 0;
}

.widget-card__body--notice :deep(.markdown-body > :first-child) {
  margin-top: 0;
}

.widget-card__body--notice :deep(.markdown-body > :last-child) {
  margin-bottom: 0;
}

.widget-card__body--notice :deep(.markdown-body h1),
.widget-card__body--notice :deep(.markdown-body h2) {
  font-size: 1.25rem;
  margin-top: 14px;
  margin-bottom: 10px;
  padding-bottom: 0;
  border-bottom: 0;
}

.widget-card__body--notice :deep(.markdown-body p) {
  margin-bottom: 10px;
}

.widget-card__body--trial {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.trial-hint {
  margin: 0;
  font-size: 14px;
  line-height: 1.6;
  color: rgba(var(--v-theme-on-surface), 0.78);
}

.starter-prompts {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.starter-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border: 1px solid rgba(var(--v-theme-primary), 0.22);
  border-radius: var(--astrbot-radius-pill);
  background: rgba(var(--v-theme-primary), 0.05);
  color: rgb(var(--v-theme-on-surface));
  font-size: 13px;
  line-height: 1.4;
  cursor: pointer;
  animation: chip-pop 320ms cubic-bezier(0.22, 1, 0.36, 1) calc(var(--chip-index, 0) * 70ms + 80ms) both;
  transition: background-color 0.15s ease, border-color 0.15s ease, transform 0.15s ease;
}

.starter-chip:hover:not(:disabled),
.starter-chip:focus-visible:not(:disabled) {
  background: rgba(var(--v-theme-primary), 0.12);
  border-color: rgba(var(--v-theme-primary), 0.55);
  transform: translateY(-1px);
}

.starter-chip:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.widget-card__body--reopened {
  border-top: 1px solid rgba(var(--v-theme-borderLight), 0.32);
}

.widget-card__footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  flex-wrap: wrap;
  padding: 12px 20px 14px;
  border-top: 1px solid rgba(var(--v-theme-borderLight), 0.32);
}

.widget-card__footer--split,
.widget-card__footer--platform {
  justify-content: space-between;
}

.widget-card__footer :deep(.v-btn),
.widget-welcome-actions :deep(.v-btn),
.widget-receipt :deep(.v-btn),
.onboarding-quickbar :deep(.v-btn) {
  text-transform: none;
  letter-spacing: 0;
  border-radius: var(--astrbot-radius-pill);
}

.widget-card__actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-inline-start: auto;
}

.widget-card__hint {
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.62);
}

.widget-receipt {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 16px;
}

.widget-receipt__info {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  font-size: 14px;
  color: rgba(var(--v-theme-on-surface), 0.82);
  overflow-wrap: anywhere;
}

.widget-receipt__icon {
  animation: check-pop 340ms cubic-bezier(0.22, 1, 0.36, 1) both;
}

.notice-expand-grid {
  display: grid;
  grid-template-rows: 0fr;
  opacity: 0;
  transition:
    grid-template-rows 280ms cubic-bezier(0.22, 1, 0.36, 1),
    opacity 200ms ease;
}

.notice-expand-grid--open {
  grid-template-rows: 1fr;
  opacity: 1;
}

.notice-expand-grid__inner {
  min-height: 0;
  overflow: hidden;
}

.widget-fold-leave-active {
  transition:
    opacity 180ms ease,
    transform 200ms cubic-bezier(0.4, 0, 1, 1);
  transform-origin: top center;
}

.widget-fold-leave-to {
  opacity: 0;
  transform: translateY(-8px) scaleY(0.92);
}

.widget-fold-enter-active {
  transition:
    opacity 240ms ease,
    transform 300ms cubic-bezier(0.22, 1, 0.36, 1);
  transform-origin: top center;
}

.widget-fold-enter-from {
  opacity: 0;
  transform: translateY(10px) scale(0.97);
}

.float-pop-enter-active {
  transition:
    opacity 220ms ease,
    transform 280ms cubic-bezier(0.22, 1, 0.36, 1);
}

.float-pop-leave-active {
  transition:
    opacity 160ms ease,
    transform 180ms ease;
}

.float-pop-enter-from,
.float-pop-leave-to {
  opacity: 0;
  transform: translateY(10px) scale(0.94);
}

.scroll-to-bottom.float-pop-enter-from,
.scroll-to-bottom.float-pop-leave-to {
  transform: translate(-50%, 10px) scale(0.88);
}

@keyframes message-spring-up {
  0% {
    opacity: 0;
    transform: translateY(18px) scale(0.975);
  }
  100% {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

@keyframes widget-spring-up {
  0% {
    opacity: 0;
    transform: translateY(20px) scale(0.98);
  }
  100% {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

@keyframes star-pop {
  0% {
    opacity: 0;
    transform: scale(0.45) rotate(-45deg);
  }
  70% {
    opacity: 1;
    transform: scale(1.08) rotate(8deg);
  }
  100% {
    opacity: 1;
    transform: scale(1) rotate(0deg);
  }
}

@keyframes check-pop {
  0% {
    opacity: 0;
    transform: scale(0.5);
  }
  70% {
    opacity: 1;
    transform: scale(1.16);
  }
  100% {
    opacity: 1;
    transform: scale(1);
  }
}

@keyframes chip-pop {
  0% {
    opacity: 0;
    transform: translateY(10px) scale(0.95);
  }
  100% {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

.widget-welcome-actions {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  flex-wrap: wrap;
  padding: 0 18px 24px;
}

/* Native ChatUI floating composer shell */
.composer-shell {
  position: absolute;
  right: 0;
  bottom: 0;
  left: 0;
  z-index: 3;
  isolation: isolate;
  pointer-events: none;
  background: transparent;
  padding: 0 0 18px;
}

.composer-shell::before {
  content: '';
  position: absolute;
  z-index: 0;
  top: -26px;
  right: 0;
  bottom: 0;
  left: 0;
  pointer-events: none;
  background: linear-gradient(
    180deg,
    transparent 0%,
    var(--chat-page-bg, rgb(var(--v-theme-surface))) 24px
  );
}

.scroll-to-bottom {
  position: absolute;
  top: -48px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 2;
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  border-radius: 50%;
  background: rgb(var(--v-theme-surface));
  color: rgb(var(--v-theme-on-surface));
  cursor: pointer;
  pointer-events: auto;
}

.scroll-to-bottom:hover {
  background: rgb(var(--v-theme-surface-variant));
}

.onboarding-quickbar {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
  width: var(--chat-content-width, 76%);
  max-width: var(--chat-content-max-width, 760px);
  margin: 0 auto 8px;
  pointer-events: auto;
}

.composer-status,
.composer-shortcuts {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.composer-shortcuts {
  margin-inline-start: auto;
}

.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: rgb(var(--v-theme-success));
  flex-shrink: 0;
}

.composer-shell :deep(.input-area) {
  position: relative;
  z-index: 1;
  padding-top: 0;
  padding-inline: 0;
  border-top: 0;
  pointer-events: none;
  background: transparent;
}

.composer-shell :deep(.input-container) {
  pointer-events: auto;
}

@media (prefers-reduced-motion: reduce) {
  .stream-chat-segment,
  .message-row.from-user,
  .message-row.from-bot,
  .message-row.from-bot .bot-avatar-symbol,
  .widget-card,
  .widget-receipt__icon,
  .starter-chip {
    animation: none !important;
  }

  .notice-expand-grid,
  .widget-fold-enter-active,
  .widget-fold-leave-active,
  .float-pop-enter-active,
  .float-pop-leave-active {
    transition: none !important;
  }
}

@media (max-width: 760px) {
  .messages-panel {
    padding: 18px 0 calc(var(--chat-composer-height, 96px) + 28px);
    scroll-padding-bottom: calc(var(--chat-composer-height, 96px) + 28px);
  }

  .messages-list-shell,
  .onboarding-quickbar {
    width: calc(100% - 20px);
    max-width: 100%;
  }

  .message-row.from-bot {
    flex-direction: column;
    align-items: stretch;
    gap: 2px;
  }

  .message-row.from-bot .bot-avatar {
    display: none;
  }

  .message-row.from-bot .message-stack {
    width: 100%;
    max-width: 100%;
  }

  .message-row.from-user .message-stack {
    max-width: 82%;
  }

  .composer-shell {
    padding: 0;
  }

  .onboarding-quickbar {
    margin-bottom: 0;
  }

  .widget-card__header,
  .widget-card__body,
  .widget-card__footer {
    padding-inline: 14px;
  }

  .widget-card__body--notice {
    max-height: min(360px, 46dvh);
  }

  .widget-card__body--notice :deep(.markdown-body) {
    font-size: 14px;
  }

  .widget-card__body--notice :deep(.markdown-body h1),
  .widget-card__body--notice :deep(.markdown-body h2) {
    font-size: 1.125rem;
  }
}

@media (max-width: 600px) {
  .widget-card__footer--split {
    flex-direction: column-reverse;
    align-items: stretch;
    gap: 8px;
  }

  .widget-card__footer--split .widget-card__actions {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    width: 100%;
    margin-inline-start: 0;
  }

  .widget-card__footer--platform {
    flex-direction: column;
    align-items: stretch;
    gap: 10px;
  }

  .widget-card__footer--platform .widget-card__actions {
    width: 100%;
    justify-content: flex-end;
    flex-wrap: wrap;
    margin-inline-start: 0;
  }
}
</style>
