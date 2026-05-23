import { computed, onBeforeUnmount, reactive, ref, type Ref } from "vue";
import axios from "axios";

export type TransportMode = "sse" | "websocket";

export interface MessagePart {
  type: string;
  text?: string;
  think?: string;
  message_id?: string | number;
  selected_text?: string;
  embedded_url?: string;
  embedded_file?: { url?: string; filename?: string; attachment_id?: string };
  attachment_id?: string;
  filename?: string;
  tool_calls?: ToolCall[];
  [key: string]: unknown;
}

export interface ToolCall {
  id?: string;
  name?: string;
  arguments?: unknown;
  result?: unknown;
  ts?: number;
  finished_ts?: number;
  [key: string]: unknown;
}

export interface ChatContent {
  type: "user" | "bot" | string;
  message: MessagePart[];
  reasoning?: string;
  isLoading?: boolean;
  agentStats?: any;
  refs?: any;
}

export interface MessageDisplayBlock {
  kind: "thinking" | "content";
  parts: MessagePart[];
}

export interface ChatRecord {
  id?: string | number;
  content: ChatContent;
  created_at?: string;
  sender_id?: string;
  sender_name?: string;
  llm_checkpoint_id?: string | null;
  threads?: ChatThread[];
}

export interface ChatThread {
  thread_id: string;
  parent_session_id: string;
  parent_message_id: number;
  base_checkpoint_id: string;
  selected_text: string;
  created_at?: string;
  updated_at?: string;
}

export interface ChatSessionProject {
  project_id: string;
  title: string;
  emoji?: string;
}

interface ActiveConnection {
  sessionId: string;
  messageId: string;
  transport: TransportMode;
  abort?: AbortController;
  ws?: WebSocket;
}

interface SendMessageStreamOptions {
  sessionId: string;
  messageId: string;
  parts: MessagePart[];
  transport: TransportMode;
  enableStreaming?: boolean;
  selectedProvider?: string;
  selectedModel?: string;
  userRecord?: ChatRecord;
  botRecord: ChatRecord;
  skipUserHistory?: boolean;
  llmCheckpointId?: string | null;
}

interface ContinueEditedMessageOptions {
  sessionId: string;
  sourceRecord: ChatRecord;
  enableStreaming?: boolean;
  selectedProvider?: string;
  selectedModel?: string;
}

interface CreateLocalExchangeOptions {
  sessionId: string;
  messageId: string;
  parts: MessagePart[];
}

interface UseMessagesOptions {
  currentSessionId: Ref<string>;
  onSessionsChanged?: () => Promise<void> | void;
  onStreamUpdate?: (sessionId: string) => void;
}

