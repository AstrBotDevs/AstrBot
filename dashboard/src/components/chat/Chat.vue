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

                    <ConversationHeader
                      :chatboxMode="chatboxMode"
                      :currCid="currCid"
                      :isDark="isDark"
                      :title="getCurrentConversation?.title"
                      :updatedAt="getCurrentConversation?.updated_at"
                      @toggle-theme="toggleTheme"
                      @fullscreen="router.push(currCid ? `/chatbox/${currCid}` : '/chatbox')"
                      @exit-fullscreen="router.push(currCid ? `/chat/${currCid}` : '/chat')"
                    />
                    <v-divider v-if="currCid && getCurrentConversation" class="conversation-divider"></v-divider>

                    <MessageList v-if="messages && messages.length > 0" :messages="messages" :isDark="isDark"
                        :isStreaming="isStreaming || isConvRunning" @openImagePreview="openImagePreview"
                        ref="messageList" />
                    <WelcomePanel v-else />

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
import MessageList from '@/components/chat/MessageList.vue';
import { useToast } from '@/utils/toast';
// new components and service
import EditTitleDialog from '@/components/chat/EditTitleDialog.vue';
import ImagePreviewDialog from '@/components/chat/ImagePreviewDialog.vue';
import ConversationHeader from '@/components/chat/ConversationHeader.vue';
import WelcomePanel from '@/components/chat/WelcomePanel.vue';
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
        MessageList,
        // register new components
        EditTitleDialog,
        ImagePreviewDialog,
        InputArea,
        SidebarPanel,
        ConversationHeader,
        WelcomePanel,
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

            // 临时缓存 Provider/Model 选择
            _tempSelection: null,
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
        // --- 通用小助手 ---
        scrollToBottomSafe() {
            this.$nextTick(() => {
                const ml = this.$refs.messageList;
                if (ml && typeof ml.scrollToBottom === 'function') {
                    ml.scrollToBottom();
                }
            });
        },
        async normalizeHistory(history) {
            for (let i = 0; i < history.length; i++) {
                const content = history[i].content || {};
                if (typeof content.message === 'string' && content.message.startsWith('[IMAGE]')) {
                    const img = content.message.replace('[IMAGE]', '');
                    const imageUrl = await this.getMediaFile(img);
                    if (!content.embedded_images) content.embedded_images = [];
                    content.embedded_images.push(imageUrl);
                    content.message = '';
                }
                if (typeof content.message === 'string' && content.message.startsWith('[RECORD]')) {
                    const audio = content.message.replace('[RECORD]', '');
                    const audioUrl = await this.getMediaFile(audio);
                    content.embedded_audio = audioUrl;
                    content.message = '';
                }
                if (Array.isArray(content.image_url) && content.image_url.length > 0) {
                    for (let j = 0; j < content.image_url.length; j++) {
                        content.image_url[j] = await this.getMediaFile(content.image_url[j]);
                    }
                }
                if (content.audio_url) {
                    content.audio_url = await this.getMediaFile(content.audio_url);
                }
            }
            return history;
        },
        ensureCorrectRoute(cid) {
            const wantChat = `/chat/${cid}`;
            const wantChatbox = `/chatbox/${cid}`;
            if (this.$route.path === wantChat || this.$route.path === wantChatbox) return true;
            if (this.$route.path.startsWith('/chatbox')) this.$router.push(wantChatbox);
            else this.$router.push(wantChat);
            return false;
        },
        async resolveImageNamesToUrls(names) {
            const imagePromises = (names || []).map((name) => {
                if (!name) return Promise.resolve('');
                if (!String(name).startsWith('blob:')) return this.getMediaFile(name);
                return Promise.resolve(name);
            });
            return Promise.all(imagePromises);
        },
        async resolveAudioNameToUrl(name) {
            if (!name) return null;
            if (!String(name).startsWith('blob:')) return this.getMediaFile(name);
            return name;
        },
        async createUserMessage(promptToSend, imageNamesToSend, audioNameToSend) {
            const userMessage = {
                type: 'user',
                message: promptToSend,
                image_url: [],
                audio_url: null,
            };
            if (imageNamesToSend?.length) {
                userMessage.image_url = await this.resolveImageNamesToUrls(imageNamesToSend);
            }
            if (audioNameToSend) {
                userMessage.audio_url = await this.resolveAudioNameToUrl(audioNameToSend);
            }
            return userMessage;
        },
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

            if (!this.ensureCorrectRoute(cid[0])) return;

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

                // 标准化并解析历史消息的媒体 URL
                await this.normalizeHistory(history);
                this.messages = history;
                // MessageList 受 messages 控制渲染，赋值后再滚动
                this.scrollToBottomSafe();
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

            // 构造展示用的用户消息（解析媒体 URL）
            const userMessage = await this.createUserMessage(
                promptToSend,
                imageNamesToSend,
                audioNameToSend,
            );

            this.messages.push({
                "content": userMessage,
            });
            this.scrollToBottomSafe();
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

<style src="./ChatPage.css"></style>