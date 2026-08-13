<template>
  <transition name="slide-left">
    <aside v-if="modelValue && thread" class="thread-panel">
      <div class="thread-panel-header">
        <div class="thread-panel-title">{{ tm("thread.title") }}</div>
        <div class="thread-panel-actions">
          <v-btn
            icon="mdi-delete-outline"
            class="thread-delete-button"
            size="small"
            variant="text"
            :title="tm('thread.delete')"
            :loading="deleting"
            :disabled="sending || deleting"
            @click="emit('delete', thread)"
          />
          <v-btn icon="mdi-close" size="small" variant="text" @click="close" />
        </div>
      </div>

      <blockquote class="thread-selected-text">
        {{ thread.selected_text }}
      </blockquote>

      <div ref="messagesEl" class="thread-messages">
        <div v-if="pagination.error" class="thread-load-error">
          <span>{{ pagination.error }}</span>
          <v-btn size="small" variant="text" @click="retryLoad">
            {{ tm("actions.retry") }}
          </v-btn>
        </div>
        <div v-if="pagination.has_more" class="thread-load-earlier">
          <v-btn
            size="small"
            variant="text"
            :loading="pagination.loading"
            @click="loadEarlier"
          >
            {{ tm("history.loadEarlier") }}
          </v-btn>
        </div>
        <ChatMessageList
          :messages="messages"
          :is-dark="isDark"
          :is-streaming="sending"
          variant="thread"
          @load-reasoning="loadReasoning"
        />
      </div>

      <form class="thread-composer" @submit.prevent="send">
        <textarea
          v-model="draft"
          class="thread-input"
          :placeholder="tm('thread.placeholder')"
          rows="1"
          :disabled="sending || pagination.loading"
          @keydown.enter.exact.prevent="send"
        ></textarea>
        <v-btn
          class="thread-send-button"
          variant="text"
          :loading="sending"
          :disabled="!draft.trim() || pagination.loading"
          type="submit"
        >
          {{ tm("input.send") }}
        </v-btn>
      </form>
    </aside>
  </transition>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, reactive, ref, watch } from "vue";
import { chatApi, fileApi } from "@/api/v1";
import { fetchWithAuth } from "@/api/http";
import {
  appendPlain,
  appendReasoningPart,
  buildChatRequestFlags,
  extractReasoningText,
  finishToolCall,
  hasPlainText,
  markMessageStarted,
  normalizeMessageParts,
  type HistoryPaginationState,
  parseJsonSafe,
  payloadText,
  upsertToolCall,
  type ChatRecord,
  type MessagePart,
  type ChatThread,
} from "@/composables/useMessages";
import { useModuleI18n } from "@/i18n/composables";
import ChatMessageList from "@/components/chat/ChatMessageList.vue";

const props = defineProps<{
  modelValue: boolean;
  thread: ChatThread | null;
  isDark: boolean;
  deleting?: boolean;
}>();

const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  delete: [thread: ChatThread];
}>();

const { tm } = useModuleI18n("features/chat");
const messages = ref<ChatRecord[]>([]);
const draft = ref("");
const sending = ref(false);
const messagesEl = ref<HTMLElement | null>(null);
const pagination = reactive<HistoryPaginationState>({
  page: 1,
  page_size: 50,
  total: 0,
  has_more: false,
  loading: false,
});
let loadEpoch = 0;
let streamAbort: AbortController | null = null;
const mediaUrls = new Set<string>();
const mediaPromises = new Map<string, Promise<string>>();

interface ActiveThreadRun {
  run_id: string;
  llm_checkpoint_id?: string | null;
  status?: string;
  content?: Record<string, unknown>;
}

function clearMediaUrls() {
  for (const url of mediaUrls) URL.revokeObjectURL(url);
  mediaUrls.clear();
  mediaPromises.clear();
}

function invalidateThread() {
  loadEpoch += 1;
  streamAbort?.abort();
  streamAbort = null;
  sending.value = false;
  clearMediaUrls();
}

watch(
  [() => props.modelValue, () => props.thread?.thread_id],
  ([isOpen, threadId]) => {
    invalidateThread();
    messages.value = [];
    pagination.error = undefined;
    pagination.page = 1;
    pagination.page_size = 50;
    pagination.total = 0;
    pagination.has_more = false;
    pagination.loading = Boolean(isOpen && threadId);
    if (isOpen && threadId) void loadThread(threadId);
  },
  { immediate: true },
);

