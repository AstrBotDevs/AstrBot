<template>
    <v-dialog v-model="isOpen" max-width="640" @update:model-value="handleDialogChange">
        <v-card>
            <v-card-title class="text-h3 pa-4 pb-0 pl-6">
                {{ isEditing ? tm('project.edit') : tm('project.create') }}
            </v-card-title>
            <v-card-text>
                <v-text-field v-model="form.emoji" :label="tm('project.emoji')" variant="outlined" hide-details class="mb-3" />
                <v-text-field v-model="form.title" :label="tm('project.name')" variant="outlined" hide-details class="mb-3" autofocus
                    @keyup.enter="handleSave" />
                <v-textarea v-model="form.description" :label="tm('project.description')" variant="outlined" hide-details rows="3" />
                <v-divider class="my-4" />
                <v-select v-model="form.workspace_type" :items="workspaceTypeItems" item-title="label" item-value="value"
                    :label="tm('project.workspace.type')" variant="outlined" hide-details class="mb-3" />
                <div v-if="form.workspace_type === 'custom'" class="d-flex align-center ga-2 mb-1">
                    <v-text-field
                        v-model="form.workspace_path"
                        :label="tm('project.workspace.path')"
                        variant="outlined"
                        hide-details
                        class="flex-grow-1"
                    />
                    <v-btn
                        v-if="canPickWorkspaceDirectory"
                        :aria-label="tm('project.workspace.selectPath')"
                        :loading="pickingWorkspaceDirectory"
                        :disabled="props.saving"
                        prepend-icon="mdi-folder-open-outline"
                        variant="tonal"
                        class="text-no-wrap"
                        @click.stop="handlePickWorkspaceDirectory"
                    >
                        {{ tm('project.workspace.selectPath') }}
                    </v-btn>
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
.dialog-title {
    font-size: 22px;
    font-weight: 500;
}
</style>
