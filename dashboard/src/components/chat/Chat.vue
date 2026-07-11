<template>
  <div
    v-if="props.active"
    class="chat-ui"
    :class="{ 'is-dark': isDark, 'sidebar-collapsed': isSidebarCollapsed }"
  >
    <v-navigation-drawer
      v-model="chatSidebarDrawer"
      class="chat-sidebar"
      :class="{ collapsed: isSidebarCollapsed }"
      :permanent="lgAndUp"
      :temporary="!lgAndUp"
      :rail="lgAndUp && customizer.chatSidebarCollapsed"
      :width="280"
      :rail-width="56"
      location="left"
      floating
    >
      <div class="sidebar-top">
        <div
          class="chat-sidebar-brand"
          :class="{ collapsed: isSidebarCollapsed }"
        >
          <div v-if="!isSidebarCollapsed" class="chat-sidebar-brand-title Outfit">
            <ChatUILogo class="chat-sidebar-brand-logo" />
            <span class="chat-sidebar-brand-copy">
              <span class="chat-sidebar-brand-name">AstrBot</span>
              <span class="chat-sidebar-brand-mode">ChatUI</span>
            </span>
          </div>
          <button
            v-if="isSidebarCollapsed"
            class="chat-sidebar-brand-toggle chat-sidebar-rail-btn"
            type="button"
            aria-label="Toggle sidebar"
            @click.stop="toggleChatSidebar"
          >
            <span class="chat-sidebar-rail-icon-stack">
              <ChatUILogo class="chat-sidebar-brand-logo chat-sidebar-brand-logo--collapsed" />
              <PanelLeft
                :size="20"
                class="sidebar-panel-toggle-icon"
              />
            </span>
          </button>
          <v-btn
            v-else
            class="chat-sidebar-brand-toggle"
            icon
            rounded="sm"
            variant="text"
            @click.stop="toggleChatSidebar"
          >
            <PanelLeft
              :size="20"
              class="sidebar-panel-toggle-icon"
            />
          </v-btn>
        </div>

        <button
          v-if="isSidebarCollapsed"
          class="new-chat-btn sidebar-provider-btn icon-only chat-sidebar-rail-btn"
          :class="{ 'sidebar-workspace-btn--active': isProviderWorkspace }"
          type="button"
          :title="tm('actions.providerConfig')"
          @click="openProviderWorkspace"
        >
          <Box :size="18" class="sidebar-action-icon" />
        </button>
        <v-btn
          v-else
          class="new-chat-btn sidebar-provider-btn"
          :class="{ 'sidebar-workspace-btn--active': isProviderWorkspace }"
          variant="text"
          @click="openProviderWorkspace"
        >
          <Box :size="18" class="sidebar-action-icon mr-2" />
          <span>{{ tm("actions.providerConfig") }}</span>
        </v-btn>

        <button
          v-if="isSidebarCollapsed"
          class="new-chat-btn icon-only chat-sidebar-rail-btn"
          type="button"
          :title="tm('actions.newChat')"
          @click="startNewChat"
        >
          <SquarePen :size="18" class="sidebar-action-icon" />
        </button>
        <v-btn
          v-else
          class="new-chat-btn"
          variant="text"
          @click="startNewChat"
        >
          <SquarePen :size="18" class="sidebar-action-icon mr-2" />
          <span>{{ tm("actions.newChat") }}</span>
        </v-btn>

      </div>

      <div v-if="!isSidebarCollapsed" class="sidebar-content">
        <ProjectList
          :projects="projects"
          :project-sessions="projectSessionsById"
          :loading-project-ids="loadingProjectSessionIds"
          :selected-project-id="selectedProjectId"
          :active-session-id="currSessionId"
          :is-session-running="isSessionRunning"
          @create-project="openCreateProjectDialog"
          @edit-project="openEditProjectDialog"
          @delete-project="handleDeleteProject"
          @toggle-project="handleProjectToggle"
          @select-project="selectProject"
          @select-session="selectProjectSession"
          @edit-session-title="editProjectSessionTitle"
          @delete-session="deleteProjectSession"
        />

        <section class="sidebar-section session-list">
          <div class="sidebar-section-header">
            <span>{{ tm("conversation.title") }}</span>
          </div>
          <div
            v-for="session in sessions"
            :key="session.session_id"
            class="session-item"
            :class="{
              active: !isProviderWorkspace && currSessionId === session.session_id,
            }"
            role="button"
            tabindex="0"
            @click="selectSession(session.session_id)"
            @keydown.enter="selectSession(session.session_id)"
            @keydown.space.prevent="selectSession(session.session_id)"
          >
            <span class="session-title">{{ sessionTitle(session) }}</span>
            <div class="session-actions" @click.stop>
              <v-btn
                icon
                size="x-small"
                variant="text"
                class="session-action-btn"
                :title="tm('conversation.editDisplayName')"
                @click="editSidebarSessionTitle(session)"
              >
                <Pencil :size="15" />
              </v-btn>
              <v-btn
                icon
                size="x-small"
                variant="text"
                class="session-action-btn"
                :title="tm('actions.deleteChat')"
                @click="deleteSidebarSession(session)"
              >
                <Trash2 :size="15" />
              </v-btn>
            </div>
            <v-progress-circular
              v-if="isSessionRunning(session.session_id)"
              class="session-progress"
              indeterminate
              size="16"
              width="2"
            />
          </div>
        </section>
      </div>

      <div class="sidebar-footer">
        <StyledMenu
          location="top start"
          offset="10"
          :close-on-content-click="false"
        >
          <template #activator="{ props: menuProps }">
            <v-btn
              v-bind="menuProps"
              class="settings-btn"
              :class="{ 'icon-only': isSidebarCollapsed }"
              variant="text"
              :icon="isSidebarCollapsed"
            >
              <Settings
                :size="20"
                :class="['sidebar-action-icon', { 'mr-2': !isSidebarCollapsed }]"
              />
              <span v-if="!isSidebarCollapsed">{{
                t("core.common.settings")
              }}</span>
            </v-btn>
          </template>

          <div class="settings-menu-content">
            <v-menu
              location="end"
              offset="8"
              open-on-hover
              :close-on-content-click="true"
            >
              <template #activator="{ props: transportMenuProps }">
                <v-list-item
                  v-bind="transportMenuProps"
                  class="styled-menu-item settings-menu-item"
                  rounded="md"
                >
                  <template #prepend>
                    <Cable :size="18" class="styled-menu-lucide-icon" />
                  </template>
                  <v-list-item-title>{{
                    tm("transport.title")
                  }}</v-list-item-title>
                  <template #append>
                    <span class="settings-menu-value">{{
                      currentTransportLabel
                    }}</span>
                    <ChevronRight :size="18" class="styled-menu-lucide-icon" />
                  </template>
                </v-list-item>
              </template>

              <v-card class="styled-menu-card" elevation="8" rounded="lg">
                <v-list density="compact" class="styled-menu-list pa-1">
                  <v-list-item
                    v-for="item in transportOptions"
                    :key="item.value"
                    class="styled-menu-item"
                    :class="{
                      'styled-menu-item-active': transportMode === item.value,
                    }"
                    rounded="md"
                    @click="transportMode = item.value"
                  >
                    <v-list-item-title>{{
                      tm(item.labelKey)
                    }}</v-list-item-title>
                    <template #append>
                      <Check
                        v-if="transportMode === item.value"
                        :size="18"
                        class="styled-menu-lucide-icon"
                      />
                    </template>
                  </v-list-item>
                </v-list>
              </v-card>
            </v-menu>

            <v-menu
              location="end"
              offset="8"
              open-on-hover
              :close-on-content-click="true"
            >
              <template #activator="{ props: languageMenuProps }">
                <v-list-item
                  v-bind="languageMenuProps"
                  class="styled-menu-item settings-menu-item"
                  rounded="md"
                >
                  <template #prepend>
                    <Languages :size="18" class="styled-menu-lucide-icon" />
                  </template>
                  <v-list-item-title>{{
                    t("core.common.language")
                  }}</v-list-item-title>
                  <template #append>
                    <span class="settings-menu-value">{{
                      currentLanguage?.label || locale
                    }}</span>
                    <ChevronRight :size="18" class="styled-menu-lucide-icon" />
                  </template>
                </v-list-item>
              </template>

              <v-card class="styled-menu-card" elevation="8" rounded="lg">
                <v-list density="compact" class="styled-menu-list pa-1">
                  <v-list-item
                    v-for="lang in languageOptions"
                    :key="lang.value"
                    class="styled-menu-item"
                    :class="{
                      'styled-menu-item-active': locale === lang.value,
                    }"
                    rounded="md"
                    @click="switchLanguage(lang.value as Locale)"
                  >
                    <template #prepend>
                      <span class="language-flag">{{ lang.flag }}</span>
                    </template>
                    <v-list-item-title>{{ lang.label }}</v-list-item-title>
                    <template #append>
                      <Check
                        v-if="locale === lang.value"
                        :size="18"
                        class="styled-menu-lucide-icon"
                      />
                    </template>
                  </v-list-item>
                </v-list>
              </v-card>
            </v-menu>

            <v-list-item
              class="styled-menu-item settings-menu-item"
              rounded="md"
              @click="toggleTheme"
            >
              <template #prepend>
                <Sun
                  v-if="isDark"
                  :size="18"
                  class="styled-menu-lucide-icon"
                />
                <Moon v-else :size="18" class="styled-menu-lucide-icon" />
              </template>
              <v-list-item-title>{{
                isDark ? tm("modes.lightMode") : tm("modes.darkMode")
              }}</v-list-item-title>
            </v-list-item>
          </div>
        </StyledMenu>
      </div>
    </v-navigation-drawer>

    <main
      class="chat-main"
      :class="{ 'empty-chat': isEmptyChat }"
    >
      <section v-if="isProviderWorkspace" class="provider-workspace-shell">
        <ProviderChatCompletionPanel
          class="provider-workspace-page"
          :show-border="false"
        />
      </section>

      <ProjectView
        v-else-if="selectedProject"
        :project="selectedProject"
        :sessions="projectSessions"
        @select-session="selectProjectSession"
        @edit-session-title="editProjectSessionTitle"
        @delete-session="deleteProjectSession"
      >
        <section class="project-composer-shell">
          <ChatInput
            ref="inputRef"
            v-model:prompt="draft"
            :staged-images-url="stagedImagesUrl"
            :staged-audio-url="stagedAudioUrl"
            :staged-files="stagedNonImageFiles"
            :disabled="sending"
            :enable-streaming="enableStreaming"
            :is-recording="isRecording"
            :is-running="
              Boolean(currSessionId && isSessionRunning(currSessionId))
            "
            :token-usage="tokenUsageIndicator"
            :session-id="currSessionId || null"
            :current-session="currentSession"
            :reply-to="chatInputReplyTarget"
            :send-shortcut="sendShortcut"
            :show-provider-selector="false"
            @send="sendCurrentMessage"
            @stop="stopCurrentSession"
            @toggle-streaming="toggleStreaming"
            @remove-image="removeImage"
            @remove-audio="removeAudio"
            @remove-file="removeFile"
            @start-recording="startRecording"
            @stop-recording="stopRecording"
            @paste-image="handlePaste"
            @file-select="handleFilesSelected"
            @clear-reply="replyTarget = null"
          />
        </section>
      </ProjectView>

      <div
        v-else
        class="conversation-stack"
        :class="{ 'is-empty': isEmptyChat }"
      >
        <section
          ref="messagesContainer"
          class="messages-panel"
          @scroll="handleMessagesScroll"
        >
          <div v-if="loadingMessages" class="center-state">
            <v-progress-circular indeterminate size="32" width="3" />
          </div>

          <div v-else-if="!activeMessages.length" class="welcome-state">
            <div class="welcome-title">{{ tm("welcome.title") }}</div>
          </div>

          <div
            v-if="!loadingMessages && activeMessages.length"
            class="messages-list-shell"
          >
            <ChatMessageList
              v-model:edit-draft="messageEditDraft"
              :messages="activeMessages"
              :is-dark="isDark"
              :is-streaming="
                Boolean(currSessionId && isSessionRunning(currSessionId))
              "
              :enable-edit="
                !Boolean(currSessionId && isSessionRunning(currSessionId))
              "
              enable-regenerate
              enable-thread-selection
              :manage-refs-sidebar="false"
              :editing-message-id="editingMessage?.id || null"
              :saving-edit="savingMessageEdit"
              @open-edit="openMessageEdit"
              @cancel-edit="cancelMessageEdit"
              @save-edit="saveMessageEdit"
              @regenerate="handleRegenerateMessage"
              @regenerate-with-model="handleRegenerateMessage"
              @select-bot-text="handleBotTextSelection"
              @open-thread="openThreadPanel"
              @open-reasoning="openReasoningPanel"
              @open-refs="openRefsSidebar"
            />
          </div>
        </section>

        <section class="composer-shell">
          <ChatInput
            ref="inputRef"
            v-model:prompt="draft"
            :staged-images-url="stagedImagesUrl"
            :staged-audio-url="stagedAudioUrl"
            :staged-files="stagedNonImageFiles"
            :disabled="sending"
            :enable-streaming="enableStreaming"
            :is-recording="isRecording"
            :is-running="
              Boolean(currSessionId && isSessionRunning(currSessionId))
            "
            :token-usage="tokenUsageIndicator"
            :session-id="currSessionId || null"
            :current-session="currentSession"
            :reply-to="chatInputReplyTarget"
            :send-shortcut="sendShortcut"
            :show-provider-selector="false"
            @send="sendCurrentMessage"
            @stop="stopCurrentSession"
            @toggle-streaming="toggleStreaming"
            @remove-image="removeImage"
            @remove-audio="removeAudio"
            @remove-file="removeFile"
            @start-recording="startRecording"
            @stop-recording="stopRecording"
            @paste-image="handlePaste"
            @file-select="handleFilesSelected"
            @clear-reply="replyTarget = null"
          />
        </section>
      </div>
    </main>

    <div
      v-if="threadSelection.visible"
      class="thread-selection-action"
      :style="{
        left: `${threadSelection.left}px`,
        top: `${threadSelection.top}px`,
      }"
    >
      <button
        class="thread-selection-button"
        type="button"
        @click="createThreadFromSelection"
      >
        {{ tm("thread.askInThread") }}
      </button>
    </div>

    <ProjectDialog
      v-model="projectDialogOpen"
      :project="editingProject"
      :error-message="projectDialogError"
      :saving="savingProject"
      @save="saveProject"
    />
    <v-dialog v-model="sessionTitleDialogOpen" max-width="420">
      <v-card>
        <v-card-title class="text-h3 pa-4 pb-0 pl-6">
          {{ tm("conversation.editDisplayName") }}
        </v-card-title>
        <v-card-text>
          <v-text-field
            v-model="sessionTitleDraft"
            :label="tm('conversation.displayName')"
            variant="outlined"
            density="comfortable"
            hide-details
            autofocus
            @keydown.enter="saveSessionTitleDialog"
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="sessionTitleDialogOpen = false">
            {{ t("core.common.cancel") }}
          </v-btn>
          <v-btn
            color="primary"
            variant="tonal"
            :loading="savingSessionTitle"
            @click="saveSessionTitleDialog"
          >
            {{ t("core.common.save") }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
    <ThreadPanel
      v-model="threadPanelOpen"
      :thread="activeThread"
      :is-dark="isDark"
      :deleting="deletingThread"
      @delete="deleteThread"
    />
    <ReasoningSidebar
      v-model="reasoningPanelOpen"
      :parts="activeReasoningParts"
      :is-dark="isDark"
    />
    <RefsSidebar v-model="refsSidebarOpen" :refs="selectedRefs" />
  </div>
</template>

<script setup lang="ts">
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  provide,
  reactive,
  ref,
  watch,
} from "vue";
import { useRoute, useRouter } from "vue-router";
import { useDisplay } from "vuetify";
import { isAxiosError } from "axios";
import {
  Box,
  Cable,
  Check,
  ChevronRight,
  Languages,
  Moon,
  PanelLeft,
  Pencil,
  Settings,
  SquarePen,
  Sun,
  Trash2,
} from "@lucide/vue";
import { chatApi, providerApi } from "@/api/v1";
import StyledMenu from "@/components/shared/StyledMenu.vue";
import ProjectDialog, {
  type ProjectFormData,
} from "@/components/chat/ProjectDialog.vue";
import ProjectList, { type Project } from "@/components/chat/ProjectList.vue";
import ProjectView from "@/components/chat/ProjectView.vue";
import ChatInput from "@/components/chat/ChatInput.vue";
import ChatMessageList from "@/components/chat/ChatMessageList.vue";
import ChatUILogo from "@/components/chat/ChatUILogo.vue";
import type { RegenerateModelSelection } from "@/components/chat/RegenerateMenu.vue";
import ReasoningSidebar from "@/components/chat/ReasoningSidebar.vue";
import ThreadPanel from "@/components/chat/ThreadPanel.vue";
import RefsSidebar from "@/components/chat/message_list_comps/RefsSidebar.vue";
import { useSessions, type Session } from "@/composables/useSessions";
import {
  messageBlocks as buildMessageBlocks,
  useMessages,
  type ChatRecord,
  type ChatThread,
  type MessagePart,
  type TransportMode,
} from "@/composables/useMessages";
import { useMediaHandling } from "@/composables/useMediaHandling";
import { useRecording } from "@/composables/useRecording";
import { useProjects } from "@/composables/useProjects";
import { useChatHeaderStore } from "@/stores/chatHeader";
import { useCustomizerStore } from "@/stores/customizer";
import ProviderChatCompletionPanel from "@/components/provider/ProviderChatCompletionPanel.vue";
import {
  useI18n,
  useLanguageSwitcher,
  useModuleI18n,
} from "@/i18n/composables";
import type { Locale } from "@/i18n/types";
import { askForConfirmation, useConfirmDialog } from "@/utils/confirmDialog";
import {
  contextLimit,
  formatTokenCount,
  type ProviderModelMetadata,
  type ProviderMetadataSource,
} from "@/utils/providerMetadata";
import { useToast } from "@/utils/toast";

