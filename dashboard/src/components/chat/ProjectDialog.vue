<template>
    <v-dialog v-model="isOpen" max-width="560" @update:model-value="handleDialogChange">
        <v-card>
            <v-card-title class="text-h3 pa-4 pb-0 pl-6">
                {{ isEditing ? tm('project.edit') : tm('project.create') }}
            </v-card-title>
            <v-card-text>
                <div class="project-name-row">
                    <EmojiPicker v-model="form.emoji" />
                    <input
                        v-model="form.title"
                        class="project-input project-name-input"
                        type="text"
                        :placeholder="tm('project.name')"
                        :aria-label="tm('project.name')"
                        autofocus
                        @keyup.enter="handleSave"
                    />
                </div>
                <v-select v-model="form.workspace_type" :items="workspaceTypeItems" item-title="label" item-value="value"
                    :label="tm('project.workspace.type')" variant="outlined" hide-details class="mb-3" />
                <div v-if="form.workspace_type === 'custom'" class="workspace-path-row">
                    <input
                        v-model="form.workspace_path"
                        class="project-input workspace-path-input"
                        type="text"
                        :placeholder="tm('project.workspace.path')"
                        :aria-label="tm('project.workspace.path')"
                    />
                    <button
                        v-if="canPickWorkspaceDirectory"
                        type="button"
                        class="folder-picker-button"
                        :aria-label="tm('project.workspace.selectPath')"
                        :disabled="props.saving"
                        @click.stop="handlePickWorkspaceDirectory"
                    >
                        <v-icon size="20">mdi-folder-open-outline</v-icon>
                        <span>{{ tm('project.workspace.selectPath') }}</span>
                    </button>
                </div>
                <div class="more-settings">
                    <span
                        class="more-settings-toggle"
                        role="button"
                        tabindex="0"
                        :aria-expanded="moreSettingsOpen"
                        @click="moreSettingsOpen = !moreSettingsOpen"
                        @keydown.enter.prevent="moreSettingsOpen = !moreSettingsOpen"
                    >
                        <span>{{ tm('project.moreSettings') }}</span>
                        <v-icon
                            size="20"
                            class="more-settings-chevron"
                            :class="{ 'is-open': moreSettingsOpen }"
                            aria-hidden="true"
                        >mdi-chevron-down</v-icon>
                    </span>
                    <div v-if="moreSettingsOpen" class="more-settings-content">
                        <textarea
                            v-model="form.description"
                            class="project-input project-description-input"
                            :placeholder="tm('project.description')"
                            :aria-label="tm('project.description')"
                            rows="3"
                        />
                    </div>
                </div>
                <v-alert
                    v-if="props.errorMessage"
                    class="mt-3"
                    type="error"
                    variant="tonal"
                    density="compact"
                >
                    {{ props.errorMessage }}
                </v-alert>
            </v-card-text>
            <v-card-actions>
                <v-spacer></v-spacer>
                <v-btn variant="text" @click="handleCancel" color="grey-darken-1" :disabled="props.saving">{{ t('core.common.cancel') }}</v-btn>
                <v-btn variant="text" @click="handleSave" color="primary" :disabled="!canSave || props.saving" :loading="props.saving">{{ t('core.common.save') }}</v-btn>
            </v-card-actions>
        </v-card>
    </v-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useI18n, useModuleI18n } from '@/i18n/composables';
import { getDesktopRuntimeInfo } from '@/utils/desktopRuntime';
import EmojiPicker from '@/components/shared/EmojiPicker.vue';

export type WorkspaceType = 'session' | 'project' | 'custom';

export interface Project {
    project_id: string;
    title: string;
    emoji?: string;
    description?: string;
    workspace_type?: WorkspaceType;
    workspace_path?: string | null;
    resolved_workspace_path?: string | null;
    created_at: string;
    updated_at: string;
}

export interface ProjectFormData {
    emoji: string;
    title: string;
    description: string;
    workspace_type: WorkspaceType;
    workspace_path: string;
}

interface Props {
    modelValue: boolean;
    project?: Project | null;
    errorMessage?: string;
    saving?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
    modelValue: false,
    project: null,
    errorMessage: '',
    saving: false
});

const emit = defineEmits<{
    'update:modelValue': [value: boolean];
    save: [formData: ProjectFormData, projectId?: string];
}>();

const { t } = useI18n();
const { tm } = useModuleI18n('features/chat');

const isOpen = ref(props.modelValue);
const isEditing = ref(false);
const moreSettingsOpen = ref(false);
const canPickWorkspaceDirectory = ref(false);
const pickingWorkspaceDirectory = ref(false);
const form = ref<ProjectFormData>({
    emoji: '📁',
    title: '',
    description: '',
    workspace_type: 'project',
    workspace_path: ''
});
const workspaceTypeItems = computed(() => [
    { label: tm('project.workspace.project'), value: 'project' },
    { label: tm('project.workspace.session'), value: 'session' },
    { label: tm('project.workspace.custom'), value: 'custom' }
]);
const canSave = computed(() => {
    if (!form.value.title.trim()) return false;
    if (form.value.workspace_type !== 'custom') return true;
    return form.value.workspace_path.trim().length > 0;
});

