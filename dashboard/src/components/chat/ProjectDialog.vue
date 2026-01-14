<template>
    <v-dialog v-model="isOpen" max-width="500" @update:model-value="handleDialogChange">
        <v-card>
            <v-card-title class="dialog-title">
                {{ isEditing ? tm('project.edit') : tm('project.create') }}
            </v-card-title>
            <v-card-text>
                <v-text-field v-model="form.emoji" :label="tm('project.emoji')" flat variant="solo-filled" hide-details class="mb-3" />
                <v-text-field v-model="form.title" :label="tm('project.name')" flat variant="solo-filled" hide-details class="mb-3" autofocus
                    @keyup.enter="handleSave" />
                <v-textarea v-model="form.description" :label="tm('project.description')" flat variant="solo-filled" hide-details rows="3" rounded="lg" />
            </v-card-text>
            <v-card-actions>
                <v-spacer></v-spacer>
                <v-btn variant="text" @click="handleCancel" color="grey-darken-1">{{ t('core.common.cancel') }}</v-btn>
                <v-btn variant="text" @click="handleSave" color="primary" :disabled="!form.title.trim()">{{ t('core.common.save') }}</v-btn>
            </v-card-actions>
        </v-card>
    </v-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue';
import { useI18n, useModuleI18n } from '@/i18n/composables';

export interface Project {
    project_id: string;
    title: string;
    emoji?: string;
    description?: string;
    created_at: string;
    updated_at: string;
}

export interface ProjectFormData {
    emoji: string;
    title: string;
    description: string;
}

interface Props {
    modelValue: boolean;
    project?: Project | null;
}

const props = withDefaults(defineProps<Props>(), {
    modelValue: false,
    project: null
});

const emit = defineEmits<{
    'update:modelValue': [value: boolean];
    save: [formData: ProjectFormData, projectId?: string];
}>();

const { t } = useI18n();
const { tm } = useModuleI18n('features/chat');

const isOpen = ref(props.modelValue);
const isEditing = ref(false);
const form = ref<ProjectFormData>({
    emoji: '📁',
    title: '',
    description: ''
});

watch(() => props.modelValue, (newVal) => {
    isOpen.value = newVal;
    if (newVal) {
        // 打开对话框时初始化表单
        if (props.project) {
            isEditing.value = true;
            form.value = {
                emoji: props.project.emoji || '📁',
                title: props.project.title,
                description: props.project.description || ''
            };
        } else {
            isEditing.value = false;
            form.value = {
                emoji: '📁',
                title: '',
                description: ''
            };
        }
    }
});

function handleDialogChange(value: boolean) {
    emit('update:modelValue', value);
}

function handleCancel() {
    isOpen.value = false;
    emit('update:modelValue', false);
}

function handleSave() {
    if (!form.value.title.trim()) {
        return;
    }

    emit('save', { ...form.value }, props.project?.project_id);
    isOpen.value = false;
    emit('update:modelValue', false);
}
</script>

<style scoped>
.dialog-title {
    font-size: 22px;
    font-weight: 500;
}
</style>