function close() {
  invalidateThread();
  messages.value = [];
  emit("update:modelValue", false);
}

onBeforeUnmount(() => {
  invalidateThread();
  clearMediaUrls();
});

async function loadThread(threadId: string) {
  const epoch = ++loadEpoch;
  const previousPagination = { ...pagination };
  pagination.page = 1;
  pagination.page_size = 50;
  pagination.total = 0;
  pagination.has_more = false;
  pagination.loading = true;
  pagination.error = undefined;
  try {
    const response = await chatApi.getThread(threadId, { page: 1, page_size: 50 });
    if (epoch !== loadEpoch) return;
    if (response.data?.status !== "ok") {
      throw new Error(response.data?.message || "Failed to load thread messages");
    }
    const payload = response.data?.data || {};
    const history = payload.history || [];
    const records: ChatRecord[] = history.map(
      (record: any): ChatRecord => normalizeRecord(record),
    );
    await resolveRecordMedia(records, epoch);
    if (epoch !== loadEpoch || props.thread?.thread_id !== threadId) return;
    messages.value = records;
    pagination.page = Number(payload.page) || 1;
    pagination.page_size = Number(payload.page_size) || 50;
    pagination.total = Number(payload.total) || messages.value.length;
    pagination.has_more = Boolean(payload.has_more);
    scrollToBottom();
    const activeRun = (payload.active_runs || [])[0] as
      | ActiveThreadRun
      | undefined;
    if (activeRun?.run_id) {
      const existing = messages.value.find(
        (record) =>
          record.content?.type === "bot" &&
          activeRun.llm_checkpoint_id &&
          record.llm_checkpoint_id === activeRun.llm_checkpoint_id,
      );
      const botRecord =
        existing ||
        normalizeRecord({
          id: `active-run-${activeRun.run_id}`,
          content: activeRun.content || { type: "bot", message: [] },
          llm_checkpoint_id: activeRun.llm_checkpoint_id || null,
        });
      botRecord.content.isLoading =
        activeRun.status === "running" && botRecord.content.message.length === 0;
      if (!existing) messages.value.push(botRecord);
      void resumeActiveRun(threadId, activeRun, botRecord, epoch);
    }
  } catch (error) {
    if (epoch !== loadEpoch) return;
    console.error("Failed to load thread:", error);
    pagination.page = previousPagination.page;
    pagination.page_size = previousPagination.page_size;
    pagination.total = previousPagination.total;
    pagination.has_more = previousPagination.has_more;
    pagination.error = String((error as Error)?.message || error);
  } finally {
    if (epoch === loadEpoch && props.thread?.thread_id === threadId) {
      pagination.loading = false;
    }
  }
}

async function retryLoad() {
  const threadId = props.thread?.thread_id;
  if (!threadId || pagination.loading) return;
  if (messages.value.length && pagination.has_more) {
    await loadEarlier();
  } else {
    await loadThread(threadId);
  }
}

async function resolveRecordMedia(records: ChatRecord[], epoch: number) {
  const mediaTypes = new Set(["image", "record", "audio", "video"]);
  const tasks: Promise<void>[] = [];
  for (const record of records) {
    for (const part of record.content?.message || []) {
      if (
        !mediaTypes.has(part.type) ||
        part.embedded_url ||
        !(part.attachment_id || part.stored_filename || part.filename)
      ) {
        continue;
      }
      const lookupFilename = part.stored_filename || part.filename || "";
      const cacheKey = part.attachment_id
        ? `attachment:${part.attachment_id}`
        : `file:${lookupFilename}`;
      let promise = mediaPromises.get(cacheKey);
      if (!promise) {
        promise = part.attachment_id
          ? fetchWithAuth(fileApi.contentUrl(part.attachment_id)).then(
              async (response) => {
                if (!response.ok) {
                  throw new Error(`Media request failed: ${response.status}`);
                }
                return URL.createObjectURL(await response.blob());
              },
            )
          : fileApi
              .getByName(lookupFilename)
              .then((response) => URL.createObjectURL(response.data));
        mediaPromises.set(cacheKey, promise);
      }
      tasks.push(
        promise
          .then((url) => {
            if (epoch === loadEpoch) {
              part.embedded_url = url;
              mediaUrls.add(url);
            } else {
              URL.revokeObjectURL(url);
            }
          })
          .catch((error) => {
            mediaPromises.delete(cacheKey);
            console.error("Failed to resolve thread media:", cacheKey, error);
          }),
      );
    }
  }
  await Promise.all(tasks);
}

