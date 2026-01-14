import { ref, reactive, type Ref } from 'vue';
import axios from 'axios';
import { useToast } from '@/utils/toast';

// 工具调用信息
export interface ToolCall {
    id: string;
    name: string;
    args: Record<string, any>;
    ts: number;              // 开始时间戳
    result?: string;         // 工具调用结果
    finished_ts?: number;    // 完成时间戳
}

// Token 使用统计
export interface TokenUsage {
    input_other: number;
    input_cached: number;
    output: number;
}

// Agent 统计信息
export interface AgentStats {
    token_usage: TokenUsage;
    start_time: number;
    end_time: number;
    time_to_first_token: number;
}

// 文件信息结构
export interface FileInfo {
    url?: string;           // blob URL (可选，点击时才加载)
    filename: string;
    attachment_id?: string; // 用于按需下载
}

// 消息部分的类型定义
export interface MessagePart {
    type: 'plain' | 'image' | 'record' | 'file' | 'video' | 'reply' | 'tool_call';
    text?: string;           // for plain
    attachment_id?: string;  // for image, record, file, video
    filename?: string;       // for file (filename from backend)
    message_id?: number;     // for reply (PlatformSessionHistoryMessage.id)
    tool_calls?: ToolCall[]; // for tool_call
    // embedded fields - 加载后填充
    embedded_url?: string;   // blob URL for image, record
    embedded_file?: FileInfo; // for file (保留 attachment_id 用于按需下载)
    selected_text?: string;  // for reply - 被引用消息的内容
}

// 引用信息 (用于发送消息时)
export interface ReplyInfo {
    messageId: number;
    selectedText?: string;  // 选中的文本内容（可选）
}

// 简化的消息内容结构
export interface MessageContent {
    type: string;                    // 'user' | 'bot'
    message: MessagePart[];          // 消息部分列表 (保持顺序)
    reasoning?: string;              // reasoning content (for bot)
    isLoading?: boolean;             // loading state
    agentStats?: AgentStats;         // agent 统计信息 (for bot)
}

export interface Message {
    id?: number;
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
    
    // 当前会话的项目信息
    const currentSessionProject = ref<{ project_id: string; title: string; emoji: string } | null>(null);

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

    // 解析消息内容，填充 embedded 字段 (保持原始顺序)
    async function parseMessageContent(content: any): Promise<void> {
        const message = content.message;

        // 如果 message 是字符串 (旧格式)，转换为数组格式
        if (typeof message === 'string') {
            const parts: MessagePart[] = [];
            let text = message;

            // 处理旧格式的特殊标记
            if (text.startsWith('[IMAGE]')) {
                const img = text.replace('[IMAGE]', '');
                const imageUrl = await getMediaFile(img);
                parts.push({
                    type: 'image',
                    embedded_url: imageUrl
                });
            } else if (text.startsWith('[RECORD]')) {
                const audio = text.replace('[RECORD]', '');
                const audioUrl = await getMediaFile(audio);
                parts.push({
                    type: 'record',
                    embedded_url: audioUrl
                });
            } else if (text) {
                parts.push({
                    type: 'plain',
                    text: text
                });
            }

            content.message = parts;
            return;
        }

        // 如果 message 是数组 (新格式)，遍历并填充 embedded 字段
        if (Array.isArray(message)) {
            for (const part of message as MessagePart[]) {
                if (part.type === 'image' && part.attachment_id) {
                    part.embedded_url = await getAttachment(part.attachment_id);
                } else if (part.type === 'record' && part.attachment_id) {
                    part.embedded_url = await getAttachment(part.attachment_id);
                } else if (part.type === 'file' && part.attachment_id) {
                    // file 类型不预加载，保留 attachment_id 以便点击时下载
                    part.embedded_file = {
                        attachment_id: part.attachment_id,
                        filename: part.filename || 'file'
                    };
                }
                // plain, reply, tool_call, video 保持原样
            }
        }

        // 处理 agent_stats (snake_case -> camelCase)
        if (content.agent_stats) {
            content.agentStats = content.agent_stats;
            delete content.agent_stats;
        }
    }

