<template>
    <v-card class="chat-page-card" elevation="0" rounded="0">
        <v-card-text class="chat-page-container">
            <!-- 遮罩层 (手机端) -->
            <div class="mobile-overlay" v-if="isMobile && mobileMenuOpen" @click="closeMobileSidebar"></div>
            
            <div class="chat-layout">
                <ConversationSidebar
                    :sessions="sessions"
                    :selectedSessions="selectedSessions"
                    :currSessionId="currSessionId"
                    :isDark="isDark"
                    :chatboxMode="chatboxMode"
                    :isMobile="isMobile"
                    :mobileMenuOpen="mobileMenuOpen"
                    @newChat="handleNewChat"
                    @selectConversation="handleSelectConversation"
                    @editTitle="showEditTitleDialog"
                    @deleteConversation="handleDeleteConversation"
                    @closeMobileSidebar="closeMobileSidebar"
                    @toggleTheme="toggleTheme"
                    @toggleFullscreen="toggleFullscreen"
                />

                <!-- 右侧聊天内容区域 -->
                <div class="chat-content-panel">

                    <div class="conversation-header fade-in" v-if="isMobile">
                        <!-- 手机端菜单按钮 -->
                        <v-btn icon class="mobile-menu-btn" @click="toggleMobileSidebar" variant="text">
                            <v-icon>mdi-menu</v-icon>
                        </v-btn>
                    </div>

                    <div class="message-list-wrapper" v-if="messages && messages.length > 0">
                        <MessageList :messages="messages" :isDark="isDark"
                            :isStreaming="isStreaming || isConvRunning" 
                            :isLoadingMessages="isLoadingMessages"
                            @openImagePreview="openImagePreview"
                            @replyMessage="handleReplyMessage"
                            @replyWithText="handleReplyWithText"
                            ref="messageList" />
                        <div class="message-list-fade" :class="{ 'fade-dark': isDark }"></div>
                    </div>
                    <div class="welcome-container fade-in" v-else>
                        <div v-if="isLoadingMessages" class="loading-overlay-welcome">
                            <v-progress-circular
                                indeterminate
                                size="48"
                                width="4"
                                color="primary"
                            ></v-progress-circular>
                        </div>
                        <div v-else class="welcome-title">
                            <span>Hello, I'm</span>
                            <span class="bot-name">AstrBot ⭐</span>
                        </div>
                    </div>

                    <!-- 输入区域 -->
                    <ChatInput
                        v-model:prompt="prompt"
                        :stagedImagesUrl="stagedImagesUrl"
                        :stagedAudioUrl="stagedAudioUrl"
                        :stagedFiles="stagedNonImageFiles"
                        :disabled="isStreaming"
                        :enableStreaming="enableStreaming"
                        :isRecording="isRecording"
                        :session-id="currSessionId || null"
                        :current-session="getCurrentSession"
                        :replyTo="replyTo"
                        @send="handleSendMessage"
                        @toggleStreaming="toggleStreaming"
                        @removeImage="removeImage"
                        @removeAudio="removeAudio"
                        @removeFile="removeFile"
                        @startRecording="handleStartRecording"
                        @stopRecording="handleStopRecording"
                        @pasteImage="handlePaste"
                        @fileSelect="handleFileSelect"
                        @clearReply="clearReply"
                        ref="chatInputRef"
                    />
                </div>

            </div>
        </v-card-text>
    </v-card>
    <!-- 编辑对话标题对话框 -->
    <v-dialog v-model="editTitleDialog" max-width="400">
        <v-card>
            <v-card-title class="dialog-title">{{ tm('actions.editTitle') }}</v-card-title>
            <v-card-text>
                <v-text-field v-model="editingTitle" :label="tm('conversation.newConversation')" variant="outlined"
                    hide-details class="mt-2" @keyup.enter="saveTitle" autofocus />
            </v-card-text>
            <v-card-actions>
                <v-spacer></v-spacer>
                <v-btn variant="text" @click="editTitleDialog = false" color="grey-darken-1">{{ t('core.common.cancel') }}</v-btn>
                <v-btn variant="text" @click="saveTitle" color="primary">{{ t('core.common.save') }}</v-btn>
            </v-card-actions>
        </v-card>
    </v-dialog>

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
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import { useCustomizerStore } from '@/stores/customizer';
import { useI18n, useModuleI18n } from '@/i18n/composables';
import { useTheme } from 'vuetify';
import LanguageSwitcher from '@/components/shared/LanguageSwitcher.vue';
import MessageList from '@/components/chat/MessageList.vue';
import ConversationSidebar from '@/components/chat/ConversationSidebar.vue';
import ChatInput from '@/components/chat/ChatInput.vue';
import { useSessions } from '@/composables/useSessions';
import { useMessages } from '@/composables/useMessages';
import { useMediaHandling } from '@/composables/useMediaHandling';
import { useRecording } from '@/composables/useRecording';

interface Props {
    chatboxMode?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
    chatboxMode: false
});

