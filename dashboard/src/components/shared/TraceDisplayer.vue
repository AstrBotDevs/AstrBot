<script setup>
import { shallowRef, nextTick, onMounted, onBeforeUnmount } from 'vue';
import axios from 'axios';
import { EventSourcePolyfill } from 'event-source-polyfill';
import { resolveApiUrl } from '@/utils/request';

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
  window.addEventListener('resize', resizeTimeline);
  resizeTimeline();
});

onBeforeUnmount(() => {
  isMounted = false;
  if (eventSource) { eventSource.close(); eventSource = null; }
  if (retryTimer) { clearTimeout(retryTimer); retryTimer = null; }
  retryAttempts = 0;
  window.removeEventListener('resize', resizeTimeline);
});

function resizeTimeline() {
  nextTick(() => {
    const timeline = document.querySelector('.trace-timeline');
    if (timeline) {
      const header = document.querySelector('.timeline-header');
      if (header) timeline.style.height = `calc(100vh - ${header.getBoundingClientRect().bottom}px - 16px)`;
    }
  });
}

async function fetchTraceHistory() {
  if (!isMounted) return;
  try {
    const res = await axios.get('/api/log-history');
    if (!isMounted) return;
    const logs = res.data?.data?.logs || [];
    const traces = logs.filter((item) => item.type === 'trace');
    processNewTraces(traces);
  } catch (err) {
    console.error('Failed to fetch trace history:', err);
  }
}

function connectSSE() {
  if (eventSource) { eventSource.close(); eventSource = null; }
  const token = localStorage.getItem('token');
  eventSource = new EventSourcePolyfill(resolveApiUrl('/api/live-log'), {
    headers: { Authorization: token ? `Bearer ${token}` : '' },
    heartbeatTimeout: 300000
  });
  eventSource.onopen = () => { retryAttempts = 0; if (!lastEventId) fetchTraceHistory(); };
  eventSource.onmessage = (event) => {
    if (!isMounted) return;
    try {
      if (event.lastEventId) lastEventId = event.lastEventId;
      const payload = JSON.parse(event.data);
      if (payload?.type !== 'trace') return;
      processNewTraces([payload]);
    } catch (e) { console.error('Failed to parse trace payload:', e); }
  };
  eventSource.onerror = () => {
    if (eventSource) { eventSource.close(); eventSource = null; }
    if (retryAttempts >= maxRetryAttempts) { console.error('Trace stream reached max retry attempts.'); return; }
    const delay = Math.min(baseRetryDelay * Math.pow(2, retryAttempts), 30000);
    if (retryTimer) { clearTimeout(retryTimer); retryTimer = null; }
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
      evt = { span_id: trace.span_id, name: trace.name, umo: trace.umo, sender_name: trace.sender_name, message_outline: trace.message_outline, first_time: trace.time, last_time: trace.time, collapsed: true, visibleCount: 20, records: [], hasAgentPrepare: trace.action === 'astr_agent_prepare' };
      eventIndex[trace.span_id] = evt;
      currentEvents.push(evt);
    }
    const exists = evt.records.some((item) => item.key === recordKey);
    if (exists) return;
    evt.records.push({ time: trace.time, action: trace.action, fieldsText: formatFields(trace.fields), timeLabel: formatTime(trace.time), key: recordKey });
    if (trace.action === 'astr_agent_prepare') evt.hasAgentPrepare = true;
    if (!evt.first_time || trace.time < evt.first_time) evt.first_time = trace.time;
    if (!evt.last_time || trace.time > evt.last_time) evt.last_time = trace.time;
    if (!evt.sender_name && trace.sender_name) evt.sender_name = trace.sender_name;
    if (!evt.message_outline && trace.message_outline) evt.message_outline = trace.message_outline;
    touched.push(trace.span_id);
  });
  if (touched.length > 0) {
    currentEvents.forEach((e) => { e.records.sort((a, b) => b.time - a.time); });
    currentEvents.sort((a, b) => b.first_time - a.first_time);
    if (currentEvents.length > 300) {
      const removed = currentEvents.splice(300);
      removed.forEach((e) => { delete eventIndex[e.span_id]; });
    }
    events.value = currentEvents;
    touched.forEach((spanId) => { pulseEvent(spanId); });
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
  if (evt) { evt.collapsed = !evt.collapsed; events.value = [...events.value]; resizeTimeline(); }
}

