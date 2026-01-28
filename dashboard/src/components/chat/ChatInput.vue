<template>
    <div class="input-area fade-in" @dragover.prevent="handleDragOver" @dragleave.prevent="handleDragLeave"
        @drop.prevent="handleDrop">
        <div class="input-container" :style="{
            width: '85%',
            maxWidth: '900px',
            margin: '0 auto',
            border: isDark ? 'none' : '1px solid #e0e0e0',
            borderRadius: '24px',
            boxShadow: isDark ? 'none' : '0px 2px 2px rgba(0, 0, 0, 0.1)',
            backgroundColor: isDark ? '#2d2d2d' : 'transparent',
            position: 'relative'
        }">
            <!-- 拖拽上传遮罩 -->
            <transition name="fade">
                <div v-if="isDragging" class="drop-overlay">
                    <div class="drop-overlay-content">
                        <v-icon size="48" color="deep-purple">mdi-cloud-upload</v-icon>
                        <span class="drop-text">{{ tm('input.dropToUpload') }}</span>
                    </div>
                </div>
            </transition>
            <!-- 引用预览区 -->
            <transition name="slideReply" @after-leave="handleReplyAfterLeave">
                <div class="reply-preview" v-if="props.replyTo && !isReplyClosing">
                    <div class="reply-content">
                        <v-icon size="small" class="reply-icon">mdi-reply</v-icon>
                        "<span class="reply-text">{{ props.replyTo.selectedText }}</span>"
                    </div>
                    <v-btn @click="handleClearReply" class="remove-reply-btn" icon="mdi-close" size="x-small"
                        color="grey" variant="text" />
                </div>
            </transition>
            <textarea ref="inputField" v-model="localPrompt" @keydown="handleKeyDown" :disabled="disabled"
                placeholder="Ask AstrBot..."
                style="width: 100%; resize: none; outline: none; border: 1px solid var(--v-theme-border); border-radius: 12px; padding: 12px 16px; min-height: 40px; font-family: inherit; font-size: 16px; background-color: var(--v-theme-surface);"></textarea>
            <div style="display: flex; justify-content: space-between; align-items: center; padding: 6px 14px;">
                <div
                    style="display: flex; justify-content: flex-start; margin-top: 4px; align-items: center; gap: 8px;">
                    <!-- Settings Menu -->
                    <StyledMenu offset="8" location="top start" :close-on-content-click="false">
                        <template v-slot:activator="{ props: activatorProps }">
                            <v-btn v-bind="activatorProps" icon="mdi-plus" variant="text" color="deep-purple" />
                        </template>

                        <!-- Upload Files -->
                        <v-list-item class="styled-menu-item" rounded="md" @click="triggerImageInput">
                            <template v-slot:prepend>
                                <v-icon icon="mdi-file-upload-outline" size="small"></v-icon>
                            </template>
                            <v-list-item-title>
                                {{ tm('input.upload') }}
                            </v-list-item-title>
                        </v-list-item>

                        <!-- Config Selector in Menu -->
                        <ConfigSelector :session-id="sessionId || null" :platform-id="sessionPlatformId"
                            :is-group="sessionIsGroup" :initial-config-id="props.configId"
                            @config-changed="handleConfigChange" />

                        <!-- Streaming Toggle in Menu -->
                        <v-list-item class="styled-menu-item" rounded="md" @click="$emit('toggleStreaming')">
                            <template v-slot:prepend>
                                <v-icon :icon="enableStreaming ? 'mdi-flash' : 'mdi-flash-off'" size="small"></v-icon>
                            </template>
                            <v-list-item-title>
                                {{ enableStreaming ? tm('streaming.enabled') : tm('streaming.disabled') }}
                            </v-list-item-title>
                        </v-list-item>
                    </StyledMenu>

                    <!-- Provider/Model Selector Menu -->
                    <ProviderModelMenu v-if="showProviderSelector" ref="providerModelMenuRef" />
                </div>
                <div style="display: flex; justify-content: flex-end; margin-top: 8px; align-items: center;">
                    <input type="file" ref="imageInputRef" @change="handleFileSelect" style="display: none" multiple />
                    <v-progress-circular v-if="disabled" indeterminate size="16" class="mr-1" width="1.5" />
                    <!-- <v-btn @click="$emit('openLiveMode')"
                        icon
                        variant="text"
                        color="purple" 
                        size="small"
                    >
                        <v-icon icon="mdi-phone-in-talk" variant="text" plain></v-icon>
                        <v-tooltip activator="parent" location="top">
                            {{ tm('voice.liveMode') }}
                        </v-tooltip>
                    </v-btn> -->
                    <v-btn @click="handleRecordClick" icon variant="text" :color="isRecording ? 'error' : 'deep-purple'"
                        class="record-btn" size="small">
                        <v-icon :icon="isRecording ? 'mdi-stop-circle' : 'mdi-microphone'" variant="text"
                            plain></v-icon>
                        <v-tooltip activator="parent" location="top">
                            {{ isRecording ? tm('voice.speaking') : tm('voice.startRecording') }}
                        </v-tooltip>
                    </v-btn>
                    <v-btn @click="$emit('send')" icon="mdi-send" variant="text" color="deep-purple"
                        :disabled="!canSend" class="send-btn" size="small" />
                </div>
            </div>
        </div>

        <!-- 附件预览区 -->
        <div class="attachments-preview"
            v-if="stagedImagesUrl.length > 0 || stagedAudioUrl || (stagedFiles && stagedFiles.length > 0)">
            <div v-for="(img, index) in stagedImagesUrl" :key="'img-' + index" class="image-preview">
                <img :src="img" class="preview-image" />
                <v-btn @click="$emit('removeImage', index)" class="remove-attachment-btn" icon="mdi-close" size="small"
                    color="error" variant="text" />
            </div>

            <div v-if="stagedAudioUrl" class="audio-preview">
                <v-chip color="deep-purple-lighten-4" class="audio-chip">
                    <v-icon start icon="mdi-microphone" size="small"></v-icon>
                    {{ tm('voice.recording') }}
                </v-chip>
                <v-btn @click="$emit('removeAudio')" class="remove-attachment-btn" icon="mdi-close" size="small"
                    color="error" variant="text" />
            </div>

            <div v-for="(file, index) in stagedFiles" :key="'file-' + index" class="file-preview">
                <v-chip color="blue-grey-lighten-4" class="file-chip">
                    <v-icon start icon="mdi-file-document-outline" size="small"></v-icon>
                    <span class="file-name-preview">{{ file.original_name }}</span>
                </v-chip>
                <v-btn @click="$emit('removeFile', index)" class="remove-attachment-btn" icon="mdi-close" size="small"
                    color="error" variant="text" />
            </div>
        </div>
    </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue';
