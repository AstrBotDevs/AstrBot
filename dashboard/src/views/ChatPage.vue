<script setup>
import { router } from '@/router';
import axios from 'axios';
import { marked } from 'marked';
import { ref } from 'vue';
import { defineProps } from 'vue';
import { useCustomizerStore } from '@/stores/customizer';

marked.setOptions({
    breaks: true
});

const props = defineProps({
    chatboxMode: {
        type: Boolean,
        default: false
    }
});
</script>

<template>
    <v-card class="chat-page-card">
        <v-card-text class="chat-page-container">
            <div class="chat-layout">
                <div class="sidebar-panel" :class="{ 'sidebar-collapsed': sidebarCollapsed }"
                    @mouseenter="handleSidebarMouseEnter" @mouseleave="handleSidebarMouseLeave">

                    <div style="display: flex; align-items: center; justify-content: center; padding: 16px; padding-bottom: 0px;" v-if="props.chatboxMode">
                        <img width="50" src="@/assets/images/astrbot_logo_mini.webp" alt="AstrBot Logo">
                        <span v-if="!sidebarCollapsed" style="font-weight: 1000; font-size: 26px; margin-left: 8px;" class="text-secondary">AstrBot</span>
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
                            v-if="!sidebarCollapsed" prepend-icon="mdi-plus" style="box-shadow: 0 1px 2px rgba(0,0,0,0.1); background-color: transparent !important; border-radius: 4px;">创建对话</v-btn>
                        <v-btn icon="mdi-plus" rounded="lg" @click="newC" :disabled="!currCid" v-if="sidebarCollapsed"
                            elevation="0"></v-btn>
                    </div>
                    <div v-if="!sidebarCollapsed">
                        <v-divider class="mx-2"></v-divider>
                    </div>

                    <div style="overflow-y: auto; flex-grow: 1;" class="sidebar-panel" :class="{ 'fade-in': sidebarHoverExpanded }"
                        v-if="!sidebarCollapsed">
                        <v-card class="conversation-list-card" v-if="conversations.length > 0" flat>
                            <v-list density="compact" nav class="conversation-list"
                                @update:selected="getConversationMessages">
                                <v-list-item v-for="(item, i) in conversations" :key="item.cid" :value="item.cid"
                                    rounded="lg" class="conversation-item" active-color="secondary">
                                    <v-list-item-title v-if="!sidebarCollapsed" class="conversation-title">{{ item.title
                                        || '新对话' }}</v-list-item-title>
                                    <!-- <v-list-item-subtitle v-if="!sidebarCollapsed" class="timestamp">{{
                                        formatDate(item.updated_at)
                                        }}</v-list-item-subtitle> -->

                                    <template v-if="!sidebarCollapsed" v-slot:append>
                                        <v-btn icon="mdi-pencil" size="x-small" variant="text" class="edit-title-btn"
                                            @click.stop="showEditTitleDialog(item.cid, item.title)" />
                                    </template>
                                </v-list-item>
                            </v-list>
                        </v-card>

                        <v-fade-transition>
                            <div class="no-conversations" v-if="conversations.length === 0">
                                <v-icon icon="mdi-message-text-outline" size="large" color="grey-lighten-1"></v-icon>
                                <div class="no-conversations-text" v-if="!sidebarCollapsed || sidebarHoverExpanded">
                                    暂无对话历史</div>
                            </div>
                        </v-fade-transition>
                    </div>

                    <div v-if="!sidebarCollapsed">
                        <v-divider class="mx-2"></v-divider>
                    </div>
                    <div style="padding: 16px;" :class="{ 'fade-in': sidebarHoverExpanded }"
                        v-if="!sidebarCollapsed">
                        <div class="sidebar-section-title">
                            系统状态
                        </div>
                        <div class="status-chips">
                            <v-chip class="status-chip" :color="status?.llm_enabled ? 'primary' : 'grey-lighten-2'"
                                variant="outlined" size="small" rounded="sm">
                                <template v-slot:prepend>
                                    <v-icon :icon="status?.llm_enabled ? 'mdi-check-circle' : 'mdi-alert-circle'"
                                        size="x-small"></v-icon>
                                </template>
                                <span>LLM 服务</span>
                            </v-chip>

                            <v-chip class="status-chip" :color="status?.stt_enabled ? 'success' : 'grey-lighten-2'"
                                variant="outlined" size="small" rounded="sm">
                                <template v-slot:prepend>
                                    <v-icon :icon="status?.stt_enabled ? 'mdi-check-circle' : 'mdi-alert-circle'"
                                        size="x-small"></v-icon>
                                </template>
                                <span>语音转文本</span>
                            </v-chip>
                        </div>

                        <transition
                            name="expand"
                            @before-enter="beforeEnter"
                            @enter="enter"
                            @after-enter="afterEnter"
                            @before-leave="beforeLeave"
                            @leave="leave"
                        >
                            <div v-if="currCid" class="delete-btn-container">
                                <v-btn variant="outlined" rounded="sm" class="delete-chat-btn"
                                    @click="deleteConversation(currCid)" color="error" density="comfortable" size="small">
                                    <v-icon start size="small">mdi-delete</v-icon>
                                    删除此对话
                                </v-btn>
                            </div>
                        </transition>
                    </div>
                </div>

                <!-- 右侧聊天内容区域 -->
                <div class="chat-content-panel">

                    <div class="conversation-header fade-in">
                        <div class="conversation-header-content" v-if="currCid && getCurrentConversation">
                            <h2 class="conversation-header-title">{{ getCurrentConversation.title || '新对话' }}</h2>
                            <div class="conversation-header-time">{{ formatDate(getCurrentConversation.updated_at) }}</div>
                        </div>
                        <div class="conversation-header-actions">
                            <!-- router 推送到 /chatbox -->
                            <v-tooltip text="全屏模式" v-if="!props.chatboxMode">
                                <template v-slot:activator="{ props }">
                                    <v-icon v-bind="props" @click="router.push(currCid ? `/chatbox/${currCid}` : '/chatbox')"
                                        class="fullscreen-icon">mdi-fullscreen</v-icon>
                                </template>
                            </v-tooltip>
                            <!-- 主题切换按钮 -->
                            <v-tooltip :text="isDark ? '切换到日间模式' : '切换到夜间模式'" v-if="props.chatboxMode">
                                <template v-slot:activator="{ props }">
                                    <v-btn v-bind="props" icon @click="toggleTheme" class="theme-toggle-icon" variant="text">
                                        <v-icon>{{ isDark ? 'mdi-weather-night' : 'mdi-white-balance-sunny' }}</v-icon>
                                    </v-btn>
                                </template>
                            </v-tooltip>
                            <!-- router 推送到 /chat -->
                            <v-tooltip text="退出全屏" v-if="props.chatboxMode">
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
                                <span>输入</span>
                                <code>help</code>
                                <span>获取帮助 😊</span>
                            </div>
                            <div class="welcome-hint">
                                <span>长按</span>
                                <code>Ctrl</code>
                                <span>录制语音 🎤</span>
                            </div>
                            <div class="welcome-hint">
                                <span>按</span>
                                <code>Ctrl + V</code>
                                <span>粘贴图片 🏞️</span>
                            </div>
                        </div>

                        <!-- 聊天消息列表 -->
                        <div v-else class="message-list">
                            <div class="message-item fade-in" v-for="(msg, index) in messages" :key="index">
                                <!-- 用户消息 -->
                                <div v-if="msg.type == 'user'" class="user-message">
                                    <div class="message-bubble user-bubble">
                                        <span>{{ msg.message }}</span>

                                        <!-- 图片附件 -->
                                        <div class="image-attachments" v-if="msg.image_url && msg.image_url.length > 0">
                                            <div v-for="(img, index) in msg.image_url" :key="index"
                                                class="image-attachment">
                                                <img :src="img" class="attached-image" />
                                            </div>
                                        </div>

                                        <!-- 音频附件 -->
                                        <div class="audio-attachment" v-if="msg.audio_url && msg.audio_url.length > 0">
                                            <audio controls class="audio-player">
                                                <source :src="msg.audio_url" type="audio/wav">
                                                您的浏览器不支持音频播放。
                                            </audio>
                                        </div>
                                    </div>
                                    <v-avatar class="user-avatar" color="deep-purple-lighten-3" size="36">
                                        <v-icon icon="mdi-account" />
                                    </v-avatar>
                                </div>

                                <!-- 机器人消息 -->
                                <div v-else class="bot-message">
                                    <v-avatar class="bot-avatar" color="deep-purple" size="36">
                                        <span class="text-h6">✨</span>
                                    </v-avatar>
                                    <div class="message-bubble bot-bubble">
                                        <div v-html="marked(msg.message)" class="markdown-content"></div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- 输入区域 -->
                    <div class="input-area fade-in">
                        <v-text-field autocomplete="off" id="input-field" variant="outlined" v-model="prompt"
                            :label="inputFieldLabel" placeholder="开始输入..." :loading="loadingChat"
                            clear-icon="mdi-close-circle" clearable @click:clear="clearMessage" class="message-input"
                            @keydown="handleInputKeyDown" hide-details>
                            <template v-slot:loader>
                                <v-progress-linear :active="loadingChat" height="3" color="deep-purple"
                                    indeterminate></v-progress-linear>
                            </template>

                            <template v-slot:append>
                                <v-tooltip text="发送">
                                    <template v-slot:activator="{ props }">
                                        <v-btn v-bind="props" @click="sendMessage" class="send-btn" icon="mdi-send"
                                            variant="text" color="deep-purple"
                                            :disabled="!prompt && stagedImagesName.length === 0 && !stagedAudioUrl" />
                                    </template>
                                </v-tooltip>

                                <v-tooltip text="语音输入">
                                    <template v-slot:activator="{ props }">
                                        <v-btn v-bind="props" @click="isRecording ? stopRecording() : startRecording()"
                                            class="record-btn"
                                            :icon="isRecording ? 'mdi-stop-circle' : 'mdi-microphone'" variant="text"
                                            :color="isRecording ? 'error' : 'deep-purple'" />
                                    </template>
                                </v-tooltip>
                            </template>
                        </v-text-field>

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
                                    新录音
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
            <v-card-title class="dialog-title">编辑对话标题</v-card-title>
            <v-card-text>
                <v-text-field v-model="editingTitle" label="对话标题" variant="outlined" hide-details class="mt-2"
                    @keyup.enter="saveTitle" autofocus />
            </v-card-text>
            <v-card-actions>
                <v-spacer></v-spacer>
                <v-btn text @click="editTitleDialog = false" color="grey-darken-1">取消</v-btn>
                <v-btn text @click="saveTitle" color="primary">保存</v-btn>
            </v-card-actions>
        </v-card>
    </v-dialog>
