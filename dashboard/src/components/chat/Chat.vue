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

        <GroupList
          v-if="!isSidebarCollapsed"
          :sessions="groupSessions"
          :selected-session-id="currSessionId"
          @create-group="startNewGroupChat"
          @select-session="selectProjectSession"
          @edit-session-title="editSidebarSessionTitle"
          @delete-session="deleteSidebarSession"
        />
      </div>

      <div v-if="!isSidebarCollapsed" class="session-list">
        <div
          v-for="session in privateSessions"
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
      <div
        v-if="currSessionId && !workspacePanelOpen && !groupPanelOpen"
        class="chat-main-actions"
      >
        <v-btn
          icon="mdi-folder-open-outline"
          size="small"
          variant="text"
          :title="tm('workspace.open')"
          @click="workspacePanelOpen = true"
        />
        <v-btn
          v-if="isGroupSession"
          icon="mdi-forum"
          size="small"
          variant="text"
          :title="tm('group.panelTitle')"
          @click="groupPanelOpen = true"
        />
      </div>

      <ProjectView
        v-if="selectedProject"
        :project="selectedProject"
        :sessions="projectSessions"
        @select-session="selectProjectSession"
        @edit-session-title="editProjectSessionTitle"
        @delete-session="deleteProjectSession"
      >
        <section class="project-composer-shell">
          <div v-if="currentTypingText" class="chat-typing-indicator">
            <span>{{ currentTypingText }}</span>
            <span class="typing-dots" aria-hidden="true">
              <span></span>
              <span></span>
              <span></span>
            </span>
          </div>
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
            :mentionable-bots="isGroupSession ? currentGroupBots : []"
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
          :class="{ 'is-group-chat': isGroupSession }"
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
            :class="{ 'is-group-chat': isGroupSession }"
          >
            <ChatMessageList
              v-model:edit-draft="messageEditDraft"
              :messages="activeMessages"
              :is-dark="isDark"
              :is-streaming="
                Boolean(currSessionId && isSessionRunning(currSessionId))
              "
              :enable-edit="
                !isGroupSession &&
                !Boolean(currSessionId && isSessionRunning(currSessionId))
              "
              :enable-regenerate="!isGroupSession"
              enable-thread-selection
              :manage-refs-sidebar="false"
              :editing-message-id="editingMessage?.id || null"
              :saving-edit="savingMessageEdit"
              :show-sender-names="isGroupSession"
              :use-default-bot-avatar="isGroupSession"
              :bot-avatars="currentGroupBotAvatars"
              :hide-loading-bot-message="isGroupSession"
              @open-edit="openMessageEdit"
              @cancel-edit="cancelMessageEdit"
              @save-edit="saveMessageEdit"
              @regenerate="handleRegenerateMessage"
              @regenerate-with-model="handleRegenerateMessage"
              @select-bot-text="handleBotTextSelection"
              @open-thread="openThreadPanel"
              @open-refs="openRefsSidebar"
            />
          </div>
        </section>

        <section class="composer-shell">
          <div v-if="currentTypingText" class="chat-typing-indicator">
            <span>{{ currentTypingText }}</span>
            <span class="typing-dots" aria-hidden="true">
              <span></span>
              <span></span>
              <span></span>
            </span>
          </div>
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
            :mentionable-bots="isGroupSession ? currentGroupBots : []"
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

    <ProviderConfigDialog v-model="providerDialog" />
    <ProjectDialog
      v-model="projectDialogOpen"
      :project="editingProject"
      @save="saveProject"
    />
    <v-dialog v-model="groupDialogOpen" max-width="500">
      <v-card>
        <v-card-title class="text-h6">{{ tm("group.create") }}</v-card-title>
        <v-card-text class="group-dialog-body">
          <v-text-field
            v-model="groupNameDraft"
            :label="tm('group.name')"
            variant="outlined"
            density="comfortable"
            hide-details
            autofocus
            @keydown.enter="createGroupFromDialog"
          />
          <div class="avatar-upload-row">
            <v-avatar size="44" rounded="lg">
              <img :src="groupAvatarDraft || defaultGroupAvatar" alt="" />
            </v-avatar>
            <v-btn
              variant="tonal"
              prepend-icon="mdi-upload"
              :loading="uploadingGroupAvatar"
              @click="groupAvatarInputRef?.click()"
            >
              {{ tm("group.uploadAvatar") }}
            </v-btn>
            <input
              ref="groupAvatarInputRef"
              class="avatar-upload-input"
              type="file"
              accept="image/*"
              @change="handleGroupAvatarSelected"
            />
          </div>
          <v-textarea
            v-model="groupDescriptionDraft"
            :label="tm('group.description')"
            variant="outlined"
            density="comfortable"
            rows="3"
            auto-grow
            hide-details
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="groupDialogOpen = false">
            {{ t("core.common.cancel") }}
          </v-btn>
          <v-btn
            color="primary"
            variant="flat"
            :loading="savingGroup"
            @click="createGroupFromDialog"
          >
            {{ t("core.common.save") }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
    <v-dialog v-model="groupBotDialogOpen" max-width="460">
      <v-card>
        <v-card-title class="text-h6">{{ tm("group.addBot") }}</v-card-title>
        <v-card-text class="group-bot-dialog-body">
          <v-btn-toggle
            v-model="groupBotDialogMode"
            mandatory
            density="comfortable"
            class="group-bot-mode-toggle"
          >
            <v-btn value="existing">
              {{ tm("group.addExisting") }}
            </v-btn>
            <v-btn value="new">
              {{ tm("group.createNewBot") }}
            </v-btn>
          </v-btn-toggle>
          <div
            v-if="groupBotDialogMode === 'existing'"
            class="group-bot-platform-list"
          >
            <div class="group-bot-platform-list-title">
              {{ tm("group.availableBots") }}
            </div>
            <div
              v-for="platform in existingGroupBotPlatformOptions"
              :key="platform.id"
              class="group-bot-platform-item"
              :class="{
                selected: groupBotPlatformId === platform.id,
                disabled: isGroupBotPlatformInUse(platform.id),
              }"
              role="button"
              tabindex="0"
              :aria-disabled="isGroupBotPlatformInUse(platform.id)"
              @click="selectGroupBotPlatform(platform)"
              @keydown.enter.prevent="selectGroupBotPlatform(platform)"
              @keydown.space.prevent="selectGroupBotPlatform(platform)"
            >
              <v-avatar size="28" rounded="lg">
                <img :src="platform.avatar || defaultGroupAvatar" alt="" />
              </v-avatar>
              <span class="group-bot-platform-name">{{ platform.name }}</span>
              <span class="group-bot-platform-id">{{ platform.id }}</span>
              <v-chip
                v-if="isGroupBotPlatformInUse(platform.id)"
                size="x-small"
                variant="tonal"
              >
                {{ tm("group.added") }}
              </v-chip>
              <v-btn
                v-if="platform.session_id && platform.bot_id"
                icon="mdi-delete-outline"
                size="x-small"
                variant="text"
                :aria-label="tm('group.deleteBot')"
                @click.stop="deleteExistingGroupBot(platform)"
              />
            </div>
            <div
              v-if="!existingGroupBotPlatformOptions.length"
              class="group-bot-empty-state"
            >
              {{ tm("group.noExistingBots") }}
            </div>
          </div>

          <template v-else>
            <v-text-field
              v-model="groupBotName"
              :label="tm('group.botName')"
              variant="outlined"
              density="comfortable"
              hide-details
              autofocus
              @keydown.enter="createGroupBotFromDialog"
            />
            <v-select
              v-model="groupBotConfId"
              :items="abconfOptions"
              item-title="name"
              item-value="id"
              :label="tm('group.config')"
              variant="outlined"
              density="comfortable"
              hide-details
            />
            <div class="avatar-upload-row">
              <v-avatar size="40" rounded="lg">
                <img :src="groupBotAvatar || defaultGroupAvatar" alt="" />
              </v-avatar>
              <v-btn
                variant="tonal"
                prepend-icon="mdi-upload"
                :loading="uploadingGroupBotAvatar"
                @click="groupBotAvatarInputRef?.click()"
              >
                {{ tm("group.uploadAvatar") }}
              </v-btn>
              <input
                ref="groupBotAvatarInputRef"
                class="avatar-upload-input"
                type="file"
                accept="image/*"
                @change="handleGroupBotAvatarSelected"
              />
            </div>
          </template>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="groupBotDialogOpen = false">
            {{ t("core.common.cancel") }}
          </v-btn>
          <v-btn
            color="primary"
            variant="flat"
            :loading="savingGroupBot"
            :disabled="!canSubmitGroupBotDialog"
            @click="createGroupBotFromDialog"
          >
            {{ t("core.common.save") }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
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
    <WorkspacePanel
      v-model="workspacePanelOpen"
      :session-id="currSessionId || null"
    />
    <GroupPanel
      v-model="groupPanelOpen"
      :group="currentGroupProfile"
      :bots="currentGroupBots"
      :fallback-name="currentSessionTitle || tm('group.defaultName')"
      @add-bot="openGroupBotDialog"
      @delete-bot="deleteGroupBot"
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
import ProviderConfigDialog from "@/components/chat/ProviderConfigDialog.vue";
import ProjectDialog, {
  type ProjectFormData,
} from "@/components/chat/ProjectDialog.vue";
import ProjectList, { type Project } from "@/components/chat/ProjectList.vue";
import GroupList from "@/components/chat/GroupList.vue";
import ProjectView from "@/components/chat/ProjectView.vue";
import ChatInput from "@/components/chat/ChatInput.vue";
import ChatMessageList from "@/components/chat/ChatMessageList.vue";
import type { RegenerateModelSelection } from "@/components/chat/RegenerateMenu.vue";
import ThreadPanel from "@/components/chat/ThreadPanel.vue";
import WorkspacePanel from "@/components/chat/WorkspacePanel.vue";
import GroupPanel from "@/components/chat/GroupPanel.vue";
import RefsSidebar from "@/components/chat/message_list_comps/RefsSidebar.vue";
import { useSessions, type Session } from "@/composables/useSessions";
import {
  useMessages,
  type ChatRecord,
  type ChatThread,
  type GroupBot,
  type GroupProfile,
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
import { useToast } from "@/utils/toast";
import defaultGroupAvatar from "@/assets/images/chatui-group-default-avatar.png";

const props = withDefaults(defineProps<{ chatboxMode?: boolean }>(), {
  chatboxMode: false,
});

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
  uploadImageAttachment,
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
const groupDialogOpen = ref(false);
const savingGroup = ref(false);
const groupNameDraft = ref("");
const groupAvatarDraft = ref("");
const groupAvatarAttachmentId = ref("");
const uploadingGroupAvatar = ref(false);
const groupAvatarInputRef = ref<HTMLInputElement | null>(null);
const groupDescriptionDraft = ref("");
const groupBotDialogOpen = ref(false);
const savingGroupBot = ref(false);
const groupBotName = ref("");
const groupBotAvatar = ref("");
const groupBotAvatarAttachmentId = ref("");
const uploadingGroupBotAvatar = ref(false);
const groupBotAvatarInputRef = ref<HTMLInputElement | null>(null);
const groupBotConfId = ref("default");
const abconfOptions = ref<Array<{ id: string; name?: string }>>([]);
const groupBotDialogMode = ref<"existing" | "new">("existing");
const groupBotPlatformId = ref("");
type GroupBotPlatformOption = {
  id: string;
  name: string;
  session_id?: string;
  avatar?: string;
  avatar_attachment_id?: string;
  bot_id?: string;
  conf_id?: string;
  platform_id?: string;
};
const groupBotPlatformOptions = ref<GroupBotPlatformOption[]>([]);
const existingGroupBotPlatformOptions = computed(() =>
  groupBotPlatformOptions.value.filter((option) => option.id),
);
const canSubmitGroupBotDialog = computed(() => {
  if (groupBotDialogMode.value === "existing") {
    return Boolean(
      groupBotPlatformId.value &&
        !isGroupBotPlatformInUse(groupBotPlatformId.value),
    );
  }
  return Boolean(groupBotName.value.trim());
});
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
const avatarObjectUrls = new Set<string>();
const shouldStickToBottom = ref(true);
const replyTarget = ref<ChatRecord | null>(null);
const threadPanelOpen = ref(false);
const activeThread = ref<ChatThread | null>(null);
const deletingThread = ref(false);
const workspacePanelOpen = ref(false);
const groupPanelOpen = ref(false);
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

const {
  loadingMessages,
  sending,
  loadedSessions,
  sessionProjects,
  groupBotsBySession,
  groupProfilesBySession,
  typingBySession,
  activeMessages,
  isSessionRunning,
  isUserMessage,
  messageParts,
  loadSessionMessages,
  ensurePersistentChatConnection,
  closePersistentChatConnections,
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
    null,
);
const privateSessions = computed(() =>
  sessions.value.filter((session) => Number(session.is_group || 0) !== 1),
);
const groupSessions = computed(() =>
  sessions.value.filter((session) => Number(session.is_group || 0) === 1),
);
const isGroupSession = computed(() => Number(currentSession.value?.is_group || 0) === 1);
const currentGroupBots = computed<GroupBot[]>(() =>
  currSessionId.value ? groupBotsBySession[currSessionId.value] || [] : [],
);
const currentGroupBotAvatars = computed<Record<string, string>>(() => {
  const avatars: Record<string, string> = {};
  for (const bot of currentGroupBots.value) {
    if (bot.avatar) avatars[bot.bot_id] = bot.avatar;
  }
  return avatars;
});
const currentGroupProfile = computed<GroupProfile | null>(() =>
  currSessionId.value ? groupProfilesBySession[currSessionId.value] || null : null,
);
const currentTypingNames = computed(() =>
  isGroupSession.value && currSessionId.value
    ? (typingBySession[currSessionId.value] || []).map(
        (item) => item.sender_name || item.sender_id,
      )
    : [],
);
const currentTypingText = computed(() =>
  currentTypingNames.value.length
    ? tm("group.typing", { name: currentTypingNames.value.join(", ") })
    : "",
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
  avatarObjectUrls.forEach((url) => URL.revokeObjectURL(url));
  avatarObjectUrls.clear();
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
      closePersistentChatConnections();
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

async function startNewGroupChat() {
  groupNameDraft.value = "";
  groupAvatarDraft.value = defaultGroupAvatar;
  groupAvatarAttachmentId.value = "";
  groupDescriptionDraft.value = "";
  groupDialogOpen.value = true;
}

async function createGroupFromDialog() {
  const groupName = groupNameDraft.value.trim() || tm("group.defaultName");
  savingGroup.value = true;
  try {
    selectedProjectId.value = null;
    replyTarget.value = null;
    transportMode.value = "websocket";
    const avatarForStorage = groupAvatarAttachmentId.value
      ? ""
      : groupAvatarDraft.value.trim() || defaultGroupAvatar;
    const sessionId = await newSession({
      isGroup: true,
      displayName: groupName,
      avatar: avatarForStorage,
      avatarAttachmentId: groupAvatarAttachmentId.value || undefined,
      description: groupDescriptionDraft.value.trim(),
    });
    groupProfilesBySession[sessionId] = {
      session_id: sessionId,
      name: groupName,
      avatar: groupAvatarDraft.value.trim() || defaultGroupAvatar,
      avatar_attachment_id: groupAvatarAttachmentId.value,
      description: groupDescriptionDraft.value.trim(),
    };
    groupBotsBySession[sessionId] = [];
    closePersistentChatConnections(sessionId);
    ensurePersistentChatConnection(sessionId);
    groupDialogOpen.value = false;
    closeMobileSidebar();
  } finally {
    savingGroup.value = false;
  }
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
  await resolveGroupResourceAvatars(sessionId);
  if (Number(currentSession.value?.is_group || 0) === 1) {
    closePersistentChatConnections(sessionId);
    ensurePersistentChatConnection(sessionId);
  } else {
    closePersistentChatConnections();
  }
  scrollToBottom();
  closeMobileSidebar();
}

async function sendCurrentMessage() {
  const selectedMentionBots = isGroupSession.value
    ? ((inputRef.value?.consumeMentions?.() || []) as GroupBot[])
    : [];
  if (!canSend.value && !selectedMentionBots.length) return;

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
    const targetBots = isGroupSession.value
      ? resolveTargetGroupBots(text, currentGroupBots.value, selectedMentionBots)
      : [];
    const targetBot = targetBots[0] || null;
    const messageId = crypto.randomUUID?.() || `${Date.now()}-${Math.random()}`;
    const outgoingParts = buildOutgoingParts(text, targetBots);
    if (!hasOutgoingContent(outgoingParts)) return;
    const selection = inputRef.value?.getCurrentSelection();
    const { userRecord, botRecord } = createLocalExchange({
      sessionId,
      messageId,
      parts: outgoingParts,
      includeBot: !isGroupSession.value,
    });
    if (isGroupSession.value) {
      userRecord.sender_id = getDashboardUsername();
      userRecord.sender_name = getDashboardUsername();
    }
    updateTitleFromText(sessionId, text);

    draft.value = "";
    replyTarget.value = null;
    clearStaged();
    scrollToBottom();

    sendMessageStream({
      sessionId,
      messageId,
      parts: outgoingParts,
      transport: isGroupSession.value ? "websocket" : transportMode.value,
      enableStreaming: isGroupSession.value ? false : enableStreaming.value,
      selectedProvider: selection?.providerId || "",
      selectedModel: selection?.modelName || "",
      targetBotId: targetBot?.bot_id || "",
      senderId: isGroupSession.value ? getDashboardUsername() : "",
      senderName: isGroupSession.value ? getDashboardUsername() : "",
      usePersistentWebSocket: isGroupSession.value,
      userRecord,
      botRecord,
    });
  } catch (error) {
    console.error("Failed to send message:", error);
  } finally {
    sending.value = false;
  }
}

function buildOutgoingParts(text: string, targetBots: GroupBot[] = []): MessagePart[] {
  const parts: MessagePart[] = [];
  if (replyTarget.value?.id != null) {
    parts.push({
      type: "reply",
      message_id: replyTarget.value.id,
      selected_text: "",
    });
  }
  for (const bot of targetBots) {
    parts.push({ type: "at", target: bot.bot_id, name: bot.name });
  }
  const plainText = targetBots.length ? stripMentionText(text, targetBots) : text;
  if (plainText) {
    parts.push({ type: "plain", text: plainText });
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

function hasOutgoingContent(parts: MessagePart[]) {
  return parts.some((part) => {
    if (part.type === "plain") return Boolean(part.text?.trim());
    if (part.type === "at") return Boolean(part.target || part.bot_id || part.name);
    if (["image", "record", "video", "file"].includes(part.type)) {
      return Boolean(part.attachment_id || part.filename);
    }
    return false;
  });
}

function resolveTargetGroupBots(
  text: string,
  bots: GroupBot[],
  selectedBots: GroupBot[] = [],
) {
  const resolved = new Map<string, GroupBot>();
  for (const bot of selectedBots) {
    resolved.set(bot.bot_id, bot);
  }
  const folded = text.toLowerCase();
  for (const bot of bots) {
    if (folded.includes(`@${bot.name.toLowerCase()}`)) {
      resolved.set(bot.bot_id, bot);
    }
  }
  return Array.from(resolved.values());
}

function stripMentionText(text: string, bots: GroupBot[]) {
  return bots
    .reduce((result, bot) => {
      const pattern = new RegExp(
        `(^|\\s)@${escapeRegExp(bot.name)}(?=\\s|$)`,
        "gi",
      );
      return result.replace(pattern, " ");
    }, text)
    .replace(/\s{2,}/g, " ")
    .trim();
}

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

async function uploadAvatarFile(file: File) {
  const uploaded = await uploadImageAttachment(file);
  avatarObjectUrls.add(uploaded.url);
  return uploaded;
}

async function handleGroupAvatarSelected(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = "";
  if (!file) return;
  uploadingGroupAvatar.value = true;
  try {
    const uploaded = await uploadAvatarFile(file);
    groupAvatarDraft.value = uploaded.url;
    groupAvatarAttachmentId.value = uploaded.attachment_id;
  } finally {
    uploadingGroupAvatar.value = false;
  }
}

async function handleGroupBotAvatarSelected(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = "";
  if (!file) return;
  uploadingGroupBotAvatar.value = true;
  try {
    const uploaded = await uploadAvatarFile(file);
    groupBotAvatar.value = uploaded.url;
    groupBotAvatarAttachmentId.value = uploaded.attachment_id;
  } finally {
    uploadingGroupBotAvatar.value = false;
  }
}

async function resolveAttachmentAvatar(attachmentId?: string) {
  if (!attachmentId) return "";
  const response = await axios.get("/api/chat/get_attachment", {
    params: { attachment_id: attachmentId },
    responseType: "blob",
  });
  const url = URL.createObjectURL(response.data);
  avatarObjectUrls.add(url);
  return url;
}

async function resolveGroupResourceAvatars(sessionId: string) {
  const group = groupProfilesBySession[sessionId];
  if (group?.avatar_attachment_id && !group.avatar?.startsWith("blob:")) {
    group.avatar = await resolveAttachmentAvatar(group.avatar_attachment_id);
  }

  const bots = groupBotsBySession[sessionId] || [];
  await Promise.all(
    bots.map(async (bot) => {
      if (bot.avatar_attachment_id && !bot.avatar?.startsWith("blob:")) {
        bot.avatar = await resolveAttachmentAvatar(bot.avatar_attachment_id);
      }
    }),
  );
}

function getDashboardUsername() {
  try {
    return localStorage.getItem("user")?.trim() || "guest";
  } catch {
    return "guest";
  }
}

async function openGroupBotDialog() {
  groupBotName.value = "";
  groupBotAvatar.value = defaultGroupAvatar;
  groupBotAvatarAttachmentId.value = "";
  groupBotConfId.value = "default";
  groupBotPlatformId.value = "";
  groupBotDialogMode.value = "existing";
  groupBotDialogOpen.value = true;
  if (!abconfOptions.value.length) {
    const response = await axios.get("/api/config/abconfs");
    abconfOptions.value = response.data?.data?.info_list || [];
  }
  const platformResponse = await axios.get("/api/chat/group/bot/platforms");
  groupBotPlatformOptions.value = await Promise.all(
    (platformResponse.data?.data?.platforms || []).map(
      async (platform: GroupBotPlatformOption) => {
        const platformId = platform.platform_id || platform.id;
        const avatar =
          platform.avatar_attachment_id && !platform.avatar?.startsWith("blob:")
            ? await resolveAttachmentAvatar(platform.avatar_attachment_id)
            : platform.avatar || "";
        return {
          ...platform,
          id: platformId,
          platform_id: platformId,
          avatar,
        };
      },
    ),
  );
  if (!existingGroupBotPlatformOptions.value.length) {
    groupBotDialogMode.value = "new";
  }
}

function isGroupBotPlatformInUse(platformId: string) {
  return currentGroupBots.value.some((bot) => bot.platform_id === platformId);
}

function selectGroupBotPlatform(platform: GroupBotPlatformOption) {
  if (isGroupBotPlatformInUse(platform.id)) return;
  groupBotPlatformId.value = platform.id;
  if (!groupBotName.value.trim()) {
    groupBotName.value = platform.name;
  }
}

async function deleteExistingGroupBot(platform: GroupBotPlatformOption) {
  if (!platform.session_id || !platform.bot_id) return;
  await axios.post("/api/chat/group/bot/delete", {
    session_id: platform.session_id,
    bot_id: platform.bot_id,
  });
  groupBotPlatformOptions.value = groupBotPlatformOptions.value.filter(
    (item) => item.id !== platform.id,
  );
  if (groupBotPlatformId.value === platform.id) {
    groupBotPlatformId.value = "";
  }
  if (currSessionId.value && platform.session_id === currSessionId.value) {
    groupBotsBySession[currSessionId.value] = currentGroupBots.value.filter(
      (item) => item.bot_id !== platform.bot_id,
    );
  }
}

async function createGroupBotFromDialog() {
  if (!currSessionId.value || !canSubmitGroupBotDialog.value) return;
  savingGroupBot.value = true;
  try {
    const selectedPlatform = existingGroupBotPlatformOptions.value.find(
      (platform) => platform.id === groupBotPlatformId.value,
    );
    const botName =
      groupBotDialogMode.value === "existing"
        ? selectedPlatform?.name || groupBotPlatformId.value
        : groupBotName.value.trim();
    const avatarAttachmentId =
      groupBotDialogMode.value === "existing"
        ? selectedPlatform?.avatar_attachment_id || ""
        : groupBotAvatarAttachmentId.value;
    const avatarValue =
      groupBotDialogMode.value === "existing"
        ? selectedPlatform?.avatar || ""
        : groupBotAvatar.value.trim();
    const avatarForStorage = avatarAttachmentId
      ? ""
      : avatarValue || defaultGroupAvatar;
    const response = await axios.post("/api/chat/group/bot/create", {
      session_id: currSessionId.value,
      name: botName,
      avatar: avatarAttachmentId ? "" : avatarForStorage,
      avatar_attachment_id: avatarAttachmentId || undefined,
      conf_id:
        groupBotDialogMode.value === "existing"
          ? selectedPlatform?.conf_id || "default"
          : groupBotConfId.value || "default",
      platform_id:
        groupBotDialogMode.value === "existing"
          ? groupBotPlatformId.value
          : undefined,
    });
    const bot = response.data?.data?.bot;
    if (bot) {
      bot.avatar = avatarValue || defaultGroupAvatar;
      bot.avatar_attachment_id =
        avatarAttachmentId || bot.avatar_attachment_id || "";
      groupBotsBySession[currSessionId.value] = [
        ...currentGroupBots.value,
        bot,
      ];
    }
    groupBotDialogOpen.value = false;
  } finally {
    savingGroupBot.value = false;
  }
}

async function deleteGroupBot(bot: GroupBot) {
  if (!currSessionId.value) return;
  await axios.post("/api/chat/group/bot/delete", {
    session_id: currSessionId.value,
    bot_id: bot.bot_id,
  });
  groupBotsBySession[currSessionId.value] = currentGroupBots.value.filter(
    (item) => item.bot_id !== bot.bot_id,
  );
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
  activeThread.value = thread;
  threadPanelOpen.value = true;
}

function openRefsSidebar(refs: unknown) {
  selectedRefs.value =
    refs && typeof refs === "object" ? (refs as Record<string, unknown>) : null;
  refsSidebarOpen.value = true;
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

.chat-main-actions {
  position: absolute;
  top: 12px;
  right: 14px;
  z-index: 3;
  display: flex;
  align-items: center;
  gap: 4px;
  color: var(--chat-muted);
}

.chat-main-actions :deep(.v-btn) {
  background: rgba(var(--v-theme-surface), 0.86);
  backdrop-filter: blur(8px);
}

.messages-panel {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 24px max(24px, calc((100% - 980px) / 2)) 18px;
}

.messages-panel.is-group-chat {
  padding-right: 16px;
  padding-left: 16px;
}

.messages-list-shell.is-group-chat {
  width: 85%;
  max-width: 900px;
  margin: 0 auto;
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

.group-dialog-body,
.group-bot-dialog-body {
  display: grid;
  gap: 14px;
}

.group-bot-platform-list {
  display: grid;
  gap: 6px;
}

.group-bot-platform-list-title {
  font-size: 12px;
  color: var(--chat-muted);
}

.group-bot-mode-toggle {
  width: fit-content;
}

.group-bot-platform-item {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto auto auto;
  align-items: center;
  gap: 8px;
  min-height: 42px;
  padding: 6px 8px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.1);
  border-radius: 8px;
  background: transparent;
  color: inherit;
  cursor: pointer;
  text-align: left;
}

.group-bot-platform-item.selected {
  border-color: rgba(var(--v-theme-primary), 0.6);
  background: rgba(var(--v-theme-primary), 0.08);
}

.group-bot-platform-item.disabled {
  cursor: default;
  opacity: 0.58;
}

.group-bot-platform-item img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.group-bot-platform-name,
.group-bot-platform-id {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.group-bot-platform-name {
  font-size: 13px;
  font-weight: 500;
}

.group-bot-platform-id {
  font-size: 11px;
  color: var(--chat-muted);
}

.group-bot-empty-state {
  padding: 10px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.1);
  border-radius: 8px;
  color: var(--chat-muted);
  font-size: 13px;
}

.avatar-upload-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.avatar-upload-row img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.avatar-upload-input {
  display: none;
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

.chat-typing-indicator {
  width: 85%;
  max-width: 900px;
  margin: 0 auto 4px;
  padding: 0 18px;
  color: rgba(var(--v-theme-on-surface), 0.58);
  display: flex;
  align-items: center;
  gap: 2px;
  font-size: 13px;
  line-height: 18px;
}

.typing-dots {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding-left: 1px;
}

.typing-dots span {
  width: 3px;
  height: 3px;
  border-radius: 50%;
  background: currentcolor;
  animation: typing-dot-pulse 1.1s infinite ease-in-out;
}

.typing-dots span:nth-child(2) {
  animation-delay: 0.15s;
}

.typing-dots span:nth-child(3) {
  animation-delay: 0.3s;
}

@keyframes typing-dot-pulse {
  0%,
  70%,
  100% {
    opacity: 0.28;
    transform: translateY(0);
  }

  35% {
    opacity: 1;
    transform: translateY(-2px);
  }
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

@media (max-width: 760px) {
  .chat-main-actions {
    top: 10px;
    right: 10px;
  }

  .messages-panel {
    padding: 18px 14px;
  }

  .messages-list-shell.is-group-chat {
    width: 100%;
    max-width: 100%;
  }

  .composer-shell,
  .project-composer-shell {
    padding: 0;
  }
}
</style>
