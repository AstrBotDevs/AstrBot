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
        <ChatMessageList
          :messages="messages"
          :is-dark="isDark"
          :is-streaming="sending"
          variant="thread"
        />
      </div>

      <form class="thread-composer" @submit.prevent="send">
        <textarea
          v-model="draft"
          class="thread-input"
          :placeholder="tm('thread.placeholder')"
          rows="1"
          :disabled="sending"
          @keydown.enter.exact.prevent="send"
        ></textarea>
        <v-btn
          class="thread-send-button"
          variant="text"
          :loading="sending"
          :disabled="!draft.trim()"
          type="submit"
        >
          {{ tm("input.send") }}
        </v-btn>
      </form>
    </aside>
  </transition>
</template>

<script setup lang="ts">
import { nextTick, ref, watch } from "vue";
import axios from "axios";
import type { ChatRecord, ChatThread, MessagePart } from "@/composables/useMessages";
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

watch(
  () => props.thread?.thread_id,
  (threadId) => {
    if (threadId) {
      loadThread(threadId);
    } else {
      messages.value = [];
    }
  },
  { immediate: true },
);

function close() {
  emit("update:modelValue", false);
}

async function loadThread(threadId: string) {
  try {
    const response = await axios.get("/api/chat/thread/get", {
      params: { thread_id: threadId },
    });
    const history = response.data?.data?.history || [];
    messages.value = history.map(normalizeRecord);
    scrollToBottom();
  } catch (error) {
    console.error("Failed to load thread:", error);
    messages.value = [];
  }
}

async function send() {
  if (!props.thread || sending.value || !draft.value.trim()) return;
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
      message: [{ type: "plain", text: "" }],
      reasoning: "",
      isLoading: true,
    },
  };
  messages.value.push(userRecord, botRecord);
  const threadUserRecord = messages.value[messages.value.length - 2];
  const threadBotRecord = messages.value[messages.value.length - 1];
  scrollToBottom();

  const abort = new AbortController();
  sending.value = true;
  try {
    const response = await fetch("/api/chat/thread/send", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${localStorage.getItem("token") || ""}`,
      },
      body: JSON.stringify({
        thread_id: props.thread.thread_id,
        message: [{ type: "plain", text }],
        enable_streaming: true,
      }),
      signal: abort.signal,
    });
    if (!response.ok || !response.body) {
      throw new Error(`Thread request failed: ${response.status}`);
    }
    await readSseStream(response.body, (payload) => {
      processPayload(threadBotRecord, threadUserRecord, payload);
      scrollToBottom();
    });
  } catch (error) {
    appendPlain(
      threadBotRecord,
      `\n\n${String((error as Error)?.message || error)}`,
    );
    console.error("Failed to send thread message:", error);
  } finally {
    sending.value = false;
  }
}

function normalizeRecord(record: any): ChatRecord {
  const content = record.content || {};
  return {
    ...record,
    content: {
      type: content.type || (record.sender_id === "bot" ? "bot" : "user"),
      message: normalizeParts(content.message || []),
      reasoning: content.reasoning || "",
      agentStats: content.agentStats || content.agent_stats,
      refs: content.refs,
    },
  };
}

function normalizeParts(parts: unknown): MessagePart[] {
  if (typeof parts === "string") {
    return parts ? [{ type: "plain", text: parts }] : [];
  }
  if (!Array.isArray(parts)) return [];
  return parts.map((part: any) => {
    if (!part || typeof part !== "object") {
      return { type: "plain", text: String(part ?? "") };
    }
    return part;
  });
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

function processPayload(botRecord: ChatRecord, userRecord: ChatRecord, payload: any) {
  const normalized =
    payload?.ct === "chat"
      ? { ...payload, type: payload.type || payload.t }
      : payload;
  const type = normalized?.type || normalized?.t;
  const chainType = normalized?.chain_type;
  const data = normalized?.data ?? "";

  if (type === "session_id" || type === "session_bound") return;

  if (type === "user_message_saved") {
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
    if (finalText && !hasPlainText(botRecord)) {
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
      botRecord.content.reasoning = `${botRecord.content.reasoning || ""}${payloadText(data)}`;
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

  if (["image", "record", "file", "video"].includes(type)) {
    markMessageStarted(botRecord);
    const filename = String(data)
      .replace("[IMAGE]", "")
      .replace("[RECORD]", "")
      .replace("[FILE]", "")
      .replace("[VIDEO]", "")
      .split("|", 1)[0];
    botRecord.content.message.push({ type, filename });
  }
}

function appendPlain(record: ChatRecord, text: string, append = true) {
  markMessageStarted(record);
  let last = record.content.message[record.content.message.length - 1];
  if (!last || last.type !== "plain") {
    last = { type: "plain", text: "" };
    record.content.message.push(last);
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

function scrollToBottom() {
  nextTick(() => {
    if (messagesEl.value) {
      messagesEl.value.scrollTop = messagesEl.value.scrollHeight;
    }
  });
}
</script>

<style scoped>
.thread-panel {
  width: 380px;
  height: 100%;
  border-left: 1px solid rgba(var(--v-theme-on-surface), 0.1);
  background: rgb(var(--v-theme-surface));
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
    border-left: 0;
  }

  .thread-panel-header {
    min-height: 52px;
    padding: calc(10px + env(safe-area-inset-top)) 12px 8px;
    border-bottom: 1px solid rgba(var(--v-border-color), 0.12);
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
    background: rgb(var(--v-theme-surface));
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
