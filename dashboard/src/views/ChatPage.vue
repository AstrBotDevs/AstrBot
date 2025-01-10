<script setup>
import axios from 'axios';
import { ref } from 'vue';
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
                        <v-list dense nav rounded="xl" v-if="conversations.length > 0"
                            @update:selected="getConversationMessages">
                            <v-list-item v-for="(item, i) in conversations" :key="item.cid" :value="item.cid"
                                color="primary" rounded="xl">
                                <v-list-item-title>新对话</v-list-item-title>
                                <v-list-item-subtitle>{{ formatDate(item.updated_at) }}</v-list-item-subtitle>

                            </v-list-item>
                        </v-list>
                    </v-card>

                    <v-btn variant="tonal" rounded="xl"
                        style="position: fixed; bottom: 48px; margin-bottom: 16px; min-width: 200px;" v-if="currCid"
                        @click="deleteConversation(currCid)" color="error">删除此对话</v-btn>
                </div>
                <div style="height: 100%; width: 100%;">
                    <div style="height: calc(100% - 130px); overflow-y: auto; padding: 16px; " ref="messageContainer">
                        <div class="fade-in" v-if="messages.length == 0"
                            style="height: 100%; display: flex; justify-content: center; align-items: center; flex-direction: column;">
                            <div>
                                <span style="font-size: 28px;">Hello, I'm</span>
                                <span style="font-weight: 1000; font-size: 28px; margin-left: 8px;">AstrBot ⭐</span>
                            </div>
                            <div style="margin-top: 8px; color: #aaa;">
                                <span>输入</span>
                                <span
                                    style="background-color: #eee; padding-left: 4px; padding-right: 4px; margin: 2px; border-radius: 4px;">/help</span>
                                <span>获取帮助 😊</span>
                            </div>

                        </div>
                        <div v-else style="max-height: 100%; padding: 16px; max-width: 700px; margin: 0 auto;">
                            <div class="fade-in" v-for="(msg, index) in messages" :key="index"
                                style="margin-bottom: 16px;">
                                <div v-if="msg.type == 'user'" style="display: flex; justify-content: flex-end;">
                                    <div
                                        style="padding: 12px; border-radius: 8px; background-color: rgba(94, 53, 177, 0.15)">
                                        <span>{{ msg.message }}</span>
                                        <div style="display: flex; gap: 8px; margin-top: 8px;" v-if="msg.image_url && msg.image_url.length > 0">
                                            <div v-for="(img, index) in msg.image_url" :key="index"
                                                style="position: relative; display: inline-block;">
                                                <img :src="img"
                                                    style="width: 100px; height: 100px; border-radius: 8px; box-shadow: 0 0 5px rgba(0, 0, 0, 0.1);" />
                                            </div>
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
                            
                            <v-text-field id="input-field" variant="outlined" v-model="prompt" label="聊天吧!"
                                placeholder="Start typing..." loading clear-icon="mdi-close-circle" clearable
                                @click:clear="clearMessage" @keyup.enter="sendMessage"
                                style="width: 100%; max-width: 930px;">
                                <template v-slot:loader>
                                    <v-progress-linear
                                    :active="loadingChat"
                                    :color="color"
                                    height="6"
                                    indeterminate
                                    ></v-progress-linear>
                                </template>

                                <template v-slot:append>
                                    <v-icon @click="sendMessage" size="35" icon="mdi-arrow-up-circle" />
                                </template>
                            </v-text-field>

                            <div>
                                <div v-for="(img, index) in stagedImagesUrl" :key="index"
                                    style="position: relative; display: inline-block;">
                                    <img :src="img"
                                        style="width: 50px; height: 50px; border-radius: 8px; box-shadow: 0 0 5px rgba(0, 0, 0, 0.1);" />
                                    <v-icon @click="removeImage(index)" size="20" color="red"
                                        style="position: absolute; top: 0; right: 0; cursor: pointer;">mdi-close-circle</v-icon>
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
            loadingChat: false
        }
    },

    mounted() {
        this.getConversations();
        let inputField = document.getElementById('input-field');
        inputField.addEventListener('paste', this.handlePaste);

    },

    methods: {
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

                        scrollToBottom();
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
                image_url: this.stagedImagesUrl
            });

            // let bot_resp = {
            //     type: 'bot',
            //     message: ref('')
            // }

            // this.messages.push(bot_resp);

            this.scrollToBottom();

            let image_filenames = [];
            for (let i = 0; i < this.stagedImagesUrl.length; i++) {
                let img = this.stagedImagesUrl[i].replace('/api/chat/get_file?filename=', '');
                image_filenames.push(img);
            }

            this.loadingChat = true;


            fetch('/api/chat/send', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': 'Bearer ' + localStorage.getItem('token')
                },
                body: JSON.stringify({ message: this.prompt, conversation_id: this.currCid, image_url: image_filenames })  // 发送请求体
            })
                .then(response => {
                    this.prompt = '';
                    this.stagedImagesUrl = [];

                    this.loadingChat = false;

                    const reader = response.body.getReader();  // 获取流的 Reader
                    const decoder = new TextDecoder();

                    const readStream = async () => {
                        const { done, value } = await reader.read();  // 读取流中的数据
                        if (done) {
                            console.log("Stream finished.");
                            return;
                        }

                        const chunk = decoder.decode(value, { stream: true });
                        // bot_resp.message.value += chunk;

                        console.log("!!!!", chunk);
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
                        readStream();  // 递归读取流
                    };

                    readStream();
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
        }
    }
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