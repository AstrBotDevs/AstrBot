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
                <OnboardingWidgetCard
                  v-if="entry.widget === 'notice' && entry.typingDone !== false"
                  :status="entry.widgetStatus"
                  icon="mdi-shield-check-outline"
                  :title="tm('guide.notice')"
                  :badge-text="tm('guide.statusConfirm')"
                  body-variant="notice"
                  :summary="tm('guide.summaryNoticeDone')"
                  :action-label="tm(entry.expanded ? 'guide.collapse' : 'guide.view')"
                  @action="toggleNoticeExpanded(entry)"
                >
                  <ReadmeDialog embedded :show="true" mode="first-notice" />
                  <template #footer>
                    <v-btn variant="text" :disabled="busy" @click="close">
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
                  </template>
                  <template #after-receipt>
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
                  </template>
                </OnboardingWidgetCard>

                <!-- Inline Widget: AI Model Configuration -->
                <OnboardingWidgetCard
                  v-else-if="entry.widget === 'model' && entry.typingDone !== false"
                  :status="entry.widgetStatus"
                  icon="mdi-creation-outline"
                  :title="tm('guide.modelTitle')"
                  :badge-text="tm('guide.statusPending')"
                  footer-layout="split"
                  :summary="resolveSummaryText(entry)"
                  :action-label="tm(entry.widgetStatus === 'done' ? 'guide.edit' : 'guide.configure')"
                  :action-disabled="busy || platformLoading || isChatRunning"
                  @action="reopenWidget('model')"
                >
                  <OnboardingModel
                    :ref="(el) => setModelFormRef(entry.id, el)"
                    :disabled="busy"
                    @update:busy="busy = $event"
                  />
                  <template #footer>
                    <v-btn variant="text" :disabled="busy" @click="skipModel">
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
                  </template>
                </OnboardingWidgetCard>

                <!-- Inline Widget: Try Model -->
                <OnboardingWidgetCard
                  v-else-if="entry.widget === 'trial' && entry.typingDone !== false"
                  :status="entry.widgetStatus"
                  icon="mdi-chat-processing-outline"
                  :title="tm('guide.trialTitle')"
                  :badge-text="selectedModel"
                  badge-tone="ready"
                  body-variant="trial"
                  :summary="resolveSummaryText(entry)"
                >
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
                  <template #footer>
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
                  </template>
                </OnboardingWidgetCard>

                <!-- Inline Widget: Messaging Platform Adapter -->
                <OnboardingWidgetCard
                  v-else-if="entry.widget === 'platform' && entry.typingDone !== false"
                  :status="entry.widgetStatus"
                  icon="mdi-robot-outline"
                  :title="tm('guide.platform')"
                  :badge-text="tm('guide.statusPending')"
                  footer-layout="platform"
                  :summary="resolveSummaryText(entry)"
                  :action-label="tm(entry.widgetStatus === 'done' ? 'guide.edit' : 'guide.configure')"
                  :action-disabled="busy || platformLoading || isChatRunning"
                  @action="reopenWidget('platform')"
                >
                  <OnboardingPlatform
                    :ref="(el) => setPlatformFormRef(entry.id, el)"
                    :disabled="busy || isChatRunning"
                    @saved="completePlatformStep"
                    @update:busy="busy = $event"
                    @update:loading="platformLoading = $event"
                  />
                  <template #footer>
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
                        :disabled="busy || !platformForm?.canSave"
                        @click="savePlatform"
                      >
                        {{ tm('guide.saveContinue') }}
                      </v-btn>
                    </div>
                  </template>
                </OnboardingWidgetCard>

                <!-- Inline Widget: Welcome Celebration -->
                <OnboardingWidgetCard
                  v-else-if="entry.widget === 'welcome' && entry.typingDone !== false"
                  variant="welcome"
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
                </OnboardingWidgetCard>
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
          <div v-if="showQuickBar" class="onboarding-quickbar">
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
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue';
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router';
import { ArrowDown } from '@lucide/vue';
import { authApi, chatApi, configRouteApi } from '@/api/v1';
import { useModuleI18n } from '@/i18n/composables';
import { useAuthStore } from '@/stores/auth';
import { useCustomizerStore } from '@/stores/customizer';
import { useMessages, type ChatRecord } from '@/composables/useMessages';
import type { Session } from '@/composables/useSessions';
import { buildWebchatUmoDetails } from '@/utils/chatConfigBinding';
import { getPluginInstallReturnUrl } from '@/utils/pluginInstallLink.mjs';
import OnboardingModel from '@/components/onboarding/OnboardingModel.vue';
import OnboardingPlatform from '@/components/onboarding/OnboardingPlatform.vue';
import OnboardingWelcome from '@/components/onboarding/OnboardingWelcome.vue';
import OnboardingWidgetCard from '@/components/onboarding/OnboardingWidgetCard.vue';
import {
  useOnboardingTimeline,
  type GuideStreamEntry,
} from '@/components/onboarding/useOnboardingTimeline';
import ReadmeDialog from '@/components/shared/ReadmeDialog.vue';
import ChatMessageList from '@/components/chat/ChatMessageList.vue';
import ChatInput from '@/components/chat/ChatInput.vue';

type OnboardingStage = 'notice' | 'model' | 'chat' | 'platform' | 'done';

