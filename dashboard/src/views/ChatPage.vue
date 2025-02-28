<script setup>
import axios from 'axios';
import { marked } from 'marked';

marked.setOptions({
    breaks: true
});
</script>

<template>

    <v-card style="margin-bottom: 16px; width: 100%; background-color: #fff; height: 100%;">
        <v-card-text style="width: 100%; height: calc(100vh - 120px);">
            <div style="height: 100%; display: flex; gap: 16px;">
                <div style="max-width: 200px;">
                    <!-- conversation -->
                    <v-btn variant="tonal" rounded="xl" style="margin-bottom: 16px; min-width: 200px;" @click="newC"
                        :disabled="!currCid">+ 创建对话</v-btn>

                    <v-card class="mx-auto" min-width="200">
                        <v-list dense nav v-if="conversations.length > 0" style="max-height: 500px; overflow-y: auto;"
                            @update:selected="getConversationMessages">
                            <v-list-item v-for="(item, i) in conversations" :key="item.cid" :value="item.cid"
                                color="primary" rounded="xl">
                                <v-list-item-title>新对话</v-list-item-title>
                                <v-list-item-subtitle>{{ formatDate(item.updated_at) }}</v-list-item-subtitle>

                            </v-list-item>
                        </v-list>
                    </v-card>

                    <div>

                        <v-chip class="mt-4" color="primary" :append-icon="status?.llm_enabled ? 'mdi-check' : 'mdi-close'">
                            LLM
                        </v-chip>

                        <v-chip class="mt-4 ml-2" color="success" :append-icon="status?.stt_enabled ? 'mdi-check' : 'mdi-close'">
                            语音转文本
                        </v-chip>
                    </div>

                    <v-btn variant="tonal" rounded="xl"
                        style="position: fixed; bottom: 48px; margin-bottom: 16px; min-width: 200px;" v-if="currCid"
                        @click="deleteConversation(currCid)" color="error">删除此对话</v-btn>
                </div>

                <div style="height: 100%; width: 100%;">
                    <div style="height: calc(100% - 120px); overflow-y: auto; padding: 16px; " ref="messageContainer">
                        <div class="fade-in" v-if="messages.length == 0"
                            style="height: 100%; display: flex; justify-content: center; align-items: center; flex-direction: column;">
                            <div>
                                <span style="font-size: 28px;">Hello, I'm</span>
                                <span style="font-weight: 1000; font-size: 28px; margin-left: 8px;">AstrBot ⭐</span>
                            </div>
                            <div style="margin-top: 8px; color: #aaa;">
                                <span>输入</span>
                                <span
                                    style="background-color: #eee; padding-left: 4px; padding-right: 4px; margin: 2px; border-radius: 4px;">help</span>
                                <span>获取帮助 😊</span>
                            </div>
                            <div style="margin-top: 8px; color: #aaa;">
                                <span>长按</span>
                                <span
                                    style="background-color: #eee; padding-left: 4px; padding-right: 4px; margin: 2px; border-radius: 4px;">Ctrl</span>
                                <span>录制语音 🎤</span>
                            </div>
                            <div style="margin-top: 8px; color: #aaa;">
                                <span>按</span>
                                <span
                                    style="background-color: #eee; padding-left: 4px; padding-right: 4px; margin: 2px; border-radius: 4px;">Ctrl + V</span>
                                <span>粘贴图片 🏞️</span>
                            </div>

                        </div>
                        <div v-else style="max-height: 100%; padding: 16px; max-width: 700px; margin: 0 auto;">
                            <div class="fade-in" v-for="(msg, index) in messages" :key="index"
                                style="margin-bottom: 16px;">
                                <div v-if="msg.type == 'user'" style="display: flex; justify-content: flex-end;">
                                    <div
                                        style="padding: 12px; border-radius: 8px; background-color: rgba(94, 53, 177, 0.15)">
                                        <span>{{ msg.message }}</span>
                                        <div style="display: flex; gap: 8px; margin-top: 8px;"
                                            v-if="msg.image_url && msg.image_url.length > 0">
                                            <div v-for="(img, index) in msg.image_url" :key="index"
                                                style="position: relative; display: inline-block;">
                                                <img :src="img"
                                                    style="width: 100px; height: 100px; border-radius: 8px; box-shadow: 0 0 5px rgba(0, 0, 0, 0.1);" />
                                            </div>
                                        </div>
                                        <!-- audio -->
                                        <div>
                                            <audio controls v-if="msg.audio_url && msg.audio_url.length > 0">
                                                <source :src="msg.audio_url" type="audio/wav">
                                                Your browser does not support the audio element.
                                            </audio>
                                        </div>
                                    </div>
                                </div>
                                <div v-else style="display: flex; justify-content: flex-start; gap: 16px;">
                                    <span style="font-size: 32px;">✨</span>
                                    <div v-html="marked(msg.message)" class="mc" style="font-family: inherit;"></div>
                                </div>
                            </div>
                        </div>
                    </div>

                    <div class="fade-in" style="bottom: 16px; width: 100%; padding: 8px; ">

                        <div
                            style="width: 100%; justify-content: center; align-items: center; display: flex; flex-direction: column; margin-top: 8px;">

                            <v-text-field id="input-field" variant="outlined" v-model="prompt" :label="inputFieldLabel"
                                placeholder="Start typing..." loading clear-icon="mdi-close-circle" clearable
                                @click:clear="clearMessage" style="width: 100%; max-width: 850px;"
                                @keydown="handleInputKeyDown">
                                <template v-slot:loader>
                                    <v-progress-linear :active="loadingChat" height="6"
                                        indeterminate></v-progress-linear>
                                </template>

                                <template v-slot:append>
                                    <v-tooltip text="发送">
                                        <template v-slot:activator="{ props }">
                                            <v-icon v-bind="props" @click="sendMessage" size="35"
                                                icon="mdi-arrow-up-circle" />
                                        </template>
                                    </v-tooltip>


                                    <v-tooltip text="语音输入">
                                        <template v-slot:activator="{ props }">
                                            <v-icon :color="isRecording ? 'error' : ''" v-bind="props"
                                                @click="isRecording ? stopRecording() : startRecording()" size="35"
                                                icon="mdi-record-circle" />
                                        </template>
                                    </v-tooltip>

                                </template>
                            </v-text-field>

                            <div style="display: flex; gap: 8px; margin-top: -8px;">
                                <div v-for="(img, index) in stagedImagesUrl" :key="index"
                                    style="position: relative; display: inline-block;">
                                    <img :src="img"
                                        style="width: 50px; height: 50px; border-radius: 8px; box-shadow: 0 0 5px rgba(0, 0, 0, 0.1);" />
                                    <v-icon @click="removeImage(index)" size="20" color="red"
                                        style="position: absolute; top: 0; right: 0; cursor: pointer;">mdi-close-circle</v-icon>
                                </div>
                                <div style="display: inline-block; width: 50px; height: 50px;">
                                    <div v-if="stagedAudioUrl"
                                        style="position: relative; padding: 6px; border-radius: 8px; background-color: rgba(94, 53, 177, 0.15); display: inline-block;">
                                        新录音
                                        <v-icon @click="removeAudio" size="20" color="red"
                                            style="position: absolute; top: 0; right: 0; cursor: pointer;">mdi-close-circle</v-icon>
                                    </div>

                                </div>
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
            
            // 添加Ctrl键长按相关变量
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
        console.log("111")
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

            while (true) {
                const { done, value } = await reader.read();
                if (done) {
                    console.log('SSE连接关闭');
                    break;
                }

                const chunk = decoder.decode(value, { stream: true });
                console.log("!!!!", chunk);

                if (chunk === '[HB]\n') {
                    continue; // 心跳包
                }
                if (chunk === '[ERROR]\n') {
                    continue;
                }

                if (chunk.startsWith('[IMAGE]')) {
                    let img = chunk.replace('[IMAGE]', '');
                    let bot_resp = {
                        type: 'bot',
                        message: `<img src="/api/chat/get_file?filename=${img}" style="max-width: 80%; border-radius: 8px; box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);"/>`
                    }
                    this.messages.push(bot_resp);
                } else {
                    let bot_resp = {
                        type: 'bot',
                        message: chunk
                    }
                    this.messages.push(bot_resp);
                }
                this.scrollToBottom();
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

                    // const reader = response.body.getReader();  // 获取流的 Reader
                    // const decoder = new TextDecoder();

                    // const readStream = async () => {
                    //     const { done, value } = await reader.read();  // 读取流中的数据
                    //     if (done) {
                    //         console.log("Stream finished.");
                    //         return;
                    //     }

                    //     const chunk = decoder.decode(value, { stream: true });
                    //     // bot_resp.message.value += chunk;

                    //     console.log("!!!!", chunk);
                    //     if (chunk.startsWith('[IMAGE]')) {
                    //         let img = chunk.replace('[IMAGE]', '');
                    //         let bot_resp = {
                    //             type: 'bot',
                    //             message: `<img src="/api/chat/get_file?filename=${img}" style="max-width: 80%; border-radius: 8px; box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);"/>`
                    //         }
                    //         this.messages.push(bot_resp);
                    //     } else {
                    //         let bot_resp = {
                    //             type: 'bot',
                    //             message: chunk
                    //         }

                    //         this.messages.push(bot_resp);
                    //     }

                    //     this.scrollToBottom();
                    //     readStream();  // 递归读取流
                    // };

                    // readStream();
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
@keyframes fadeIn {
    from {
        opacity: 0;
    }

    to {
        opacity: 1;
    }
}

.fade-in {
    animation: fadeIn 0.2s ease-in-out;
}

.mc h1,
.mc h2,
.mc h3,
.mc h4,
.mc h5,
.mc h6 {
    margin-bottom: 10px;
}

.mc li {
    margin-left: 16px;
}


.mc p {
    margin-top: 10px;
    margin-bottom: 10px;
}
</style>