async function loadEarlier() {
  const threadId = props.thread?.thread_id;
  if (!threadId || pagination.loading || !pagination.has_more) return;
  const epoch = loadEpoch;
  const anchor = messages.value[0];
  const anchorId = anchor?.id == null ? "" : String(anchor.id);
  const anchorTop = anchorId
    ? messagesEl.value?.querySelector<HTMLElement>(
        `[data-message-id="${CSS.escape(anchorId)}"]`,
      )?.getBoundingClientRect().top
    : undefined;
  pagination.loading = true;
  try {
    const response = await chatApi.getThread(threadId, {
      page: pagination.page + 1,
      page_size: pagination.page_size,
    });
    if (epoch !== loadEpoch || props.thread?.thread_id !== threadId) return;
    if (response.data?.status !== "ok") {
      throw new Error(response.data?.message || "Failed to load earlier thread messages");
    }
    const payload = response.data?.data || {};
    const incoming: ChatRecord[] = (payload.history || []).map(
      (record: any): ChatRecord => normalizeRecord(record),
    );
    await resolveRecordMedia(incoming, epoch);
    if (epoch !== loadEpoch || props.thread?.thread_id !== threadId) return;
    const ids = new Set(messages.value.map((record) => String(record.id)));
    messages.value = [
      ...incoming.filter((record) => record.id == null || !ids.has(String(record.id))),
      ...messages.value,
    ];
    pagination.page = Number(payload.page) || pagination.page + 1;
    pagination.total = Number(payload.total) || pagination.total;
    pagination.has_more = Boolean(payload.has_more);
    pagination.error = undefined;
    await nextTick();
    if (
      anchorTop != null &&
      messagesEl.value &&
      anchorId &&
      epoch === loadEpoch &&
      props.thread?.thread_id === threadId
    ) {
      const row = messagesEl.value.querySelector<HTMLElement>(
        `[data-message-id="${CSS.escape(anchorId)}"]`,
      );
      if (row) messagesEl.value.scrollTop += row.getBoundingClientRect().top - anchorTop;
    }
  } catch (error) {
    if (epoch === loadEpoch && props.thread?.thread_id === threadId) {
      pagination.error = String((error as Error)?.message || error);
      console.error("Failed to load earlier thread messages:", error);
    }
  } finally {
    if (epoch === loadEpoch && props.thread?.thread_id === threadId) {
      pagination.loading = false;
    }
  }
}

async function loadReasoning(record: ChatRecord) {
  if (!record.hasReasoning || record.id == null || record.reasoningStatus === "loading") return;
  const threadId = props.thread?.thread_id;
  const epoch = loadEpoch;
  const requestId = String(record.id);
  record.reasoningStatus = "loading";
  try {
    const response = await chatApi.getMessage(record.id);
    const full = response.data?.data?.message;
    if (response.data?.status !== "ok") {
      throw new Error(response.data?.message || "Failed to load message reasoning");
    }
    if (!full) throw new Error("Reasoning message is unavailable");
    const normalized = normalizeRecord(full);
    await resolveRecordMedia([normalized], epoch);
    if (
      epoch !== loadEpoch ||
      props.thread?.thread_id !== threadId ||
      String(record.id) !== requestId
    ) {
      return;
    }
    Object.assign(record, normalized);
    record.reasoningStatus = "loaded";
  } catch (error) {
    if (
      epoch === loadEpoch &&
      props.thread?.thread_id === threadId &&
      String(record.id) === requestId
    ) {
      record.reasoningStatus = "error";
      record.reasoningError = String((error as Error)?.message || error);
    }
  }
}