watch(() => props.modelValue, async (newVal) => {
    isOpen.value = newVal;
    moreSettingsOpen.value = false;
    canPickWorkspaceDirectory.value = false;
    if (newVal) {
        if (props.project) {
            isEditing.value = true;
            form.value = {
                emoji: props.project.emoji || '📁',
                title: props.project.title,
                description: props.project.description || '',
                workspace_type: props.project.workspace_type || 'session',
                workspace_path: props.project.workspace_path || ''
            };
        } else {
            isEditing.value = false;
            form.value = {
                emoji: '📁',
                title: '',
                description: '',
                workspace_type: 'project',
                workspace_path: ''
            };
        }

        const runtimeInfo = await getDesktopRuntimeInfo();
        canPickWorkspaceDirectory.value = runtimeInfo.isDesktopRuntime &&
            typeof runtimeInfo.bridge?.pickDirectory === 'function';
    }
});

watch(() => form.value.workspace_type, (workspaceType) => {
    if (workspaceType !== 'custom') {
        form.value.workspace_path = '';
    }
});

function handleDialogChange(value: boolean) {
    emit('update:modelValue', value);
}

function handleCancel() {
    isOpen.value = false;
    emit('update:modelValue', false);
}

async function handlePickWorkspaceDirectory() {
    const pickDirectory = window.astrbotDesktop?.pickDirectory;
    if (!canPickWorkspaceDirectory.value || !pickDirectory || pickingWorkspaceDirectory.value) {
        return;
    }

    pickingWorkspaceDirectory.value = true;
    try {
        const selectedPath = await pickDirectory(form.value.workspace_path || null);
        if (selectedPath) {
            form.value.workspace_path = selectedPath;
            const normalizedPath = selectedPath.replace(/[\\/]+$/, '');
            const folderName = normalizedPath.split(/[\\/]/).pop();
            if (folderName) {
                form.value.title = folderName;
            }
        }
    } catch (error) {
        console.warn('[chat-project] Failed to pick workspace directory.', error);
    } finally {
        pickingWorkspaceDirectory.value = false;
    }
}

function handleSave() {
    if (!canSave.value) {
        return;
    }

    emit('save', {
        ...form.value,
        workspace_path: form.value.workspace_path.trim()
    }, props.project?.project_id);
}

</script>

<style scoped>
.project-name-row,
.workspace-path-row {
    display: flex;
    align-items: center;
    gap: 10px;
}

.project-input {
    width: 100%;
    border: 1px solid rgba(var(--v-theme-on-surface), 0.38);
    border-radius: 4px;
    background: transparent;
    color: rgb(var(--v-theme-on-surface));
    font: inherit;
    outline: none;
    transition: border-color 120ms ease, box-shadow 120ms ease;
}

.project-input:focus {
    border-color: rgb(var(--v-theme-primary));
    box-shadow: 0 0 0 1px rgb(var(--v-theme-primary));
}

.project-name-input,
.workspace-path-input {
    height: 48px;
    padding: 0 14px;
}

.more-settings {
    margin-top: 14px;
}

.more-settings-toggle {
    display: flex;
    align-items: center;
    justify-content: space-between;
    width: 100%;
    padding: 4px 0;
    border: 0;
    background: transparent;
    color: rgba(var(--v-theme-on-surface), 0.72);
    cursor: pointer;
    font: inherit;
    text-align: left;
}

.more-settings-toggle:hover {
    color: rgb(var(--v-theme-primary));
}

.more-settings-chevron {
    font-size: 22px;
    line-height: 1;
    transition: transform 120ms ease;
}

.more-settings-chevron.is-open {
    transform: rotate(180deg);
}

.more-settings-content {
    padding-top: 10px;
}

.project-description-input {
    min-height: 92px;
    padding: 12px 14px;
    resize: vertical;
}

.folder-picker-button {
    display: inline-flex;
    flex: 0 0 auto;
    align-items: center;
    justify-content: center;
    gap: 7px;
    height: 48px;
    padding: 0 16px;
    border: 0;
    border-radius: 4px;
    background: rgba(var(--v-theme-primary), 0.12);
    color: rgb(var(--v-theme-primary));
    cursor: pointer;
    font: inherit;
    white-space: nowrap;
}

.folder-picker-button:hover {
    background: rgba(var(--v-theme-primary), 0.2);
}

.folder-picker-button:disabled {
    cursor: default;
    opacity: 0.5;
}
</style>
