<template>
  <div
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
          @create-project="openCreateProjectDialog"
          @edit-project="openEditProjectDialog"
          @delete-project="handleDeleteProject"
          @select-project="selectProject"
        />
      </div>

      <div v-if="!isSidebarCollapsed" class="session-list">
        <div
          v-for="session in sessions"
          :key="session.session_id"
          class="session-item"
          :class="{ active: currSessionId === session.session_id }"
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

        <div
          v-if="!isSidebarCollapsed && !sessions.length && !loadingSessions"
          class="empty-sessions"
        >
          {{ tm("conversation.noHistory") }}
        </div>
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
              <v-icon
                size="20"
                class="sidebar-action-icon"
                :class="{ 'mr-2': !isSidebarCollapsed }"
                >mdi-cog-outline</v-icon
              >
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
              @click="providerDialog = true"
            >
              <template #prepend>
                <v-icon size="18">mdi-robot-outline</v-icon>
              </template>
              <v-list-item-title>{{
                tm("actions.providerConfig")
              }}</v-list-item-title>
            </v-list-item>

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
    </v-navigation-drawer>

    <main
      class="chat-main"
      :class="{
        'empty-chat':
          !selectedProject && !loadingMessages && !activeMessages.length,
      }"
    >
      <ProjectView
        v-if="selectedProject"
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
          <div v-if="loadingMessages" class="center-state">
            <v-progress-circular indeterminate size="32" width="3" />
          </div>

          <div v-else-if="sessionProject" class="session-project-breadcrumb">
            <span>{{ sessionProject.title }}</span>
            <v-icon size="16">mdi-chevron-right</v-icon>
            <span>{{ currentSessionTitle }}</span>
          </div>

          <div v-else-if="!activeMessages.length" class="welcome-state">
            <div class="welcome-title">{{ tm("welcome.title") }}</div>
          </div>

          <div
            v-if="!loadingMessages && activeMessages.length"
            class="messages-list"
          >
            <div
              v-for="(msg, msgIndex) in activeMessages"
              :key="msg.id || `${msgIndex}-${msg.created_at || ''}`"
              class="message-row"
              :class="isUserMessage(msg) ? 'from-user' : 'from-bot'"
            >
              <v-avatar v-if="!isUserMessage(msg)" class="bot-avatar" size="56">
                <v-progress-circular
                  style="margin-top: -4px"
                  v-if="isMessageStreaming(msg, msgIndex)"
                  indeterminate
                  size="22"
                  width="2"
                />
                <span v-else class="bot-avatar-symbol" aria-hidden="true">
                  ✦
                </span>
              </v-avatar>

              <div class="message-stack">
                <div
                  class="message-bubble"
                  :class="{
                    user: isUserMessage(msg),
                    bot: !isUserMessage(msg),
                  }"
                >
                  <div
                    v-if="messageContent(msg).isLoading"
                    class="loading-message"
                  >
                    <span>{{ tm("message.loading") }}</span>
                  </div>

                  <template v-else>
                    <ReasoningBlock
                      v-if="messageContent(msg).reasoning"
                      :reasoning="messageContent(msg).reasoning || ''"
                      :is-dark="isDark"
                      :initial-expanded="false"
                      :is-streaming="isMessageStreaming(msg, msgIndex)"
                      :has-non-reasoning-content="hasNonReasoningContent(msg)"
                    />

                    <template
                      v-for="(part, partIndex) in messageParts(msg)"
                      :key="`${msgIndex}-${partIndex}-${part.type}`"
                    >
                      <button
                        v-if="part.type === 'reply'"
                        class="reply-quote"
                        type="button"
                        @click="scrollToMessage(part.message_id)"
                      >
                        <v-icon size="15">mdi-reply</v-icon>
                        <span>{{
                          replyPreview(part.message_id, part.selected_text)
                        }}</span>
                      </button>

                      <div
                        v-else-if="part.type === 'plain' && isUserMessage(msg)"
                        class="plain-content"
                      >
                        {{ part.text || "" }}
                      </div>

                      <MarkdownMessagePart
                        v-else-if="part.type === 'plain'"
                        :content="part.text || ''"
                        :refs="resolvedMessageRefs(msg)"
                        :is-dark="isDark"
                        :custom-html-tags="customMarkdownTags"
                      />

                      <button
                        v-else-if="part.type === 'image'"
                        class="image-part"
                        type="button"
                        @click="openImage(partUrl(part))"
                      >
                        <img
                          :src="partUrl(part)"
                          :alt="part.filename || 'image'"
                        />
                      </button>

                      <audio
                        v-else-if="part.type === 'record'"
                        class="audio-part"
                        controls
                        :src="partUrl(part)"
                      />

                      <video
                        v-else-if="part.type === 'video'"
                        class="video-part"
                        controls
                        :src="partUrl(part)"
                      />

                      <div v-else-if="part.type === 'file'" class="file-part">
                        <v-icon size="20">mdi-file-document-outline</v-icon>
                        <span>{{ part.filename || "file" }}</span>
                        <v-btn
                          icon="mdi-download"
                          size="x-small"
                          variant="text"
                          :loading="
                            downloadingFiles.has(
                              part.attachment_id || part.filename || '',
                            )
                          "
                          @click="downloadPart(part)"
                        />
                      </div>

                      <div
                        v-else-if="part.type === 'tool_call'"
                        class="tool-call-block"
                      >
                        <template
                          v-for="tool in part.tool_calls || []"
                          :key="tool.id || tool.name"
                        >
                          <ToolCallItem
                            v-if="isIPythonToolCall(tool)"
                            :is-dark="isDark"
                          >
                            <template #label>
                              <v-icon size="16">mdi-code-json</v-icon>
                              <span>{{ tool.name || "python" }}</span>
                              <span class="tool-call-inline-status">
                                {{ toolCallStatusText(tool) }}
                              </span>
                            </template>
                            <template #details>
                              <IPythonToolBlock
                                :tool-call="normalizeToolCall(tool)"
                                :is-dark="isDark"
                                :show-header="false"
                                :force-expanded="true"
                              />
                            </template>
                          </ToolCallItem>
                          <ToolCallCard
                            v-else
                            :tool-call="normalizeToolCall(tool)"
                            :is-dark="isDark"
                          />
                        </template>
                      </div>

                      <div v-else class="unknown-part">
                        {{ formatJson(part) }}
                      </div>
                    </template>
                  </template>
                </div>

                <div v-if="showMessageMeta(msg, msgIndex)" class="message-meta">
                  <span v-if="msg.created_at">{{
                    formatTime(msg.created_at)
                  }}</span>
                  <v-btn
                    v-if="!isUserMessage(msg)"
                    icon="mdi-content-copy"
                    size="x-small"
                    variant="text"
                    @click="copyMessage(msg)"
                  />
                  <v-btn
                    icon="mdi-reply-outline"
                    size="x-small"
                    variant="text"
                    @click="setReplyTarget(msg)"
                  />
                  <v-menu
                    v-if="messageContent(msg).agentStats"
                    location="bottom"
                  >
                    <template #activator="{ props: statsProps }">
                      <v-btn
                        v-bind="statsProps"
                        icon="mdi-information-outline"
                        size="x-small"
                        variant="text"
                      />
                    </template>
                    <v-card class="stats-card" elevation="4">
                      <div class="stats-row">
                        <span>{{ tm("stats.inputTokens") }}</span>
                        <strong>{{
                          inputTokens(messageContent(msg).agentStats)
                        }}</strong>
                      </div>
                      <div class="stats-row">
                        <span>{{ tm("stats.outputTokens") }}</span>
                        <strong>{{
                          outputTokens(messageContent(msg).agentStats)
                        }}</strong>
                      </div>
                      <div
                        v-if="agentTtft(messageContent(msg).agentStats)"
                        class="stats-row"
                      >
                        <span>{{ tm("stats.ttft") }}</span>
                        <strong>{{
                          agentTtft(messageContent(msg).agentStats)
                        }}</strong>
                      </div>
                      <div class="stats-row">
                        <span>{{ tm("stats.duration") }}</span>
                        <strong>{{
                          agentDuration(messageContent(msg).agentStats)
                        }}</strong>
                      </div>
                    </v-card>
                  </v-menu>
                  <div v-if="messageRefs(msg).length" class="message-meta-refs">
                    <ActionRef
                      :refs="resolvedMessageRefs(msg)"
                      @open-refs="openRefsSidebar"
                    />
                  </div>
                </div>
              </div>
            </div>
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

    <ProviderConfigDialog v-model="providerDialog" />
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
    <RefsSidebar v-model="refsSidebarOpen" :refs="selectedRefs" />

    <v-overlay
      v-model="imagePreview.visible"
      class="image-preview-overlay"
      @click="closeImage"
    >
      <img
        :src="imagePreview.url"
        class="preview-image"
        alt="preview"
        @click.stop
      />
    </v-overlay>
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
import axios from "axios";
import { setCustomComponents } from "markstream-vue";
import "markstream-vue/index.css";
import StyledMenu from "@/components/shared/StyledMenu.vue";
import ProviderConfigDialog from "@/components/chat/ProviderConfigDialog.vue";
import ProjectDialog, {
  type ProjectFormData,
} from "@/components/chat/ProjectDialog.vue";
import ProjectList, { type Project } from "@/components/chat/ProjectList.vue";
import ProjectView from "@/components/chat/ProjectView.vue";
import ChatInput from "@/components/chat/ChatInput.vue";
import ReasoningBlock from "@/components/chat/message_list_comps/ReasoningBlock.vue";
import ToolCallCard from "@/components/chat/message_list_comps/ToolCallCard.vue";
import ToolCallItem from "@/components/chat/message_list_comps/ToolCallItem.vue";
import IPythonToolBlock from "@/components/chat/message_list_comps/IPythonToolBlock.vue";
import RefsSidebar from "@/components/chat/message_list_comps/RefsSidebar.vue";
import RefNode from "@/components/chat/message_list_comps/RefNode.vue";
import ActionRef from "@/components/chat/message_list_comps/ActionRef.vue";
import MarkdownMessagePart from "@/components/chat/message_list_comps/MarkdownMessagePart.vue";
import ThemeAwareMarkdownCodeBlock from "@/components/shared/ThemeAwareMarkdownCodeBlock.vue";
import { useSessions, type Session } from "@/composables/useSessions";
import {
  useMessages,
  type ChatRecord,
  type MessagePart,
  type TransportMode,
} from "@/composables/useMessages";
import { useMediaHandling } from "@/composables/useMediaHandling";
import { useProjects } from "@/composables/useProjects";
import { useCustomizerStore } from "@/stores/customizer";
import {
  useI18n,
  useLanguageSwitcher,
  useModuleI18n,
} from "@/i18n/composables";
import type { Locale } from "@/i18n/types";
import { askForConfirmation, useConfirmDialog } from "@/utils/confirmDialog";

