<template>
    <v-card class="chat-page-card">
        <v-card-text class="chat-page-container">
            <div class="chat-layout">
                <div class="sidebar-panel" :class="{ 'sidebar-collapsed': sidebarCollapsed }"
                    :style="{ 'background-color': isDark ? sidebarCollapsed ? '#1e1e1e' : '#2d2d2d' : sidebarCollapsed ? '#ffffff' : '#f5f5f5' }"
                    @mouseenter="handleSidebarMouseEnter" @mouseleave="handleSidebarMouseLeave">

                    <div style="display: flex; align-items: center; justify-content: center; padding: 16px; padding-bottom: 0px;"
                        v-if="chatboxMode">
                        <img width="50" src="@/assets/images/astrbot_logo_mini.webp" alt="AstrBot Logo">
                        <span v-if="!sidebarCollapsed" style="font-weight: 1000; font-size: 26px; margin-left: 8px;"
                            class="text-secondary">AstrBot</span>
                    </div>


                    <div class="sidebar-collapse-btn-container">
                        <v-btn icon class="sidebar-collapse-btn" @click="toggleSidebar" variant="text"
                            color="deep-purple">
                            <v-icon>{{ (sidebarCollapsed || (!sidebarCollapsed && sidebarHoverExpanded)) ?
                                'mdi-chevron-right' : 'mdi-chevron-left' }}</v-icon>
                        </v-btn>
                    </div>

                    <div style="padding: 16px; padding-top: 8px;">
                        <v-btn block variant="text" class="new-chat-btn" @click="newC" :disabled="!currCid"
                            v-if="!sidebarCollapsed" prepend-icon="mdi-plus"
                            style="background-color: transparent !important; border-radius: 4px;">{{
                                tm('actions.newChat') }}</v-btn>
                        <v-btn icon="mdi-plus" rounded="lg" @click="newC" :disabled="!currCid" v-if="sidebarCollapsed"
                            elevation="0"></v-btn>
                    </div>
                    <div v-if="!sidebarCollapsed">
                        <v-divider class="mx-4"></v-divider>
                    </div>


                    <div style="overflow-y: auto; flex-grow: 1;" :class="{ 'fade-in': sidebarHoverExpanded }"
                        v-if="!sidebarCollapsed">
                        <v-card v-if="conversations.length > 0" flat style="background-color: transparent;">
                            <v-list density="compact" nav class="conversation-list"
                                style="background-color: transparent;" @update:selected="getConversationMessages">
                                <v-list-item v-for="(item, i) in conversations" :key="item.cid" :value="item.cid"
                                    rounded="lg" class="conversation-item" active-color="secondary">
                                    <v-list-item-title v-if="!sidebarCollapsed" class="conversation-title">{{ item.title
                                        || tm('conversation.newConversation') }}</v-list-item-title>
                                    <!-- <v-list-item-subtitle v-if="!sidebarCollapsed" class="timestamp">{{
                                        formatDate(item.updated_at)
                                        }}</v-list-item-subtitle> -->

                                    <template v-if="!sidebarCollapsed" v-slot:append>
                                        <div class="conversation-actions">
                                            <v-btn icon="mdi-pencil" size="x-small" variant="text"
                                                class="edit-title-btn"
                                                @click.stop="showEditTitleDialog(item.cid, item.title)" />
                                            <v-btn icon="mdi-delete" size="x-small" variant="text"
                                                class="delete-conversation-btn" color="error"
                                                @click.stop="deleteConversation(item.cid)" />
                                        </div>
                                    </template>
                                </v-list-item>
                            </v-list>
                        </v-card>

                        <v-fade-transition>
                            <div class="no-conversations" v-if="conversations.length === 0">
                                <v-icon icon="mdi-message-text-outline" size="large" color="grey-lighten-1"></v-icon>
                                <div class="no-conversations-text" v-if="!sidebarCollapsed || sidebarHoverExpanded">
                                    {{ tm('conversation.noHistory') }}</div>
                            </div>
                        </v-fade-transition>
                    </div>

                </div>

                <!-- 右侧聊天内容区域 -->
                <div class="chat-content-panel">

                    <div class="conversation-header fade-in">
                        <div class="conversation-header-content" v-if="currCid && getCurrentConversation">
                            <h2 class="conversation-header-title">{{ getCurrentConversation.title ||
                                tm('conversation.newConversation')
                                }}</h2>
                            <div class="conversation-header-time">{{ formatDate(getCurrentConversation.updated_at) }}
                            </div>
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

                    <div class="messages-container" ref="messageContainer">
                        <!-- 空聊天欢迎页 -->
                        <div class="welcome-container fade-in" v-if="messages.length == 0">
                            <div class="welcome-title">
                                <span>Hello, I'm</span>
                                <span class="bot-name">AstrBot ⭐</span>
                            </div>
                            <div class="welcome-hint">
                                <span>{{ t('core.common.type') }}</span>
                                <code>help</code>
                                <span>{{ tm('shortcuts.help') }} 😊</span>
                            </div>
                            <div class="welcome-hint">
                                <span>{{ t('core.common.longPress') }}</span>
                                <code>Ctrl + B</code>
                                <span>{{ tm('shortcuts.voiceRecord') }} 🎤</span>
                            </div>
                            <div class="welcome-hint">
                                <span>{{ t('core.common.press') }}</span>
                                <code>Ctrl + V</code>
                                <span>{{ tm('shortcuts.pasteImage') }} 🏞️</span>
                            </div>
                        </div>

                        <!-- 聊天消息列表 -->
                        <div v-else class="message-list">
                            <div class="message-item fade-in" v-for="(msg, index) in messages" :key="index">
                                <!-- 用户消息 -->
                                <div v-if="msg.type == 'user'" class="user-message">
                                    <div class="message-bubble user-bubble"
                                        :class="{ 'has-audio': msg.audio_url }"
                                        :style="{ backgroundColor: isDark ? '#2d2e30' : '#e7ebf4' }">
                                        <span>{{ msg.message }}</span>

                                        <!-- 图片附件 -->
                                        <div class="image-attachments" v-if="msg.image_url && msg.image_url.length > 0">
                                            <div v-for="(img, index) in msg.image_url" :key="index"
                                                class="image-attachment">
                                                <img :src="img" class="attached-image" @click="openImagePreview(img)" />
                                            </div>
                                        </div>

                                        <!-- 音频附件 -->
                                        <div class="audio-attachment" v-if="msg.audio_url && msg.audio_url.length > 0">
                                            <audio controls class="audio-player">
                                                <source :src="msg.audio_url" type="audio/wav">
                                                {{ t('messages.errors.browser.audioNotSupported') }}
                                            </audio>
                                        </div>
                                    </div>
                                </div>

                                <!-- 机器人消息 -->
                                <div v-else class="bot-message">
                                    <v-avatar class="bot-avatar" size="36">
                                        <span class="text-h2">✨</span>
                                    </v-avatar>
                                    <div class="bot-message-content">
                                        <div class="message-bubble bot-bubble">
                                            <div v-html="md.render(msg.message)" class="markdown-content"></div>
                                        </div>
                                        <div class="message-actions">
                                            <v-btn :icon="getCopyIcon(index)" size="small" variant="text"
                                                class="copy-message-btn"
                                                :class="{ 'copy-success': isCopySuccess(index) }"
                                                @click="copyBotMessage(msg.message, index)"
                                                :title="t('core.common.copy')" />
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- 输入区域 -->
                    <div class="input-area fade-in">
                        <div
                            style="width: 85%; max-width: 900px; margin: 0 auto; border: 1px solid #e0e0e0; border-radius: 24px; padding: 4px;">
                            <textarea id="input-field" v-model="prompt" @keydown="handleInputKeyDown"
                                @click:clear="clearMessage" placeholder="Ask AstrBot..."
                                style="width: 100%; resize: none; outline: none; border: 1px solid var(--v-theme-border); border-radius: 12px; padding: 12px 16px; min-height: 40px; font-family: inherit; font-size: 16px; background-color: var(--v-theme-surface);"></textarea>
                            <div
                                style="display: flex; justify-content: space-between; align-items: center; padding: 0px 8px;">
                                <div style="display: flex; justify-content: flex-start; margin-top: 8px;">
                                    <!-- 选择提供商和模型 -->
                                    <ProviderModelSelector ref="providerModelSelector" />
                                </div>
                                <div style="display: flex; justify-content: flex-end; margin-top: 8px;">
                                    <v-btn @click="sendMessage" icon="mdi-send" variant="text" color="deep-purple"
                                        :disabled="!prompt && stagedImagesName.length === 0 && !stagedAudioUrl"
                                        class="send-btn" size="small" />
                                    <v-btn @click="isRecording ? stopRecording() : startRecording()"
                                        :icon="isRecording ? 'mdi-stop-circle' : 'mdi-microphone'" variant="text"
                                        :color="isRecording ? 'error' : 'deep-purple'" class="record-btn"
                                        size="small" />
                                </div>
                            </div>

                        </div>

                        <!-- 附件预览区 -->
                        <div class="attachments-preview" v-if="stagedImagesUrl.length > 0 || stagedAudioUrl">
                            <div v-for="(img, index) in stagedImagesUrl" :key="index" class="image-preview">
                                <img :src="img" class="preview-image" />
                                <v-btn @click="removeImage(index)" class="remove-attachment-btn" icon="mdi-close"
                                    size="small" color="error" variant="text" />
                            </div>

                            <div v-if="stagedAudioUrl" class="audio-preview">
                                <v-chip color="deep-purple-lighten-4" class="audio-chip">
                                    <v-icon start icon="mdi-microphone" size="small"></v-icon>
                                    {{ tm('voice.recording') }}
                                </v-chip>
                                <v-btn @click="removeAudio" class="remove-attachment-btn" icon="mdi-close" size="small"
                                    color="error" variant="text" />
                            </div>
                        </div>
                    </div>
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
                <v-btn text @click="editTitleDialog = false" color="grey-darken-1">{{ t('core.common.cancel') }}</v-btn>
                <v-btn text @click="saveTitle" color="primary">{{ t('core.common.save') }}</v-btn>
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