const router = useRouter();
const route = useRoute();
const { t } = useI18n();
const { tm } = useModuleI18n('features/chat');
const theme = useTheme();

// UI 状态
const isMobile = ref(false);
const mobileMenuOpen = ref(false);
const imagePreviewDialog = ref(false);
const previewImageUrl = ref('');
const isLoadingMessages = ref(false);

// 使用 composables
const {
    sessions,
    selectedSessions,
    currSessionId,
    pendingSessionId,
    editTitleDialog,
    editingTitle,
    editingSessionId,
    getCurrentSession,
    getSessions,
    newSession,
    deleteSession: deleteSessionFn,
    showEditTitleDialog,
    saveTitle,
    updateSessionTitle,
    newChat
} = useSessions(props.chatboxMode);

const {
    stagedImagesUrl,
    stagedAudioUrl,
    stagedFiles,
    stagedNonImageFiles,
    getMediaFile,
    processAndUploadImage,
    processAndUploadFile,
    handlePaste,
    removeImage,
    removeAudio,
    removeFile,
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

// 引用消息状态
interface ReplyInfo {
    messageId: number;  // PlatformSessionHistoryMessage 的 id
    selectedText?: string;  // 选中的文本内容（可选）
}
const replyTo = ref<ReplyInfo | null>(null);

const isDark = computed(() => useCustomizerStore().uiTheme === 'PurpleThemeDark');

// 检测是否为手机端
function checkMobile() {
    isMobile.value = window.innerWidth <= 768;
    if (!isMobile.value) {
        mobileMenuOpen.value = false;
    }
}

function toggleMobileSidebar() {
    mobileMenuOpen.value = !mobileMenuOpen.value;
}

function closeMobileSidebar() {
    mobileMenuOpen.value = false;
}

function toggleTheme() {
    const customizer = useCustomizerStore();
    const newTheme = customizer.uiTheme === 'PurpleTheme' ? 'PurpleThemeDark' : 'PurpleTheme';
    customizer.SET_UI_THEME(newTheme);
    theme.global.name.value = newTheme;
}

function toggleFullscreen() {
    if (props.chatboxMode) {
        router.push(currSessionId.value ? `/chat/${currSessionId.value}` : '/chat');
    } else {
        router.push(currSessionId.value ? `/chatbox/${currSessionId.value}` : '/chatbox');
    }
}

function openImagePreview(imageUrl: string) {
    previewImageUrl.value = imageUrl;
    imagePreviewDialog.value = true;
}

function handleReplyMessage(msg: any, index: number) {
    // 从消息中获取 id (PlatformSessionHistoryMessage 的 id)
    const messageId = msg.id;
    if (!messageId) {
        console.warn('Message does not have an id');
        return;
    }
    
    // 获取消息内容用于显示
    let messageContent = '';
    if (typeof msg.content.message === 'string') {
        messageContent = msg.content.message;
    } else if (Array.isArray(msg.content.message)) {
        // 从消息段数组中提取纯文本
        const textParts = msg.content.message
            .filter((part: any) => part.type === 'plain' && part.text)
            .map((part: any) => part.text);
        messageContent = textParts.join('');
    }
    
    // 截断过长的内容
    if (messageContent.length > 100) {
        messageContent = messageContent.substring(0, 100) + '...';
    }
    
    replyTo.value = {
        messageId,
        selectedText: messageContent || '[媒体内容]'
    };
}

function clearReply() {
    replyTo.value = null;
}

function handleReplyWithText(replyData: any) {
    // 处理选中文本的引用
    const { messageId, selectedText, messageIndex } = replyData;
    
    if (!messageId) {
        console.warn('Message does not have an id');
        return;
    }
    
    replyTo.value = {
        messageId,
        selectedText: selectedText  // 保存原始的选中文本
    };
}

async function handleSelectConversation(sessionIds: string[]) {
    if (!sessionIds[0]) return;

    // 立即更新选中状态，避免需要点击两次
    currSessionId.value = sessionIds[0];
    selectedSessions.value = [sessionIds[0]];

    // 更新 URL
    const basePath = props.chatboxMode ? '/chatbox' : '/chat';
    if (route.path !== `${basePath}/${sessionIds[0]}`) {
        router.push(`${basePath}/${sessionIds[0]}`);
    }

    // 手机端关闭侧边栏
    if (isMobile.value) {
        closeMobileSidebar();
    }

    // 清除引用状态
    clearReply();
    
    // 开始加载消息
    isLoadingMessages.value = true;
    
    try {
        await getSessionMsg(sessionIds[0]);
    } finally {
        isLoadingMessages.value = false;
    }
    
    nextTick(() => {
        messageList.value?.scrollToBottom();
    });
}

function handleNewChat() {
    newChat(closeMobileSidebar);
    messages.value = [];
    clearReply();
}

async function handleDeleteConversation(sessionId: string) {
    await deleteSessionFn(sessionId);
    messages.value = [];
}

async function handleStartRecording() {
    await startRec();
}

async function handleStopRecording() {
    const audioFilename = await stopRec();
    stagedAudioUrl.value = audioFilename;
}

async function handleFileSelect(files: FileList) {
    const imageTypes = ['image/jpeg', 'image/png', 'image/gif', 'image/webp'];
    for (const file of files) {
        if (imageTypes.includes(file.type)) {
            await processAndUploadImage(file);
        } else {
            await processAndUploadFile(file);
        }
    }
}

async function handleSendMessage() {
    // 只有引用不能发送，必须有输入内容
    if (!prompt.value.trim() && stagedFiles.value.length === 0 && !stagedAudioUrl.value) {
        return;
    }

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
    const replyToSend = replyTo.value ? { ...replyTo.value } : null;

    // 清空输入和附件和引用
    prompt.value = '';
    clearStaged();
    clearReply();

    // 获取选择的提供商和模型
    const selection = chatInputRef.value?.getCurrentSelection();
    const selectedProviderId = selection?.providerId || '';
    const selectedModelName = selection?.modelName || '';

    await sendMsg(
        promptToSend,
        filesToSend,
        audioNameToSend,
        selectedProviderId,
        selectedModelName,
        replyToSend
    );
}

// 路由变化监听
watch(
    () => route.path,
    (to, from) => {
        if (from &&
            ((from.startsWith('/chat') && to.startsWith('/chatbox')) ||
                (from.startsWith('/chatbox') && to.startsWith('/chat')))) {
            return;
        }

        if (to.startsWith('/chat/') || to.startsWith('/chatbox/')) {
            const pathSessionId = to.split('/')[2];
            if (pathSessionId && pathSessionId !== currSessionId.value) {
                if (sessions.value.length > 0) {
                    const session = sessions.value.find(s => s.session_id === pathSessionId);
                    if (session) {
                        handleSelectConversation([pathSessionId]);
                    }
                } else {
                    pendingSessionId.value = pathSessionId;
                }
            }
        }
    },
    { immediate: true }
);

// 会话列表加载后处理待定会话
watch(sessions, (newSessions) => {
    if (pendingSessionId.value && newSessions.length > 0) {
        const session = newSessions.find(s => s.session_id === pendingSessionId.value);
        if (session) {
            selectedSessions.value = [pendingSessionId.value];
            handleSelectConversation([pendingSessionId.value]);
            pendingSessionId.value = null;
        }
    } else if (!currSessionId.value && newSessions.length > 0) {
        const firstSession = newSessions[0];
        selectedSessions.value = [firstSession.session_id];
        handleSelectConversation([firstSession.session_id]);
    }
});

onMounted(() => {
    checkMobile();
    window.addEventListener('resize', checkMobile);
    getSessions();
});

onBeforeUnmount(() => {
    window.removeEventListener('resize', checkMobile);
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

.chat-page-card {
    width: 100%;
    height: 100%;
    max-height: 100%;
    overflow: hidden;
}

.chat-page-container {
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

/* 手机端遮罩层 */
.mobile-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background-color: rgba(0, 0, 0, 0.5);
    z-index: 999;
    animation: fadeIn 0.3s ease;
}

.chat-content-panel {
    height: 100%;
    max-height: 100%;
    width: 100%;
    display: flex;
    flex-direction: column;
    overflow: hidden;
}

.message-list-wrapper {
    flex: 1;
    position: relative;
    overflow: hidden;
    display: flex;
    flex-direction: column;
}

.message-list-fade {
    position: absolute;
    bottom: 0;
    left: 0;
    right: 0;
    height: 40px;
    background: linear-gradient(to top, rgba(255, 255, 255, 1) 0%, rgba(255, 255, 255, 0) 100%);
    pointer-events: none;
    z-index: 1;
}

.message-list-fade.fade-dark {
    background: linear-gradient(to top, rgba(30, 30, 30, 1) 0%, rgba(30, 30, 30, 0) 100%);
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

.mobile-menu-btn {
    margin-right: 8px;
}

.conversation-header-actions {
    display: flex;
    gap: 8px;
    align-items: center;
}

.fullscreen-icon {
    cursor: pointer;
    margin-left: 8px;
}

.welcome-container {
    height: 100%;
    display: flex;
    justify-content: center;
    align-items: center;
    flex-direction: column;
    position: relative;
}

.welcome-title {
    font-size: 28px;
    margin-bottom: 16px;
}

.loading-overlay-welcome {
    display: flex;
    justify-content: center;
    align-items: center;
}

.bot-name {
    font-weight: 700;
    margin-left: 8px;
    color: var(--v-theme-secondary);
}

.fade-in {
    animation: fadeIn 0.3s ease-in-out;
}

.dialog-title {
    font-size: 18px;
    font-weight: 500;
    padding-bottom: 8px;
}

/* 手机端样式调整 */
@media (max-width: 768px) {
    .chat-content-panel {
        width: 100%;
    }
    
    .chat-page-container {
        padding: 0 !important;
    }

    .conversation-header {
        padding: 2px;
    }
}
</style>
