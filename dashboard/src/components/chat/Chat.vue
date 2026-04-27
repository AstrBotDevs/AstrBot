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
          <span v-if="!isSidebarCollapsed">{{
            tm("actions.providerConfig")
          }}</span>
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
          :expanded-project-ids="expandedProjectIds"
          :project-sessions-by-id="projectSessionsById"
          :drag-active="draggingSessionIds.length > 0"
          @create-project="openCreateProjectDialog"
          @edit-project="openEditProjectDialog"
          @delete-project="handleDeleteProject"
          @select-project="selectProject"
          @drop-sessions="dropDraggedSessionsOnProject"
        >
          <template #project-sessions="{ project, sessions: projectSessions }">
            <div class="project-inline-sessions">
              <div
                v-for="session in projectSessions"
                :key="session.session_id"
                class="session-item project-session-sidebar-item"
                :class="{
                  active: currSessionId === session.session_id,
                  selected: isSessionSelected(session.session_id),
                  'selection-mode': isSessionSelectionMode,
                  'drop-before': isDropTarget(session.session_id, 'before'),
                  'drop-after': isDropTarget(session.session_id, 'after'),
                }"
                role="button"
                tabindex="0"
                draggable="true"
                @click="
                  handleProjectSessionItemClick(
                    session.session_id,
                    project.project_id,
                  )
                "
                @pointerdown="startSessionLongPress(session.session_id)"
                @pointerup="cancelSessionLongPress"
                @pointerleave="cancelSessionLongPress"
                @pointercancel="cancelSessionLongPress"
                @dragstart="
                  startProjectSessionDrag(
                    $event,
                    session.session_id,
                    project.project_id,
                  )
                "
                @dragend="finishSidebarSessionDrag"
                @dragover.prevent="markDropTarget($event, session.session_id)"
                @dragleave="clearDropTarget(session.session_id)"
                @drop.stop.prevent="
                  dropProjectSessionsBefore(
                    project.project_id,
                    session.session_id,
                  )
                "
                @keydown.enter="
                  handleProjectSessionItemClick(
                    session.session_id,
                    project.project_id,
                  )
                "
                @keydown.space.prevent="
                  handleProjectSessionItemClick(
                    session.session_id,
                    project.project_id,
                  )
                "
              >
                <span class="session-title">{{ sessionTitle(session) }}</span>
                <div class="session-actions" @click.stop @pointerdown.stop>
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
              </div>
              <div
                v-if="!projectSessions.length"
                class="empty-sessions expanded-project-empty"
              >
                {{ tm("project.noSessions") }}
              </div>
            </div>
          </template>
        </ProjectList>
      </div>

      <div
        v-if="!isSidebarCollapsed && isSessionSelectionMode"
        class="session-selection-floating-bar"
      >
        <span class="session-selection-count">
          {{ tm("batch.selected", { count: selectedSessions.length }) }}
        </span>
        <div class="session-selection-actions">
          <button
            class="session-selection-action danger"
            type="button"
            :disabled="!selectedSessions.length || deletingSelectedSessions"
            @click="deleteSelectedSidebarSessions"
          >
            {{ tm("batch.delete") }}
          </button>
          <button
            class="session-selection-action"
            type="button"
            @click="clearSessionSelection"
          >
            {{ t("core.common.cancel") }}
          </button>
        </div>
      </div>

      <div v-if="!isSidebarCollapsed" class="session-list">
        <div
          class="session-drop-zone"
          :class="{ 'drop-ready': sessionListDropReady }"
          @dragover.prevent="handleSessionListDragOver"
          @dragleave="handleSessionListDragLeave"
          @drop.prevent="dropDraggedProjectSessionsOut"
        >
          <div
            v-for="session in sessions"
            :key="session.session_id"
            class="session-item"
            :class="{
              active:
                !isProviderWorkspace && currSessionId === session.session_id,
              selected: isSessionSelected(session.session_id),
              'selection-mode': isSessionSelectionMode,
              'drop-before': isDropTarget(session.session_id, 'before'),
              'drop-after': isDropTarget(session.session_id, 'after'),
            }"
            role="button"
            tabindex="0"
            draggable="true"
            @click="handleSessionItemClick(session.session_id)"
            @pointerdown="startSessionLongPress(session.session_id)"
            @pointerup="cancelSessionLongPress"
            @pointerleave="cancelSessionLongPress"
            @pointercancel="cancelSessionLongPress"
            @dragstart="startSessionDrag($event, session.session_id)"
            @dragend="finishSidebarSessionDrag"
            @dragover.prevent="markDropTarget($event, session.session_id)"
            @dragleave="clearDropTarget(session.session_id)"
            @drop.stop.prevent="dropSessionsBefore(session.session_id)"
            @keydown.enter="handleSessionItemClick(session.session_id)"
            @keydown.space.prevent="handleSessionItemClick(session.session_id)"
          >
            <span v-if="!isSidebarCollapsed" class="session-title">{{
              sessionTitle(session)
            }}</span>
            <div class="session-actions" @click.stop @pointerdown.stop>
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
        </div>

        <div
          v-if="
            !isSidebarCollapsed &&
            !sessions.length &&
            !loadingSessions &&
            !expandedProjectIds.length
          "
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
          !isProviderWorkspace &&
          !selectedProject &&
          !loadingMessages &&
          !activeMessages.length,
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
        :sessions="projectSessionsFor(selectedProject.project_id)"
        @select-session="
          (sessionId) =>
            selectProjectSession(sessionId, selectedProject!.project_id)
        "
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
import { useSessionSelectionDrag } from "@/composables/useSessionSelectionDrag";
import { useCustomizerStore } from "@/stores/customizer";
import {
  configureSessionDrag,
  moveSessionIdsAfter,
  moveSessionIdsBefore,
  moveSessionIdsToEnd,
  toggleExpandedProjectIds,
} from "@/utils/sessionManagement.mjs";
import ProviderChatCompletionPanel from "@/components/provider/ProviderChatCompletionPanel.vue";
import {
  useI18n,
  useLanguageSwitcher,
  useModuleI18n,
} from "@/i18n/composables";
import type { Locale } from "@/i18n/types";
import { askForConfirmation, useConfirmDialog } from "@/utils/confirmDialog";
import { useToast } from "@/utils/toast";