function resumeActiveRun(
  threadId: string,
  run: ActiveThreadRun,
  botRecord: ChatRecord,
  epoch: number,
) {
  const abort = new AbortController();
  streamAbort = abort;
  sending.value = true;
  void (async () => {
    let receivedEnd = false;
    try {
      const response = await fetchWithAuth(chatApi.resumeRunStreamUrl(run.run_id), {
        headers: { Accept: "text/event-stream" },
        signal: abort.signal,
      });
      const contentType = response.headers.get("content-type") || "";
      if (
        !response.ok ||
        !response.body ||
        !contentType.includes("text/event-stream")
      ) {
        throw new Error(`Resume thread stream failed: ${response.status}`);
      }
      await readSseStream(response.body, (payload) => {
        if (
          epoch !== loadEpoch ||
          props.thread?.thread_id !== threadId ||
          !messages.value.includes(botRecord)
        ) {
          return;
        }
        processPayload(botRecord, undefined, payload);
        if ((payload?.type || payload?.t) === "end") receivedEnd = true;
        scrollToBottom(threadId, epoch);
      });
    } catch (error) {
      if (!abort.signal.aborted && epoch === loadEpoch) {
        console.error("Failed to resume thread stream:", error);
      }
    } finally {
      if (
        epoch === loadEpoch &&
        props.thread?.thread_id === threadId &&
        streamAbort === abort
      ) {
        streamAbort = null;
        sending.value = false;
        botRecord.content.isLoading = false;
        if (!receivedEnd) pagination.error = "Thread stream closed before completion.";
      }
    }
  })();
}

async function send() {
  if (
    !props.thread ||
    sending.value ||
    pagination.loading ||
    !draft.value.trim()
  ) {
    return;
  }
  const threadId = props.thread.thread_id;
  const epoch = loadEpoch;
  const text = draft.value.trim();
  draft.value = "";
  const messageId = crypto.randomUUID?.() || `${Date.now()}-${Math.random()}`;
  const userRecord: ChatRecord = {
    id: `local-thread-user-${messageId}`,
    created_at: new Date().toISOString(),
    content: {
      type: "user",
      message: [{ type: "plain", text }],
    },
  };
  const botRecord: ChatRecord = {
    id: `local-thread-bot-${messageId}`,
    created_at: new Date().toISOString(),
    content: {
      type: "bot",
      message: [],
      reasoning: "",
      isLoading: true,
    },
  };
  messages.value.push(userRecord, botRecord);
  const threadUserRecord = messages.value[messages.value.length - 2];
  const threadBotRecord = messages.value[messages.value.length - 1];
  scrollToBottom();

  const abort = new AbortController();
  streamAbort = abort;
  sending.value = true;
  try {
    const response = await fetchWithAuth(chatApi.sendThreadMessageUrl(threadId), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        message: [{ type: "plain", text }],
        flags: buildChatRequestFlags(),
      }),
      signal: abort.signal,
    });
    if (!response.ok || !response.body) {
      throw new Error(`Thread request failed: ${response.status}`);
    }
    await readSseStream(response.body, (payload) => {
      if (
        epoch !== loadEpoch ||
        props.thread?.thread_id !== threadId ||
        !messages.value.includes(threadBotRecord)
      ) {
        return;
      }
      processPayload(threadBotRecord, threadUserRecord, payload);
      scrollToBottom();
    });
  } catch (error) {
    if (
      epoch !== loadEpoch ||
      props.thread?.thread_id !== threadId ||
      abort.signal.aborted
    ) {
      return;
    }
    appendPlain(
      threadBotRecord,
      `\n\n${String((error as Error)?.message || error)}`,
    );
    console.error("Failed to send thread message:", error);
  } finally {
    if (
      epoch === loadEpoch &&
      props.thread?.thread_id === threadId &&
      streamAbort === abort
    ) {
      streamAbort = null;
      sending.value = false;
    }
  }
}

function normalizeRecord(record: any): ChatRecord {
  const content = record.content || {};
  const normalizedMessage = normalizeMessageParts(
    content.message || [],
    content.reasoning || "",
  );
  const reasoning = extractReasoningText(normalizedMessage, content.reasoning || "");
  const hasReasoning = record.has_reasoning === true || Boolean(reasoning);
  const reasoningLen = Number(record.reasoning_len);
  return {
    ...record,
    content: {
      type: content.type || (record.sender_id === "bot" ? "bot" : "user"),
      message: normalizedMessage,
      reasoning,
      agentStats: content.agentStats || content.agent_stats,
      refs: content.refs,
    },
    hasReasoning,
    reasoningLen:
      Number.isFinite(reasoningLen) && reasoningLen >= 0
        ? reasoningLen
        : reasoning.length,
    reasoningStatus: hasReasoning && !reasoning ? "unloaded" : "loaded",
  };
}