const props = withDefaults(defineProps<{ chatboxMode?: boolean; active?: boolean }>(), {
  chatboxMode: false,
  active: true,
});

const route = useRoute();
const router = useRouter();
const { lgAndUp } = useDisplay();
const chatHeader = useChatHeaderStore();
const customizer = useCustomizerStore();
const { t } = useI18n();
const { tm } = useModuleI18n("features/chat");
const confirmDialog = useConfirmDialog();
const toast = useToast();
const { languageOptions, currentLanguage, switchLanguage, locale } =
  useLanguageSwitcher();
const {
  sessions,
  currSessionId,
  getSessions,
  newSession,
  newChat,
  deleteSession,
  updateSessionTitle,
} = useSessions(props.chatboxMode);
const {
  projects,
  selectedProjectId,
  getProjects,
  createProject,
  updateProject,
  deleteProject: deleteProjectById,
  addSessionToProject,
  getProjectSessions,
} = useProjects();

const {
  stagedFiles,
  stagedImagesUrl,
  stagedAudioUrl,
  stagedNonImageFiles,
  processAndUploadImage,
  processAndUploadFile,
  handlePaste,
  removeImage,
  removeAudio,
  removeFile,
  clearStaged,
  cleanupMediaCache,
} = useMediaHandling();

type WorkspaceView = "chat" | "providers";

