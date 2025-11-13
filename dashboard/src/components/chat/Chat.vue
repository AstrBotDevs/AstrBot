<template>
    <v-card class="chat-page-card" elevation="0" rounded="0">
        <v-card-text class="chat-page-container">
            <!-- 遮罩层 (手机端) -->
            <div class="mobile-overlay" v-if="isMobile && mobileMenuOpen" @click="closeMobileSidebar"></div>
            
            <div class="chat-layout">
                <div class="sidebar-panel" 
                    :class="{ 
                        'sidebar-collapsed': sidebarCollapsed && !isMobile,
                        'mobile-sidebar-open': isMobile && mobileMenuOpen,
                        'mobile-sidebar': isMobile
                    }"
                    :style="{ 'background-color': isDark ? sidebarCollapsed ? '#1e1e1e' : '#2d2d2d' : sidebarCollapsed ? '#ffffff' : '#f1f4f9' }"
                    @mouseenter="handleSidebarMouseEnter" @mouseleave="handleSidebarMouseLeave">

                    <div style="display: flex; align-items: center; justify-content: center; padding: 16px; padding-bottom: 0px;"
                        v-if="chatboxMode">
                        <img width="50" src="@/assets/images/icon-no-shadow.svg" alt="AstrBot Logo">
                        <span v-if="!sidebarCollapsed"
                            style="font-weight: 1000; font-size: 26px; margin-left: 8px;">AstrBot</span>
                    </div>


                    <div class="sidebar-collapse-btn-container" v-if="!isMobile">
                        <v-btn icon class="sidebar-collapse-btn" @click="toggleSidebar" variant="text"
                            color="deep-purple">
                            <v-icon>{{ (sidebarCollapsed || (!sidebarCollapsed && sidebarHoverExpanded)) ?
                                'mdi-chevron-right' : 'mdi-chevron-left' }}</v-icon>
                        </v-btn>
                    </div>
                    <!-- 手机端关闭按钮 -->
                    <div class="sidebar-collapse-btn-container" v-if="isMobile">
                        <v-btn icon class="sidebar-collapse-btn" @click="closeMobileSidebar" variant="text"
                            color="deep-purple">
                            <v-icon>mdi-close</v-icon>
                        </v-btn>
                    </div>

                    <div style="padding: 16px; padding-top: 8px;">
                        <v-btn block variant="text" class="new-chat-btn" @click="newC" :disabled="!currCid"
                            v-if="!sidebarCollapsed || isMobile" prepend-icon="mdi-plus"
                            style="background-color: transparent !important; border-radius: 4px;">{{
                                tm('actions.newChat') }}</v-btn>
                        <v-btn icon="mdi-plus" rounded="lg" @click="newC" :disabled="!currCid" v-if="sidebarCollapsed && !isMobile"
                            elevation="0"></v-btn>
                    </div>
                    <div v-if="!sidebarCollapsed || isMobile">
                        <v-divider class="mx-4"></v-divider>
                    </div>


                    <div style="overflow-y: auto; flex-grow: 1;" :class="{ 'fade-in': sidebarHoverExpanded }"
                        v-if="!sidebarCollapsed || isMobile">
                        <v-card v-if="conversations.length > 0" flat style="background-color: transparent;">
                            <v-list density="compact" nav class="conversation-list"
                                style="background-color: transparent;" v-model:selected="selectedConversations"
                                @update:selected="getConversationMessages">
                                <v-list-item v-for="(item, i) in conversations" :key="item.cid" :value="item.cid"
                                    rounded="lg" class="conversation-item" active-color="secondary">
                                    <v-list-item-title v-if="!sidebarCollapsed || isMobile" class="conversation-title">{{ item.title
                                        || tm('conversation.newConversation') }}</v-list-item-title>
                                    <v-list-item-subtitle v-if="!sidebarCollapsed || isMobile" class="timestamp">{{
                                        formatDate(item.updated_at)
                                        }}</v-list-item-subtitle>

                                    <template v-if="!sidebarCollapsed || isMobile" v-slot:append>
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
                                <div class="no-conversations-text" v-if="!sidebarCollapsed || sidebarHoverExpanded || isMobile">
                                    {{ tm('conversation.noHistory') }}</div>
                            </div>
                        </v-fade-transition>
                    </div>

                </div>

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
                    <div class="input-area fade-in">
                        <div class="input-container"
                            style="width: 85%; max-width: 900px; margin: 0 auto; border: 1px solid #e0e0e0; border-radius: 24px;">
                            <textarea id="input-field" v-model="prompt" @keydown="handleInputKeyDown"
                                :disabled="isStreaming" @click:clear="clearMessage" placeholder="Ask AstrBot..."
                                style="width: 100%; resize: none; outline: none; border: 1px solid var(--v-theme-border); border-radius: 12px; padding: 8px 16px; min-height: 40px; font-family: inherit; font-size: 16px; background-color: var(--v-theme-surface);"></textarea>
                            <div
                                style="display: flex; justify-content: space-between; align-items: center; padding: 0px 12px;">
                                <div
                                    style="display: flex; justify-content: flex-start; margin-top: 4px; align-items: center; gap: 8px;">
                                    <!-- 选择提供商和模型 -->
                                    <ProviderModelSelector ref="providerModelSelector" />
                                    <!-- 流式响应开关 -->
                                    <v-tooltip
                                        :text="enableStreaming ? tm('streaming.enabled') : tm('streaming.disabled')"
                                        location="top">
                                        <template v-slot:activator="{ props }">
                                            <v-chip v-bind="props" @click="toggleStreaming" size="x-small"
                                                class="streaming-toggle-chip">
                                                <v-icon start :icon="enableStreaming ? 'mdi-flash' : 'mdi-flash-off'"
                                                    size="small"></v-icon>
                                                {{ enableStreaming ? tm('streaming.on') : tm('streaming.off') }}
                                            </v-chip>
                                        </template>
                                    </v-tooltip>
                                </div>
                                <div
                                    style="display: flex; justify-content: flex-end; margin-top: 8px; align-items: center;">
                                    <input type="file" ref="imageInput" @change="handleFileSelect" accept="image/*"
                                        style="display: none" multiple />
                                    <v-progress-circular v-if="isStreaming || isConvRunning" indeterminate size="16"
                                        class="mr-1" width="1.5" />
                                    <v-btn @click="triggerImageInput" icon="mdi-plus" variant="text" color="deep-purple"
                                        class="add-btn" size="small" />
                                    <v-btn @click="isRecording ? stopRecording() : startRecording()"
                                        :icon="isRecording ? 'mdi-stop-circle' : 'mdi-microphone'" variant="text"
                                        :color="isRecording ? 'error' : 'deep-purple'" class="record-btn"
                                        size="small" />
                                    <v-btn @click="sendMessage" icon="mdi-send" variant="text" color="deep-purple"
                                        :disabled="!prompt && stagedImagesName.length === 0 && !stagedAudioUrl"
                                        class="send-btn" size="small" />
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
import { ref } from 'vue';
import { useCustomizerStore } from '@/stores/customizer';
import { useI18n, useModuleI18n } from '@/i18n/composables';
import LanguageSwitcher from '@/components/shared/LanguageSwitcher.vue';
import ProviderModelSelector from '@/components/chat/ProviderModelSelector.vue';
import MessageList from '@/components/chat/MessageList.vue';
import 'highlight.js/styles/github.css';
import { useToast } from '@/utils/toast';
import { useTheme } from 'vuetify';

