<script setup>
import axios from 'axios';
import { marked } from 'marked';
import { ref } from 'vue';

marked.setOptions({
    breaks: true
});
</script>

<template>
    <v-card class="chat-page-card">
        <v-card-text class="chat-page-container">
            <div class="chat-layout">
                <!-- 左侧对话列表面板 - 优化版 -->
                <div class="sidebar-panel">
                    <div class="sidebar-header">
                        <v-btn variant="elevated" rounded="lg" class="new-chat-btn" @click="newC" :disabled="!currCid"
                            prepend-icon="mdi-plus">
                            创建对话
                        </v-btn>
                    </div>

                    <div class="conversations-container">
                        <div class="sidebar-section-title" v-if="conversations.length > 0">
                            对话历史
                        </div>

                        <v-card class="conversation-list-card" v-if="conversations.length > 0" flat>
                            <v-list density="compact" nav class="conversation-list"
                                @update:selected="getConversationMessages">
                                <v-list-item v-for="(item, i) in conversations" :key="item.cid" :value="item.cid"
                                    color="primary" rounded="lg" class="conversation-item" active-color="primary">
                                    <template v-slot:prepend>
                                        <v-icon size="small" icon="mdi-message-text-outline"></v-icon>
                                    </template>
                                    <v-list-item-title class="conversation-title">新对话</v-list-item-title>
                                    <v-list-item-subtitle class="timestamp">{{ formatDate(item.updated_at)
                                    }}</v-list-item-subtitle>
                                </v-list-item>
                            </v-list>
                        </v-card>

                        <v-fade-transition>
                            <div class="no-conversations" v-if="conversations.length === 0">
                                <v-icon icon="mdi-message-text-outline" size="large" color="grey-lighten-1"></v-icon>
                                <div class="no-conversations-text">暂无对话历史</div>
                            </div>
                        </v-fade-transition>
                    </div>

                    <div class="sidebar-footer">
                        <div class="sidebar-section-title">
                            系统状态
                        </div>
                        <div class="status-chips">
                            <v-chip class="status-chip" :color="status?.llm_enabled ? 'primary' : 'grey-lighten-2'"
                                variant="elevated" size="small">
                                <template v-slot:prepend>
                                    <v-icon :icon="status?.llm_enabled ? 'mdi-check-circle' : 'mdi-alert-circle'"
                                        size="x-small"></v-icon>
                                </template>
                                LLM 服务
                            </v-chip>

                            <v-chip class="status-chip" :color="status?.stt_enabled ? 'success' : 'grey-lighten-2'"
                                variant="elevated" size="small">
                                <template v-slot:prepend>
                                    <v-icon :icon="status?.stt_enabled ? 'mdi-check-circle' : 'mdi-alert-circle'"
                                        size="x-small"></v-icon>
                                </template>
                                语音转文本
                            </v-chip>
                        </div>

                        <v-btn variant="tonal" rounded="lg" class="delete-chat-btn" v-if="currCid"
                            @click="deleteConversation(currCid)" color="error" density="comfortable" size="small">
                            <v-icon start size="small">mdi-delete</v-icon>
                            删除此对话
                        </v-btn>
                    </div>
                </div>

                <!-- 右侧聊天内容区域 -->
                <div class="chat-content-panel">
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
                        <v-text-field id="input-field" variant="outlined" v-model="prompt" :label="inputFieldLabel"
                            placeholder="开始输入..." :loading="loadingChat" clear-icon="mdi-close-circle" clearable
                            @click:clear="clearMessage" class="message-input" @keydown="handleInputKeyDown"
                            hide-details>
                            <template v-slot:loader>
                                <v-progress-linear :active="loadingChat" height="3" color="deep-purple"
                                    indeterminate></v-progress-linear>
                            </template>

                            <template v-slot:append>
                                <v-tooltip text="发送">
                                    <template v-slot:activator="{ props }">
                                        <v-btn v-bind="props" @click="sendMessage" class="send-btn" icon="mdi-send"
                                            variant="text" color="deep-purple"
                                            :disabled="!prompt && stagedImagesUrl.length === 0 && !stagedAudioUrl" />
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
            stagedImagesUrl: [],
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
            ctrlKeyLongPressThreshold: 300 // 长按阈值，单位毫秒
        }
    },

    mounted() {
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
    },

    beforeUnmount() {
        if (this.eventSource) {
            this.eventSource.cancel();
            console.log('SSE连接已断开');
        }

        // 移除keyup事件监听
        document.removeEventListener('keyup', this.handleInputKeyUp);
    },

    methods: {

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
                        let bot_resp = {
                            type: 'bot',
                            message: `<img src="/api/chat/get_file?filename=${img}" style="max-width: 80%; border-radius: 8px; box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);"/>`
                        }
                        this.messages.push(bot_resp);
                    } else if (chunk_json.type === 'record') {
                        let audio = chunk_json.data.replace('[RECORD]', '');
                        let bot_resp = {
                            type: 'bot',
                            message: `<audio controls class="audio-player">
                    <source src="/api/chat/get_file?filename=${audio}" type="audio/wav">
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
                            'Content-Type': 'multipart/form-data',
                            'Authorization': 'Bearer ' + localStorage.getItem('token')
                        }
                    });

                    const audio = response.data.data.filename;
                    console.log('Audio uploaded:', audio);

                    this.stagedAudioUrl = `/api/chat/get_file?filename=${audio}`;
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
                                'Content-Type': 'multipart/form-data',
                                'Authorization': 'Bearer ' + localStorage.getItem('token')
                            }
                        });

                        const img = response.data.data.filename;
                        this.stagedImagesUrl.push(`/api/chat/get_file?filename=${img}`);

                    } catch (err) {
                        console.error('Error uploading image:', err);
                    }
                }
            }
        },

        removeImage(index) {
            this.stagedImagesUrl.splice(index, 1);
        },

        clearMessage() {
            this.prompt = '';
        },
        getConversations() {
            axios.get('/api/chat/conversations').then(response => {
                this.conversations = response.data.data;
            }).catch(err => {
                console.error(err);
            });
        },
        getConversationMessages(cid) {
            if (!cid[0])
                return;
            axios.get('/api/chat/get_conversation?conversation_id=' + cid[0]).then(response => {
                this.currCid = cid[0];
                let message = JSON.parse(response.data.data.history);
                for (let i = 0; i < message.length; i++) {
                    if (message[i].message.startsWith('[IMAGE]')) {
                        let img = message[i].message.replace('[IMAGE]', '');
                        message[i].message = `<img src="/api/chat/get_file?filename=${img}" style="max-width: 80%; border-radius: 8px; box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);"/>`
                    }
                    if (message[i].message.startsWith('[RECORD]')) {
                        let audio = message[i].message.replace('[RECORD]', '');
                        message[i].message = `<audio controls class="audio-player">
                                    <source src="/api/chat/get_file?filename=${audio}" type="audio/wav">
                                    您的浏览器不支持音频播放。
                                  </audio>`
                    }
                    if (message[i].image_url && message[i].image_url.length > 0) {
                        for (let j = 0; j < message[i].image_url.length; j++) {
                            message[i].image_url[j] = `/api/chat/get_file?filename=${message[i].image_url[j]}`;
                        }
                    }
                    if (message[i].audio_url) {
                        message[i].audio_url = `/api/chat/get_file?filename=${message[i].audio_url}`;
                    }
                }
                this.messages = message;
            }).catch(err => {
                console.error(err);
            });
        },
        async newConversation() {
            await axios.get('/api/chat/new_conversation').then(response => {
                this.currCid = response.data.data.conversation_id;
                this.getConversations();
            }).catch(err => {
                console.error(err);
            });
        },

        newC() {
            this.currCid = '';
            this.messages = [];
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
                await this.newConversation();
            }

            this.messages.push({
                type: 'user',
                message: this.prompt,
                image_url: this.stagedImagesUrl,
                audio_url: this.stagedAudioUrl
            });

            this.scrollToBottom();

            // images
            let image_filenames = [];
            for (let i = 0; i < this.stagedImagesUrl.length; i++) {
                let img = this.stagedImagesUrl[i].replace('/api/chat/get_file?filename=', '');
                image_filenames.push(img);
            }

            // audio
            let audio_filenames = [];
            if (this.stagedAudioUrl) {
                let audio = this.stagedAudioUrl.replace('/api/chat/get_file?filename=', '');
                audio_filenames.push(audio);
            }

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
                    image_url: image_filenames,
                    audio_url: audio_filenames
                })  // 发送请求体
            })
                .then(response => {
                    this.prompt = '';
                    this.stagedImagesUrl = [];
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

/* 聊天页面布局 */
.chat-page-card {
    margin-bottom: 16px;
    width: 100%;
    height: 100%;
    border-radius: 12px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05) !important;
    background-color: #fff;
}

.chat-page-container {
    width: 100%;
    height: calc(100vh - 120px);
    padding: 0;
}

.chat-layout {
    height: 100%;
    display: flex;
    gap: 24px;
}

/* 侧边栏样式 - 优化版 */
.sidebar-panel {
    max-width: 270px;
    min-width: 240px;
    display: flex;
    flex-direction: column;
    padding: 0;
    border-right: 1px solid rgba(0, 0, 0, 0.05);
    background-color: #fcfcfc;
    height: 100%;
    position: relative;
}

.sidebar-header {
    padding: 16px;
    border-bottom: 1px solid rgba(0, 0, 0, 0.04);
}

.conversations-container {
    flex-grow: 1;
    overflow-y: auto;
    padding: 16px;
}

.sidebar-footer {
    padding: 16px;
    border-top: 1px solid rgba(0, 0, 0, 0.04);
}

.sidebar-section-title {
    font-size: 12px;
    font-weight: 500;
    color: #666;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 12px;
    padding-left: 4px;
}

.new-chat-btn {
    width: 100%;
    background-color: #673ab7 !important;
    color: white !important;
    font-weight: 500;
    box-shadow: 0 2px 8px rgba(103, 58, 183, 0.25) !important;
    transition: all 0.2s ease;
    text-transform: none;
    letter-spacing: 0.25px;
}

.new-chat-btn:hover {
    background-color: #7e57c2 !important;
    box-shadow: 0 4px 12px rgba(103, 58, 183, 0.3) !important;
    transform: translateY(-1px);
}

.conversation-list-card {
    border-radius: 12px;
    box-shadow: none !important;
    background-color: transparent;
}

.conversation-list {
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
    padding: 8px 12px !important;
}

.conversation-item:hover {
    background-color: rgba(103, 58, 183, 0.05);
}

.conversation-title {
    font-weight: 500;
    font-size: 14px;
    line-height: 1.3;
    margin-bottom: 2px;
}

.timestamp {
    font-size: 11px;
    color: #999;
    line-height: 1;
}

.status-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-bottom: 16px;
}

.status-chip {
    font-size: 12px;
    height: 24px !important;
}

.delete-chat-btn {
    width: 100%;
    color: #d32f2f !important;
    font-weight: 500;
    box-shadow: none !important;
    margin-top: 8px;
    text-transform: none;
    letter-spacing: 0.25px;
    font-size: 12px;
}

.delete-chat-btn:hover {
    background-color: rgba(211, 47, 47, 0.1) !important;
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
    color: #999;
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
    color: #673ab7;
}

.welcome-hint {
    margin-top: 8px;
    color: #666;
    font-size: 14px;
}

.welcome-hint code {
    background-color: #f5f0ff;
    padding: 2px 6px;
    margin: 0 4px;
    border-radius: 4px;
    color: #673ab7;
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
    background-color: #f5f0ff;
    color: #333;
    border-top-right-radius: 4px;
}

.bot-bubble {
    background-color: #fff;
    border: 1px solid #e8e8e8;
    color: #333;
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
    background-color: #fff;
    position: relative;
    border-top: 1px solid #f5f5f5;
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
    color: #333;
}

.markdown-content h1 {
    font-size: 1.8em;
    border-bottom: 1px solid #eee;
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
    background-color: #f8f8f8;
    padding: 12px;
    border-radius: 6px;
    overflow-x: auto;
    margin: 12px 0;
}

.markdown-content code {
    background-color: #f5f0ff;
    padding: 2px 4px;
    border-radius: 4px;
    font-family: 'Fira Code', monospace;
    font-size: 0.9em;
    color: #673ab7;
}

.markdown-content img {
    max-width: 100%;
    border-radius: 8px;
    margin: 10px 0;
}

.markdown-content blockquote {
    border-left: 4px solid #673ab7;
    padding-left: 16px;
    color: #666;
    margin: 16px 0;
}

.markdown-content table {
    border-collapse: collapse;
    width: 100%;
    margin: 16px 0;
}

.markdown-content th,
.markdown-content td {
    border: 1px solid #eee;
    padding: 8px 12px;
    text-align: left;
}

.markdown-content th {
    background-color: #f5f0ff;
}

/* 动画类 */
.fade-in {
    animation: fadeIn 0.3s ease-in-out;
}
</style>