import { useModuleI18n } from '@/i18n/composables';
import { useCustomizerStore } from '@/stores/customizer';
import ConfigSelector from './ConfigSelector.vue';
import ProviderModelMenu from './ProviderModelMenu.vue';
import StyledMenu from '@/components/shared/StyledMenu.vue';
import type { Session } from '@/composables/useSessions';

interface StagedFileInfo {
    attachment_id: string;
    filename: string;
    original_name: string;
    url: string;
    type: string;
}

interface ReplyInfo {
    messageId: number;
    selectedText?: string;
}

interface Props {
    prompt: string;
    stagedImagesUrl: string[];
    stagedAudioUrl: string;
    stagedFiles?: StagedFileInfo[];
    disabled: boolean;
    enableStreaming: boolean;
    isRecording: boolean;
    sessionId?: string | null;
    currentSession?: Session | null;
    configId?: string | null;
    replyTo?: ReplyInfo | null;
}

const props = withDefaults(defineProps<Props>(), {
    sessionId: null,
    currentSession: null,
    configId: null,
    stagedFiles: () => [],
    replyTo: null
});

const emit = defineEmits<{
    'update:prompt': [value: string];
    send: [];
    toggleStreaming: [];
    removeImage: [index: number];
    removeAudio: [];
    removeFile: [index: number];
    startRecording: [];
    stopRecording: [];
    pasteImage: [event: ClipboardEvent];
    fileSelect: [files: FileList];
    clearReply: [];
    openLiveMode: [];
}>();

const { tm } = useModuleI18n('features/chat');
const isDark = computed(() => useCustomizerStore().uiTheme === 'PurpleThemeDark');

const inputField = ref<HTMLTextAreaElement | null>(null);
const imageInputRef = ref<HTMLInputElement | null>(null);
const providerModelMenuRef = ref<InstanceType<typeof ProviderModelMenu> | null>(null);
const showProviderSelector = ref(true);
const isReplyClosing = ref(false);
const isDragging = ref(false);
let dragLeaveTimeout: number | null = null;

const localPrompt = computed({
    get: () => props.prompt,
    set: (value) => emit('update:prompt', value)
});

