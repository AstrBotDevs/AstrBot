<template>
    <div class="input-area fade-in">
        <div class="input-container"
            style="width: 85%; max-width: 900px; margin: 0 auto; border: 1px solid #e0e0e0; border-radius: 24px;">
            <textarea 
                ref="inputField"
                v-model="localPrompt" 
                @keydown="handleKeyDown"
                :disabled="disabled" 
                placeholder="Ask AstrBot..."
                style="width: 100%; resize: none; outline: none; border: 1px solid var(--v-theme-border); border-radius: 12px; padding: 8px 16px; min-height: 40px; font-family: inherit; font-size: 16px; background-color: var(--v-theme-surface);"></textarea>
            <div style="display: flex; justify-content: space-between; align-items: center; padding: 0px 12px;">
                <div style="display: flex; justify-content: flex-start; margin-top: 4px; align-items: center; gap: 8px;">
                    <ConfigSelector
                        :session-id="sessionId || null"
                        :platform-id="sessionPlatformId"
                        :is-group="sessionIsGroup"
                        :initial-config-id="props.configId"
                        @config-changed="handleConfigChange"
                    />
                    <ProviderModelSelector v-if="showProviderSelector" ref="providerModelSelectorRef" />
                    
                    <v-tooltip :text="enableStreaming ? tm('streaming.enabled') : tm('streaming.disabled')" location="top">
                        <template v-slot:activator="{ props }">
                            <v-chip v-bind="props" @click="$emit('toggleStreaming')" size="x-small" class="streaming-toggle-chip">
                                <v-icon start :icon="enableStreaming ? 'mdi-flash' : 'mdi-flash-off'" size="small"></v-icon>
                                {{ enableStreaming ? tm('streaming.on') : tm('streaming.off') }}
                            </v-chip>
                        </template>
                    </v-tooltip>
                </div>
                <div style="display: flex; justify-content: flex-end; margin-top: 8px; align-items: center;">
                    <input type="file" ref="imageInputRef" @change="handleFileSelect" accept="image/*"
                        style="display: none" multiple />
                    <v-progress-circular v-if="disabled" indeterminate size="16" class="mr-1" width="1.5" />
                    <v-btn @click="triggerImageInput" icon="mdi-plus" variant="text" color="deep-purple"
                        class="add-btn" size="small" />
                    <v-btn @click="handleRecordClick"
                        :icon="isRecording ? 'mdi-stop-circle' : 'mdi-microphone'" variant="text"
                        :color="isRecording ? 'error' : 'deep-purple'" class="record-btn" size="small" />
                    <v-btn @click="$emit('send')" icon="mdi-send" variant="text" color="deep-purple"
                        :disabled="!canSend" class="send-btn" size="small" />
                </div>
            </div>
        </div>

        <!-- 附件预览区 -->
        <div class="attachments-preview" v-if="stagedImagesUrl.length > 0 || stagedAudioUrl">
            <div v-for="(img, index) in stagedImagesUrl" :key="index" class="image-preview">
                <img :src="img" class="preview-image" />
                <v-btn @click="$emit('removeImage', index)" class="remove-attachment-btn" icon="mdi-close"
                    size="small" color="error" variant="text" />
            </div>

            <div v-if="stagedAudioUrl" class="audio-preview">
                <v-chip color="deep-purple-lighten-4" class="audio-chip">
                    <v-icon start icon="mdi-microphone" size="small"></v-icon>
                    {{ tm('voice.recording') }}
                </v-chip>
                <v-btn @click="$emit('removeAudio')" class="remove-attachment-btn" icon="mdi-close" size="small"
                    color="error" variant="text" />
            </div>
        </div>
    </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue';
import { useModuleI18n } from '@/i18n/composables';
import ProviderModelSelector from './ProviderModelSelector.vue';
import ConfigSelector from './ConfigSelector.vue';
import type { Session } from '@/composables/useSessions';

interface Props {
    prompt: string;
    stagedImagesUrl: string[];
    stagedAudioUrl: string;
    disabled: boolean;
    enableStreaming: boolean;
    isRecording: boolean;
    sessionId?: string | null;
    currentSession?: Session | null;
    configId?: string | null;
}

const props = withDefaults(defineProps<Props>(), {
    sessionId: null,
    currentSession: null,
    configId: null
});

const emit = defineEmits<{
    'update:prompt': [value: string];
    send: [];
    toggleStreaming: [];
    removeImage: [index: number];
    removeAudio: [];
    startRecording: [];
    stopRecording: [];
    pasteImage: [event: ClipboardEvent];
    fileSelect: [files: FileList];
}>();

const { tm } = useModuleI18n('features/chat');

