<script setup>
defineOptions({ name: 'TraceDisplayer' });

import { ref, onMounted, onBeforeUnmount, nextTick } from 'vue';
import axios from 'axios';
import { EventSourcePolyfill } from 'event-source-polyfill';

const props = defineProps({
  selectedTraceId: {
    type: String,
    default: null
  }
});

const emit = defineEmits(['select-trace']);

// ── state ──────────────────────────────────────────────────────────────────
const traces = ref([]);
const pagination = ref({ page: 1, page_size: 20, total: 0 });
const loading = ref(false);
const searchText = ref('');
const umoFilter = ref('');
const highlightMap = ref({});
const traceCount = ref(0);
const traceDiskUsage = ref('0 B');
const dbDiskUsage = ref('0 B');

let highlightTimers = {};
let eventSource = null;
let retryTimer = null;
let retryAttempts = 0;
const MAX_RETRY = 10;

// ── fetch ───────────────────────────────────────────────────────────────────
async function fetchTraces(page = 1) {
  loading.value = true;
  try {
    const params = { page, page_size: pagination.value.page_size };
    if (searchText.value) params.search = searchText.value;
    if (umoFilter.value) params.umo = umoFilter.value;
    const res = await axios.get('/api/trace/list', { params });
    if (res.data?.status === 'ok') {
      traces.value = res.data.data.traces;
      pagination.value = { ...pagination.value, ...res.data.data.pagination };
      traceCount.value = res.data.data.pagination.total;
      traceDiskUsage.value = res.data.data.trace_disk_usage;
      dbDiskUsage.value = res.data.data.db_disk_usage;
    }
  } catch (err) {
    console.error('Failed to fetch traces:', err);
  } finally {
    loading.value = false;
  }
}

function onSearch() {
  pagination.value.page = 1;
  fetchTraces(1);
}

function onPageChange(page) {
  fetchTraces(page);
}

// ── SSE (real-time new traces) ─────────────────────────────────────────────
function connectSSE() {
  if (eventSource) {
    eventSource.close();
    eventSource = null;
  }
  const token = localStorage.getItem('token');
  eventSource = new EventSourcePolyfill('/api/live-log', {
    headers: { Authorization: token ? `Bearer ${token}` : '' },
    heartbeatTimeout: 300000,
    withCredentials: true
  });

  eventSource.onopen = () => { retryAttempts = 0; };

  eventSource.onmessage = (e) => {
    try {
      const payload = JSON.parse(e.data);
      if (payload?.type !== 'trace_complete') return;
      // new trace completed – prepend if on first page
      if (pagination.value.page === 1) {
        prependTrace(payload);
      }
    } catch {}
  };

  eventSource.onerror = () => {
    if (eventSource) { eventSource.close(); eventSource = null; }
    if (retryAttempts >= MAX_RETRY) return;
    const delay = Math.min(1000 * Math.pow(2, retryAttempts), 30000);
    retryTimer = setTimeout(() => { retryAttempts++; connectSSE(); }, delay);
  };
}

function prependTrace(payload) {
  // Avoid duplicates
  if (traces.value.some(t => t.trace_id === payload.trace_id)) return;
  traces.value.unshift({
    trace_id: payload.trace_id,
    umo: payload.umo,
    sender_name: payload.sender_name,
    message_outline: payload.message_outline,
    started_at: payload.started_at,
    finished_at: payload.finished_at,
    duration_ms: payload.duration_ms,
    status: payload.status,
    total_input_tokens: payload.total_input_tokens ?? 0,
    total_output_tokens: payload.total_output_tokens ?? 0
  });
  pagination.value.total += 1;
  traceCount.value += 1; // Update traceCount as well
  // trim to page_size
  if (traces.value.length > pagination.value.page_size) {
    traces.value.pop();
  }
  pulseTrace(payload.trace_id);
}

