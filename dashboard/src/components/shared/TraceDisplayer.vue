<script setup>
import { shallowRef, onMounted, onBeforeUnmount } from "vue";
import { EventSourcePolyfill } from "event-source-polyfill";
import axios, { resolveApiUrl } from "@/utils/request";

let isMounted = false;
const events = shallowRef([]);
const eventIndex = {};
const highlightMap = shallowRef({});
const highlightTimers = {};
let eventSource = null;
let retryTimer = null;
let retryAttempts = 0;
const maxRetryAttempts = 10;
const baseRetryDelay = 1000;
let lastEventId = null;

onMounted(async () => {
  isMounted = true;
  await fetchTraceHistory();
  connectSSE();
});

onBeforeUnmount(() => {
  isMounted = false;
  if (eventSource) {
    eventSource.close();
    eventSource = null;
  }
  if (retryTimer) {
    clearTimeout(retryTimer);
    retryTimer = null;
  }
  Object.values(highlightTimers).forEach((timer) => clearTimeout(timer));
  retryAttempts = 0;
});

async function fetchTraceHistory() {
  if (!isMounted) return;
  try {
    const res = await axios.get("/api/log-history");
    if (!isMounted) return;
    const logs = res.data?.data?.logs || [];
    const traces = logs.filter((item) => item.type === "trace");
    processNewTraces(traces);
  } catch (err) {
    console.error("Failed to fetch trace history:", err);
  }
}

function connectSSE() {
  if (eventSource) {
    eventSource.close();
    eventSource = null;
  }
  const token = localStorage.getItem("token");
  eventSource = new EventSourcePolyfill(resolveApiUrl("/api/live-log"), {
    headers: { Authorization: token ? `Bearer ${token}` : "" },
    heartbeatTimeout: 300000,
  });
  eventSource.onopen = () => {
    retryAttempts = 0;
    if (!lastEventId) fetchTraceHistory();
  };
  eventSource.onmessage = (event) => {
    if (!isMounted) return;
    try {
      if (event.lastEventId) lastEventId = event.lastEventId;
      const payload = JSON.parse(event.data);
      if (payload?.type !== "trace") return;
      processNewTraces([payload]);
    } catch (e) {
      console.error("Failed to parse trace payload:", e);
    }
  };
  eventSource.onerror = () => {
    if (eventSource) {
      eventSource.close();
      eventSource = null;
    }
    if (retryAttempts >= maxRetryAttempts) {
      console.error("Trace stream reached max retry attempts.");
      return;
    }
    const delay = Math.min(baseRetryDelay * Math.pow(2, retryAttempts), 30000);
    if (retryTimer) {
      clearTimeout(retryTimer);
      retryTimer = null;
    }
    retryTimer = setTimeout(async () => {
      retryAttempts++;
      if (!lastEventId) await fetchTraceHistory();
      connectSSE();
    }, delay);
  };
}

function processNewTraces(newTraces) {
  if (!isMounted || !newTraces || newTraces.length === 0) return;
  const touched = [];
  const currentEvents = [...events.value];
  newTraces.forEach((trace) => {
    if (!trace.span_id) return;
    const recordKey = `${trace.time}-${trace.span_id}-${trace.action}`;
    let evt = eventIndex[trace.span_id];
    if (!evt) {
      evt = {
        span_id: trace.span_id,
        name: trace.name,
        umo: trace.umo,
        sender_name: trace.sender_name,
        message_outline: trace.message_outline,
        first_time: trace.time,
        last_time: trace.time,
        collapsed: true,
        visibleCount: 20,
        records: [],
        hasAgentPrepare: trace.action === "astr_agent_prepare",
      };
      eventIndex[trace.span_id] = evt;
      currentEvents.push(evt);
    }
    const exists = evt.records.some((item) => item.key === recordKey);
    if (exists) return;
    evt.records.push({
      time: trace.time,
      action: trace.action,
      fieldsText: formatFields(trace.fields),
      timeLabel: formatTime(trace.time),
      key: recordKey,
    });
    if (trace.action === "astr_agent_prepare") evt.hasAgentPrepare = true;
    if (!evt.first_time || trace.time < evt.first_time)
      evt.first_time = trace.time;
    if (!evt.last_time || trace.time > evt.last_time)
      evt.last_time = trace.time;
    if (!evt.sender_name && trace.sender_name)
      evt.sender_name = trace.sender_name;
    if (!evt.message_outline && trace.message_outline)
      evt.message_outline = trace.message_outline;
    touched.push(trace.span_id);
  });
  if (touched.length > 0) {
    currentEvents.forEach((e) => {
      e.records.sort((a, b) => b.time - a.time);
    });
    currentEvents.sort((a, b) => b.first_time - a.first_time);
    if (currentEvents.length > 300) {
      const removed = currentEvents.splice(300);
      removed.forEach((e) => {
        delete eventIndex[e.span_id];
      });
    }
    events.value = currentEvents;
    touched.forEach((spanId) => {
      pulseEvent(spanId);
    });
  }
}