<script>
import { router } from '@/router';
import axios from 'axios';
import MarkdownIt from 'markdown-it';
import { ref } from 'vue';
import { useCustomizerStore } from '@/stores/customizer';
import { useI18n, useModuleI18n } from '@/i18n/composables';
import LanguageSwitcher from '@/components/shared/LanguageSwitcher.vue';
import ProviderModelSelector from '@/components/chat/ProviderModelSelector.vue';
import hljs from 'highlight.js';
import 'highlight.js/styles/github.css';

// 配置markdown-it，启用代码高亮
const md = new MarkdownIt({
    html: false,        // 禁用HTML标签，防XSS
    breaks: true,       // 换行转<br>
    linkify: true,      // 自动转链接
    highlight: function (code, lang) {
        if (lang && hljs.getLanguage(lang)) {
            try {
                return hljs.highlight(code, { language: lang }).value;
            } catch (err) {
                console.error('Highlight error:', err);
            }
        }
        return hljs.highlightAuto(code).value;
    }
});

export default {
    name: 'ChatPage',
    components: {
        LanguageSwitcher,
        ProviderModelSelector
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
            md,
            ref
        };
    },
    data() {
        return {
            prompt: '',
            messages: [],
            conversations: [],
            currCid: '',
            stagedImagesName: [], // 用于存储图片**文件名**的数组
            stagedImagesUrl: [], // 用于存储图片的blob URL数组
            loadingChat: false,

            inputFieldLabel: '',

            isRecording: false,
            audioChunks: [],
            stagedAudioUrl: "",
            mediaRecorder: null,

            status: {},
            statusText: '',

            eventSource: null,
            eventSourceReader: null,

            // // Ctrl键长按相关变量
            ctrlKeyDown: false,
            ctrlKeyTimer: null,
            ctrlKeyLongPressThreshold: 300, // 长按阈值，单位毫秒

            mediaCache: {}, // Add a cache to store media blobs

            // 添加对话标题编辑相关变量
            editTitleDialog: false,
            editingTitle: '',
            editingCid: '',

            // 侧边栏折叠状态
            sidebarCollapsed: false,
            sidebarHovered: false,
            sidebarHoverTimer: null,
            sidebarHoverExpanded: false,
            sidebarHoverDelay: 100, // 悬停延迟，单位毫秒            
            pendingCid: null, // Store pending conversation ID for route handling

            // 复制成功提示
            copySuccessMessage: null,
            copySuccessTimeout: null,
            copiedMessages: new Set(), // 存储已复制的消息索引

            // 图片预览相关变量
            imagePreviewDialog: false,
            previewImageUrl: ''
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
        // Watch for route changes to handle direct navigation to /chat/<cid>
        '$route': {
            immediate: true,
            handler(to, from) {
                console.log('Route changed:', to.path, 'from:', from?.path);                // 如果是从不同的路由模式切换（chat <-> chatbox），重新建立SSE连接
                if (from &&
                    ((from.path.startsWith('/chat') && to.path.startsWith('/chatbox')) ||
                        (from.path.startsWith('/chatbox') && to.path.startsWith('/chat')))) {
                }

                // Check if the route matches /chat/<cid> or /chatbox/<cid> pattern
                if (to.path.startsWith('/chat/') || to.path.startsWith('/chatbox/')) {
                    const pathCid = to.path.split('/')[2];
                    console.log('Path CID:', pathCid);
                    if (pathCid && pathCid !== this.currCid) {
                        // If conversations are already loaded
                        if (this.conversations.length > 0) {
                            const conversation = this.conversations.find(c => c.cid === pathCid);
                            if (conversation) {
                                this.getConversationMessages([pathCid]);
                            }
                        } else {
                            // Store the cid to be used after conversations are loaded
                            this.pendingCid = pathCid;
                        }
                    }
                }
            }
        },

        // Watch for conversations loaded to handle pending cid
        conversations: {
            handler(newConversations) {
                if (this.pendingCid && newConversations.length > 0) {
                    const conversation = newConversations.find(c => c.cid === this.pendingCid);
                    if (conversation) {
                        this.getConversationMessages([this.pendingCid]);
                        this.pendingCid = null;
                    }
                }
            }
        }
    },

    mounted() {
        // Theme is now handled globally by the customizer store.
        // 设置输入框标签
        this.inputFieldLabel = this.tm('input.chatPrompt');
        this.checkStatus();
        this.getConversations();
        let inputField = document.getElementById('input-field');
        inputField.addEventListener('paste', this.handlePaste);
        inputField.addEventListener('keydown', function (e) {
            if (e.keyCode == 13 && !e.shiftKey) {
                e.preventDefault();
                // 检查是否有内容可发送
                if (this.canSendMessage()) {
                    this.sendMessage();
                }
            }
        }.bind(this));

        // 添加keyup事件监听
        document.addEventListener('keyup', this.handleInputKeyUp);

        // 从 localStorage 获取侧边栏折叠状态
        const savedCollapseState = localStorage.getItem('sidebarCollapsed');
        if (savedCollapseState !== null) {
            this.sidebarCollapsed = JSON.parse(savedCollapseState);
        }
    },

    beforeUnmount() {
        // 移除keyup事件监听
        document.removeEventListener('keyup', this.handleInputKeyUp);

        // 清除悬停定时器
        if (this.sidebarHoverTimer) {
            clearTimeout(this.sidebarHoverTimer);
        }

        // Cleanup blob URLs
        this.cleanupMediaCache();
    },
    methods: {
        toggleTheme() {
            const customizer = useCustomizerStore();
            const newTheme = customizer.uiTheme === 'PurpleTheme' ? 'PurpleThemeDark' : 'PurpleTheme';
            customizer.SET_UI_THEME(newTheme);
        },
        // 切换侧边栏折叠状态
        toggleSidebar() {
            if (this.sidebarHoverExpanded) {
                this.sidebarHoverExpanded = false;
                return
            }
            this.sidebarCollapsed = !this.sidebarCollapsed;
            // 保存折叠状态到 localStorage
            localStorage.setItem('sidebarCollapsed', JSON.stringify(this.sidebarCollapsed));
        },

        // 侧边栏鼠标悬停处理
        handleSidebarMouseEnter() {
            if (!this.sidebarCollapsed) return;

            this.sidebarHovered = true;

            // 设置延迟定时器
            this.sidebarHoverTimer = setTimeout(() => {
                if (this.sidebarHovered) {
                    this.sidebarHoverExpanded = true;
                    this.sidebarCollapsed = false;
                }
            }, this.sidebarHoverDelay);
        },

        handleSidebarMouseLeave() {
            this.sidebarHovered = false;

            // 清除定时器
            if (this.sidebarHoverTimer) {
                clearTimeout(this.sidebarHoverTimer);
                this.sidebarHoverTimer = null;
            }

            if (this.sidebarHoverExpanded) {
                this.sidebarCollapsed = true;
            }
            this.sidebarHoverExpanded = false;
        },

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
            axios.post('/api/chat/rename_conversation', {
                conversation_id: this.editingCid,
                title: trimmedTitle
            })
                .then(response => {
                    // 更新本地对话列表中的标题
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
            if (this.mediaCache[filename]) {
                return this.mediaCache[filename];
            }

            try {
                const response = await axios.get('/api/chat/get_file', {
                    params: { filename },
                    responseType: 'blob'
                });

                const blobUrl = URL.createObjectURL(response.data);
                this.mediaCache[filename] = blobUrl;
                return blobUrl;
            } catch (error) {
                console.error('Error fetching media file:', error);
                return '';
            }
        },


        showConnectionStatus(message, type) {
            // You can implement a toast notification here or update UI status
            console.log(`Connection status: ${message} (${type})`);
        },

        removeAudio() {
            this.stagedAudioUrl = null;
        },

        openImagePreview(imageUrl) {
            this.previewImageUrl = imageUrl;
            this.imagePreviewDialog = true;
        },

        initImageClickEvents() {
            this.$nextTick(() => {
                // 查找所有动态生成的图片（在markdown-content中）
                const images = document.querySelectorAll('.markdown-content img');
                images.forEach((img) => {
                    if (!img.hasAttribute('data-click-enabled')) {
                        img.style.cursor = 'pointer';
                        img.setAttribute('data-click-enabled', 'true');
                        img.onclick = () => this.openImagePreview(img.src);
                    }
                });
            });
        },

        checkStatus() {
            axios.get('/api/chat/status').then(response => {
                console.log(response.data);
                this.status = response.data.data;
            }).catch(err => {
                console.error(err);
            });
        },

        async startRecording() {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            this.mediaRecorder = new MediaRecorder(stream);
            this.mediaRecorder.ondataavailable = (event) => {
                this.audioChunks.push(event.data);
            };
            this.mediaRecorder.start();
            this.isRecording = true;
            this.inputFieldLabel = this.tm('input.recordingPrompt');
        },

        async stopRecording() {
            this.isRecording = false;
            this.inputFieldLabel = this.tm('input.chatPrompt');
            this.mediaRecorder.stop();
            this.mediaRecorder.onstop = async () => {
                const audioBlob = new Blob(this.audioChunks, { type: 'audio/wav' });
                this.audioChunks = [];

                this.mediaRecorder.stream.getTracks().forEach(track => track.stop());

                const formData = new FormData();
                formData.append('file', audioBlob);

                try {
                    const response = await axios.post('/api/chat/post_file', formData, {
                        headers: {
                            'Content-Type': 'multipart/form-data'
                        }
                    });

                    const audio = response.data.data.filename;
                    console.log('Audio uploaded:', audio);

                    this.stagedAudioUrl = audio; // Store just the filename
                } catch (err) {
                    console.error('Error uploading audio:', err);
                }
            };
        },

        async handlePaste(event) {
            console.log('Pasting image...');
            const items = event.clipboardData.items;
            for (let i = 0; i < items.length; i++) {
                if (items[i].type.indexOf('image') !== -1) {
                    const file = items[i].getAsFile();
                    const formData = new FormData();
                    formData.append('file', file);

                    try {
                        const response = await axios.post('/api/chat/post_image', formData, {
                            headers: {
                                'Content-Type': 'multipart/form-data'
                            }
                        });

                        const img = response.data.data.filename;
                        this.stagedImagesName.push(img); // Store just the filename
                        this.stagedImagesUrl.push(URL.createObjectURL(file)); // Create a blob URL for immediate display

                    } catch (err) {
                        console.error('Error uploading image:', err);
                    }
                }
            }
        },

        removeImage(index) {
            this.stagedImagesName.splice(index, 1);
            this.stagedImagesUrl.splice(index, 1);
        },

        clearMessage() {
            this.prompt = '';
        },
        getConversations() {
            axios.get('/api/chat/conversations').then(response => {
                this.conversations = response.data.data;

                // If there's a pending conversation ID from the route
                if (this.pendingCid) {
                    const conversation = this.conversations.find(c => c.cid === this.pendingCid);
                    if (conversation) {
                        this.getConversationMessages([this.pendingCid]);
                        this.pendingCid = null;
                    }
                }
            }).catch(err => {
                if (err.response.status === 401) {
                    this.$router.push('/auth/login?redirect=/chatbox');
                }
                console.error(err);
            });
        },
        getConversationMessages(cid) {
            if (!cid[0])
                return;

            // Update the URL to reflect the selected conversation
            if (this.$route.path !== `/chat/${cid[0]}` && this.$route.path !== `/chatbox/${cid[0]}`) {
                if (this.$route.path.startsWith('/chatbox')) {
                    this.$router.push(`/chatbox/${cid[0]}`);
                } else {
                    this.$router.push(`/chat/${cid[0]}`);
                }
            }


            axios.get('/api/chat/get_conversation?conversation_id=' + cid[0]).then(async response => {
                this.currCid = cid[0];
                let message = JSON.parse(response.data.data.history);
                for (let i = 0; i < message.length; i++) {
                    if (message[i].message.startsWith('[IMAGE]')) {
                        let img = message[i].message.replace('[IMAGE]', '');
                        const imageUrl = await this.getMediaFile(img);
                        message[i].message = `<img src="${imageUrl}" style="max-width: 80%; border-radius: 8px; box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);"/>`
                    }
                    if (message[i].message.startsWith('[RECORD]')) {
                        let audio = message[i].message.replace('[RECORD]', '');
                        const audioUrl = await this.getMediaFile(audio);
                        message[i].message = `<audio controls class="audio-player">
                                    <source src="${audioUrl}" type="audio/wav">
                                    ${this.t('messages.errors.browser.audioNotSupported')}
                                  </audio>`
                    }
                    if (message[i].image_url && message[i].image_url.length > 0) {
                        for (let j = 0; j < message[i].image_url.length; j++) {
                            message[i].image_url[j] = await this.getMediaFile(message[i].image_url[j]);
                        }
                    }
                    if (message[i].audio_url) {
                        message[i].audio_url = await this.getMediaFile(message[i].audio_url);
                    }
                }
                this.messages = message;
                this.initCodeCopyButtons();
                this.initImageClickEvents();
            }).catch(err => {
                console.error(err);
            });
        },
        async newConversation() {
            return axios.get('/api/chat/new_conversation').then(response => {
                const cid = response.data.data.conversation_id;
                this.currCid = cid;
                // Update the URL to reflect the new conversation
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
            this.messages = [];
            if (this.$route.path.startsWith('/chatbox')) {
                this.$router.push('/chatbox');
            } else {
                this.$router.push('/chat');
            }
        },

        formatDate(timestamp) {
            const date = new Date(timestamp * 1000); // 假设时间戳是以秒为单位
            const options = {
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit',
                hour12: false
            };
            // 使用当前语言环境的locale
            const locale = this.t('core.common.locale') || 'zh-CN';
            return date.toLocaleString(locale, options).replace(/\//g, '-').replace(/, /g, ' ');
        },

        deleteConversation(cid) {
            axios.get('/api/chat/delete_conversation?conversation_id=' + cid).then(response => {
                this.getConversations();
                this.currCid = '';
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

            // Create a message object with actual URLs for display
            const userMessage = {
                type: 'user',
                message: this.prompt.trim(), // 使用 trim() 去除前后空格
                image_url: [],
                audio_url: null
            };

            // Convert image filenames to blob URLs for display
            if (this.stagedImagesName.length > 0) {
                for (let i = 0; i < this.stagedImagesName.length; i++) {
                    // If it's just a filename, get the blob URL
                    if (!this.stagedImagesName[i].startsWith('blob:')) {
                        const imgUrl = await this.getMediaFile(this.stagedImagesName[i]);
                        userMessage.image_url.push(imgUrl);
                    } else {
                        userMessage.image_url.push(this.stagedImagesName[i]);
                    }
                }
            }

            // Convert audio filename to blob URL for display
            if (this.stagedAudioUrl) {
                if (!this.stagedAudioUrl.startsWith('blob:')) {
                    userMessage.audio_url = await this.getMediaFile(this.stagedAudioUrl);
                } else {
                    userMessage.audio_url = this.stagedAudioUrl;
                }
            }

            this.messages.push(userMessage);
            this.scrollToBottom();

            this.loadingChat = true

            // 从ProviderModelSelector组件获取当前选择
            const selection = this.$refs.providerModelSelector?.getCurrentSelection();
            const selectedProviderId = selection?.providerId || '';
            const selectedModelName = selection?.modelName || '';

            try {
                const response = await fetch('/api/chat/send', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': 'Bearer ' + localStorage.getItem('token')
                    },
                    body: JSON.stringify({
                        message: this.prompt.trim(), // 确保发送的消息已去除前后空格
                        conversation_id: this.currCid,
                        image_url: this.stagedImagesName,
                        audio_url: this.stagedAudioUrl ? [this.stagedAudioUrl] : [],
                        selected_provider: selectedProviderId,
                        selected_model: selectedModelName
                    })
                });

                this.prompt = ''; // 清空输入框;

                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }

                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let in_streaming = false;
                let message_obj = null;

                while (true) {
                    try {
                        const { done, value } = await reader.read();
                        if (done) {
                            console.log('SSE stream completed');
                            break;
                        }

                        const chunk = decoder.decode(value, { stream: true });
                        const lines = chunk.split('\n\n');

                        for (let i = 0; i < lines.length; i++) {
                            let line = lines[i].trim();

                            if (!line) {
                                continue;
                            }

                            // Parse SSE data
                            let chunk_json;
                            try {
                                chunk_json = JSON.parse(line.replace('data: ', ''));
                            } catch (parseError) {
                                console.warn('JSON解析失败:', line, parseError);
                                continue;
                            }

                            // 检查解析后的数据是否有效
                            if (!chunk_json || typeof chunk_json !== 'object' || !chunk_json.hasOwnProperty('type')) {
                                console.warn('无效的数据对象:', chunk_json);
                                continue;
                            }

                            if (chunk_json.type === 'heartbeat') {
                                continue; // 心跳包
                            }
                            if (chunk_json.type === 'error') {
                                console.error('Error received:', chunk_json.data);
                                continue;
                            }

                            if (chunk_json.type === 'image') {
                                let img = chunk_json.data.replace('[IMAGE]', '');
                                const imageUrl = await this.getMediaFile(img);
                                let bot_resp = {
                                    type: 'bot',
                                    message: `<img src="${imageUrl}" style="max-width: 80%; border-radius: 8px; box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);"/>`
                                }
                                this.messages.push(bot_resp);
                            } else if (chunk_json.type === 'record') {
                                let audio = chunk_json.data.replace('[RECORD]', '');
                                const audioUrl = await this.getMediaFile(audio);
                                let bot_resp = {
                                    type: 'bot',
                                    message: `<audio controls class="audio-player">
                                        <source src="${audioUrl}" type="audio/wav">
                                        ${this.t('messages.errors.browser.audioNotSupported')}
                                      </audio>`
                                }
                                this.messages.push(bot_resp);
                            } else if (chunk_json.type === 'plain') {
                                if (!in_streaming) {
                                    message_obj = {
                                        type: 'bot',
                                        message: this.ref(chunk_json.data),
                                    }
                                    this.messages.push(message_obj);
                                    in_streaming = true;
                                } else {
                                    message_obj.message.value += chunk_json.data;
                                }
                            } else if (chunk_json.type === 'end') {
                                in_streaming = false;
                                // 在消息流结束后初始化代码复制按钮和图片点击事件
                                this.initCodeCopyButtons();
                                this.initImageClickEvents();
                                continue;
                            } else if (chunk_json.type === 'update_title') {
                                // 更新对话标题
                                const conversation = this.conversations.find(c => c.cid === chunk_json.cid);
                                if (conversation) {
                                    conversation.title = chunk_json.data;
                                }
                            } else {
                                console.warn('未知数据类型:', chunk_json.type);
                            }
                            this.scrollToBottom();
                        }
                    } catch (readError) {
                        console.error('SSE读取错误:', readError);
                        break;
                    }
                }

                // Clear input after successful send
                this.prompt = '';
                this.stagedImagesName = [];
                this.stagedImagesUrl = [];
                this.stagedAudioUrl = "";
                this.loadingChat = false;

                // get the latest conversations
                this.getConversations();

            } catch (err) {
                console.error('发送消息失败:', err);
                this.loadingChat = false;
                this.showConnectionStatus(this.tm('connection.status.failed'), 'error');
            }
        },

        scrollToBottom() {
            this.$nextTick(() => {
                const container = this.$refs.messageContainer;
                container.scrollTop = container.scrollHeight;
                // 在滚动后初始化代码复制按钮和图片点击事件
                this.initCodeCopyButtons();
                this.initImageClickEvents();
            });
        },
        handleInputKeyDown(e) {
            if (e.ctrlKey && e.keyCode === 66) { // Ctrl+B组合键
                e.preventDefault(); // 防止默认行为

                // 防止重复触发
                if (this.ctrlKeyDown) return;

                this.ctrlKeyDown = true;

                // 设置定时器识别长按
                this.ctrlKeyTimer = setTimeout(() => {
                    if (this.ctrlKeyDown && !this.isRecording) {
                        this.startRecording();
                    }
                }, this.ctrlKeyLongPressThreshold);
            }
        },
        handleInputKeyUp(e) {
            if (e.keyCode === 66) { // B键释放
                this.ctrlKeyDown = false;

                // 清除定时器
                if (this.ctrlKeyTimer) {
                    clearTimeout(this.ctrlKeyTimer);
                    this.ctrlKeyTimer = null;
                }

                // 如果正在录音，停止录音
                if (this.isRecording) {
                    this.stopRecording();
                }
            }
        },

        cleanupMediaCache() {
            Object.values(this.mediaCache).forEach(url => {
                if (url.startsWith('blob:')) {
                    URL.revokeObjectURL(url);
                }
            });
            this.mediaCache = {};
        },

        // 复制代码到剪贴板
        copyCodeToClipboard(code) {
            navigator.clipboard.writeText(code).then(() => {
                console.log('代码已复制到剪贴板');
            }).catch(err => {
                console.error('复制失败:', err);
                // 如果现代API失败，使用传统方法
                const textArea = document.createElement('textarea');
                textArea.value = code;
                document.body.appendChild(textArea);
                textArea.select();
                try {
                    document.execCommand('copy');
                    console.log('代码已复制到剪贴板 (fallback)');
                } catch (fallbackErr) {
                    console.error('复制失败 (fallback):', fallbackErr);
                }
                document.body.removeChild(textArea);
            });
        },

        // 复制bot消息到剪贴板
        copyBotMessage(message, messageIndex) {
            // 移除HTML标签，获取纯文本
            const tempDiv = document.createElement('div');
            tempDiv.innerHTML = message;
            const plainText = tempDiv.textContent || tempDiv.innerText || message;

            navigator.clipboard.writeText(plainText).then(() => {
                console.log('消息已复制到剪贴板');
                this.showCopySuccess(messageIndex);
            }).catch(err => {
                console.error('复制失败:', err);
                // 如果现代API失败，使用传统方法
                const textArea = document.createElement('textarea');
                textArea.value = plainText;
                document.body.appendChild(textArea);
                textArea.select();
                try {
                    document.execCommand('copy');
                    console.log('消息已复制到剪贴板 (fallback)');
                    this.showCopySuccess(messageIndex);
                } catch (fallbackErr) {
                    console.error('复制失败 (fallback):', fallbackErr);
                }
                document.body.removeChild(textArea);
            });
        },

        // 显示复制成功提示
        showCopySuccess(messageIndex) {
            this.copiedMessages.add(messageIndex);

            // 2秒后移除成功状态
            setTimeout(() => {
                this.copiedMessages.delete(messageIndex);
            }, 2000);
        },

        // 获取复制按钮图标
        getCopyIcon(messageIndex) {
            return this.copiedMessages.has(messageIndex) ? 'mdi-check' : 'mdi-content-copy';
        },

        // 检查是否为复制成功状态
        isCopySuccess(messageIndex) {
            return this.copiedMessages.has(messageIndex);
        },

        // 获取复制图标SVG
        getCopyIconSvg() {
            return '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>';
        },

        // 获取成功图标SVG
        getSuccessIconSvg() {
            return '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20,6 9,17 4,12"></polyline></svg>';
        },

        // 初始化代码块复制按钮
        initCodeCopyButtons() {
            this.$nextTick(() => {
                const codeBlocks = this.$refs.messageContainer?.querySelectorAll('pre code') || [];
                codeBlocks.forEach((codeBlock, index) => {
                    const pre = codeBlock.parentElement;
                    if (pre && !pre.querySelector('.copy-code-btn')) {
                        const button = document.createElement('button');
                        button.className = 'copy-code-btn';
                        button.innerHTML = this.getCopyIconSvg();
                        button.title = '复制代码';
                        button.addEventListener('click', () => {
                            this.copyCodeToClipboard(codeBlock.textContent);
                            // 显示复制成功提示
                            button.innerHTML = this.getSuccessIconSvg();
                            button.style.color = '#4caf50';
                            setTimeout(() => {
                                button.innerHTML = this.getCopyIconSvg();
                                button.style.color = '';
                            }, 2000);
                        });
                        pre.style.position = 'relative';
                        pre.appendChild(button);
                    }
                });
            });
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
    height: calc(100vh - 84px);
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

.messages-container {
    height: 100%;
    max-height: 100%;
    overflow-y: auto;
    padding: 16px;
    display: flex;
    flex-direction: column;
    flex: 1;
    min-height: 0;
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
    color: var(--v-theme-secondaryText);
    font-size: 14px;
}

.welcome-hint code {
    background-color: var(--v-theme-codeBg);
    padding: 2px 6px;
    margin: 0 4px;
    border-radius: 4px;
    color: var(--v-theme-code);
    font-family: 'Fira Code', monospace;
    font-size: 13px;
}

/* 消息列表样式 */
.message-list {
    max-width: 900px;
    margin: 0 auto;
    width: 100%;
}

.message-item {
    margin-bottom: 24px;
    animation: fadeIn 0.3s ease-out;
}

.user-message {
    display: flex;
    justify-content: flex-end;
    align-items: flex-start;
    gap: 12px;
}

.bot-message {
    display: flex;
    justify-content: flex-start;
    align-items: flex-start;
    gap: 12px;
}

.bot-message-content {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    max-width: 80%;
    position: relative;
}

.message-actions {
    display: flex;
    gap: 4px;
    opacity: 0;
    transition: opacity 0.2s ease;
    margin-left: 8px;
}

.bot-message:hover .message-actions {
    opacity: 1;
}

.copy-message-btn {
    opacity: 0.6;
    transition: all 0.2s ease;
    color: var(--v-theme-secondary);
}

.copy-message-btn:hover {
    opacity: 1;
    background-color: rgba(103, 58, 183, 0.1);
}

.copy-message-btn.copy-success {
    color: #4caf50;
    opacity: 1;
}

.copy-message-btn.copy-success:hover {
    color: #4caf50;
    background-color: rgba(76, 175, 80, 0.1);
}

.message-bubble {
    padding: 8px 16px;
    border-radius: 12px;
}

.user-bubble {
    color: var(--v-theme-primaryText);
    padding: 18px 20px;
    font-size: 16px;
    max-width: 60%;
    border-radius: 1.5rem;
}

.bot-bubble {
    border: 1px solid var(--v-theme-border);
    color: var(--v-theme-primaryText);
}

.user-avatar,
.bot-avatar {
    align-self: flex-start;
    margin-top: 12px;
}

/* 附件样式 */
.image-attachments {
    display: flex;
    gap: 8px;
    margin-top: 8px;
    flex-wrap: wrap;
}

.image-attachment {
    position: relative;
    display: inline-block;
}

.attached-image {
    width: 120px;
    height: 120px;
    object-fit: cover;
    border-radius: 12px;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
    transition: transform 0.2s ease;
}

.attached-image:hover {
    transform: scale(1.02);
    cursor: pointer;
}

/* 图片预览对话框样式 */
.image-preview-card {
    background-color: var(--v-theme-surface) !important;
    border: 1px solid var(--v-theme-border);
}

/* 亮色主题下的图片预览对话框 */
.v-theme--light .image-preview-card,
.v-theme--PurpleTheme .image-preview-card {
    background-color: #ffffff !important;
    border-color: #e0e0e0 !important;
}

/* 暗色主题下的图片预览对话框 */
.v-theme--dark .image-preview-card,
.v-theme--PurpleThemeDark .image-preview-card {
    background-color: #1e1e1e !important;
    border-color: #333333 !important;
}

/* 确保对话框标题栏和内容区域的背景色 */
.image-preview-card .v-card-title {
    background-color: inherit;
}

.image-preview-card .v-card-text {
    background-color: inherit;
}

.preview-image-large {
    max-width: 100%;
    max-height: 75vh;
    width: auto;
    height: auto;
    border-radius: 8px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.audio-attachment {
    margin-top: 8px;
    min-width: 250px;
}

/* 包含音频的消息气泡最小宽度 */
.message-bubble.has-audio {
    min-width: 280px;
}

.audio-player {
    width: 100%;
    height: 36px;
    border-radius: 18px;
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

/* Markdown内容样式 */
.markdown-content {
    font-family: inherit;
    line-height: 1.6;
}

.markdown-content h1,
.markdown-content h2,
.markdown-content h3,
.markdown-content h4,
.markdown-content h5,
.markdown-content h6 {
    margin-top: 16px;
    margin-bottom: 10px;
    font-weight: 600;
    color: var(--v-theme-primaryText);
}

.markdown-content h1 {
    font-size: 1.8em;
    border-bottom: 1px solid var(--v-theme-border);
    padding-bottom: 6px;
}

.markdown-content h2 {
    font-size: 1.5em;
}

.markdown-content h3 {
    font-size: 1.3em;
}

.markdown-content li {
    margin-left: 16px;
    margin-bottom: 4px;
}

.markdown-content p {
    margin-top: 10px;
    margin-bottom: 10px;
}

.markdown-content pre {
    background-color: var(--v-theme-surface);
    padding: 12px;
    border-radius: 6px;
    overflow-x: auto;
    margin: 12px 0;
    position: relative;
}

.markdown-content code {
    background-color: var(--v-theme-codeBg);
    padding: 2px 4px;
    border-radius: 4px;
    font-family: 'Fira Code', monospace;
    font-size: 0.9em;
    color: var(--v-theme-code);
}

/* 代码块中的code标签样式 */
.markdown-content pre code {
    background-color: transparent;
    padding: 0;
    border-radius: 0;
    font-family: 'Fira Code', 'Consolas', 'Monaco', 'Courier New', monospace;
    font-size: 0.85em;
    color: inherit;
    display: block;
    overflow-x: auto;
    line-height: 1.5;
}

/* 自定义代码高亮样式 */
.markdown-content pre {
    border: 1px solid var(--v-theme-border);
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

/* 确保highlight.js的样式正确应用 */
.markdown-content pre code.hljs {
    background: transparent !important;
    color: inherit;
}

/* 亮色主题下的代码高亮 */
.v-theme--light .markdown-content pre {
    background-color: #f6f8fa;
}

/* 暗色主题下的代码块样式 */
.v-theme--dark .markdown-content pre {
    background-color: #0d1117 !important;
    border-color: rgba(255, 255, 255, 0.1);
}

.v-theme--dark .markdown-content pre code {
    color: #e6edf3 !important;
}

/* 暗色主题下的highlight.js样式覆盖 */
.v-theme--dark .hljs {
    background: #0d1117 !important;
    color: #e6edf3 !important;
}

.v-theme--dark .hljs-keyword,
.v-theme--dark .hljs-selector-tag,
.v-theme--dark .hljs-built_in,
.v-theme--dark .hljs-name,
.v-theme--dark .hljs-tag {
    color: #ff7b72 !important;
}

.v-theme--dark .hljs-string,
.v-theme--dark .hljs-title,
.v-theme--dark .hljs-section,
.v-theme--dark .hljs-attribute,
.v-theme--dark .hljs-literal,
.v-theme--dark .hljs-template-tag,
.v-theme--dark .hljs-template-variable,
.v-theme--dark .hljs-type,
.v-theme--dark .hljs-addition {
    color: #a5d6ff !important;
}

.v-theme--dark .hljs-comment,
.v-theme--dark .hljs-quote,
.v-theme--dark .hljs-deletion,
.v-theme--dark .hljs-meta {
    color: #8b949e !important;
}

.v-theme--dark .hljs-number,
.v-theme--dark .hljs-regexp,
.v-theme--dark .hljs-symbol,
.v-theme--dark .hljs-variable,
.v-theme--dark .hljs-template-variable,
.v-theme--dark .hljs-link,
.v-theme--dark .hljs-selector-attr,
.v-theme--dark .hljs-selector-pseudo {
    color: #79c0ff !important;
}

.v-theme--dark .hljs-function,
.v-theme--dark .hljs-class,
.v-theme--dark .hljs-title.class_ {
    color: #d2a8ff !important;
}

/* 复制按钮样式 */
.copy-code-btn {
    position: absolute;
    top: 8px;
    right: 8px;
    background: rgba(255, 255, 255, 0.9);
    border: 1px solid rgba(0, 0, 0, 0.1);
    border-radius: 4px;
    padding: 6px;
    cursor: pointer;
    opacity: 0;
    transition: all 0.2s ease;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #666;
    font-size: 12px;
    z-index: 10;
    backdrop-filter: blur(4px);
}

.copy-code-btn:hover {
    background: rgba(255, 255, 255, 1);
    color: #333;
    transform: scale(1.05);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
}

.copy-code-btn:active {
    transform: scale(0.95);
}

.markdown-content pre:hover .copy-code-btn {
    opacity: 1;
}

.v-theme--dark .copy-code-btn {
    background: rgba(45, 45, 45, 0.9);
    border-color: rgba(255, 255, 255, 0.15);
    color: #ccc;
}

.v-theme--dark .copy-code-btn:hover {
    background: rgba(45, 45, 45, 1);
    color: #fff;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
}

.markdown-content img {
    max-width: 100%;
    border-radius: 8px;
    margin: 10px 0;
}

.markdown-content blockquote {
    border-left: 4px solid var(--v-theme-secondary);
    padding-left: 16px;
    color: var(--v-theme-secondaryText);
    margin: 16px 0;
}

.markdown-content table {
    border-collapse: collapse;
    width: 100%;
    margin: 16px 0;
}

.markdown-content th,
.markdown-content td {
    border: 1px solid var(--v-theme-background);
    padding: 8px 12px;
    text-align: left;
}

.markdown-content th {
    background-color: var(--v-theme-containerBg);
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
    padding: 16px 16px 16px 16px;
    border-bottom: 1px solid var(--v-theme-border);
    width: 100%;
    padding-right: 32px;
    flex-shrink: 0;
}
</style>