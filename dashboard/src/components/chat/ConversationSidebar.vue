<template>
    <div class="sidebar-panel" 
        :class="{ 
            'sidebar-collapsed': sidebarCollapsed && !isMobile,
            'mobile-sidebar-open': isMobile && mobileMenuOpen,
            'mobile-sidebar': isMobile
        }"
        :style="{ 'background-color': isDark ? sidebarCollapsed ? '#1e1e1e' : '#2d2d2d' : sidebarCollapsed ? '#ffffff' : '#f1f4f9' }"
        @mouseenter="handleSidebarMouseEnter" 
        @mouseleave="handleSidebarMouseLeave">

        <div style="display: flex; align-items: center; justify-content: center; padding: 16px; padding-bottom: 0px;"
            v-if="chatboxMode">
            <img width="50" src="@/assets/images/icon-no-shadow.svg" alt="AstrBot Logo">
            <span v-if="!sidebarCollapsed"
                style="font-weight: 1000; font-size: 26px; margin-left: 8px;">AstrBot</span>
        </div>

        <div class="sidebar-collapse-btn-container" v-if="!isMobile">
            <v-btn icon class="sidebar-collapse-btn" @click="toggleSidebar" variant="text" color="deep-purple">
                <v-icon>{{ (sidebarCollapsed || (!sidebarCollapsed && sidebarHoverExpanded)) ?
                    'mdi-chevron-right' : 'mdi-chevron-left' }}</v-icon>
            </v-btn>
        </div>

        <div class="sidebar-collapse-btn-container" v-if="isMobile">
            <v-btn icon class="sidebar-collapse-btn" @click="$emit('closeMobileSidebar')" variant="text"
                color="deep-purple">
                <v-icon>mdi-close</v-icon>
            </v-btn>
        </div>

        <div style="padding: 16px; padding-top: 8px;">
            <v-btn block variant="text" class="new-chat-btn" @click="$emit('newChat')" :disabled="!currSessionId"
                v-if="!sidebarCollapsed || isMobile" prepend-icon="mdi-plus"
                style="background-color: transparent !important; border-radius: 4px;">{{ tm('actions.newChat') }}</v-btn>
            <v-btn icon="mdi-plus" rounded="lg" @click="$emit('newChat')" :disabled="!currSessionId" 
                v-if="sidebarCollapsed && !isMobile" elevation="0"></v-btn>
        </div>
        
        <div v-if="!sidebarCollapsed || isMobile">
            <v-divider class="mx-4"></v-divider>
        </div>

        <div style="overflow-y: auto; flex-grow: 1;" :class="{ 'fade-in': sidebarHoverExpanded }"
            v-if="!sidebarCollapsed || isMobile">
            <v-card v-if="sessions.length > 0" flat style="background-color: transparent;">
                <v-list density="compact" nav class="conversation-list"
                    style="background-color: transparent;" :selected="selectedSessions"
                    @update:selected="$emit('selectConversation', $event)">
                    <v-list-item v-for="item in sessions" :key="item.session_id" :value="item.session_id"
                        rounded="lg" class="conversation-item" active-color="secondary">
                        <v-list-item-title v-if="!sidebarCollapsed || isMobile" class="conversation-title">
                            {{ item.display_name || tm('conversation.newConversation') }}
                        </v-list-item-title>
                        <v-list-item-subtitle v-if="!sidebarCollapsed || isMobile" class="timestamp">
                            {{ new Date(item.updated_at).toLocaleString() }}
                        </v-list-item-subtitle>

                        <template v-if="!sidebarCollapsed || isMobile" v-slot:append>
                            <div class="conversation-actions">
                                <v-btn icon="mdi-pencil" size="x-small" variant="text"
                                    class="edit-title-btn"
                                    @click.stop="$emit('editTitle', item.session_id, item.display_name)" />
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
                    <div class="no-conversations-text" v-if="!sidebarCollapsed || sidebarHoverExpanded || isMobile">
                        {{ tm('conversation.noHistory') }}
                    </div>
                </div>
            </v-fade-transition>
        </div>
    </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useModuleI18n } from '@/i18n/composables';
import type { Session } from '@/composables/useSessions';

interface Props {
    sessions: Session[];
    selectedSessions: string[];
    currSessionId: string;
    isDark: boolean;
    chatboxMode: boolean;
    isMobile: boolean;
    mobileMenuOpen: boolean;
}

const props = defineProps<Props>();

const emit = defineEmits<{
    newChat: [];
    selectConversation: [sessionIds: string[]];
    editTitle: [sessionId: string, title: string];
    deleteConversation: [sessionId: string];
    closeMobileSidebar: [];
}>();

const { tm } = useModuleI18n('features/chat');

const sidebarCollapsed = ref(true);
const sidebarHovered = ref(false);
const sidebarHoverTimer = ref<number | null>(null);
const sidebarHoverExpanded = ref(false);
const sidebarHoverDelay = 100;

// 从 localStorage 读取侧边栏折叠状态
const savedCollapsedState = localStorage.getItem('sidebarCollapsed');
if (savedCollapsedState !== null) {
    sidebarCollapsed.value = JSON.parse(savedCollapsedState);
} else {
    sidebarCollapsed.value = true;
}

function toggleSidebar() {
    if (sidebarHoverExpanded.value) {
        sidebarHoverExpanded.value = false;
        return;
    }
    sidebarCollapsed.value = !sidebarCollapsed.value;
    localStorage.setItem('sidebarCollapsed', JSON.stringify(sidebarCollapsed.value));
}

function handleSidebarMouseEnter() {
    if (!sidebarCollapsed.value || props.isMobile) return;

    sidebarHovered.value = true;
    sidebarHoverTimer.value = window.setTimeout(() => {
        if (sidebarHovered.value) {
            sidebarHoverExpanded.value = true;
            sidebarCollapsed.value = false;
        }
    }, sidebarHoverDelay);
}

function handleSidebarMouseLeave() {
    sidebarHovered.value = false;

    if (sidebarHoverTimer.value) {
        clearTimeout(sidebarHoverTimer.value);
        sidebarHoverTimer.value = null;
    }

    if (sidebarHoverExpanded.value) {
        sidebarCollapsed.value = true;
    }
    sidebarHoverExpanded.value = false;
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
    border-right: 1px solid rgba(0, 0, 0, 0.04);
    height: 100%;
    max-height: 100%;
    position: relative;
    transition: all 0.3s ease;
    overflow: hidden;
}

.sidebar-collapsed {
    max-width: 75px;
    min-width: 75px;
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
    margin: 16px;
    margin-bottom: 0px;
    z-index: 10;
}

.sidebar-collapse-btn {
    opacity: 0.6;
    max-height: none;
    overflow-y: visible;
    padding: 0;
}

.conversation-item {
    margin-bottom: 4px;
    border-radius: 8px !important;
    transition: all 0.2s ease;
    height: auto !important;
    min-height: 56px;
    padding: 8px 16px !important;
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

.fade-in {
    animation: fadeInContent 0.3s ease;
}

@keyframes fadeInContent {
    from {
        opacity: 0;
    }
    to {
        opacity: 1;
    }
}
</style>

