<template>
    <v-dialog v-model="isOpen" max-width="460" @update:model-value="handleDialogChange">
        <v-card class="project-dialog-card">
            <v-card-title class="text-h3 pa-4 pb-0 pl-6 project-dialog-title">
                {{ isEditing ? tm('project.edit') : tm('project.create') }}
            </v-card-title>
            <v-card-text class="project-dialog-content">
                <div class="project-name-row">
                    <EmojiPicker v-model="form.emoji" />
                    <input
                        v-model="form.title"
                        class="project-name-input"
                        type="text"
                        :placeholder="tm('project.name')"
                        :aria-label="tm('project.name')"
                        autofocus
                        @keyup.enter="handleSave"
                    />
                </div>

                <div class="project-field">
                    <label class="field-label" for="project-workspace-type">{{ tm('project.workspace.type') }}</label>
                    <v-menu location="bottom start" offset="6">
                        <template #activator="{ props: activatorProps }">
                            <button
                                id="project-workspace-type"
                                ref="workspaceSelectTrigger"
                                v-bind="activatorProps"
                                type="button"
                                class="project-select-trigger"
                                :aria-label="tm('project.workspace.type')"
                                aria-haspopup="listbox"
                                @click="syncWorkspaceMenuWidth"
                            >
                                <span>{{ currentWorkspaceLabel }}</span>
                                <v-icon class="select-chevron" size="18" aria-hidden="true">mdi-chevron-down</v-icon>
                            </button>
                        </template>
                        <div
                            class="project-select-menu"
                            role="listbox"
                            :style="{ minWidth: workspaceMenuWidth ? `${workspaceMenuWidth}px` : undefined }"
                        >
                            <button
                                v-for="item in workspaceTypeItems"
                                :key="item.value"
                                type="button"
                                role="option"
                                class="project-select-option"
                                :class="{ 'is-selected': form.workspace_type === item.value }"
                                :aria-selected="form.workspace_type === item.value"
                                @click="form.workspace_type = item.value"
                            >
                                <span>{{ item.label }}</span>
                                <v-icon v-if="form.workspace_type === item.value" size="16" aria-hidden="true">mdi-check</v-icon>
                            </button>
                        </div>
                    </v-menu>
                </div>

                <div v-if="form.workspace_type === 'custom'" class="project-field">
                    <label class="field-label" for="project-workspace-path">{{ tm('project.workspace.path') }}</label>
                    <div class="workspace-path-row">
                        <input
                            id="project-workspace-path"
                            v-model="form.workspace_path"
                            class="project-path-input"
                            type="text"
                            :aria-label="tm('project.workspace.path')"
                        />
                        <button
                            v-if="canPickWorkspaceDirectory"
                            type="button"
                            class="folder-picker-button"
                            :disabled="props.saving"
                            @click.stop="handlePickWorkspaceDirectory"
                        >
                            <v-icon size="18">mdi-folder-open-outline</v-icon>
                            <span>{{ tm('project.workspace.selectPath') }}</span>
                        </button>
                    </div>
                </div>

                <div class="more-settings">
                    <button
                        type="button"
                        class="more-settings-toggle"
                        :aria-expanded="moreSettingsOpen"
                        @click="moreSettingsOpen = !moreSettingsOpen"
                    >
                        <span>{{ tm('project.moreSettings') }}</span>
                        <v-icon
                            size="18"
                            class="more-settings-chevron"
                            :class="{ 'is-open': moreSettingsOpen }"
                            aria-hidden="true"
                        >mdi-chevron-down</v-icon>
                    </button>
                    <textarea
                        v-if="moreSettingsOpen"
                        v-model="form.description"
                        class="project-description-input"
                        :placeholder="tm('project.description')"
                        :aria-label="tm('project.description')"
                        rows="3"
                    />
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
            <div class="project-dialog-actions">
                <button type="button" class="dialog-action" :disabled="props.saving" @click="handleCancel">
                    {{ t('core.common.cancel') }}
                </button>
                <button
                    type="button"
                    class="dialog-action dialog-action-save"
                    :disabled="!canSave || props.saving"
                    :aria-busy="props.saving"
                    @click="handleSave"
                >
                    {{ t('core.common.save') }}
                </button>
            </div>
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
const workspaceTypeItems = computed<{ label: string; value: WorkspaceType }[]>(() => [
    { label: tm('project.workspace.project'), value: 'project' },
    { label: tm('project.workspace.session'), value: 'session' },
    { label: tm('project.workspace.custom'), value: 'custom' }
]);
const currentWorkspaceLabel = computed(() =>
    workspaceTypeItems.value.find((item) => item.value === form.value.workspace_type)?.label || ''
);
const workspaceSelectTrigger = ref<HTMLElement | null>(null);
const workspaceMenuWidth = ref(0);

