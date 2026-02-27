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

export type ChatTransportMode = 'sse' | 'websocket';

type StreamChunk = {
    type?: string;
    t?: string;
    data?: any;
    chain_type?: string;
    streaming?: boolean;
    session_id?: string;
    message_id?: string;
    code?: string;
    ct?: string;
    [key: string]: any;
};

type WsStreamContext = {
    handleChunk: (payload: StreamChunk) => Promise<void>;
    finish: (err?: unknown) => void;
};

const STREAMING_STORAGE_KEY = 'enableStreaming';
const TRANSPORT_MODE_STORAGE_KEY = 'chatTransportMode';

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
    const activeStreamCount = ref(0);
    const enableStreaming = ref(true);
    const transportMode = ref<ChatTransportMode>('sse');
    const attachmentCache = new Map<string, string>();  // attachment_id -> blob URL
    const currentRequestController = ref<AbortController | null>(null);
    const currentReader = ref<ReadableStreamDefaultReader<Uint8Array> | null>(null);
    const currentRunningSessionId = ref('');
    const currentWsMessageId = ref('');
    const currentBoundSessionId = ref('');
    const userStopRequested = ref(false);

    const currentWebSocket = ref<WebSocket | null>(null);
    const webSocketConnectPromise = ref<Promise<WebSocket> | null>(null);
    const wsContexts = new Map<string, WsStreamContext>();

    // 当前会话的项目信息
    const currentSessionProject = ref<{ project_id: string; title: string; emoji: string } | null>(null);

    // 从 localStorage 读取配置
    const savedStreamingState = localStorage.getItem(STREAMING_STORAGE_KEY);
    if (savedStreamingState !== null) {
        enableStreaming.value = JSON.parse(savedStreamingState);
    }

    const savedTransportMode = localStorage.getItem(TRANSPORT_MODE_STORAGE_KEY);
    if (savedTransportMode === 'sse' || savedTransportMode === 'websocket') {
        transportMode.value = savedTransportMode;
    }

    function toggleStreaming() {
        enableStreaming.value = !enableStreaming.value;
        localStorage.setItem(STREAMING_STORAGE_KEY, JSON.stringify(enableStreaming.value));
    }

    function setTransportMode(mode: ChatTransportMode) {
        transportMode.value = mode;
        localStorage.setItem(TRANSPORT_MODE_STORAGE_KEY, mode);
        if (mode === 'websocket') {
            if (currSessionId.value) {
                void bindSessionToWebSocket(currSessionId.value).catch((err) => {
                    console.error('建立 WebSocket 连接失败:', err);
                });
            }
        } else {
            closeChatWebSocket();
        }
    }

    function generateMessageId(): string {
        if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
            return crypto.randomUUID();
        }
        return `msg_${Date.now()}_${Math.random().toString(36).slice(2)}`;
    }

    function buildWebSocketUrl(): string {
        const token = localStorage.getItem('token');
        if (!token) {
            throw new Error('Missing authentication token');
        }
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = new URL('/api/unified_chat/ws', window.location.href);
        wsUrl.protocol = protocol;
        wsUrl.searchParams.set('token', token);
        return wsUrl.toString();
    }

    function closeChatWebSocket() {
        if (currentWebSocket.value) {
            try {
                currentWebSocket.value.close();
            } catch {
                // ignore websocket close errors
            }
            currentWebSocket.value = null;
        }
        webSocketConnectPromise.value = null;
        currentBoundSessionId.value = '';
    }

    async function bindSessionToWebSocket(sessionId: string) {
        if (!sessionId || transportMode.value !== 'websocket') {
            return;
        }
        const ws = await ensureChatWebSocket();
        if (ws.readyState !== WebSocket.OPEN) {
            return;
        }
        if (currentBoundSessionId.value === sessionId) {
            return;
        }

        ws.send(JSON.stringify({
            ct: 'chat',
            t: 'bind',
            session_id: sessionId
        }));
        currentBoundSessionId.value = sessionId;
    }

    async function handlePassiveWebSocketChunk(payload: StreamChunk) {
        if (!payload.type) {
            return;
        }

        if (payload.type === 'plain') {
            const chainType = payload.chain_type || 'normal';
            if (chainType === 'reasoning') {
                messages.value.push({
                    content: {
                        type: 'bot',
                        message: [],
                        reasoning: String(payload.data || '')
                    }
                });
                return;
            }

            messages.value.push({
                content: {
                    type: 'bot',
                    message: [{
                        type: 'plain',
                        text: String(payload.data || '')
                    }]
                }
            });
            return;
        }

        if (payload.type === 'image') {
            const img = String(payload.data || '').replace('[IMAGE]', '');
            const imageUrl = await getMediaFile(img);
            messages.value.push({
                content: {
                    type: 'bot',
                    message: [{ type: 'image', embedded_url: imageUrl }]
                }
            });
            return;
        }

        if (payload.type === 'record') {
            const audio = String(payload.data || '').replace('[RECORD]', '');
            const audioUrl = await getMediaFile(audio);
            messages.value.push({
                content: {
                    type: 'bot',
                    message: [{ type: 'record', embedded_url: audioUrl }]
                }
            });
            return;
        }

        if (payload.type === 'file') {
            const fileData = String(payload.data || '').replace('[FILE]', '');
            const [filename, originalName] = fileData.includes('|')
                ? fileData.split('|', 2)
                : [fileData, fileData];
            const fileUrl = await getMediaFile(filename);
            messages.value.push({
                content: {
                    type: 'bot',
                    message: [{
                        type: 'file',
                        embedded_file: { url: fileUrl, filename: originalName }
                    }]
                }
            });
        }
    }

    async function dispatchWebSocketMessage(event: MessageEvent) {
        let payload: StreamChunk;
        try {
            payload = JSON.parse(event.data);
        } catch (err) {
            console.warn('WebSocket JSON parse failed:', err);
            return;
        }

        if (payload.ct && payload.ct !== 'chat') {
            return;
        }

        if (payload.type === 'session_bound') {
            if (typeof payload.session_id === 'string') {
                currentBoundSessionId.value = payload.session_id;
            }
            return;
        }

        if (payload.t === 'error') {
            const targetMessageId = payload.message_id || currentWsMessageId.value;
            if (!targetMessageId) {
                console.warn('WebSocket chat error:', payload);
                return;
            }
            const ctx = wsContexts.get(targetMessageId);
            if (!ctx) {
                console.warn('WebSocket chat error (no ctx):', payload);
                return;
            }

            if (userStopRequested.value || payload.code === 'INTERRUPTED') {
                ctx.finish();
            } else {
                ctx.finish(new Error(payload.data || 'WebSocket chat error'));
            }
            return;
        }

        const targetMessageId = payload.message_id || currentWsMessageId.value;
        if (!targetMessageId) {
            return;
        }

        const ctx = wsContexts.get(targetMessageId);
        if (!ctx) {
            await handlePassiveWebSocketChunk(payload);
            return;
        }

        try {
            await ctx.handleChunk(payload);
        } catch (err) {
            ctx.finish(err);
            return;
        }

        if (payload.type === 'end') {
            ctx.finish();
        }
    }

    function ensureChatWebSocket(): Promise<WebSocket> {
        if (currentWebSocket.value?.readyState === WebSocket.OPEN) {
            return Promise.resolve(currentWebSocket.value);
        }

        if (webSocketConnectPromise.value) {
            return webSocketConnectPromise.value;
        }

        const connectPromise = new Promise<WebSocket>((resolve, reject) => {
            let settled = false;
            let ws: WebSocket;

            try {
                ws = new WebSocket(buildWebSocketUrl());
            } catch (err) {
                reject(err);
                return;
            }

            const timeoutId = window.setTimeout(() => {
                if (settled) {
                    return;
                }
                settled = true;
                webSocketConnectPromise.value = null;
                try {
                    ws.close();
                } catch {
                    // ignore close errors
                }
                reject(new Error('WebSocket connection timeout'));
            }, 5000);

            ws.onopen = () => {
                if (settled) {
                    return;
                }
                settled = true;
                window.clearTimeout(timeoutId);
                currentWebSocket.value = ws;
                resolve(ws);
            };

            ws.onerror = () => {
                if (settled) {
                    return;
                }
                settled = true;
                window.clearTimeout(timeoutId);
                webSocketConnectPromise.value = null;
                reject(new Error('WebSocket connection failed'));
            };

            ws.onmessage = (event) => {
                void dispatchWebSocketMessage(event);
            };

            ws.onclose = () => {
                currentWebSocket.value = null;
                webSocketConnectPromise.value = null;
                const pending = Array.from(wsContexts.values());
                for (const ctx of pending) {
                    if (userStopRequested.value) {
                        ctx.finish();
                    } else {
                        ctx.finish(new Error('WebSocket closed'));
                    }
                }
            };
        });

        webSocketConnectPromise.value = connectPromise;
        return connectPromise;
    }

    function createStreamChunkProcessor() {
        let inStreaming = false;
        let messageObj: MessageContent | null = null;

        return async (chunkJson: StreamChunk) => {
            if (!chunkJson || typeof chunkJson !== 'object') {
                return;
            }

            if (chunkJson.type === 'session_id') {
                return;
            }

            if (!chunkJson.type) {
                return;
            }

            const lastMsg = messages.value[messages.value.length - 1];
            if (lastMsg?.content?.isLoading) {
                messages.value.pop();
            }

            if (chunkJson.type === 'error') {
                console.error('Error received:', chunkJson.data);
                return;
            }

            if (chunkJson.type === 'image') {
                const img = String(chunkJson.data || '').replace('[IMAGE]', '');
                const imageUrl = await getMediaFile(img);
                const botResp: MessageContent = {
                    type: 'bot',
                    message: [{
                        type: 'image',
                        embedded_url: imageUrl
                    }]
                };
                messages.value.push({ content: botResp });
            } else if (chunkJson.type === 'record') {
                const audio = String(chunkJson.data || '').replace('[RECORD]', '');
                const audioUrl = await getMediaFile(audio);
                const botResp: MessageContent = {
                    type: 'bot',
                    message: [{
                        type: 'record',
                        embedded_url: audioUrl
                    }]
                };
                messages.value.push({ content: botResp });
            } else if (chunkJson.type === 'file') {
                const fileData = String(chunkJson.data || '').replace('[FILE]', '');
                const [filename, originalName] = fileData.includes('|')
                    ? fileData.split('|', 2)
                    : [fileData, fileData];
                const fileUrl = await getMediaFile(filename);
                const botResp: MessageContent = {
                    type: 'bot',
                    message: [{
                        type: 'file',
                        embedded_file: {
                            url: fileUrl,
                            filename: originalName
                        }
                    }]
                };
                messages.value.push({ content: botResp });
            } else if (chunkJson.type === 'plain') {
                const chainType = chunkJson.chain_type || 'normal';

                if (chainType === 'tool_call') {
                    let toolCallData: any;
                    try {
                        toolCallData = JSON.parse(String(chunkJson.data || '{}'));
                    } catch {
                        return;
                    }

                    const toolCall: ToolCall = {
                        id: toolCallData.id,
                        name: toolCallData.name,
                        args: toolCallData.args,
                        ts: toolCallData.ts
                    };

                    if (!inStreaming) {
                        messageObj = reactive<MessageContent>({
                            type: 'bot',
                            message: [{
                                type: 'tool_call',
                                tool_calls: [toolCall]
                            }]
                        });
                        messages.value.push({ content: messageObj });
                        inStreaming = true;
                    } else {
                        const lastPart = messageObj!.message[messageObj!.message.length - 1];
                        if (lastPart?.type === 'tool_call') {
                            const existingIndex = lastPart.tool_calls!.findIndex((tc: ToolCall) => tc.id === toolCall.id);
                            if (existingIndex === -1) {
                                lastPart.tool_calls!.push(toolCall);
                            }
                        } else {
                            messageObj!.message.push({
                                type: 'tool_call',
                                tool_calls: [toolCall]
                            });
                        }
                    }
                } else if (chainType === 'tool_call_result') {
                    let resultData: any;
                    try {
                        resultData = JSON.parse(String(chunkJson.data || '{}'));
                    } catch {
                        return;
                    }

                    if (messageObj) {
                        for (const part of messageObj.message) {
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
                } else if (chainType === 'reasoning') {
                    if (!inStreaming) {
                        messageObj = reactive<MessageContent>({
                            type: 'bot',
                            message: [],
                            reasoning: String(chunkJson.data || '')
                        });
                        messages.value.push({ content: messageObj });
                        inStreaming = true;
                    } else {
                        messageObj!.reasoning = (messageObj!.reasoning || '') + String(chunkJson.data || '');
                    }
                } else {
                    if (!inStreaming) {
                        messageObj = reactive<MessageContent>({
                            type: 'bot',
                            message: [{
                                type: 'plain',
                                text: String(chunkJson.data || '')
                            }]
                        });
                        messages.value.push({ content: messageObj });
                        inStreaming = true;
                    } else {
                        const lastPart = messageObj!.message[messageObj!.message.length - 1];
                        if (lastPart?.type === 'plain') {
                            lastPart.text = (lastPart.text || '') + String(chunkJson.data || '');
                        } else {
                            messageObj!.message.push({
                                type: 'plain',
                                text: String(chunkJson.data || '')
                            });
                        }
                    }
                }
            } else if (chunkJson.type === 'update_title') {
                if (chunkJson.session_id) {
                    updateSessionTitle(chunkJson.session_id, chunkJson.data);
                }
            } else if (chunkJson.type === 'message_saved') {
                const lastBotMsg = messages.value[messages.value.length - 1];
                if (lastBotMsg && lastBotMsg.content?.type === 'bot') {
                    lastBotMsg.id = chunkJson.data?.id;
                    lastBotMsg.created_at = chunkJson.data?.created_at;
                }
            } else if (chunkJson.type === 'agent_stats') {
                if (messageObj) {
                    messageObj.agentStats = chunkJson.data;
                }
            }

            if (typeof chunkJson.streaming === 'boolean') {
                if ((chunkJson.type === 'break' && chunkJson.streaming) || !chunkJson.streaming) {
                    inStreaming = false;
                    if (!chunkJson.streaming) {
                        isStreaming.value = false;
                    }
                }
            }
        };
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
            if (transportMode.value === 'websocket') {
                try {
                    await bindSessionToWebSocket(sessionId);
                } catch (err) {
                    console.error('进入会话时建立 WebSocket 连接失败:', err);
                }
            }

            const response = await axios.get('/api/chat/get_session?session_id=' + sessionId);
            isConvRunning.value = response.data.data.is_running || false;
            let history = response.data.data.history;

            // 保存项目信息（如果存在）
            currentSessionProject.value = response.data.data.project || null;

            if (isConvRunning.value) {
                if (!isToastedRunningInfo.value) {
                    useToast().info('该会话正在运行中。', { timeout: 5000 });
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

    function buildBackendMessageParts(
        prompt: string,
        stagedFiles: { attachment_id: string; url: string; original_name: string; type: string }[],
        replyTo: ReplyInfo | null
    ): MessagePart[] {
        const parts: MessagePart[] = [];

        if (replyTo) {
            parts.push({
                type: 'reply',
                message_id: replyTo.messageId,
                selected_text: replyTo.selectedText
            });
        }

        if (prompt) {
            parts.push({
                type: 'plain',
                text: prompt
            });
        }

        for (const f of stagedFiles) {
            const partType = f.type === 'image' ? 'image' :
                f.type === 'record' ? 'record' : 'file';
            parts.push({
                type: partType as 'image' | 'record' | 'file',
                attachment_id: f.attachment_id
            });
        }

        return parts;
    }

    async function sendMessageViaSSE(
        messageToSend: string | MessagePart[],
        selectedProviderId: string,
        selectedModelName: string
    ) {
        const controller = new AbortController();
        currentRequestController.value = controller;

        const response = await fetch('/api/chat/send', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': 'Bearer ' + localStorage.getItem('token')
            },
            signal: controller.signal,
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
        currentReader.value = reader;
        const decoder = new TextDecoder();
        const processChunk = createStreamChunkProcessor();

        isStreaming.value = true;

        while (true) {
            try {
                const { done, value } = await reader.read();
                if (done) {
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

                    let chunkJson: StreamChunk;
                    try {
                        chunkJson = JSON.parse(line.replace('data: ', ''));
                    } catch (parseError) {
                        console.warn('JSON解析失败:', line, parseError);
                        continue;
                    }

                    await processChunk(chunkJson);
                }
            } catch (readError) {
                if (!userStopRequested.value) {
                    console.error('SSE读取错误:', readError);
                }
                break;
            }
        }
    }

    async function sendMessageViaWebSocket(
        messageParts: MessagePart[],
        selectedProviderId: string,
        selectedModelName: string
    ) {
        await bindSessionToWebSocket(currSessionId.value);
        const ws = await ensureChatWebSocket();
        const messageId = generateMessageId();
        currentWsMessageId.value = messageId;

        const processChunk = createStreamChunkProcessor();

        isStreaming.value = true;

        await new Promise<void>((resolve, reject) => {
            let finished = false;

            const finish = (err?: unknown) => {
                if (finished) {
                    return;
                }
                finished = true;
                wsContexts.delete(messageId);
                if (err) {
                    reject(err);
                } else {
                    resolve();
                }
            };

            wsContexts.set(messageId, {
                handleChunk: processChunk,
                finish
            });

            try {
                ws.send(JSON.stringify({
                    ct: 'chat',
                    t: 'send',
                    message_id: messageId,
                    session_id: currSessionId.value,
                    message: messageParts,
                    selected_provider: selectedProviderId,
                    selected_model: selectedModelName,
                    enable_streaming: enableStreaming.value
                }));
            } catch (err) {
                finish(err);
            }
        });

        if (currSessionId.value) {
            await getSessionMessages(currSessionId.value);
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
        const userMessageParts: MessagePart[] = [];

        if (replyTo) {
            userMessageParts.push({
                type: 'reply',
                message_id: replyTo.messageId,
                selected_text: replyTo.selectedText
            });
        }

        if (prompt) {
            userMessageParts.push({
                type: 'plain',
                text: prompt
            });
        }

        for (const f of stagedFiles) {
            const partType = f.type === 'image' ? 'image' :
                f.type === 'record' ? 'record' : 'file';

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

        if (audioName) {
            userMessageParts.push({
                type: 'record',
                embedded_url: audioName
            });
        }

        const userMessage: MessageContent = {
            type: 'user',
            message: userMessageParts
        };

        messages.value.push({ content: userMessage });

        const loadingMessage = reactive<MessageContent>({
            type: 'bot',
            message: [],
            reasoning: '',
            isLoading: true
        });
        messages.value.push({ content: loadingMessage });

        try {
            activeStreamCount.value++;
            if (activeStreamCount.value === 1) {
                isConvRunning.value = true;
            }

            userStopRequested.value = false;
            currentRunningSessionId.value = currSessionId.value;

            const backendMessageParts = buildBackendMessageParts(prompt, stagedFiles, replyTo);
            const hasAttachmentOrReply = stagedFiles.length > 0 || !!replyTo;

            if (transportMode.value === 'websocket') {
                await sendMessageViaWebSocket(
                    backendMessageParts,
                    selectedProviderId,
                    selectedModelName
                );
            } else {
                const messageToSend: string | MessagePart[] = hasAttachmentOrReply
                    ? backendMessageParts
                    : prompt;
                await sendMessageViaSSE(
                    messageToSend,
                    selectedProviderId,
                    selectedModelName
                );
            }

            onSessionsUpdate();

        } catch (err) {
            if (!userStopRequested.value) {
                console.error('发送消息失败:', err);
            }
            const lastMsg = messages.value[messages.value.length - 1];
            if (lastMsg?.content?.isLoading) {
                messages.value.pop();
            }
        } finally {
            isStreaming.value = false;
            currentReader.value = null;
            currentRequestController.value = null;
            currentRunningSessionId.value = '';
            currentWsMessageId.value = '';
            userStopRequested.value = false;
            activeStreamCount.value--;
            if (activeStreamCount.value === 0) {
                isConvRunning.value = false;
            }
        }
    }

    async function stopMessage() {
        const sessionId = currentRunningSessionId.value || currSessionId.value;
        if (!sessionId) {
            return;
        }

        userStopRequested.value = true;

        try {
            await axios.post('/api/chat/stop', {
                session_id: sessionId
            });
        } catch (err) {
            console.error('停止会话失败:', err);
        }

        if (transportMode.value === 'websocket' && currentWebSocket.value?.readyState === WebSocket.OPEN) {
            try {
                currentWebSocket.value.send(JSON.stringify({
                    ct: 'chat',
                    t: 'interrupt',
                    session_id: sessionId,
                    message_id: currentWsMessageId.value || undefined
                }));
            } catch (err) {
                console.error('发送 websocket interrupt 失败:', err);
            }
        }

        try {
            await currentReader.value?.cancel();
        } catch {
            // ignore reader cancel failures
        }
        currentReader.value = null;
        currentRequestController.value?.abort();
        currentRequestController.value = null;

        isStreaming.value = false;
    }

    function cleanupTransport() {
        closeChatWebSocket();
    }

    return {
        messages,
        isStreaming,
        isConvRunning,
        enableStreaming,
        transportMode,
        currentSessionProject,
        getSessionMessages,
        sendMessage,
        stopMessage,
        toggleStreaming,
        setTransportMode,
        cleanupTransport,
        getAttachment
    };
}
