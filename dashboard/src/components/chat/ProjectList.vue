<template>
    <div>
        <!-- 项目按钮 -->
        <div style="padding: 0 8px 0px 8px; opacity: 0.6;">
            <v-btn block variant="text" class="project-btn" @click="toggleExpanded" prepend-icon="mdi-folder-outline">
                {{ tm('project.title') }}
                <template v-slot:append>
                    <v-icon size="small">{{ expanded ? 'mdi-chevron-up' : 'mdi-chevron-down' }}</v-icon>
                </template>
            </v-btn>
        </div>

        <!-- 项目列表 -->
        <v-expand-transition>
            <div v-show="expanded" style="padding: 0 8px;">
                <v-list density="compact" nav class="project-list" style="background-color: transparent;">
                    <v-list-item @click="$emit('createProject')" class="create-project-item" rounded="lg">
                        <template v-slot:prepend>
                            <span class="project-emoji"><v-icon size="small">mdi-plus</v-icon></span>
                        </template>
                        <v-list-item-title style="font-size: 13px;">{{ tm('project.create') }}</v-list-item-title>
                    </v-list-item>
                    <v-list-item v-for="project in projects" :key="project.project_id"
                        @click="$emit('selectProject', project.project_id)" rounded="lg" class="project-item">
                        <template v-slot:prepend>
                            <span class="project-emoji">{{ project.emoji || '📁' }}</span>
                        </template>
                        <v-list-item-title class="project-title">{{ project.title }}</v-list-item-title>
                        <template v-slot:append>
                            <div class="project-actions">
                                <v-btn icon="mdi-pencil" size="x-small" variant="text" class="edit-project-btn"
                                    @click.stop="$emit('editProject', project)" />
                                <v-btn icon="mdi-delete" size="x-small" variant="text" class="delete-project-btn"
                                    color="error" @click.stop="handleDeleteProject(project)" />
                            </div>
                        </template>
                    </v-list-item>
                </v-list>
            </div>
        </v-expand-transition>
    </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue';
import { useModuleI18n } from '@/i18n/composables';

export interface Project {
    project_id: string;
    title: string;
    emoji?: string;
    description?: string;
    created_at: string;
    updated_at: string;
}

interface Props {
    projects: Project[];
    initialExpanded?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
    initialExpanded: false
});

const emit = defineEmits<{
    selectProject: [projectId: string];
    createProject: [];
    editProject: [project: Project];
    deleteProject: [projectId: string];
}>();

const { tm } = useModuleI18n('features/chat');

const expanded = ref(props.initialExpanded);

// 从 localStorage 读取项目展开状态
const savedProjectsExpandedState = localStorage.getItem('projectsExpanded');
if (savedProjectsExpandedState !== null) {
    expanded.value = JSON.parse(savedProjectsExpandedState);
}

function toggleExpanded() {
    expanded.value = !expanded.value;
    localStorage.setItem('projectsExpanded', JSON.stringify(expanded.value));
}

function handleDeleteProject(project: Project) {
    const message = tm('project.confirmDelete', { title: project.title });
    if (window.confirm(message)) {
        emit('deleteProject', project.project_id);
    }
}
</script>

<style scoped>
.project-btn {
    justify-content: flex-start;
    background-color: transparent !important;
    border-radius: 20px;
    padding: 8px 16px !important;
    text-transform: none;
}

.project-item {
    border-radius: 16px !important;
    padding: 4px 12px !important;
    margin-bottom: 2px;
}

.project-item:hover {
    background-color: rgba(103, 58, 183, 0.05);
}

.project-item:hover .project-actions {
    opacity: 1;
    visibility: visible;
}

.project-emoji {
    font-size: 16px;
    margin-right: 6px;
}

.project-title {
    font-size: 13px;
    font-weight: 500;
}

.project-actions {
    display: flex;
    gap: 2px;
    opacity: 0;
    visibility: hidden;
    transition: all 0.2s ease;
}

.edit-project-btn,
.delete-project-btn {
    opacity: 0.7;
    transition: opacity 0.2s ease;
}

.edit-project-btn:hover,
.delete-project-btn:hover {
    opacity: 1;
}

.create-project-item {
    border-radius: 16px !important;
    padding: 4px 12px !important;
    opacity: 0.7;
}

.create-project-item:hover {
    background-color: rgba(103, 58, 183, 0.08);
    opacity: 1;
}
</style>