const props = withDefaults(defineProps<{ chatboxMode?: boolean }>(), {
  chatboxMode: false,
});

setCustomComponents("chat-message", {
  ref: RefNode,
  code_block: ThemeAwareMarkdownCodeBlock,
});

const route = useRoute();
const router = useRouter();
const { lgAndUp } = useDisplay();
const customizer = useCustomizerStore();
const { t } = useI18n();
const { tm } = useModuleI18n("features/chat");
const confirmDialog = useConfirmDialog();
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

const sidebarCollapsed = ref(false);
const providerDialog = ref(false);
const projectDialogOpen = ref(false);
const editingProject = ref<Project | null>(null);
const sessionTitleDialogOpen = ref(false);
const sessionTitleDraft = ref("");
const editingSessionTitleId = ref("");
const refreshProjectSessionsAfterTitleSave = ref(false);
const savingSessionTitle = ref(false);
const projectSessions = ref<Session[]>([]);
const loadingSessions = ref(false);
const draft = ref("");
const downloadingFiles = ref(new Set<string>());
const messagesContainer = ref<HTMLElement | null>(null);
const inputRef = ref<InstanceType<typeof ChatInput> | null>(null);
const shouldStickToBottom = ref(true);
const replyTarget = ref<ChatRecord | null>(null);
const imagePreview = reactive({ visible: false, url: "" });
const refsSidebarOpen = ref(false);
const selectedRefs = ref<Record<string, unknown> | null>(null);
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