interface TokenProviderConfig extends ProviderMetadataSource {
  id: string;
  enable?: boolean;
}

const activeWorkspace = ref<WorkspaceView>("chat");
const projectDialogOpen = ref(false);
const editingProject = ref<Project | null>(null);
const projectDialogError = ref("");
const savingProject = ref(false);
const sessionTitleDialogOpen = ref(false);
const sessionTitleDraft = ref("");
const editingSessionTitleId = ref("");
const refreshProjectSessionsAfterTitleSave = ref(false);
const savingSessionTitle = ref(false);
const messageEditDraft = ref("");
const editingMessage = ref<ChatRecord | null>(null);
const savingMessageEdit = ref(false);
const projectSessions = ref<Session[]>([]);
const projectSessionsById = ref<Record<string, Session[]>>({});
const loadingProjectSessionIds = ref<string[]>([]);
const loadingSessions = ref(false);
const draft = ref("");
const tokenProviderConfigs = ref<TokenProviderConfig[]>([]);
const tokenModelMetadata = ref<Record<string, ProviderModelMetadata>>({});
const selectedTokenProviderId = ref("");
const messagesContainer = ref<HTMLElement | null>(null);
const inputRef = ref<InstanceType<typeof ChatInput> | null>(null);
const shouldStickToBottom = ref(true);
const replyTarget = ref<ChatRecord | null>(null);
const threadPanelOpen = ref(false);
const activeThread = ref<ChatThread | null>(null);
const reasoningPanelOpen = ref(false);
const activeReasoningTarget = ref<{
  message: ChatRecord;
  blockIndex: number;
} | null>(null);
const deletingThread = ref(false);
const refsSidebarOpen = ref(false);
const selectedRefs = ref<Record<string, unknown> | null>(null);
const threadSelection = reactive<{
  visible: boolean;
  left: number;
  top: number;
  message: ChatRecord | null;
  selectedText: string;
}>({
  visible: false,
  left: 0,
  top: 0,
  message: null,
  selectedText: "",
});
const enableStreaming = ref(true);
const sendShortcut = ref<"enter" | "shift_enter">("enter");
const {
  isRecording,
  startRecording: startRecorder,
  stopRecording: stopRecorder,
} = useRecording();
const chatSidebarDrawer = computed({
  get: () => lgAndUp.value || customizer.chatSidebarOpen,
  set: (value: boolean) => {
    if (!lgAndUp.value) {
      customizer.SET_CHAT_SIDEBAR(value);
    }
  },
});
const isSidebarCollapsed = computed(() =>
  lgAndUp.value ? customizer.chatSidebarCollapsed : !customizer.chatSidebarOpen,
);
const isProviderWorkspace = computed(
  () => activeWorkspace.value === "providers",
);

function toggleChatSidebar() {
  if (lgAndUp.value) {
    customizer.SET_CHAT_SIDEBAR_COLLAPSED(!customizer.chatSidebarCollapsed);
    return;
  }
  customizer.TOGGLE_CHAT_SIDEBAR();
}

const activeReasoningParts = computed<MessagePart[]>(() => {
  if (!activeReasoningTarget.value) return [];
  const blocks = buildMessageBlocks(
    activeReasoningTarget.value.message.content || { type: "bot", message: [] },
  );
  const block = blocks[activeReasoningTarget.value.blockIndex];
  return block?.kind === "thinking" ? block.parts : [];
});

