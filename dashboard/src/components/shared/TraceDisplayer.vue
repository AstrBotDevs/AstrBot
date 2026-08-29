<script setup lang="ts">
import { logApi } from '@/api/v1';
import { useModuleI18n } from '@/i18n/composables';
import { EventSourcePolyfill } from 'event-source-polyfill';
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue';

interface TracePayload {
  type?: string;
  time?: number;
  span_id?: string;
  action?: string;
  name?: string;
  umo?: string;
  sender_name?: string;
  message_outline?: string;
  fields?: unknown;
  [key: string]: unknown;
}

interface TraceRecord {
  time: number;
  action: string;
  fieldsText: string;
  timeLabel: string;
  key: string;
}

interface TraceEventGroup {
  span_id: string;
  name?: string;
  umo?: string;
  sender_name?: string;
  message_outline?: string;
  first_time: number;
  last_time: number;
  collapsed: boolean;
  visibleCount: number;
  records: TraceRecord[];
  hasAgentPrepare: boolean;
}

const props = withDefaults(
  defineProps<{
    maxItems?: number;
  }>(),
  {
    maxItems: 300,
  },
);

const { tm } = useModuleI18n('features/trace');

const events = ref<TraceEventGroup[]>([]);
const eventIndex = ref<Record<string, TraceEventGroup>>({});
const highlightMap = ref<Record<string, boolean>>({});
const highlightTimers = ref<
  Record<string, ReturnType<typeof window.setTimeout>>
>({});
const eventSource = ref<EventSourcePolyfill | null>(null);
const retryTimer = ref<ReturnType<typeof window.setTimeout> | null>(null);
const retryAttempts = ref(0);
const lastEventId = ref<string | null>(null);
const tableHeight = ref('auto');
const scrollEl = ref<HTMLDivElement | null>(null);

const maxRetryAttempts = 10;
const baseRetryDelay = 1000;

function closeEventSource(): void {
  if (eventSource.value) {
    eventSource.value.close();
    eventSource.value = null;
  }
}

function clearRetryTimer(): void {
  if (retryTimer.value !== null) {
    clearTimeout(retryTimer.value);
    retryTimer.value = null;
  }
}

function clearHighlightTimers(): void {
  for (const timer of Object.values(highlightTimers.value)) {
    clearTimeout(timer);
  }
  highlightTimers.value = {};
}

async function updateTableHeight(): Promise<void> {
  await nextTick();
  const el = scrollEl.value;
  if (!el || typeof window === 'undefined') {
    return;
  }
  const viewportHeight =
    window.innerHeight || document.documentElement.clientHeight;
  const offsetTop = el.getBoundingClientRect().top;
  const height = Math.max(viewportHeight - offsetTop, 0);
  tableHeight.value = `${height}px`;
}

function scheduleTableHeightUpdate(): void {
  void updateTableHeight();
}

function formatTime(ts?: number): string {
  if (!ts) {
    return '';
  }
  const date = new Date(ts * 1000);
  const base = date.toLocaleString();
  const ms = String(date.getMilliseconds()).padStart(3, '0');
  return `${base}.${ms}`;
}

function shortSpan(spanId?: string): string {
  return spanId ? spanId.slice(0, 8) : '';
}

function formatFields(fields: unknown): string {
  if (!fields) {
    return '';
  }
  try {
    return JSON.stringify(fields, null, 2);
  } catch {
    return String(fields);
  }
}

function normalizeTracePayload(raw: unknown): TracePayload | null {
  if (!raw || typeof raw !== 'object') {
    return null;
  }
  return raw as TracePayload;
}

function pulseEvent(spanId: string): void {
  if (!spanId) {
    return;
  }
  const existingTimer = highlightTimers.value[spanId];
  if (existingTimer) {
    clearTimeout(existingTimer);
  }
  highlightMap.value = { ...highlightMap.value, [spanId]: true };
  const removeTimer = window.setTimeout(() => {
    const nextHighlights = { ...highlightMap.value };
    delete nextHighlights[spanId];
    highlightMap.value = nextHighlights;

    const nextTimers = { ...highlightTimers.value };
    delete nextTimers[spanId];
    highlightTimers.value = nextTimers;
  }, 1200);
  highlightTimers.value = {
    ...highlightTimers.value,
    [spanId]: removeTimer,
  };
}