const {
  loadingMessages,
  sending,
  loadedSessions,
  sessionProjects,
  activeMessages,
  isSessionRunning,
  isUserMessage,
  isMessageStreaming,
  messageContent,
  messageParts,
  loadSessionMessages,
  createLocalExchange,
  sendMessageStream,
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
const customMarkdownTags = ["ref"];
const currentSession = computed(
  () =>
    sessions.value.find(
      (session) => session.session_id === currSessionId.value,
    ) ||
    projectSessions.value.find(
      (session) => session.session_id === currSessionId.value,
    ) ||
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
const chatInputReplyTarget = computed(() =>
  replyTarget.value?.id == null
    ? null
    : {
        messageId: replyTarget.value.id,
        selectedText: replyPreview(replyTarget.value.id, ""),
      },
);

provide("isDark", isDark);

onMounted(async () => {
  loadingSessions.value = true;
  try {
    await Promise.all([getSessions(), getProjects()]);
    const routeSessionId = getRouteSessionId();
    if (routeSessionId) {
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
    if (routeSessionId && routeSessionId !== currSessionId.value) {
      selectedProjectId.value = null;
      await selectSession(routeSessionId, false);
    } else if (!routeSessionId && currSessionId.value) {
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

function sessionTitle(session: Session) {
  return session.display_name?.trim() || tm("conversation.newConversation");
}

async function startNewChat() {
  selectedProjectId.value = null;
  replyTarget.value = null;
  newChat();
  closeMobileSidebar();
}

function openCreateProjectDialog() {
  editingProject.value = null;
  projectDialogOpen.value = true;
}

function openEditProjectDialog(project: Project) {
  editingProject.value = project;
  projectDialogOpen.value = true;
}

async function selectProject(projectId: string) {
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
    return;
  }
  projectSessions.value = await getProjectSessions(projectId);
}

async function handleDeleteProject(projectId: string) {
  await deleteProjectById(projectId);
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
    await axios.post("/api/chat/update_session_display_name", {
      session_id: sessionId,
      display_name: displayName,
    });
    updateSessionTitle(sessionId, displayName);
    const projectSession = projectSessions.value.find(
      (session) => session.session_id === sessionId,
    );
    if (projectSession) {
      projectSession.display_name = displayName;
    }
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

async function deleteProjectSession(sessionId: string) {
  await deleteSession(sessionId);
  await loadProjectSessions();
}

async function saveProject(formData: ProjectFormData, projectId?: string) {
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
    const { botRecord } = createLocalExchange({
      sessionId,
      messageId,
      parts: outgoingParts,
    });
    updateTitleFromText(sessionId, text);

    draft.value = "";
    replyTarget.value = null;
    clearStaged();
    scrollToBottom();

    sendMessageStream({
      sessionId,
      messageId,
      parts: outgoingParts,
      transport: transportMode.value,
      enableStreaming: enableStreaming.value,
      selectedProvider: selection?.providerId || "",
      selectedModel: selection?.modelName || "",
      botRecord,
    });
  } catch (error) {
    console.error("Failed to send message:", error);
  } finally {
    sending.value = false;
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

function hasNonReasoningContent(message: ChatRecord) {
  return messageParts(message).some((part) => {
    if (part.type === "reply") return false;
    if (part.type === "plain") return Boolean(String(part.text || "").trim());
    return true;
  });
}

function updateTitleFromText(sessionId: string, text: string) {
  const session = sessions.value.find((item) => item.session_id === sessionId);
  if (!session || session.display_name || !text) return;
  updateSessionTitle(sessionId, text.slice(0, 40));
}

function partUrl(part: MessagePart) {
  if (part.embedded_url) return part.embedded_url;
  if (part.embedded_file?.url) return part.embedded_file.url;
  if (part.attachment_id)
    return `/api/chat/get_attachment?attachment_id=${encodeURIComponent(
      part.attachment_id,
    )}`;
  if (part.filename)
    return `/api/chat/get_file?filename=${encodeURIComponent(part.filename)}`;
  return "";
}

function formatJson(value: unknown) {
  if (typeof value === "string") {
    const parsed = parseJsonSafe(value);
    if (parsed !== value) return JSON.stringify(parsed, null, 2);
    return value;
  }
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value ?? "");
  }
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

function setReplyTarget(message: ChatRecord) {
  replyTarget.value = message;
  nextTick(() => inputRef.value?.focusInput?.());
}

function showMessageMeta(message: ChatRecord, msgIndex: number) {
  return (
    !messageContent(message).isLoading && !isMessageStreaming(message, msgIndex)
  );
}

function messageRefs(message: ChatRecord) {
  return resolvedMessageRefs(message).used;
}

function resolvedMessageRefs(message: ChatRecord) {
  return normalizeRefs(messageContent(message).refs);
}

function normalizeRefs(refs: unknown) {
  if (!refs) return { used: [] as Array<Record<string, unknown>> };
  const used = Array.isArray((refs as any)?.used)
    ? (refs as any).used
    : Array.isArray(refs)
    ? refs
    : [];

  return {
    used: normalizeRefItems(used),
  };
}

function normalizeRefItems(items: unknown[]) {
  return items
    .map((item: any) => ({
      index: item?.index,
      title: item?.title || item?.url || tm("refs.title"),
      url: item?.url,
      snippet: item?.snippet,
      favicon: item?.favicon,
    }))
    .filter((item) => item.url);
}

function openRefsSidebar(refs: unknown) {
  selectedRefs.value =
    refs && typeof refs === "object" ? (refs as Record<string, unknown>) : null;
  refsSidebarOpen.value = true;
}

function normalizeToolCall(tool: Record<string, unknown>) {
  const normalized = { ...tool };
  normalized.args = normalized.args ?? normalized.arguments ?? {};
  normalized.ts = normalized.ts ?? Date.now() / 1000;
  if (normalized.result && typeof normalized.result === "object") {
    normalized.result = JSON.stringify(normalized.result, null, 2);
  }
  return normalized;
}

function isIPythonToolCall(tool: Record<string, unknown>) {
  const name = String(tool.name || "").toLowerCase();
  return name.includes("python") || name.includes("ipython");
}

function toolCallStatusText(tool: Record<string, unknown>) {
  if (tool.finished_ts) return tm("toolStatus.done");
  return tm("toolStatus.running");
}

function parseJsonSafe(value: unknown) {
  if (typeof value !== "string") return value;
  try {
    return JSON.parse(value);
  } catch {
    return value;
  }
}

async function copyMessage(message: ChatRecord) {
  const text = plainTextFromMessage(message);
  if (!text) return;
  await navigator.clipboard?.writeText(text);
}

async function downloadPart(part: MessagePart) {
  const key = part.attachment_id || part.filename || "";
  if (!key) return;
  downloadingFiles.value = new Set(downloadingFiles.value).add(key);
  try {
    const response = await axios.get(partUrl(part), { responseType: "blob" });
    const url = URL.createObjectURL(response.data);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = part.filename || "file";
    anchor.click();
    URL.revokeObjectURL(url);
  } finally {
    const next = new Set(downloadingFiles.value);
    next.delete(key);
    downloadingFiles.value = next;
  }
}

function openImage(url: string) {
  imagePreview.url = url;
  imagePreview.visible = true;
}

function closeImage() {
  imagePreview.visible = false;
  imagePreview.url = "";
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

function startRecording() {
  isRecording.value = true;
}

function stopRecording() {
  isRecording.value = false;
}

function handleMessagesScroll() {
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

function formatTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function inputTokens(stats: any) {
  const usage = stats?.token_usage || {};
  return (usage.input_other || 0) + (usage.input_cached || 0);
}

function outputTokens(stats: any) {
  return stats?.token_usage?.output || 0;
}

function agentDuration(stats: any) {
  const directDuration = readPositiveNumber(stats, [
    "duration",
    "total_duration",
  ]);
  if (directDuration !== null) return formatDuration(directDuration);

  const startTime = readPositiveNumber(stats, ["start_time"]);
  const endTime = readPositiveNumber(stats, ["end_time"]);
  if (startTime === null || endTime === null || endTime < startTime) return "-";
  return formatDuration(endTime - startTime);
}

function agentTtft(stats: any) {
  const ttft = readPositiveNumber(stats, [
    "time_to_first_token",
    "ttft",
    "first_token_latency",
  ]);
  if (ttft === null) return "";
  return formatDuration(ttft);
}

function readPositiveNumber(source: any, keys: string[]) {
  for (const key of keys) {
    const value = Number(source?.[key]);
    if (Number.isFinite(value) && value > 0) return value;
  }
  return null;
}

function formatDuration(seconds: number) {
  if (seconds < 1) return `${Math.round(seconds * 1000)}ms`;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const minutes = Math.floor(seconds / 60);
  const restSeconds = Math.round(seconds % 60);
  return `${minutes}m ${restSeconds}s`;
}
</script>

<style scoped>
.chat-ui {
  --chat-sidebar-bg: #fbfbfb;
  --chat-session-active-bg: #efefef;
  --chat-page-bg: rgb(var(--v-theme-background));
  --chat-border: rgba(var(--v-border-color), 0.16);
  --chat-muted: rgba(var(--v-theme-on-surface), 0.62);
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
  --chat-border: rgba(255, 255, 255, 0.1);
}

.chat-sidebar {
  height: 100%;
  background: var(--chat-sidebar-bg);
}

.chat-sidebar.collapsed {
  background: transparent;
}

.chat-sidebar :deep(.v-navigation-drawer__content) {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.sidebar-top {
  padding: 12px;
}

.brand-row,
.composer-actions,
.message-meta,
.reply-target,
.staged-files {
  display: flex;
  align-items: center;
}

.brand-row {
  justify-content: flex-start;
  min-height: 36px;
  margin-bottom: 8px;
}

.sidebar-toggle,
.new-chat-btn,
.settings-btn {
  color: var(--chat-muted);
  border-radius: 8px;
}

.sidebar-action-icon {
  color: currentcolor;
}

.sidebar-toggle {
  width: 40px;
  height: 40px;
  min-width: 40px;
}

.new-chat-btn,
.settings-btn {
  width: 100%;
  justify-content: flex-start;
  border-radius: 8px;
  text-transform: none;
  font-weight: 500;
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
  min-height: 38px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: inherit;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
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
  flex-shrink: 0;
}

.session-actions {
  display: none;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
}

.session-item:hover .session-actions,
.session-item:focus-within .session-actions {
  display: flex;
}

.session-action-btn {
  color: var(--chat-muted);
}

.session-action-btn:hover {
  color: rgb(var(--v-theme-on-surface));
}

.empty-sessions {
  padding: 12px;
  color: var(--chat-muted);
  font-size: 13px;
}

.sidebar-footer {
  margin-top: auto;
  padding: 10px 12px 14px;
}

.settings-menu-content {
  min-width: 230px;
  padding: 6px;
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
}

.chat-main.empty-chat {
  justify-content: center;
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
  text-overflow: ellipsis;
  white-space: nowrap;
}

.messages-list {
  display: flex;
  flex-direction: column;
  gap: 22px;
}

.message-row {
  display: flex;
  gap: 10px;
  max-width: 100%;
}

.message-row.from-user {
  justify-content: flex-end;
}

.message-stack {
  max-width: min(760px, 82%);
}

.from-user .message-stack {
  align-items: flex-end;
  max-width: 60%;
}

.bot-avatar {
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
  user-select: none;
}

.message-bubble {
  border-radius: 8px;
  padding: 10px 14px;
  line-height: 1.65;
  overflow-wrap: anywhere;
}

.message-bubble.user {
  color: var(--v-theme-primaryText);
  padding: 12px 18px;
  font-size: 15px;
  max-width: 100%;
  border-radius: 1.5rem;
  background: rgba(var(--v-theme-primary), 0.12);
}

.message-bubble.bot {
  background: transparent;
  padding-left: 0;
}

.plain-content {
  white-space: pre-wrap;
}

.loading-message {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
  color: var(--chat-muted);
}

.markdown-content :deep(p) {
  margin: 0.25rem 0;
}

.markdown-content :deep(pre),
.unknown-part {
  max-width: 100%;
  overflow-x: auto;
  border-radius: 8px;
  padding: 10px;
  background: rgba(var(--v-theme-on-surface), 0.06);
  font-size: 13px;
  line-height: 1.5;
}

.reply-quote {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 6px;
  border: 0;
  border-left: 3px solid rgb(var(--v-theme-primary));
  border-radius: 6px;
  padding: 7px 9px;
  margin-bottom: 8px;
  background: rgba(var(--v-theme-primary), 0.08);
  color: inherit;
  cursor: pointer;
  text-align: left;
}

.image-part {
  display: block;
  border: 0;
  padding: 0;
  margin-top: 8px;
  background: transparent;
  cursor: zoom-in;
}

.image-part img {
  max-width: min(420px, 100%);
  max-height: 360px;
  border-radius: 8px;
  object-fit: contain;
}

.audio-part,
.video-part {
  display: block;
  max-width: 100%;
  margin-top: 8px;
}

.video-part {
  max-height: 360px;
  border-radius: 8px;
}

.file-part {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
  padding: 8px 10px;
  border: 1px solid var(--chat-border);
  border-radius: 8px;
}

.file-part span {
  min-width: 0;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tool-call-block {
  margin: 8px 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.message-bubble.bot
  > .tool-call-block:first-child
  :deep(.tool-call-card:first-child) {
  margin-top: 0;
}

.tool-call-inline-status {
  color: var(--chat-muted);
  font-size: 12px;
}

.message-meta {
  gap: 2px;
  min-height: 24px;
  color: var(--chat-muted);
  font-size: 12px;
}

.message-meta-refs {
  display: flex;
  align-items: center;
}

.from-user .message-meta {
  justify-content: flex-end;
}

.stats-card {
  min-width: 150px;
  padding: 8px 10px;
}

.stats-row {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  padding: 2px 0;
  font-size: 12px;
  line-height: 1.35;
}

.stats-row span {
  color: var(--chat-muted);
}

.stats-row strong {
  font-size: 12px;
  font-weight: 600;
}

.composer-shell {
  position: relative;
  z-index: 1;
  background: var(--chat-page-bg);
  padding: 0 0 18px;
}

.composer-shell::before {
  content: "";
  position: absolute;
  z-index: -1;
  left: 0;
  right: 0;
  top: -36px;
  height: 36px;
  pointer-events: none;
  background: linear-gradient(
    to bottom,
    rgba(var(--v-theme-background), 0),
    var(--chat-page-bg)
  );
}

.composer-shell :deep(.input-area) {
  border-top: 0;
}

.empty-chat .composer-shell {
  padding-bottom: 0;
}

.empty-chat .composer-shell::before {
  display: none;
}

.reply-target,
.staged-files {
  gap: 8px;
  margin-bottom: 8px;
}

.reply-target {
  max-width: 100%;
  border-left: 3px solid rgb(var(--v-theme-primary));
  border-radius: 6px;
  padding: 6px 8px;
  background: rgba(var(--v-theme-primary), 0.08);
}

.reply-target span {
  min-width: 0;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.staged-files {
  flex-wrap: wrap;
}

.composer {
  min-height: 96px;
  border: 1px solid var(--chat-border);
  border-radius: 8px;
  background: rgb(var(--v-theme-surface));
  box-shadow: 0 8px 30px rgba(0, 0, 0, 0.06);
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
}

.message-input {
  flex: 1;
}

.composer-actions {
  justify-content: space-between;
}

.file-input {
  display: none;
}

.composer-hint {
  margin-top: 8px;
  text-align: center;
  color: var(--chat-muted);
  font-size: 12px;
}

kbd {
  padding: 1px 5px;
  border-radius: 4px;
  background: rgba(var(--v-theme-on-surface), 0.08);
  font: inherit;
}

.image-preview-overlay {
  display: flex;
  align-items: center;
  justify-content: center;
}

.preview-image {
  max-width: min(92vw, 1200px);
  max-height: 88vh;
  border-radius: 8px;
  object-fit: contain;
}

@media (max-width: 760px) {
  .messages-panel {
    padding: 18px 14px;
  }

  .message-stack {
    max-width: 88%;
  }

  .message-row.from-bot {
    flex-direction: column;
    gap: 2px;
  }

  .message-row.from-bot .message-stack {
    max-width: 100%;
  }

  .message-row.from-bot .bot-avatar {
    display: none;
  }

  .composer-shell {
    padding: 0 0 12px;
  }
}
</style>