function showMore(spanId) {
  const evt = eventIndex[spanId];
  if (evt) { evt.visibleCount = Math.min(evt.records.length, evt.visibleCount + 20); events.value = [...events.value]; }
}

function getVisibleRecords(evt) { if (!evt.records.length) return []; return evt.records.slice(0, evt.visibleCount); }
function formatTime(ts) { if (!ts) return ''; const date = new Date(ts * 1000); return `${date.toLocaleString()}.${String(date.getMilliseconds()).padStart(3, '0')}`; }
function shortSpan(spanId) { return spanId ? spanId.slice(0, 8) : ''; }
function formatFields(fields) { if (!fields) return ''; try { return JSON.stringify(fields, null, 2); } catch (e) { return String(fields); } }
</script>

<template>
  <div class="timeline-container">
    <!-- Timeline header -->
    <div class="timeline-header">
      <div class="tl-title">追踪</div>
      <div class="tl-subtitle">实时模型调用链</div>
    </div>

    <!-- Timeline body -->
    <div class="trace-timeline">
      <!-- Empty state -->
      <div v-if="events.length === 0" class="tl-empty">
        <div class="tl-empty-icon">⏳</div>
        <div class="tl-empty-text">暂无追踪数据</div>
        <div class="tl-empty-hint">发送消息后即可看到调用链路</div>
      </div>

      <!-- Timeline items -->
      <div
        v-for="(event, idx) in events"
        :key="event.span_id"
        class="tl-item"
        :class="{ 'tl-item-active': highlightMap[event.span_id], 'tl-item-expanded': !event.collapsed }"
      >
        <!-- Timeline line + dot -->
        <div class="tl-track">
          <div class="tl-dot" :class="{ 'tl-dot-active': event.hasAgentPrepare }"></div>
          <div v-if="idx < events.length - 1" class="tl-line"></div>
        </div>

        <!-- Event card -->
        <div class="tl-card">
          <!-- Card header -->
          <div class="tl-card-header" @click="toggleEvent(event.span_id)">
            <div class="tl-card-top">
              <span class="tl-event-id">{{ shortSpan(event.span_id) }}</span>
              <span class="tl-umo">{{ event.umo || '-' }}</span>
              <span class="tl-time">{{ formatTime(event.first_time) }}</span>
            </div>
            <div class="tl-card-bottom">
              <span class="tl-sender">{{ event.sender_name || 'Unknown' }}</span>
              <span class="tl-outline">{{ event.message_outline || '-' }}</span>
              <span class="tl-expand-btn">{{ event.collapsed ? '展开' : '收起' }}</span>
            </div>
          </div>

          <!-- Expanded records -->
          <div v-if="!event.collapsed && event.records.length > 0" class="tl-records">
            <div class="tl-records-header">调用链 · {{ event.records.length }} 条记录</div>
            <div v-for="record in getVisibleRecords(event)" :key="record.key" class="tl-record">
              <div class="tl-record-left">
                <div class="tl-record-time">{{ record.timeLabel }}</div>
                <div class="tl-record-action">{{ record.action }}</div>
              </div>
              <pre class="tl-record-fields">{{ record.fieldsText }}</pre>
            </div>
            <div v-if="event.visibleCount < event.records.length" class="tl-records-more">
              <button @click.stop="showMore(event.span_id)">加载更多 (+{{ event.records.length - event.visibleCount }})</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style>
.timeline-container {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: #050507;
  font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
  overflow: hidden;
}

.timeline-header {
  padding: 20px 32px 16px;
  background: #0d0d12;
  border-bottom: 1px solid rgba(0, 242, 255, 0.12);
  flex-shrink: 0;
}

.tl-title {
  font-size: 20px;
  font-weight: 700;
  color: #00F2FF;
  letter-spacing: 2px;
  text-transform: uppercase;
}

.tl-subtitle {
  font-size: 11px;
  color: #4b5563;
  margin-top: 4px;
  letter-spacing: 0.5px;
}

.trace-timeline {
  flex: 1;
  overflow-y: auto;
  padding: 24px 32px;
}

.tl-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 0;
  color: #4b5563;
}

.tl-empty-icon {
  font-size: 48px;
  margin-bottom: 16px;
  opacity: 0.5;
}

.tl-empty-text {
  font-size: 16px;
  color: #6b7280;
  margin-bottom: 8px;
}

.tl-empty-hint {
  font-size: 12px;
  color: #4b5563;
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
  background: #1e293b;
  border: 2px solid #334155;
  flex-shrink: 0;
  margin-top: 18px;
  z-index: 1;
  transition: all 0.3s ease;
}