const props = withDefaults(
  defineProps<{ chatboxMode?: boolean; active?: boolean }>(),
  {
    chatboxMode: false,
    active: true,
  },
);

const route = useRoute();
const router = useRouter();
const { lgAndUp } = useDisplay();
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
  batchDeleteSessions,
  reorderSessions,
  selectedSessions,
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
  removeSessionFromProject,
  getProjectSessions,
  reorderProjectSessions,
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
const projectSessionsById = reactive<Record<string, Session[]>>({});
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
const deletingSelectedSessions = ref(false);
const refsSidebarOpen = ref(false);
const expandedProjectIds = ref<string[]>([]);
const selectedProjectSessionSourceId = ref<string | null>(null);
const dropTargetSessionId = ref<string | null>(null);
const dropTargetPosition = ref<"before" | "after">("before");
const {
  draggingSessionIds,
  draggingSourceProjectId,
  sessionListDropReady,
  isSessionSelectionMode,
  isSessionSelected,
  clearSessionSelection,
  toggleSidebarSessionSelection,
  startSessionLongPress,
  cancelSessionLongPress,
  consumeSuppressedSessionClick,
  startSessionDragState,
  startProjectSessionDragState,
  finishSessionDrag,
} = useSessionSelectionDrag(selectedSessions);
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
    Object.values(projectSessionsById)
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
  cancelSessionLongPress();
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

async function startNewChat() {
  showChatWorkspace();
  selectedProjectId.value = null;
  clearSessionSelection();
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
  showChatWorkspace();
  expandedProjectIds.value = toggleExpandedProjectIds(
    expandedProjectIds.value,
    projectId,
  );
  selectedProjectId.value = expandedProjectIds.value.includes(projectId)
    ? projectId
    : null;
  currSessionId.value = "";
  replyTarget.value = null;
  await router.push(basePath());
  if (expandedProjectIds.value.includes(projectId)) {
    await loadProjectSessions(projectId);
  } else {
    delete projectSessionsById[projectId];
  }
  closeMobileSidebar();
}

async function loadProjectSessions(projectId = selectedProjectId.value) {
  if (!projectId) return;
  projectSessionsById[projectId] = await getProjectSessions(projectId);
}

function projectSessionsFor(projectId: string) {
  return projectSessionsById[projectId] || [];
}

