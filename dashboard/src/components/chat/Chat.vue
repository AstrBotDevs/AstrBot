<template>
    <v-card class="chat-page-card">
        <v-card-text class="chat-page-container">
            <div class="chat-layout">
                <SidebarPanel
                  :chatboxMode="chatboxMode"
                  :conversations="conversations"
                  :selected="selectedConversations"
                  :currCid="currCid"
                  :isDark="isDark"
                  @update:selected="getConversationMessages"
                  @new="newC"
                  @edit-title="(p) => showEditTitleDialog(p.cid, p.title)"
                  @delete="deleteConversation"
                />

                <!-- 右侧聊天内容区域 -->
                <div class="chat-content-panel">

                    <div class="conversation-header fade-in">
                        <div v-if="currCid && getCurrentConversation">
                            <h3
                                style="max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                                {{ getCurrentConversation.title || tm('conversation.newConversation') }}</h3>
                            <span style="font-size: 12px;">{{ formatDate(getCurrentConversation.updated_at) }}</span>
                        </div>
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
                    <v-divider v-if="currCid && getCurrentConversation" class="conversation-divider"></v-divider>

                    <MessageList v-if="messages && messages.length > 0" :messages="messages" :isDark="isDark"
                        :isStreaming="isStreaming || isConvRunning" @openImagePreview="openImagePreview"
                        ref="messageList" />
                    <div class="welcome-container fade-in" v-else>
                        <div class="welcome-title">
                            <span>Hello, I'm</span>
                            <span class="bot-name">AstrBot ⭐</span>
                        </div>
                        <div class="welcome-hint markdown-content">
                            <span>{{ t('core.common.type') }}</span>
                            <code>help</code>
                            <span>{{ tm('shortcuts.help') }} 😊</span>
                        </div>
                        <div class="welcome-hint markdown-content">
                            <span>{{ t('core.common.longPress') }}</span>
                            <code>Ctrl + B</code>
                            <span>{{ tm('shortcuts.voiceRecord') }} 🎤</span>
                        </div>
                        <div class="welcome-hint markdown-content">
                            <span>{{ t('core.common.press') }}</span>
                            <code>Ctrl + V</code>
                            <span>{{ tm('shortcuts.pasteImage') }} 🏞️</span>
                        </div>
                    </div>

                    <!-- 输入区域 -->
                    <InputArea
                        :disabled="isStreaming || isConvRunning"
                        @send="onInputSend"
                    />

                </div>

            </div>
        </v-card-text>
    </v-card>
    <!-- 编辑对话标题对话框 -->
    <EditTitleDialog
        v-model="editTitleDialog"
        :title="editingTitle"
        :i18n="{ titleText: tm('actions.editTitle'), placeholder: tm('conversation.newConversation'), cancelText: t('core.common.cancel'), saveText: t('core.common.save') }"
        @save="saveTitle"
    />

    <!-- 图片预览对话框 -->
    <ImagePreviewDialog
        v-model="imagePreviewDialog"
        :title="t('core.common.imagePreview')"
        :imageUrl="previewImageUrl"
    />
</template>

<script>
import { router } from '@/router';
import { ref } from 'vue';
import { useCustomizerStore } from '@/stores/customizer';
import { useI18n, useModuleI18n } from '@/i18n/composables';
import LanguageSwitcher from '@/components/shared/LanguageSwitcher.vue';
import MessageList from '@/components/chat/MessageList.vue';
import { useToast } from '@/utils/toast';
// new components and service
import EditTitleDialog from '@/components/chat/EditTitleDialog.vue';
import ImagePreviewDialog from '@/components/chat/ImagePreviewDialog.vue';
import {
  listConversations,
  getConversation as apiGetConversation,
  newConversation as apiNewConversation,
  deleteConversation as apiDeleteConversation,
  renameConversation as apiRenameConversation,
  getFile as apiGetFile,
  sendMessageStream
} from '@/services/chat.api';
import { createMediaCache } from '@/composables/chat/useMediaCache';
import InputArea from '@/components/chat/InputArea.vue';
import { useChatStream } from '@/composables/chat/useChatStream';
import SidebarPanel from '@/components/chat/SidebarPanel.vue';
import { useChatRouteSync } from '@/composables/chat/useChatRouteSync';
import { formatTimestampSeconds } from '@/composables/chat/useDateFormat';