export function useMessages(options: UseMessagesOptions) {
  const loadingMessages = ref(false);
  const sending = ref(false);
  const messagesBySession = reactive<Record<string, ChatRecord[]>>({});
  const loadedSessions = reactive<Record<string, boolean>>({});
  const activeConnections = reactive<Record<string, ActiveConnection>>({});
  const attachmentBlobCache = new Map<string, Promise<string>>();
  const sessionProjects = reactive<Record<string, ChatSessionProject | null>>(
    {},
  );

  const activeMessages = computed(() =>
    options.currentSessionId.value
      ? messagesBySession[options.currentSessionId.value] || []
      : [],
  );

  onBeforeUnmount(() => {
    cleanupConnections();
    for (const promise of attachmentBlobCache.values()) {
      promise.then((url) => URL.revokeObjectURL(url)).catch(() => {});
    }
    attachmentBlobCache.clear();
  });

  function isSessionRunning(sessionId: string) {
    return Boolean(activeConnections[sessionId]);
  }

  function isUserMessage(msg: ChatRecord) {
    return messageContent(msg).type === "user";
  }

  function messageContent(msg: ChatRecord): ChatContent {
    return msg.content || { type: "bot", message: [] };
  }

  function messageParts(msg: ChatRecord): MessagePart[] {
    const parts = messageContent(msg).message;
    if (Array.isArray(parts)) return parts;
    if (typeof parts === "string") return [{ type: "plain", text: parts }];
    return [];
  }

  function isMessageStreaming(msg: ChatRecord, msgIndex: number) {
    if (
      !options.currentSessionId.value ||
      !isSessionRunning(options.currentSessionId.value)
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
                                // Parse tool call result payload
                                const resultData = JSON.parse(chunk_json.data);

                                const updateToolCallInContent = (content: MessageContent | null | undefined): boolean => {
                                    if (!content || !Array.isArray(content.message)) {
                                        return false;
                                    }
                                    for (const part of content.message) {
                                        if (part.type !== 'tool_call' || !part.tool_calls) {
                                            continue;
                                        }
                                        const toolCall = part.tool_calls.find((tc: ToolCall) => tc.id === resultData.id);
                                        if (!toolCall) {
                                            continue;
                                        }
                                        toolCall.result = resultData.result;
                                        toolCall.finished_ts = resultData.ts;
                                        return true;
                                    }
                                    return false;
                                };

                                let updated = updateToolCallInContent(message_obj);
                                if (!updated) {
                                    for (let i = messages.value.length - 1; i >= 0; i--) {
                                        const message = messages.value[i]?.content;
                                        if (message?.type !== 'bot') {
                                            continue;
                                        }
                                        if (updateToolCallInContent(message)) {
                                            updated = true;
                                            break;
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

                        const isToolCallEvent =
                            chunk_json.type === 'plain' &&
                            (chunk_json.chain_type === 'tool_call' || chunk_json.chain_type === 'tool_call_result');

                        if (
                            ((chunk_json.type === 'break' && chunk_json.streaming) || !chunk_json.streaming) &&
                            !isToolCallEvent
                        ) {
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
    return !isUserMessage(msg) && msgIndex === activeMessages.value.length - 1;
  }

  async function resolvePartMedia(part: MessagePart): Promise<void> {
    if (part.embedded_url) return;
    let url: string;
    let cacheKey: string;
    if (part.attachment_id) {
      cacheKey = `att:${part.attachment_id}`;
      url = `/api/chat/get_attachment?attachment_id=${encodeURIComponent(part.attachment_id)}`;
    } else if (part.filename) {
      cacheKey = `file:${part.filename}`;
      url = `/api/chat/get_file?filename=${encodeURIComponent(part.filename)}`;
    } else {
      return;
    }
    let promise = attachmentBlobCache.get(cacheKey);
    if (!promise) {
      promise = axios
        .get(url, { responseType: "blob" })
        .then((resp) => URL.createObjectURL(resp.data));
      attachmentBlobCache.set(cacheKey, promise);
    }
    try {
      part.embedded_url = await promise;
    } catch (e) {
      attachmentBlobCache.delete(cacheKey);
      console.error("Failed to resolve media:", cacheKey, e);
    }
  }

  async function resolveRecordMedia(records: ChatRecord[]) {
    const mediaTypes = ["image", "record", "video"];
    const tasks: Promise<void>[] = [];
    for (const record of records) {
      for (const part of record.content?.message || []) {
        if (mediaTypes.includes(part.type) && !part.embedded_url && (part.attachment_id || part.filename)) {
          tasks.push(resolvePartMedia(part));
        }
      }
    }
    await Promise.all(tasks);
  }

  async function loadSessionMessages(sessionId: string) {
    if (!sessionId) return;
    loadingMessages.value = true;
    try {
      const response = await axios.get("/api/chat/get_session", {
        params: { session_id: sessionId },
      });
      const payload = response.data?.data || {};
      const history = payload.history || [];
      const records = history.map(normalizeHistoryRecord);
      attachThreads(records, payload.threads || []);
      await resolveRecordMedia(records);
      messagesBySession[sessionId] = records;
      sessionProjects[sessionId] = normalizeSessionProject(payload.project);
      loadedSessions[sessionId] = true;
    } catch (error) {
      console.error("Failed to load session messages:", error);
      messagesBySession[sessionId] = messagesBySession[sessionId] || [];
    } finally {
      loadingMessages.value = false;
    }
  }

  function createLocalExchange({
    sessionId,
    messageId,
    parts,
  }: CreateLocalExchangeOptions) {
    loadedSessions[sessionId] = true;
    messagesBySession[sessionId] = messagesBySession[sessionId] || [];

    const userRecord: ChatRecord = {
      id: `local-user-${messageId}`,
      created_at: new Date().toISOString(),
      content: {
        type: "user",
        message: parts.map(stripUploadOnlyFields),
      },
    };

    const botRecord: ChatRecord = {
      id: `local-bot-${messageId}`,
      created_at: new Date().toISOString(),
      content: {
        type: "bot",
        message: [],
        reasoning: "",
        isLoading: true,
      },
    };

    messagesBySession[sessionId].push(userRecord, botRecord);

    const sessionMessages = messagesBySession[sessionId];
    return {
      userRecord: sessionMessages[sessionMessages.length - 2],
      botRecord: sessionMessages[sessionMessages.length - 1],
    };
  }

  function sendMessageStream({
    sessionId,
    messageId,
    parts,
    transport,
    enableStreaming = true,
    selectedProvider = "",
    selectedModel = "",
    botRecord,
    userRecord,
    skipUserHistory = false,
    llmCheckpointId = null,
  }: SendMessageStreamOptions) {
    if (transport === "websocket") {
      startWebSocketStream(
        sessionId,
        messageId,
        parts,
        botRecord,
        userRecord,
        enableStreaming,
        selectedProvider,
        selectedModel,
      );
      return;
    }
    startSseStream(
      sessionId,
      messageId,
      parts,
      botRecord,
      userRecord,
      enableStreaming,
      selectedProvider,
      selectedModel,
      skipUserHistory,
      llmCheckpointId,
    );
  }

  async function editMessage(
    sessionId: string,
    record: ChatRecord,
    editedText: string,
  ) {
    if (!sessionId || record.id == null) return { needsRegenerate: false };
    const content = cloneContentWithEditedText(record, editedText);
    const response = await axios.post("/api/chat/message/edit", {
      session_id: sessionId,
      message_id: record.id,
      content,
    });
    const payload = response.data?.data || {};
    const updated = payload.message ? normalizeHistoryRecord(payload.message) : null;
    if (updated) {
      Object.assign(record, updated);
      await resolveRecordMedia([record]);
    }
    if (payload.truncated_after_message) {
      truncateMessagesAfter(sessionId, record);
    }
    return {
      needsRegenerate: Boolean(payload.needs_regenerate),
      truncatedAfterMessage: Boolean(payload.truncated_after_message),
    };
  }

  function truncateMessagesAfter(sessionId: string, record: ChatRecord) {
    const records = messagesBySession[sessionId];
    if (!records?.length || record.id == null) return;
    const index = records.findIndex(
      (message) => String(message.id) === String(record.id),
    );
    if (index < 0) return;
    messagesBySession[sessionId] = records.slice(0, index + 1);
  }

  function continueEditedMessage({
    sessionId,
    sourceRecord,
    enableStreaming = true,
    selectedProvider = "",
    selectedModel = "",
  }: ContinueEditedMessageOptions) {
    if (!sessionId) return;
    const parts = messageParts(sourceRecord).map(stripUploadOnlyFields);
    const messageId = crypto.randomUUID?.() || `${Date.now()}-${Math.random()}`;
    messagesBySession[sessionId] = messagesBySession[sessionId] || [];

    const botRecord: ChatRecord = {
      id: `local-edited-bot-${messageId}`,
      created_at: new Date().toISOString(),
      content: {
        type: "bot",
        message: [],
        reasoning: "",
        isLoading: true,
      },
    };
    messagesBySession[sessionId].push(botRecord);

    startSseStream(
      sessionId,
      messageId,
      parts,
      botRecord,
      undefined,
      enableStreaming,
      selectedProvider,
      selectedModel,
      true,
      sourceRecord.llm_checkpoint_id || null,
    );
  }

  async function regenerateMessage(
    sessionId: string,
    botRecord: ChatRecord,
    selectedProvider = "",
    selectedModel = "",
  ) {
    if (!sessionId || botRecord.id == null) return;
    const targetMessageId = botRecord.id;

    botRecord.id = `local-regenerate-${Date.now()}`;
    botRecord.created_at = new Date().toISOString();
    botRecord.content = {
      type: "bot",
      message: [],
      reasoning: "",
      isLoading: true,
    };

    const abort = new AbortController();
    activeConnections[sessionId] = {
      sessionId,
      messageId: String(botRecord.id),
      transport: "sse",
      abort,
    };

    try {
      const response = await fetch("/api/chat/message/regenerate", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${localStorage.getItem("token") || ""}`,
        },
        body: JSON.stringify({
          session_id: sessionId,
          message_id: targetMessageId,
          selected_provider: selectedProvider,
          selected_model: selectedModel,
        }),
        signal: abort.signal,
      });
      if (!response.ok || !response.body) {
        throw new Error(`Regenerate failed: ${response.status}`);
      }
      const contentType = response.headers.get("content-type") || "";
      if (!contentType.includes("text/event-stream")) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.message || "Regenerate failed.");
      }
      await readSseStream(response.body, (payload) => {
        processStreamPayload(botRecord, payload);
        options.onStreamUpdate?.(sessionId);
      });
    } catch (error) {
      if (!abort.signal.aborted) {
        appendPlain(botRecord, `\n\n${String((error as Error)?.message || error)}`);
        console.error("Regenerate failed:", error);
      }
    } finally {
      delete activeConnections[sessionId];
      await options.onSessionsChanged?.();
    }
  }

  async function stopSession(sessionId: string) {
    if (!sessionId) return;
    await axios.post("/api/chat/stop", { session_id: sessionId });
  }

  function cleanupConnections() {
    Object.values(activeConnections).forEach((connection) => {
      connection.abort?.abort();
      connection.ws?.close();
    });
  }

  function normalizeHistoryRecord(record: any): ChatRecord {
    const content = record.content || {};
    const normalizedMessage = normalizeMessageParts(
      content.message || [],
      content.reasoning || "",
    );
    const normalizedContent: ChatContent = {
      type: content.type || (record.sender_id === "bot" ? "bot" : "user"),
      message: normalizedMessage,
      reasoning: extractReasoningText(normalizedMessage, content.reasoning || ""),
      agentStats: content.agentStats || content.agent_stats,
      refs: content.refs,
    };

    return {
      ...record,
      content: normalizedContent,
    };
  }

  function attachThreads(records: ChatRecord[], threads: ChatThread[]) {
    const threadsByMessage = new Map<string, ChatThread[]>();
    for (const thread of threads) {
      const key = String(thread.parent_message_id);
      const list = threadsByMessage.get(key) || [];
      list.push(thread);
      threadsByMessage.set(key, list);
    }
    for (const record of records) {
      const key = record.id == null ? "" : String(record.id);
      record.threads = threadsByMessage.get(key) || [];
    }
  }

  function startSseStream(
    sessionId: string,
    messageId: string,
    parts: MessagePart[],
    botRecord: ChatRecord,
    userRecord: ChatRecord | undefined,
    enableStreaming: boolean,
    selectedProvider: string,
    selectedModel: string,
    skipUserHistory = false,
    llmCheckpointId: string | null = null,
  ) {
    const abort = new AbortController();
    activeConnections[sessionId] = {
      sessionId,
      messageId,
      transport: "sse",
      abort,
    };

    fetch("/api/chat/send", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${localStorage.getItem("token") || ""}`,
      },
      body: JSON.stringify({
        session_id: sessionId,
        message: parts.map(partToPayload),
        enable_streaming: enableStreaming,
        selected_provider: selectedProvider,
        selected_model: selectedModel,
        _skip_user_history: skipUserHistory,
        _llm_checkpoint_id: llmCheckpointId || undefined,
      }),
      signal: abort.signal,
    })
      .then(async (response) => {
        if (!response.ok || !response.body) {
          throw new Error(`SSE connection failed: ${response.status}`);
        }
        await readSseStream(response.body, (payload) => {
          processStreamPayload(botRecord, payload, userRecord);
          options.onStreamUpdate?.(sessionId);
        });
      })
      .catch((error) => {
        if (abort.signal.aborted) return;
        appendPlain(botRecord, `\n\n${String(error?.message || error)}`);
        console.error("SSE chat failed:", error);
      })
      .finally(async () => {
        delete activeConnections[sessionId];
        await options.onSessionsChanged?.();
      });
  }

  function startWebSocketStream(
    sessionId: string,
    messageId: string,
    parts: MessagePart[],
    botRecord: ChatRecord,
    userRecord: ChatRecord | undefined,
    enableStreaming: boolean,
    selectedProvider: string,
    selectedModel: string,
  ) {
    const token = encodeURIComponent(localStorage.getItem("token") || "");
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(
      `${protocol}//${window.location.host}/api/unified_chat/ws?token=${token}`,
    );

    activeConnections[sessionId] = {
      sessionId,
      messageId,
      transport: "websocket",
      ws,
    };

    ws.onopen = () => {
      ws.send(
        JSON.stringify({
          ct: "chat",
          t: "send",
          session_id: sessionId,
          message_id: messageId,
          message: parts.map(partToPayload),
          enable_streaming: enableStreaming,
          selected_provider: selectedProvider,
          selected_model: selectedModel,
        }),
      );
    };
    ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        processStreamPayload(botRecord, payload, userRecord);
        options.onStreamUpdate?.(sessionId);
        if (payload.type === "end" || payload.t === "end") {
          ws.close();
        }
      } catch (error) {
        console.error("Failed to parse WebSocket payload:", error);
      }
    };
    ws.onerror = () => {
      appendPlain(botRecord, "\n\nWebSocket connection failed.");
    };
    ws.onclose = async () => {
      delete activeConnections[sessionId];
      await options.onSessionsChanged?.();
    };
  }

  function processStreamPayload(
    botRecord: ChatRecord,
    payload: any,
    userRecord?: ChatRecord,
  ) {
    const normalized =
      payload?.ct === "chat"
        ? { ...payload, type: payload.type || payload.t }
        : payload;
    const msgType = normalized?.type || normalized?.t;
    const chainType = normalized?.chain_type;
    const data = normalized?.data ?? "";

    if (msgType === "session_id" || msgType === "session_bound") return;
    if (msgType === "user_message_saved") {
      if (userRecord) {
        userRecord.id = data?.id || userRecord.id;
        userRecord.created_at = data?.created_at || userRecord.created_at;
        userRecord.llm_checkpoint_id =
          data?.llm_checkpoint_id || userRecord.llm_checkpoint_id;
      }
      return;
    }
    if (msgType === "message_saved") {
      markMessageStarted(botRecord);
      botRecord.id = data?.id || botRecord.id;
      botRecord.created_at = data?.created_at || botRecord.created_at;
      botRecord.llm_checkpoint_id =
        data?.llm_checkpoint_id || botRecord.llm_checkpoint_id;
      if (data?.refs) {
        messageContent(botRecord).refs = data.refs;
      }
      return;
    }
    if (msgType === "agent_stats" || chainType === "agent_stats") {
      markMessageStarted(botRecord);
      messageContent(botRecord).agentStats = data;
      return;
    }
    if (msgType === "error") {
      markMessageStarted(botRecord);
      appendPlain(botRecord, `\n\n${String(data)}`);
      return;
    }
    if (msgType === "complete" || msgType === "break") {
      markMessageStarted(botRecord);
      const finalText = payloadText(data);
      if (finalText && !hasPlainText(botRecord)) {
        appendPlain(botRecord, finalText, false);
      }
      return;
    }
    if (msgType === "end") {
      markMessageStarted(botRecord);
      return;
    }

    if (msgType === "plain") {
      markMessageStarted(botRecord);
      if (chainType === "reasoning") {
        appendReasoningPart(botRecord, payloadText(data));
        return;
      }
      if (chainType === "tool_call") {
        upsertToolCall(botRecord, parseJsonSafe(data));
        return;
      }
      if (chainType === "tool_call_result") {
        finishToolCall(botRecord, parseJsonSafe(data));
        return;
      }
      appendPlain(botRecord, payloadText(data), normalized.streaming !== false);
      return;
    }

    if (["image", "record", "file", "video"].includes(msgType)) {
      markMessageStarted(botRecord);
      const filename = String(data)
        .replace("[IMAGE]", "")
        .replace("[RECORD]", "")
        .replace("[FILE]", "")
        .replace("[VIDEO]", "")
        .split("|", 1)[0];
      const mediaPart: MessagePart = { type: msgType, filename };
      if (msgType !== "file") {
        resolvePartMedia(mediaPart).then(() => {
          messageContent(botRecord).message.push(mediaPart);
        });
      } else {
        messageContent(botRecord).message.push(mediaPart);
      }
    }
  }

  return {
    loadingMessages,
    sending,
    messagesBySession,
    loadedSessions,
    sessionProjects,
    activeMessages,
    isSessionRunning,
    isUserMessage,
    isMessageStreaming,
    messageContent,
    messageParts,
    loadSessionMessages,
    createLocalExchange,
    sendMessageStream,
    editMessage,
    continueEditedMessage,
    regenerateMessage,
    stopSession,
    cleanupConnections,
  };
}
