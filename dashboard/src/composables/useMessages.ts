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

// 工具调用信息
export interface ToolCall {
  id: string;
  name: string;
  args: Record<string, any>;
  ts: number; // 开始时间戳
  result?: string; // 工具调用结果
  finished_ts?: number; // 完成时间戳
}

// Token 使用统计
export interface TokenUsage {
  input_other: number;
  input_cached: number;
  output: number;
}

export interface MessageDisplayBlock {
  kind: "thinking" | "content";
  parts: MessagePart[];
}

export interface ChatRecord {
  id?: string | number;
  content: ChatContent;
  created_at?: string;
}

export type ChatTransportMode = "sse" | "websocket";

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

const STREAMING_STORAGE_KEY = "enableStreaming";
const TRANSPORT_MODE_STORAGE_KEY = "chatTransportMode";
const HIDDEN_TOOL_CALL_NAMES = new Set(["send_message_to_user"]);

function isHiddenToolCall(
  toolCall: ToolCall | { name?: unknown } | null | undefined,
): boolean {
  if (!toolCall || typeof toolCall !== "object") {
    return false;
  }
  const name = toolCall.name;
  return typeof name === "string" && HIDDEN_TOOL_CALL_NAMES.has(name);
}

export function useMessages(
  currSessionId: Ref<string>,
  getMediaFile: (filename: string) => Promise<string>,
  updateSessionTitle: (sessionId: string, title: string) => void,
  onSessionsUpdate: () => void,
) {
  const messages = ref<Message[]>([]);
  const isStreaming = ref(false);
  const isConvRunning = ref(false);
  const isToastedRunningInfo = ref(false);
  const activeStreamCount = ref(0);
  const enableStreaming = ref(true);
  const transportMode = ref<ChatTransportMode>("sse");
  const attachmentCache = new Map<string, string>(); // attachment_id -> blob URL
  const currentRequestController = ref<AbortController | null>(null);
  const currentReader = ref<ReadableStreamDefaultReader<Uint8Array> | null>(
    null,
  );
  const currentRunningSessionId = ref("");
  const currentWsMessageId = ref("");
  const currentBoundSessionId = ref("");
  const userStopRequested = ref(false);

  const currentWebSocket = ref<WebSocket | null>(null);
  const webSocketConnectPromise = ref<Promise<WebSocket> | null>(null);
  const wsContexts = new Map<string, WsStreamContext>();

  // 当前会话的项目信息
  const currentSessionProject = ref<{
    project_id: string;
    title: string;
    emoji: string;
  } | null>(null);

  // 从 localStorage 读取配置
  const savedStreamingState = localStorage.getItem(STREAMING_STORAGE_KEY);
  if (savedStreamingState !== null) {
    enableStreaming.value = JSON.parse(savedStreamingState);
  }

  const savedTransportMode = localStorage.getItem(TRANSPORT_MODE_STORAGE_KEY);
  if (savedTransportMode === "sse" || savedTransportMode === "websocket") {
    transportMode.value = savedTransportMode;
  }

  function toggleStreaming() {
    enableStreaming.value = !enableStreaming.value;
    localStorage.setItem(
      STREAMING_STORAGE_KEY,
      JSON.stringify(enableStreaming.value),
    );
  }

  function setTransportMode(mode: ChatTransportMode) {
    transportMode.value = mode;
    localStorage.setItem(TRANSPORT_MODE_STORAGE_KEY, mode);
    if (mode === "websocket") {
      if (currSessionId.value) {
        void bindSessionToWebSocket(currSessionId.value).catch((err) => {
          console.error("建立 WebSocket 连接失败:", err);
        });
      }
    } else {
      closeChatWebSocket();
    }
  }

  function generateMessageId(): string {
    if (
      typeof crypto !== "undefined" &&
      typeof crypto.randomUUID === "function"
    ) {
      return crypto.randomUUID();
    }
    return `msg_${Date.now()}_${Math.random().toString(36).slice(2)}`;
  }

  function buildWebSocketUrl(): string {
    const token = localStorage.getItem("token");
    if (!token) {
      throw new Error("Missing authentication token");
    }
    return resolveWebSocketUrl("/api/unified_chat/ws", { token });
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
    currentBoundSessionId.value = "";
  }

  async function bindSessionToWebSocket(sessionId: string) {
    if (!sessionId || transportMode.value !== "websocket") {
      return;
    }
    const ws = await ensureChatWebSocket();
    if (ws.readyState !== WebSocket.OPEN) {
      return;
    }
    if (currentBoundSessionId.value === sessionId) {
      return;
    }

    ws.send(
      JSON.stringify({
        ct: "chat",
        t: "bind",
        session_id: sessionId,
      }),
    );
    currentBoundSessionId.value = sessionId;
  }

  async function handlePassiveWebSocketChunk(payload: StreamChunk) {
    if (!payload.type) {
      return;
    }

    if (payload.type === "plain") {
      const chainType = payload.chain_type || "normal";
      if (chainType === "reasoning") {
        messages.value.push({
          content: {
            type: "bot",
            message: [],
            reasoning: String(payload.data || ""),
          },
        });
        return;
      }

      messages.value.push({
        content: {
          type: "bot",
          message: [
            {
              type: "plain",
              text: String(payload.data || ""),
            },
          ],
        },
      });
      return;
    }

    if (payload.type === "image") {
      const img = String(payload.data || "").replace("[IMAGE]", "");
      const imageUrl = await getMediaFile(img);
      messages.value.push({
        content: {
          type: "bot",
          message: [{ type: "image", embedded_url: imageUrl }],
        },
      });
      return;
    }

    if (payload.type === "record") {
      const audio = String(payload.data || "").replace("[RECORD]", "");
      const audioUrl = await getMediaFile(audio);
      messages.value.push({
        content: {
          type: "bot",
          message: [{ type: "record", embedded_url: audioUrl }],
        },
      });
      return;
    }

    if (payload.type === "file") {
      const fileData = String(payload.data || "").replace("[FILE]", "");
      const [filename, originalName] = fileData.includes("|")
        ? fileData.split("|", 2)
        : [fileData, fileData];
      const fileUrl = await getMediaFile(filename);
      messages.value.push({
        content: {
          type: "bot",
          message: [
            {
              type: "file",
              embedded_file: { url: fileUrl, filename: originalName },
            },
          ],
        },
      });
    }
  }

  async function dispatchWebSocketMessage(event: MessageEvent) {
    let payload: StreamChunk;
    try {
      payload = JSON.parse(event.data);
    } catch (err) {
      console.warn("WebSocket JSON parse failed:", err);
      return;
    }

    if (payload.ct && payload.ct !== "chat") {
      return;
    }

    if (payload.type === "session_bound") {
      if (typeof payload.session_id === "string") {
        currentBoundSessionId.value = payload.session_id;
      }
      return;
    }

    if (payload.t === "error") {
      const targetMessageId = payload.message_id || currentWsMessageId.value;
      if (!targetMessageId) {
        console.warn("WebSocket chat error:", payload);
        return;
      }
      const ctx = wsContexts.get(targetMessageId);
      if (!ctx) {
        console.warn("WebSocket chat error (no ctx):", payload);
        return;
      }

      if (userStopRequested.value || payload.code === "INTERRUPTED") {
        ctx.finish();
      } else {
        ctx.finish(new Error(payload.data || "WebSocket chat error"));
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

    if (payload.type === "end") {
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
        reject(new Error("WebSocket connection timeout"));
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
        reject(new Error("WebSocket connection failed"));
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
            ctx.finish(new Error("WebSocket closed"));
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
      if (!chunkJson || typeof chunkJson !== "object") {
        return;
      }

      if (chunkJson.type === "session_id") {
        return;
      }

      if (!chunkJson.type) {
        return;
      }

      const lastMsg = messages.value[messages.value.length - 1];
      if (lastMsg?.content?.isLoading) {
        messages.value.pop();
      }

      if (chunkJson.type === "error") {
        console.error("Error received:", chunkJson.data);
        return;
      }

      if (chunkJson.type === "image") {
        const img = String(chunkJson.data || "").replace("[IMAGE]", "");
        const imageUrl = await getMediaFile(img);
        const botResp: MessageContent = {
          type: "bot",
          message: [
            {
              type: "image",
              embedded_url: imageUrl,
            },
          ],
        };
        messages.value.push({ content: botResp });
      } else if (chunkJson.type === "record") {
        const audio = String(chunkJson.data || "").replace("[RECORD]", "");
        const audioUrl = await getMediaFile(audio);
        const botResp: MessageContent = {
          type: "bot",
          message: [
            {
              type: "record",
              embedded_url: audioUrl,
            },
          ],
        };
        messages.value.push({ content: botResp });
      } else if (chunkJson.type === "file") {
        const fileData = String(chunkJson.data || "").replace("[FILE]", "");
        const [filename, originalName] = fileData.includes("|")
          ? fileData.split("|", 2)
          : [fileData, fileData];
        const fileUrl = await getMediaFile(filename);
        const botResp: MessageContent = {
          type: "bot",
          message: [
            {
              type: "file",
              embedded_file: {
                url: fileUrl,
                filename: originalName,
              },
            },
          ],
        };
        messages.value.push({ content: botResp });
      } else if (chunkJson.type === "plain") {
        const chainType = chunkJson.chain_type || "normal";

        if (chainType === "tool_call") {
          let toolCallData: any;
          try {
            toolCallData = JSON.parse(String(chunkJson.data || "{}"));
          } catch {
            return;
          }
          if (isHiddenToolCall(toolCallData)) {
            return;
          }

          const toolCall: ToolCall = {
            id: toolCallData.id,
            name: toolCallData.name,
            args: toolCallData.args,
            ts: toolCallData.ts,
          };

          if (!inStreaming) {
            messageObj = reactive<MessageContent>({
              type: "bot",
              message: [
                {
                  type: "tool_call",
                  tool_calls: [toolCall],
                },
              ],
            });
            messages.value.push({ content: messageObj });
            inStreaming = true;
          } else {
            const lastPart =
              messageObj!.message[messageObj!.message.length - 1];
            if (lastPart?.type === "tool_call") {
              const existingIndex = lastPart.tool_calls!.findIndex(
                (tc: ToolCall) => tc.id === toolCall.id,
              );
              if (existingIndex === -1) {
                lastPart.tool_calls!.push(toolCall);
              }
            } else {
              messageObj!.message.push({
                type: "tool_call",
                tool_calls: [toolCall],
              });
            }
          }
        } else if (chainType === "tool_call_result") {
          let resultData: any;
          try {
            resultData = JSON.parse(String(chunkJson.data || "{}"));
          } catch {
            return;
          }
          if (isHiddenToolCall(resultData)) {
            return;
          }

          if (messageObj) {
            for (const part of messageObj.message) {
              if (part.type === "tool_call" && part.tool_calls) {
                const toolCall = part.tool_calls.find(
                  (tc: ToolCall) => tc.id === resultData.id,
                );
                if (toolCall) {
                  toolCall.result = resultData.result;
                  toolCall.finished_ts = resultData.ts;
                  break;
                }
              }
            }
          }
        } else if (chainType === "reasoning") {
          if (!inStreaming) {
            messageObj = reactive<MessageContent>({
              type: "bot",
              message: [],
              reasoning: String(chunkJson.data || ""),
            });
            messages.value.push({ content: messageObj });
            inStreaming = true;
          } else {
            messageObj!.reasoning =
              (messageObj!.reasoning || "") + String(chunkJson.data || "");
          }
        } else {
          if (!inStreaming) {
            messageObj = reactive<MessageContent>({
              type: "bot",
              message: [
                {
                  type: "plain",
                  text: String(chunkJson.data || ""),
                },
              ],
            });
            messages.value.push({ content: messageObj });
            inStreaming = true;
          } else {
            const lastPart =
              messageObj!.message[messageObj!.message.length - 1];
            if (lastPart?.type === "plain") {
              lastPart.text =
                (lastPart.text || "") + String(chunkJson.data || "");
            } else {
              messageObj!.message.push({
                type: "plain",
                text: String(chunkJson.data || ""),
              });
            }
          }
        }
      } else if (chunkJson.type === "update_title") {
        if (chunkJson.session_id) {
          updateSessionTitle(chunkJson.session_id, chunkJson.data);
        }
      } else if (chunkJson.type === "message_saved") {
        const lastBotMsg = messages.value[messages.value.length - 1];
        if (lastBotMsg && lastBotMsg.content?.type === "bot") {
          lastBotMsg.id = chunkJson.data?.id;
          lastBotMsg.created_at = chunkJson.data?.created_at;
        }
      } else if (chunkJson.type === "agent_stats") {
        if (messageObj) {
          messageObj.agentStats = chunkJson.data;
        }
      }

      if (typeof chunkJson.streaming === "boolean") {
        if (
          (chunkJson.type === "break" && chunkJson.streaming) ||
          !chunkJson.streaming
        ) {
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
      const response = await axios.get(
        `/api/chat/get_attachment?attachment_id=${attachmentId}`,
        {
          responseType: "blob",
        },
      );
      const blobUrl = URL.createObjectURL(response.data);
      attachmentCache.set(attachmentId, blobUrl);
      return blobUrl;
    } catch (err) {
      console.error("Failed to get attachment:", attachmentId, err);
      return "";
    }
  }

  // 解析消息内容，填充 embedded 字段 (保持原始顺序)
  async function parseMessageContent(content: any): Promise<void> {
    const message = content.message;

    // 如果 message 是字符串 (旧格式)，转换为数组格式
    if (typeof message === "string") {
      const parts: MessagePart[] = [];
      const text = message;

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

      content.message = parts;
      return;
    }

    // 如果 message 是数组 (新格式)，遍历并填充 embedded 字段
    if (Array.isArray(message)) {
      const filteredMessage: MessagePart[] = [];
      for (const part of message as MessagePart[]) {
        if (part.type === "tool_call" && Array.isArray(part.tool_calls)) {
          const visibleToolCalls = part.tool_calls.filter(
            (toolCall) => !isHiddenToolCall(toolCall),
          );
          if (!visibleToolCalls.length) {
            continue;
          }
          part.tool_calls = visibleToolCalls;
        }

        if (part.type === "image" && part.attachment_id) {
          part.embedded_url = await getAttachment(part.attachment_id);
        } else if (part.type === "record" && part.attachment_id) {
          part.embedded_url = await getAttachment(part.attachment_id);
        } else if (part.type === "file" && part.attachment_id) {
          // file 类型不预加载，保留 attachment_id 以便点击时下载
          part.embedded_file = {
            attachment_id: part.attachment_id,
            filename: part.filename || "file",
          };
        }
        // plain, reply, tool_call, video 保持原样
        filteredMessage.push(part);
      }
      content.message = filteredMessage;
    }

    // 处理 agent_stats (snake_case -> camelCase)
    if (content.agent_stats) {
      content.agentStats = content.agent_stats;
      delete content.agent_stats;
    }
  }

  async function getSessionMessages(sessionId: string) {
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
      if (transportMode.value === "websocket") {
        try {
          await bindSessionToWebSocket(sessionId);
        } catch (err) {
          console.error("进入会话时建立 WebSocket 连接失败:", err);
        }
      }

      const response = await axios.get(
        "/api/chat/get_session?session_id=" + sessionId,
      );
      isConvRunning.value = response.data.data.is_running || false;
      const history = response.data.data.history;

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
        const content = history[i].content;
        await parseMessageContent(content);
      }

      messages.value = history;
    } catch (err) {
      console.error(err);
    }
  }

  function buildBackendMessageParts(
    prompt: string,
    stagedFiles: {
      attachment_id: string;
      url: string;
      original_name: string;
      type: string;
    }[],
    replyTo: ReplyInfo | null,
  ): MessagePart[] {
    const parts: MessagePart[] = [];

    if (replyTo) {
      parts.push({
        type: "reply",
        message_id: replyTo.messageId,
        selected_text: replyTo.selectedText,
      });
    }

    if (prompt) {
      parts.push({
        type: "plain",
        text: prompt,
      });
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

    return parts;
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
    const controller = new AbortController();
    currentRequestController.value = controller;

    const response = await fetch(resolveApiUrl("/api/chat/send"), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: "Bearer " + localStorage.getItem("token"),
      },
      signal: controller.signal,
      body: JSON.stringify({
        message: messageToSend,
        session_id: currSessionId.value,
        selected_provider: selectedProviderId,
        selected_model: selectedModelName,
        enable_streaming: enableStreaming.value,
      }),
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const reader = response.body!.getReader();
    currentReader.value = reader;
    const decoder = new TextDecoder();
    const processChunk = createStreamChunkProcessor();

    isStreaming.value = true;

    for (;;) {
      try {
        const { done, value } = await reader.read();
        if (done) {
          if (currSessionId.value) {
            await getSessionMessages(currSessionId.value);
          }
          break;
        }

        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split("\n\n");

        for (let i = 0; i < lines.length; i++) {
          const line = lines[i].trim();
          if (!line) continue;

          let chunkJson: StreamChunk;
          try {
            chunkJson = JSON.parse(line.replace("data: ", ""));
          } catch (parseError) {
            console.warn("JSON解析失败:", line, parseError);
            continue;
          }

          await processChunk(chunkJson);
        }
      } catch (readError) {
        if (!userStopRequested.value) {
          console.error("SSE读取错误:", readError);
        }
        break;
      }
    }
  }

  async function sendMessageViaWebSocket(
    messageParts: MessagePart[],
    selectedProviderId: string,
    selectedModelName: string,
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
        finish,
      });

      try {
        ws.send(
          JSON.stringify({
            ct: "chat",
            t: "send",
            message_id: messageId,
            session_id: currSessionId.value,
            message: messageParts,
            selected_provider: selectedProviderId,
            selected_model: selectedModelName,
            enable_streaming: enableStreaming.value,
          }),
        );
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
    stagedFiles: {
      attachment_id: string;
      url: string;
      original_name: string;
      type: string;
    }[],
    audioName: string,
    selectedProviderId: string,
    selectedModelName: string,
    replyTo: ReplyInfo | null = null,
  ) {
    const userMessageParts: MessagePart[] = [];

    if (replyTo) {
      userMessageParts.push({
        type: "reply",
        message_id: replyTo.messageId,
        selected_text: replyTo.selectedText,
      });
    }

    if (prompt) {
      userMessageParts.push({
        type: "plain",
        text: prompt,
      });
    }

    for (const f of stagedFiles) {
      const partType =
        f.type === "image" ? "image" : f.type === "record" ? "record" : "file";

      const embeddedUrl = await getAttachment(f.attachment_id);

      userMessageParts.push({
        type: partType,
        attachment_id: f.attachment_id,
        filename: f.original_name,
        embedded_url: partType !== "file" ? embeddedUrl : undefined,
        embedded_file:
          partType === "file"
            ? {
                attachment_id: f.attachment_id,
                filename: f.original_name,
              }
            : undefined,
      });
    }

    if (audioName) {
      userMessageParts.push({
        type: "record",
        embedded_url: audioName,
      });
    }

    const userMessage: MessageContent = {
      type: "user",
      message: userMessageParts,
    };

    messages.value.push({ content: userMessage });

    const loadingMessage = reactive<MessageContent>({
      type: "bot",
      message: [],
      reasoning: "",
      isLoading: true,
    });
    messages.value.push({ content: loadingMessage });

    try {
      activeStreamCount.value++;
      if (activeStreamCount.value === 1) {
        isConvRunning.value = true;
      }

      userStopRequested.value = false;
      currentRunningSessionId.value = currSessionId.value;

      const backendMessageParts = buildBackendMessageParts(
        prompt,
        stagedFiles,
        replyTo,
      );
      const hasAttachmentOrReply = stagedFiles.length > 0 || !!replyTo;

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
        const messageToSend: string | MessagePart[] = hasAttachmentOrReply
          ? backendMessageParts
          : prompt;
        await sendMessageViaSSE(
          messageToSend,
          selectedProviderId,
          selectedModelName,
        );
      }

      onSessionsUpdate();
    } catch (err) {
      if (!userStopRequested.value) {
        console.error("发送消息失败:", err);
      }
      const lastMsg = messages.value[messages.value.length - 1];
      if (lastMsg?.content?.isLoading) {
        messages.value.pop();
      }
    } finally {
      isStreaming.value = false;
      currentReader.value = null;
      currentRequestController.value = null;
      currentRunningSessionId.value = "";
      currentWsMessageId.value = "";
      userStopRequested.value = false;
      activeStreamCount.value--;
      if (activeStreamCount.value === 0) {
        isConvRunning.value = false;
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

function cloneContentWithEditedText(
  record: ChatRecord,
  editedText: string,
): ChatContent {
  const content = record.content || { type: "bot", message: [] };
  const message = Array.isArray(content.message)
    ? content.message.map((part) => ({ ...part }))
    : [];
  let replaced = false;
  for (const part of message) {
    if (part.type === "plain") {
      part.text = editedText;
      replaced = true;
      break;
    }
  }
  if (!replaced && editedText) {
    message.push({ type: "plain", text: editedText });
  }
  return {
    ...content,
    message,
  };
}

function stripUploadOnlyFields(part: MessagePart): MessagePart {
  const copied = { ...part };
  delete copied.path;
  return copied;
}

function normalizeSessionProject(value: unknown): ChatSessionProject | null {
  if (!value || typeof value !== "object") return null;
  const project = value as Record<string, unknown>;
  if (
    typeof project.project_id !== "string" ||
    typeof project.title !== "string"
  ) {
    return null;
  }

  return {
    project_id: project.project_id,
    title: project.title,
    emoji: typeof project.emoji === "string" ? project.emoji : undefined,
  };
}

export function normalizeMessageParts(
  parts: unknown,
  legacyReasoning = "",
): MessagePart[] {
  const normalizedParts = normalizePartsInternal(parts);
  if (legacyReasoning && !normalizedParts.some((part) => part.type === "think")) {
    normalizedParts.unshift({ type: "think", think: legacyReasoning });
  }
  return normalizedParts;
}

export function extractReasoningText(
  parts: MessagePart[] | unknown,
  legacyReasoning = "",
) {
  const normalizedParts = Array.isArray(parts)
    ? parts
    : normalizeMessageParts(parts, legacyReasoning);
  const text = normalizedParts
    .filter((part) => part.type === "think")
    .map((part) => String(part.think || ""))
    .join("");
  return text || legacyReasoning;
}

export function thinkingParts(content: ChatContent): MessagePart[] {
  const firstThinkingBlock = messageBlocks(content).find(
    (block) => block.kind === "thinking",
  );
  if (firstThinkingBlock) return firstThinkingBlock.parts;

  const fallbackReasoning = String(content.reasoning || "");
  return fallbackReasoning ? [{ type: "think", think: fallbackReasoning }] : [];
}

export function displayParts(content: ChatContent): MessagePart[] {
  return messageBlocks(content)
    .filter((block) => block.kind === "content")
    .flatMap((block) => block.parts);
}

export function messageBlocks(content: ChatContent): MessageDisplayBlock[] {
  const parts = Array.isArray(content.message)
    ? content.message
    : normalizeMessageParts(content.message, content.reasoning || "");

  const blocks: MessageDisplayBlock[] = [];
  let currentKind: MessageDisplayBlock["kind"] | null = null;
  let currentParts: MessagePart[] = [];

  for (const part of parts) {
    if (isEmptyPlainPart(part)) continue;

    const nextKind: MessageDisplayBlock["kind"] = isThinkingPart(part)
      ? "thinking"
      : "content";

    if (currentKind !== nextKind) {
      if (currentKind && currentParts.length) {
        blocks.push({ kind: currentKind, parts: currentParts });
      }
      currentKind = nextKind;
      currentParts = [{ ...part }];
      continue;
    }

    currentParts.push({ ...part });
  }

  if (currentKind && currentParts.length) {
    blocks.push({ kind: currentKind, parts: currentParts });
  }

  if (!blocks.length && content.reasoning) {
    return [
      {
        kind: "thinking",
        parts: [{ type: "think", think: String(content.reasoning) }],
      },
    ];
  }

  return blocks;
}

function partToPayload(part: MessagePart) {
  if (part.type === "plain") return { type: "plain", text: part.text || "" };
  if (part.type === "reply") {
    return {
      type: "reply",
      message_id: part.message_id,
      selected_text: part.selected_text || "",
    };
  }
  return {
    type: part.type,
    attachment_id: part.attachment_id,
    filename: part.filename,
  };
}

async function readSseStream(
  body: ReadableStream<Uint8Array>,
  onPayload: (payload: any) => void,
) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split("\n\n");
    buffer = events.pop() || "";

    for (const event of events) {
      const data = event
        .split("\n")
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trimStart())
        .join("\n");
      if (!data) continue;
      try {
        onPayload(JSON.parse(data));
      } catch (error) {
        console.error("Failed to parse SSE payload:", error, data);
      }
    }
  }
}

function normalizePartsInternal(parts: unknown): MessagePart[] {
  if (typeof parts === "string") {
    return parts ? [{ type: "plain", text: parts }] : [];
  }
  if (!Array.isArray(parts)) return [];
  return parts.map((part: any) => {
    if (!part || typeof part !== "object") {
      return { type: "plain", text: String(part ?? "") };
    }
    if (part.type === "reasoning") {
      return {
        ...part,
        type: "think",
        think: String(part.think ?? part.text ?? ""),
      };
    }
    return { ...part };
  });
}

function isEmptyPlainPart(part: MessagePart) {
  return part.type === "plain" && !String(part.text || "");
}

function isThinkingPart(part: MessagePart) {
  return part.type === "think" || part.type === "tool_call";
}

function firstNonEmptyPartIndex(parts: MessagePart[]) {
  return parts.findIndex((part) => !isEmptyPlainPart(part));
}

export function appendPlain(record: ChatRecord, text: string, append = true) {
  markMessageStarted(record);
  const content = record.content;
  let last = content.message[content.message.length - 1];
  if (!last || last.type !== "plain") {
    last = { type: "plain", text: "" };
    content.message.push(last);
  }
  last.text = append ? `${last.text || ""}${text}` : text;
}

export function appendReasoningPart(record: ChatRecord, text: string) {
  markMessageStarted(record);
  if (!text) return;
  const content = record.content;
  const last = content.message[content.message.length - 1];
  if (last?.type === "think") {
    last.think = `${String(last.think || "")}${text}`;
  } else {
    content.message.push({ type: "think", think: text });
  }
  content.reasoning = extractReasoningText(content.message);
}

export function upsertToolCall(record: ChatRecord, toolCall: any) {
  markMessageStarted(record);
  if (!toolCall || typeof toolCall !== "object") return;
  const targetId = toolCall.id;
  if (targetId != null) {
    for (const part of record.content.message) {
      if (part.type !== "tool_call" || !Array.isArray(part.tool_calls)) continue;
      const matched = part.tool_calls.find((item) => item.id === targetId);
      if (matched) {
        Object.assign(matched, toolCall);
        return;
      }
    }
  }
  record.content.message.push({ type: "tool_call", tool_calls: [{ ...toolCall }] });
}

export function finishToolCall(record: ChatRecord, result: any) {
  markMessageStarted(record);
  if (!result || typeof result !== "object") return;
  const targetId = result.id;
  for (const part of record.content.message) {
    if (part.type !== "tool_call" || !Array.isArray(part.tool_calls)) continue;
    const tool = part.tool_calls.find((item) => item.id === targetId);
    if (tool) {
      tool.result = result.result;
      tool.finished_ts = result.ts || Date.now() / 1000;
      return;
    }

    userStopRequested.value = true;

    try {
      await axios.post("/api/chat/stop", {
        session_id: sessionId,
      });
    } catch (err) {
      console.error("停止会话失败:", err);
    }

    if (
      transportMode.value === "websocket" &&
      currentWebSocket.value?.readyState === WebSocket.OPEN
    ) {
      try {
        currentWebSocket.value.send(
          JSON.stringify({
            ct: "chat",
            t: "interrupt",
            session_id: sessionId,
            message_id: currentWsMessageId.value || undefined,
          }),
        );
      } catch (err) {
        console.error("发送 websocket interrupt 失败:", err);
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
  record.content.message.push({
    type: "tool_call",
    tool_calls: [
      {
        id: targetId,
        result: result.result,
        finished_ts: result.ts || Date.now() / 1000,
      },
    ],
  });
}

export function markMessageStarted(record: ChatRecord) {
  record.content.isLoading = false;
}

export function hasPlainText(record: ChatRecord) {
  return record.content.message.some(
    (part) =>
      part.type === "plain" && typeof part.text === "string" && part.text,
  );
}

export function payloadText(value: unknown) {
  if (typeof value === "string") return value;
  if (value == null) return "";
  if (typeof value === "object") {
    const payload = value as Record<string, unknown>;
    if (typeof payload.text === "string") return payload.text;
    if (typeof payload.content === "string") return payload.content;
    if (typeof payload.message === "string") return payload.message;
  }

export function parseJsonSafe(value: unknown) {
  if (typeof value !== "string") return value;
  try {
    return JSON.parse(value);
  } catch {
    return value;
  }
}