watch(reasoningPanelOpen, (open) => {
  if (!open) {
    activeReasoningTarget.value = null;
  }
});

const {
  loadingMessages,
  sending,
  loadedSessions,
  sessionProjects,
  activeMessages,
  isSessionRunning,
  isUserMessage,
  messageParts,
  loadSessionMessages,
  createLocalExchange,
  sendMessageStream,
  editMessage,
  continueEditedMessage,
  regenerateMessage,
  stopSession,
} = useMessages({
  currentSessionId: currSessionId,
  onSessionsChanged: getSessions,
  onStreamUpdate: (sessionId) => {
    if (sessionId === currSessionId.value && shouldStickToBottom.value) {
      scrollToBottom();
    }
  },
});

const transportMode = ref<TransportMode>(
  (localStorage.getItem("chat.transportMode") as TransportMode) === "websocket"
    ? "websocket"
    : "sse",
);
const transportOptions: Array<{ value: TransportMode; labelKey: string }> = [
  { value: "sse", labelKey: "transport.sse" },
  { value: "websocket", labelKey: "transport.websocket" },
];
const currentTransportLabel = computed(() =>
  tm(
    transportOptions.find((item) => item.value === transportMode.value)
      ?.labelKey || "transport.sse",
  ),
);

watch(transportMode, (mode) => {
  localStorage.setItem("chat.transportMode", mode);
});

const isDark = computed(() => customizer.uiTheme === "PurpleThemeDark");
const canSend = computed(
  () =>
    Boolean(draft.value.trim() || stagedFiles.value.length) && !sending.value,
);
const currentSession = computed(
  () =>
    sessions.value.find(
      (session) => session.session_id === currSessionId.value,
    ) ||
    projectSessions.value.find(
      (session) => session.session_id === currSessionId.value,
    ) ||
    Object.values(projectSessionsById.value)
      .flat()
      .find((session) => session.session_id === currSessionId.value) ||
    null,
);
const sessionProject = computed(() =>
  currSessionId.value ? sessionProjects[currSessionId.value] : null,
);
const currentSessionTitle = computed(() =>
  currentSession.value ? sessionTitle(currentSession.value) : "",
);
const selectedProject = computed(
  () =>
    projects.value.find(
      (project) => project.project_id === selectedProjectId.value,
    ) || null,
);
const isEmptyChat = computed(
  () =>
    !isProviderWorkspace.value &&
    !selectedProject.value &&
    !loadingMessages.value &&
    !activeMessages.value.length,
);
const chatHeaderTitle = computed(
  () => currentSessionTitle.value || selectedProject.value?.title || "",
);
const chatHeaderSubtitle = computed(() =>
  currentSessionTitle.value
    ? sessionProject.value?.title || selectedProject.value?.title || ""
    : "",
);
const chatInputReplyTarget = computed(() =>
  replyTarget.value?.id == null
    ? null
    : {
        messageId: replyTarget.value.id,
        selectedText: replyPreview(replyTarget.value.id, ""),
      },
);
const currentTokenProvider = computed(() => {
  const selectedProvider = tokenProviderConfigs.value.find(
    (provider) => provider.id === selectedTokenProviderId.value,
  );
  return selectedProvider || tokenProviderConfigs.value[0] || null;
});
const currentTokenMetadata = computed(() => {
  const model = currentTokenProvider.value?.model;
  return model ? tokenModelMetadata.value[model] || null : null;
});
const latestTokenUsageTotal = computed(() => {
  for (let index = activeMessages.value.length - 1; index >= 0; index -= 1) {
    const message = activeMessages.value[index];
    if (isUserMessage(message)) continue;
    const usage = message.content?.agentStats?.token_usage;
    if (!usage) continue;
    return (
      readTokenCount(usage.input_other) +
      readTokenCount(usage.input_cached) +
      readTokenCount(usage.output)
    );
  }
  return 0;
});
const tokenUsageIndicator = computed(() => {
  const used = latestTokenUsageTotal.value;
  const limit = contextLimit(currentTokenProvider.value, currentTokenMetadata.value);
  if (used <= 0 || limit <= 0) return null;

  const percent = (used / limit) * 100;
  return {
    used,
    limit,
    percent: Math.min(100, Math.max(0, percent)),
    tooltip: tm("tokenUsage.tooltip", {
      used: formatTokenCount(used),
      limit: formatTokenCount(limit),
      percent: formatUsagePercent(percent),
    }),
  };
});

function getSelectedProviderSelection() {
  const inputSelection = inputRef.value?.getCurrentSelection();
  if (inputSelection?.providerId) {
    selectedTokenProviderId.value = inputSelection.providerId;
    return inputSelection;
  }
  if (typeof window === "undefined") {
    return { providerId: "", modelName: "" };
  }
  syncSelectedTokenProvider();
  return {
    providerId: localStorage.getItem("selectedProvider") || "",
    modelName: localStorage.getItem("selectedProviderModel") || "",
  };
}

provide("isDark", isDark);

watch(
  [chatHeaderTitle, chatHeaderSubtitle],
  ([title, subtitle]) => {
    chatHeader.SET_CONTEXT({ title, subtitle });
  },
  { immediate: true },
);

onMounted(async () => {
  loadingSessions.value = true;
  try {
    await Promise.all([getSessions(), getProjects(), loadTokenProviders()]);
    const routeSessionId = getRouteSessionId();
    if (routeSessionId === "models") {
      activeWorkspace.value = "providers";
    } else if (routeSessionId) {
      await selectSession(routeSessionId, false);
    }
  } finally {
    loadingSessions.value = false;
  }
});

onBeforeUnmount(() => {
  chatHeader.CLEAR_CONTEXT();
  cleanupMediaCache();
});

watch(
  () => route.params.conversationId,
  async () => {
    const routeSessionId = getRouteSessionId();
    if (routeSessionId === "models") {
      activeWorkspace.value = "providers";
      return;
    }
    if (routeSessionId && routeSessionId !== currSessionId.value) {
      showChatWorkspace();
      selectedProjectId.value = null;
      await selectSession(routeSessionId, false);
    } else if (!routeSessionId && currSessionId.value) {
      showChatWorkspace();
      currSessionId.value = "";
    }
  },
);

watch(activeMessages, () => {
  if (shouldStickToBottom.value) {
    scrollToBottom();
  }
});

function getRouteSessionId() {
  const raw = route.params.conversationId;
  return Array.isArray(raw) ? raw[0] : raw || "";
}

function basePath() {
  return props.chatboxMode ? "/chatbox" : "/chat";
}

function closeMobileSidebar() {
  if (!lgAndUp.value) {
    customizer.SET_CHAT_SIDEBAR(false);
  }
}

function closeSecondaryPanels() {
  threadSelection.visible = false;
  threadPanelOpen.value = false;
  activeThread.value = null;
  reasoningPanelOpen.value = false;
  activeReasoningTarget.value = null;
  refsSidebarOpen.value = false;
  selectedRefs.value = null;
}

function showChatWorkspace() {
  activeWorkspace.value = "chat";
}

async function openProviderWorkspace() {
  closeSecondaryPanels();
  activeWorkspace.value = "providers";
  const targetPath = `${basePath()}/models`;
  if (route.path !== targetPath) {
    await router.push(targetPath);
  }
  closeMobileSidebar();
}

function sessionTitle(session: Session) {
  return session.display_name?.trim() || tm("conversation.newConversation");
}

function syncSelectedTokenProvider() {
  if (typeof window === "undefined") return;
  selectedTokenProviderId.value = localStorage.getItem("selectedProvider") || "";
}

