import { computed, onBeforeUnmount, reactive, ref, type Ref } from "vue";
import axios from "axios";

export type TransportMode = "sse" | "websocket";

export interface MessagePart {
  type: string;
  text?: string;
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

export interface ChatRecord {
  id?: string | number;
  content: ChatContent;
  created_at?: string;
  sender_id?: string;
  sender_name?: string;
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
  botRecord: ChatRecord;
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
      return false;
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
        message: [{ type: "plain", text: "" }],
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
  }: SendMessageStreamOptions) {
    if (transport === "websocket") {
      startWebSocketStream(
        sessionId,
        messageId,
        parts,
        botRecord,
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
      enableStreaming,
      selectedProvider,
      selectedModel,
    );
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
    const normalizedContent: ChatContent = {
      type: content.type || (record.sender_id === "bot" ? "bot" : "user"),
      message: normalizeParts(content.message || []),
      reasoning: content.reasoning || "",
      agentStats: content.agentStats || content.agent_stats,
      refs: content.refs,
    };

    return {
      ...record,
      content: normalizedContent,
    };
  }

  function normalizeParts(parts: unknown): MessagePart[] {
    if (typeof parts === "string") {
      return parts ? [{ type: "plain", text: parts }] : [];
    }
    if (!Array.isArray(parts)) return [];
    return parts.map((part: any) => {
      if (!part || typeof part !== "object")
        return { type: "plain", text: String(part ?? "") };
      return part;
    });
  }

  function startSseStream(
    sessionId: string,
    messageId: string,
    parts: MessagePart[],
    botRecord: ChatRecord,
    enableStreaming: boolean,
    selectedProvider: string,
    selectedModel: string,
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
      }),
      signal: abort.signal,
    })
      .then(async (response) => {
        if (!response.ok || !response.body) {
          throw new Error(`SSE connection failed: ${response.status}`);
        }
        await readSseStream(response.body, (payload) => {
          processStreamPayload(botRecord, payload);
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
        processStreamPayload(botRecord, payload);
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

  function processStreamPayload(botRecord: ChatRecord, payload: any) {
    const normalized =
      payload?.ct === "chat"
        ? { ...payload, type: payload.type || payload.t }
        : payload;
    const msgType = normalized?.type || normalized?.t;
    const chainType = normalized?.chain_type;
    const data = normalized?.data ?? "";

    if (msgType === "session_id" || msgType === "session_bound") return;
    if (msgType === "message_saved") {
      markMessageStarted(botRecord);
      botRecord.id = data?.id || botRecord.id;
      botRecord.created_at = data?.created_at || botRecord.created_at;
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
        messageContent(botRecord).reasoning = `${
          messageContent(botRecord).reasoning || ""
        }${payloadText(data)}`;
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
    stopSession,
    cleanupConnections,
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

function appendPlain(record: ChatRecord, text: string, append = true) {
  markMessageStarted(record);
  const content = record.content;
  let last = content.message[content.message.length - 1];
  if (!last || last.type !== "plain") {
    last = { type: "plain", text: "" };
    content.message.push(last);
  }
  last.text = append ? `${last.text || ""}${text}` : text;
}

function upsertToolCall(record: ChatRecord, toolCall: any) {
  markMessageStarted(record);
  if (!toolCall || typeof toolCall !== "object") return;
  record.content.message.push({ type: "tool_call", tool_calls: [toolCall] });
}

function finishToolCall(record: ChatRecord, result: any) {
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
  }
}

function markMessageStarted(record: ChatRecord) {
  record.content.isLoading = false;
}

function hasPlainText(record: ChatRecord) {
  return record.content.message.some(
    (part) =>
      part.type === "plain" && typeof part.text === "string" && part.text,
  );
}

function payloadText(value: unknown) {
  if (typeof value === "string") return value;
  if (value == null) return "";
  if (typeof value === "object") {
    const payload = value as Record<string, unknown>;
    if (typeof payload.text === "string") return payload.text;
    if (typeof payload.content === "string") return payload.content;
    if (typeof payload.message === "string") return payload.message;
  }
  return String(value);
}

function parseJsonSafe(value: unknown) {
  if (typeof value !== "string") return value;
  try {
    return JSON.parse(value);
  } catch {
    return value;
  }
}