async function readSseStream(
  stream: ReadableStream<Uint8Array>,
  onPayload: (payload: any) => void,
) {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() || "";
    for (const chunk of chunks) {
      const data = chunk
        .split("\n")
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trimStart())
        .join("\n");
      if (!data) continue;
      try {
        onPayload(JSON.parse(data));
      } catch (error) {
        console.error("Failed to parse thread SSE payload:", error, data);
      }
    }
  }
}

function processPayload(
  botRecord: ChatRecord,
  userRecord: ChatRecord | undefined,
  payload: any,
) {
  const normalized =
    payload?.ct === "chat"
      ? { ...payload, type: payload.type || payload.t }
      : payload;
  const type = normalized?.type || normalized?.t;
  const chainType = normalized?.chain_type;
  const data = normalized?.data ?? "";

  if (type === "session_id" || type === "session_bound") return;

  if (type === "run_snapshot") {
    const snapshot = data && typeof data === "object" ? data : {};
    const snapshotRecord = normalizeRecord({
      id: botRecord.id,
      content: snapshot.content || { type: "bot", message: [] },
      llm_checkpoint_id: snapshot.llm_checkpoint_id || botRecord.llm_checkpoint_id,
    });
    botRecord.content = snapshotRecord.content;
    botRecord.hasReasoning = snapshotRecord.hasReasoning;
    botRecord.reasoningLen = snapshotRecord.reasoningLen;
    botRecord.reasoningStatus = snapshotRecord.reasoningStatus;
    botRecord.reasoningError = undefined;
    botRecord.llm_checkpoint_id = snapshotRecord.llm_checkpoint_id;
    botRecord.content.isLoading =
      snapshot.status === "running" && botRecord.content.message.length === 0;
    void resolveRecordMedia([botRecord], loadEpoch);
    return;
  }

  if (type === "user_message_saved") {
    if (!userRecord) return;
    userRecord.id = data?.id || userRecord.id;
    userRecord.created_at = data?.created_at || userRecord.created_at;
    userRecord.llm_checkpoint_id =
      data?.llm_checkpoint_id || userRecord.llm_checkpoint_id;
    return;
  }

  if (type === "message_saved") {
    markMessageStarted(botRecord);
    botRecord.id = data?.id || botRecord.id;
    botRecord.created_at = data?.created_at || botRecord.created_at;
    botRecord.llm_checkpoint_id =
      data?.llm_checkpoint_id || botRecord.llm_checkpoint_id;
    if (data?.refs) {
      botRecord.content.refs = data.refs;
    }
    return;
  }

  if (type === "agent_stats" || chainType === "agent_stats") {
    markMessageStarted(botRecord);
    botRecord.content.agentStats = data;
    return;
  }

  if (type === "error") {
    markMessageStarted(botRecord);
    appendPlain(botRecord, `\n\n${String(data)}`);
    return;
  }

  if (type === "complete" || type === "break") {
    markMessageStarted(botRecord);
    const finalText = payloadText(data);
    const existingText = botRecord.content.message
      .filter((part) => part.type === "plain")
      .map((part) => part.text || "")
      .join("");
    const missingText = finalText.slice(existingText.length);
    if (
      type === "complete" &&
      missingText &&
      finalText.startsWith(existingText)
    ) {
      appendPlain(botRecord, missingText);
    } else if (finalText && !hasPlainText(botRecord)) {
      appendPlain(botRecord, finalText, false);
    }
    return;
  }

  if (type === "end") {
    markMessageStarted(botRecord);
    return;
  }

  if (type === "plain") {
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

  if (["image", "record", "file", "video", "audio"].includes(type)) {
    markMessageStarted(botRecord);
    const rawFilename = String(data)
      .replace("[IMAGE]", "")
      .replace("[RECORD]", "")
      .replace("[FILE]", "")
      .replace("[VIDEO]", "")
      .replace("[AUDIO]", "");
    const separatorIndex = rawFilename.indexOf("|");
    const storedFilename =
      separatorIndex >= 0 ? rawFilename.slice(0, separatorIndex) : rawFilename;
    const displayFilename =
      separatorIndex >= 0 ? rawFilename.slice(separatorIndex + 1) : storedFilename;
    const filename = displayFilename || storedFilename;
    const mediaPart: MessagePart = { type, filename };
    if (storedFilename && storedFilename !== filename) {
      mediaPart.stored_filename = storedFilename;
    }
    botRecord.content.message.push(mediaPart);
    if (type !== "file") void resolveRecordMedia([botRecord], loadEpoch);
  }
}

function scrollToBottom(
  threadId = props.thread?.thread_id,
  epoch = loadEpoch,
) {
  nextTick(() => {
    if (
      epoch !== loadEpoch ||
      props.thread?.thread_id !== threadId ||
      !messagesEl.value
    ) {
      return;
    }
    messagesEl.value.scrollTop = messagesEl.value.scrollHeight;
  });
}
</script>

<style scoped>
.thread-panel {
  width: 380px;
  height: calc(100% - var(--chat-panel-top-offset, 0px));
  margin-top: var(--chat-panel-top-offset, 0px);
  border-left: 1px solid var(--chat-border, rgba(var(--v-theme-on-surface), 0.1));
  background: var(--chat-page-bg, rgb(var(--v-theme-surface)));
  color: rgb(var(--v-theme-on-surface));
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}

.slide-left-enter-active,
.slide-left-leave-active {
  transition: all 0.2s ease;
}

.slide-left-enter-from,
.slide-left-leave-to {
  transform: translateX(100%);
  opacity: 0;
}

.thread-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px 8px;
}