async function loadTokenProviders() {
  syncSelectedTokenProvider();
  try {
    const response = await providerApi.listByProviderType("chat_completion");
    if (response.data.status === "ok") {
      tokenModelMetadata.value = (
        (response.data as any).model_metadata || {}
      ) as Record<string, ProviderModelMetadata>;
      tokenProviderConfigs.value = (
        (response.data.data || []) as unknown as TokenProviderConfig[]
      ).filter((provider) => provider.enable !== false);
    }
  } catch (error) {
    console.error("Failed to load provider context metadata:", error);
  }
}

function readTokenCount(value: unknown) {
  const count = Number(value || 0);
  return Number.isFinite(count) && count > 0 ? count : 0;
}

function formatUsagePercent(value: number) {
  if (!Number.isFinite(value) || value <= 0) return "0";
  if (value >= 10) return String(Math.round(value));
  if (value >= 1) return String(Math.round(value * 10) / 10);
  return String(Math.round(value * 100) / 100);
}

async function startNewChat() {
  showChatWorkspace();
  selectedProjectId.value = null;
  replyTarget.value = null;
  newChat();
  closeMobileSidebar();
  await focusChatInput();
}

function openCreateProjectDialog() {
  editingProject.value = null;
  projectDialogError.value = "";
  projectDialogOpen.value = true;
}

function openEditProjectDialog(project: Project) {
  editingProject.value = project;
  projectDialogError.value = "";
  projectDialogOpen.value = true;
}

async function selectProject(projectId: string) {
  showChatWorkspace();
  selectedProjectId.value = projectId;
  currSessionId.value = "";
  replyTarget.value = null;
  await router.push(basePath());
  await loadProjectSessions(projectId);
  closeMobileSidebar();
}

async function loadProjectSessions(projectId = selectedProjectId.value) {
  if (!projectId) {
    projectSessions.value = [];
    return [];
  }
  const sessions = await getProjectSessions(projectId);
  projectSessionsById.value = {
    ...projectSessionsById.value,
    [projectId]: sessions,
  };
  if (projectId === selectedProjectId.value) {
    projectSessions.value = sessions;
  }
  return sessions;
}

async function handleProjectToggle(projectId: string, expanded: boolean) {
  if (!expanded || projectSessionsById.value[projectId]) return;
  if (loadingProjectSessionIds.value.includes(projectId)) return;
  loadingProjectSessionIds.value = [...loadingProjectSessionIds.value, projectId];
  try {
    await loadProjectSessions(projectId);
  } finally {
    loadingProjectSessionIds.value = loadingProjectSessionIds.value.filter(
      (item) => item !== projectId,
    );
  }
}

async function handleDeleteProject(projectId: string) {
  await deleteProjectById(projectId);
  const nextSessionsById = { ...projectSessionsById.value };
  delete nextSessionsById[projectId];
  projectSessionsById.value = nextSessionsById;
  loadingProjectSessionIds.value = loadingProjectSessionIds.value.filter(
    (item) => item !== projectId,
  );
  if (selectedProjectId.value === projectId) {
    selectedProjectId.value = null;
    projectSessions.value = [];
  }
}

function openSessionTitleDialog(
  sessionId: string,
  title: string,
  refreshProjectSessions = false,
) {
  editingSessionTitleId.value = sessionId;
  sessionTitleDraft.value = title;
  refreshProjectSessionsAfterTitleSave.value = refreshProjectSessions;
  sessionTitleDialogOpen.value = true;
}

async function saveSessionTitleDialog() {
  if (!editingSessionTitleId.value) return;

  savingSessionTitle.value = true;
  try {
    const sessionId = editingSessionTitleId.value;
    const displayName = sessionTitleDraft.value.trim();
    await chatApi.updateSession(sessionId, {
      display_name: displayName,
    });
    updateSessionTitle(sessionId, displayName);
    const projectSession = projectSessions.value.find(
      (session) => session.session_id === sessionId,
    );
    if (projectSession) {
      projectSession.display_name = displayName;
    }
    Object.values(projectSessionsById.value).forEach((projectSessionList) => {
      const cachedProjectSession = projectSessionList.find(
        (session) => session.session_id === sessionId,
      );
      if (cachedProjectSession) {
        cachedProjectSession.display_name = displayName;
      }
    });
    if (refreshProjectSessionsAfterTitleSave.value) {
      await loadProjectSessions();
    }
    sessionTitleDialogOpen.value = false;
  } finally {
    savingSessionTitle.value = false;
  }
}

function editSidebarSessionTitle(session: Session) {
  openSessionTitleDialog(session.session_id, session.display_name || "");
}

async function deleteSidebarSession(session: Session) {
  const title = sessionTitle(session);
  const message = tm("conversation.confirmDelete", { name: title });
  if (!(await askForConfirmation(message, confirmDialog))) return;

  const wasCurrent = currSessionId.value === session.session_id;
  await deleteSession(session.session_id);
  if (wasCurrent) {
    selectedProjectId.value = null;
    await router.push(basePath());
  }
}

async function selectProjectSession(sessionId: string) {
  selectedProjectId.value = null;
  await selectSession(sessionId);
}

async function editProjectSessionTitle(sessionId: string, title: string) {
  openSessionTitleDialog(sessionId, title, true);
}

async function deleteProjectSession(
  sessionId: string,
  projectId = selectedProjectId.value,
) {
  await deleteSession(sessionId);
  if (projectId) {
    await loadProjectSessions(projectId);
  } else {
    await loadProjectSessions();
  }
}

async function saveProject(formData: ProjectFormData, projectId?: string) {
  savingProject.value = true;
  projectDialogError.value = "";
  try {
    if (projectId) {
      await updateProject(
        projectId,
        formData.title,
        formData.emoji,
        formData.description,
        formData.workspace_type,
        formData.workspace_path,
      );
    } else {
      await createProject(
        formData.title,
        formData.emoji,
        formData.description,
        formData.workspace_type,
        formData.workspace_path,
      );
    }
    projectDialogOpen.value = false;
    editingProject.value = null;
  } catch (error) {
    projectDialogError.value =
      error instanceof Error ? error.message : "Failed to save project";
  } finally {
    savingProject.value = false;
  }
}

watch(projectDialogOpen, (open) => {
  if (!open) {
    projectDialogError.value = "";
    savingProject.value = false;
  }
});

async function selectSession(sessionId: string, pushRoute = true) {
  showChatWorkspace();
  selectedProjectId.value = null;
  currSessionId.value = sessionId;
  replyTarget.value = null;
  if (pushRoute && route.path !== `${basePath()}/${sessionId}`) {
    await router.push(`${basePath()}/${sessionId}`);
  }
  if (!loadedSessions[sessionId]) {
    await loadSessionMessages(sessionId);
  }
  scrollToBottom();
  closeMobileSidebar();
  await focusChatInput();
}

async function sendCurrentMessage() {
  if (!canSend.value) return;

  sending.value = true;
  try {
    let sessionId = currSessionId.value;
    const targetProjectId = selectedProjectId.value;
    const targetProject = selectedProject.value;
    if (!sessionId) {
      sessionId = await newSession();
      if (targetProjectId) {
        await addSessionToProject(sessionId, targetProjectId);
        sessionProjects[sessionId] = targetProject
          ? {
              project_id: targetProject.project_id,
              title: targetProject.title,
              emoji: targetProject.emoji,
            }
          : null;
        await loadProjectSessions(targetProjectId);
        selectedProjectId.value = null;
      }
    }

    const text = draft.value.trim();
    const messageId = crypto.randomUUID?.() || `${Date.now()}-${Math.random()}`;
    const outgoingParts = buildOutgoingParts(text);
    const selection = getSelectedProviderSelection();
    const { userRecord, botRecord } = createLocalExchange({
      sessionId,
      messageId,
      parts: outgoingParts,
    });
    updateTitleFromText(sessionId, text);

    draft.value = "";
    replyTarget.value = null;
    clearStaged({ revokeUrls: false });
    scrollToBottom();

    sendMessageStream({
      sessionId,
      messageId,
      parts: outgoingParts,
      transport: transportMode.value,
      enableStreaming: enableStreaming.value,
      selectedProvider: selection?.providerId || "",
      selectedModel: selection?.modelName || "",
      userRecord,
      botRecord,
    });
  } catch (error) {
    console.error("Failed to send message:", error);
  } finally {
    sending.value = false;
    await focusChatInput();
  }
}

