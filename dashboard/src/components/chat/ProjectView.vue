<template>
    <div class="project-sessions-container fade-in">
        <div class="project-header">
            <div class="project-header-info">
                <span class="project-header-emoji">{{ project?.emoji || '📁' }}</span>
                <h2 class="project-header-title">{{ project?.title }}</h2>
            </div>
            <p class="project-header-description" v-if="project?.description">
                {{ project.description }}
            </p>
        </div>

        <div class="project-input-slot">
            <slot></slot>
        </div>

        <v-card flat class="project-sessions-list">
            <v-list v-if="sessions.length > 0">
                <v-list-item v-for="session in sessions" :key="session.session_id"
                    @click="$emit('selectSession', session.session_id)" class="project-session-item" rounded="lg">
                    <v-list-item-title>
                        {{ session.display_name || tm('conversation.newConversation') }}
                    </v-list-item-title>
                    <v-list-item-subtitle>
                        {{ formatDate(session.updated_at) }}
                    </v-list-item-subtitle>
                    <template v-slot:append>
                        <div class="session-actions">
                            <v-btn icon="mdi-pencil" size="x-small" variant="text"
                                class="edit-session-btn"
                                @click.stop="$emit('editSessionTitle', session.session_id, session.display_name ?? '')" />
                            <v-btn icon="mdi-delete" size="x-small" variant="text"
                                class="delete-session-btn" color="error"
                                @click.stop="handleDeleteSession(session)" />
                        </div>
                    </template>
                </v-list-item>
            </v-list>
            <div v-else class="no-sessions-in-project">
                <v-icon icon="mdi-message-off-outline" size="large" color="grey-lighten-1"></v-icon>
                <p>{{ tm('project.noSessions') }}</p>
            </div>
        </v-card>
    </div>
</template>

<script setup lang="ts">
import { useModuleI18n } from '@/i18n/composables';
import type { Project } from '@/components/chat/ProjectList.vue';

interface Session {
    session_id: string;
    display_name?: string;
    updated_at: string;
}

interface Props {
    project?: Project | null;
    sessions: Session[];
}

defineProps<Props>();

const emit = defineEmits<{
    selectSession: [sessionId: string];
    editSessionTitle: [sessionId: string, title: string];
    deleteSession: [sessionId: string];
}>();

const { tm } = useModuleI18n('features/chat');

function formatDate(dateString: string): string {
    return new Date(dateString).toLocaleString();
}

function handleDeleteSession(session: Session) {
    const sessionTitle = session.display_name || tm('conversation.newConversation');
    const message = tm('conversation.confirmDelete', { name: sessionTitle });
    if (window.confirm(message)) {
        emit('deleteSession', session.session_id);
    }
}
</script>

<style scoped>
.project-sessions-container {
    height: 100%;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 32px;
    overflow-y: auto;
}

.project-header {
    text-align: center;
    margin-bottom: 32px;
    max-width: 600px;
}

.project-header-info {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 12px;
    margin-bottom: 12px;
}

.project-header-emoji {
    font-size: 48px;
}

.project-header-title {
    font-size: 32px;
    font-weight: 600;
}

.project-header-description {
    font-size: 14px;
    color: var(--v-theme-secondaryText);
    margin: 0;
}

.project-input-slot {
    width: 100%;
    max-width: 800px;
    margin-bottom: 24px;
}

.project-sessions-list {
    width: 100%;
    max-width: 680px;
    background-color: transparent !important;
}

.project-session-item {
    margin-bottom: 8px;
    border-radius: 12px !important;
    cursor: pointer;
}

.project-session-item:hover {
    background-color: rgba(103, 58, 183, 0.05);
}

.project-session-item:hover .session-actions {
    opacity: 1;
    visibility: visible;
}

.session-actions {
    display: flex;
    gap: 2px;
    opacity: 1;
}

.no-sessions-in-project {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 48px;
    opacity: 0.6;
}

.no-sessions-in-project p {
    margin-top: 12px;
    font-size: 14px;
}

.fade-in {
    animation: fadeIn 0.3s ease-in-out;
}

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
</style>
