<template>
    <div class="sidebar-panel" 
        :class="{ 
            'sidebar-collapsed': sidebarCollapsed && !isMobile,
            'mobile-sidebar-open': isMobile && mobileMenuOpen,
            'mobile-sidebar': isMobile
        }"
        :style="{ 'background-color': isDark ? sidebarCollapsed ? '#1e1e1e' : '#2d2d2d' : sidebarCollapsed ? '#ffffff' : '#f1f4f9' }">

        <div class="sidebar-collapse-btn-container" v-if="!isMobile">
            <v-btn icon class="sidebar-collapse-btn" @click="toggleSidebar" variant="text" color="deep-purple">
                <v-icon>{{ sidebarCollapsed ? 'mdi-chevron-right' : 'mdi-chevron-left' }}</v-icon>
            </v-btn>
        </div>

        <div class="sidebar-collapse-btn-container" v-if="isMobile">
            <v-btn icon class="sidebar-collapse-btn" @click="$emit('closeMobileSidebar')" variant="text"
                color="deep-purple">
                <v-icon>mdi-close</v-icon>
            </v-btn>
        </div>

        <div style="padding: 8px; opacity: 0.6;">
            <v-btn block variant="text" class="new-chat-btn" @click="$emit('newChat')" :disabled="!currSessionId && !selectedProjectId"
                v-if="!sidebarCollapsed || isMobile" prepend-icon="mdi-square-edit-outline">{{ tm('actions.newChat') }}</v-btn>
            <v-btn icon="mdi-square-edit-outline" rounded="xl" @click="$emit('newChat')" :disabled="!currSessionId && !selectedProjectId" 
                v-if="sidebarCollapsed && !isMobile" elevation="0"></v-btn>
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

        <div style="overflow-y: auto; flex-grow: 1;"
            v-if="!sidebarCollapsed || isMobile">
            <v-card v-if="sessions.length > 0" flat style="background-color: transparent;">
                <v-list density="compact" nav class="conversation-list"
                    style="background-color: transparent;" :selected="selectedSessions"
                    @update:selected="$emit('selectConversation', $event)">
                    <v-list-item v-for="item in sessions" :key="item.session_id" :value="item.session_id"
                        rounded="lg" class="conversation-item" active-color="secondary">
                        <v-list-item-title v-if="!sidebarCollapsed || isMobile" class="conversation-title"
                            :style="{ color: isDark ? '#ffffff' : '#000000' }">
                            {{ item.display_name || tm('conversation.newConversation') }}
                        </v-list-item-title>
                        <!-- <v-list-item-subtitle v-if="!sidebarCollapsed || isMobile" class="timestamp">
                            {{ new Date(item.updated_at).toLocaleString() }}
                        </v-list-item-subtitle> -->

                        <template v-if="!sidebarCollapsed || isMobile" v-slot:append>
                            <div class="conversation-actions">
                                <v-btn icon="mdi-pencil" size="x-small" variant="text"
                                    class="edit-title-btn"
                                    @click.stop="$emit('editTitle', item.session_id, item.display_name ?? '')" />
                                <v-btn icon="mdi-delete" size="x-small" variant="text"
                                    class="delete-conversation-btn" color="error"
                                    @click.stop="handleDeleteConversation(item)" />
                            </div>
                        </template>
                    </v-list-item>
                </v-list>
            </v-card>

            <v-fade-transition>
                <div class="no-conversations" v-if="sessions.length === 0">
                    <v-icon icon="mdi-message-text-outline" size="large" color="grey-lighten-1"></v-icon>
                    <div class="no-conversations-text" v-if="!sidebarCollapsed || isMobile">
                        {{ tm('conversation.noHistory') }}
                    </div>
                </div>
            </v-fade-transition>
        </div>

        <!-- 收起时的占位元素 -->
        <div class="sidebar-spacer" v-if="sidebarCollapsed && !isMobile"></div>

        <!-- 底部设置按钮 -->
        <div class="sidebar-footer">
            <StyledMenu location="top" :close-on-content-click="false">
                <template v-slot:activator="{ props: menuProps }">
                    <v-btn 
                        v-bind="menuProps"
                        :icon="sidebarCollapsed && !isMobile"
                        :block="!sidebarCollapsed || isMobile"
                        variant="text" 
                        class="settings-btn"
                        :class="{ 'settings-btn-collapsed': sidebarCollapsed && !isMobile }"
                        :prepend-icon="(!sidebarCollapsed || isMobile) ? 'mdi-cog-outline' : undefined"
                    >
                        <v-icon v-if="sidebarCollapsed && !isMobile">mdi-cog-outline</v-icon>
                        <template v-if="!sidebarCollapsed || isMobile">{{ t('core.common.settings') }}</template>
                    </v-btn>
                </template>
                
                <!-- 语言切换 -->
                <v-list-item class="styled-menu-item">
                    <template v-slot:prepend>
                        <v-icon>mdi-translate</v-icon>
                    </template>
                    <v-list-item-title>{{ t('core.common.language') }}</v-list-item-title>
                    <template v-slot:append>
                        <LanguageSwitcher variant="chatbox" />
                    </template>
                </v-list-item>
                
                <!-- 主题切换 -->
                <v-list-item class="styled-menu-item" @click="$emit('toggleTheme')">
                    <template v-slot:prepend>
                        <v-icon>{{ isDark ? 'mdi-weather-night' : 'mdi-white-balance-sunny' }}</v-icon>
                    </template>
                    <v-list-item-title>{{ isDark ? tm('modes.lightMode') : tm('modes.darkMode') }}</v-list-item-title>
                </v-list-item>

                <!-- 全屏/退出全屏 -->
                <v-list-item class="styled-menu-item" @click="$emit('toggleFullscreen')">
                    <template v-slot:prepend>
                        <v-icon>{{ chatboxMode ? 'mdi-fullscreen-exit' : 'mdi-fullscreen' }}</v-icon>
                    </template>
                    <v-list-item-title>{{ chatboxMode ? tm('actions.exitFullscreen') : tm('actions.fullscreen') }}</v-list-item-title>
                </v-list-item>

                <!-- 提供商配置 -->
                <v-list-item class="styled-menu-item" @click="showProviderConfigDialog = true">
                    <template v-slot:prepend>
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
import { ref } from 'vue';
import { useI18n, useModuleI18n } from '@/i18n/composables';
import type { Session } from '@/composables/useSessions';
import LanguageSwitcher from '@/components/shared/LanguageSwitcher.vue';
import StyledMenu from '@/components/shared/StyledMenu.vue';
import ProviderConfigDialog from '@/components/chat/ProviderConfigDialog.vue';
import ProjectList from '@/components/chat/ProjectList.vue';
import type { Project } from '@/components/chat/ProjectList.vue';