function buildOutgoingParts(text: string): MessagePart[] {
  const parts: MessagePart[] = [];
  if (replyTarget.value?.id != null) {
    parts.push({
      type: "reply",
      message_id: replyTarget.value.id,
      selected_text: "",
    });
  }
  if (text) {
    parts.push({ type: "plain", text });
  }
  stagedFiles.value.forEach((file) => {
    parts.push({
      type: file.type,
      attachment_id: file.attachment_id,
      filename: file.filename,
      embedded_url: file.url,
    });
  });
  return parts;
}

function updateTitleFromText(sessionId: string, text: string) {
  const session = sessions.value.find((item) => item.session_id === sessionId);
  const projectSession = projectSessions.value.find(
    (item) => item.session_id === sessionId,
  );
  const cachedProjectSessions = Object.values(projectSessionsById.value)
    .flat()
    .filter((item) => item.session_id === sessionId);
  if (
    (!session && !projectSession && !cachedProjectSessions.length) ||
    session?.display_name ||
    projectSession?.display_name ||
    cachedProjectSessions.some((item) => item.display_name) ||
    !text
  ) {
    return;
  }
  updateSessionTitle(sessionId, text.slice(0, 40));
  if (projectSession) {
    projectSession.display_name = text.slice(0, 40);
  }
  cachedProjectSessions.forEach((item) => {
    item.display_name = text.slice(0, 40);
  });
}

function replyPreview(messageId?: string | number, fallback?: string) {
  if (fallback) return truncate(fallback, 80);
  const found = activeMessages.value.find(
    (message) => String(message.id) === String(messageId),
  );
  const text = found ? plainTextFromMessage(found) : "";
  return text ? truncate(text, 80) : tm("reply.replyTo");
}

function plainTextFromMessage(message: ChatRecord) {
  return messageParts(message)
    .filter((part) => part.type === "plain" && part.text)
    .map((part) => part.text)
    .join("\n");
}

function truncate(value: string, max: number) {
  return value.length > max ? `${value.slice(0, max)}...` : value;
}

function scrollToMessage(messageId?: string | number) {
  if (!messageId) return;
  const index = activeMessages.value.findIndex(
    (message) => String(message.id) === String(messageId),
  );
  if (index < 0) return;
  const rows = messagesContainer.value?.querySelectorAll(".message-row");
  rows?.[index]?.scrollIntoView({ behavior: "smooth", block: "center" });
}

function openMessageEdit(message: ChatRecord) {
  messageEditDraft.value = plainTextFromMessage(message);
  editingMessage.value = message;
  nextTick(() => scrollToMessage(message.id));
}

function cancelMessageEdit() {
  editingMessage.value = null;
  messageEditDraft.value = "";
}

async function saveMessageEdit() {
  if (!currSessionId.value || !editingMessage.value) return;
  savingMessageEdit.value = true;
  try {
    const target = editingMessage.value;
    const result = await editMessage(
      currSessionId.value,
      target,
      messageEditDraft.value,
    );
    cancelMessageEdit();

    if (result.needsRegenerate && result.truncatedAfterMessage) {
      const selection = getSelectedProviderSelection();
      continueEditedMessage({
        sessionId: currSessionId.value,
        sourceRecord: target,
        enableStreaming: enableStreaming.value,
        selectedProvider: selection?.providerId || "",
        selectedModel: selection?.modelName || "",
      });
      scrollToBottom();
    } else if (result.needsRegenerate) {
      const index = activeMessages.value.findIndex(
        (message) => String(message.id) === String(target.id),
      );
      const nextBot = activeMessages.value
        .slice(index + 1)
        .find((message) => !isUserMessage(message));
      if (nextBot) {
        await handleRegenerateMessage(nextBot);
      }
    }
  } catch (error) {
    console.error("Failed to edit message:", error);
  } finally {
    savingMessageEdit.value = false;
  }
}

async function handleRegenerateMessage(
  message: ChatRecord,
  selection?: RegenerateModelSelection,
) {
  if (!currSessionId.value || isUserMessage(message)) return;
  message.threads = [];
  await regenerateMessage(
    currSessionId.value,
    message,
    selection?.providerId || "",
    selection?.modelName || "",
  );
}

function handleBotTextSelection(event: MouseEvent, message: ChatRecord) {
  if (message.id == null || String(message.id).startsWith("local-")) return;
  const container = event.currentTarget as HTMLElement | null;
  window.setTimeout(() => {
    const selection = window.getSelection();
    const selectedText = selection?.toString().trim() || "";
    if (!selection || !selectedText) {
      threadSelection.visible = false;
      return;
    }
    if (
      !container ||
      !container.contains(selection.anchorNode) ||
      !container.contains(selection.focusNode)
    ) {
      threadSelection.visible = false;
      return;
    }
    const range = selection.getRangeAt(0);
    const rect = range.getBoundingClientRect();
    threadSelection.message = message;
    threadSelection.selectedText = selectedText;
    threadSelection.left = Math.min(
      window.innerWidth - 180,
      Math.max(12, rect.left + rect.width / 2 - 70),
    );
    threadSelection.top = Math.max(12, rect.top - 42);
    threadSelection.visible = true;
  }, 0);
}

async function createThreadFromSelection() {
  const message = threadSelection.message;
  if (!currSessionId.value || !message?.id || !threadSelection.selectedText) return;
  try {
    const response = await chatApi.createThread({
      session_id: currSessionId.value,
      parent_message_id: message.id,
      selected_text: threadSelection.selectedText,
    });
    if (response.data?.status !== "ok") {
      toast.error(response.data?.message || tm("thread.createFailed"));
      return;
    }
    const thread = response.data?.data as ChatThread | undefined;
    if (!thread) {
      toast.error(tm("thread.createFailed"));
      return;
    }
    message.threads = message.threads || [];
    if (!message.threads.some((item) => item.thread_id === thread.thread_id)) {
      message.threads.push(thread);
    }
    openThreadPanel(thread);
    window.getSelection()?.removeAllRanges();
  } catch (error) {
    toast.error(
      isAxiosError(error)
        ? error.response?.data?.message || error.message
        : tm("thread.createFailed"),
    );
    console.error("Failed to create thread:", error);
  } finally {
    threadSelection.visible = false;
  }
}

function openThreadPanel(thread: ChatThread) {
  reasoningPanelOpen.value = false;
  activeReasoningTarget.value = null;
  refsSidebarOpen.value = false;
  activeThread.value = thread;
  threadPanelOpen.value = true;
}

function openRefsSidebar(refs: unknown) {
  threadPanelOpen.value = false;
  activeThread.value = null;
  reasoningPanelOpen.value = false;
  activeReasoningTarget.value = null;
  selectedRefs.value =
    refs && typeof refs === "object" ? (refs as Record<string, unknown>) : null;
  refsSidebarOpen.value = true;
}

function openReasoningPanel(payload: {
  message: ChatRecord;
  blockIndex: number;
}) {
  threadPanelOpen.value = false;
  activeThread.value = null;
  refsSidebarOpen.value = false;
  selectedRefs.value = null;
  activeReasoningTarget.value = payload;
  reasoningPanelOpen.value = true;
}

