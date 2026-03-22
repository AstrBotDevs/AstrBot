<template>
  <div
    class="sidebar-panel" 
    :class="{ 
      'sidebar-collapsed': sidebarCollapsed && !isMobile,
      'mobile-sidebar-open': isMobile && mobileMenuOpen,
      'mobile-sidebar': isMobile
    }"
    :style="{ backgroundColor: sidebarCollapsed && !isMobile ? 'rgb(var(--v-theme-surface))' : 'rgb(var(--v-theme-mcpCardBg))' }"
  >
    <div
      v-if="!isMobile"
      class="sidebar-collapse-btn-container"
    >
      <v-btn
        icon
        class="sidebar-collapse-btn"
        variant="text"
        color="deep-purple"
        @click="toggleSidebar"
      >
        <v-icon>{{ sidebarCollapsed ? 'mdi-chevron-right' : 'mdi-chevron-left' }}</v-icon>
      </v-btn>
    </div>

    <div
      v-if="isMobile"
      class="sidebar-collapse-btn-container"
    >
      <v-btn
        icon
        class="sidebar-collapse-btn"
        variant="text"
        color="deep-purple"
        @click="$emit('closeMobileSidebar')"
      >
        <v-icon>mdi-close</v-icon>
      </v-btn>
    </div>

    <div style="padding: 8px; opacity: 0.6;">
      <div
        v-if="!sidebarCollapsed || isMobile"
        class="new-chat-row"
      >
        <v-btn
          block
          variant="text"
          class="new-chat-btn"
          :disabled="!currSessionId && !selectedProjectId"
          prepend-icon="mdi-square-edit-outline"
          @click="$emit('newChat')"
        >
          {{ tm('actions.newChat') }}
        </v-btn>
        <v-btn
          v-if="sessions.length > 0"
          icon
          size="small"
          variant="text"
          :color="batchMode ? 'primary' : undefined"
          @click="toggleBatchMode"
        >
          <v-icon>mdi-checkbox-multiple-marked-outline</v-icon>
        </v-btn>
      </div>
      <v-btn
        v-if="sidebarCollapsed && !isMobile"
        icon="mdi-square-edit-outline"
        rounded="xl"
        :disabled="!currSessionId && !selectedProjectId"
        elevation="0"
        @click="$emit('newChat')"
      />
    </div>

    <!-- Batch action bar -->
    <div
      v-if="batchMode && (!sidebarCollapsed || isMobile)"
      class="batch-action-bar"
    >
      <v-btn
        size="x-small"
        variant="text"
        @click="toggleSelectAll"
      >
        {{ isAllSelected ? tm('batch.deselectAll') : tm('batch.selectAll') }}
      </v-btn>
      <span class="batch-selected-count">{{ tm('batch.selected', { count: batchSelected.length }) }}</span>
      <v-spacer />
      <v-btn
        size="x-small"
        variant="text"
        color="error"
        :disabled="batchSelected.length === 0"
        @click="handleBatchDelete"
      >
        {{ tm('batch.delete') }}
      </v-btn>
    </div>

    <!-- 项目列表组件 -->
    <ProjectList
      v-if="!sidebarCollapsed || isMobile"
      :projects="projects"
      @selectProject="$emit('selectProject', $event)"
      @createProject="$emit('createProject')"
      @editProject="$emit('editProject', $event)"
      @deleteProject="$emit('deleteProject', $event)"
    />

    <div
      v-if="!sidebarCollapsed || isMobile"
      style="overflow-y: auto; flex-grow: 1; overscroll-behavior-y: contain;"
    >
      <v-card
        v-if="sessions.length > 0"
        flat
        style="background-color: transparent;"
      >
        <v-list
          density="compact"
          nav
          class="conversation-list"
          style="background-color: transparent;"
          :selected="batchMode ? [] : selectedSessions"
          @update:selected="handleListSelect"
        >
          <v-list-item
            v-for="item in sessions"
            :key="item.session_id"
            :value="item.session_id"
            rounded="lg"
            class="conversation-item"
            active-color="secondary"
            @click="batchMode ? toggleBatchItem(item.session_id) : undefined"
          >
            <template #prepend>
              <div
                class="batch-checkbox-slot"
                :class="{ 'batch-checkbox-slot--active': batchMode }"
              >
                <v-checkbox-btn
                  :model-value="batchSelected.includes(item.session_id)"
                  density="compact"
                  hide-details
                  class="batch-checkbox"
                  @update:model-value="toggleBatchItem(item.session_id)"
                  @click.stop
                />
              </div>
            </template>

            <v-list-item-title
              v-if="!sidebarCollapsed || isMobile"
              class="conversation-title"
              :style="{ color: 'rgb(var(--v-theme-primaryText))' }"
            >
              {{ item.display_name || tm('conversation.newConversation') }}
            </v-list-item-title>
            <!-- <v-list-item-subtitle v-if="!sidebarCollapsed || isMobile" class="timestamp">
                            {{ new Date(item.updated_at).toLocaleString() }}
                        </v-list-item-subtitle> -->

            <template
              v-if="!batchMode && (!sidebarCollapsed || isMobile)"
              #append
            >
              <div class="conversation-actions">
                <v-btn
                  icon="mdi-pencil"
                  size="x-small"
                  variant="text"
                  class="edit-title-btn"
                  @click.stop="$emit('editTitle', item.session_id, item.display_name ?? '')"
                />
                <v-btn
                  icon="mdi-delete"
                  size="x-small"
                  variant="text"
                  class="delete-conversation-btn"
                  color="error"
                  @click.stop="handleDeleteConversation(item)"
                />
              </div>
            </template>
          </v-list-item>
        </v-list>
      </v-card>

      <v-fade-transition>
        <div
          v-if="sessions.length === 0"
          class="no-conversations"
        >
          <v-icon
            icon="mdi-message-text-outline"
            size="large"
            color="grey-lighten-1"
          />
          <div
            v-if="!sidebarCollapsed || isMobile"
            class="no-conversations-text"
          >
            {{ tm('conversation.noHistory') }}
          </div>
        </div>
      </v-fade-transition>
    </div>

    <!-- 收起时的占位元素 -->
    <div
      v-if="sidebarCollapsed && !isMobile"
      class="sidebar-spacer"
    />

    <!-- 底部设置按钮 -->
    <div class="sidebar-footer">
      <StyledMenu
        location="top"
        :close-on-content-click="false"
      >
        <template #activator="{ props: menuProps }">
          <v-btn 
            v-bind="menuProps"
            :icon="sidebarCollapsed && !isMobile"
            :block="!sidebarCollapsed || isMobile"
            variant="text" 
            class="settings-btn"
            :class="{ 'settings-btn-collapsed': sidebarCollapsed && !isMobile }"
            :prepend-icon="(!sidebarCollapsed || isMobile) ? 'mdi-cog-outline' : undefined"
          >
            <v-icon v-if="sidebarCollapsed && !isMobile">
              mdi-cog-outline
            </v-icon>
            <template v-if="!sidebarCollapsed || isMobile">
              {{ t('core.common.settings') }}
            </template>
          </v-btn>
        </template>
                
        <!-- 语言切换（分组） -->
        <v-menu
          :open-on-hover="!isMobile"
          :open-on-click="isMobile"
          :open-delay="!isMobile ? 60 : 0"
          :close-delay="!isMobile ? 120 : 0"
          :location="isMobile ? 'bottom' : 'end center'"
          offset="8"
          close-on-content-click
        >
          <template #activator="{ props: languageMenuProps }">
            <v-list-item
              v-bind="languageMenuProps"
              class="styled-menu-item chat-settings-group-trigger"
              rounded="md"
            >
              <template #prepend>
                <v-icon>mdi-translate</v-icon>
              </template>
              <v-list-item-title>{{ t('core.common.language') }}</v-list-item-title>
              <template #append>
                <span class="chat-settings-group-current">{{ currentLanguage?.flag }}</span>
                <v-icon
                  size="18"
                  class="chat-settings-group-arrow"
                >
                  mdi-chevron-right
                </v-icon>
              </template>
            </v-list-item>
          </template>

          <v-card
            class="styled-menu-card"
            style="min-width: 180px;"
            elevation="8"
            rounded="lg"
          >
            <v-list
              density="compact"
              class="styled-menu-list pa-1"
            >
              <v-list-item
                v-for="lang in languages"
                :key="lang.code"
                :value="lang.code"
                :class="{ 'styled-menu-item-active': currentLocale === lang.code }"
                class="styled-menu-item"
                rounded="md"
                @click="changeLanguage(lang.code)"
              >
                <template #prepend>
                  <span class="language-flag">{{ lang.flag }}</span>
                </template>
                <v-list-item-title>{{ lang.name }}</v-list-item-title>
              </v-list-item>
            </v-list>
          </v-card>
        </v-menu>
                
        <!-- 主题切换 -->
        <v-list-item
          class="styled-menu-item"
          @click="$emit('toggleTheme')"
        >
          <template #prepend>
            <v-icon>{{ isDark ? 'mdi-weather-night' : 'mdi-white-balance-sunny' }}</v-icon>
          </template>
          <v-list-item-title>{{ isDark ? tm('modes.lightMode') : tm('modes.darkMode') }}</v-list-item-title>
        </v-list-item>

        <!-- 通信传输模式（分组） -->
        <v-menu
          :open-on-hover="!isMobile"
          :open-on-click="isMobile"
          :open-delay="!isMobile ? 60 : 0"
          :close-delay="!isMobile ? 120 : 0"
          :location="isMobile ? 'bottom' : 'end center'"
          offset="8"
          close-on-content-click
        >
          <template #activator="{ props: transportMenuProps }">
            <v-list-item
              v-bind="transportMenuProps"
              class="styled-menu-item chat-settings-group-trigger"
              rounded="md"
            >
              <template #prepend>
                <v-icon>mdi-lan-connect</v-icon>
              </template>
              <v-list-item-title>{{ tm('transport.title') }}</v-list-item-title>
              <template #append>
                <span class="chat-settings-group-current chat-settings-transport-current">{{ currentTransportLabel }}</span>
                <v-icon
                  size="18"
                  class="chat-settings-group-arrow"
                >
                  mdi-chevron-right
                </v-icon>
              </template>
            </v-list-item>
          </template>

          <v-card
            class="styled-menu-card"
            style="min-width: 220px;"
            elevation="8"
            rounded="lg"
          >
            <v-list
              density="compact"
              class="styled-menu-list pa-1"
            >
              <v-list-item
                v-for="opt in transportOptions"
                :key="opt.value"
                :value="opt.value"
                :class="{ 'styled-menu-item-active': transportMode === opt.value }"
                class="styled-menu-item"
                rounded="md"
                @click="handleTransportModeChange(opt.value)"
              >
                <v-list-item-title>{{ opt.label }}</v-list-item-title>
              </v-list-item>
            </v-list>
          </v-card>
        </v-menu>

        <!-- 发送快捷键（分组） -->
        <v-menu
          :open-on-hover="!isMobile"
          :open-on-click="isMobile"
          :open-delay="!isMobile ? 60 : 0"
          :close-delay="!isMobile ? 120 : 0"
          :location="isMobile ? 'bottom' : 'end center'"
          offset="8"
          close-on-content-click
        >
          <template #activator="{ props: sendShortcutMenuProps }">
            <v-list-item
              v-bind="sendShortcutMenuProps"
              class="styled-menu-item chat-settings-group-trigger"
              rounded="md"
            >
              <template #prepend>
                <v-icon>mdi-keyboard-outline</v-icon>
              </template>
              <v-list-item-title>{{ tm('shortcuts.sendKey.title') }}</v-list-item-title>
              <template #append>
                <span class="chat-settings-group-current chat-settings-transport-current">{{ currentSendShortcutLabel }}</span>
                <v-icon
                  size="18"
                  class="chat-settings-group-arrow"
                >
                  mdi-chevron-right
                </v-icon>
              </template>
            </v-list-item>
          </template>

          <v-card
            class="styled-menu-card"
            style="min-width: 220px;"
            elevation="8"
            rounded="lg"
          >
            <v-list
              density="compact"
              class="styled-menu-list pa-1"
            >
              <v-list-item
                v-for="opt in sendShortcutOptions"
                :key="opt.value"
                :value="opt.value"
                :class="{ 'styled-menu-item-active': props.sendShortcut === opt.value }"
                class="styled-menu-item"
                rounded="md"
                @click="handleSendShortcutChange(opt.value)"
              >
                <v-list-item-title>{{ opt.label }}</v-list-item-title>
              </v-list-item>
            </v-list>
          </v-card>
        </v-menu>

        <!-- 全屏/退出全屏 -->
        <v-list-item
          class="styled-menu-item"
          @click="$emit('toggleFullscreen')"
        >
          <template #prepend>
            <v-icon>{{ chatboxMode ? 'mdi-fullscreen-exit' : 'mdi-fullscreen' }}</v-icon>
          </template>
          <v-list-item-title>{{ chatboxMode ? tm('actions.exitFullscreen') : tm('actions.fullscreen') }}</v-list-item-title>
        </v-list-item>

        <!-- 提供商配置 -->
        <v-list-item
          class="styled-menu-item"
          @click="showProviderConfigDialog = true"
        >
          <template #prepend>
            <v-icon>mdi-creation</v-icon>
          </template>
          <v-list-item-title>{{ tm('actions.providerConfig') }}</v-list-item-title>
        </v-list-item>
      </StyledMenu>
    </div>

    <!-- 提供商配置对话框 -->
    <ProviderConfigDialog v-model="showProviderConfigDialog" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import { useI18n, useModuleI18n } from '@/i18n/composables';
