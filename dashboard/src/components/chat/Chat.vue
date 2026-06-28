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
            @send-command="sendSystemCommand"
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
            @open-diff-sidebar="openGitDiffSidebar"
          />
        </section>
      </ProjectView>

      <template v-else>
        <section
          ref="messagesContainer"
          class="messages-panel"
          @scroll="handleMessagesScroll"
        >
          <!-- 可拖动的 todo summary 浮窗:
               初始位置: 页面顶部正中;
               拖动范围: 不得超出 .chat-main 边界,不得进入 .composer-shell 区域;
               位置持久化: localStorage。
               键盘 a11y: tabindex=0 让 button 可被 Tab 聚焦;Enter/Space 自动触发 click
               (浏览器对 <button> 的默认行为,会调用 onTodoBarClick → toggleTodoSidebar);
               方向键移动位置 (8px/次),复用 clampBarPos + 同一个 localStorage key。-->
          <transition name="todo-bar-fade">
            <button
              v-if="currentTodoSnapshot"
              type="button"
              class="todo-summary-bar"
              :class="{
                'todo-summary-bar--active': todoSidebarOpen,
                'todo-summary-bar--dragging': isDraggingTodoBar,
                'todo-summary-bar--centered': todoBarPos === null,
              }"
              :style="todoBarStyle"
              tabindex="0"
              :aria-label="tm('todo.summary')"
              :aria-keyshortcuts="todoBarKeyShortcuts"
              @mousedown="startDragTodoBar"
              @click="onTodoBarClick"
              @keydown="onTodoBarKeydown"
            >
              <v-icon size="16" class="todo-summary-icon">mdi-format-list-checks</v-icon>
              <v-icon size="14" class="todo-summary-drag-handle">mdi-drag-horizontal-variant</v-icon>
              <span class="todo-summary-text">
                {{ currentTodoSnapshot.stats?.done || 0 }}/{{ currentTodoSnapshot.stats?.effective_total || 0 }}
                <template v-if="currentTodoSnapshot.stats?.in_progress">
                  · <span class="todo-summary-progress">{{ currentTodoSnapshot.stats.in_progress }} in progress</span>
                </template>
              </span>
              <v-progress-circular
                v-if="currentTodoSnapshot.stats?.progress_pct > 0 && currentTodoSnapshot.stats?.progress_pct < 100"
                :model-value="currentTodoSnapshot.stats.progress_pct"
                :size="16"
                :width="2"
                class="todo-summary-circular"
              >
                {{ currentTodoSnapshot.stats.progress_pct }}%
              </v-progress-circular>
              <v-icon
                v-if="currentTodoSnapshot.attentionItems?.length"
                size="10"
                color="warning"
                class="todo-summary-attention"
                :title="tm('todo.attentionHint', { count: currentTodoSnapshot.attentionItems.length })"
              >mdi-circle-medium</v-icon>
            </button>
          </transition>

          <!-- 项目 breadcrumb (非 sticky,普通文档流定位在顶部) -->
          <div
            v-if="sessionProject"
            class="session-project-breadcrumb"
          >
            <span>{{ sessionProject.title }}</span>
            <v-icon size="16">mdi-chevron-right</v-icon>
            <span>{{ currentSessionTitle }}</span>
          </div>

          <!-- 加载中 / 消息流 / 欢迎区 主体内容 -->
          <div
            v-if="loadingMessages"
            class="center-state"
          >
            <v-progress-circular indeterminate size="32" width="3" />
          </div>

          <div
            v-else-if="activeMessages.length"
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
              @submit-choice="onInteractiveChoiceSubmit"
            />
          </div>

          <!-- 空消息时的欢迎区 (非 sticky,自然居中) -->
          <div
            v-else-if="!loadingMessages"
            class="welcome-state"
          >
            <div class="welcome-title">{{ tm("welcome.title") }}</div>
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
            @send-command="sendSystemCommand"
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
            @open-diff-sidebar="openGitDiffSidebar"
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
    <RefsSidebar v-model="refsSidebarOpen" :refs="selectedRefs" @update:model-value="onRefsToggle" />
    <TodoSidebar
      v-model="todoSidebarOpen"
      :list="currentTodoSnapshot?.list"
      :stats="currentTodoSnapshot?.stats"
      :attention-items="currentTodoSnapshot?.attentionItems || []"
    />
    <GitDiffSidebar
      v-model="gitDiffSidebarOpen"
      :is-dark="isDark"
    />
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
import { chatApi } from "@/api/v1";
import { useSpcodeProjectStatus } from "@/composables/useSpcodeProjectStatus";
import { useSpcodeCodegraphStatus } from "@/composables/useSpcodeCodegraphStatus";
import { useSpcodePlanMode } from "@/composables/useSpcodePlanMode";
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
import TodoSidebar from "@/components/chat/message_list_comps/TodoSidebar.vue";
import GitDiffSidebar from "@/components/chat/GitDiffSidebar.vue";
import { useSessions, type Session } from "@/composables/useSessions";
import { useFileComments } from "@/composables/useFileComments";
import { buildWebchatUmoDetails } from "@/utils/chatConfigBinding";
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

