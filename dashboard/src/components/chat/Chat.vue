<template>
    <v-card class="chat-page-card" elevation="0" rounded="0">
        <v-card-text class="chat-page-container">
            <!-- 遮罩层 (手机端) -->
            <div class="mobile-overlay" v-if="isMobile && mobileMenuOpen" @click="closeMobileSidebar"></div>
            
            <div class="chat-layout">
                <ConversationSidebar
                    :conversations="conversations"
                    :selectedConversations="selectedConversations"
                    :currCid="currCid"
                    :isDark="isDark"
                    :chatboxMode="chatboxMode"
                    :isMobile="isMobile"
                    :mobileMenuOpen="mobileMenuOpen"
                    @newChat="handleNewChat"
                    @selectConversation="handleSelectConversation"
                    @editTitle="showEditTitleDialog"
                    @deleteConversation="handleDeleteConversation"
                    @closeMobileSidebar="closeMobileSidebar"
                />

                <!-- 右侧聊天内容区域 -->
                <div class="chat-content-panel">

                    <div class="conversation-header fade-in">
                        <!-- 手机端菜单按钮 -->
                        <v-btn icon class="mobile-menu-btn" @click="toggleMobileSidebar" v-if="isMobile" variant="text">
                            <v-icon>mdi-menu</v-icon>
                        </v-btn>
                        
                        <!-- <div v-if="currCid && getCurrentConversation">
                            <h3
                                style="max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                                {{ getCurrentConversation.title || tm('conversation.newConversation') }}</h3>
                            <span style="font-size: 12px;">{{ formatDate(getCurrentConversation.updated_at) }}</span>
                        </div> -->
                        <div class="conversation-header-actions">
                            <!-- router 推送到 /chatbox -->
                            <v-tooltip :text="tm('actions.fullscreen')" v-if="!chatboxMode">
                                <template v-slot:activator="{ props }">
                                    <v-icon v-bind="props"
                                        @click="router.push(currCid ? `/chatbox/${currCid}` : '/chatbox')"
                                        class="fullscreen-icon">mdi-fullscreen</v-icon>
                                </template>
                            </v-tooltip>
                            <!-- 语言切换按钮 -->
                            <v-tooltip :text="t('core.common.language')" v-if="chatboxMode">
                                <template v-slot:activator="{ props }">
                                    <LanguageSwitcher variant="chatbox" />
                                </template>
                            </v-tooltip>
                            <!-- 主题切换按钮 -->
                            <v-tooltip :text="isDark ? tm('modes.lightMode') : tm('modes.darkMode')" v-if="chatboxMode">
                                <template v-slot:activator="{ props }">
                                    <v-btn v-bind="props" icon @click="toggleTheme" class="theme-toggle-icon"
                                        size="small" rounded="sm" style="margin-right: 8px;" variant="text">
                                        <v-icon>{{ isDark ? 'mdi-weather-night' : 'mdi-white-balance-sunny' }}</v-icon>
                                    </v-btn>
                                </template>
                            </v-tooltip>
                            <!-- router 推送到 /chat -->
                            <v-tooltip :text="tm('actions.exitFullscreen')" v-if="chatboxMode">
                                <template v-slot:activator="{ props }">
                                    <v-icon v-bind="props" @click="router.push(currCid ? `/chat/${currCid}` : '/chat')"
                                        class="fullscreen-icon">mdi-fullscreen-exit</v-icon>
                                </template>
                            </v-tooltip>
                        </div>
                    </div>

                    <MessageList v-if="messages && messages.length > 0" :messages="messages" :isDark="isDark"
                        :isStreaming="isStreaming || isConvRunning" @openImagePreview="openImagePreview"
                        ref="messageList" />
                    <div class="welcome-container fade-in" v-else>
                        <div class="welcome-title">
                            <span>Hello, I'm</span>
                            <span class="bot-name">AstrBot ⭐</span>
                        </div>
                    </div>

                    <!-- 输入区域 -->
                    <ChatInput
                        v-model:prompt="prompt"
                        :stagedImagesUrl="stagedImagesUrl"
                        :stagedAudioUrl="stagedAudioUrl"
                        :disabled="isStreaming || isConvRunning"
                        :enableStreaming="enableStreaming"
                        :isRecording="isRecording"
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
import { useConversations } from '@/composables/useConversations';
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