import type { Session } from '@/composables/useSessions';
import { askForConfirmation, useConfirmDialog } from '@/utils/confirmDialog';
import StyledMenu from '@/components/shared/StyledMenu.vue';
import ProviderConfigDialog from '@/components/chat/ProviderConfigDialog.vue';
import ProjectList from '@/components/chat/ProjectList.vue';
import type { Project } from '@/components/chat/ProjectList.vue';
import { useLanguageSwitcher } from '@/i18n/composables';
import type { Locale } from '@/i18n/types';

interface Props {
    sessions: Session[];
    selectedSessions: string[];
    currSessionId: string;
    selectedProjectId?: string | null;
    transportMode: 'sse' | 'websocket';
    isDark: boolean;
    chatboxMode: boolean;
    isMobile: boolean;
    mobileMenuOpen: boolean;
    projects?: Project[];
    sendShortcut: 'enter' | 'shift_enter';
}

const props = withDefaults(defineProps<Props>(), {
    projects: () => []
});

const emit = defineEmits<{
    newChat: [];
    selectConversation: [sessionIds: string[]];
    editTitle: [sessionId: string, title: string];
    deleteConversation: [sessionId: string];
    batchDeleteConversations: [sessionIds: string[]];
    closeMobileSidebar: [];
    toggleTheme: [];
    toggleFullscreen: [];
    selectProject: [projectId: string];
    createProject: [];
    editProject: [project: Project];
    deleteProject: [projectId: string];
    updateTransportMode: [mode: 'sse' | 'websocket'];
    updateSendShortcut: [mode: 'enter' | 'shift_enter'];
}>();

