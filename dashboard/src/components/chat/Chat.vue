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
      :rail="lgAndUp && sidebarCollapsed"
      :width="280"
      :rail-width="68"
      location="left"
      floating
    >
      <div class="sidebar-top">
        <div v-if="lgAndUp" class="brand-row">
          <v-btn
            icon
            size="small"
            variant="text"
            class="sidebar-toggle"
            @click="sidebarCollapsed = !sidebarCollapsed"
          >
            <v-icon
              size="20"
              class="sidebar-action-icon"
              :class="{ 'chevron-collapsed': isSidebarCollapsed }"
            >
              mdi-chevron-left
            </v-icon>
          </v-btn>
        </div>

        <v-btn
          class="new-chat-btn sidebar-provider-btn"
          :class="{
            'icon-only': isSidebarCollapsed,
            'sidebar-workspace-btn--active': isProviderWorkspace,
          }"
          variant="text"
          :icon="isSidebarCollapsed"
          @click="openProviderWorkspace"
        >
          <v-icon
            size="20"
            class="sidebar-action-icon"
            :class="{ 'mr-2': !isSidebarCollapsed }"
            >mdi-creation</v-icon
          >
          <span v-if="!isSidebarCollapsed">{{ tm("actions.providerConfig") }}</span>
        </v-btn>

        <v-btn
          class="new-chat-btn"
          :class="{ 'icon-only': isSidebarCollapsed }"
          variant="text"
          :icon="isSidebarCollapsed"
          @click="startNewChat"
        >
          <v-icon
            size="20"
            class="sidebar-action-icon"
            :class="{ 'mr-2': !isSidebarCollapsed }"
            >mdi-square-edit-outline</v-icon
          >
          <span v-if="!isSidebarCollapsed">{{ tm("actions.newChat") }}</span>
        </v-btn>

        <ProjectList
          v-if="!isSidebarCollapsed"
          :projects="projects"
          :selected-project-id="selectedProjectId"
          :transport-mode="transportMode"
          :send-shortcut="sendShortcut"
          :is-dark="isDark"
          :chatbox-mode="chatboxMode"
          :is-mobile="isMobile"
          :mobile-menu-open="mobileMenuOpen"
          :projects="projects"
          @newChat="handleNewChat"
          @selectConversation="handleSelectConversation"
          @editTitle="showEditTitleDialog"
          @deleteConversation="handleDeleteConversation"
          @batchDeleteConversations="handleBatchDeleteConversations"
          @closeMobileSidebar="closeMobileSidebar"
          @toggleTheme="toggleTheme"
          @toggleFullscreen="toggleFullscreen"
          @selectProject="handleSelectProject"
          @createProject="showCreateProjectDialog"
          @editProject="showEditProjectDialog"
          @deleteProject="handleDeleteProject"
          @updateTransportMode="setTransportMode"
          @updateSendShortcut="setSendShortcut"
        />

      <div v-if="!isSidebarCollapsed" class="session-list">
        <div
          v-for="session in sessions"
          :key="session.session_id"
          class="session-item"
          :class="{ active: !isProviderWorkspace && currSessionId === session.session_id }"
          role="button"
          tabindex="0"
          @click="selectSession(session.session_id)"
          @keydown.enter="selectSession(session.session_id)"
          @keydown.space.prevent="selectSession(session.session_id)"
        >
          <span v-if="!isSidebarCollapsed" class="session-title">{{
            sessionTitle(session)
          }}</span>
          <div class="session-actions" @click.stop>
            <v-btn
              icon="mdi-pencil-outline"
              size="x-small"
              variant="text"
              class="session-action-btn"
              :title="tm('conversation.editDisplayName')"
              @click="editSidebarSessionTitle(session)"
            />
            <v-btn
              icon="mdi-delete-outline"
              size="x-small"
              variant="text"
              class="session-action-btn"
              :title="tm('actions.deleteChat')"
              @click="deleteSidebarSession(session)"
            />
          </div>
          <v-progress-circular
            v-if="isSessionRunning(session.session_id)"
            class="session-progress"
            indeterminate
            size="16"
            width="2"
          />
        </div>

          <!-- 正常聊天界面 -->
          <template v-else>
            <div
              v-if="currentSessionProject && messages && messages.length > 0"
              class="breadcrumb-container"
            >
              <div class="breadcrumb-content">
                <span class="breadcrumb-emoji">{{
                  currentSessionProject.emoji || "📁"
                }}</span>
                <span
                  class="breadcrumb-project"
                  @click="handleSelectProject(currentSessionProject.project_id)"
                  >{{ currentSessionProject.title }}</span
                >
                <v-icon size="small" class="breadcrumb-separator">
                  mdi-chevron-right
                </v-icon>
                <span class="breadcrumb-session">{{
                  getCurrentSession?.display_name ||
                  tm("conversation.newConversation")
                }}</span>
              </div>
            </div>

            <div
              v-if="currSessionId && !selectedProjectId"
              class="message-list-wrapper"
            >
              <MessageList
                ref="messageList"
                :messages="messages"
                :is-dark="isDark"
                :is-streaming="isStreaming || isConvRunning"
                :is-loading-messages="isLoadingMessages"
                @openImagePreview="openImagePreview"
                @replyMessage="handleReplyMessage"
                @replyWithText="handleReplyWithText"
                @openRefs="handleOpenRefs"
              />
              <div class="message-list-fade" :class="{ 'fade-dark': isDark }" />
            </div>
            <ProjectView
              v-else-if="selectedProjectId"
              :project="currentProject"
              :sessions="projectSessions"
              @selectSession="
                (sessionId) => handleSelectConversation([sessionId])
              "
              @editSessionTitle="showEditTitleDialog"
              @deleteSession="handleDeleteConversation"
            >
              <ChatInput
                ref="chatInputRef"
                v-model:prompt="prompt"
                :staged-images-url="stagedImagesUrl"
                :staged-audio-url="stagedAudioUrl"
                :staged-files="stagedNonImageFiles"
                :disabled="false"
                :is-running="isStreaming || isConvRunning"
                :enable-streaming="enableStreaming"
                :is-recording="isRecording"
                :session-id="currSessionId || null"
                :current-session="getCurrentSession"
                :reply-to="replyTo"
                :send-shortcut="sendShortcut"
                @send="handleSendMessage"
                @stop="handleStopMessage"
                @toggleStreaming="toggleStreaming"
                @removeImage="removeImage"
                @removeAudio="removeAudio"
                @removeFile="removeFile"
                @startRecording="handleStartRecording"
                @stopRecording="handleStopRecording"
                @pasteImage="handlePaste"
                @fileSelect="handleFileSelect"
                @clearReply="clearReply"
                @openLiveMode="openLiveMode"
              />
            </ProjectView>
            <WelcomeView v-else :is-loading="isLoadingMessages">
              <ChatInput
                ref="chatInputRef"
                v-model:prompt="prompt"
                :staged-images-url="stagedImagesUrl"
                :staged-audio-url="stagedAudioUrl"
                :staged-files="stagedNonImageFiles"
                :disabled="false"
                :is-running="isStreaming || isConvRunning"
                :enable-streaming="enableStreaming"
                :is-recording="isRecording"
                :session-id="currSessionId || null"
                :current-session="getCurrentSession"
                :reply-to="replyTo"
                :send-shortcut="sendShortcut"
                @send="handleSendMessage"
                @stop="handleStopMessage"
                @toggleStreaming="toggleStreaming"
                @removeImage="removeImage"
                @removeAudio="removeAudio"
                @removeFile="removeFile"
                @startRecording="handleStartRecording"
                @stopRecording="handleStopRecording"
                @pasteImage="handlePaste"
                @fileSelect="handleFileSelect"
                @clearReply="clearReply"
                @openLiveMode="openLiveMode"
              />
            </WelcomeView>

            <!-- 输入区域 -->
            <ChatInput
              v-if="currSessionId && !selectedProjectId"
              ref="chatInputRef"
              v-model:prompt="prompt"
              :staged-images-url="stagedImagesUrl"
              :staged-audio-url="stagedAudioUrl"
              :staged-files="stagedNonImageFiles"
              :disabled="false"
              :is-running="isStreaming || isConvRunning"
              :enable-streaming="enableStreaming"
              :is-recording="isRecording"
              :session-id="currSessionId || null"
              :current-session="getCurrentSession"
              :reply-to="replyTo"
              :send-shortcut="sendShortcut"
              @send="handleSendMessage"
              @stop="handleStopMessage"
              @toggleStreaming="toggleStreaming"
              @removeImage="removeImage"
              @removeAudio="removeAudio"
              @removeFile="removeFile"
              @startRecording="handleStartRecording"
              @stopRecording="handleStopRecording"
              @pasteImage="handlePaste"
              @fileSelect="handleFileSelect"
              @clearReply="clearReply"
              @openLiveMode="openLiveMode"
            />
          </template>
        </div>

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
                  class="styled-menu-item"
                  rounded="md"
                >
                  <template #prepend>
                    <v-icon size="18">mdi-connection</v-icon>
                  </template>
                  <v-list-item-title>{{
                    tm("transport.title")
                  }}</v-list-item-title>
                  <template #append>
                    <span class="settings-menu-value">{{
                      currentTransportLabel
                    }}</span>
                    <v-icon size="18">mdi-chevron-right</v-icon>
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
                      <v-icon v-if="transportMode === item.value" size="18">
                        mdi-check
                      </v-icon>
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
                  class="styled-menu-item"
                  rounded="md"
                >
                  <template #prepend>
                    <v-icon size="18">mdi-translate</v-icon>
                  </template>
                  <v-list-item-title>{{
                    t("core.common.language")
                  }}</v-list-item-title>
                  <template #append>
                    <span class="settings-menu-value">{{
                      currentLanguage?.label || locale
                    }}</span>
                    <v-icon size="18">mdi-chevron-right</v-icon>
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
                      <v-icon v-if="locale === lang.value" size="18">
                        mdi-check
                      </v-icon>
                    </template>
                  </v-list-item>
                </v-list>
              </v-card>
            </v-menu>

            <v-list-item
              class="styled-menu-item"
              rounded="md"
              @click="toggleTheme"
            >
              <template #prepend>
                <v-icon size="18">{{
                  isDark ? "mdi-white-balance-sunny" : "mdi-weather-night"
                }}</v-icon>
              </template>
              <v-list-item-title>{{
                isDark ? tm("modes.lightMode") : tm("modes.darkMode")
              }}</v-list-item-title>
            </v-list-item>
          </div>
        </StyledMenu>
      </div>
    </v-card-text>
  </v-card>

    <main
      class="chat-main"
      :class="{
        'empty-chat': !isProviderWorkspace &&
          !selectedProject && !loadingMessages && !activeMessages.length,
      }"
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
            :session-id="currSessionId || null"
            :current-session="currentSession"
            :reply-to="chatInputReplyTarget"
            :send-shortcut="sendShortcut"
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

      <template v-else>
        <section
          ref="messagesContainer"
          class="messages-panel"
          @scroll="handleMessagesScroll"
        >
          {{ t("core.common.cancel") }}
        </v-btn>
        <v-btn variant="text" color="primary" @click="handleSaveTitle">
          {{ t("core.common.save") }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- 图片预览对话框 -->
  <v-dialog v-model="imagePreviewDialog" max-width="90vw" max-height="90vh">
    <v-card class="image-preview-card" elevation="8">
      <v-card-title class="d-flex justify-space-between align-center pa-4">
        <span>{{ t("core.common.imagePreview") }}</span>
        <v-btn
          icon="mdi-close"
          variant="text"
          @click="imagePreviewDialog = false"
        />
      </v-card-title>
      <v-card-text class="text-center pa-4">
        <img :src="previewImageUrl" class="preview-image-large" />
      </v-card-text>
    </v-card>
  </v-dialog>

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
            :session-id="currSessionId || null"
            :current-session="currentSession"
            :reply-to="chatInputReplyTarget"
            :send-shortcut="sendShortcut"
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
      </template>
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
      @save="saveProject"
    />
    <v-dialog v-model="sessionTitleDialogOpen" max-width="420">
      <v-card>
        <v-card-title class="text-h6">
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
  ref,
  computed,
  watch,
  onMounted,
  onBeforeUnmount,
  nextTick,
} from "vue";
import { useRoute, useRouter } from "vue-router";
import { useDisplay } from "vuetify";
import axios from "axios";
import StyledMenu from "@/components/shared/StyledMenu.vue";
import ProjectDialog, {
  type ProjectFormData,
} from "@/components/chat/ProjectDialog.vue";
import ProjectList, { type Project } from "@/components/chat/ProjectList.vue";
import ProjectView from "@/components/chat/ProjectView.vue";
import ChatInput from "@/components/chat/ChatInput.vue";
import ChatMessageList from "@/components/chat/ChatMessageList.vue";
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
import { useProjects } from "@/composables/useProjects";
import { useCustomizerStore } from "@/stores/customizer";
import ProviderChatCompletionPanel from "@/components/provider/ProviderChatCompletionPanel.vue";
import {
  useI18n,
  useLanguageSwitcher,
  useModuleI18n,
} from "@/i18n/composables";
import type { Locale } from "@/i18n/types";
import { askForConfirmation, useConfirmDialog } from "@/utils/confirmDialog";
import { useToast } from "@/utils/toast";

