import { computed, onBeforeUnmount, reactive, ref, type Ref } from "vue";
import { chatApi, fileApi } from "@/api/v1";
import { fetchWithAuth } from "@/api/http";
import { useInteractiveChoiceStore } from "@/stores/interactiveChoice";
import {
  isInteractiveChoicePayload,
  validateInteractiveChoice,
  truncateInteractiveChoice,
} from "./parseInteractiveChoice";
import { applyInteractiveChoiceSse } from "./dispatchInteractiveChoice";
import { abandonPendingInteractiveChoices } from "./abandonPendingInteractiveChoices";
// Author: elecvoid243
// Date: 2026-07-05
// Plan: docs/superpowers/plans/2026-07-05-interactive-choice-history-roundtrip.md
// §2.4 Amendment F — keep the live SSE handler and the history
// reload path using the same predicates. The leaf module
// `askUserChoiceToolFilter.ts` has no `@/api` dependency so it is
// testable from a node-only test runner.
import {
  isAskUserChoiceToolCall,
  isAskUserChoiceToolCallResult,
} from "./askUserChoiceToolFilter";
// Author: elecvoid243
// Date: 2026-07-05
// Plan: docs/superpowers/plans/2026-07-05-interactive-choice-history-roundtrip.md
// §2.4 Amendment F — `normalizePartsInternal` was extracted to a
// leaf module so the ask_user_choice history-reload filter can be
// unit-tested without pulling in `@/api`.
import { normalizeMessageParts as normalizeMessagePartsFromLeaf } from "./normalizeMessageParts";

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
  stored_filename?: string;
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

/**
 * Todo 工具返回的标准化快照结构。
 *
 * 数据源:spcode 插件 4 个 todo 工具的 `call()` 返回值(经 `unwrap()` 包装成
 * `{"ok": true, "data": {list, stats, attention_items}}`)。前端在 SSE
 * `tool_call_result` 阶段从 tool.result 字符串中解析出来,按 sessionId 缓存,
 * 供 Chat.vue 的 todo summary bar / TodoSidebar 实时消费。
 *
 * - `list.items[].attention` 由后端在 `_build_list_state` 时注入,标识需要
 *   关注的 item(stuck/blocked:`in_progress` 且 `notes` 非空)。
 * - `attentionItems` 是后端的 attention id 数组(便于 summary bar 展示徽标)。
 */
export type TodoItemStatus = "pending" | "in_progress" | "done" | "cancelled";

export interface TodoItem {
  id: number;
  title: string;
  status: TodoItemStatus;
  notes?: string;
  attention?: boolean;
}

export interface TodoList {
  title: string;
  items: TodoItem[];
  created_at?: string;
  updated_at?: string;
  sender_key?: string;
  platform?: string;
  sender_id?: string;
  [key: string]: unknown;
}

export interface TodoStats {
  total: number;
  done: number;
  in_progress: number;
  pending: number;
  cancelled: number;
  effective_total: number;
  progress_pct: number;
  blocked_count?: number;
}

export interface TodoSnapshot {
  list: TodoList;
  stats: TodoStats;
  attentionItems: number[];
  /** 写入时间戳,便于在多次事件中排序/去抖。 */
  updatedAt: number;
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
  botRecord?: ChatRecord;
  userRecord?: ChatRecord;
  completed?: boolean;
  errorShown?: boolean;
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
  /**
   * Fired exactly once when a streaming response for a given session
   * ends — either because the server closed the stream normally, an
   * error terminated it, the user pressed stop, or the regenerate
   * path completed. Fires for both SSE and WebSocket transports.
   *
   * This is the canonical "bot just finished talking" signal. It is
   * the right hook for refetching authoritative state that the bot's
   * response may have mutated (for example the spcode project
   * status). Distinct from :attr:`onSessionsChanged` which also
   * fires for session-list mutations unrelated to any specific
   * stream; ``onStreamEnd`` is a pure stream-lifecycle event.
   *
   * Args:
   *   sessionId: The session whose stream just ended.
   */
  onStreamEnd?: (sessionId: string) => void;
}