const { t } = useI18n();
const { tm } = useModuleI18n('features/chat');

const confirmDialog = useConfirmDialog();

const sidebarCollapsed = ref(true);
const showProviderConfigDialog = ref(false);

// Batch mode state
const batchMode = ref(false);
const batchSelected = ref<string[]>([]);

const isAllSelected = computed(() =>
    props.sessions.length > 0 && batchSelected.value.length === props.sessions.length
);

function toggleBatchMode() {
    batchMode.value = !batchMode.value;
    batchSelected.value = [];
}

function toggleBatchItem(sessionId: string) {
    const idx = batchSelected.value.indexOf(sessionId);
    if (idx >= 0) {
        batchSelected.value.splice(idx, 1);
    } else {
        batchSelected.value.push(sessionId);
    }
}

function toggleSelectAll() {
    if (isAllSelected.value) {
        batchSelected.value = [];
    } else {
        batchSelected.value = props.sessions.map(s => s.session_id);
    }
}

async function handleBatchDelete() {
    const count = batchSelected.value.length;
    if (count === 0) return;
    const message = tm('batch.confirmDelete', { count });
    if (await askForConfirmation(message, confirmDialog)) {
        emit('batchDeleteConversations', [...batchSelected.value]);
        batchSelected.value = [];
        batchMode.value = false;
    }
}

