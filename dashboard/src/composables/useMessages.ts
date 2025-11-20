import { ref, reactive, type Ref } from 'vue';
import axios from 'axios';
import { useToast } from '@/utils/toast';

export interface MessageContent {
    type: string;
    message: string;
    reasoning?: string;
    image_url?: string[];
    audio_url?: string;
    embedded_images?: string[];
    embedded_audio?: string;
    isLoading?: boolean;
}

export interface Message {
    content: MessageContent;
}

export function useMessages(
    currSessionId: Ref<string>,
    getMediaFile: (filename: string) => Promise<string>,
    updateSessionTitle: (sessionId: string, title: string) => void,
    onSessionsUpdate: () => void
) {
    const messages = ref<Message[]>([]);
    const isStreaming = ref(false);
    const isConvRunning = ref(false);
    const isToastedRunningInfo = ref(false);
    const activeSSECount = ref(0);
    const enableStreaming = ref(true);

    // 从 localStorage 读取流式响应开关状态
    const savedStreamingState = localStorage.getItem('enableStreaming');
    if (savedStreamingState !== null) {
        enableStreaming.value = JSON.parse(savedStreamingState);
    }

    function toggleStreaming() {
        enableStreaming.value = !enableStreaming.value;
        localStorage.setItem('enableStreaming', JSON.stringify(enableStreaming.value));
    }

    async function getSessionMessages(sessionId: string, router: any) {
        if (!sessionId) return;

        try {
            const response = await axios.get('/api/chat/get_session?session_id=' + sessionId);
            isConvRunning.value = response.data.data.is_running || false;
            let history = response.data.data.history;

            if (isConvRunning.value) {
                if (!isToastedRunningInfo.value) {
                    useToast().info("该会话正在运行中。", { timeout: 5000 });
                    isToastedRunningInfo.value = true;
                }

                // 如果会话还在运行，3秒后重新获取消息
                setTimeout(() => {
                    getSessionMessages(currSessionId.value, router);
                }, 3000);
            }

            // 处理历史消息中的媒体文件
            for (let i = 0; i < history.length; i++) {
                let content = history[i].content;
                
                if (content.message?.startsWith('[IMAGE]')) {
                    let img = content.message.replace('[IMAGE]', '');
                    const imageUrl = await getMediaFile(img);
                    if (!content.embedded_images) {
                        content.embedded_images = [];
                    }
                    content.embedded_images.push(imageUrl);
                    content.message = '';
                }

                if (content.message?.startsWith('[RECORD]')) {
                    let audio = content.message.replace('[RECORD]', '');
                    const audioUrl = await getMediaFile(audio);
                    content.embedded_audio = audioUrl;
                    content.message = '';
                }

                if (content.image_url && content.image_url.length > 0) {
                    for (let j = 0; j < content.image_url.length; j++) {
                        content.image_url[j] = await getMediaFile(content.image_url[j]);
                    }
                }

                if (content.audio_url) {
                    content.audio_url = await getMediaFile(content.audio_url);
                }
            }
            
            messages.value = history;
        } catch (err) {
            console.error(err);
        }
    }

    async function sendMessage(
        prompt: string,
        imageNames: string[],
        audioName: string,
        selectedProviderId: string,
        selectedModelName: string
    ) {
        // Create user message
        const userMessage: MessageContent = {
            type: 'user',
            message: prompt,
            image_url: [],
            audio_url: undefined
        };

        // Convert image filenames to blob URLs
        if (imageNames.length > 0) {
            const imagePromises = imageNames.map(name => {
                if (!name.startsWith('blob:')) {
                    return getMediaFile(name);
                }
                return Promise.resolve(name);
            });
            userMessage.image_url = await Promise.all(imagePromises);
        }

        // Convert audio filename to blob URL
        if (audioName) {
            if (!audioName.startsWith('blob:')) {
                userMessage.audio_url = await getMediaFile(audioName);
            } else {
                userMessage.audio_url = audioName;
            }
        }

        messages.value.push({ content: userMessage });

        // 添加一个加载中的机器人消息占位符
        const loadingMessage = reactive({
            type: 'bot',
            message: '',
            reasoning: '',
            isLoading: true
        });
        messages.value.push({ content: loadingMessage });

        try {
            activeSSECount.value++;
            if (activeSSECount.value === 1) {
                isConvRunning.value = true;
            }

            const response = await fetch('/api/chat/send', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': 'Bearer ' + localStorage.getItem('token')
                },
                body: JSON.stringify({
                    message: prompt,
                    session_id: currSessionId.value,
                    image_url: imageNames,
                    audio_url: audioName ? [audioName] : [],
                    selected_provider: selectedProviderId,
                    selected_model: selectedModelName,
                    enable_streaming: enableStreaming.value
                })
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const reader = response.body!.getReader();
            const decoder = new TextDecoder();
            let in_streaming = false;
            let message_obj: any = null;

            isStreaming.value = true;

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
                        if (!line) continue;

                        let chunk_json;
                        try {
                            chunk_json = JSON.parse(line.replace('data: ', ''));
                        } catch (parseError) {
                            console.warn('JSON解析失败:', line, parseError);
                            continue;
                        }

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
                            const imageUrl = await getMediaFile(img);
                            let bot_resp: MessageContent = {
                                type: 'bot',
                                message: '',
                                embedded_images: [imageUrl]
                            };
                            messages.value.push({ content: bot_resp });
                        } else if (chunk_json.type === 'record') {
                            let audio = chunk_json.data.replace('[RECORD]', '');
                            const audioUrl = await getMediaFile(audio);
                            let bot_resp: MessageContent = {
                                type: 'bot',
                                message: '',
                                embedded_audio: audioUrl
                            };
                            messages.value.push({ content: bot_resp });
                        } else if (chunk_json.type === 'plain') {
                            const chain_type = chunk_json.chain_type || 'normal';
                            
                            if (!in_streaming) {
                                // 移除加载占位符
                                const lastMsg = messages.value[messages.value.length - 1];
                                if (lastMsg?.content?.isLoading) {
                                    messages.value.pop();
                                }
                                
                                message_obj = reactive({
                                    type: 'bot',
                                    message: chain_type === 'reasoning' ? '' : chunk_json.data,
                                    reasoning: chain_type === 'reasoning' ? chunk_json.data : '',
                                });
                                messages.value.push({ content: message_obj });
                                in_streaming = true;
                            } else {
                                if (chain_type === 'reasoning') {
                                    // 使用 reactive 对象，直接修改属性会触发响应式更新
                                    message_obj.reasoning = (message_obj.reasoning || '') + chunk_json.data;
                                } else {
                                    message_obj.message = (message_obj.message || '') + chunk_json.data;
                                }
                            }
                        } else if (chunk_json.type === 'update_title') {
                            updateSessionTitle(chunk_json.session_id, chunk_json.data);
                        }

                        if ((chunk_json.type === 'break' && chunk_json.streaming) || !chunk_json.streaming) {
                            in_streaming = false;
                            if (!chunk_json.streaming) {
                                isStreaming.value = false;
                            }
                        }
                    }
                } catch (readError) {
                    console.error('SSE读取错误:', readError);
                    break;
                }
            }

            // 获取最新的会话列表
            onSessionsUpdate();

        } catch (err) {
            console.error('发送消息失败:', err);
            // 移除加载占位符
            const lastMsg = messages.value[messages.value.length - 1];
            if (lastMsg?.content?.isLoading) {
                messages.value.pop();
            }
        } finally {
            isStreaming.value = false;
            activeSSECount.value--;
            if (activeSSECount.value === 0) {
                isConvRunning.value = false;
            }
        }
    }

    return {
        messages,
        isStreaming,
        isConvRunning,
        enableStreaming,
        getSessionMessages,
        sendMessage,
        toggleStreaming
    };
}