function pulseEvent(spanId) {
  if (!spanId || !isMounted) return;
  if (highlightTimers[spanId]) clearTimeout(highlightTimers[spanId]);
  highlightMap.value = { ...highlightMap.value, [spanId]: true };
  const remove = setTimeout(() => {
    if (!isMounted) return;
    const next = { ...highlightMap.value };
    delete next[spanId];
    highlightMap.value = next;
    delete highlightTimers[spanId];
  }, 1500);
  highlightTimers[spanId] = remove;
}

function toggleEvent(spanId) {
  const evt = eventIndex[spanId];
  if (evt) {
    evt.collapsed = !evt.collapsed;
    events.value = [...events.value];
  }
}

function showMore(spanId) {
  const evt = eventIndex[spanId];
  if (evt) {
    evt.visibleCount = Math.min(evt.records.length, evt.visibleCount + 20);
    events.value = [...events.value];
  }
}

function getVisibleRecords(evt) {
  if (!evt.records.length) return [];
  return evt.records.slice(0, evt.visibleCount);
}
function formatTime(ts) {
  if (!ts) return "";
  const date = new Date(ts * 1000);
  return `${date.toLocaleString()}.${String(date.getMilliseconds()).padStart(3, "0")}`;
}
function shortSpan(spanId) {
  return spanId ? spanId.slice(0, 8) : "";
}
function formatFields(fields) {
  if (!fields) return "";
  try {
    return JSON.stringify(fields, null, 2);
  } catch (_error) {
    return String(fields);
  }
}
</script>

<template>
  <div class="timeline-container">
    <div class="trace-timeline">
      <!-- Empty state -->
      <div v-if="events.length === 0" class="tl-empty">
        <div class="tl-empty-icon">⏳</div>
        <div
          class="tl-empty-text"
          style="
            color: var(--trace-title, #f4feff) !important;
            -webkit-text-fill-color: var(--trace-title, #f4feff) !important;
            opacity: 1 !important;
            visibility: visible !important;
          "
        >
          暂无追踪数据
        </div>
        <div
          class="tl-empty-hint"
          style="
            color: var(--trace-muted, rgba(203, 213, 225, 0.76)) !important;
            -webkit-text-fill-color: var(
              --trace-muted,
              rgba(203, 213, 225, 0.76)
            ) !important;
            opacity: 1 !important;
            visibility: visible !important;
          "
        >
          发送消息后即可看到调用链路
        </div>
      </div>

      <!-- Timeline items -->
      <div
        v-for="(event, idx) in events"
        :key="event.span_id"
        class="tl-item"
        :class="{
          'tl-item-active': highlightMap[event.span_id],
          'tl-item-expanded': !event.collapsed,
        }"
      >
        <!-- Timeline line + dot -->
        <div class="tl-track">
          <div
            class="tl-dot"
            :class="{ 'tl-dot-active': event.hasAgentPrepare }"
          ></div>
          <div v-if="idx < events.length - 1" class="tl-line"></div>
        </div>

        <!-- Event card -->
        <div class="tl-card">
          <!-- Card header -->
          <div class="tl-card-header" @click="toggleEvent(event.span_id)">
            <div class="tl-card-top">
              <span class="tl-event-id">{{ shortSpan(event.span_id) }}</span>
              <span class="tl-umo">{{ event.umo || "-" }}</span>
              <span class="tl-time">{{ formatTime(event.first_time) }}</span>
            </div>
            <div class="tl-card-bottom">
              <span class="tl-sender">{{
                event.sender_name || "Unknown"
              }}</span>
              <span class="tl-outline">{{ event.message_outline || "-" }}</span>
              <span class="tl-expand-btn">{{
                event.collapsed ? "展开" : "收起"
              }}</span>
            </div>
          </div>

          <!-- Expanded records -->
          <div
            v-if="!event.collapsed && event.records.length > 0"
            class="tl-records"
          >
            <div class="tl-records-header">
              调用链 · {{ event.records.length }} 条记录
            </div>
            <div
              v-for="record in getVisibleRecords(event)"
              :key="record.key"
              class="tl-record"
            >
              <div class="tl-record-left">
                <div class="tl-record-time">{{ record.timeLabel }}</div>
                <div class="tl-record-action">{{ record.action }}</div>
              </div>
              <pre class="tl-record-fields">{{ record.fieldsText }}</pre>
            </div>
            <div
              v-if="event.visibleCount < event.records.length"
              class="tl-records-more"
            >
              <button @click.stop="showMore(event.span_id)">
                加载更多 (+{{ event.records.length - event.visibleCount }})
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.timeline-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  color: var(--trace-text, rgba(226, 232, 240, 0.92));
  font-family: inherit;
  overflow: hidden;
}