export default {
    name: 'ChatPage',
    components: {
        LanguageSwitcher,
        MessageList,
        // register new components
        EditTitleDialog,
        ImagePreviewDialog,
        InputArea,
        SidebarPanel
    },
    props: {
        chatboxMode: {
            type: Boolean,
            default: false
        }
    }, setup() {
        const { t } = useI18n();
        const { tm } = useModuleI18n('features/chat');

        return {
            t,
            tm,
            router,
            ref
        };
    },
    data() {
        const mediaCache = createMediaCache(apiGetFile);
        const { runStream } = useChatStream(mediaCache.getMediaUrl);
        return {
            prompt: '',
            messages: [],
            conversations: [],
            selectedConversations: [], // 用于控制左侧列表的选中状态
            currCid: '',
            stagedImagesName: [], // 用于存储图片文件名的数组
            loadingChat: false,

            inputFieldLabel: '',

            // 录音逻辑已迁移至 InputArea
            stagedAudioUrl: "",

            mediaCacheInst: mediaCache,
            runStream,

            // 添加对话标题编辑相关变量
            editTitleDialog: false,
            editingTitle: '',
            editingCid: '',

            pendingCid: null, // Store pending conversation ID for route handling

            // 图片预览相关变量
            imagePreviewDialog: false,
            previewImageUrl: '',

            isStreaming: false,
            isConvRunning: false, // Track if the current conversation is running

            isToastedRunningInfo: false, // To avoid multiple toasts
        }
    },

    computed: {
        isDark() {
            return useCustomizerStore().uiTheme === 'PurpleThemeDark';
        },
        // Get the current conversation from the conversations array
        getCurrentConversation() {
            if (!this.currCid) return null;
            return this.conversations.find(c => c.cid === this.currCid);
        }
    },

    watch: {
        '$route': {
            immediate: true,
            handler(to) {
                const { onRouteChange } = useChatRouteSync();
                onRouteChange(to, this.currCid, this.conversations, {
                    setPendingCid: (cid) => { this.pendingCid = cid; },
                    getConversationMessages: (cid) => this.getConversationMessages([cid]),
                });
            }
        },
        conversations: {
            handler(newConversations) {
                const { onConversationsChange } = useChatRouteSync();
                onConversationsChange(newConversations, this.currCid, this.pendingCid, {
                    selectAndOpen: (cid) => {
                        this.selectedConversations = [cid];
                        this.getConversationMessages([cid]);
                    },
                    clearPending: () => { this.pendingCid = null; },
                });
            }
        }
    },

    mounted() {
        // Theme is now handled globally by the customizer store.
        // 设置输入框标签
        this.inputFieldLabel = this.tm('input.chatPrompt');
        this.getConversations();
        // 输入与粘贴、快捷键逻辑交由 InputArea 组件内部处理
    },

    beforeUnmount() {
        // 移除keyup事件监听
        // 相关输入监听均已迁移到 InputArea 组件内，这里无需移除

        // Cleanup blob URLs
        this.cleanupMediaCache();
    },
    methods: {
        toggleTheme() {
            const customizer = useCustomizerStore();
            const newTheme = customizer.uiTheme === 'PurpleTheme' ? 'PurpleThemeDark' : 'PurpleTheme';
            customizer.SET_UI_THEME(newTheme);
        },
        // 侧边栏相关逻辑已迁移至 SidebarPanel 组件

        // 显示编辑对话标题对话框
        showEditTitleDialog(cid, title) {
            this.editingCid = cid;
            this.editingTitle = title || ''; // 如果标题为空，则设置为空字符串
            this.editTitleDialog = true;
        },

        // 保存对话标题
        saveTitle() {
            if (!this.editingCid) return;

            const trimmedTitle = this.editingTitle.trim();
            apiRenameConversation(this.editingCid, trimmedTitle)
                .then(() => {
                    const conversation = this.conversations.find(c => c.cid === this.editingCid);
                    if (conversation) {
                        conversation.title = trimmedTitle;
                    }
                    this.editTitleDialog = false;
                })
                .catch(err => {
                    console.error('重命名对话失败:', err);
                });
        },

        async getMediaFile(filename) {
            try {
                return await this.mediaCacheInst.getMediaUrl(filename);
            } catch (error) {
                console.error('Error fetching media file:', error);
                return '';
            }
        },
        // 输入相关热键、录音、粘贴与选择均已迁移至 InputArea 组件

        openImagePreview(imageUrl) {
            this.previewImageUrl = imageUrl;
            this.imagePreviewDialog = true;
        },

        // --- 小型内部助手：推送/更新 Bot 消息（用于流式回调） ---
        pushBotImage(imageUrl) {
            const bot_resp = { type: 'bot', message: '', embedded_images: [imageUrl] };
            this.messages.push({ content: bot_resp });
        },
        pushBotAudio(audioUrl) {
            const bot_resp = { type: 'bot', message: '', embedded_audio: audioUrl };
            this.messages.push({ content: bot_resp });
        },
        startBotText(text) {
            const obj = { type: 'bot', message: ref(text) };
            this.messages.push({ content: obj });
            return obj;
        },
        appendBotText(msgObj, text) {
            if (msgObj && msgObj.message && typeof msgObj.message.value === 'string') {
                msgObj.message.value += text;
            }
        },
        getConversations() {
            listConversations().then(data => {
                this.conversations = data;

                if (this.pendingCid) {
                    const conversation = this.conversations.find(c => c.cid === this.pendingCid);
                    if (conversation) {
                        this.getConversationMessages([this.pendingCid]);
                        this.pendingCid = null;
                    }
                } else {
                    if (!this.currCid && this.conversations.length > 0) {
                        const firstConversation = this.conversations[0];
                        this.selectedConversations = [firstConversation.cid];
                        this.getConversationMessages([firstConversation.cid]);
                    }
                }
            }).catch(err => {
                if (err?.response?.status === 401) {
                    this.$router.push('/auth/login?redirect=/chatbox');
                }
                console.error(err);
            });
        },
        getConversationMessages(cid) {
            if (!cid[0])
                return;

            if (this.$route.path !== `/chat/${cid[0]}` && this.$route.path !== `/chatbox/${cid[0]}`) {
                if (this.$route.path.startsWith('/chatbox')) {
                    this.$router.push(`/chatbox/${cid[0]}`);
                } else {
                    this.$router.push(`/chat/${cid[0]}`);
                }
                return
            }

            apiGetConversation(cid[0]).then(async data => {
                this.currCid = cid[0];
                this.selectedConversations = [cid[0]];
                let history = data.history;
                this.isConvRunning = data.is_running || false;

                if (this.isConvRunning) {
                    if (!this.isToastedRunningInfo) {
                        useToast().info("该对话正在运行中。", { timeout: 5000 });
                        this.isToastedRunningInfo = true;
                    }

                    setTimeout(() => {
                        this.getConversationMessages([this.currCid]);
                    }, 3000);
                }

                // 注意：MessageList 受 messages.length 控制渲染，需在赋值后再滚动

                for (let i = 0; i < history.length; i++) {
                    let content = history[i].content;
                    if (content.message.startsWith('[IMAGE]')) {
                        let img = content.message.replace('[IMAGE]', '');
                        const imageUrl = await this.getMediaFile(img);
                        if (!content.embedded_images) {
                            content.embedded_images = [];
                        }
                        content.embedded_images.push(imageUrl);
                        content.message = '';
                    }

                    if (content.message.startsWith('[RECORD]')) {
                        let audio = content.message.replace('[RECORD]', '');
                        const audioUrl = await this.getMediaFile(audio);
                        content.embedded_audio = audioUrl;
                        content.message = '';
                    }

                    if (content.image_url && content.image_url.length > 0) {
                        for (let j = 0; j < content.image_url.length; j++) {
                            content.image_url[j] = await this.getMediaFile(content.image_url[j]);
                        }
                    }

                    if (content.audio_url) {
                        content.audio_url = await this.getMediaFile(content.audio_url);
                    }
                }
                this.messages = history;
                this.$nextTick(() => {
                    const ml = this.$refs.messageList;
                    if (ml && typeof ml.scrollToBottom === 'function') {
                        ml.scrollToBottom();
                    }
                });
            }).catch(err => {
                console.error(err);
            });
        },
        async newConversation() {
            return apiNewConversation().then(data => {
                const cid = data.conversation_id;
                this.currCid = cid;
                if (this.$route.path.startsWith('/chatbox')) {
                    this.$router.push(`/chatbox/${cid}`);
                } else {
                    this.$router.push(`/chat/${cid}`);
                }
                this.getConversations();
                return cid;
            }).catch(err => {
                console.error(err);
                throw err;
            });
        },

        newC() {
            this.currCid = '';
            this.selectedConversations = []; // 清除选中状态
            this.messages = [];
            if (this.$route.path.startsWith('/chatbox')) {
                this.$router.push('/chatbox');
            } else {
                this.$router.push('/chat');
            }
        },

        formatDate(timestamp) {
            const locale = this.t('core.common.locale') || 'zh-CN';
            return formatTimestampSeconds(timestamp, locale);
        },

        deleteConversation(cid) {
            apiDeleteConversation(cid).then(() => {
                this.getConversations();
                this.currCid = '';
                this.selectedConversations = []; // 清除选中状态
                this.messages = [];
            }).catch(err => {
                console.error(err);
            });
        },

        // 检查是否可以发送消息
        canSendMessage() {
            return (this.prompt && this.prompt.trim()) ||
                this.stagedImagesName.length > 0 ||
                this.stagedAudioUrl;
        },

        async sendMessage() {
            // 检查是否有内容可发送
            if (!this.canSendMessage()) {
                console.log('没有内容可发送');
                return;
            }

            if (this.currCid == '') {
                const cid = await this.newConversation();
                // URL is already updated in newConversation method
            }

            // 保存当前要发送的数据到临时变量
            const promptToSend = this.prompt.trim();
            const imageNamesToSend = [...this.stagedImagesName];
            const audioNameToSend = this.stagedAudioUrl;

            // 立即清空输入和附件预览
            this.prompt = '';
            this.stagedImagesName = [];
            this.stagedAudioUrl = "";

            // Create a message object with actual URLs for display
            const userMessage = {
                type: 'user',
                message: promptToSend,
                image_url: [],
                audio_url: null
            };

            // Convert image filenames to blob URLs for display
            if (imageNamesToSend.length > 0) {
                const imagePromises = imageNamesToSend.map(name => {
                    if (!name.startsWith('blob:')) {
                        return this.getMediaFile(name);
                    }
                    return Promise.resolve(name);
                });
                userMessage.image_url = await Promise.all(imagePromises);
            }

            // Convert audio filename to blob URL for display
            if (audioNameToSend) {
                if (!audioNameToSend.startsWith('blob:')) {
                    userMessage.audio_url = await this.getMediaFile(audioNameToSend);
                } else {
                    userMessage.audio_url = audioNameToSend;
                }
            }

            this.messages.push({
                "content": userMessage,
            });
            this.loadingChat = true

            // 从ProviderModelSelector组件获取当前选择
            const selection = this._tempSelection || {};
            const selectedProviderId = selection?.providerId || '';
            const selectedModelName = selection?.modelName || '';
            this._tempSelection = null;

            try {
                const response = await sendMessageStream({
                    message: promptToSend,
                    conversation_id: this.currCid,
                    image_url: imageNamesToSend,
                    audio_url: audioNameToSend ? [audioNameToSend] : [],
                    selected_provider: selectedProviderId,
                    selected_model: selectedModelName
                });

                this.isStreaming = true;
                let message_obj = null;
                await this.runStream(response.body, {
                    onImage: async (imageUrl) => this.pushBotImage(imageUrl),
                    onAudio: async (audioUrl) => this.pushBotAudio(audioUrl),
                    onTextStart: (text) => { message_obj = this.startBotText(text); },
                    onTextAppend: (text) => this.appendBotText(message_obj, text),
                    onUpdateTitle: (cid, title) => {
                        const conversation = this.conversations.find((c) => c.cid === cid);
                        if (conversation) conversation.title = title;
                    },
                    onError: (err) => {
                        console.error('SSE读取错误:', err);
                    },
                });

                // Input and attachments are already cleared
                this.loadingChat = false;

                // get the latest conversations
                this.getConversations();

            } catch (err) {
                console.error('发送消息失败:', err);
                this.loadingChat = false;
            } finally {
                this.isStreaming = false;
            }
        },

        // 输入组件回传的发送事件处理
        onInputSend({ text, imageNames, audioName, selection }) {
            // 覆盖本组件的 prompt/staged 状态，以兼容后续 sendMessage 逻辑
            this.prompt = text;
            this.stagedImagesName = imageNames || [];
            this.stagedAudioUrl = audioName || '';

            // 将 Provider/Model 选择暂存到一个临时字段，供 sendMessage 使用
            this._tempSelection = selection || { providerId: '', modelName: '' };

            this.sendMessage();
        },

        cleanupMediaCache() {
            if (this.mediaCacheInst) this.mediaCacheInst.cleanup();
        },
    },
}
</script>