</template>

<script>
export default {
    name: 'ChatPage',
    components: {
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

            inputFieldLabel: '聊天吧!',

            isRecording: false,
            audioChunks: [],
            stagedAudioUrl: "",
            mediaRecorder: null,

            status: {},
            statusText: '',

            eventSource: null,

            // Ctrl键长按相关变量
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
            handler(to) {
                console.log('Route changed:', to.path);
                // Check if the route matches /chat/<cid> pattern
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
        this.startListeningEvent();
        this.checkStatus();
        this.getConversations();
        let inputField = document.getElementById('input-field');
        inputField.addEventListener('paste', this.handlePaste);
        inputField.addEventListener('keydown', function (e) {
            if (e.keyCode == 13 && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
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
        if (this.eventSource) {
            this.eventSource.cancel();
            console.log('SSE连接已断开');
        }

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

        async startListeningEvent() {
            const response = await fetch('/api/chat/listen', {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': 'Bearer ' + localStorage.getItem('token')
                }
            })

            if (!response.ok) {
                console.error('SSE连接失败:', response.statusText);
                return;
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();

            this.eventSource = reader

            let in_streaming = false
            let message_obj = null

            while (true) {
                const { done, value } = await reader.read();
                if (done) {
                    console.log('SSE连接关闭');
                    break;
                }

                const chunk = decoder.decode(value, { stream: true });

                // 可能有多行

                let lines = chunk.split('\n\n');

                console.log('SSE数据:', lines);

                for (let i = 0; i < lines.length; i++) {
                    let line = lines[i].trim();

                    if (!line) {
                        continue;
                    }

                    console.log(line)

                    // data: {"type": "plain", "data": "helloworld"}
                    let chunk_json = JSON.parse(line.replace('data: ', ''));

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
                    您的浏览器不支持音频播放。
                  </audio>`
                        }
                        this.messages.push(bot_resp);
                    } else if (chunk_json.type === 'plain') {
                        if (!in_streaming) {
                            message_obj = {
                                type: 'bot',
                                message: ref(chunk_json.data),
                            }
                            this.messages.push(message_obj);
                            in_streaming = true;
                        } else {
                            message_obj.message.value += chunk_json.data;
                        }
                    } else if (chunk_json.type === 'end') {
                        in_streaming = false;
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
            }
        },

        removeAudio() {
            this.stagedAudioUrl = null;
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
            this.inputFieldLabel = "录音中，请说话...";
        },

        async stopRecording() {
            this.isRecording = false;
            this.inputFieldLabel = "聊天吧!";
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
                    router.push(`/chatbox/${cid[0]}`);
                } else {
                    router.push(`/chat/${cid[0]}`);
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
                                    您的浏览器不支持音频播放。
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
                    router.push(`/chatbox/${cid}`);
                } else {
                    router.push(`/chat/${cid}`);
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
                router.push('/chatbox');
            } else {
                router.push('/chat');
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
            return date.toLocaleString('zh-CN', options).replace(/\//g, '-').replace(/, /g, ' ');
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

        async sendMessage() {
            if (this.currCid == '') {
                const cid = await this.newConversation();
                // URL is already updated in newConversation method
            }

            // Create a message object with actual URLs for display
            const userMessage = {
                type: 'user',
                message: this.prompt,
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

            this.loadingChat = true;

            fetch('/api/chat/send', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': 'Bearer ' + localStorage.getItem('token')
                },
                body: JSON.stringify({
                    message: this.prompt,
                    conversation_id: this.currCid,
                    image_url: this.stagedImagesName, // Already contains just filenames
                    audio_url: this.stagedAudioUrl ? [this.stagedAudioUrl] : [] // Already contains just filename
                })
            })
                .then(response => {
                    this.prompt = '';
                    this.stagedImagesName = [];
                    this.stagedAudioUrl = "";
                    this.loadingChat = false;
                })
                .catch(err => {
                    console.error(err);
                });
        },
        scrollToBottom() {
            this.$nextTick(() => {
                const container = this.$refs.messageContainer;
                container.scrollTop = container.scrollHeight;
            });
        },

        handleInputKeyDown(e) {
            if (e.keyCode === 17) { // Ctrl键
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
            if (e.keyCode === 17) { // Ctrl键
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

        // For smooth height transition on delete button
        beforeEnter(el) {
            el.style.height = '0';
        },
        enter(el) {
            el.style.height = el.scrollHeight + 'px';
        },
        afterEnter(el) {
            el.style.height = 'auto';
        },
        beforeLeave(el) {
            el.style.height = el.scrollHeight + 'px';
        },
        leave(el) {
            el.style.height = '0';
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


/* 聊天页面布局 */
.chat-page-card {
    margin-bottom: 16px;
    width: 100%;
    height: 100%;
    border-radius: 16px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05) !important;
}

.chat-page-container {
    width: 100%;
    height: 100%;
    max-height: calc(100vh - 120px);
    padding: 0;
}

.chat-layout {
    height: 100%;
    display: flex;
}

.sidebar-panel {
    max-width: 270px;
    min-width: 240px;
    display: flex;
    flex-direction: column;
    padding: 0;
    border-right: 1px solid rgba(0, 0, 0, 0.05);
    background-color: var(--v-theme-containerBg);
    height: 100%;
    position: relative;
    transition: all 0.3s ease;
    overflow: hidden;
    /* 防止内容溢出 */
}

.sidebar-panel ::-webkit-scrollbar {
    width: 6px;
}

.sidebar-panel ::-webkit-scrollbar-track {
    background: transparent;
}

.sidebar-panel ::-webkit-scrollbar-thumb {
    background-color: rgba(0, 0, 0, 0.2);
    border-radius: 3px;
}

.sidebar-panel ::-webkit-scrollbar-thumb:hover {
    background-color: rgba(0, 0, 0, 0.3);
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
    opacity: 0.7; /* Make border and text slightly transparent */
}

.status-chip {
    font-size: 12px;
    height: 24px !important;
}

.delete-chat-btn {
    height: 32px !important;
    width: 100%;
    color: rgb(var(--v-theme-error)) !important;
    font-weight: 500;
    box-shadow: none !important;
    margin-top: 8px;
    text-transform: none;
    letter-spacing: 0.25px;
    font-size: 12px;
    line-height: 1.2em;
    transition: opacity 0.25s ease;
    opacity: 0.7;
}

.delete-chat-btn:hover {
    background-color: rgba(var(--v-theme-error-rgb), 0.1) !important;
}

.delete-btn-container {
    /* margin-top: -8px; */ /* Removed for better layout practices */
}

.expand-enter-active,
.expand-leave-active {
    transition: height 0.15s ease-in-out;
    overflow: hidden;
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

/* 聊天内容区域 */
.chat-content-panel {
    height: 100%;
    width: 100%;
    display: flex;
    flex-direction: column;
}

.messages-container {
    height: calc(100% - 80px);
    overflow-y: auto;
    padding: 16px;
    display: flex;
    flex-direction: column;
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

.message-bubble {
    padding: 12px 16px;
    border-radius: 18px;
    max-width: 80%;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.1);
}

.user-bubble {
    background-color: var(--v-theme-background);
    color: var(--v-theme-primaryText);
    border-top-right-radius: 4px;
}

.bot-bubble {
    background-color: var(--v-theme-surface);
    border: 1px solid var(--v-theme-border);
    color: var(--v-theme-primaryText);
    border-top-left-radius: 4px;
}

.user-avatar,
.bot-avatar {
    align-self: flex-end;
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
}

.audio-attachment {
    margin-top: 8px;
}

.audio-player {
    height: 36px;
    border-radius: 18px;
}

/* 输入区域样式 */
.input-area {
    padding: 16px;
    background-color: var(--v-theme-surface);
    position: relative;
    border-top: 1px solid var(--v-theme-border);
}

.message-input {
    border-radius: 24px;
    max-width: 900px;
    margin: 0 auto;
}

.send-btn,
.record-btn {
    margin-left: 4px;
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
}

.markdown-content code {
    background-color: var(--v-theme-codeBg);
    padding: 2px 4px;
    border-radius: 4px;
    font-family: 'Fira Code', monospace;
    font-size: 0.9em;
    color: var(--v-theme-code);
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
}

.conversation-header-content {
    display: flex;
    flex-direction: column;
}

.conversation-header-title {
    font-size: 18px;
    font-weight: 600;
    margin: 0;
    color: var(--v-theme-primaryText);
}

.conversation-header-time {
    font-size: 12px;
    color: var(--v-theme-secondaryText);
    margin-top: 4px;
}

.conversation-header-actions {
    display: flex;
    align-items: center;
}

.fullscreen-icon {
    opacity: 0.7;
    transition: opacity 0.2s;
    cursor: pointer;
}

.fullscreen-icon:hover {
    opacity: 1;
}
</style>