interface Props {
    sessions: Session[];
    selectedSessions: string[];
    currSessionId: string;
    selectedProjectId?: string | null;
    isDark: boolean;
    chatboxMode: boolean;
    isMobile: boolean;
    mobileMenuOpen: boolean;
    projects?: Project[];
}

const props = withDefaults(defineProps<Props>(), {
    projects: () => []
});

const emit = defineEmits<{
    newChat: [];
    selectConversation: [sessionIds: string[]];
    editTitle: [sessionId: string, title: string];
    deleteConversation: [sessionId: string];
    closeMobileSidebar: [];
    toggleTheme: [];
    toggleFullscreen: [];
    selectProject: [projectId: string];
    createProject: [];
    editProject: [project: Project];
    deleteProject: [projectId: string];
}>();

const { t } = useI18n();
const { tm } = useModuleI18n('features/chat');

const sidebarCollapsed = ref(true);
const showProviderConfigDialog = ref(false);

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

function handleDeleteConversation(session: Session) {
    const sessionTitle = session.display_name || tm('conversation.newConversation');
    const message = tm('conversation.confirmDelete', { name: sessionTitle });
    if (window.confirm(message)) {
        emit('deleteConversation', session.session_id);
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
    background-color: rgba(103, 58, 183, 0.05);
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
</style>