const route = useRoute();
const router = useRouter();
const { lgAndUp } = useDisplay();
const customizer = useCustomizerStore();
const { t } = useI18n();
const { tm } = useModuleI18n("features/chat");

// Spcode project state is shared via a module-level ref in the
// composable; just grab a handle so the chat-stream watcher below can
// apply updates and so the refresh-on-session-change handler can call
// the plugin's HTTP API.
const spcodeStatus = useSpcodeProjectStatus();
const codegraphStatus = useSpcodeCodegraphStatus();
// Plan/build mode singleton. Mirrors the spcodeStatus lifecycle so
// both chips stay in sync across session switches and stream-ends.
const spcodePlanMode = useSpcodePlanMode();
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
const commandSending = ref(false);
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
const todoSidebarOpen = ref(false);
const gitDiffSidebarOpen = ref(false);

/* ── todo summary bar 拖动 ───────────────────────────
 * 浮窗可拖动,位置持久化到 localStorage。
 * 边界:不得超出 .chat-main 矩形,不得进入 .composer-shell 区域(按 max 高度算)。
 */
type BarPos = { left: number; top: number };
const TODO_BAR_POS_KEY = "chatui.todoBarPos.v1";
const todoBarPos = ref<BarPos | null>(null);
const isDraggingTodoBar = ref(false);
let dragState: {
  mouseStartX: number;
  mouseStartY: number;
  barStartLeft: number;
  barStartTop: number;
  didMove: boolean;
} | null = null;
let suppressNextClick = false;

/** 把 (left, top) 限制在 chat-main 内, 不与 composer-shell 重叠。 */
function clampBarPos(
  desiredLeft: number,
  desiredTop: number,
  barRect: DOMRect,
  mainRect: DOMRect,
): BarPos {
  // 边界: 不得超出 main 矩形
  const minLeft = mainRect.left;
  const maxLeft = Math.max(minLeft, mainRect.right - barRect.width);
  const minTop = mainRect.top;
  // 输入框区域: chat-main 内 .composer-shell 的顶部。
  // composer 在多行内容时会增高, 这里直接以"main 底部减 bar 高度"作为最底,
  // 避免压到任何状态下的输入框 (单行/多行均不会越界)。
  const composer = document.querySelector(
    ".chat-main .composer-shell",
  ) as HTMLElement | null;
  let maxTop: number;
  if (composer) {
    const composerRect = composer.getBoundingClientRect();
    // composer 区域可能因为多行内容上下扩张, 取其 top 减 bar 高度
    maxTop = composerRect.top - barRect.height - 4;
  } else {
    maxTop = mainRect.bottom - barRect.height;
  }
  maxTop = Math.max(minTop, maxTop);

  return {
    left: Math.max(minLeft, Math.min(desiredLeft, maxLeft)),
    top: Math.max(minTop, Math.min(desiredTop, maxTop)),
  };
}

/** 根据当前 chat-main 容器 + 元素本身尺寸,初始化居中位置。
 *  仅在 todoBarPos === null 时调用(首次出现 / 持久化位置超出边界时回退)。
 */
