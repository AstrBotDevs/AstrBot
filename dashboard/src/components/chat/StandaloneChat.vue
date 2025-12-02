<template>
    <v-card class="standalone-chat-card" elevation="0" rounded="0">
        <v-card-text class="standalone-chat-container">
            <div class="chat-layout">
                <!-- 聊天内容区域 -->
                <div class="chat-content-panel">
                    <MessageList v-if="messages && messages.length > 0" :messages="messages" :isDark="isDark"
                        :isStreaming="isStreaming || isConvRunning" @openImagePreview="openImagePreview"
                        ref="messageList" />
                    <div class="welcome-container fade-in" v-else>
                        <div class="welcome-title">
                            <span>Hello, I'm</span>
                            <span class="bot-name">AstrBot ⭐</span>
                        </div>
                        <p class="text-caption text-medium-emphasis mt-2">
                            测试配置: {{ configId || 'default' }}
                        </p>
                    </div>

                    <!-- 输入区域 -->
                    <ChatInput
                        v-model:prompt="prompt"
                        :stagedImagesUrl="stagedImagesUrl"
                        :stagedAudioUrl="stagedAudioUrl"
                        :disabled="isStreaming"
                        :enableStreaming="enableStreaming"
                        :isRecording="isRecording"
                        :session-id="currSessionId || null"
                        :current-session="getCurrentSession"
                        :config-id="configId"
                        @send="handleSendMessage"
                        @toggleStreaming="toggleStreaming"
                        @removeImage="removeImage"
                        @removeAudio="removeAudio"
                        @startRecording="handleStartRecording"
                        @stopRecording="handleStopRecording"
                        @pasteImage="handlePaste"
                        @fileSelect="handleFileSelect"
                        ref="chatInputRef"
                    />
                </div>
            </div>
        </v-card-text>
    </v-card>

    <!-- 图片预览对话框 -->
    <v-dialog v-model="imagePreviewDialog" max-width="90vw" max-height="90vh">
        <v-card class="image-preview-card" elevation="8">
            <v-card-title class="d-flex justify-space-between align-center pa-4">
                <span>{{ t('core.common.imagePreview') }}</span>
                <v-btn icon="mdi-close" variant="text" @click="imagePreviewDialog = false" />
            </v-card-title>
            <v-card-text class="text-center pa-4">
                <img :src="previewImageUrl" class="preview-image-large" />
            </v-card-text>
        </v-card>
    </v-dialog>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue';
import axios from 'axios';
import { useCustomizerStore } from '@/stores/customizer';
import { useI18n, useModuleI18n } from '@/i18n/composables';
import { useTheme } from 'vuetify';
import MessageList from '@/components/chat/MessageList.vue';
import ChatInput from '@/components/chat/ChatInput.vue';
import { useMessages } from '@/composables/useMessages';
import { useMediaHandling } from '@/composables/useMediaHandling';
import { useRecording } from '@/composables/useRecording';
import { useToast } from '@/utils/toast';

interface Props {
    configId?: string | null;
}

const props = withDefaults(defineProps<Props>(), {
    configId: null
});

const { t } = useI18n();
const { error: showError } = useToast();

// UI 状态
const imagePreviewDialog = ref(false);
const previewImageUrl = ref('');

// 会话管理（不使用 useSessions 避免路由跳转）
const currSessionId = ref('');
const getCurrentSession = computed(() => null); // 独立测试模式不需要会话信息

async function newSession() {
    try {
        const response = await axios.get('/api/chat/new_session');
        const sessionId = response.data.data.session_id;
        currSessionId.value = sessionId;
        return sessionId;
    } catch (err) {
        console.error(err);
        throw err;
    }
}

function updateSessionTitle(sessionId: string, title: string) {
    // 独立模式不需要更新会话标题
}

function getSessions() {
    // 独立模式不需要加载会话列表
}

const {
    stagedImagesUrl,
    stagedAudioUrl,
    stagedFiles,
    getMediaFile,
    processAndUploadImage,
    handlePaste,
    removeImage,
    removeAudio,
    clearStaged,
    cleanupMediaCache
} = useMediaHandling();