function processNewTraces(newTraces: unknown[]): void {
  if (newTraces.length === 0) {
    return;
  }

  let hasUpdate = false;
  const touched = new Set<string>();

  for (const rawTrace of newTraces) {
    const trace = normalizeTracePayload(rawTrace);
    if (!trace?.span_id || !trace.action || !trace.time) {
      continue;
    }
    const recordKey = `${trace.time}-${trace.span_id}-${trace.action}`;
    let event = eventIndex.value[trace.span_id];
    if (!event) {
      event = {
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
        hasAgentPrepare: trace.action === 'astr_agent_prepare',
      };
      eventIndex.value[trace.span_id] = event;
      events.value.push(event);
      hasUpdate = true;
    }

    const exists = event.records.some((item) => item.key === recordKey);
    if (exists) {
      continue;
    }

    event.records.push({
      time: trace.time,
      action: trace.action,
      fieldsText: formatFields(trace.fields),
      timeLabel: formatTime(trace.time),
      key: recordKey,
    });
    if (trace.action === 'astr_agent_prepare') {
      event.hasAgentPrepare = true;
    }
    if (trace.time < event.first_time) {
      event.first_time = trace.time;
    }
    if (trace.time > event.last_time) {
      event.last_time = trace.time;
    }
    if (!event.sender_name && trace.sender_name) {
      event.sender_name = trace.sender_name;
    }
    if (!event.message_outline && trace.message_outline) {
      event.message_outline = trace.message_outline;
    }
    touched.add(trace.span_id);
    hasUpdate = true;
  }

  if (!hasUpdate) {
    return;
  }

  for (const event of events.value) {
    event.records.sort((a, b) => b.time - a.time);
  }
  events.value.sort((a, b) => b.first_time - a.first_time);

  if (events.value.length > props.maxItems) {
    const removed = events.value.splice(
      props.maxItems,
      events.value.length - props.maxItems,
    );
    for (const event of removed) {
      delete eventIndex.value[event.span_id];
    }
  }

  for (const spanId of touched) {
    pulseEvent(spanId);
  }
}

async function fetchTraceHistory(): Promise<void> {
  try {
    const res = await logApi.history();
    const logs = Array.isArray(res.data?.data?.logs) ? res.data.data.logs : [];
    const traces = logs.filter((item): item is TracePayload =>
      Boolean(
        item &&
        typeof item === 'object' &&
        (item as TracePayload).type === 'trace',
      ),
    );
    processNewTraces(traces);
  } catch (error) {
    console.error('Failed to fetch trace history:', error);
  }
}

function connectSSE(): void {
  closeEventSource();

  const token = localStorage.getItem('token');
  eventSource.value = new EventSourcePolyfill(logApi.liveUrl(), {
    headers: {
      Authorization: token ? `Bearer ${token}` : '',
    },
    heartbeatTimeout: 300000,
    withCredentials: true,
  });

  eventSource.value.onopen = () => {
    retryAttempts.value = 0;
    if (!lastEventId.value) {
      void fetchTraceHistory();
    }
  };

  eventSource.value.onmessage = (event: MessageEvent<string>) => {
    try {
      if (event.lastEventId) {
        lastEventId.value = event.lastEventId;
      }

      const payload = JSON.parse(event.data) as TracePayload;
      if (payload.type !== 'trace') {
        return;
      }
      processNewTraces([payload]);
    } catch (error) {
      console.error('Failed to parse trace payload:', error);
    }
  };

  eventSource.value.onerror = () => {
    closeEventSource();

    if (retryAttempts.value >= maxRetryAttempts) {
      console.error('Trace stream reached max retry attempts.');
      return;
    }

    const delay = Math.min(
      baseRetryDelay * Math.pow(2, retryAttempts.value),
      30000,
    );

    clearRetryTimer();
    retryTimer.value = window.setTimeout(async () => {
      retryAttempts.value += 1;
      if (!lastEventId.value) {
        await fetchTraceHistory();
      }
      connectSSE();
    }, delay);
  };
}

function toggleEvent(spanId: string): void {
  const event = eventIndex.value[spanId];
  if (!event) {
    return;
  }
  event.collapsed = !event.collapsed;
}

function showMore(spanId: string): void {
  const event = eventIndex.value[spanId];
  if (!event) {
    return;
  }
  event.visibleCount = Math.min(event.records.length, event.visibleCount + 20);
}

function getVisibleRecords(event: TraceEventGroup): TraceRecord[] {
  return event.records.slice(0, event.visibleCount);
}

onMounted(async () => {
  await fetchTraceHistory();
  connectSSE();
  await updateTableHeight();
  window.addEventListener('resize', scheduleTableHeightUpdate);
});

onBeforeUnmount(() => {
  closeEventSource();
  clearRetryTimer();
  clearHighlightTimers();
  retryAttempts.value = 0;
  window.removeEventListener('resize', scheduleTableHeightUpdate);
});
</script>