<style>
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

@keyframes pulse {
    0% {
        transform: scale(1);
    }

    50% {
        transform: scale(1.05);
    }

    100% {
        transform: scale(1);
    }
}

@keyframes slideIn {
    from {
        transform: translateX(20px);
        opacity: 0;
    }

    to {
        transform: translateX(0);
        opacity: 1;
    }
}

/* 添加淡入动画 */
@keyframes fadeInContent {
    from {
        opacity: 0;
    }

    to {
        opacity: 1;
    }
}

/* 欢迎页样式 */
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

.welcome-hint {
    margin-top: 8px;
    color: rgb(var(--v-theme-secondaryText));
    font-size: 14px;
}

.welcome-hint code {
    background-color: rgb(var(--v-theme-codeBg));
    padding: 2px 6px;
    margin: 0 4px;
    border-radius: 4px;
    font-family: 'Fira Code', monospace;
    font-size: 13px;
}

.fade-enter-active,
.fade-leave-active {
    transition: opacity 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
    opacity: 0;
}

.chat-page-card {
    width: 100%;
    height: 100%;
    max-height: 100%;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05) !important;
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

.sidebar-panel {
    max-width: 270px;
    min-width: 240px;
    display: flex;
    flex-direction: column;
    padding: 0;
    border-right: 1px solid rgba(0, 0, 0, 0.05);
    height: 100%;
    max-height: 100%;
    position: relative;
    transition: all 0.3s ease;
    overflow: hidden;
}

