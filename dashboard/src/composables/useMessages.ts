import { computed, onBeforeUnmount, reactive, ref, type Ref } from "vue";
import axios from "axios";

export type TransportMode = "sse" | "websocket";

export interface MessagePart {
  type: string;
  text?: string;
  target?: string;
  bot_id?: string;
  name?: string;
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

export interface GroupBot {
  bot_id: string;
  session_id?: string;
  name: string;
  avatar?: string;
  avatar_attachment_id?: string;
  conf_id: string;
  platform_id?: string;
}

export interface GroupProfile {
  session_id: string;
  name: string;
  avatar?: string;
  avatar_attachment_id?: string;
  description?: string;
}

export interface TypingState {
  sender_id: string;
  sender_name: string;
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
  targetBotId?: string;
  senderId?: string;
  senderName?: string;
  usePersistentWebSocket?: boolean;
  userRecord?: ChatRecord;
  botRecord?: ChatRecord;
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
  includeBot?: boolean;
}

interface ActiveBotRecordState {
  current?: ChatRecord;
  startNewAfterSave: boolean;
}

interface PendingChatRequest {
  botState: ActiveBotRecordState;
  userRecord?: ChatRecord;
}

interface PersistentChatConnection {
  sessionId: string;
  ws: WebSocket;
  openPromise: Promise<void>;
  pending: Record<string, PendingChatRequest>;
  subscriptionBotStates: Record<string, ActiveBotRecordState>;
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
  const groupBotsBySession = reactive<Record<string, GroupBot[]>>({});
  const groupProfilesBySession = reactive<Record<string, GroupProfile | null>>({});
  const typingBySession = reactive<Record<string, TypingState[]>>({});
  const persistentChatConnections = reactive<Record<string, PersistentChatConnection>>(
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

  function setTypingState(sessionId: string, data: unknown) {
    const payload = data && typeof data === "object" ? data as Record<string, unknown> : {};
    const senderId = String(payload.sender_id || "");
    const senderName = String(payload.sender_name || senderId);
    if (!senderId) return;
    const current = typingBySession[sessionId] || [];
    if (payload.typing) {
      typingBySession[sessionId] = [
        ...current.filter((item) => item.sender_id !== senderId),
        { sender_id: senderId, sender_name: senderName },
      ];
      return;
    }
    typingBySession[sessionId] = current.filter(
      (item) => item.sender_id !== senderId,
    );
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
      attachThreads(records, payload.threads || []);
      await resolveRecordMedia(records);
      messagesBySession[sessionId] = records;
      sessionProjects[sessionId] = normalizeSessionProject(payload.project);
      groupBotsBySession[sessionId] = normalizeGroupBots(payload.group_bots);
      groupProfilesBySession[sessionId] = normalizeGroupProfile(payload.group);
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
    includeBot = true,
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

    let botRecord: ChatRecord | undefined;
    if (includeBot) {
      botRecord = {
        id: `local-bot-${messageId}`,
        created_at: new Date().toISOString(),
        content: {
          type: "bot",
          message: [{ type: "plain", text: "" }],
          reasoning: "",
          isLoading: true,
        },
      };
    }

    messagesBySession[sessionId].push(
      ...([userRecord, botRecord].filter(Boolean) as ChatRecord[]),
    );

    const sessionMessages = messagesBySession[sessionId];
    return {
      userRecord: includeBot
        ? sessionMessages[sessionMessages.length - 2]
        : sessionMessages[sessionMessages.length - 1],
      botRecord: includeBot
        ? sessionMessages[sessionMessages.length - 1]
        : undefined,
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
    targetBotId = "",
    senderId = "",
    senderName = "",
    usePersistentWebSocket = false,
    botRecord,
    userRecord,
    skipUserHistory = false,
    llmCheckpointId = null,
  }: SendMessageStreamOptions) {
    if (transport === "websocket") {
      if (usePersistentWebSocket) {
        const connection = ensurePersistentChatConnection(sessionId);
        sendPersistentChatMessage(
          connection,
          sessionId,
          messageId,
          parts,
          botRecord,
          userRecord,
          enableStreaming,
          selectedProvider,
          selectedModel,
          targetBotId,
          senderId,
          senderName,
        );
        return;
      }
      startWebSocketStream(
        sessionId,
        messageId,
        parts,
        botRecord,
        userRecord,
        enableStreaming,
        selectedProvider,
        selectedModel,
        targetBotId,
        senderId,
        senderName,
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
      targetBotId,
      senderId,
      senderName,
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
        message: [{ type: "plain", text: "" }],
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
      "",
      "",
      "",
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
      message: [{ type: "plain", text: "" }],
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
      const botState = createBotRecordState(botRecord);
      await readSseStream(response.body, (payload) => {
        processStreamPayload(botState, payload, undefined, sessionId);
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
    Object.values(persistentChatConnections).forEach((connection) => {
      connection.ws.close();
    });
  }

  function closePersistentChatConnections(exceptSessionId = "") {
    Object.entries(persistentChatConnections).forEach(([sessionId, connection]) => {
      if (sessionId === exceptSessionId) return;
      connection.ws.close();
      delete persistentChatConnections[sessionId];
    });
  }

  function ensurePersistentChatConnection(sessionId: string) {
    const existing = persistentChatConnections[sessionId];
    if (
      existing &&
      (existing.ws.readyState === WebSocket.CONNECTING ||
        existing.ws.readyState === WebSocket.OPEN)
    ) {
      return existing;
    }

    const token = encodeURIComponent(localStorage.getItem("token") || "");
    const ws = createUnifiedChatWebSocket(token);
    let didOpen = false;
    let resolveOpen: () => void = () => {};
    let rejectOpen: (error: Event) => void = () => {};
    const openPromise = new Promise<void>((resolve, reject) => {
      resolveOpen = resolve;
      rejectOpen = reject;
    });
    const connection: PersistentChatConnection = {
      sessionId,
      ws,
      openPromise,
      pending: {},
      subscriptionBotStates: {},
    };
    persistentChatConnections[sessionId] = connection;

    ws.onopen = () => {
      didOpen = true;
      ws.send(JSON.stringify({ ct: "chat", t: "bind", session_id: sessionId }));
      resolveOpen();
    };
    ws.onmessage = (event) => {
      handlePersistentChatPayload(connection, event.data);
    };
    ws.onerror = (event) => {
      rejectOpen(event);
      Object.values(connection.pending).forEach((pending) => {
        if (pending.botState.current) {
          appendPlain(pending.botState.current, "\n\nWebSocket connection failed.");
        }
      });
    };
    ws.onclose = async () => {
      if (!didOpen) rejectOpen(new Event("close"));
      if (persistentChatConnections[sessionId] === connection) {
        delete persistentChatConnections[sessionId];
      }
      Object.keys(connection.pending).forEach((messageId) => {
        delete activeConnections[sessionId];
        delete connection.pending[messageId];
      });
      await options.onSessionsChanged?.();
    };

    return connection;
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
    botRecord: ChatRecord | undefined,
    userRecord: ChatRecord | undefined,
    enableStreaming: boolean,
    selectedProvider: string,
    selectedModel: string,
    targetBotId: string,
    senderId: string,
    senderName: string,
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
        target_bot_id: targetBotId || undefined,
        sender_id: senderId || undefined,
        sender_name: senderName || undefined,
        _skip_user_history: skipUserHistory,
        _llm_checkpoint_id: llmCheckpointId || undefined,
      }),
      signal: abort.signal,
    })
      .then(async (response) => {
        if (!response.ok || !response.body) {
          throw new Error(`SSE connection failed: ${response.status}`);
        }
        const botState = createBotRecordState(botRecord);
        await readSseStream(response.body, (payload) => {
          processStreamPayload(botState, payload, userRecord, sessionId);
          options.onStreamUpdate?.(sessionId);
        });
      })
      .catch((error) => {
        if (abort.signal.aborted) return;
        if (botRecord) {
          appendPlain(botRecord, `\n\n${String(error?.message || error)}`);
        }
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
    botRecord: ChatRecord | undefined,
    userRecord: ChatRecord | undefined,
    enableStreaming: boolean,
    selectedProvider: string,
    selectedModel: string,
    targetBotId: string,
    senderId: string,
    senderName: string,
  ) {
    const token = encodeURIComponent(localStorage.getItem("token") || "");
    const ws = createUnifiedChatWebSocket(token);

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
          target_bot_id: targetBotId || undefined,
          sender_id: senderId || undefined,
          sender_name: senderName || undefined,
        }),
      );
    };
    const botState = createBotRecordState(botRecord);
    ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        processStreamPayload(botState, payload, userRecord, sessionId);
        options.onStreamUpdate?.(sessionId);
        if (payload.type === "end" || payload.t === "end") {
          ws.close();
        }
      } catch (error) {
        console.error("Failed to parse WebSocket payload:", error);
      }
    };
    ws.onerror = () => {
      if (botRecord) {
        appendPlain(botRecord, "\n\nWebSocket connection failed.");
      }
    };
    ws.onclose = async () => {
      delete activeConnections[sessionId];
      await options.onSessionsChanged?.();
    };
  }

  function sendPersistentChatMessage(
    connection: PersistentChatConnection,
    sessionId: string,
    messageId: string,
    parts: MessagePart[],
    botRecord: ChatRecord | undefined,
    userRecord: ChatRecord | undefined,
    enableStreaming: boolean,
    selectedProvider: string,
    selectedModel: string,
    targetBotId: string,
    senderId: string,
    senderName: string,
  ) {
    connection.pending[messageId] = {
      botState: createBotRecordState(botRecord),
      userRecord,
    };
    activeConnections[sessionId] = {
      sessionId,
      messageId,
      transport: "websocket",
    };

    connection.openPromise
      .then(() => {
        if (connection.ws.readyState !== WebSocket.OPEN) {
          throw new Error("WebSocket connection is not open.");
        }
        connection.ws.send(
          JSON.stringify({
            ct: "chat",
            t: "send",
            session_id: sessionId,
            message_id: messageId,
            message: parts.map(partToPayload),
            enable_streaming: enableStreaming,
            selected_provider: selectedProvider,
            selected_model: selectedModel,
            target_bot_id: targetBotId || undefined,
            sender_id: senderId || undefined,
            sender_name: senderName || undefined,
          }),
        );
      })
      .catch((error) => {
        delete activeConnections[sessionId];
        delete connection.pending[messageId];
        if (botRecord) {
          appendPlain(botRecord, `\n\n${String(error?.message || error)}`);
        }
        console.error("Persistent WebSocket chat failed:", error);
      });
  }

  function handlePersistentChatPayload(
    connection: PersistentChatConnection,
    rawPayload: string,
  ) {
    let payload: any;
    try {
      payload = JSON.parse(rawPayload);
    } catch (error) {
      console.error("Failed to parse WebSocket payload:", error);
      return;
    }

    const normalized =
      payload?.ct === "chat"
        ? { ...payload, type: payload.type || payload.t }
        : payload;
    const msgType = normalized?.type || normalized?.t;
    if (msgType === "session_bound") return;

    const messageId = String(normalized?.message_id || "");
    const pending = messageId ? connection.pending[messageId] : undefined;
    if (pending) {
      if (
        isGroupChatSession(connection.sessionId) &&
        msgType !== "user_message_saved"
      ) {
        processSubscriptionPayload(connection, normalized, msgType);
        options.onStreamUpdate?.(connection.sessionId);
        return;
      }
      processStreamPayload(
        pending.botState,
        normalized,
        pending.userRecord,
        connection.sessionId,
      );
      if (msgType === "end") {
        delete activeConnections[connection.sessionId];
        delete connection.pending[messageId];
        void options.onSessionsChanged?.();
      }
      options.onStreamUpdate?.(connection.sessionId);
      return;
    }

    processSubscriptionPayload(connection, normalized, msgType);
    options.onStreamUpdate?.(connection.sessionId);
  }

  function processSubscriptionPayload(
    connection: PersistentChatConnection,
    normalized: any,
    msgType: string | undefined,
  ) {
    const subscriptionStateKey = getSubscriptionStateKey(normalized);
    const subscriptionState =
      connection.subscriptionBotStates[subscriptionStateKey] ||
      createBotRecordState(undefined);
    connection.subscriptionBotStates[subscriptionStateKey] = subscriptionState;
    ensureSubscriptionBotRecord(subscriptionState, connection.sessionId, normalized);
    processStreamPayload(
      subscriptionState,
      normalized,
      undefined,
      connection.sessionId,
    );
    if (msgType === "complete" || msgType === "end") {
      delete connection.subscriptionBotStates[subscriptionStateKey];
      void options.onSessionsChanged?.();
    }
  }

  function getSubscriptionStateKey(payload: any) {
    const messageId = String(payload?.message_id || "");
    if (messageId) return messageId;
    const senderId = String(payload?.sender_id || payload?.data?.sender_id || "");
    return senderId ? `sender:${senderId}` : "__default__";
  }

  function ensureSubscriptionBotRecord(
    state: ActiveBotRecordState,
    sessionId: string,
    payload: any,
  ) {
    if (state.current || !startsNewBotRecord(payload)) return;
    state.current = appendFollowupBotRecord(sessionId);
  }

  function processStreamPayload(
    botState: ActiveBotRecordState,
    payload: any,
    userRecord?: ChatRecord,
    sessionId = options.currentSessionId.value,
  ) {
    const normalized =
      payload?.ct === "chat"
        ? { ...payload, type: payload.type || payload.t }
        : payload;
    const msgType = normalized?.type || normalized?.t;
    const chainType = normalized?.chain_type;
    const data = normalized?.data ?? "";

    if (msgType === "session_id" || msgType === "session_bound") return;
    if (msgType === "typing") {
      setTypingState(sessionId, data);
      return;
    }
    if (msgType === "user_message_saved") {
      if (userRecord) {
        userRecord.id = data?.id || userRecord.id;
        userRecord.created_at = data?.created_at || userRecord.created_at;
        userRecord.llm_checkpoint_id =
          data?.llm_checkpoint_id || userRecord.llm_checkpoint_id;
      }
      return;
    }
    const botRecord = getCurrentBotRecord(botState, sessionId, normalized);
    if (!botRecord) return;
    if (normalized.sender_id) {
      botRecord.sender_id = String(normalized.sender_id);
    }
    if (normalized.sender_name) {
      botRecord.sender_name = String(normalized.sender_name);
    }
    if (msgType === "message_saved") {
      if (data?.sender_id) {
        setTypingState(sessionId, {
          typing: false,
          sender_id: data.sender_id,
          sender_name: data.sender_name,
        });
      }
      markMessageStarted(botRecord);
      botRecord.id = data?.id || botRecord.id;
      botRecord.created_at = data?.created_at || botRecord.created_at;
      botRecord.llm_checkpoint_id =
        data?.llm_checkpoint_id || botRecord.llm_checkpoint_id;
      botRecord.sender_id = data?.sender_id || botRecord.sender_id;
      botRecord.sender_name = data?.sender_name || botRecord.sender_name;
      if (data?.refs) {
        messageContent(botRecord).refs = data.refs;
      }
      botState.startNewAfterSave = true;
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
      if (typeof normalized.reasoning === "string" && normalized.reasoning) {
        messageContent(botRecord).reasoning = normalized.reasoning;
      }
      const finalText = payloadText(data);
      if (finalText && !hasPlainText(botRecord)) {
        appendPlain(botRecord, finalText, false);
      }
      return;
    }
    if (msgType === "end") {
      if (botRecord.sender_id) {
        setTypingState(sessionId, {
          typing: false,
          sender_id: botRecord.sender_id,
          sender_name: botRecord.sender_name,
        });
      }
      markMessageStarted(botRecord);
      return;
    }

    if (msgType === "plain") {
      markMessageStarted(botRecord);
      if (botRecord.sender_id) {
        setTypingState(sessionId, {
          typing: false,
          sender_id: botRecord.sender_id,
          sender_name: botRecord.sender_name,
        });
      }
      if (chainType === "reasoning") {
        messageContent(botRecord).reasoning = `${
          messageContent(botRecord).reasoning || ""
        }${payloadText(data)}`;
        return;
      }
      if (chainType === "tool_call" && !isGroupChatSession(sessionId)) {
        upsertToolCall(botRecord, parseJsonSafe(data));
        return;
      }
      if (chainType === "tool_call_result") {
        finishToolCall(botRecord, parseJsonSafe(data));
        return;
      }
      appendPlain(
        botRecord,
        payloadText(data),
        isGroupChatSession(sessionId) || normalized.streaming !== false,
      );
      return;
    }

    if (msgType === "chain") {
      markMessageStarted(botRecord);
      const parts = Array.isArray(data) ? data : [];
      for (const part of parts) {
        if (!part || typeof part !== "object") continue;
        if (isGroupChatSession(sessionId) && part.type === "tool_call") continue;
        if (part.type === "plain") {
          appendPlain(
            botRecord,
            String(part.text || ""),
            isGroupChatSession(sessionId) || normalized.streaming !== false,
          );
        } else {
          messageContent(botRecord).message.push({ ...part });
        }
      }
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

    if (msgType === "at") {
      markMessageStarted(botRecord);
      const mention = parseJsonSafe(data);
      if (!mention || typeof mention !== "object") return;
      const target = String(
        mention.target || mention.bot_id || mention.qq || "",
      );
      const name = String(mention.name || "");
      if (!target && !name) return;
      messageContent(botRecord).message.push({ type: "at", target, name });
    }
  }

  function createBotRecordState(
    botRecord: ChatRecord | undefined,
  ): ActiveBotRecordState {
    return { current: botRecord, startNewAfterSave: false };
  }

  function getCurrentBotRecord(
    state: ActiveBotRecordState,
    sessionId: string,
    payload: any,
  ) {
    if (state.startNewAfterSave && startsNewBotRecord(payload)) {
      state.current = appendFollowupBotRecord(sessionId, state.current);
      state.startNewAfterSave = false;
    }
    return state.current;
  }

  function startsNewBotRecord(payload: any) {
    const msgType = payload?.type || payload?.t;
    if (msgType === "plain") return true;
    if (msgType === "chain") return true;
    if (msgType === "message_saved") return true;
    if (msgType === "at") return true;
    if (msgType === "error") return true;
    return ["image", "record", "file", "video"].includes(msgType);
  }

  function isGroupChatSession(sessionId: string) {
    return Boolean(groupProfilesBySession[sessionId]);
  }

  function appendFollowupBotRecord(sessionId: string, previous?: ChatRecord) {
    messagesBySession[sessionId] = messagesBySession[sessionId] || [];
    const record: ChatRecord = {
      id: `local-bot-${crypto.randomUUID?.() || Date.now()}`,
      created_at: new Date().toISOString(),
      sender_id: previous?.sender_id,
      sender_name: previous?.sender_name,
      content: {
        type: "bot",
        message: [{ type: "plain", text: "" }],
        reasoning: "",
        isLoading: true,
      },
    };
    messagesBySession[sessionId].push(record);
    return messagesBySession[sessionId][messagesBySession[sessionId].length - 1];
  }

  return {
    loadingMessages,
    sending,
    messagesBySession,
    loadedSessions,
    sessionProjects,
    groupBotsBySession,
    groupProfilesBySession,
    typingBySession,
    activeMessages,
    isSessionRunning,
    isUserMessage,
    isMessageStreaming,
    messageContent,
    messageParts,
    loadSessionMessages,
    ensurePersistentChatConnection,
    closePersistentChatConnections,
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

function createUnifiedChatWebSocket(token: string) {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return new WebSocket(
    `${protocol}//${window.location.host}/api/unified_chat/ws?token=${token}`,
  );
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
  if (part.type === "at") {
    return {
      type: "at",
      target: part.target || part.bot_id || "",
      name: part.name || "",
    };
  }
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

function normalizeGroupBots(value: unknown): GroupBot[] {
  if (!Array.isArray(value)) return [];
  const bots: GroupBot[] = [];
  for (const item of value) {
    if (!item || typeof item !== "object") continue;
    const bot = item as Record<string, unknown>;
    if (typeof bot.bot_id !== "string" || typeof bot.name !== "string") {
      continue;
    }
    bots.push({
      bot_id: bot.bot_id,
      name: bot.name,
      avatar: typeof bot.avatar === "string" ? bot.avatar : "",
      avatar_attachment_id:
        typeof bot.avatar_attachment_id === "string" ? bot.avatar_attachment_id : "",
      conf_id: typeof bot.conf_id === "string" ? bot.conf_id : "default",
      platform_id: typeof bot.platform_id === "string" ? bot.platform_id : "",
    });
  }
  return bots;
}

function normalizeGroupProfile(value: unknown): GroupProfile | null {
  if (!value || typeof value !== "object") return null;
  const group = value as Record<string, unknown>;
  if (typeof group.session_id !== "string" || typeof group.name !== "string") {
    return null;
  }
  return {
    session_id: group.session_id,
    name: group.name,
    avatar: typeof group.avatar === "string" ? group.avatar : "",
    avatar_attachment_id:
      typeof group.avatar_attachment_id === "string" ? group.avatar_attachment_id : "",
    description:
      typeof group.description === "string" ? group.description : "",
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
      tool.finished_ts = result.finished_ts || result.ts || Date.now() / 1000;
      return;
    }
  }
  record.content.message.push({
    type: "tool_call",
    tool_calls: [
      {
        ...result,
        result: result.result,
        finished_ts: result.finished_ts || result.ts || Date.now() / 1000,
      },
    ],
  });
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