function pulseTrace(traceId) {
  if (highlightTimers[traceId]) clearTimeout(highlightTimers[traceId]);
  highlightMap.value = { ...highlightMap.value, [traceId]: true };
  highlightTimers[traceId] = setTimeout(() => {
    const next = { ...highlightMap.value };
    delete next[traceId];
    highlightMap.value = next;
    delete highlightTimers[traceId];
  }, 1500);
}

// ── utils ───────────────────────────────────────────────────────────────────
function formatTime(ts) {
  if (!ts) return '-';
  return new Date(ts * 1000).toLocaleString();
}

function formatDuration(ms) {
  if (ms == null) return '-';
  if (ms < 1000) return `${ms.toFixed(0)}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

function statusColor(status) {
  if (status === 'ok') return 'success';
  if (status === 'error') return 'error';
  if (status === 'filtered') return 'warning';
  return 'default';
}

// ── lifecycle ────────────────────────────────────────────────────────────────
onMounted(async () => {
  await fetchTraces();
  connectSSE();
});

onBeforeUnmount(() => {
  if (eventSource) { eventSource.close(); eventSource = null; }
  if (retryTimer) { clearTimeout(retryTimer); retryTimer = null; }
  Object.values(highlightTimers).forEach(clearTimeout);
  highlightTimers = {};
});
</script>

<template>
  <div class="trace-displayer">
    <!-- toolbar -->
    <div class="trace-toolbar">
      <v-text-field
        v-model="searchText"
        density="compact"
        variant="outlined"
        rounded="lg"
        hide-details
        placeholder="Search message..."
        prepend-inner-icon="mdi-magnify"
        clearable
        style="max-width: 260px;"
        @keyup.enter="onSearch"
        @click:clear="onSearch"
      />
      <v-text-field
        v-model="umoFilter"
        density="compact"
        variant="outlined"
        rounded="lg"
        hide-details
        placeholder="Filter UMO..."
        clearable
        style="max-width: 200px;"
        @keyup.enter="onSearch"
        @click:clear="onSearch"
      />
      <v-btn
        density="compact"
        variant="tonal"
        color="primary"
        icon="mdi-magnify"
        rounded="lg"
        @click="onSearch"
      />
      <v-spacer />
      <div class="trace-toolbar-left">
        <span class="trace-count">Count: {{ traceCount }}</span>
        <div v-if="traceDiskUsage" class="trace-disk-tag ml-3" title="Trace Log Size">
          <v-icon size="12" class="mr-1">mdi-harddisk</v-icon>
          <span>{{ traceDiskUsage }}</span>
        </div>
      </div>
    </div>

    <!-- table -->
    <div class="trace-table-wrap">
      <v-progress-linear v-if="loading" indeterminate color="primary" class="mb-1" />

      <div v-if="traces.length === 0 && !loading" class="trace-empty">
        <v-icon size="40" color="grey-lighten-1" class="mb-2">mdi-chart-timeline-variant</v-icon>
        <div>No traces yet. Enable tracing and send a message.</div>
      </div>

      <div
        v-for="trace in traces"
        :key="trace.trace_id"
        class="trace-row"
        :class="{
          highlight: highlightMap[trace.trace_id],
          selected: trace.trace_id === selectedTraceId
        }"
        @click="$emit('select-trace', trace.trace_id)"
      >
        <!-- status indicator -->
        <div class="trace-status-bar" :class="`status-${trace.status}`" />

        <div class="trace-row-content">
          <div class="trace-row-top">
            <v-chip size="x-small" :color="statusColor(trace.status)" variant="flat" rounded="pill" class="mr-2">
              {{ trace.status }}
            </v-chip>
            <span class="trace-sender">{{ trace.sender_name || '-' }}</span>
            <span class="trace-outline">{{ trace.message_outline || '-' }}</span>
            <v-spacer />
            <span class="trace-duration">{{ formatDuration(trace.duration_ms) }}</span>
          </div>
          <div class="trace-row-bottom">
            <span class="trace-time">{{ formatTime(trace.started_at) }}</span>
            <span class="trace-umo ml-2">{{ trace.umo || '' }}</span>
            <v-spacer />
            <div v-if="trace.total_input_tokens" class="trace-tokens-tag">
              <v-icon size="10" color="grey" class="mr-1">mdi-arrow-up-bold-outline</v-icon>
              <span>{{ trace.total_input_tokens }}</span>
              <v-icon size="10" color="grey" class="ml-2 mr-1">mdi-arrow-down-bold-outline</v-icon>
              <span>{{ trace.total_output_tokens }}</span>
            </div>
          </div>
        </div>

        <v-icon size="16" color="grey" class="trace-row-arrow">mdi-chevron-right</v-icon>
      </div>
    </div>

    <!-- pagination -->
    <div class="trace-pagination" v-show="pagination.total > pagination.page_size">
      <v-pagination
        v-model="pagination.page"
        :length="Math.max(1, Math.ceil(pagination.total / pagination.page_size))"
        density="compact"
        rounded
        @update:model-value="onPageChange"
      />
    </div>
  </div>
</template>

<style scoped>
.trace-displayer {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.trace-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  flex-shrink: 0;
  flex-wrap: wrap;
}

.trace-toolbar-left {
  display: flex;
  align-items: center;
}

.trace-count {
  font-size: 14px;
  color: rgba(var(--v-theme-on-surface), 0.6);
  font-weight: 500;
  white-space: nowrap;
}

.trace-disk-tag {
  display: inline-flex;
  align-items: center;
  font-size: 12px;
  color: rgba(var(--v-theme-primary), 0.8);
  background: rgba(var(--v-theme-primary), 0.1);
  padding: 1px 10px;
  border-radius: 20px;
  border: 1px solid rgba(var(--v-theme-primary), 0.2);
}

.trace-table-wrap {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
}

.trace-row {
  display: flex;
  align-items: stretch;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.05);
  cursor: pointer;
  transition: background 0.12s;
  position: relative;
}

.trace-row:hover {
  background: rgba(var(--v-theme-primary), 0.04);
}

.trace-row.selected {
  background: rgba(var(--v-theme-primary), 0.08);
  border-left: 2px solid rgba(var(--v-theme-primary), 0.6);
}

.trace-row.highlight {
  animation: pulse-bg 1.5s ease;
}

@keyframes pulse-bg {
  0% { background: rgba(var(--v-theme-primary), 0.18); }
  100% { background: transparent; }
}

.trace-status-bar {
  width: 4px;
  flex-shrink: 0;
  border-radius: 2px 0 0 2px;
}

.status-ok { background: rgb(var(--v-theme-success)); }
.status-error { background: rgb(var(--v-theme-error)); }
.status-filtered { background: rgb(var(--v-theme-warning)); }

.trace-row-content {
  flex: 1;
  padding: 10px 14px;
  min-width: 0;
}

.trace-row-top {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 2px;
}

.trace-sender {
  font-size: 14px;
  font-weight: 500;
  white-space: nowrap;
}

.trace-outline {
  font-size: 13px;
  color: rgba(var(--v-theme-on-surface), 0.6);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
  flex: 1;
}

.trace-duration {
  font-size: 13px;
  color: rgba(var(--v-theme-on-surface), 0.5);
  white-space: nowrap;
  flex-shrink: 0;
}

.trace-row-bottom {
  display: flex;
  align-items: center;
}

.trace-time {
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.45);
  white-space: nowrap;
}

.trace-umo {
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.35);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 200px;
}

.trace-tokens-tag {
  display: inline-flex;
  align-items: center;
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), 0.55);
  background: rgba(var(--v-theme-on-surface), 0.05);
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  padding: 1px 8px;
  border-radius: 6px;
  white-space: nowrap;
}

.trace-row-arrow {
  flex-shrink: 0;
  align-self: center;
  margin-right: 8px;
}

.trace-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 200px;
  color: rgba(var(--v-theme-on-surface), 0.4);
  font-size: 14px;
  text-align: center;
  gap: 4px;
}

.trace-pagination {
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 8px;
  border-top: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  flex-shrink: 0;
  min-height: 56px;
  overflow: hidden;
}
</style>