function handleListSelect(sessionIds: string[]) {
    if (!batchMode.value) {
        emit('selectConversation', sessionIds);
    }
}
const transportOptions = [
    { label: tm('transport.sse'), value: 'sse' as const },
    { label: tm('transport.websocket'), value: 'websocket' as const }
];
const sendShortcutOptions = [
    { label: tm('shortcuts.sendKey.enterToSend'), value: 'enter' as const },
    { label: tm('shortcuts.sendKey.shiftEnterToSend'), value: 'shift_enter' as const }
];

// Language switcher
const { languageOptions, currentLanguage, switchLanguage, locale } = useLanguageSwitcher();
const languages = computed(() =>
    languageOptions.value.map(lang => ({
        code: lang.value,
        name: lang.label,
        flag: lang.flag
    }))
);
const currentLocale = computed(() => locale.value);
const changeLanguage = async (langCode: string) => {
    await switchLanguage(langCode as Locale);
};

const currentTransportLabel = computed(() => {
    const found = transportOptions.find(opt => opt.value === props.transportMode);
    return found?.label ?? '';
});
const currentSendShortcutLabel = computed(() => {
    const found = sendShortcutOptions.find(opt => opt.value === props.sendShortcut);
    return found?.label ?? '';
});

// 从 localStorage 读取侧边栏折叠状态
const savedCollapsedState = localStorage.getItem('sidebarCollapsed');
if (savedCollapsedState !== null) {
    sidebarCollapsed.value = JSON.parse(savedCollapsedState);
} else {
    sidebarCollapsed.value = true;
}

