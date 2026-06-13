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

  /**
   * todo_list 工具的最新快照,**按 session_id 隔离**。
   *
   * 为什么用 ref + 整体对象替换(而非 reactive 字典的 SET 单个 key):
   *   1. 不同会话的 todo 列表互不相关,A 会话的 add 不应影响 B 会话的 sidebar。
   *   2. Vue 3 的 reactive 字典在 SET 一个新 key 时,set trap 触发了依赖,
   *      但**首次访问(只读)时建立的依赖关系**对后续 SET 新 key 偶尔不可靠
   *      (尤其当 Chat.vue 的 computed 首次执行时 key 不存在,后续写入时
   *      computed 内部读取走的是 `reactive[key]`,会追踪 — 看似 OK 但
   *      实际生产中多次报告不更新)。
   *   3. 改用 ref + 整体赋值 `value = {...current, [sid]: snap}`:
   *      - ref 的 set 100% 触发 ref 依赖
   *      - 整体对象赋值让 Vue 重新建立深响应关系
   *      - 性能:todo list 至多几十项,整体赋值开销可忽略
   */
  const latestTodoSnapshotBySession = ref<
    Record<
      string,
      { list: any; stats: any; attentionItems: number[] } | null
    >
  >({});

  /**
   * 方案三: 收集再批量更新。
   * 当同一个 SSE chunk 内包含多个 tool_call_result 事件时,
   * Vue 3 的同步批处理会导致中间状态的 ref 更新被合并,
   * 最终 computed 求值可能拿到非预期的中间快照。
   *
   * 解决: processStreamPayload 中不立即写 ref,而是存入
   * _pendingTodoSnapshots (后面的覆盖前面的),在 SSE chunk
   * 处理完毕、进入下一轮 await 之前,通过 _flushTodoSnapshots()
   * 一次性将最新快照写入 ref,保证 Vue 在一个 tick 内只做一次
   * ref 赋值,computed 求值看到的就是该 chunk 的最新状态。
   *
   * @author astrbot / 2026-06-10
   */
  // value 可能是 Snapshot | null:
  //   - Snapshot: 来自 todo_create / todo_modify(add|update) / todo_modify(delete-单条) /
  //               todo_query  的正常快照(后端会回传 list+stats+attention_items)
  //   - null:     来自 todo_clear — 显式清空,或 todo_modify(delete) 把最后一项
  //               删光(effective_total===0) 时也走 null 让 bar 隐藏
  const _pendingTodoSnapshots: Record<
    string,
    { list: any; stats: any; attentionItems: number[] } | null
  > = {};

  function _flushTodoSnapshots() {
    const keys = Object.keys(_pendingTodoSnapshots);
    if (keys.length === 0) return;
    const updates: Record<
      string,
      { list: any; stats: any; attentionItems: number[] } | null
    > = {};
    for (const sid of keys) {
      updates[sid] = _pendingTodoSnapshots[sid];
      delete _pendingTodoSnapshots[sid];
    }
    // [DEBUG-keep] 临时诊断: 用于定位"快速调用时气泡不更新"问题
    for (const sid of keys) {
      const snap = updates[sid];
      // eslint-disable-next-line no-console
      console.log(
        "[todo-flush]",
        new Date().toISOString().slice(11, 23),
        "stats.done=",
        snap?.stats?.done,
        "items=",
        snap?.list?.items?.length,
      );
    }
    latestTodoSnapshotBySession.value = {
      ...latestTodoSnapshotBySession.value,
      ...updates,
    };
  }

  /**
   * 尝试从 tool result 解析出 todo_list 快照。识别特征:
   *   1. result 是 dict 且含 list.items 数组 + stats 字段(直出格式)
   *   2. result 是 dict 且含 ok+data 结构,data 里有 list/stats(spcode 包装格式)
   *   3. result 是 JSON 字符串,parse 后匹配上面任一模式
   * 返回 null 表示不是 todo_list 或数据格式不识别。
   */
  function _tryParseTodoSnapshot(rawResult: unknown): {
    list: any;
    stats: any;
    attentionItems: number[];
  } | null {
    if (rawResult == null) return null;
    let parsed: any = rawResult;
    if (typeof parsed === "string") {
      const trimmed = parsed.trim();
      if (!trimmed) return null;
      try {
        parsed = JSON.parse(trimmed);
      } catch {
        return null;
      }
    }
    if (!parsed || typeof parsed !== "object") return null;
    // 剥 envelope: {ok:true, data:{...}} → {...}
    if (
      parsed.ok === true &&
      parsed.data &&
      typeof parsed.data === "object"
    ) {
      parsed = parsed.data;
    }
    if (
      !parsed.list ||
      typeof parsed.list !== "object" ||
      !Array.isArray(parsed.list.items) ||
      !parsed.stats ||
      typeof parsed.stats !== "object"
    ) {
      return null;
    }
    return {
      list: parsed.list,
      stats: parsed.stats,
      attentionItems: Array.isArray(parsed.attention_items)
        ? parsed.attention_items
        : [],
    };
  }

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
        processStreamPayload(botRecord, payload, undefined, sessionId);
        options.onStreamUpdate?.(sessionId);
      }, () => {
        _flushTodoSnapshots();
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
          processStreamPayload(botRecord, payload, userRecord, sessionId);
          options.onStreamUpdate?.(sessionId);
        }, () => {
          _flushTodoSnapshots();
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
        processStreamPayload(botRecord, payload, userRecord, sessionId);
        // WebSocket 消息逐条到达，但为保持一致性：
        // 如果单条 WS 消息内含多个 tool_call_result 数据，
        // 由 _flushTodoSnapshots 统一提交最新快照。
        _flushTodoSnapshots();
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
        const parsedResult = parseJsonSafe(data);
        // 多层穿透: 后端 SSE event 的 data 字段可能是
        //   {id, ts, result: <dict | string>}  (A/B)
        //   {id, ts, data:   <dict | string>}  (C/D)
        //   或 tool 返回 dict 本身              (E)
        // 任何一种,都尝试穿透到 list+stats 字段。
        function unwrapTodoResult(input: unknown): unknown {
          if (input == null) return input;  // ← 关键:不要返回 null,避免丢数据
          if (typeof input === "string") {
            const trimmed = input.trim();
            if (!trimmed) return input;  // 空字符串:回退 input
            try { return unwrapTodoResult(JSON.parse(trimmed)); }
            catch { return input; }
          }
          if (Array.isArray(input)) return input;
          if (typeof input !== "object") return input;
          const obj = input as Record<string, unknown>;
          if (obj.list && obj.stats) return obj;  // E: 已经是 tool 返回
          // 关键:result 是空字符串/null 时不要穿透(避免链断裂丢数据)
          if (obj.result != null) {
            if (typeof obj.result === "string" && !obj.result.trim()) {
              // 空字符串 result → 跳过这个字段,继续尝试 data
            } else {
              return unwrapTodoResult(obj.result);  // A/B
            }
          }
          if (obj.data != null) return unwrapTodoResult(obj.data);    // C/D
          return input;
        }
        const toolResult = unwrapTodoResult(parsedResult);

        // 反查 tool_call 拿到工具名,用于更精准的 clear / 空列表检测。
        // 优先按 SSE event 的 id 字段匹配;若 id 不在,fallback 到 data.result.id。
        // 没匹配上就当普通工具处理,不影响原行为。
        const toolCallId =
          (parsedResult as any)?.id ?? (toolResult as any)?.id;
        let toolName: string | undefined;
        if (toolCallId && botRecord?.content?.message) {
          for (const part of botRecord.content.message) {
            if (part.type !== "tool_call" || !Array.isArray(part.tool_calls)) continue;
            const tc = (part.tool_calls as ToolCall[]).find(
              (t) => t?.id === toolCallId,
            );
            if (tc) { toolName = tc.name; break; }
          }
        }

        if (sessionId && toolResult && typeof toolResult === "object" && !Array.isArray(toolResult)) {
          const snap = _tryParseTodoSnapshotExternal(toolResult);
          if (snap) {
            // 情况 A: 正常快照 (todo_create / todo_modify(add|update) /
            //          todo_modify(delete-单条,list 还非空) / todo_query)
            //   进一步细分: 如果 effective_total === 0 (例如 todo_modify(delete) 把
            //   最后一项删光,或 todo_create 时 items=[]), UI 上没有可总结的内容,
            //   也走 null 让 bar 隐藏。
            //   注意: stats.effective_total 已排除 cancelled 项,所以这是"实际还有多少要做"的真实计数。
            if (
              typeof snap.stats?.effective_total === "number" &&
              snap.stats.effective_total === 0
            ) {
              _pendingTodoSnapshots[sessionId] = null;
            } else {
              // 方案三: 收集快照到 pending map,同一 chunk 内后续的 snapshot 自动覆盖之前的,
              // 由 _flushTodoSnapshots() 在 chunk 边界统一写入 ref。
              _pendingTodoSnapshots[sessionId] = snap;
            }
          } else {
            // 情况 B: 不是带 list/stats 的快照, 检查 clear 信号。
            //   优先级: 工具名(最稳) > 数据特征(兜底)
            if (toolName === "todo_clear") {
              // B-1: 工具名 = todo_clear → 必是清空
              _pendingTodoSnapshots[sessionId] = null;
            } else {
              // B-2: 数据特征兜底, 兼容 botRecord 里没匹配到 tool_call 的边缘情况
              //   (例如 tool_call_result 早于 tool_call 到达的极端 race)
              const inner =
                (toolResult as any).ok === true && (toolResult as any).data &&
                typeof (toolResult as any).data === "object"
                  ? (toolResult as any).data
                  : toolResult;
              if (inner && (inner as any).deleted === "list") {
                _pendingTodoSnapshots[sessionId] = null;
              }
            }
          }
        }
        finishToolCall(botRecord, parsedResult);
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

export function reasoningActivityCounts(
  parts: MessagePart[] | unknown,
  legacyReasoning = "",
) {
  const normalizedParts = Array.isArray(parts)
    ? parts
    : normalizeMessageParts(parts, legacyReasoning);
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
  return [
    counts.thinkCount > 0
      ? tm("reasoning.thinkSummary", { count: counts.thinkCount })
      : "",
    counts.toolCount > 0
      ? tm("reasoning.toolSummary", { count: counts.toolCount })
      : "",
  ]
    .filter(Boolean)
    .join(tm("reasoning.summarySeparator")) || tm("reasoning.thinking");
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

/**
 * @param onBatchComplete — 每个 SSE chunk 处理完毕后调用。
 *   用于批量提交在同一个同步 tick 内收集到的待处理数据
 *   (如 todo_list 快照),避免 Vue 3 响应式批处理导致中间
 *   状态的非预期渲染。
 *   @author astrbot / 2026-06-10
 */
async function readSseStream(
  body: ReadableStream<Uint8Array>,
  onPayload: (payload: any) => void,
  onBatchComplete?: () => void,
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

    onBatchComplete?.();
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

export function finishToolCall(
  record: ChatRecord,
  result: any,
) {
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

/**
 * 导出版本的 _tryParseTodoSnapshot,供 finishToolCall (上面) 使用,
 * 因为该函数定义在 useMessages 闭包内,需要单独 export 一份给外部调用。
 */
function _tryParseTodoSnapshotExternal(rawResult: unknown): {
  list: any;
  stats: any;
  attentionItems: number[];
} | null {
  if (rawResult == null) return null;
  let parsed: any = rawResult;
  if (typeof parsed === "string") {
    const trimmed = parsed.trim();
    if (!trimmed) return null;
    try {
      parsed = JSON.parse(trimmed);
    } catch {
      return null;
    }
  }
  if (!parsed || typeof parsed !== "object") return null;
  if (
    parsed.ok === true &&
    parsed.data &&
    typeof parsed.data === "object"
  ) {
    parsed = parsed.data;
  }
  if (
    !parsed.list ||
    typeof parsed.list !== "object" ||
    !Array.isArray(parsed.list.items) ||
    !parsed.stats ||
    typeof parsed.stats !== "object"
  ) {
    return null;
  }
  return {
    list: parsed.list,
    stats: parsed.stats,
    attentionItems: Array.isArray(parsed.attention_items)
      ? parsed.attention_items
      : [],
  };
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