function initTodoBarPos() {
  nextTick(() => {
    const bar = document.querySelector(".todo-summary-bar") as HTMLElement | null;
    const main = document.querySelector(".chat-main") as HTMLElement | null;
    if (!bar || !main) return;
    const mainRect = main.getBoundingClientRect();
    const barRect = bar.getBoundingClientRect();
    const desiredLeft = mainRect.left + Math.max(16, (mainRect.width - barRect.width) / 2);
    const desiredTop = mainRect.top + 16;
    todoBarPos.value = clampBarPos(desiredLeft, desiredTop, barRect, mainRect);
  });
}

/** 计算最终应用的 inline style: 初始居中 / 拖动后 absolute。 */
const todoBarStyle = computed(() => {
  if (todoBarPos.value === null) {
    return {}; // 由 CSS .todo-summary-bar--centered 居中
  }
  return {
    left: `${todoBarPos.value.left}px`,
    top: `${todoBarPos.value.top}px`,
  };
});

function startDragTodoBar(e: MouseEvent) {
  if (!todoBarPos.value) {
    // 第一次出现: 同步初始化位置,然后进入拖动
    initTodoBarPos();
    // 等下一帧位置就绪后再开始 drag,否则 mouseStart 基准是错的
    nextTick(() => {
      if (todoBarPos.value) actuallyStartDrag(e);
    });
    return;
  }
  actuallyStartDrag(e);
}

function actuallyStartDrag(e: MouseEvent) {
  if (!todoBarPos.value) return;
  isDraggingTodoBar.value = true;
  dragState = {
    mouseStartX: e.clientX,
    mouseStartY: e.clientY,
    barStartLeft: todoBarPos.value.left,
    barStartTop: todoBarPos.value.top,
    didMove: false,
  };
  document.addEventListener("mousemove", onDragTodoBarMove);
  document.addEventListener("mouseup", endDragTodoBar);
  // 阻止默认文本选择
  e.preventDefault();
}

function onDragTodoBarMove(e: MouseEvent) {
  if (!dragState || !todoBarPos.value) return;
  const deltaX = e.clientX - dragState.mouseStartX;
  const deltaY = e.clientY - dragState.mouseStartY;
  // 超过阈值才算"拖动",否则视为准备 click
  if (!dragState.didMove && (Math.abs(deltaX) > 3 || Math.abs(deltaY) > 3)) {
    dragState.didMove = true;
    suppressNextClick = true; // 一旦真拖动, 屏蔽紧随其后的 click
  }
  if (!dragState.didMove) return;

  const bar = document.querySelector(".todo-summary-bar") as HTMLElement | null;
  const main = document.querySelector(".chat-main") as HTMLElement | null;
  if (!bar || !main) return;
  const mainRect = main.getBoundingClientRect();
  const barRect = bar.getBoundingClientRect();
  const desiredLeft = dragState.barStartLeft + deltaX;
  const desiredTop = dragState.barStartTop + deltaY;
  todoBarPos.value = clampBarPos(desiredLeft, desiredTop, barRect, mainRect);
}

function endDragTodoBar() {
  isDraggingTodoBar.value = false;
  if (dragState?.didMove && todoBarPos.value) {
    // 持久化拖动后的位置
    try {
      localStorage.setItem(
        TODO_BAR_POS_KEY,
        JSON.stringify(todoBarPos.value),
      );
    } catch {
      /* 忽略 localStorage 写入失败 (隐私模式等) */
    }
  }
  dragState = null;
  document.removeEventListener("mousemove", onDragTodoBarMove);
  document.removeEventListener("mouseup", endDragTodoBar);
}

/** 区分 click 和 drag 结束: 仅当未发生实际拖动时触发 toggle。 */
function onTodoBarClick(e: MouseEvent) {
  if (suppressNextClick) {
    e.preventDefault();
    e.stopPropagation();
    suppressNextClick = false;
    return;
  }
  toggleTodoSidebar();
}