const props = withDefaults(defineProps<{ chatboxMode?: boolean; active?: boolean }>(), {
  chatboxMode: false,
  active: true,
});

const router = useRouter();
const route = useRoute();
const { t } = useI18n();
const { tm } = useModuleI18n("features/chat");
const { warning: toastWarning } = useToast();
const customizer = useCustomizerStore();

// UI 状态
const isMobile = ref(false);
const mobileMenuOpen = ref(false);
const imagePreviewDialog = ref(false);
const previewImageUrl = ref("");
const isLoadingMessages = ref(false);
const liveModeOpen = ref(false);

// 使用 composables
const {
  sessions,
  selectedSessions,
  currSessionId,
  pendingSessionId,
  editTitleDialog,
  editingTitle,
  editingSessionId,
  getCurrentSession,
  getSessions,
  newSession,
  deleteSession: deleteSessionFn,
  batchDeleteSessions,
  showEditTitleDialog,
  saveTitle,
  updateSessionTitle,
  newChat,
} = useSessions(props.chatboxMode);

const {
  stagedImagesUrl,
  stagedAudioUrl,
  stagedFiles,
  stagedNonImageFiles,
  getMediaFile,
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

const sidebarCollapsed = ref(false);
const activeWorkspace = ref<WorkspaceView>("chat");
const projectDialogOpen = ref(false);
const editingProject = ref<Project | null>(null);
const sessionTitleDialogOpen = ref(false);
const sessionTitleDraft = ref("");
const editingSessionTitleId = ref("");
const refreshProjectSessionsAfterTitleSave = ref(false);
const savingSessionTitle = ref(false);
const messageEditDraft = ref("");
const editingMessage = ref<ChatRecord | null>(null);
const savingMessageEdit = ref(false);
const projectSessions = ref<Session[]>([]);
const loadingSessions = ref(false);
const draft = ref("");
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
const isRecording = ref(false);
const sendShortcut = ref<"enter" | "shift_enter">("enter");
const chatSidebarDrawer = computed({
  get: () => lgAndUp.value || customizer.chatSidebarOpen,
  set: (value: boolean) => {
    if (!lgAndUp.value) {
      customizer.SET_CHAT_SIDEBAR(value);
    }
  },
});
const isSidebarCollapsed = computed(() =>
  lgAndUp.value ? sidebarCollapsed.value : !customizer.chatSidebarOpen,
);
const isProviderWorkspace = computed(
  () => activeWorkspace.value === "providers",
);
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
  projects,
  selectedProjectId,
  getProjects,
  createProject,
  updateProject,
  deleteProject,
  addSessionToProject,
  getProjectSessions,
} = useProjects();