const emit = defineEmits<{
  (event: 'model-saved', payload: { providerId: string; modelName: string }): void;
  (event: 'session-created', sessionId: string): void;
  (event: 'open-session', sessionId?: string): void;
}>();

const FIRST_NOTICE_SEEN_KEY = 'astrbot:first_notice_seen:v1';
const starterPromptKeys = ['guide.starterIntro', 'guide.starterTest'] as const;

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
const platformForm = ref<InstanceType<typeof OnboardingPlatform>>();

const stage = ref<OnboardingStage>('notice');
const completed = ref(false);
const busy = ref(false);
const platformLoading = ref(false);
const modelReady = ref(false);
const selectedModel = ref('');
const selectedModelName = ref('');
const hasLiveChat = ref(false);

const draft = ref('');
const currSessionId = ref('');
const currentSession = ref<Session | null>(null);
const chatInitializing = ref(false);

const {
  timeline,
  activeWidgetId,
  shouldStickToBottom,
  isAwayFromBottom,
  resolveEntryText,
  resolveDisplayedText,
  resolveSummaryText,
  handleStreamScroll,
  scrollToBottom,
  flushTypingQueue,
  startInitialTyping,
  findActiveWidget,
  deactivateActiveFormWidgets,
  pushGuideMessage,
  appendLiveChatExchange,
} = useOnboardingTimeline({
  translate: (key, params) => tm(key, params),
  hasLiveChat,
  scrollContainer,
  streamFeed,
  composerShell,
  onDeactivateFormWidgets: () => {
    modelForm.value = undefined;
    platformForm.value = undefined;
    platformLoading.value = false;
  },
});

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
const showQuickBar = computed(() => stage.value !== 'notice' && stage.value !== 'done');
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
  platformForm.value = (el as InstanceType<typeof OnboardingPlatform> | null) || undefined;
}

function toggleNoticeExpanded(entry: GuideStreamEntry) {
  if (!entry.expanded) {
    entry.expandedMounted = true;
    entry.expanded = true;
  } else {
    entry.expanded = false;
  }
}

function isChatRecordStreaming(record: ChatRecord): boolean {
  const index = activeMessages.value.indexOf(record);
  if (index < 0) return false;
  return isMessageStreaming(record, index);
}

let mounted = true;

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
    startInitialTyping();
  } catch {
    if (mounted) {
      void router.replace({ path: '/auth/login', query: { redirect } });
    }
  }
}

onMounted(() => {
  void checkAccess();
});

onBeforeUnmount(() => {
  mounted = false;
});

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
  await modelForm.value?.test();
}

async function saveModel() {
  if (busy.value || platformLoading.value || isChatRunning.value) return;
  const active = findActiveWidget('model');
  if (!active || !modelForm.value) return;

  busy.value = true;
  try {
    const saved = await modelForm.value.save(true);
    if (!saved) return;

    const wasReady = modelReady.value;
    modelReady.value = true;
    selectedModel.value = saved.providerId;
    selectedModelName.value = saved.modelName;
    emit('model-saved', {
      providerId: saved.providerId,
      modelName: saved.modelName,
    });

    active.widgetStatus = 'done';
    active.summaryKey = 'guide.summaryModelDone';
    active.summaryParams = { model: saved.providerId };
    modelForm.value = undefined;
    flushTypingQueue();

    pushGuideMessage(
      {
        role: 'user',
        textKey: 'guide.userConfiguredModel',
        textParams: { model: saved.providerId },
      },
      'user',
    );

    if (completed.value) {
      stage.value = 'done';
      pushGuideMessage(
        {
          role: 'assistant',
          textKey: 'guide.agentModelUpdated',
          textParams: { model: saved.providerId },
        },
        'guide',
      );
    } else {
      stage.value = 'chat';
      pushGuideMessage(
        {
          role: 'assistant',
          textKey: wasReady ? 'guide.agentModelUpdated' : 'guide.agentModelReady',
          textParams: { model: saved.providerId },
          widget: 'trial',
          widgetStatus: 'active',
        },
        'widget-trial',
      );
      void ensureChatSession().catch(() => undefined);
    }
    void nextTick(() => inputRef.value?.focusInput());
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
  flushTypingQueue();
  if (emitUserTurn) {
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
}

async function savePlatform() {
  if (busy.value || platformLoading.value || isChatRunning.value) return;
  await platformForm.value?.save();
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
  platformLoading.value = false;
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
  platformLoading.value = false;
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
    appendLiveChatExchange(userRecord, botRecord);

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

.widget-card__body--reopened {
  padding: 14px 20px;
  max-height: 360px;
  overflow-y: auto;
  overscroll-behavior: contain;
  border-top: 1px solid rgba(var(--v-theme-borderLight), 0.32);
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

.onboarding-quickbar :deep(.v-btn) {
  text-transform: none;
  letter-spacing: 0;
  border-radius: var(--astrbot-radius-pill);
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

@media (prefers-reduced-motion: reduce) {
  .stream-chat-segment,
  .message-row.from-user,
  .message-row.from-bot,
  .message-row.from-bot .bot-avatar-symbol,
  .starter-chip {
    animation: none !important;
  }

  .notice-expand-grid,
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

  .widget-card__body--reopened {
    padding-inline: 14px;
    max-height: min(360px, 46dvh);
  }
}
</style>