    async function getSessionMessages(sessionId: string) {
        if (!sessionId) return;

        try {
            const response = await axios.get('/api/chat/get_session?session_id=' + sessionId);
            isConvRunning.value = response.data.data.is_running || false;
            let history = response.data.data.history;
            
            // 保存项目信息（如果存在）
            currentSessionProject.value = response.data.data.project || null;

            if (isConvRunning.value) {
                if (!isToastedRunningInfo.value) {
                    useToast().info("该会话正在运行中。", { timeout: 5000 });
                    isToastedRunningInfo.value = true;
                }

                // 如果会话还在运行，3秒后重新获取消息
                setTimeout(() => {
                    getSessionMessages(currSessionId.value);
                }, 3000);
            }

            // 处理历史消息
            for (let i = 0; i < history.length; i++) {
                let content = history[i].content;
                await parseMessageContent(content);
            }

            messages.value = history;
        } catch (err) {
            console.error(err);
        }
    }

    async function sendMessage(
        prompt: string,
        stagedFiles: { attachment_id: string; url: string; original_name: string; type: string }[],
        audioName: string,
        selectedProviderId: string,
        selectedModelName: string,
        replyTo: ReplyInfo | null = null
    ) {
        // 构建用户消息的 message 部分
        const userMessageParts: MessagePart[] = [];

        // 添加引用消息段
        console.log('ReplyTo in sendMessage:', replyTo);
        if (replyTo) {
            userMessageParts.push({
                type: 'reply',
                message_id: replyTo.messageId,
                selected_text: replyTo.selectedText
            });
        }

        // 添加纯文本消息段
        if (prompt) {
            userMessageParts.push({
                type: 'plain',
                text: prompt
            });
        }

        // 添加文件消息段
        for (const f of stagedFiles) {
            const partType = f.type === 'image' ? 'image' :
                f.type === 'record' ? 'record' : 'file';
            
            // 获取嵌入 URL
            const embeddedUrl = await getAttachment(f.attachment_id);
            
            userMessageParts.push({
                type: partType as 'image' | 'record' | 'file',
                attachment_id: f.attachment_id,
                filename: f.original_name,
                embedded_url: partType !== 'file' ? embeddedUrl : undefined,
                embedded_file: partType === 'file' ? {
                    attachment_id: f.attachment_id,
                    filename: f.original_name
                } : undefined
            });
        }

        // 添加录音（如果有）
        if (audioName) {
            userMessageParts.push({
                type: 'record',
                embedded_url: audioName  // 录音使用本地 URL
            });
        }

        // 创建用户消息
        const userMessage: MessageContent = {
            type: 'user',
            message: userMessageParts
        };

        messages.value.push({ content: userMessage });

        // 添加一个加载中的机器人消息占位符
        const loadingMessage = reactive<MessageContent>({
            type: 'bot',
            message: [],
            reasoning: '',
            isLoading: true
        });
        messages.value.push({ content: loadingMessage });

        try {
            activeSSECount.value++;
            if (activeSSECount.value === 1) {
                isConvRunning.value = true;
            }

            // 收集所有 attachment_id
            const files = stagedFiles.map(f => f.attachment_id);

            // 构建发送给后端的 message 参数
            let messageToSend: string | MessagePart[];
            if (files.length > 0 || replyTo) {
                const parts: MessagePart[] = [];

                // 添加引用消息段
                if (replyTo) {
                    parts.push({
                        type: 'reply',
                        message_id: replyTo.messageId,
                        selected_text: replyTo.selectedText
                    });
                }

                // 添加纯文本消息段
                if (prompt) {
                    parts.push({
                        type: 'plain',
                        text: prompt
                    });
                }

                // 添加文件消息段
                for (const f of stagedFiles) {
                    const partType = f.type === 'image' ? 'image' :
                        f.type === 'record' ? 'record' : 'file';
                    parts.push({
                        type: partType as 'image' | 'record' | 'file',
                        attachment_id: f.attachment_id
                    });
                }

                messageToSend = parts;
            } else {
                messageToSend = prompt;
            }

            const response = await fetch('/api/chat/send', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': 'Bearer ' + localStorage.getItem('token')
                },
                body: JSON.stringify({
                    message: messageToSend,
                    session_id: currSessionId.value,
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
            let message_obj: MessageContent | null = null;

            isStreaming.value = true;

            while (true) {
                try {
                    const { done, value } = await reader.read();
                    if (done) {
                        console.log('SSE stream completed');
                        // 流式传输结束后，获取最终消息并重新渲染
                        if (currSessionId.value) {
                            await getSessionMessages(currSessionId.value);
                        }
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
                                message: [{
                                    type: 'image',
                                    embedded_url: imageUrl
                                }]
                            };
                            messages.value.push({ content: bot_resp });
                        } else if (chunk_json.type === 'record') {
                            let audio = chunk_json.data.replace('[RECORD]', '');
                            const audioUrl = await getMediaFile(audio);
                            let bot_resp: MessageContent = {
                                type: 'bot',
                                message: [{
                                    type: 'record',
                                    embedded_url: audioUrl
                                }]
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
                                message: [{
                                    type: 'file',
                                    embedded_file: {
                                        url: fileUrl,
                                        filename: originalName
                                    }
                                }]
                            };
                            messages.value.push({ content: bot_resp });
                        } else if (chunk_json.type === 'plain') {
                            const chain_type = chunk_json.chain_type || 'normal';

                            if (chain_type === 'tool_call') {
                                // 解析工具调用数据
                                const toolCallData = JSON.parse(chunk_json.data);
                                const toolCall: ToolCall = {
                                    id: toolCallData.id,
                                    name: toolCallData.name,
                                    args: toolCallData.args,
                                    ts: toolCallData.ts
                                };

                                if (!in_streaming) {
                                    message_obj = reactive<MessageContent>({
                                        type: 'bot',
                                        message: [{
                                            type: 'tool_call',
                                            tool_calls: [toolCall]
                                        }]
                                    });
                                    messages.value.push({ content: message_obj });
                                    in_streaming = true;
                                } else {
                                    // 找到最后一个 tool_call part 或创建新的
                                    const lastPart = message_obj!.message[message_obj!.message.length - 1];
                                    if (lastPart?.type === 'tool_call') {
                                        // 检查是否已存在相同id的tool_call
                                        const existingIndex = lastPart.tool_calls!.findIndex((tc: ToolCall) => tc.id === toolCall.id);
                                        if (existingIndex === -1) {
                                            lastPart.tool_calls!.push(toolCall);
                                        }
                                    } else {
                                        // 添加新的 tool_call part
                                        message_obj!.message.push({
                                            type: 'tool_call',
                                            tool_calls: [toolCall]
                                        });
                                    }
                                }
                            } else if (chain_type === 'tool_call_result') {
                                // 解析工具调用结果数据
                                const resultData = JSON.parse(chunk_json.data);

                                if (message_obj) {
                                    // 遍历所有 tool_call parts 找到对应的 tool_call
                                    for (const part of message_obj.message) {
                                        if (part.type === 'tool_call' && part.tool_calls) {
                                            const toolCall = part.tool_calls.find((tc: ToolCall) => tc.id === resultData.id);
                                            if (toolCall) {
                                                toolCall.result = resultData.result;
                                                toolCall.finished_ts = resultData.ts;
                                                break;
                                            }
                                        }
                                    }
                                }
                            } else if (chain_type === 'reasoning') {
                                if (!in_streaming) {
                                    message_obj = reactive<MessageContent>({
                                        type: 'bot',
                                        message: [],
                                        reasoning: chunk_json.data
                                    });
                                    messages.value.push({ content: message_obj });
                                    in_streaming = true;
                                } else {
                                    message_obj!.reasoning = (message_obj!.reasoning || '') + chunk_json.data;
                                }
                            } else {
                                // normal text
                                if (!in_streaming) {
                                    message_obj = reactive<MessageContent>({
                                        type: 'bot',
                                        message: [{
                                            type: 'plain',
                                            text: chunk_json.data
                                        }]
                                    });
                                    messages.value.push({ content: message_obj });
                                    in_streaming = true;
                                } else {
                                    // 找到最后一个 plain part 或创建新的
                                    const lastPart = message_obj!.message[message_obj!.message.length - 1];
                                    if (lastPart?.type === 'plain') {
                                        lastPart.text = (lastPart.text || '') + chunk_json.data;
                                    } else {
                                        message_obj!.message.push({
                                            type: 'plain',
                                            text: chunk_json.data
                                        });
                                    }
                                }
                            }
                        } else if (chunk_json.type === 'update_title') {
                            updateSessionTitle(chunk_json.session_id, chunk_json.data);
                        } else if (chunk_json.type === 'message_saved') {
                            // 更新最后一条 bot 消息的 id 和 created_at
                            const lastBotMsg = messages.value[messages.value.length - 1];
                            if (lastBotMsg && lastBotMsg.content?.type === 'bot') {
                                lastBotMsg.id = chunk_json.data.id;
                                lastBotMsg.created_at = chunk_json.data.created_at;
                            }
                        } else if (chunk_json.type === 'agent_stats') {
                            // 更新当前 bot 消息的 agent 统计信息
                            if (message_obj) {
                                message_obj.agentStats = chunk_json.data;
                            }
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
        currentSessionProject,
        getSessionMessages,
        sendMessage,
        toggleStreaming,
        getAttachment
    };
}