const {
  messages,
  isStreaming,
  isConvRunning,
  enableStreaming,
  transportMode,
  currentSessionProject,
  getSessionMessages: getSessionMsg,
  sendMessage: sendMsg,
  stopMessage: stopMsg,
  toggleStreaming,
  setTransportMode,
  cleanupTransport,
} = useMessages(currSessionId, getMediaFile, updateSessionTitle, getSessions);

// 组件引用
const messageList = ref<InstanceType<typeof MessageList> | null>(null);
const chatInputRef = ref<InstanceType<typeof ChatInput> | null>(null);

// 输入状态
const prompt = ref("");

// 项目状态
const projectDialog = ref(false);
const editingProject = ref<Project | null>(null);
const projectSessions = ref<any[]>([]);
const currentProject = computed(() =>
  projects.value.find((p) => p.project_id === selectedProjectId.value),
);

// 引用消息状态
interface ReplyInfo {
  messageId: number; // PlatformSessionHistoryMessage 的 id
  selectedText?: string; // 选中的文本内容（可选）
}
const replyTo = ref<ReplyInfo | null>(null);

const isDark = computed(() => customizer.isDarkTheme);
const sendShortcut = ref<SendShortcut>("shift_enter");

provide("isDark", isDark);

onMounted(async () => {
  loadingSessions.value = true;
  try {
    await Promise.all([getSessions(), getProjects()]);
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

function focusChatInput() {
  nextTick(() => {
    chatInputRef.value?.focusInput?.();
  });
}

// 检测是否为手机端
function checkMobile() {
  isMobile.value = window.innerWidth <= 768;
  if (!isMobile.value) {
    mobileMenuOpen.value = false;
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

async function startNewChat() {
  showChatWorkspace();
  selectedProjectId.value = null;
  replyTarget.value = null;
  newChat();
  closeMobileSidebar();
}

// 同步 nav header 中的 sidebar toggle
watch(
  () => customizer.chatSidebarOpen,
  (val) => {
    if (isMobile.value) {
      mobileMenuOpen.value = val;
    }
  },
);

// 使用新的逻辑切换主题
function toggleTheme() {
  customizer.TOGGLE_DARK_MODE();
}

function toggleFullscreen() {
  if (props.chatboxMode) {
    router.push(currSessionId.value ? `/chat/${currSessionId.value}` : "/chat");
  } else {
    router.push(
      currSessionId.value ? `/chatbox/${currSessionId.value}` : "/chatbox",
    );
  }
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

async function handleSaveTitle() {
  await saveTitle();

  // 如果在项目视图中，刷新项目会话列表
  if (selectedProjectId.value) {
    const sessions = await getProjectSessions(selectedProjectId.value);
    projectSessions.value = sessions;
  }
}

function handleReplyMessage(msg: any, index: number) {
  // 从消息中获取 id (PlatformSessionHistoryMessage 的 id)
  const messageId = msg.id;
  if (!messageId) {
    console.warn("Message does not have an id");
    return;
  }

  // 获取消息内容用于显示
  let messageContent = "";
  if (typeof msg.content.message === "string") {
    messageContent = msg.content.message;
  } else if (Array.isArray(msg.content.message)) {
    // 从消息段数组中提取纯文本
    const textParts = msg.content.message
      .filter((part: any) => part.type === "plain" && part.text)
      .map((part: any) => part.text);
    messageContent = textParts.join("");
  }

  // 截断过长的内容
  if (messageContent.length > 100) {
    messageContent = messageContent.substring(0, 100) + "...";
  }

  replyTo.value = {
    messageId,
    selectedText: messageContent || "[媒体内容]",
  };
}

function clearReply() {
  replyTo.value = null;
}

function handleReplyWithText(replyData: any) {
  // 处理选中文本的引用
  const { messageId, selectedText, messageIndex } = replyData;

  if (!messageId) {
    console.warn("Message does not have an id");
    return;
  }

  replyTo.value = {
    messageId,
    selectedText: selectedText, // 保存原始的选中文本
  };
}

// Refs Sidebar 状态
const refsSidebarOpen = ref(false);
const refsSidebarRefs = ref<any>(null);

function handleOpenRefs(refs: any) {
  // 如果sidebar已打开且点击的是同一个refs，则关闭
  if (refsSidebarOpen.value && refsSidebarRefs.value === refs) {
    refsSidebarOpen.value = false;
  } else {
    // 否则打开sidebar并更新refs
    refsSidebarRefs.value = refs;
    refsSidebarOpen.value = true;
  }
}

async function handleSelectConversation(sessionIds: string[]) {
  if (!sessionIds[0]) return;

  // 退出项目视图
  selectedProjectId.value = null;
  projectSessions.value = [];

  // 立即更新选中状态，避免需要点击两次
  currSessionId.value = sessionIds[0];
  selectedSessions.value = [sessionIds[0]];

  // 更新 URL
  const basePath = props.chatboxMode ? "/chatbox" : "/chat";
  if (route.path !== `${basePath}/${sessionIds[0]}`) {
    router.push(`${basePath}/${sessionIds[0]}`);
  }

  // 手机端关闭侧边栏
  if (isMobile.value) {
    closeMobileSidebar();
  }

  // 清除引用状态
  clearReply();

  // 开始加载消息
  isLoadingMessages.value = true;

  try {
    await getSessionMsg(sessionIds[0]);
  } finally {
    isLoadingMessages.value = false;
  }

  nextTick(() => {
    messageList.value?.scrollToBottom();
  });
  focusChatInput();
}

function handleNewChat() {
  newChat(closeMobileSidebar);
  messages.value = [];
  clearReply();
  // 退出项目视图
  selectedProjectId.value = null;
  projectSessions.value = [];
  focusChatInput();
}

async function handleDeleteConversation(sessionId: string) {
  await deleteSessionFn(sessionId);
  messages.value = [];

  // 如果在项目视图中，刷新项目会话列表
  if (selectedProjectId.value) {
    const sessions = await getProjectSessions(selectedProjectId.value);
    projectSessions.value = sessions;
  }
}

async function handleBatchDeleteConversations(sessionIds: string[]) {
  try {
    const result = await batchDeleteSessions(sessionIds);

    // 仅在当前会话成功删除时清除信息
    if (result.currentSessionDeleted) {
      messages.value = [];
    }

    // 失败处理
    if (result.failed_count > 0) {
      toastWarning(
        tm("batch.partialFailure", {
          failed: result.failed_count,
          total: sessionIds.length,
        }),
      );
    }

    // 如果在项目视图中，刷新项目会话列表
    if (selectedProjectId.value) {
      const sessions = await getProjectSessions(selectedProjectId.value);
      projectSessions.value = sessions;
    }
  } catch (err) {
    console.error("Batch delete sessions failed:", err);
    toastWarning(tm("batch.requestFailed"));
  }
}

async function handleSelectProject(projectId: string) {
  selectedProjectId.value = projectId;
  const sessions = await getProjectSessions(projectId);
  projectSessions.value = sessions;
  messages.value = [];

  // 清空当前会话ID，准备在项目中创建新对话
  currSessionId.value = "";
  selectedSessions.value = [];

  // 手机端关闭侧边栏
  if (isMobile.value) {
    closeMobileSidebar();
  }
}

function showCreateProjectDialog() {
  editingProject.value = null;
  projectDialog.value = true;
}

function showEditProjectDialog(project: Project) {
  editingProject.value = project;
  projectDialog.value = true;
}

async function handleSaveProject(
  formData: ProjectFormData,
  projectId?: string,
) {
  if (projectId) {
    await updateProject(
      projectId,
      formData.title,
      formData.emoji,
      formData.description,
    );
    return;
  }

  await createProject(formData.title, formData.emoji, formData.description);
}

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
    const selection = inputRef.value?.getCurrentSelection();
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
  }
}

async function handleDeleteProject(projectId: string) {
  await deleteProject(projectId);
}

async function handleStartRecording() {
  await startRec();
}

async function handleStopRecording() {
  const audioFilename = await stopRec();
  stagedAudioUrl.value = audioFilename;
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
      const selection = inputRef.value?.getCurrentSelection();
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
    const response = await axios.post("/api/chat/thread/create", {
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
      axios.isAxiosError(error)
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
    await axios.post("/api/chat/thread/delete", {
      thread_id: thread.thread_id,
    });
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

function openLiveMode() {
  liveModeOpen.value = true;
}

function closeLiveMode() {
  liveModeOpen.value = false;
}

async function handleSendMessage() {
  // 只有引用不能发送，必须有输入内容
  if (
    !prompt.value.trim() &&
    stagedFiles.value.length === 0 &&
    !stagedAudioUrl.value
  ) {
    return;
  }

  const isCreatingNewSession = !currSessionId.value;
  const currentProjectId = selectedProjectId.value; // 保存当前项目ID

  if (isCreatingNewSession) {
    await newSession();

    // 如果在项目视图中创建新会话，立即退出项目视图
    if (currentProjectId) {
      selectedProjectId.value = null;
      projectSessions.value = [];
    }
  }

  const promptToSend = prompt.value.trim();
  const audioNameToSend = stagedAudioUrl.value;
  const filesToSend = stagedFiles.value.map((f) => ({
    attachment_id: f.attachment_id,
    url: f.url,
    original_name: f.original_name,
    type: f.type,
  }));
  const replyToSend = replyTo.value ? { ...replyTo.value } : null;

  // 清空输入和附件和引用
  prompt.value = "";
  clearStaged();
  clearReply();

  // 获取选择的提供商和模型
  const selection = chatInputRef.value?.getCurrentSelection();
  const selectedProviderId = selection?.providerId || "";
  const selectedModelName = selection?.modelName || "";

  // 点击发送后立即将消息区滚到底部，确保用户看到最新消息
  nextTick(() => {
    messageList.value?.scrollToBottom();
  });

  await sendMsg(
    promptToSend,
    filesToSend,
    audioNameToSend,
    selectedProviderId,
    selectedModelName,
    replyToSend,
  );

  // 发送流程结束后再兜底一次，处理异步渲染场景
  nextTick(() => {
    messageList.value?.scrollToBottom();
  });

  // 如果在项目中创建了新会话，将其添加到项目
  if (isCreatingNewSession && currentProjectId && currSessionId.value) {
    await addSessionToProject(currSessionId.value, currentProjectId);
    // 刷新会话列表，移除已添加到项目的会话
    await getSessions();
    // 重新获取会话消息以更新项目信息（用于面包屑显示）
    await getSessionMsg(currSessionId.value);
  }
}

async function handleStopMessage() {
  await stopMsg();
}

// 路由变化监听
watch(
  () => route.path,
  (to, from) => {
    if (
      from &&
      ((from.startsWith("/chat") && to.startsWith("/chatbox")) ||
        (from.startsWith("/chatbox") && to.startsWith("/chat")))
    ) {
      return;
    }

    if (to.startsWith("/chat/") || to.startsWith("/chatbox/")) {
      const pathSessionId = to.split("/")[2];
      if (pathSessionId && pathSessionId !== currSessionId.value) {
        if (sessions.value.length > 0) {
          const session = sessions.value.find(
            (s) => s.session_id === pathSessionId,
          );
          if (session) {
            handleSelectConversation([pathSessionId]);
          }
        } else {
          pendingSessionId.value = pathSessionId;
        }
      }
    }
  },
  { immediate: true },
);

// 会话列表加载后处理待定会话
watch(sessions, (newSessions) => {
  if (pendingSessionId.value && newSessions.length > 0) {
    const session = newSessions.find(
      (s) => s.session_id === pendingSessionId.value,
    );
    if (session) {
      selectedSessions.value = [pendingSessionId.value];
      handleSelectConversation([pendingSessionId.value]);
      pendingSessionId.value = null;
    }
  } else if (!currSessionId.value && newSessions.length > 0) {
    const firstSession = newSessions[0];
    selectedSessions.value = [firstSession.session_id];
    handleSelectConversation([firstSession.session_id]);
  }
});

onMounted(() => {
  const storedShortcut = localStorage.getItem(SEND_SHORTCUT_STORAGE_KEY);
  if (storedShortcut === "enter" || storedShortcut === "shift_enter") {
    sendShortcut.value = storedShortcut;
  }
  checkMobile();
  window.addEventListener("resize", checkMobile);
  getSessions();
  getProjects();
});

onBeforeUnmount(() => {
  window.removeEventListener("resize", checkMobile);
  cleanupMediaCache();
  cleanupTransport();
});
</script>

<style scoped>
/* 基础动画 */
@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.chat-page-card {
  width: 100%;
  height: 100%;
  max-height: 100%;
  overflow: hidden;
  overscroll-behavior: none;
}

.sidebar-provider-btn {
  margin-bottom: 8px;
}

.new-chat-btn:not(.icon-only),
.settings-btn:not(.icon-only) {
  padding-inline: 12px;
}

.new-chat-btn.icon-only,
.settings-btn.icon-only {
  width: 40px;
  height: 40px;
  min-width: 40px;
  justify-content: center;
}

.chat-sidebar.collapsed .brand-row,
.chat-sidebar.collapsed .sidebar-footer {
  display: flex;
  justify-content: center;
}

.sidebar-toggle:hover,
.new-chat-btn:hover,
.settings-btn:hover {
  background: var(--chat-session-active-bg);
}

.sidebar-workspace-btn--active {
  background: var(--chat-session-active-bg);
  color: rgb(var(--v-theme-on-surface));
}

.chevron-collapsed {
  transform: rotate(180deg);
}

.session-list {
  flex: 1;
  overflow-y: auto;
  padding: 4px 12px 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.session-item {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  position: relative;
}

.chat-main.empty-chat {
  justify-content: center;
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

.messages-panel {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 24px max(24px, calc((100% - 980px) / 2)) 18px;
}

.empty-chat .messages-panel {
  flex: 0 0 auto;
  min-height: auto;
  overflow: visible;
  padding: 0 max(24px, calc((100% - 980px) / 2)) 20px;
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

.empty-chat .welcome-state {
  height: auto;
}

.welcome-title {
  font-size: 28px;
  font-weight: 800;
}

.welcome-subtitle {
  margin-top: 8px;
  color: var(--chat-muted);
  font-size: 16px;
}

.session-project-breadcrumb {
  display: flex;
  align-items: center;
  gap: 6px;
  max-width: min(760px, 82%);
  margin-bottom: 18px;
  color: var(--chat-muted);
  font-size: 13px;
  font-weight: 500;
}

.session-project-breadcrumb span {
  min-width: 0;
  overflow: hidden;
}

.chat-layout {
  height: 100%;
  max-height: 100%;
  display: flex;
  overflow: hidden;
}

/* 手机端遮罩层 */
.mobile-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.5);
  z-index: 999;
  animation: fadeIn 0.3s ease;
}

.chat-content-panel {
  height: 100%;
  max-height: 100%;
  width: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.message-list-wrapper {
  flex: 1;
  position: relative;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.message-list-fade {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 40px;
  background: linear-gradient(
    to top,
    rgba(255, 255, 255, 1) 0%,
    rgba(255, 255, 255, 0) 100%
  );
  pointer-events: none;
  z-index: 1;
}

.message-list-fade.fade-dark {
  background: linear-gradient(
    to top,
    rgba(30, 30, 30, 1) 0%,
    rgba(30, 30, 30, 0) 100%
  );
}

.conversation-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px;
  padding-left: 16px;
  border-bottom: 1px solid var(--v-theme-border);
  width: 100%;
  padding-right: 32px;
  flex-shrink: 0;
}

.mobile-menu-btn {
  margin-right: 8px;
}

.conversation-header-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

.fullscreen-icon {
  cursor: pointer;
  margin-left: 8px;
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
  .messages-panel {
    padding: 18px 14px;
  }

  .chat-page-container {
    padding: 0 !important;
  }

  .conversation-header {
    padding: 2px;
  }
}
</style>