async function deleteThread(thread: ChatThread) {
  if (deletingThread.value) return;
  if (!(await askForConfirmation(tm("thread.confirmDelete"), confirmDialog))) return;
  deletingThread.value = true;
  try {
    await chatApi.deleteThread(thread.thread_id);
    removeThreadFromMessages(thread.thread_id);
    if (activeThread.value?.thread_id === thread.thread_id) {
      threadPanelOpen.value = false;
      activeThread.value = null;
    }
  } catch (error) {
    console.error("Failed to delete thread:", error);
  } finally {
    deletingThread.value = false;
  }
}

function removeThreadFromMessages(threadId: string) {
  for (const message of activeMessages.value) {
    if (!message.threads?.length) continue;
    message.threads = message.threads.filter(
      (thread) => thread.thread_id !== threadId,
    );
  }
}

async function handleFilesSelected(files: FileList) {
  const selectedFiles = Array.from(files || []);
  for (const file of selectedFiles) {
    if (file.type.startsWith("image/")) {
      await processAndUploadImage(file);
    } else {
      await processAndUploadFile(file);
    }
  }
}

function toggleStreaming() {
  enableStreaming.value = !enableStreaming.value;
}

async function startRecording() {
  try {
    await startRecorder();
  } catch (error) {
    console.error("Failed to start recording:", error);
    toast.error(tm("voice.error"));
  }
}

async function stopRecording() {
  try {
    const audioFile = await stopRecorder();
    const uploaded = await processAndUploadFile(audioFile);
    if (!uploaded) {
      toast.error(tm("voice.error"));
    }
  } catch (error) {
    console.error("Failed to stop recording:", error);
    toast.error(tm("voice.error"));
  }
}

function handleMessagesScroll() {
  threadSelection.visible = false;
  const container = messagesContainer.value;
  if (!container) return;
  const distance =
    container.scrollHeight - container.scrollTop - container.clientHeight;
  shouldStickToBottom.value = distance < 80;
}

function scrollToBottom() {
  nextTick(() => {
    const container = messagesContainer.value;
    if (!container) return;
    container.scrollTop = container.scrollHeight;
    shouldStickToBottom.value = true;
  });
}

async function focusChatInput() {
  await nextTick();
  window.requestAnimationFrame(() => {
    inputRef.value?.focusInput();
  });
}

async function stopCurrentSession() {
  if (!currSessionId.value) return;
  try {
    await stopSession(currSessionId.value);
  } catch (error) {
    console.error("Failed to stop session:", error);
  }
}

function toggleTheme() {
  customizer.SET_UI_THEME(isDark.value ? "PurpleTheme" : "PurpleThemeDark");
}
</script>

<style scoped>
.chat-ui {
  --chat-panel-top-offset: 50px;
  --chat-sidebar-bg: rgb(var(--v-theme-surface));
  --chat-session-active-bg: #efefef;
  --chat-page-bg: #fdfcfc;
  --chat-border: #f2f2f2;
  --chat-muted: rgba(var(--v-theme-on-surface), 0.62);
  --chat-section-label: rgba(var(--v-theme-on-surface), 0.48);
  --chat-content-width: 76%;
  --chat-content-max-width: 760px;
  display: flex;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  background: var(--chat-page-bg);
  color: rgb(var(--v-theme-on-surface));
  font-family:
    system-ui,
    -apple-system,
    BlinkMacSystemFont,
    "Segoe UI",
    Roboto,
    Oxygen,
    Ubuntu,
    Cantarell,
    "Open Sans",
    "Helvetica Neue",
    sans-serif;
}

.chat-ui.is-dark {
  --chat-sidebar-bg: #2d2d2d;
  --chat-session-active-bg: rgba(255, 255, 255, 0.08);
  --chat-page-bg: rgb(var(--v-theme-background));
  --chat-border: rgba(255, 255, 255, 0.1);
  --chat-section-label: rgba(255, 255, 255, 0.5);
}

.chat-sidebar {
  top: 0 !important;
  height: 100vh !important;
  background: var(--chat-sidebar-bg);
  border-right: 1px solid var(--chat-border);
}

.chat-sidebar.collapsed {
  background: var(--chat-sidebar-bg);
  border-right: 1px solid var(--chat-border);
}