.thread-panel-title {
  font-size: 16px;
  font-weight: 600;
  line-height: 1.4;
  color: rgb(var(--v-theme-on-surface));
}

.thread-panel-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.thread-delete-button {
  color: rgb(var(--v-theme-on-surface));
}

.thread-delete-button:hover {
  background: transparent;
}

.thread-selected-text {
  margin: 4px 16px 12px;
  padding: 12px 14px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.1);
  background: rgba(var(--v-theme-on-surface), 0.035);
  border-radius: 18px;
  color: rgba(var(--v-theme-on-surface), 0.72);
  font-size: 13px;
  line-height: 1.6;
  max-height: 120px;
  overflow-y: auto;
}

.thread-messages {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 0 14px 12px;
}

.thread-load-error {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 8px 4px;
  color: rgb(var(--v-theme-error));
  font-size: 12px;
  text-align: center;
}

.thread-composer {
  display: flex;
  gap: 8px;
  align-items: flex-end;
  padding: 12px;
  border-top: 1px solid rgba(var(--v-border-color), 0.14);
}

.thread-input {
  flex: 1;
  box-sizing: border-box;
  height: 40px;
  min-height: 40px;
  max-height: 140px;
  padding: 9px 12px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.14);
  border-radius: 18px;
  outline: none;
  resize: none;
  background: transparent;
  color: inherit;
  font: inherit;
  line-height: 20px;
}

.thread-input:focus {
  border-color: rgba(var(--v-theme-on-surface), 0.36);
}

.thread-send-button {
  height: 40px;
  min-height: 40px;
  padding: 0 14px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.14);
  border-radius: 999px;
  color: rgb(var(--v-theme-on-surface));
}

@media (max-width: 760px) {
  .thread-panel {
    position: fixed;
    inset: 0;
    z-index: 1300;
    width: 100vw;
    height: 100dvh;
    margin-top: 0;
    border-left: 0;
  }

  .thread-panel-header {
    min-height: 52px;
    padding: calc(10px + env(safe-area-inset-top)) 12px 8px;
    border-bottom: 1px solid var(--chat-border, rgba(var(--v-border-color), 0.12));
  }

  .thread-selected-text {
    margin: 10px 12px;
    padding: 10px 12px;
    border-radius: 14px;
    max-height: 96px;
    font-size: 13px;
  }

  .thread-messages {
    padding: 0 12px 10px;
  }

  .thread-composer {
    gap: 8px;
    padding: 10px 12px calc(10px + env(safe-area-inset-bottom));
    background: var(--chat-page-bg, rgb(var(--v-theme-surface)));
  }

  .thread-input {
    min-width: 0;
    font-size: 16px;
  }

  .thread-send-button {
    min-width: 56px;
    flex-shrink: 0;
  }
}

</style>