export default {
    name: 'ChatPage',
    components: {
        LanguageSwitcher,
        ProviderModelSelector,
        MessageList
    },
    props: {
        chatboxMode: {
            type: Boolean,
            default: false
        }
    }, setup() {
        const { t } = useI18n();
        const { tm } = useModuleI18n('features/chat');
        const theme = useTheme();

        return {
            t,
            tm,
            theme,
            router,
            ref
        };
    },
    data() {
        return {
            prompt: '',
            messages: [],
            conversations: [],
            selectedConversations: [], // 用于控制左侧列表的选中状态
            currCid: '',
            stagedImagesName: [], // 用于存储图片文件名的数组
            stagedImagesUrl: [], // 用于存储图片的blob URL数组
            loadingChat: false,

            inputFieldLabel: '',

            isRecording: false,
            audioChunks: [],
            stagedAudioUrl: "",
            mediaRecorder: null,

            // Ctrl键长按相关变量
            ctrlKeyDown: false,
            ctrlKeyTimer: null,
            ctrlKeyLongPressThreshold: 300, // 长按阈值,单位毫秒

            mediaCache: {}, // Add a cache to store media blobs

            // 添加对话标题编辑相关变量
            editTitleDialog: false,
            editingTitle: '',
            editingCid: '',

            // 侧边栏折叠状态
            sidebarCollapsed: true,
            sidebarHovered: false,
            sidebarHoverTimer: null,
            sidebarHoverExpanded: false,
            sidebarHoverDelay: 100, // 悬停延迟，单位毫秒            
            pendingCid: null, // Store pending conversation ID for route handling

            // 图片预览相关变量
            imagePreviewDialog: false,
            previewImageUrl: '',

            isStreaming: false,
            isConvRunning: false, // Track if the current conversation is running

            isToastedRunningInfo: false, // To avoid multiple toasts
            activeSSECount: 0, // Track number of active SSE connections

            // 流式响应开关
            enableStreaming: true, // 默认开启流式响应
            
            // 手机端相关变量
            isMobile: false,
            mobileMenuOpen: false,
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
                console.log('Route changed:', to.path, 'from:', from?.path);
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
                        // 先设置选中状态，然后加载对话消息
                        this.selectedConversations = [this.pendingCid];
                        this.getConversationMessages([this.pendingCid]);
                        this.pendingCid = null;
                    }
                } else {
                    // 如果没有URL参数指定的对话，且当前没有选中对话，则默认打开第一个对话
                    if (!this.currCid && newConversations.length > 0) {
                        const firstConversation = newConversations[0];
                        this.selectedConversations = [firstConversation.cid];
                        this.getConversationMessages([firstConversation.cid]);
                    }
                }
            }
        }
    },

    mounted() {
        // Theme is now handled globally by the customizer store.
        // 从 localStorage 读取侧边栏折叠状态，默认为 true（折叠）
        const savedCollapsedState = localStorage.getItem('sidebarCollapsed');
        if (savedCollapsedState !== null) {
            this.sidebarCollapsed = JSON.parse(savedCollapsedState);
        } else {
            this.sidebarCollapsed = true; // 默认折叠状态
        }

        // 从 localStorage 读取流式响应开关状态，默认为 true（开启）
        const savedStreamingState = localStorage.getItem('enableStreaming');
        if (savedStreamingState !== null) {
            this.enableStreaming = JSON.parse(savedStreamingState);
        } else {
            this.enableStreaming = true; // 默认开启
        }

        // 检测是否为手机端
        this.checkMobile();
        window.addEventListener('resize', this.checkMobile);

        // 设置输入框标签
        this.inputFieldLabel = this.tm('input.chatPrompt');
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
    },

    beforeUnmount() {
        // 移除keyup事件监听
        document.removeEventListener('keyup', this.handleInputKeyUp);
        
        // 移除resize事件监听
        window.removeEventListener('resize', this.checkMobile);

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
            this.theme.global.name.value = newTheme;
        },
        // 检测是否为手机端
        checkMobile() {
            this.isMobile = window.innerWidth <= 768;
            // 如果切换到桌面端，关闭手机菜单
            if (!this.isMobile) {
                this.mobileMenuOpen = false;
            }
        },
        // 切换手机端菜单
        toggleMobileSidebar() {
            this.mobileMenuOpen = !this.mobileMenuOpen;
        },
        // 关闭手机端菜单
        closeMobileSidebar() {
            this.mobileMenuOpen = false;
        },
        // 切换流式响应
        toggleStreaming() {
            this.enableStreaming = !this.enableStreaming;
            localStorage.setItem('enableStreaming', JSON.stringify(this.enableStreaming));
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
            if (!this.sidebarCollapsed || this.isMobile) return;

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

        removeAudio() {
            this.stagedAudioUrl = null;
        },

        openImagePreview(imageUrl) {
            this.previewImageUrl = imageUrl;
            this.imagePreviewDialog = true;
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

        async processAndUploadImage(file) {
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
        },

        async handlePaste(event) {
            console.log('Pasting image...');
            const items = event.clipboardData.items;
            for (let i = 0; i < items.length; i++) {
                if (items[i].type.indexOf('image') !== -1) {
                    const file = items[i].getAsFile();
                    this.processAndUploadImage(file);
                }
            }
        },

        removeImage(index) {
            // Revoke the blob URL to prevent memory leaks
            const urlToRevoke = this.stagedImagesUrl[index];
            if (urlToRevoke && urlToRevoke.startsWith('blob:')) {
                URL.revokeObjectURL(urlToRevoke);
            }

            this.stagedImagesName.splice(index, 1);
            this.stagedImagesUrl.splice(index, 1);
        },

        clearMessage() {
            this.prompt = '';
        },

        triggerImageInput() {
            this.$refs.imageInput.click();
        },

        handleFileSelect(event) {
            const files = event.target.files;
            if (files) {
                for (const file of files) {
                    this.processAndUploadImage(file);
                }
            }
            // Reset the input value to allow selecting the same file again
            event.target.value = '';
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
                } else {
                    // 如果没有URL参数指定的对话，且当前没有选中对话，则默认打开第一个对话
                    if (!this.currCid && this.conversations.length > 0) {
                        const firstConversation = this.conversations[0];
                        this.selectedConversations = [firstConversation.cid];
                        this.getConversationMessages([firstConversation.cid]);
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
                return
            }

            // 手机端关闭侧边栏
            if (this.isMobile) {
                this.closeMobileSidebar();
            }

            axios.get('/api/chat/get_conversation?conversation_id=' + cid[0]).then(async response => {
                this.currCid = cid[0];
                // Update the selected conversation in the sidebar
                this.selectedConversations = [cid[0]];
                let history = response.data.data.history;
                this.isConvRunning = response.data.data.is_running || false;

                if (this.isConvRunning) {
                    if (!this.isToastedRunningInfo) {
                        useToast().info("该对话正在运行中。", { timeout: 5000 });
                        this.isToastedRunningInfo = true;
                    }

                    // 如果对话还在运行，3秒后重新获取消息
                    setTimeout(() => {
                        this.getConversationMessages([this.currCid]);
                    }, 3000);
                }

                // 滚动到底部
                this.$nextTick(() => {
                    this.$refs.messageList.scrollToBottom();
                });

                for (let i = 0; i < history.length; i++) {
                    let content = history[i].content;
                    if (content.message.startsWith('[IMAGE]')) {
                        let img = content.message.replace('[IMAGE]', '');
                        const imageUrl = await this.getMediaFile(img);
                        if (!content.embedded_images) {
                            content.embedded_images = [];
                        }
                        content.embedded_images.push(imageUrl);
                        content.message = ''; // 清空message，避免显示标记文本
                    }

                    if (content.message.startsWith('[RECORD]')) {
                        let audio = content.message.replace('[RECORD]', '');
                        const audioUrl = await this.getMediaFile(audio);
                        content.embedded_audio = audioUrl;
                        content.message = ''; // 清空message，避免显示标记文本
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
            this.selectedConversations = []; // 清除选中状态
            this.messages = [];
            // 手机端关闭侧边栏
            if (this.isMobile) {
                this.closeMobileSidebar();
            }
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
            this.stagedImagesUrl = [];
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
            const selection = this.$refs.providerModelSelector?.getCurrentSelection();
            const selectedProviderId = selection?.providerId || '';
            const selectedModelName = selection?.modelName || '';

            try {
                this.activeSSECount++;
                if (this.activeSSECount === 1) {
                    this.isConvRunning = true;
                }
                const response = await fetch('/api/chat/send', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': 'Bearer ' + localStorage.getItem('token')
                    },
                    body: JSON.stringify({
                        message: promptToSend,
                        conversation_id: this.currCid,
                        image_url: imageNamesToSend,
                        audio_url: audioNameToSend ? [audioNameToSend] : [],
                        selected_provider: selectedProviderId,
                        selected_model: selectedModelName,
                        enable_streaming: this.enableStreaming
                    })
                });

                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }

                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let in_streaming = false;
                let message_obj = null;

                this.isStreaming = true

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

                            if (chunk_json.type === 'error') {
                                console.error('Error received:', chunk_json.data);
                                continue;
                            }

                            if (chunk_json.type === 'image') {
                                let img = chunk_json.data.replace('[IMAGE]', '');
                                const imageUrl = await this.getMediaFile(img);
                                let bot_resp = {
                                    type: 'bot',
                                    message: '',
                                    embedded_images: [imageUrl]
                                }
                                this.messages.push({
                                    "content": bot_resp
                                });
                            } else if (chunk_json.type === 'record') {
                                let audio = chunk_json.data.replace('[RECORD]', '');
                                const audioUrl = await this.getMediaFile(audio);
                                let bot_resp = {
                                    type: 'bot',
                                    message: '',
                                    embedded_audio: audioUrl
                                }
                                this.messages.push({
                                    "content": bot_resp
                                });
                            } else if (chunk_json.type === 'plain') {
                                const chain_type = chunk_json.chain_type || 'normal';
                                
                                if (!in_streaming) {
                                    message_obj = {
                                        type: 'bot',
                                        message: this.ref(chain_type === 'reasoning' ? '' : chunk_json.data),
                                        reasoning: this.ref(chain_type === 'reasoning' ? chunk_json.data : ''),
                                    }
                                    this.messages.push({
                                        "content": message_obj
                                    });
                                    in_streaming = true;
                                } else {
                                    if (chain_type === 'reasoning') {
                                        // Append to reasoning content
                                        message_obj.reasoning.value += chunk_json.data;
                                    } else {
                                        // Append to normal message
                                        message_obj.message.value += chunk_json.data;
                                    }
                                }
                            } else if (chunk_json.type === 'update_title') {
                                // 更新对话标题
                                const conversation = this.conversations.find(c => c.cid === chunk_json.cid);
                                if (conversation) {
                                    conversation.title = chunk_json.data;
                                }
                            }
                            if ((chunk_json.type === 'break' && chunk_json.streaming) || !chunk_json.streaming) {
                                // break means a segment end
                                in_streaming = false;
                                // 当SSE传入streaming=false时，恢复输入框
                                if (!chunk_json.streaming) {
                                    this.isStreaming = false;
                                }
                            }
                        }
                    } catch (readError) {
                        console.error('SSE读取错误:', readError);
                        break;
                    }
                }

                // Input and attachments are already cleared
                this.loadingChat = false;

                // get the latest conversations
                this.getConversations();

            } catch (err) {
                console.error('发送消息失败:', err);
                this.loadingChat = false;
            } finally {
                this.isStreaming = false;
                this.activeSSECount--;
                if (this.activeSSECount === 0) {
                    this.isConvRunning = false;
                }
            }
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

/* 流式响应开关芯片样式 */
.streaming-toggle-chip {
    cursor: pointer;
    transition: all 0.2s ease;
    user-select: none;
}

.streaming-toggle-chip:hover {
    opacity: 0.8;
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
    border-right: 1px solid rgba(0, 0, 0, 0.04);
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

/* 手机端菜单按钮 */
.mobile-menu-btn {
    margin-right: 8px;
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

/* 手机端侧边栏 */
.mobile-sidebar {
    position: fixed;
    top: 0;
    left: 0;
    bottom: 0;
    max-width: 280px !important;
    min-width: 280px !important;
    transform: translateX(-100%);
    transition: transform 0.3s ease;
    z-index: 1000;
}

.mobile-sidebar-open {
    transform: translateX(0) !important;
}

/* 手机端样式调整 */
@media (max-width: 768px) {
    .sidebar-panel:not(.mobile-sidebar) {
        display: none;
    }
    
    .chat-content-panel {
        width: 100%;
    }
    
    /* 手机端去掉容器padding */
    .chat-page-container {
        padding: 0 !important;
    }
    
    /* 手机端输入区域样式 */
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
    
    #input-field {
        border-radius: 0 !important;
        border-left: none !important;
        border-right: none !important;
    }
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

.v-chip {
    flex: 1 1 0;
    justify-content: center;
    opacity: 0.7;
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