/* 侧边栏折叠状态 */
.sidebar-collapsed {
    max-width: 75px;
    min-width: 75px;
    transition: all 0.3s ease;
}

/* 当悬停展开时 */
.sidebar-collapsed.sidebar-hovered {
    max-width: 270px;
    min-width: 240px;
    transition: all 0.3s ease;
}

/* 侧边栏折叠按钮 */
.sidebar-collapse-btn-container {
    margin: 16px;
    margin-bottom: 0px;
    z-index: 10;
}

.sidebar-collapse-btn {
    opacity: 0.6;
    max-height: none;
    overflow-y: visible;
    padding: 0;
}

.conversation-item {
    margin-bottom: 4px;
    border-radius: 8px !important;
    transition: all 0.2s ease;
    height: auto !important;
    min-height: 56px;
    padding: 8px 16px !important;
    position: relative;
}

.conversation-item:hover {
    background-color: rgba(103, 58, 183, 0.05);
}

.conversation-item:hover .conversation-actions {
    opacity: 1;
    visibility: visible;
}

.conversation-actions {
    display: flex;
    gap: 4px;
    opacity: 0;
    visibility: hidden;
    transition: all 0.2s ease;
}

.edit-title-btn,
.delete-conversation-btn {
    opacity: 0.7;
    transition: opacity 0.2s ease;
}