// localStorage 恢复已禁用: 每次居中,避免缓存污染。
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
  latestTodoSnapshotBySession,
} = useMessages({
  currentSessionId: currSessionId,
  onSessionsChanged: getSessions,
  onStreamUpdate: (sessionId) => {
    if (sessionId === currSessionId.value && shouldStickToBottom.value) {
      scrollToBottom();
    }
  },
  // Refresh the spcode "currently loaded project" chip every time a
  // bot response finishes, so commands like `/project load <dir>` or
  // `/project unload` show their effect on the chip immediately
  // without forcing the user to refresh the page.
  //
  // The previous design parsed bot text for hidden JSON markers or
  // plain-text patterns; that was abandoned because some markdown
  // renderers leaked the marker into the chat. We now let the bot
  // respond with pure prose and re-fetch the authoritative state from
  // the plugin's HTTP endpoint after every response.
  //
  // Filtered to the active session: if the user navigates away while
  // a stream is in flight, the new session's state is already covered
  // by the `currSessionId` watcher above.
  onStreamEnd: (sessionId) => {
    if (sessionId === currSessionId.value) {
      // Bug fix (2026-06-23, elecvoid243): spcodeStatus.refresh()
      // must receive the full umo (not be called bare). Without it,
      // backend's fallback branch returns the most-recently-loaded
      // project across ALL umos, so the indicator can display another
      // session's project when several umos have projects loaded
      // concurrently. Plan mode already passes umo (see below);
      // project status now mirrors the same pattern.
      void spcodeStatus.refresh(resolveCurrentUmo(currSessionId.value));
      // Plan/build has the same race: an `/plan` or `/build`
      // response is processed during stream-end, so the chip needs
      // to be refreshed in lockstep to stay in sync with the bot's
      // state of record. We re-query with the FULL unified_msg_origin
      // (not the bare session id) so the backend's `_plan_mode[umo]`
      // lookup actually hits the key the bot just wrote.
      void spcodePlanMode.refresh(resolveCurrentUmo(currSessionId.value));
      // Codegraph MCP state is global (not per-umo), so no umo arg.
      // Mirrors project/plan: stream-end is the authoritative sync
      // point — the bot has just finished processing any
      // `/codegraph start|stop|set` command the user dispatched.
      void codegraphStatus.refresh();
    }
  },
});