// The dropdown is teleported to the body, so its width has to be synced from the trigger.
function syncWorkspaceMenuWidth() {
    workspaceMenuWidth.value = workspaceSelectTrigger.value?.getBoundingClientRect().width ?? 0;
}

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
.project-dialog-card {
    --project-border: rgba(var(--v-theme-on-surface), 0.13);
    --project-divider: rgba(var(--v-theme-on-surface), 0.09);
    --project-muted: rgba(var(--v-theme-on-surface), 0.64);
    overflow: hidden !important;
    border: 1px solid var(--project-border);
    border-radius: 20px !important;
    background: rgb(var(--v-theme-surface));
}

.project-dialog-title {
    font-weight: 780;
    line-height: 1.25;
}

.project-dialog-content {
    padding: 20px 24px 0 !important;
}

.project-name-row {
    display: flex;
    align-items: center;
    height: 40px;
    border: 1px solid var(--project-border);
    border-radius: 10px;
    transition: border-color 120ms ease, box-shadow 120ms ease;
}

.project-name-row:focus-within {
    border-color: rgb(var(--v-theme-primary));
    box-shadow: 0 0 0 3px rgba(var(--v-theme-primary), 0.14);
}

.project-name-row :deep(.emoji-picker-trigger) {
    flex: 0 0 auto;
    min-width: 40px;
    height: 38px;
    padding: 0;
    border-radius: 9px 0 0 9px;
    font-size: 20px;
}

.project-name-input,
.project-path-input {
    flex: 1 1 auto;
    min-width: 0;
    height: 100%;
    padding: 0 12px;
    border: 0;
    background: transparent;
    color: rgb(var(--v-theme-on-surface));
    font: inherit;
    font-size: 0.86rem;
    outline: none;
}

.project-name-input {
    padding-left: 2px;
}

.project-name-input::placeholder,
.project-path-input::placeholder,
.project-description-input::placeholder {
    color: var(--project-muted);
}

.project-field {
    margin-top: 16px;
}

.field-label {
    display: block;
    margin-bottom: 6px;
    color: var(--project-muted);
    font-size: 0.78rem;
}

.project-select-trigger {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    width: 100%;
    height: 40px;
    padding: 0 10px 0 12px;
    border: 1px solid var(--project-border);
    border-radius: 10px;
    background: transparent;
    color: rgb(var(--v-theme-on-surface));
    font: inherit;
    font-size: 0.86rem;
    text-align: left;
    cursor: pointer;
    outline: none;
    transition: border-color 120ms ease, box-shadow 120ms ease;
}

.project-select-trigger:hover {
    border-color: rgba(var(--v-theme-on-surface), 0.24);
}

.project-select-trigger:focus-visible {
    border-color: rgb(var(--v-theme-primary));
    box-shadow: 0 0 0 3px rgba(var(--v-theme-primary), 0.14);
}

.select-chevron {
    flex: 0 0 auto;
    color: var(--project-muted);
}

