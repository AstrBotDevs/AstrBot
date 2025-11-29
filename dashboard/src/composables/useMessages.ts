import { ref, reactive, type Ref } from 'vue';
import axios from 'axios';
import { useToast } from '@/utils/toast';

// 新格式消息部分的类型定义
export interface MessagePart {
    type: 'plain' | 'image' | 'record' | 'file' | 'video';
    text?: string;           // for plain
    attachment_id?: string;  // for image, record, file, video
    name?: string;           // for file (original filename)
}

// 文件信息结构
export interface FileInfo {
    url: string;
    name: string;
}

export interface MessageContent {
    type: string;
    message: string | MessagePart[];  // 支持旧格式(string)和新格式(MessagePart[])
    reasoning?: string;
    image_url?: string[];
    audio_url?: string;
    file_url?: FileInfo[];
    embedded_images?: string[];
    embedded_audio?: string;
    embedded_files?: FileInfo[];
    isLoading?: boolean;
}

export interface Message {
    content: MessageContent;
    created_at?: string;
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
    const attachmentCache = new Map<string, string>();  // attachment_id -> blob URL

    // 从 localStorage 读取流式响应开关状态
    const savedStreamingState = localStorage.getItem('enableStreaming');
    if (savedStreamingState !== null) {
        enableStreaming.value = JSON.parse(savedStreamingState);
    }

    function toggleStreaming() {
        enableStreaming.value = !enableStreaming.value;
        localStorage.setItem('enableStreaming', JSON.stringify(enableStreaming.value));
    }

    // 获取 attachment 文件并返回 blob URL
    async function getAttachment(attachmentId: string): Promise<string> {
        if (attachmentCache.has(attachmentId)) {
            return attachmentCache.get(attachmentId)!;
        }
        try {
            const response = await axios.get(`/api/chat/get_attachment?attachment_id=${attachmentId}`, {
                responseType: 'blob'
            });
            const blobUrl = URL.createObjectURL(response.data);
            attachmentCache.set(attachmentId, blobUrl);
            return blobUrl;
        } catch (err) {
            console.error('Failed to get attachment:', attachmentId, err);
            return '';
        }
    }

    // 解析新格式消息为旧格式兼容的结构 (用于显示)
    async function parseMessageContent(content: any): Promise<void> {
        const message = content.message;

        // 如果 message 是数组 (新格式)
        if (Array.isArray(message)) {
            let textParts: string[] = [];
            let imageUrls: string[] = [];
            let audioUrl: string | undefined;
            let fileInfos: FileInfo[] = [];

            for (const part of message as MessagePart[]) {
                if (part.type === 'plain' && part.text) {
                    textParts.push(part.text);
                } else if (part.type === 'image' && part.attachment_id) {
                    const url = await getAttachment(part.attachment_id);
                    if (url) imageUrls.push(url);
                } else if (part.type === 'record' && part.attachment_id) {
                    audioUrl = await getAttachment(part.attachment_id);
                } else if (part.type === 'file' && part.attachment_id) {
                    const url = await getAttachment(part.attachment_id);
                    if (url) {
                        fileInfos.push({
                            url: url,
                            name: part.name || 'file'
                        });
                    }
                }
                // video 类型可以后续扩展
            }

            // 转换为旧格式兼容的结构
            content.message = textParts.join('\n');
            if (content.type === 'user') {
                content.image_url = imageUrls.length > 0 ? imageUrls : undefined;
                content.audio_url = audioUrl;
                content.file_url = fileInfos.length > 0 ? fileInfos : undefined;
            } else {
                content.embedded_images = imageUrls.length > 0 ? imageUrls : undefined;
                content.embedded_audio = audioUrl;
                content.embedded_files = fileInfos.length > 0 ? fileInfos : undefined;
            }
        }
        // 如果 message 是字符串 (旧格式)，保持原有处理逻辑
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

                // 首先尝试解析新格式消息
                await parseMessageContent(content);

                // 以下是旧格式的兼容处理 (message 是字符串的情况)
                if (typeof content.message === 'string') {
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
                }

                // 旧格式中的 image_url 和 audio_url 字段处理
                if (content.image_url && content.image_url.length > 0) {
                    for (let j = 0; j < content.image_url.length; j++) {
                        // 检查是否已经是 blob URL (新格式解析后的结果)
                        if (!content.image_url[j].startsWith('blob:')) {
                            content.image_url[j] = await getMediaFile(content.image_url[j]);
                        }
                    }
                }

                if (content.audio_url && !content.audio_url.startsWith('blob:')) {
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
        selectedModelName: string,
        fileInfos: { filename: string; original_name: string }[] = []
    ) {
        // Create user message
        const userMessage: MessageContent = {
            type: 'user',
            message: prompt,
            image_url: [],
            audio_url: undefined,
            file_url: []
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

        // Convert file filenames to blob URLs
        if (fileInfos.length > 0) {
            const filePromises = fileInfos.map(async (info) => {
                const url = await getMediaFile(info.filename);
                return {
                    url: url,
                    name: info.original_name || info.filename
                };
            });
            userMessage.file_url = await Promise.all(filePromises);
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
                    file_url: fileInfos,
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

                        const lastMsg = messages.value[messages.value.length - 1];
                        if (lastMsg?.content?.isLoading) {
                            messages.value.pop();
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
                        } else if (chunk_json.type === 'file') {
                            // 格式: [FILE]filename|original_name
                            let fileData = chunk_json.data.replace('[FILE]', '');
                            let [filename, originalName] = fileData.includes('|') 
                                ? fileData.split('|', 2) 
                                : [fileData, fileData];
                            const fileUrl = await getMediaFile(filename);
                            let bot_resp: MessageContent = {
                                type: 'bot',
                                message: '',
                                embedded_files: [{
                                    url: fileUrl,
                                    name: originalName
                                }]
                            };
                            messages.value.push({ content: bot_resp });
                        } else if (chunk_json.type === 'plain') {
                            const chain_type = chunk_json.chain_type || 'normal';

                            if (!in_streaming) {
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