function toggleSidebar() {
    sidebarCollapsed.value = !sidebarCollapsed.value;
    localStorage.setItem('sidebarCollapsed', JSON.stringify(sidebarCollapsed.value));
}

async function handleDeleteConversation(session: Session) {
    const sessionTitle = session.display_name || tm('conversation.newConversation');
    const message = tm('conversation.confirmDelete', { name: sessionTitle });
    if (await askForConfirmation(message, confirmDialog)) {
        emit('deleteConversation', session.session_id);
    }
}

function handleTransportModeChange(mode: string | null) {
    if (mode === 'sse' || mode === 'websocket') {
        emit('updateTransportMode', mode);
    }
}

function handleSendShortcutChange(mode: string | null) {
    if (mode === 'enter' || mode === 'shift_enter') {
        emit('updateSendShortcut', mode);
    }
}
</script>

<style scoped>
.sidebar-panel {
    max-width: 270px;
    min-width: 240px;
    display: flex;
    flex-direction: column;
    padding: 0;
    height: 100%;
    max-height: 100%;
    position: relative;
    transition: all 0.3s ease;
    overflow: hidden;
}

.sidebar-collapsed {
    max-width: 60px;
    min-width: 60px;
    transition: all 0.3s ease;
}

.mobile-sidebar {
    position: fixed;
    top: 0;
    left: 0;
    bottom: 0;
    max-width: 280px !important;
    min-width: 280px !important;
    transform: translateX(-100%);
    transition: transform 0.3s ease;
    z-index: 1000;
}