.edit-title-btn:hover,
.delete-conversation-btn:hover {
    opacity: 1;
}

.conversation-title {
    font-weight: 500;
    font-size: 14px;
    line-height: 1.3;
    margin-bottom: 2px;
    transition: opacity 0.25s ease;
}

.timestamp {
    font-size: 11px;
    color: var(--v-theme-secondaryText);
    line-height: 1;
    transition: opacity 0.25s ease;
}

.sidebar-section-title {
    font-size: 12px;
    font-weight: 500;
    color: var(--v-theme-secondaryText);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 12px;
    padding-left: 4px;
    transition: opacity 0.25s ease;
    white-space: nowrap;
}

.status-chips {
    display: flex;
    flex-wrap: nowrap;
    gap: 8px;
    margin-bottom: 8px;
    transition: opacity 0.25s ease;
}

.status-chips .v-chip {
    flex: 1 1 0;
    justify-content: center;
    opacity: 0.7;
}

.status-chip {
    font-size: 12px;
    height: 24px !important;
}

.no-conversations {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 150px;
    opacity: 0.6;
    gap: 12px;
}

.no-conversations-text {
    font-size: 14px;
    color: var(--v-theme-secondaryText);
    transition: opacity 0.25s ease;
}

.chat-content-panel {
    height: 100%;
    max-height: 100%;
    width: 100%;
    display: flex;
    flex-direction: column;
    overflow: hidden;
}

/* 输入区域样式 */
.input-area {
    padding: 16px;
    background-color: var(--v-theme-surface);
    position: relative;
    border-top: 1px solid var(--v-theme-border);
    flex-shrink: 0;
    /* 防止输入区域被压缩 */
}

/* 附件预览区 */
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

/* 动画类 */
.fade-in {
    animation: fadeIn 0.3s ease-in-out;
}

/* 对话框标题样式 */
.dialog-title {
    font-size: 18px;
    font-weight: 500;
    padding-bottom: 8px;
}

/* 对话标题和时间样式 */
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
</style>