.tl-dot-active {
  background: #00F2FF;
  border-color: #00F2FF;
  box-shadow: 0 0 8px rgba(0, 242, 255, 0.5);
}

.tl-item-active .tl-dot {
  background: #00F2FF;
  border-color: #00F2FF;
  box-shadow: 0 0 12px rgba(0, 242, 255, 0.8);
  transform: scale(1.3);
}

.tl-line {
  width: 2px;
  flex: 1;
  background: rgba(51, 65, 85, 0.5);
  margin-top: 4px;
  min-height: 20px;
}

.tl-item-active .tl-line {
  background: rgba(0, 242, 255, 0.3);
}

/* Card */
.tl-card {
  flex: 1;
  margin-left: 12px;
  margin-bottom: 16px;
  background: #0d0d12;
  border: 1px solid rgba(51, 65, 85, 0.4);
  border-radius: 8px;
  overflow: hidden;
  transition: border-color 0.3s ease;
}

.tl-item-active .tl-card {
  border-color: rgba(0, 242, 255, 0.4);
  box-shadow: 0 0 16px rgba(0, 242, 255, 0.1);
}

.tl-item-expanded .tl-card {
  border-color: rgba(0, 242, 255, 0.3);
}

.tl-card-header {
  padding: 12px 16px;
  cursor: pointer;
  transition: background 0.2s ease;
}

.tl-card-header:hover {
  background: rgba(0, 242, 255, 0.04);
}

.tl-card-top {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 6px;
}

.tl-event-id {
  font-size: 13px;
  font-weight: 700;
  color: #00F2FF;
  background: rgba(0, 242, 255, 0.1);
  padding: 2px 8px;
  border-radius: 4px;
  border: 1px solid rgba(0, 242, 255, 0.2);
}

.tl-umo {
  font-size: 11px;
  color: #6b7280;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tl-time {
  font-size: 10px;
  color: #4b5563;
  flex-shrink: 0;
}

.tl-card-bottom {
  display: flex;
  align-items: center;
  gap: 12px;
}

.tl-sender {
  font-size: 12px;
  color: #9ca3af;
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tl-outline {
  flex: 1;
  font-size: 12px;
  color: #6b7280;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tl-expand-btn {
  font-size: 10px;
  color: #00F2FF;
  background: rgba(0, 242, 255, 0.05);
  border: 1px solid rgba(0, 242, 255, 0.15);
  padding: 2px 8px;
  border-radius: 4px;
  flex-shrink: 0;
}

/* Records */
.tl-records {
  border-top: 1px solid rgba(51, 65, 85, 0.3);
  background: rgba(0, 0, 0, 0.3);
  padding: 12px 16px;
}

.tl-records-header {
  font-size: 10px;
  color: #4b5563;
  text-transform: uppercase;
  letter-spacing: 1px;
  margin-bottom: 10px;
  padding-bottom: 8px;
  border-bottom: 1px solid rgba(51, 65, 85, 0.2);
}

.tl-record {
  display: flex;
  gap: 12px;
  margin-bottom: 10px;
  padding-bottom: 10px;
  border-bottom: 1px solid rgba(51, 65, 85, 0.15);
}

.tl-record:last-child {
  border-bottom: none;
  margin-bottom: 0;
  padding-bottom: 0;
}

.tl-record-left {
  flex-shrink: 0;
  width: 180px;
}

.tl-record-time {
  font-size: 10px;
  color: #4b5563;
  margin-bottom: 2px;
}

.tl-record-action {
  font-size: 11px;
  font-weight: 700;
  color: #00F2FF;
}

.tl-record-fields {
  flex: 1;
  margin: 0;
  font-size: 10px;
  color: #9ca3af;
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
  background: rgba(0, 242, 255, 0.05);
  border: 1px solid rgba(0, 242, 255, 0.15);
  color: #00F2FF;
  padding: 4px 16px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 11px;
  font-family: inherit;
  transition: all 0.2s ease;
}

.tl-records-more button:hover {
  background: rgba(0, 242, 255, 0.12);
  border-color: rgba(0, 242, 255, 0.3);
}

@media (max-width: 700px) {
  .tl-umo { display: none; }
  .tl-record-left { width: 120px; }
  .trace-timeline { padding: 16px; }
  .timeline-header { padding: 16px; }
}
</style>