.mobile-sidebar-open {
    transform: translateX(0) !important;
}

.sidebar-collapse-btn-container {
    margin: 8px;
    margin-bottom: 0px;
    z-index: 10;
}

.sidebar-collapse-btn {
    opacity: 0.6;
    max-height: none;
    overflow-y: visible;
    padding: 0;
}

.new-chat-btn {
    justify-content: flex-start;
    background-color: transparent !important;
    border-radius: 20px;
    padding: 8px 16px !important;
}

.conversation-item {
    /* margin-bottom: 4px; */
    border-radius: 20px !important;
    height: auto !important;
    /* min-height: 56px; */
    padding: 0px 16px !important;
    position: relative;
}

.conversation-item:hover {
    background-color: rgba(var(--v-theme-primary), 0.05);
}

.conversation-item:hover .conversation-actions {
    opacity: 1;
    visibility: visible;
}

.conversation-actions {
    display: flex;
    gap: 4px;
    opacity: 0;
    visibility: hidden;
    transition: all 0.2s ease;
}

@media (max-width: 768px) {
    .conversation-actions {
        opacity: 1 !important;
        visibility: visible !important;
    }
}

.edit-title-btn,
.delete-conversation-btn {
    opacity: 0.7;
    transition: opacity 0.2s ease;
}

.edit-title-btn:hover,
.delete-conversation-btn:hover {
    opacity: 1;
}

.conversation-title {
    font-weight: 500;
    font-size: 14px;
    line-height: 1.3;
    margin-bottom: 2px;
    transition: opacity 0.25s ease;
}

.timestamp {
    font-size: 11px;
    color: var(--v-theme-secondaryText);
    line-height: 1;
    transition: opacity 0.25s ease;
}

.no-conversations {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 150px;
    opacity: 0.6;
    gap: 12px;
}

.no-conversations-text {
    font-size: 14px;
    color: var(--v-theme-secondaryText);
    transition: opacity 0.25s ease;
}

.sidebar-spacer {
    flex-grow: 1;
}

.sidebar-footer {
    padding: 8px 8px;
    padding-bottom: 16px;
    flex-shrink: 0;
}

.settings-btn {
    opacity: 0.6;
    justify-content: flex-start;
    padding: 8px 16px !important;
    border-radius: 20px !important;
}

.settings-btn:hover {
    opacity: 1;
}

.settings-btn-collapsed {
    width: 100%;
    display: flex;
    justify-content: center;
}

.chat-settings-group-trigger :deep(.v-list-item__append) {
    display: flex;
    align-items: center;
    gap: 6px;
}

.chat-settings-group-current {
    font-size: 14px;
    line-height: 1;
    opacity: 0.8;
}

.chat-settings-transport-current {
    font-size: 12px;
}

.chat-settings-group-arrow {
    opacity: 0.7;
}

.language-flag {
    font-size: 16px;
    margin-right: 8px;
}

.new-chat-row {
    display: flex;
    align-items: center;
    gap: 4px;
}

.new-chat-row .new-chat-btn {
    flex: 1;
    min-width: 0;
}

.batch-action-bar {
    display: flex;
    align-items: center;
    padding: 4px 12px;
    gap: 4px;
    flex-shrink: 0;
}

.batch-selected-count {
    font-size: 12px;
    opacity: 0.7;
    white-space: nowrap;
}

.batch-checkbox {
    flex: none;
    transition: opacity 0.2s ease, transform 0.2s ease;
}

.batch-checkbox-slot {
    width: 0;
    opacity: 0;
    overflow: hidden;
    pointer-events: none;
    transform: translateX(-8px);
    transition: width 0.2s ease, opacity 0.2s ease, transform 0.2s ease;
}

.batch-checkbox-slot--active {
    width: 28px;
    opacity: 1;
    pointer-events: auto;
    transform: translateX(0);
}
</style>