export function useMessages(options: UseMessagesOptions) {
  const loadingMessages = ref(false);
  const sending = ref(false);
  const messagesBySession = reactive<Record<string, ChatRecord[]>>({});
  const loadedSessions = reactive<Record<string, boolean>>({});
  const activeConnections = reactive<Record<string, ActiveConnection>>({});
  const chatWebSockets: Record<string, WebSocket> = {};
  const closingChatWebSockets = new WeakSet<WebSocket>();
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
    const storedFilename =
      typeof part.stored_filename === "string" ? part.stored_filename : "";
    const lookupFilename = storedFilename || part.filename || "";
    if (part.attachment_id) {
      cacheKey = `att:${part.attachment_id}`;
      url = fileApi.contentUrl(part.attachment_id);
    } else if (lookupFilename) {
      cacheKey = `file:${lookupFilename}`;
      url = "";
    } else {
      return;
    }
    let promise = attachmentBlobCache.get(cacheKey);
    if (!promise) {
      if (!part.attachment_id && lookupFilename) {
        promise = fileApi
          .getByName(lookupFilename)
          .then((resp) => URL.createObjectURL(resp.data));
      } else {
        promise = fetchWithAuth(url).then(async (resp) => {
          if (!resp.ok) throw new Error(`Media request failed: ${resp.status}`);
          return URL.createObjectURL(await resp.blob());
        });
      }
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
        if (
          mediaTypes.includes(part.type) &&
          !part.embedded_url &&
          (part.attachment_id || part.stored_filename || part.filename)
        ) {
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
      const response = await chatApi.getSession(sessionId);
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

    // Bug 3 fix: see `abandonPendingInteractiveChoices` for the full
    // rationale. A typed chat-input message abandons any pending
    // ask_user_choice prompt — mark the current active set ignored
    // before pushing the new user_msg so the runtime reverse-walk
    // in `ChatMessageList.vue` no longer has to derive this state.
    abandonPendingInteractiveChoices(sessionId);

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
    const response = await chatApi.updateMessage(sessionId, record.id, {
      content: content as unknown as Record<string, unknown>,
    });
    const payload = response.data?.data || {};
    const updated = payload.message
      ? normalizeHistoryRecord(payload.message)
      : null;
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
      const response = await fetchWithAuth(
        chatApi.regenerateMessageUrl(sessionId, targetMessageId),
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            selected_provider: selectedProvider,
            selected_model: selectedModel,
          }),
          signal: abort.signal,
        },
      );
      if (!response.ok || !response.body) {
        throw new Error(`Regenerate failed: ${response.status}`);
      }
      const contentType = response.headers.get("content-type") || "";
      if (!contentType.includes("text/event-stream")) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.message || "Regenerate failed.");
      }
      await readSseStream(response.body, (payload) => {
        processStreamPayload(botRecord, payload, undefined, sessionId);
        options.onStreamUpdate?.(sessionId);
      });
    } catch (error) {
      if (!abort.signal.aborted) {
        appendPlain(
          botRecord,
          `\n\n${String((error as Error)?.message || error)}`,
        );
        console.error("Regenerate failed:", error);
      }
    } finally {
      delete activeConnections[sessionId];
      await options.onSessionsChanged?.();
      options.onStreamEnd?.(sessionId);
    }
  }

  async function stopSession(sessionId: string) {
    if (!sessionId) return;
    await chatApi.stopSession(sessionId);
  }

  function cleanupConnections() {
    Object.values(activeConnections).forEach((connection) => {
      connection.abort?.abort();
    });
    Object.values(chatWebSockets).forEach(closeTrackedWebSocket);
    Object.keys(activeConnections).forEach((sessionId) => {
      delete activeConnections[sessionId];
    });
    Object.keys(chatWebSockets).forEach((sessionId) => {
      delete chatWebSockets[sessionId];
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
      reasoning: extractReasoningText(
        normalizedMessage,
        content.reasoning || "",
      ),
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

    fetchWithAuth(chatApi.sendStreamUrl(), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
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
          processStreamPayload(botRecord, payload, userRecord, sessionId);
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
        options.onStreamEnd?.(sessionId);
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
    const ws = getOrCreateChatWebSocket(sessionId);

    activeConnections[sessionId] = {
      sessionId,
      messageId,
      transport: "websocket",
      ws,
      botRecord,
      userRecord,
      completed: false,
      errorShown: false,
    };

    sendWebSocketPayload(sessionId, messageId, {
      ct: "chat",
      t: "send",
      session_id: sessionId,
      message_id: messageId,
      message: parts.map(partToPayload),
      enable_streaming: enableStreaming,
      selected_provider: selectedProvider,
      selected_model: selectedModel,
    });
  }

  function getOrCreateChatWebSocket(sessionId: string) {
    const existing = chatWebSockets[sessionId];
    if (
      existing &&
      (existing.readyState === WebSocket.OPEN ||
        existing.readyState === WebSocket.CONNECTING)
    ) {
      return existing;
    }

    const token = localStorage.getItem("token") || "";
    const ws = new WebSocket(chatApi.unifiedWebSocketUrl(token));
    chatWebSockets[sessionId] = ws;

    ws.onmessage = (event) => {
      handleWebSocketMessage(sessionId, event);
    };
    ws.onerror = () => {
      const connection = activeConnections[sessionId];
      if (connection?.transport === "websocket" && connection.botRecord) {
        connection.errorShown = true;
        appendPlain(connection.botRecord, "\n\nWebSocket connection failed.");
      }
    };
    ws.onclose = async () => {
      if (chatWebSockets[sessionId] === ws) {
        delete chatWebSockets[sessionId];
      }

      const connection = activeConnections[sessionId];
      if (connection?.transport !== "websocket" || connection.ws !== ws) {
        return;
      }
      if (
        !connection.completed &&
        !connection.errorShown &&
        !closingChatWebSockets.has(ws) &&
        connection.botRecord
      ) {
        appendPlain(connection.botRecord, "\n\nWebSocket connection closed.");
      }
      delete activeConnections[sessionId];
      await options.onSessionsChanged?.();
      options.onStreamEnd?.(sessionId);
    };
    return ws;
  }

  function sendWebSocketPayload(
    sessionId: string,
    messageId: string,
    payload: Record<string, unknown>,
  ) {
    const ws = getOrCreateChatWebSocket(sessionId);
    const send = () => {
      const connection = activeConnections[sessionId];
      if (
        connection?.transport !== "websocket" ||
        connection.messageId !== messageId ||
        connection.ws !== ws
      ) {
        return;
      }
      try {
        ws.send(JSON.stringify(payload));
      } catch (error) {
        connection.errorShown = true;
        if (connection.botRecord) {
          appendPlain(connection.botRecord, "\n\nWebSocket connection failed.");
        }
        console.error("Failed to send WebSocket payload:", error);
        void finishWebSocketStream(sessionId, messageId);
      }
    };

    if (ws.readyState === WebSocket.OPEN) {
      send();
      return;
    }
    if (ws.readyState === WebSocket.CONNECTING) {
      ws.addEventListener("open", send, { once: true });
      return;
    }
    void finishWebSocketStream(sessionId, messageId);
  }

  function handleWebSocketMessage(sessionId: string, event: MessageEvent) {
    const connection = activeConnections[sessionId];
    if (connection?.transport !== "websocket" || !connection.botRecord) {
      return;
    }

    try {
      const payload = JSON.parse(event.data);
      processStreamPayload(
        connection.botRecord,
        payload,
        connection.userRecord,
        sessionId,
      );
      options.onStreamUpdate?.(sessionId);
      if (payload.type === "end" || payload.t === "end") {
        void finishWebSocketStream(sessionId, connection.messageId);
      }
    } catch (error) {
      console.error("Failed to parse WebSocket payload:", error);
    }
  }

  async function finishWebSocketStream(sessionId: string, messageId: string) {
    const connection = activeConnections[sessionId];
    if (
      connection?.transport !== "websocket" ||
      connection.messageId !== messageId
    ) {
      return;
    }
    connection.completed = true;
    delete activeConnections[sessionId];
    await options.onSessionsChanged?.();
    options.onStreamEnd?.(sessionId);
  }

  function closeTrackedWebSocket(ws: WebSocket) {
    closingChatWebSockets.add(ws);
    if (
      ws.readyState === WebSocket.OPEN ||
      ws.readyState === WebSocket.CONNECTING
    ) {
      ws.close();
    }
  }

  /**
   * spcode 插件 todo_* 工具的统一识别集合。
   *
   * v2.2.0 拆出 4 个独立工具(todo_create / todo_query / todo_modify /
   *   todo_clear);v2.12 进一步把 `todo_modify` 拆为 `todo_add` /
   *   `todo_update` / `todo_delete` 3 个独立工具。
   *   - create / query / add / update / delete:返回的 data 都含
   *     `list` / `stats` / `attention_items` 三件套,前端实时刷新
   *     todo summary bar 与 TodoSidebar。
   *   - clear:返回 null,显式置空(bar 立即消失)。
   * - `todo_list` / `todo_modify` 是 v2.2.0 / v2.12 之前的合并工具,这里
   *   保留以便兼容老会话历史中可能出现的 tool_call 事件。
   */
  const TODO_TOOL_NAMES: ReadonlySet<string> = new Set([
    "todo_create",
    "todo_query",
    "todo_add",
    "todo_update",
    "todo_delete",
    "todo_clear",
    "todo_modify", // legacy (v2.12 之前)
    "todo_list", // legacy (v2.2.0 之前)
  ]);

  /**
   * 按 sessionId 隔离的最新 todo 快照。
   *
   * - value[sid] = TodoSnapshot:
   *     todo_create/query/add/update/delete(及 v2.12 之前的 todo_modify)
   *     成功时写入。
   * - value[sid] = null:todo_clear 成功时显式置空(bar 立即消失)。
   * - key 不存在:该 session 尚未调用过 todo 工具(bar 不显示)。
   *
   * 写入策略:每次整体替换 `value = {...current, [sid]: snap}`,
   * 100% 触发依赖此 ref 的 computed 重算(Chat.vue 里的 currentTodoSnapshot)。
   * 整体替换而非 in-place 修改,是为了在 useMessages 多次调用 writeTodos
   * 时 Vue 一定能捕获到依赖变化(对 in-place 写入 `value[sid] = x`,
   * Vue 3 的 ref 对嵌套对象可能不触发响应,需要 .value = .value 触发)。
   */
  const latestTodoSnapshotBySession = ref<Record<string, TodoSnapshot | null>>(
    {},
  );

  /**
   * 从 tool.result(JSON 字符串)中解析出 TodoSnapshot。
   *
   * 返回值语义:
   * - `TodoSnapshot` 对象:write 进去,bar/sidebar 立即刷新。
   * - `null`:显式清空(todo_clear 成功路径)。
   * - `undefined`:保持现状 — 用于失败/无法解析的情况,避免覆盖已有快照。
   *
   * 协议参考:spcode 插件 `tools/_helpers.py` 中的 `unwrap()` —
   * 成功路径输出 `{"ok": true, "data": {list, stats, attention_items}, ...}`,
   * 失败路径输出 `{"ok": false, "error": "..."}`(或 err_json)。
   * 部分响应可能携带 `proposal` / `options` 字段,这些不影响 data 段。
   */
  function parseTodoToolResult(
    toolName: string,
    resultJson: string,
  ): TodoSnapshot | null | undefined {
    if (!resultJson || typeof resultJson !== "string") return undefined;
    let parsed: any;
    try {
      parsed = JSON.parse(resultJson);
    } catch {
      return undefined;
    }
    if (!parsed || typeof parsed !== "object") return undefined;

    // 失败路径 → 保持现状,不动快照
    if (parsed.ok === false) return undefined;

    // todo_clear 成功 → 显式置空(让 bar 立即消失)
    if (toolName === "todo_clear") {
      return null;
    }

    // 拆 envelope:{"ok": true, "data": {...}} → 取 data
    // 也兼容少数情况(老 todo_list 工具、proposal 路径等)data 直接挂在根上
    const data =
      parsed.ok === true && parsed.data && typeof parsed.data === "object"
        ? parsed.data
        : parsed;

    const list = data?.list;
    const stats = data?.stats;
    if (!list || typeof list !== "object") return undefined;
    if (!stats || typeof stats !== "object") return undefined;

    const attentionRaw = data?.attention_items;
    const attentionItems: number[] = Array.isArray(attentionRaw)
      ? attentionRaw.filter((n) => typeof n === "number")
      : [];

    return {
      list: list as TodoList,
      stats: stats as TodoStats,
      attentionItems,
      updatedAt: Date.now(),
    };
  }

  /**
   * 在 record 的 tool_call parts 中按 id 找到对应的 tool 调用项。
   * 用于在 tool_call_result 阶段反查 tool_name 和 tool.arguments。
   */
  function findToolCallById(
    record: ChatRecord,
    callId: string | number | undefined,
  ): ToolCall | null {
    if (callId == null) return null;
    for (const part of record.content.message) {
      if (part.type !== "tool_call" || !Array.isArray(part.tool_calls))
        continue;
      const matched = part.tool_calls.find((item) => item.id === callId);
      if (matched) return matched;
    }
    return null;
  }

  /**
   * 写入 / 清除某个 session 的 todo 快照。
   * 触发响应式更新(整体替换 ref.value)。
   */
  function writeTodoSnapshot(
    sessionId: string | null | undefined,
    snapshot: TodoSnapshot | null,
  ) {
    if (!sessionId) return;
    latestTodoSnapshotBySession.value = {
      ...latestTodoSnapshotBySession.value,
      [sessionId]: snapshot,
    };
  }

  // Author: elecvoid243
  // Date: 2026-07-05
  // Plan: docs/superpowers/plans/2026-07-05-interactive-choice-history-roundtrip.md
  // §2.4 Amendment F — closure-scoped set of call_ids whose `tool_call`
  // was filtered as `ask_user_choice`. The matching `tool_call_result`
  // event is dropped using this set (the result payload itself does
  // not carry the tool name, so we cannot tell from the payload
  // alone).
  //
  // Scoping note: this is a per-SSE-connection set. The dashboard
  // opens a fresh SSE stream for each message send, so cross-session
  // leakage is structurally impossible — there is no shared
  // long-lived store. The history reload path
  // (`normalizePartsInternal`) handles the persistent-data side
  // independently.
  const filteredToolCallIds = new Set<string>();

  function processStreamPayload(
    botRecord: ChatRecord,
    payload: any,
    userRecord?: ChatRecord,
    sessionId?: string,
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

    // ── InteractiveChoice (Plan Amendment E.1 / spec §5.1) ──────────
    // The backend's ask_user_choice plugin emits a top-level SSE event
    // (not embedded in a tool_call part) via
    // `_push_to_webchat_back_queue`. The dispatcher:
    //   1. parses + validates the wire payload into a part,
    //   2. pushes the part into `botRecord.content.message` so
    //      `ChatMessageList.vue` (which iterates `messageParts(msg)`)
    //      can render `<InteractiveChoiceBox>` immediately,
    //   3. mirrors the part into the Pinia store for hydrate / reconcile.
    // The store-only path is insufficient because the v-else-if
    // branch in `ChatMessageList.vue` reads from `messageParts(msg)`,
    // not from the store — without step (2) the box never mounts.
    if (msgType === "interactive_choice") {
      // Bug Y1 fix: scope the store write to the live session. We
      // guard on `sessionId` for safety — if a caller forgets to
      // thread sessionId through to a stream consumer, we skip the
      // write rather than dump the part into a phantom bucket.
      if (!sessionId) {
        console.warn(
          "[interactiveChoice] SSE event without sessionId; dropping",
        );
        return;
      }
      applyInteractiveChoiceSse(sessionId, botRecord, normalized);
      return;
    }

    if (msgType === "plain") {
      markMessageStarted(botRecord);
      if (chainType === "reasoning") {
        appendReasoningPart(botRecord, payloadText(data));
        return;
      }
      if (chainType === "tool_call") {
        const parsed = parseJsonSafe(data);
        // Author: elecvoid243
        // Date: 2026-07-05
        // Plan: docs/superpowers/plans/2026-07-05-interactive-choice-history-roundtrip.md
        // §2.4 Amendment F — `ask_user_choice` is rendered exclusively as
        // an `interactive_choice` part. Skip the corresponding
        // `tool_call` (and the matching `tool_call_result` below) so the
        // dashboard never shows a phantom "tool" entry next to the
        // InteractiveChoiceBox. Remember the id so the result can be
        // dropped in turn.
        if (isAskUserChoiceToolCall(parsed)) {
          const callId = (parsed as { id?: unknown } | null)?.id;
          if (typeof callId === "string" || typeof callId === "number") {
            filteredToolCallIds.add(String(callId));
          }
          return;
        }
        upsertToolCall(botRecord, parsed);
        return;
      }
      // Author: elecvoid243
      // Date: 2026-07-05
      // Plan: docs/superpowers/plans/2026-07-05-interactive-choice-history-roundtrip.md §2.4
      // The plugin emits the box as a chain_type event
      // (`type: "plain"`, `chain_type: "interactive_choice"`,
      // `data: <json string>`) so the chat_service can persist the
      // part into the bot record. We unwrap the JSON string into
      // the historical envelope `{type, data}` so
      // `applyInteractiveChoiceSse` and its downstream
      // `interactiveChoicePartFromSsePayload` helper need no
      // contract change.
      if (chainType === "interactive_choice") {
        if (!sessionId) {
          console.warn(
            "[interactiveChoice] SSE event without sessionId; dropping",
          );
          return;
        }
        const inner = parseJsonSafe(data);
        if (!inner || typeof inner !== "object") {
          console.warn(
            "[interactiveChoice] SSE data is not a JSON object; dropping",
          );
          return;
        }
        applyInteractiveChoiceSse(sessionId, botRecord, {
          type: "interactive_choice",
          data: inner,
        });
        return;
      }
      if (chainType === "tool_call_result") {
        const parsed = parseJsonSafe(data);
        // Author: elecvoid243
        // Date: 2026-07-05
        // Plan: docs/superpowers/plans/2026-07-05-interactive-choice-history-roundtrip.md
        // §2.4 Amendment F — Drop `tool_call_result` events whose matching
        // `tool_call` was an `ask_user_choice` (already filtered above).
        // `finishToolCall` would otherwise synthesise a name-less part on
        // miss, which renders as "tool" next to the InteractiveChoiceBox.
        if (isAskUserChoiceToolCallResult(botRecord, parsed, filteredToolCallIds)) {
          return;
        }
        finishToolCall(botRecord, parsed);

        // todo 工具结果 → 解析并写入按 sessionId 隔离的快照。
        // 注意:tool_call 事件先于 tool_call_result 到达,tool.name 已被
        // upsertToolCall 写入 botRecord,这里按 id 反查即可。
        if (sessionId && parsed && typeof parsed === "object") {
          const callId = (parsed as any).id;
          const matched = findToolCallById(botRecord, callId);
          const toolName = matched?.name;
          if (
            toolName &&
            TODO_TOOL_NAMES.has(toolName) &&
            typeof (parsed as any).result === "string"
          ) {
            const snapshot = parseTodoToolResult(
              toolName,
              (parsed as any).result,
            );
            // undefined → 保持现状;null → 清空;对象 → 写入。
            if (snapshot !== undefined) {
              writeTodoSnapshot(sessionId, snapshot);
            }
          }
        }
        return;
      }
      appendPlain(botRecord, payloadText(data), normalized.streaming !== false);
      return;
    }

    if (["image", "record", "file", "video"].includes(msgType)) {
      markMessageStarted(botRecord);
      const rawFilename = String(data)
        .replace("[IMAGE]", "")
        .replace("[RECORD]", "")
        .replace("[FILE]", "")
        .replace("[VIDEO]", "");
      const separatorIndex = rawFilename.indexOf("|");
      const storedFilename =
        separatorIndex >= 0 ? rawFilename.slice(0, separatorIndex) : rawFilename;
      const displayFilename =
        separatorIndex >= 0 ? rawFilename.slice(separatorIndex + 1) : storedFilename;
      const filename = displayFilename || storedFilename;
      const mediaPart: MessagePart = { type: msgType, filename };
      if (storedFilename && storedFilename !== filename) {
        mediaPart.stored_filename = storedFilename;
      }
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
    /**
     * 按 sessionId 隔离的最新 todo 快照。
     * Chat.vue 通过此字段渲染 todo summary bar 与 TodoSidebar。
     * 详见 `parseTodoToolResult` 注释。
     */
    latestTodoSnapshotBySession,
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
  fallbackReasoning = "",
): MessagePart[] {
  const normalizedParts = normalizePartsInternal(parts);
  if (
    fallbackReasoning &&
    !normalizedParts.some((part) => part.type === "think")
  ) {
    normalizedParts.unshift({ type: "think", think: fallbackReasoning });
  }
  return normalizedParts;
}

export function extractReasoningText(
  parts: MessagePart[] | unknown,
  fallbackReasoning = "",
) {
  const normalizedParts = Array.isArray(parts)
    ? parts
    : normalizeMessageParts(parts, fallbackReasoning);
  const text = normalizedParts
    .filter((part) => part.type === "think")
    .map((part) => String(part.think || ""))
    .join("");
  return text || fallbackReasoning;
}

export function reasoningActivityCounts(
  parts: MessagePart[] | unknown,
  fallbackReasoning = "",
) {
  const normalizedParts = Array.isArray(parts)
    ? parts
    : normalizeMessageParts(parts, fallbackReasoning);
  let thinkCount = 0;
  let toolCount = 0;

  for (const part of normalizedParts) {
    if (part.type === "think" && String(part.think || "").trim()) {
      thinkCount += 1;
    }
    if (part.type === "tool_call" && Array.isArray(part.tool_calls)) {
      toolCount += part.tool_calls.length;
    }
  }

  return { thinkCount, toolCount };
}

export function reasoningActivityTitle(
  counts: ReturnType<typeof reasoningActivityCounts>,
  tm: (key: string, params?: Record<string, string | number>) => string,
) {
  return (
    [
      counts.thinkCount > 0
        ? tm("reasoning.thinkSummary", { count: counts.thinkCount })
        : "",
      counts.toolCount > 0
        ? tm("reasoning.toolSummary", { count: counts.toolCount })
        : "",
    ]
      .filter(Boolean)
      .join(tm("reasoning.summarySeparator")) || tm("reasoning.thinking")
  );
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
  // Author: elecvoid243
  // Date: 2026-07-05
  // Plan: docs/superpowers/plans/2026-07-05-interactive-choice-history-roundtrip.md
  // §2.4 Amendment F — `normalizePartsInternal` was moved to a leaf
  // module (`normalizeMessageParts.ts`) so the ask_user_choice
  // history-reload filter can be unit-tested from a bare node
  // runner. This thin wrapper exists only to preserve the
  // `useMessages.ts` internal call sites and the public
  // `normalizeMessageParts` re-export.
  return normalizeMessagePartsFromLeaf(parts) as MessagePart[];
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
      if (part.type !== "tool_call" || !Array.isArray(part.tool_calls))
        continue;
      const matched = part.tool_calls.find((item) => item.id === targetId);
      if (matched) {
        Object.assign(matched, toolCall);
        return;
      }
    }
  }
  record.content.message.push({
    type: "tool_call",
    tool_calls: [{ ...toolCall }],
  });
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

// Author: elecvoid243
// Date: 2026-07-05
// Plan: docs/superpowers/plans/2026-07-05-interactive-choice-history-roundtrip.md
// §2.4 Amendment F — the predicate helpers
// `isAskUserChoiceToolCall` / `isAskUserChoiceToolCallResult` live
// in `askUserChoiceToolFilter.ts` (a leaf module with no `@/api`
// dependency) so the live SSE handler and the history reload path
// share one source of truth. The const
// `ASK_USER_CHOICE_TOOL_NAME` is exported from there directly;
// any consumer that previously imported it from `useMessages.ts`
// can switch to the leaf module without behavioural change.

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
  return String(value);
}

export function parseJsonSafe(value: unknown) {
  if (typeof value !== "string") return value;
  try {
    return JSON.parse(value);
  } catch {
    return value;
  }
}