const sessionPlatformId = computed(() => props.currentSession?.platform_id || 'webchat');
const sessionIsGroup = computed(() => Boolean(props.currentSession?.is_group));

const canSend = computed(() => {
    return (props.prompt && props.prompt.trim()) || props.stagedImagesUrl.length > 0 || props.stagedAudioUrl || (props.stagedFiles && props.stagedFiles.length > 0);
});

// Ctrl+B 长按录音相关
const ctrlKeyDown = ref(false);
const ctrlKeyTimer = ref<number | null>(null);
const ctrlKeyLongPressThreshold = 300;

// 处理清除引用 - 触发关闭动画
function handleClearReply() {
    isReplyClosing.value = true;
}

// 动画完成后发送clearReply事件
function handleReplyAfterLeave() {
    emit('clearReply');
    isReplyClosing.value = false;
}

function handleKeyDown(e: KeyboardEvent) {
    // Enter 发送消息或触发命令
    if (e.keyCode === 13 && !e.shiftKey) {
        e.preventDefault();

        // 检查是否是 /astr_live_dev 命令
        if (localPrompt.value.trim() === '/astr_live_dev') {
            emit('openLiveMode');
            localPrompt.value = '';
            return;
        }

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

function handleDragOver(e: DragEvent) {
    // 清除之前的 leave timeout
    if (dragLeaveTimeout) {
        clearTimeout(dragLeaveTimeout);
        dragLeaveTimeout = null;
    }

    // 检查是否有文件
    if (e.dataTransfer?.types.includes('Files')) {
        isDragging.value = true;
    }
}

function handleDragLeave(e: DragEvent) {
    // 使用 timeout 避免在子元素间移动时闪烁
    dragLeaveTimeout = window.setTimeout(() => {
        isDragging.value = false;
    }, 50);
}

function handleDrop(e: DragEvent) {
    isDragging.value = false;

    const files = e.dataTransfer?.files;
    if (files && files.length > 0) {
        emit('fileSelect', files);
    }
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
    return providerModelMenuRef.value?.getCurrentSelection();
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
    background-color: transparent;
    position: relative;
    border-top: 1px solid var(--v-theme-border);
    flex-shrink: 0;
}

/* 拖拽上传遮罩 */
.drop-overlay {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background-color: rgba(103, 58, 183, 0.15);
    border: 2px dashed rgba(103, 58, 183, 0.5);
    border-radius: 24px;
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 100;
    pointer-events: none;
}

.drop-overlay-content {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 8px;
}

.drop-text {
    font-size: 16px;
    font-weight: 500;
    color: #673ab7;
}

/* Fade transition for drop overlay */
.fade-enter-active,
.fade-leave-active {
    transition: opacity 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
    opacity: 0;
}

.reply-preview {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 16px;
    margin: 8px 8px 0 8px;
    background-color: rgba(103, 58, 183, 0.06);
    border-radius: 12px;
    gap: 8px;
    max-height: 500px;
    overflow: hidden;
}

/* Transition animations for reply preview */
.slideReply-enter-active {
    animation: slideDown 0.2s ease-out;
}

.slideReply-leave-active {
    animation: slideUp 0.2s ease-out;
}

@keyframes slideDown {
    from {
        max-height: 0;
        opacity: 0;
        margin-top: 0;
        padding-top: 0;
        padding-bottom: 0;
    }

    to {
        max-height: 500px;
        opacity: 1;
        margin-top: 8px;
        padding-top: 8px;
        padding-bottom: 8px;
    }
}

@keyframes slideUp {
    from {
        max-height: 500px;
        opacity: 1;
        margin-top: 8px;
        padding-top: 8px;
        padding-bottom: 8px;
    }

    to {
        max-height: 0;
        opacity: 0;
        margin-top: 0;
        padding-top: 0;
        padding-bottom: 0;
    }
}

.reply-content {
    display: flex;
    align-items: center;
    gap: 6px;
    flex: 1;
    min-width: 0;
    overflow: hidden;
}

.reply-icon {
    color: var(--v-theme-secondary);
    flex-shrink: 0;
}

.reply-text {
    font-size: 13px;
    color: var(--v-theme-secondaryText);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    flex: 1;
    min-width: 0;
}

.remove-reply-btn {
    flex-shrink: 0;
    opacity: 0.6;
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
.audio-preview,
.file-preview {
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

.audio-chip,
.file-chip {
    height: 36px;
    border-radius: 18px;
}

.file-name-preview {
    max-width: 120px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
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
    }
}
</style>