// Inline file-review comments (Chunk 4). The store is a module-level
// singleton (see useFileComments.ts header); FileBrowserFilePreview
// (inside GitDiffSidebar → FileBrowserView) and this ChatInput share
// the same instance. resetForSession() drops the current session's
// comments so they don't leak across sessions (spec §2).
const fileComments = useFileComments();
watch(currSessionId, (newId, oldId) => {
  if (oldId && newId !== oldId) {
    fileComments.resetForSession();
  }
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

// Re-fetch the spcode status when the active session changes. Each
// session has its own loaded project so the chip must refresh.
//
// This is the only code path that updates the chip from chat activity:
// the dashboard deliberately does NOT parse bot message text for
// status markers. Status is always pulled via the plugin's HTTP
// endpoint (`spcode/project-status`) so the bot's `/project *`
// responses are free to be pure prose without hidden side channels.
watch(
  currSessionId,
  async (next) => {
    if (!next) {
      spcodeStatus.reset();
      // Plan/build is strictly per-umo; clearing the session wipes
      // its associated plan state too. We pass null so the backend
      // returns the default build status (active=false), which the
      // chip displays correctly until the next session is selected.
      spcodePlanMode.reset();
      return;
    }
    // Close the Git Diff sidebar on session switch: the new session's
    // project status (if any) is fetched async, but the sidebar would
    // otherwise keep showing the previous session's diff. Other sidebars
    // retain their current behavior (the spec's E13 "close together"
    // wording is inaccurate — only the git-diff sidebar closes here).
    gitDiffSidebarOpen.value = false;
    // Bug fix (2026-06-23, elecvoid243): pass the resolved umo so the
    // backend queries THIS session's loaded project. The bare
    // refresh() hit the "most-recently-loaded project across all
    // umos" fallback branch — wrong in the multi-umo case. See the
    // matching fix in onStreamEnd above and in ChatInput.vue's
    // showSpcodeIndicator watcher.
    await spcodeStatus.refresh(resolveCurrentUmo(next));
    // Same lifecycle for plan/build: the chip is per-umo, so it
        // MUST be re-fetched on every session switch. We do not
        // optimistically carry over the previous session's flag because
        // plan/build is intentionally NOT shared between sessions (a
        // user might want plan mode in one project while building in
        // another).
        //
        // CRITICAL: refresh() requires the full unified_msg_origin string
        // the backend keys per-session state on, NOT the bare session id
        // (webchat conversation id). See :func:`resolveCurrentUmo` for the
        // exact format.
        await spcodePlanMode.refresh(resolveCurrentUmo(next));
  },
  { immediate: true },
);

/**
 * Build the unified message origin (umo) string for a session id,
 * matching the format the backend uses to key its per-session state
 * (e.g. spcode's ``_plan_mode[umo]`` dict).
 *
 * Why this exists:
 *   - The backend's webchat adapter sets
 *     ``abm.session_id = f"webchat!{username}!{cid}"``, so the umo
 *     that ``MessageSession.__str__()`` produces is
 *     ``webchat:{FriendMessage|GroupMessage}:webchat!{user}!{cid}``.
 *   - The frontend's ``currentSession.session_id`` is the bare
 *     ``cid`` (the conversation id), not the full umo.
 *   - Passing the bare cid to ``spcodePlanMode.refresh()`` makes the
 *     backend's ``_plan_mode.get(bareCid, False)`` always miss, so
 *     ``active`` comes back ``False`` regardless of what /plan did.
 *     That is why the chip flashed plan-active for a frame then
 *     snapped back to build mode after every toggle.
 *
 * Returns the full umo, or ``null`` if the session is unknown (the
 * refresh caller treats ``null`` as "no umo → backend returns
 * build-state", which is the correct fallback for an unmapped
 * session).
 */
function resolveCurrentUmo(sessionId: string): string | null {
  if (!sessionId) return null;
  const session =
    sessions.value.find((s) => s.session_id === sessionId) ||
    projectSessions.value.find((s) => s.session_id === sessionId);
  if (!session) return null;
  const platformId = session.platform_id || "webchat";
  if (platformId === "webchat") {
    return buildWebchatUmoDetails(
      sessionId,
      Boolean(session.is_group),
    ).umo;
  }
  // Generic fallback for non-webchat platforms: trust the platform's
  // own session_id format. message_type falls back to FriendMessage
  // when is_group is missing or zero.
  const messageType = session.is_group ? "GroupMessage" : "FriendMessage";
  return `${platformId}:${messageType}:${sessionId}`;
}

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
  replyTarget.value = null;
  newChat();
  closeMobileSidebar();
  await focusChatInput();
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
  // D13 guard: allow sending when draft is empty if there are staged
  // files OR file-review comments. Otherwise return.
  if (
    !canSend.value &&
    !stagedFiles.value.length &&
    fileComments.totalCount.value === 0
  ) {
    return;
  }

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

    const userText = draft.value.trim();
    const commentText = fileComments.formatForLLM();
    // Concatenate user text + comment block with a blank line. The
    // bot's first message will show "[File review comments]" header
    // even when userText is empty.
    const text = [userText, commentText].filter(Boolean).join("\n\n");
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
    await focusChatInput();
  }
}

/**
 * Handle InteractiveChoiceBox submit (spec §4.5): bubbled up from
 * ChatMessageList, creates a user record + bot record via
 * createLocalExchange and dispatches sendMessageStream with the
 * currently selected transport / streaming / provider settings.
 *
 * Unlike sendCurrentMessage, no new session is created — the user
 * can only encounter an interactive choice inside an existing chat.
 */
function onInteractiveChoiceSubmit(text: string) {
  const sessionId = currSessionId.value;
  if (!sessionId) return;
  const messageId = crypto.randomUUID?.() || `${Date.now()}-${Math.random()}`;
  const parts: MessagePart[] = [{ type: "plain", text }];
  const selection = inputRef.value?.getCurrentSelection();
  const { userRecord, botRecord } = createLocalExchange({
    sessionId,
    messageId,
    parts,
  });
  sendMessageStream({
    sessionId,
    messageId,
    parts,
    transport: transportMode.value,
    enableStreaming: enableStreaming.value,
    selectedProvider: selection?.providerId || "",
    selectedModel: selection?.modelName || "",
    userRecord,
    botRecord,
  });
}