function removeSessionsFromProjectCache(
  projectId: string,
  sessionIds: string[],
) {
  const existingSessions = projectSessionsById[projectId];
  if (!existingSessions) return;
  const movedSessionIds = new Set(sessionIds);
  projectSessionsById[projectId] = existingSessions.filter(
    (session) => !movedSessionIds.has(session.session_id),
  );
}

function removeSessionsFromUnassignedCache(sessionIds: string[]) {
  const movedSessionIds = new Set(sessionIds);
  sessions.value = sessions.value.filter(
    (session) => !movedSessionIds.has(session.session_id),
  );
}

async function loadExpandedProjectSessions() {
  await Promise.all(
    expandedProjectIds.value.map((id) => loadProjectSessions(id)),
  );
}

async function handleDeleteProject(projectId: string) {
  await deleteProjectById(projectId);
  if (selectedProjectId.value === projectId) {
    selectedProjectId.value = null;
  }
  expandedProjectIds.value = expandedProjectIds.value.filter(
    (id) => id !== projectId,
  );
  delete projectSessionsById[projectId];
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
    for (const projectSessions of Object.values(projectSessionsById)) {
      const projectSession = projectSessions.find(
        (session) => session.session_id === sessionId,
      );
      if (projectSession) {
        projectSession.display_name = displayName;
      }
    }
    if (refreshProjectSessionsAfterTitleSave.value) {
      await loadExpandedProjectSessions();
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

function handleSessionItemClick(sessionId: string) {
  cancelSessionLongPress();
  if (consumeSuppressedSessionClick()) return;

  if (isSessionSelectionMode.value) {
    toggleSidebarSessionSelection(sessionId);
    return;
  }
  selectSession(sessionId);
}

function handleProjectSessionItemClick(
  sessionId: string,
  sourceProjectId: string,
) {
  selectedProjectSessionSourceId.value = sourceProjectId;
  cancelSessionLongPress();
  if (consumeSuppressedSessionClick()) return;

  if (isSessionSelectionMode.value) {
    toggleSidebarSessionSelection(sessionId);
    return;
  }
  selectProjectSession(sessionId, sourceProjectId);
}

function isDropTarget(sessionId: string, position: "before" | "after") {
  return (
    dropTargetSessionId.value === sessionId &&
    dropTargetPosition.value === position
  );
}

function markDropTarget(event: DragEvent, sessionId: string) {
  if (
    !draggingSessionIds.value.length ||
    draggingSessionIds.value.includes(sessionId)
  ) {
    return;
  }
  const target = event.currentTarget as HTMLElement | null;
  if (target) {
    const rect = target.getBoundingClientRect();
    dropTargetPosition.value =
      event.clientY > rect.top + rect.height / 2 ? "after" : "before";
  }
  dropTargetSessionId.value = sessionId;
}

function clearDropTarget(sessionId?: string) {
  if (!sessionId || dropTargetSessionId.value === sessionId) {
    dropTargetSessionId.value = null;
  }
}

function startSessionDrag(event: DragEvent, sessionId: string) {
  const sessionIds = startSessionDragState(sessionId);
  configureSessionDrag(event, sessionIds);
}

async function dropDraggedSessionsOnProject(projectId: string) {
  const sessionIds = [...draggingSessionIds.value];
  const sourceProjectId = draggingSourceProjectId.value;
  if (!sessionIds.length) return;
  if (sourceProjectId === projectId) {
    clearDropTarget();
    finishSessionDrag();
    return;
  }
  try {
    const results = await Promise.all(
      sessionIds.map((sessionId) => addSessionToProject(sessionId, projectId)),
    );
    const movedCount = results.filter(Boolean).length;
    if (movedCount > 0) {
      if (sourceProjectId) {
        removeSessionsFromProjectCache(sourceProjectId, sessionIds);
      } else {
        removeSessionsFromUnassignedCache(sessionIds);
      }
      await getSessions();
      await loadProjectSessions(projectId);
      if (sourceProjectId && sourceProjectId !== projectId) {
        await loadProjectSessions(sourceProjectId);
      }
      clearSessionSelection();
    }
  } finally {
    clearDropTarget();
    finishSessionDrag();
  }
}

async function dropSessionsBefore(targetSessionId: string) {
  const sessionIds = [...draggingSessionIds.value];
  const sourceProjectId = draggingSourceProjectId.value;
  if (!sessionIds.length) return;
  const movedSessionIds = new Set(sessionIds);
  const movedSessions = sourceProjectId
    ? projectSessionsFor(sourceProjectId).filter((session) =>
        movedSessionIds.has(session.session_id),
      )
    : sessions.value.filter((session) =>
        movedSessionIds.has(session.session_id),
      );

  if (sourceProjectId) {
    const results = await Promise.all(
      sessionIds.map((sessionId) => removeSessionFromProject(sessionId)),
    );
    if (!results.some(Boolean)) {
      clearDropTarget();
      finishSessionDrag();
      return;
    }
    removeSessionsFromProjectCache(sourceProjectId, sessionIds);
    await loadProjectSessions(sourceProjectId);
  }

  const currentSessionIds = sessions.value.map((session) => session.session_id);
  const nextSessionIds =
    dropTargetPosition.value === "after"
      ? moveSessionIdsAfter(currentSessionIds, sessionIds, targetSessionId)
      : moveSessionIdsBefore(currentSessionIds, sessionIds, targetSessionId);

  const currentSessionsById = new Map(
    sessions.value.map((session) => [session.session_id, session]),
  );
  for (const session of movedSessions) {
    currentSessionsById.set(session.session_id, session);
  }
  sessions.value = nextSessionIds
    .map((sessionId: string) => currentSessionsById.get(sessionId))
    .filter((session: Session | undefined): session is Session =>
      Boolean(session),
    );

  try {
    if (!(await reorderSessions(nextSessionIds))) {
      await getSessions();
    }
    clearSessionSelection();
  } finally {
    clearDropTarget();
    finishSessionDrag();
  }
}

async function dropProjectSessionsBefore(
  projectId: string,
  targetSessionId: string,
) {
  const sessionIds = [...draggingSessionIds.value];
  const sourceProjectId = draggingSourceProjectId.value;
  if (!sessionIds.length) return;
  const movedSessionIds = new Set(sessionIds);
  const movedSessions = sourceProjectId
    ? projectSessionsFor(sourceProjectId).filter((session) =>
        movedSessionIds.has(session.session_id),
      )
    : sessions.value.filter((session) =>
        movedSessionIds.has(session.session_id),
      );

  if (sourceProjectId !== projectId) {
    const results = await Promise.all(
      sessionIds.map((sessionId) => addSessionToProject(sessionId, projectId)),
    );
    if (!results.some(Boolean)) {
      clearDropTarget();
      finishSessionDrag();
      return;
    }
    if (sourceProjectId) {
      removeSessionsFromProjectCache(sourceProjectId, sessionIds);
      await loadProjectSessions(sourceProjectId);
    } else {
      removeSessionsFromUnassignedCache(sessionIds);
      await getSessions();
    }
  }

  const currentSessionIds = projectSessionsFor(projectId).map(
    (session) => session.session_id,
  );
  const nextSessionIds =
    dropTargetPosition.value === "after"
      ? moveSessionIdsAfter(currentSessionIds, sessionIds, targetSessionId)
      : moveSessionIdsBefore(currentSessionIds, sessionIds, targetSessionId);
  if (nextSessionIds.join("\0") === currentSessionIds.join("\0")) {
    clearDropTarget();
    finishSessionDrag();
    return;
  }

  const currentSessionsById = new Map(
    projectSessionsFor(projectId).map((session) => [
      session.session_id,
      session,
    ]),
  );
  for (const session of movedSessions) {
    currentSessionsById.set(session.session_id, session);
  }
  projectSessionsById[projectId] = nextSessionIds
    .map((sessionId: string) => currentSessionsById.get(sessionId))
    .filter((session: Session | undefined): session is Session =>
      Boolean(session),
    );

  try {
    if (!(await reorderProjectSessions(projectId, nextSessionIds))) {
      await loadProjectSessions(projectId);
    }
  } finally {
    clearDropTarget();
    finishSessionDrag();
  }
}

function startProjectSessionDrag(
  event: DragEvent,
  sessionId: string,
  sourceProjectId: string,
) {
  const payload = startProjectSessionDragState(sessionId, sourceProjectId);
  configureSessionDrag(event, payload.sessionIds);
}

function finishSidebarSessionDrag() {
  clearDropTarget();
  finishSessionDrag();
}

function handleSessionListDragOver() {
  if (draggingSourceProjectId.value) {
    sessionListDropReady.value = true;
  }
}

function handleSessionListDragLeave() {
  sessionListDropReady.value = false;
}

async function dropDraggedProjectSessionsOut() {
  const sessionIds = [...draggingSessionIds.value];
  const sourceProjectId = draggingSourceProjectId.value;
  if (!sourceProjectId || !sessionIds.length) return;
  const movedSessionIds = new Set(sessionIds);
  const movedSessions = projectSessionsFor(sourceProjectId).filter((session) =>
    movedSessionIds.has(session.session_id),
  );
  try {
    const results = await Promise.all(
      sessionIds.map((sessionId) => removeSessionFromProject(sessionId)),
    );
    if (results.some(Boolean)) {
      removeSessionsFromProjectCache(sourceProjectId, sessionIds);
      const currentSessionIds = sessions.value.map(
        (session) => session.session_id,
      );
      const nextSessionIds = moveSessionIdsToEnd(currentSessionIds, sessionIds);
      const currentSessionsById = new Map(
        sessions.value.map((session) => [session.session_id, session]),
      );
      for (const session of movedSessions) {
        currentSessionsById.set(session.session_id, session);
      }
      sessions.value = nextSessionIds
        .map((sessionId: string) => currentSessionsById.get(sessionId))
        .filter((session: Session | undefined): session is Session =>
          Boolean(session),
        );
      await reorderSessions(nextSessionIds);
      for (const sessionId of sessionIds) {
        sessionProjects[sessionId] = null;
      }
      await loadProjectSessions(sourceProjectId);
    }
  } finally {
    clearDropTarget();
    finishSessionDrag();
  }
}

async function deleteSelectedSidebarSessions() {
  if (!selectedSessions.value.length || deletingSelectedSessions.value) return;
  const count = selectedSessions.value.length;
  const message = tm("batch.confirmDelete", { count });
  if (!(await askForConfirmation(message, confirmDialog))) return;

  deletingSelectedSessions.value = true;
  try {
    const result = await batchDeleteSessions([...selectedSessions.value]);
    clearSessionSelection();
    if (result.currentSessionDeleted) {
      selectedProjectId.value = null;
      await router.push(basePath());
    }
    if (result.failed_count > 0) {
      toast.error(
        tm("batch.partialFailure", {
          failed: result.failed_count,
          total: count,
        }),
      );
    }
  } finally {
    deletingSelectedSessions.value = false;
  }
}

async function selectProjectSession(
  sessionId: string,
  sourceProjectId?: string,
) {
  if (sourceProjectId) {
    selectedProjectSessionSourceId.value = sourceProjectId;
  }
  selectedProjectId.value = null;
  await selectSession(sessionId);
}

async function editProjectSessionTitle(sessionId: string, title: string) {
  openSessionTitleDialog(sessionId, title, true);
}

async function deleteProjectSession(sessionId: string) {
  await deleteSession(sessionId);
  await loadProjectSessions(selectedProjectSessionSourceId.value || undefined);
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
  if (!session || session.display_name || !text) return;
  updateSessionTitle(sessionId, text.slice(0, 40));
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
  if (!currSessionId.value || !message?.id || !threadSelection.selectedText)
    return;
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
  if (!(await askForConfirmation(tm("thread.confirmDelete"), confirmDialog)))
    return;
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
  --chat-sidebar-bg: #fbfbfb;
  --chat-session-active-bg: #efefef;
  --chat-session-current-bg: rgba(var(--v-theme-on-surface), 0.08);
  --chat-session-selected-bg: rgba(80, 150, 230, 0.16);
  --chat-session-selected-bg-hover: rgba(80, 150, 230, 0.22);
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
  --chat-session-current-bg: rgba(255, 255, 255, 0.12);
  --chat-session-selected-bg: rgba(96, 165, 250, 0.18);
  --chat-session-selected-bg-hover: rgba(96, 165, 250, 0.24);
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
  position: relative;
}

.sidebar-top {
  padding: 12px;
}

.brand-row {
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

.session-selection-floating-bar {
  position: absolute;
  z-index: 3;
  left: 12px;
  right: 12px;
  bottom: 74px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-height: 44px;
  padding: 8px 12px;
  border: 1px solid rgba(80, 150, 230, 0.22);
  border-radius: 14px;
  background: color-mix(in srgb, var(--chat-sidebar-bg) 86%, #ffffff 14%);
  box-shadow: 0 12px 36px rgba(0, 0, 0, 0.12);
  backdrop-filter: blur(14px);
}

.session-selection-count {
  color: rgb(var(--v-theme-on-surface));
  font-size: 16px;
  font-weight: 700;
  line-height: 22px;
}

.session-selection-actions {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.session-selection-action {
  min-height: 32px;
  border: 0;
  border-radius: 999px;
  background: transparent;
  color: var(--chat-muted);
  padding: 0 10px;
  cursor: pointer;
  font: inherit;
  font-size: 16px;
  font-weight: 700;
  line-height: 22px;
}

.session-selection-action:hover:not(:disabled) {
  background: rgba(var(--v-theme-on-surface), 0.08);
  color: rgb(var(--v-theme-on-surface));
}

.session-selection-action.danger {
  color: rgb(var(--v-theme-error));
}

.session-selection-action:disabled {
  cursor: default;
  opacity: 0.5;
}

.session-drop-zone {
  display: flex;
  flex-direction: column;
  flex: 1;
  gap: 8px;
  border-radius: 12px;
  transition:
    background-color 0.18s ease,
    box-shadow 0.18s ease;
}

.session-drop-zone.drop-ready {
  background: rgba(80, 150, 230, 0.1);
  box-shadow: inset 0 0 0 1px rgba(80, 150, 230, 0.22);
}

.project-inline-sessions {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 2px 0 6px 28px;
}

.project-session-sidebar-item {
  height: 36px;
  padding: 8px 10px;
  border-radius: 8px;
}

.expanded-project-empty {
  padding: 8px 4px 2px;
}

.session-item {
  width: 100%;
  height: 38px;
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
  position: relative;
  transition:
    background-color 0.16s ease,
    transform 0.16s ease,
    box-shadow 0.16s ease,
    margin-top 0.16s ease;
}

.session-item.drop-before {
  margin-top: 12px;
}

.session-item.drop-after {
  margin-bottom: 12px;
}

.session-item.drop-before {
  transform: translateY(2px);
}

.session-item.drop-after {
  transform: translateY(-2px);
}

.session-item.drop-before::before,
.session-item.drop-after::after {
  content: "";
  position: absolute;
  left: 10px;
  right: 10px;
  height: 3px;
  border-radius: 999px;
  background: rgba(80, 150, 230, 0.72);
  box-shadow: 0 0 0 4px rgba(80, 150, 230, 0.12);
}

.session-item.drop-before::before {
  top: -8px;
}

.session-item.drop-after::after {
  bottom: -8px;
}

.session-item:hover,
.session-item.active {
  background: var(--chat-session-active-bg);
}

.session-item.active {
  background: var(--chat-session-current-bg);
}

.session-item.active .session-title {
  font-weight: 600;
}

.session-item.selected {
  background: var(--chat-session-selected-bg);
}

.session-item.selected:hover {
  background: var(--chat-session-selected-bg-hover);
}

.session-item.selection-mode:not(.selected) {
  opacity: 0.82;
}

.session-title {
  min-width: 0;
  flex: 1;
  align-self: center;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 14px;
  font-weight: 500;
  line-height: 20px;
}

.session-progress {
  flex-shrink: 0;
}

.session-actions {
  display: flex;
  align-items: center;
  gap: 2px;
  width: 56px;
  flex-shrink: 0;
  justify-content: flex-end;
  opacity: 0;
  visibility: hidden;
  transition:
    opacity 0.14s ease,
    visibility 0.14s ease;
}

.session-item:hover .session-actions,
.session-item:focus-within .session-actions {
  opacity: 1;
  visibility: visible;
}

.session-item.selection-mode .session-actions,
.session-item.selection-mode:hover .session-actions,
.session-item.selection-mode:focus-within .session-actions {
  opacity: 0;
  visibility: hidden;
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
  text-overflow: ellipsis;
  white-space: nowrap;
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
  border-top-width: 0.3px;
}

:deep(.paragraph-node) {
  margin: 0.5rem 0;
  line-height: 1.7;
}

:deep(.list-node) {
  margin-top: 0.5rem;
  margin-bottom: 0.5rem;
}

@media (max-width: 760px) {
  .messages-panel {
    padding: 18px 14px;
  }

  .composer-shell,
  .project-composer-shell {
    padding: 0;
  }
}
</style>