.project-select-menu {
    --project-border: rgba(var(--v-theme-on-surface), 0.13);
    --project-muted: rgba(var(--v-theme-on-surface), 0.64);
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: 4px;
    border: 1px solid var(--project-border);
    border-radius: 12px;
    background: rgb(var(--v-theme-surface));
    box-shadow: 0 12px 32px rgba(0, 0, 0, 0.36);
}

.project-select-option {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    height: 34px;
    padding: 0 10px;
    border: 0;
    border-radius: 8px;
    background: transparent;
    color: rgb(var(--v-theme-on-surface));
    cursor: pointer;
    font: inherit;
    font-size: 0.86rem;
    text-align: left;
}

.project-select-option:hover {
    background: rgba(var(--v-theme-on-surface), 0.06);
}

.project-select-option.is-selected {
    background: rgba(var(--v-theme-primary), 0.14);
    color: rgb(var(--v-theme-primary));
    font-weight: 600;
}

.workspace-path-row {
    display: flex;
    align-items: center;
    gap: 8px;
}

.project-path-input {
    height: 40px;
    border: 1px solid var(--project-border);
    border-radius: 10px;
    transition: border-color 120ms ease, box-shadow 120ms ease;
}

.project-path-input:focus {
    border-color: rgb(var(--v-theme-primary));
    box-shadow: 0 0 0 3px rgba(var(--v-theme-primary), 0.14);
}

.folder-picker-button {
    display: inline-flex;
    flex: 0 0 auto;
    align-items: center;
    gap: 6px;
    height: 40px;
    padding: 0 12px;
    border: 0;
    border-radius: 10px;
    background: rgba(var(--v-theme-primary), 0.14);
    color: rgb(var(--v-theme-primary));
    cursor: pointer;
    font: inherit;
    font-size: 0.82rem;
    white-space: nowrap;
}

.folder-picker-button:hover:not(:disabled) {
    background: rgba(var(--v-theme-primary), 0.22);
}

.folder-picker-button:disabled {
    cursor: default;
    opacity: 0.5;
}

.more-settings {
    margin-top: 14px;
}

.more-settings-toggle {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 0;
    border: 0;
    background: transparent;
    color: var(--project-muted);
    cursor: pointer;
    font: inherit;
    font-size: 0.78rem;
}

.more-settings-toggle:hover {
    color: rgb(var(--v-theme-on-surface));
}

.more-settings-chevron {
    transition: transform 140ms ease;
}

.more-settings-chevron.is-open {
    transform: rotate(180deg);
}

.project-description-input {
    display: block;
    width: 100%;
    min-height: 76px;
    margin-top: 10px;
    padding: 10px 12px;
    border: 1px solid var(--project-border);
    border-radius: 10px;
    background: transparent;
    color: rgb(var(--v-theme-on-surface));
    font: inherit;
    font-size: 0.86rem;
    line-height: 1.5;
    outline: none;
    resize: vertical;
    transition: border-color 120ms ease, box-shadow 120ms ease;
}

.project-description-input:focus {
    border-color: rgb(var(--v-theme-primary));
    box-shadow: 0 0 0 3px rgba(var(--v-theme-primary), 0.14);
}

.project-dialog-actions {
    display: flex;
    justify-content: flex-end;
    gap: 4px;
    padding: 16px 16px 16px;
}

.dialog-action {
    min-width: 60px;
    height: 36px;
    padding: 0 12px;
    border: 0;
    border-radius: 8px;
    background: transparent;
    color: rgb(var(--v-theme-on-surface));
    cursor: pointer;
    font: inherit;
    font-size: 0.86rem;
    font-weight: 600;
}

.dialog-action-save {
    color: rgb(var(--v-theme-primary));
}

.dialog-action:hover:not(:disabled) {
    background: rgba(var(--v-theme-on-surface), 0.06);
}

.dialog-action:disabled {
    cursor: default;
    opacity: 0.4;
}
</style>