/**
 * Send a system command (e.g. /plan, /build) as a chat message without
 * touching the user's draft, reply target, or staged attachments.
 *
 * The chip emits "send-command" so the parent can dispatch the toggle
 * command while the user's current input remains untouched. This mirrors
 * the existing sendMessageStream pattern used in sendCurrentMessage
 * but intentionally skips:
 *   - draft.value = ""
 *   - replyTarget reset
 *   - clearStaged({ revokeUrls: false })
 *   - updateTitleFromText
 *   - focusChatInput (let the user keep their cursor)
 *
 * Args:
 *   command: The command text to send (e.g. "/plan", "/build").
 */
async function sendSystemCommand(command: string) {
  if (!command.trim()) return;

  // Prevent overlapping system-command sends. The chip remains disabled
  // via the parent's `:disabled="sending"` binding on ChatInput, but
  // direct double-click on the chip edge can still reach here.
  if (commandSending.value) return;
  commandSending.value = true;

  try {
    let sessionId = currSessionId.value;
    if (!sessionId) {
      sessionId = await newSession();
    }

    const messageId =
      crypto.randomUUID?.() || `${Date.now()}-${Math.random()}`;

    const outgoingParts: MessagePart[] = [
      { type: "plain", text: command },
    ];

    const selection = inputRef.value?.getCurrentSelection();

    const { userRecord, botRecord } = createLocalExchange({
      sessionId,
      messageId,
      parts: outgoingParts,
    });

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
    console.error("Failed to send system command:", error);
  } finally {
    commandSending.value = false;
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
  todoSidebarOpen.value = false;
  gitDiffSidebarOpen.value = false;
  activeReasoningTarget.value = payload;
  reasoningPanelOpen.value = true;
}

function openGitDiffSidebar(): void {
  // Mutual exclusion: close every other sidebar before opening the
  // Git Diff sidebar. The watch in GitDiffSidebar will also auto-close
  // the sidebar when the underlying spcode project is unloaded.
  threadPanelOpen.value = false;
  activeThread.value = null;
  reasoningPanelOpen.value = false;
  activeReasoningTarget.value = null;
  refsSidebarOpen.value = false;
  selectedRefs.value = null;
  todoSidebarOpen.value = false;
  gitDiffSidebarOpen.value = true;
}

// 之前基于 reactive 追踪的 parseTodoToolResult / extractLatestTodoSnapshot
// 已经被 useMessages 层主动 emit 替代(见 useMessages.ts 的 latestTodoSnapshot)。

/** todo 快照按当前会话隔离。
 *
 * useMessages 暴露 `latestTodoSnapshotBySession` 是 ref<Record<sessionId, snapshot>>,
 * 每次 finishToolCall 时整体替换 `value = {...current, [sid]: snap}`,
 * ref.set 100% 触发响应 → 本 computed 重算 → ChatUI 实时刷新。
 *
 * key 可能是 undefined (新会话还没 todo) → 读出 undefined → 转为 null 给 UI。
 */
const currentTodoSnapshot = computed(() => {
  const sid = currSessionId.value;
  if (!sid) return null;
  return latestTodoSnapshotBySession.value[sid] ?? null;
});

/** summary bar 出现时,如果持久化的位置已超出当前窗口, 则重置居中。
 *  同时: 快照被清空(todo_clear / 全删光)时同步关闭抽屉,
 *  避免出现"bar 没了但抽屉还开着显示空状态"的尴尬。
 */
watch(currentTodoSnapshot, (snap) => {
  // 1) 快照为 null → 关抽屉 (清空/全删空场景)
  if (snap === null && todoSidebarOpen.value) {
    todoSidebarOpen.value = false;
  }
  // 2) 快照非空且 bar 位置已确定 → 位置越界时回弹
  if (!snap || todoBarPos.value === null) return;
  nextTick(() => {
    const main = document.querySelector(".chat-main") as HTMLElement | null;
    const bar = document.querySelector(".todo-summary-bar") as HTMLElement | null;
    if (!main || !bar) return;
    const mainRect = main.getBoundingClientRect();
    const barRect = bar.getBoundingClientRect();
    const clamped = clampBarPos(
      todoBarPos.value!.left,
      todoBarPos.value!.top,
      barRect,
      mainRect,
    );
    if (
      clamped.left !== todoBarPos.value!.left ||
      clamped.top !== todoBarPos.value!.top
    ) {
      todoBarPos.value = clamped;
    }
  });
}, { immediate: true });

// 与 RefsSidebar 互斥:打开 todo 时收起 refs
watch(todoSidebarOpen, (open) => {
  if (open) refsSidebarOpen.value = false;
});
watch(refsSidebarOpen, (open) => {
  if (open) todoSidebarOpen.value = false;
});

function toggleTodoSidebar() {
  todoSidebarOpen.value = !todoSidebarOpen.value;
}

/** 键盘焦点落在 bar 上时的快捷键声明(用于 a11y 屏幕阅读器)。
 *
 * 实际行为:
 * - Enter / Space  → 浏览器对 <button> 的默认行为 → 触发 @click → toggleTodoSidebar()
 * - Arrow 方向键  → onTodoBarKeydown → 移动位置 8px
 */
const todoBarKeyShortcuts = "Enter Space ArrowLeft ArrowRight ArrowUp ArrowDown";

/** 键盘移动 bar 位置。Shift 加速为 32px/次;Home 复位到居中。 */
const TODO_BAR_KEY_STEP = 8;
function onTodoBarKeydown(e: KeyboardEvent) {
  // 防御:只有 bar 可见且有快照时才进入(理论上 v-if 已 guard,但 keydown 仍要防)
  if (!currentTodoSnapshot.value) return;

  // 方向键移动
  let dx = 0;
  let dy = 0;
  if (e.key === "ArrowLeft") dx = -1;
  else if (e.key === "ArrowRight") dx = 1;
  else if (e.key === "ArrowUp") dy = -1;
  else if (e.key === "ArrowDown") dy = 1;
  else if (e.key === "Home") {
    // 复位:清空位置让 CSS centered 样式接管
    todoBarPos.value = null;
    try { localStorage.removeItem(TODO_BAR_POS_KEY); } catch { /* ignore */ }
    e.preventDefault();
    return;
  } else {
    // 其它键不拦(让 Enter/Space 等透传给 button 默认行为)
    return;
  }

  // 阻止页面方向键滚动
  e.preventDefault();
  e.stopPropagation();
  const step = (e.shiftKey ? 4 : 1) * TODO_BAR_KEY_STEP;

  // 第一次方向键按下:如果位置未初始化,先按当前 CSS centered 位置算一个起点
  if (todoBarPos.value === null) {
    const bar = document.querySelector(".todo-summary-bar") as HTMLElement | null;
    const main = document.querySelector(".chat-main") as HTMLElement | null;
    if (!bar || !main) return;
    const mainRect = main.getBoundingClientRect();
    const barRect = bar.getBoundingClientRect();
    const startLeft = mainRect.left + Math.max(16, (mainRect.width - barRect.width) / 2);
    const startTop = mainRect.top + 16;
    todoBarPos.value = clampBarPos(startLeft, startTop, barRect, mainRect);
  }

  const current = todoBarPos.value!;
  const bar = document.querySelector(".todo-summary-bar") as HTMLElement | null;
  const main = document.querySelector(".chat-main") as HTMLElement | null;
  if (!bar || !main) return;
  const mainRect = main.getBoundingClientRect();
  const barRect = bar.getBoundingClientRect();
  todoBarPos.value = clampBarPos(
    current.left + dx * step,
    current.top + dy * step,
    barRect,
    mainRect,
  );
  // 持久化(与鼠标拖动 endDragTodoBar 共用同一 key,策略一致)
  try {
    localStorage.setItem(TODO_BAR_POS_KEY, JSON.stringify(todoBarPos.value));
  } catch { /* ignore quota / private mode */ }
}

/** RefsSidebar 的 modelValue 变化回调:关闭时由用户主动操作,无需特别处理;
 *  开启时由于 watch 已自动收起 todo,这里只作为占位以保持事件链可读。
 */
function onRefsToggle(open: boolean) {
  if (!open) return;
  // 互斥由 watch(refsSidebarOpen) 自动处理 todo 侧
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
  padding-right: 68px;
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
  right: 12px;
  top: 50%;
  transform: translateY(-50%);
  flex-shrink: 0;
  transition: right 0.16s ease;
}

.session-actions {
  display: flex;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
  opacity: 0;
  pointer-events: none;
  position: absolute;
  right: 8px;
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
  right: 62px;
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

/* Todo summary bar — 浮窗式 (position: fixed)
   初始位置: 顶部工具栏下方 64px 处的页面正中 (避开 50px v-app-bar + 14px buffer)
   拖动后: 改用 inline style (left/top px), 通过 clampBarPos 限制在 chat-main 内
   z-index: 必须大于 v-app-bar (z-index: 100) 否则被工具栏遮挡 */
.todo-summary-bar {
  position: fixed;
  z-index: 9999;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  border: 1px solid rgba(var(--v-border-color), 0.18);
  border-radius: 999px;
  background: rgba(var(--v-theme-surface), 0.78);
  color: rgba(var(--v-theme-on-surface), 0.82);
  font-size: 12.5px;
  font-weight: 500;
  line-height: 1;
  cursor: grab;
  user-select: none;
  -webkit-user-select: none;
  transition: background 0.18s ease, border-color 0.18s ease,
    color 0.18s ease, box-shadow 0.18s ease;
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
  max-width: calc(100vw - 24px);
}
.todo-summary-bar:hover {
  background: rgba(var(--v-theme-primary), 0.1);
  border-color: rgba(var(--v-theme-primary), 0.35);
  color: rgb(var(--v-theme-on-surface));
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.1);
}
.todo-summary-bar--active {
  background: rgba(var(--v-theme-primary), 0.14);
  border-color: rgba(var(--v-theme-primary), 0.5);
  color: rgb(var(--v-theme-on-surface));
  box-shadow: 0 0 0 2px rgba(var(--v-theme-primary), 0.15);
}
.todo-summary-bar--dragging {
  cursor: grabbing;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  transition: none; /* 拖动中不要 transition 跟手 */
}
/* 初始居中状态: 拖动后会被 inline left/top 覆盖
   注意: top 必须大于 v-app-bar 的 50px,否则会被顶部工具栏遮挡;
   z-index 抬高到 1201 略高于 .v-toolbar 的 1200,作为防御。*/
.todo-summary-bar--centered {
  left: 50% !important;
  top: 60px !important;
  z-index: 1201;
  transform: translateX(-50%);
  animation: todo-bar-fade-in 0.2s ease;
}
@keyframes todo-bar-fade-in {
  from { opacity: 0; transform: translateX(-50%) translateY(-4px); }
  to   { opacity: 1; transform: translateX(-50%) translateY(0); }
}

/* 整体淡入/淡出: 跟随 currentTodoSnapshot 的 v-if 切换。
   故意只动 opacity,不碰 transform — 避免和 --centered 的
   translateX(-50%) 互相覆盖造成"漂"的感觉。
   leave 时短暂禁用 pointer-events,防止用户在淡出过程中误点。 */
.todo-bar-fade-enter-active,
.todo-bar-fade-leave-active {
  transition: opacity 0.2s ease;
}
.todo-bar-fade-enter-from,
.todo-bar-fade-leave-to {
  opacity: 0;
}
.todo-bar-fade-leave-to {
  pointer-events: none;
}
.todo-summary-icon {
  color: rgba(var(--v-theme-primary), 0.85);
  flex-shrink: 0;
}
.todo-summary-drag-handle {
  color: rgba(var(--v-theme-on-surface), 0.35);
  flex-shrink: 0;
  margin-right: 2px;
}
.todo-summary-text {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  white-space: nowrap;
}
.todo-summary-progress {
  color: #b58400;
  font-weight: 500;
}
.todo-summary-circular {
  flex-shrink: 0;
  font-size: 9px;
  font-weight: 600;
}
.todo-summary-attention {
  flex-shrink: 0;
  margin-left: 2px;
}

@media (max-width: 760px) {
  .todo-summary-text {
    /* 移动端隐藏冗长文字, 只留进度环 + 图标 */
    display: none;
  }
  .todo-summary-drag-handle {
    display: none;
  }
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

  .composer-shell,
  .project-composer-shell {
    padding: 0;
  }
}
</style>