const { isRecording, startRecording: startRec, stopRecording: stopRec } = useRecording();

const {
    messages,
    isStreaming,
    isConvRunning,
    enableStreaming,
    getSessionMessages: getSessionMsg,
    sendMessage: sendMsg,
    toggleStreaming
} = useMessages(currSessionId, getMediaFile, updateSessionTitle, getSessions);

// 组件引用
const messageList = ref<InstanceType<typeof MessageList> | null>(null);
const chatInputRef = ref<InstanceType<typeof ChatInput> | null>(null);

// 输入状态
const prompt = ref('');

const isDark = computed(() => useCustomizerStore().uiTheme === 'PurpleThemeDark');

function openImagePreview(imageUrl: string) {
    previewImageUrl.value = imageUrl;
    imagePreviewDialog.value = true;
}

async function handleStartRecording() {
    await startRec();
}

async function handleStopRecording() {
    const audioFilename = await stopRec();
    stagedAudioUrl.value = audioFilename;
}

async function handleFileSelect(files: FileList) {
    for (const file of files) {
        await processAndUploadImage(file);
    }
}

async function handleSendMessage() {
    if (!prompt.value.trim() && stagedFiles.value.length === 0 && !stagedAudioUrl.value) {
        return;
    }

    try {
        if (!currSessionId.value) {
            await newSession();
        }

        const promptToSend = prompt.value.trim();
        const audioNameToSend = stagedAudioUrl.value;
        const filesToSend = stagedFiles.value.map(f => ({
            attachment_id: f.attachment_id,
            url: f.url,
            original_name: f.original_name,
            type: f.type
        }));

        // 清空输入和附件
        prompt.value = '';
        clearStaged();

        // 获取选择的提供商和模型
        const selection = chatInputRef.value?.getCurrentSelection();
        const selectedProviderId = selection?.providerId || '';
        const selectedModelName = selection?.modelName || '';

        await sendMsg(
            promptToSend,
            filesToSend,
            audioNameToSend,
            selectedProviderId,
            selectedModelName
        );

        // 滚动到底部
        nextTick(() => {
            messageList.value?.scrollToBottom();
        });
    } catch (err) {
        console.error('Failed to send message:', err);
        showError(t('features.chat.errors.sendMessageFailed'));
        // 恢复输入内容，让用户可以重试
        // 注意：附件已经上传到服务器，所以不恢复附件
    }
}

onMounted(async () => {
    // 独立模式在挂载时创建新会话
    try {
        await newSession();
    } catch (err) {
        console.error('Failed to create initial session:', err);
        showError(t('features.chat.errors.createSessionFailed'));
    }
});

onBeforeUnmount(() => {
    cleanupMediaCache();
});
</script>

<style scoped>
/* 基础动画 */
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

.standalone-chat-card {
    width: 100%;
    height: 100%;
    max-height: 100%;
    overflow: hidden;
}

.standalone-chat-container {
    width: 100%;
    height: 100%;
    max-height: 100%;
    padding: 0;
    overflow: hidden;
}

.chat-layout {
    height: 100%;
    max-height: 100%;
    display: flex;
    overflow: hidden;
}

.chat-content-panel {
    height: 100%;
    max-height: 100%;
    width: 100%;
    display: flex;
    flex-direction: column;
    overflow: hidden;
}

.conversation-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 8px;
    padding-left: 16px;
    border-bottom: 1px solid var(--v-theme-border);
    width: 100%;
    padding-right: 32px;
    flex-shrink: 0;
}

.conversation-header-info h4 {
    margin: 0;
    font-weight: 500;
}

.conversation-header-actions {
    display: flex;
    gap: 8px;
    align-items: center;
}

.welcome-container {
    height: 100%;
    display: flex;
    justify-content: center;
    align-items: center;
    flex-direction: column;
}

.welcome-title {
    font-size: 28px;
    margin-bottom: 8px;
}

.bot-name {
    font-weight: 700;
    margin-left: 8px;
    color: var(--v-theme-secondary);
}

.fade-in {
    animation: fadeIn 0.3s ease-in-out;
}

.preview-image-large {
    max-width: 100%;
    max-height: 70vh;
    object-fit: contain;
}
</style>