.trace-timeline {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 20px;
  display: flex;
  flex-direction: column;
}

.tl-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  flex: 1;
  min-height: 320px;
  padding: 48px 24px;
  text-align: center;
  border: 1px solid var(--trace-border, rgba(83, 104, 120, 0.3));
  border-radius: 14px;
  background: var(--trace-empty-surface, rgba(7, 16, 24, 0.8));
}

.tl-empty-icon {
  display: grid;
  place-items: center;
  width: 56px;
  height: 56px;
  margin-bottom: 16px;
  font-size: 24px;
  border-radius: 999px;
  background: var(--trace-empty-icon-bg, rgba(0, 242, 255, 0.12));
  box-shadow: inset 0 0 0 1px
    var(--trace-border-strong, rgba(0, 242, 255, 0.18));
}

.tl-empty-text {
  font-size: 20px;
  font-weight: 700;
  line-height: 1.4;
  color: var(--trace-title, #f4feff) !important;
  -webkit-text-fill-color: var(--trace-title, #f4feff);
  margin-bottom: 8px;
}

.tl-empty-hint {
  max-width: 38ch;
  font-size: 14px;
  line-height: 1.6;
  color: var(--trace-muted, rgba(203, 213, 225, 0.76)) !important;
  -webkit-text-fill-color: var(--trace-muted, rgba(203, 213, 225, 0.76));
}

.tl-item {
  display: flex;
  gap: 0;
  margin-bottom: 0;
}

.tl-item:last-child .tl-line {
  display: none;
}

/* Track: dot + line */
.tl-track {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex-shrink: 0;
  width: 32px;
}

.tl-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: var(--trace-card-bg, rgba(10, 18, 25, 0.94));
  border: 2px solid var(--trace-border, rgba(83, 104, 120, 0.3));
  flex-shrink: 0;
  margin-top: 18px;
  z-index: 1;
  transition: all 0.3s ease;
}

.tl-dot-active {
  background: var(--trace-primary, #00f2ff);
  border-color: var(--trace-primary, #00f2ff);
  box-shadow: 0 0 8px rgba(0, 242, 255, 0.5);
}

.tl-item-active .tl-dot {
  background: var(--trace-primary, #00f2ff);
  border-color: var(--trace-primary, #00f2ff);
  box-shadow: 0 0 12px rgba(0, 242, 255, 0.8);
  transform: scale(1.3);
}

.tl-line {
  width: 2px;
  flex: 1;
  background: var(--trace-track, rgba(71, 85, 105, 0.42));
  margin-top: 4px;
  min-height: 20px;
}

.tl-item-active .tl-line {
  background: var(--trace-track-active, rgba(0, 242, 255, 0.3));
}

/* Card */
.tl-card {
  flex: 1;
  margin-left: 12px;
  margin-bottom: 16px;
  background: var(--trace-card-bg, rgba(10, 18, 25, 0.94));
  border: 1px solid var(--trace-border, rgba(83, 104, 120, 0.3));
  border-radius: 12px;
  overflow: hidden;
  transition:
    border-color 0.3s ease,
    box-shadow 0.3s ease,
    transform 0.3s ease;
}

.tl-item-active .tl-card {
  border-color: var(--trace-border-active, rgba(0, 242, 255, 0.38));
  box-shadow: var(--trace-shadow, 0 10px 24px rgba(15, 23, 42, 0.08));
}

.tl-item-expanded .tl-card {
  border-color: var(--trace-border-strong, rgba(0, 242, 255, 0.18));
}

.tl-card-header {
  padding: 14px 16px;
  cursor: pointer;
  transition: background 0.2s ease;
}

.tl-card-header:hover {
  background: var(--trace-primary-soft, rgba(0, 242, 255, 0.1));
}

.tl-card-top {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.tl-event-id {
  font-size: 12px;
  font-weight: 700;
  color: var(--trace-primary, #00f2ff);
  background: var(--trace-primary-soft, rgba(0, 242, 255, 0.1));
  padding: 3px 8px;
  border-radius: 999px;
  border: 1px solid var(--trace-border-strong, rgba(0, 242, 255, 0.18));
  font-family:
    "JetBrains Mono", "Fira Code", "PingFang SC", "Microsoft YaHei", monospace;
}

.tl-umo {
  font-size: 11px;
  color: var(--trace-muted, rgba(203, 213, 225, 0.76)) !important;
  -webkit-text-fill-color: var(--trace-muted, rgba(203, 213, 225, 0.76));
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tl-time {
  font-size: 10px;
  color: var(--trace-subtle, rgba(148, 163, 184, 0.76)) !important;
  -webkit-text-fill-color: var(--trace-subtle, rgba(148, 163, 184, 0.76));
  flex-shrink: 0;
  font-family:
    "JetBrains Mono", "Fira Code", "PingFang SC", "Microsoft YaHei", monospace;
}

.tl-card-bottom {
  display: flex;
  align-items: center;
  gap: 12px;
}

.tl-sender {
  font-size: 13px;
  font-weight: 600;
  color: var(--trace-text, rgba(226, 232, 240, 0.92)) !important;
  -webkit-text-fill-color: var(--trace-text, rgba(226, 232, 240, 0.92));
  max-width: 140px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tl-outline {
  flex: 1;
  font-size: 13px;
  color: var(--trace-muted, rgba(203, 213, 225, 0.76)) !important;
  -webkit-text-fill-color: var(--trace-muted, rgba(203, 213, 225, 0.76));
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tl-expand-btn {
  font-size: 11px;
  font-weight: 600;
  color: var(--trace-primary, #00f2ff);
  background: var(--trace-primary-soft, rgba(0, 242, 255, 0.1));
  border: 1px solid var(--trace-border-strong, rgba(0, 242, 255, 0.18));
  padding: 4px 10px;
  border-radius: 999px;
  flex-shrink: 0;
  font-family:
    "JetBrains Mono", "Fira Code", "PingFang SC", "Microsoft YaHei", monospace;
}

/* Records */
.tl-records {
  border-top: 1px solid var(--trace-border, rgba(83, 104, 120, 0.3));
  background: var(--trace-record-bg, rgba(3, 10, 16, 0.52));
  padding: 14px 16px;
}

.tl-records-header {
  font-size: 11px;
  color: var(--trace-subtle, rgba(148, 163, 184, 0.76)) !important;
  -webkit-text-fill-color: var(--trace-subtle, rgba(148, 163, 184, 0.76));
  letter-spacing: 0.04em;
  margin-bottom: 10px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--trace-border, rgba(83, 104, 120, 0.3));
  font-family:
    "JetBrains Mono", "Fira Code", "PingFang SC", "Microsoft YaHei", monospace;
}

.tl-record {
  display: flex;
  gap: 12px;
  margin-bottom: 10px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--trace-border, rgba(83, 104, 120, 0.3));
}

.tl-record:last-child {
  border-bottom: none;
  margin-bottom: 0;
  padding-bottom: 0;
}

.tl-record-left {
  flex-shrink: 0;
  width: 200px;
}

.tl-record-time {
  font-size: 10px;
  color: var(--trace-subtle, rgba(148, 163, 184, 0.76)) !important;
  -webkit-text-fill-color: var(--trace-subtle, rgba(148, 163, 184, 0.76));
  margin-bottom: 2px;
  font-family:
    "JetBrains Mono", "Fira Code", "PingFang SC", "Microsoft YaHei", monospace;
}

.tl-record-action {
  font-size: 11px;
  font-weight: 700;
  color: var(--trace-primary, #00f2ff);
  font-family:
    "JetBrains Mono", "Fira Code", "PingFang SC", "Microsoft YaHei", monospace;
}

.tl-record-fields {
  flex: 1;
  margin: 0;
  font-size: 11px;
  color: var(--trace-text, rgba(226, 232, 240, 0.92)) !important;
  -webkit-text-fill-color: var(--trace-text, rgba(226, 232, 240, 0.92));
  white-space: pre-wrap;
  word-break: break-word;
  font-family: inherit;
  background: transparent;
  border: none;
  padding: 0;
  line-height: 1.6;
}

.tl-records-more {
  text-align: center;
  padding-top: 10px;
}

.tl-records-more button {
  background: var(--trace-primary-soft, rgba(0, 242, 255, 0.1));
  border: 1px solid var(--trace-border-strong, rgba(0, 242, 255, 0.18));
  color: var(--trace-primary, #00f2ff);
  padding: 6px 14px;
  border-radius: 999px;
  cursor: pointer;
  font-size: 11px;
  font-family:
    "JetBrains Mono", "Fira Code", "PingFang SC", "Microsoft YaHei", monospace;
  transition: all 0.2s ease;
}

.tl-records-more button:hover {
  background: var(--trace-primary-soft, rgba(0, 242, 255, 0.1));
  border-color: var(--trace-border-active, rgba(0, 242, 255, 0.38));
}

.timeline-container :is(div, span, pre, button) {
  mix-blend-mode: normal;
}

@media (max-width: 700px) {
  .tl-umo {
    display: none;
  }

  .tl-card-top,
  .tl-card-bottom,
  .tl-record {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }

  .tl-record-left,
  .tl-sender {
    width: 100%;
    max-width: none;
  }

  .trace-timeline,
  .timeline-container {
    padding: 16px;
  }

  .tl-empty {
    min-height: 260px;
    padding: 40px 20px;
  }
}
</style>