.chat-sidebar :deep(.v-navigation-drawer__content) {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.sidebar-top {
  padding: 0 16px 2px;
}

.chat-sidebar.collapsed .sidebar-top {
  width: 56px;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 0 0 2px;
}

.chat-sidebar-brand {
  min-height: 50px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 0 10px 2px;
}

.chat-sidebar-brand.collapsed {
  width: 36px;
  justify-content: center;
  padding: 0 0 2px;
}

.chat-sidebar-brand-title {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  color: rgb(var(--v-theme-on-surface));
  line-height: 1.05;
}

.chat-sidebar-brand-logo {
  width: 22px;
  height: 22px;
  flex: 0 0 22px;
  display: block;
}

.chat-sidebar-brand-title .chat-sidebar-brand-logo {
  transform: translateX(-2px);
}

.chat-sidebar-brand-copy {
  min-width: 0;
  display: inline-flex;
  align-items: baseline;
  gap: 5px;
}

.chat-sidebar-brand-name {
  font-size: 18px;
  font-weight: 800;
}

.chat-sidebar-brand-mode {
  color: var(--chat-muted);
  font-size: 18px;
  font-weight: 500;
}

.chat-sidebar-brand-toggle {
  width: 36px;
  height: 36px;
  min-width: 36px;
  color: var(--chat-muted);
}

.chat-sidebar-rail-btn {
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: rgb(var(--v-theme-on-surface));
  cursor: pointer;
  display: grid;
  place-items: center;
  padding: 0;
}

.chat-sidebar-brand-toggle:hover {
  background: var(--chat-session-active-bg);
  color: rgb(var(--v-theme-on-surface));
}

.chat-sidebar-rail-icon-stack {
  width: 24px;
  height: 24px;
  display: grid;
  place-items: center;
}

.chat-sidebar-rail-icon-stack > * {
  grid-area: 1 / 1;
}

.chat-sidebar-brand-logo--collapsed {
  width: 20px;
  height: 20px;
  transition:
    opacity 0.14s ease,
    visibility 0.14s ease;
  opacity: 1;
  visibility: visible;
}

.chat-sidebar-rail-icon-stack .sidebar-panel-toggle-icon {
  transition:
    opacity 0.14s ease,
    visibility 0.14s ease;
  opacity: 0;
  visibility: hidden;
}

.chat-sidebar-brand-toggle:hover .chat-sidebar-brand-logo--collapsed,
.chat-sidebar-brand-toggle:focus-visible .chat-sidebar-brand-logo--collapsed {
  opacity: 0;
  visibility: hidden;
}

.chat-sidebar-brand-toggle:hover .sidebar-panel-toggle-icon,
.chat-sidebar-brand-toggle:focus-visible .sidebar-panel-toggle-icon {
  opacity: 1;
  visibility: visible;
}

.sidebar-panel-toggle-icon {
  flex: 0 0 auto;
}

.new-chat-btn,
.settings-btn {
  color: rgb(var(--v-theme-on-surface));
  border-radius: 8px;
}

.sidebar-action-icon {
  color: currentcolor;
  flex: 0 0 auto;
  stroke-width: 2;
}

.new-chat-btn:not(.icon-only) .sidebar-action-icon {
  margin-right: 12px !important;
}

.new-chat-btn,
.settings-btn {
  width: 100%;
  min-height: 36px;
  height: 36px;
  justify-content: flex-start;
  border-radius: 8px;
  text-transform: none;
  letter-spacing: 0;
  font-size: 14px;
  font-weight: 500;
}

.sidebar-provider-btn {
  margin-bottom: 2px;
}

.new-chat-btn:not(.icon-only),
.settings-btn:not(.icon-only) {
  padding-inline: 10px;
}

.new-chat-btn.icon-only,
.settings-btn.icon-only {
  width: 36px !important;
  height: 36px !important;
  min-width: 36px !important;
  margin-inline: auto;
  padding: 0 !important;
  justify-content: center;
}

.chat-sidebar.collapsed .new-chat-btn.icon-only :deep(.v-btn__content),
.chat-sidebar.collapsed .settings-btn.icon-only :deep(.v-btn__content) {
  display: flex;
  align-items: center;
  justify-content: center;
}

.new-chat-btn :deep(.v-btn__content),
.settings-btn :deep(.v-btn__content) {
  min-width: 0;
  font-size: 14px;
  line-height: 20px;
}

.chat-sidebar.collapsed .sidebar-footer {
  display: flex;
  justify-content: center;
}

.new-chat-btn:hover,
.settings-btn:hover {
  background: var(--chat-session-active-bg);
}

.sidebar-workspace-btn--active {
  background: var(--chat-session-active-bg);
  color: rgb(var(--v-theme-on-surface));
}

.sidebar-content {
  flex: 1;
  overflow-y: auto;
  padding: 2px 16px 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.sidebar-section {
  flex: 0 0 auto;
}

.sidebar-section-header {
  min-height: 24px;
  display: flex;
  align-items: center;
  padding: 0 10px 4px;
  color: var(--chat-section-label);
  font-size: 12px;
  font-weight: 500;
}

.session-list {
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.session-item {
  width: 100%;
  min-height: 30px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: inherit;
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 4px 56px 4px 10px;
  position: relative;
  box-sizing: border-box;
  cursor: pointer;
  text-align: left;
}

.session-item:hover,
.session-item.active {
  background: var(--chat-session-active-bg);
}

.session-title {
  min-width: 0;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 14px;
  font-weight: 500;
}

.session-progress {
  position: absolute;
  right: 4px;
  top: 50%;
  transform: translateY(-50%);
  flex-shrink: 0;
  transition:
    opacity 0.14s ease,
    visibility 0.14s ease;
}

.session-actions {
  display: flex;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
  opacity: 0;
  pointer-events: none;
  position: absolute;
  right: 0;
  top: 50%;
  transform: translateY(-50%);
  visibility: hidden;
}

.session-item:hover .session-actions,
.session-item:focus-within .session-actions {
  opacity: 1;
  pointer-events: auto;
  visibility: visible;
}

.session-item:hover .session-progress,
.session-item:focus-within .session-progress {
  opacity: 0;
  visibility: hidden;
}

.session-action-btn {
  color: var(--chat-muted);
}

.session-action-btn:hover {
  color: rgb(var(--v-theme-on-surface));
}

.sidebar-footer {
  margin-top: auto;
  padding: 10px 16px 14px;
}

.chat-sidebar.collapsed .sidebar-footer {
  width: 56px;
  box-sizing: border-box;
  padding-inline: 10px;
}

.settings-menu-content {
  min-width: 270px;
  padding: 6px;
}

.settings-menu-item {
  min-height: 42px;
}

.settings-menu-content :deep(.settings-menu-item .v-list-item__prepend) {
  width: 28px;
  margin-inline-end: 12px;
  align-self: center;
}

.settings-menu-content :deep(.settings-menu-item .v-list-item__content) {
  min-width: 0;
}

.settings-menu-content :deep(.settings-menu-item .v-list-item-title) {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.settings-menu-content :deep(.settings-menu-item .v-list-item__append) {
  margin-inline-start: auto;
  padding-inline-start: 18px;
  gap: 8px;
  align-self: center;
}

.styled-menu-lucide-icon {
  flex: 0 0 auto;
  color: currentcolor;
  stroke-width: 2;
}

.settings-menu-value {
  color: var(--chat-muted);
  font-size: 12px;
  margin-right: 4px;
  max-width: 92px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.language-flag {
  display: inline-block;
  width: 20px;
  margin-right: 8px;
}

.chat-main {
  flex: 1;
  min-width: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
  position: relative;
  box-sizing: border-box;
  padding-top: 50px;
}

.provider-workspace-shell {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.provider-workspace-page {
  height: 100%;
  min-height: 0;
}

.conversation-stack {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  position: relative;
}

.conversation-stack.is-empty {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 28px;
}

.messages-panel {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 24px 0 116px;
  scroll-padding-bottom: 116px;
}

.conversation-stack.is-empty .messages-panel {
  flex: none;
  min-height: auto;
  overflow: visible;
  padding: 0;
  scroll-padding-bottom: 0;
}

.messages-list-shell {
  width: var(--chat-content-width);
  max-width: var(--chat-content-max-width);
  margin: 0 auto;
}

.center-state,
.welcome-state {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
}

.conversation-stack.is-empty .welcome-state {
  height: auto;
}

.welcome-title {
  font-family: "Outfit", "Noto Sans", sans-serif;
  font-size: 28px;
  font-weight: 800;
}

.welcome-subtitle {
  margin-top: 8px;
  color: var(--chat-muted);
  font-size: 16px;
}

.thread-selection-action {
  position: fixed;
  z-index: 1200;
  pointer-events: auto;
}

.thread-selection-button {
  min-height: 34px;
  padding: 0 14px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.14);
  border-radius: 999px;
  background: rgb(var(--v-theme-surface));
  color: rgb(var(--v-theme-on-surface));
  box-shadow: 0 10px 28px rgba(0, 0, 0, 0.14);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
}

.composer-shell {
  position: relative;
  z-index: 3;
  isolation: isolate;
  background: transparent;
  padding: 0 0 18px;
}

.conversation-stack:not(.is-empty) .composer-shell {
  position: absolute;
  right: 0;
  bottom: 0;
  left: 0;
  pointer-events: none;
}

.conversation-stack:not(.is-empty) .composer-shell::before {
  content: "";
  position: absolute;
  z-index: 0;
  top: 32px;
  right: 0;
  bottom: 0;
  left: 0;
  pointer-events: none;
  background: var(--chat-page-bg);
}

.composer-shell :deep(.input-area),
.project-composer-shell :deep(.input-area) {
  padding-top: 0;
  border-top: 0;
}

.conversation-stack:not(.is-empty) .composer-shell :deep(.input-area) {
  position: relative;
  z-index: 1;
  pointer-events: none;
  background: transparent;
}

.conversation-stack:not(.is-empty) .composer-shell :deep(.input-container) {
  pointer-events: auto;
}

.conversation-stack.is-empty .composer-shell {
  padding-bottom: 0;
}

kbd {
  padding: 1px 5px;
  border-radius: 4px;
  background: rgba(var(--v-theme-on-surface), 0.08);
  font: inherit;
}

:deep(.hr-node) {
    margin-top: 1.25rem;
    margin-bottom: 1.25rem;
    opacity: 0.5;
    border-top-width: .3px;
}

:deep(.paragraph-node) {
    margin: .5rem 0;
    line-height: 1.7;
}

:deep(.list-node) {
    margin-top: .5rem;
    margin-bottom: .5rem;
}

@media (max-width: 760px) {
  .chat-sidebar {
    top: 50px !important;
    height: calc(100vh - 50px) !important;
  }

  .messages-panel {
    padding: 18px 0 92px;
    scroll-padding-bottom: 92px;
  }

  .conversation-stack.is-empty .messages-panel {
    padding: 0;
    scroll-padding-bottom: 0;
  }

  .messages-list-shell {
    width: calc(100% - 20px);
    max-width: 100%;
  }

  .composer-shell,
  .project-composer-shell {
    padding: 0;
  }
}
</style>