<template>
  <div class="trace-wrapper">
    <div ref="scrollEl" class="trace-table" :style="{ height: tableHeight }">
      <div class="trace-row trace-header">
        <div class="trace-cell time">{{ tm('table.time') }}</div>
        <div class="trace-cell span">{{ tm('table.eventId') }}</div>
        <div class="trace-cell umo">{{ tm('table.umo') }}</div>
        <div class="trace-cell sender">{{ tm('table.sender') }}</div>
        <div class="trace-cell outline">{{ tm('table.outline') }}</div>
        <div class="trace-cell fields"></div>
      </div>
      <div
        v-for="event in events"
        :key="event.span_id"
        class="trace-group"
        :class="{ highlight: highlightMap[event.span_id] }"
      >
        <div class="trace-row trace-event">
          <div class="trace-cell time">{{ formatTime(event.first_time) }}</div>
          <div class="trace-cell span" :title="event.span_id">
            <div class="event-title">
              {{ shortSpan(event.span_id) }}
            </div>
          </div>
          <div class="trace-cell umo">{{ event.umo }}</div>
          <div class="trace-cell sender">
            <div class="event-sub trace-sender">
              {{ event.sender_name || '-' }}
            </div>
          </div>
          <div class="trace-cell outline">
            <div class="event-sub outline">
              {{ event.message_outline || '-' }}
            </div>
          </div>
          <div class="trace-cell fields event-controls">
            <v-btn
              size="x-small"
              variant="text"
              color="primary"
              @click="toggleEvent(event.span_id)"
            >
              {{ event.collapsed ? tm('expand') : tm('collapse') }}
              <span v-if="event.hasAgentPrepare" class="agent-dot" />
            </v-btn>
          </div>
        </div>
        <div v-if="!event.collapsed" class="trace-records">
          <div
            v-for="record in getVisibleRecords(event)"
            :key="record.key"
            class="trace-record"
          >
            <div class="trace-record-time">{{ record.timeLabel }}</div>
            <div class="trace-record-action">{{ record.action }}</div>
            <pre class="trace-record-fields">{{ record.fieldsText }}</pre>
          </div>
          <div
            v-if="event.visibleCount < event.records.length"
            class="event-more"
          >
            <v-btn
              size="x-small"
              variant="tonal"
              color="primary"
              @click="showMore(event.span_id)"
            >
              {{ tm('showMore') }}
            </v-btn>
          </div>
        </div>
      </div>
      <div v-if="events.length === 0" class="trace-empty">
        {{ tm('empty') }}
      </div>
    </div>
  </div>
</template>

<style scoped>
.trace-sender {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.trace-wrapper {
  height: 100%;
}

.trace-table {
  background: transparent;
  border-radius: 0;
  padding: 0;
  height: 100%;
  overflow-y: auto;
  color: rgba(var(--v-theme-on-surface), 0.88);
  font-family: var(--astrbot-font-mono);
}

.trace-row {
  display: grid;
  grid-template-columns: 200px 100px 300px 90px 180px 140px 200px 1fr;
  gap: 12px;
}

.trace-group {
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  background: transparent;
  padding: 8px 0;
}

.trace-group.highlight {
  background: rgba(59, 130, 246, 0.08);
  transition: background 0.6s ease;
}

.trace-event {
  align-items: start;
}

.trace-header {
  font-weight: 600;
  color: rgba(var(--v-theme-on-surface), 0.62);
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  padding-bottom: 10px;
}

.trace-cell {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 12px;
}

.event-title {
  font-weight: 600;
  color: rgba(var(--v-theme-on-surface), 0.88);
}

.event-sub {
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.72);
  margin-top: 2px;
  word-break: break-word;
}

.event-sub.outline {
  color: rgba(var(--v-theme-on-surface), 0.62);
}

.event-controls {
  display: flex;
  justify-content: flex-end;
}

.agent-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #22c55e;
  margin-left: 6px;
  vertical-align: middle;
}

.trace-empty {
  padding: 24px;
  text-align: center;
  color: rgba(var(--v-theme-on-surface), 0.62);
}

@media (max-width: 1200px) {
  .trace-row {
    grid-template-columns: 140px 160px 300px 70px 140px 180px 1fr;
  }

  .trace-cell.fields {
    grid-column: 1 / -1;
  }
}

.trace-record {
  display: grid;
  grid-template-columns: 200px 120px 1fr;
  gap: 8px;
  padding: 2px 0;
}

.trace-record:last-child {
  border-bottom: none;
}

.trace-record-time {
  color: rgba(var(--v-theme-on-surface), 0.62);
  font-size: 11px;
}

.trace-record-action {
  color: rgba(var(--v-theme-on-surface), 0.88);
  font-weight: 600;
  font-size: 11px;
}

.trace-record-fields {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  color: rgba(var(--v-theme-on-surface), 0.72);
  font-size: 10px;
}

.event-more {
  display: flex;
  justify-content: center;
  padding: 6px 0 2px;
}

.trace-records {
  padding: 4px 0 2px 0;
}
</style>