// 使用 composables
const {
    conversations,
    selectedConversations,
    currCid,
    pendingCid,
    editTitleDialog,
    editingTitle,
    editingCid,
    getCurrentConversation,
    getConversations,
    newConversation,
    deleteConversation: deleteConv,
    showEditTitleDialog,
    saveTitle,
    updateConversationTitle,
    newChat
} = useConversations(props.chatboxMode);

const {
    stagedImagesName,
    stagedImagesUrl,
    stagedAudioUrl,
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
    getConversationMessages: getConvMessages,
    sendMessage: sendMsg,
    toggleStreaming
} = useMessages(currCid, getMediaFile, updateConversationTitle, getConversations);

// 组件引用
const messageList = ref<InstanceType<typeof MessageList> | null>(null);
const chatInputRef = ref<InstanceType<typeof ChatInput> | null>(null);

// 输入状态
const prompt = ref('');

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

function openImagePreview(imageUrl: string) {
    previewImageUrl.value = imageUrl;
    imagePreviewDialog.value = true;
}

async function handleSelectConversation(cids: string[]) {
    if (!cids[0]) return;

    // 更新 URL
    const basePath = props.chatboxMode ? '/chatbox' : '/chat';
    if (route.path !== `${basePath}/${cids[0]}`) {
        router.push(`${basePath}/${cids[0]}`);
        return;
    }

    // 手机端关闭侧边栏
    if (isMobile.value) {
        closeMobileSidebar();
    }

    currCid.value = cids[0];
    selectedConversations.value = [cids[0]];
    
    await getConvMessages(cids[0], router);
    
    nextTick(() => {
        messageList.value?.scrollToBottom();
    });
}

function handleNewChat() {
    newChat(closeMobileSidebar);
    messages.value = [];
}

async function handleDeleteConversation(cid: string) {
    await deleteConv(cid);
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
    for (const file of files) {
        await processAndUploadImage(file);
    }
}

async function handleSendMessage() {
    if (!prompt.value.trim() && stagedImagesName.value.length === 0 && !stagedAudioUrl.value) {
        return;
    }

    if (!currCid.value) {
        await newConversation();
    }

    const promptToSend = prompt.value.trim();
    const imageNamesToSend = [...stagedImagesName.value];
    const audioNameToSend = stagedAudioUrl.value;

    // 清空输入和附件
    prompt.value = '';
    clearStaged();

    // 获取选择的提供商和模型
    const selection = chatInputRef.value?.getCurrentSelection();
    const selectedProviderId = selection?.providerId || '';
    const selectedModelName = selection?.modelName || '';

    await sendMsg(
        promptToSend,
        imageNamesToSend,
        audioNameToSend,
        selectedProviderId,
        selectedModelName
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
            const pathCid = to.split('/')[2];
            if (pathCid && pathCid !== currCid.value) {
                if (conversations.value.length > 0) {
                    const conversation = conversations.value.find(c => c.cid === pathCid);
                    if (conversation) {
                        handleSelectConversation([pathCid]);
                    }
                } else {
                    pendingCid.value = pathCid;
                }
            }
        }
    },
    { immediate: true }
);

// 会话列表加载后处理待定会话
watch(conversations, (newConversations) => {
    if (pendingCid.value && newConversations.length > 0) {
        const conversation = newConversations.find(c => c.cid === pendingCid.value);
        if (conversation) {
            selectedConversations.value = [pendingCid.value];
            handleSelectConversation([pendingCid.value]);
            pendingCid.value = null;
        }
    } else if (!currCid.value && newConversations.length > 0) {
        const firstConversation = newConversations[0];
        selectedConversations.value = [firstConversation.cid];
        handleSelectConversation([firstConversation.cid]);
    }
});

onMounted(() => {
    checkMobile();
    window.addEventListener('resize', checkMobile);
    getConversations();
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
}

.welcome-title {
    font-size: 28px;
    margin-bottom: 16px;
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
}
</style>