const inputField = ref<HTMLTextAreaElement | null>(null);
const imageInputRef = ref<HTMLInputElement | null>(null);
const providerModelSelectorRef = ref<InstanceType<typeof ProviderModelSelector> | null>(null);
const showProviderSelector = ref(true);

const localPrompt = computed({
    get: () => props.prompt,
    set: (value) => emit('update:prompt', value)
});

const sessionPlatformId = computed(() => props.currentSession?.platform_id || 'webchat');
const sessionIsGroup = computed(() => Boolean(props.currentSession?.is_group));

const canSend = computed(() => {
    return (props.prompt && props.prompt.trim()) || props.stagedImagesUrl.length > 0 || props.stagedAudioUrl;
});

// Ctrl+B 长按录音相关
const ctrlKeyDown = ref(false);
const ctrlKeyTimer = ref<number | null>(null);
const ctrlKeyLongPressThreshold = 300;

function handleKeyDown(e: KeyboardEvent) {
    // Enter 发送消息
    if (e.keyCode === 13 && !e.shiftKey) {
        e.preventDefault();
        if (canSend.value) {
            emit('send');
        }
    }

    // Ctrl+B 录音
    if (e.ctrlKey && e.keyCode === 66) {
        e.preventDefault();
        if (ctrlKeyDown.value) return;

        ctrlKeyDown.value = true;
        ctrlKeyTimer.value = window.setTimeout(() => {
            if (ctrlKeyDown.value && !props.isRecording) {
                emit('startRecording');
            }
        }, ctrlKeyLongPressThreshold);
    }
}

function handleKeyUp(e: KeyboardEvent) {
    if (e.keyCode === 66) {
        ctrlKeyDown.value = false;

        if (ctrlKeyTimer.value) {
            clearTimeout(ctrlKeyTimer.value);
            ctrlKeyTimer.value = null;
        }

        if (props.isRecording) {
            emit('stopRecording');
        }
    }
}

function handlePaste(e: ClipboardEvent) {
    emit('pasteImage', e);
}

function triggerImageInput() {
    imageInputRef.value?.click();
}

function handleFileSelect(event: Event) {
    const target = event.target as HTMLInputElement;
    const files = target.files;
    if (files) {
        emit('fileSelect', files);
    }
    target.value = '';
}

function handleRecordClick() {
    if (props.isRecording) {
        emit('stopRecording');
    } else {
        emit('startRecording');
    }
}

function handleConfigChange(payload: { configId: string; agentRunnerType: string }) {
    const runnerType = (payload.agentRunnerType || '').toLowerCase();
    const isInternal = runnerType === 'internal' || runnerType === 'local';
    showProviderSelector.value = isInternal;
}

function getCurrentSelection() {
    if (!showProviderSelector.value) {
        return null;
    }
    return providerModelSelectorRef.value?.getCurrentSelection();
}

onMounted(() => {
    if (inputField.value) {
        inputField.value.addEventListener('paste', handlePaste);
    }
    document.addEventListener('keyup', handleKeyUp);
});

onBeforeUnmount(() => {
    if (inputField.value) {
        inputField.value.removeEventListener('paste', handlePaste);
    }
    document.removeEventListener('keyup', handleKeyUp);
});

defineExpose({
    getCurrentSelection
});
</script>

<style scoped>
.input-area {
    padding: 16px;
    background-color: var(--v-theme-surface);
    position: relative;
    border-top: 1px solid var(--v-theme-border);
    flex-shrink: 0;
}

.attachments-preview {
    display: flex;
    gap: 8px;
    margin-top: 8px;
    max-width: 900px;
    margin: 8px auto 0;
    flex-wrap: wrap;
}

.image-preview,
.audio-preview {
    position: relative;
    display: inline-flex;
}

.preview-image {
    width: 60px;
    height: 60px;
    object-fit: cover;
    border-radius: 8px;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.audio-chip {
    height: 36px;
    border-radius: 18px;
}

.remove-attachment-btn {
    position: absolute;
    top: -8px;
    right: -8px;
    opacity: 0.8;
    transition: opacity 0.2s;
}

.remove-attachment-btn:hover {
    opacity: 1;
}

.streaming-toggle-chip {
    cursor: pointer;
    transition: all 0.2s ease;
    user-select: none;
}

.streaming-toggle-chip:hover {
    opacity: 0.8;
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

@media (max-width: 768px) {
    .input-area {
        padding: 0 !important;
    }
    
    .input-container {
        width: 100% !important;
        max-width: 100% !important;
        margin: 0 !important;
        border-radius: 0 !important;
        border-left: none !important;
        border-right: none !important;
        border-bottom: none !important;
    }
}
</style>
