<script setup>
import axios from 'axios';
import { EventSourcePolyfill } from 'event-source-polyfill';
</script>

<template>
  <div class="trace-wrapper">
    <div class="trace-table" ref="scrollEl" :style="{ height: tableHeight }">
      <div class="trace-row trace-header">
        <div class="trace-cell time">Time</div>
        <div class="trace-cell span">Event ID</div>
        <div class="trace-cell umo">UMO</div>
        <!-- <div class="trace-cell count">Records</div> -->
        <!-- <div class="trace-cell last">Last</div> -->
        <div class="trace-cell sender">Sender</div>
        <div class="trace-cell outline">Outline</div>
        <div class="trace-cell fields"></div>
      </div>
      <div class="trace-group" :class="{ highlight: highlightMap[event.span_id] }" v-for="event in events"
        :key="event.span_id">
        <div class="trace-row trace-event">
          <div class="trace-cell time">{{ formatTime(event.first_time) }}</div>
          <div class="trace-cell span" :title="event.span_id">
            <div class="event-title">
              {{ shortSpan(event.span_id) }}
            </div>
          </div>
          <div class="trace-cell umo">{{ event.umo }}</div>
          <!-- <div class="trace-cell count">
            <div class="event-meta">{{ event.records.length }}</div>
          </div> -->
          <!-- <div class="trace-cell last">
            <div class="event-meta">{{ formatTime(event.last_time) }}</div>
          </div> -->
          <div class="trace-cell sender">
            <div class="event-sub" style="white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">{{
              event.sender_name || '-' }}</div>
          </div>
          <div class="trace-cell outline">
            <div class="event-sub outline">{{ event.message_outline || '-' }}</div>
          </div>
          <div class="trace-cell fields event-controls">
            <v-btn size="x-small" variant="text" color="primary" @click="toggleEvent(event.span_id)">
              {{ event.collapsed ? 'Expand' : 'Collapse' }}
              <span v-if="event.hasAgentPrepare" class="agent-dot" />
            </v-btn>
          </div>
        </div>
        <div class="trace-records" v-if="!event.collapsed">
          <div class="trace-record" v-for="record in getVisibleRecords(event)" :key="record.key">
            <div class="trace-record-time">{{ record.timeLabel }}</div>
            <div class="trace-record-action">{{ record.action }}</div>
            <pre class="trace-record-fields">{{ record.fieldsText }}</pre>
          </div>
          <div class="event-more" v-if="event.visibleCount < event.records.length">
            <v-btn size="x-small" variant="tonal" color="primary" @click="showMore(event.span_id)">
              Show more
            </v-btn>
          </div>
        </div>
      </div>
      <div v-if="events.length === 0" class="trace-empty">No trace data yet.</div>
    </div>
  </div>
</template>

<script>
export default {
  name: 'TraceDisplayer',
  props: {
    autoScroll: {
      type: Boolean,
      default: true
    },
    maxItems: {
      type: Number,
      default: 300
    }
  },
  data() {
    return {
      events: [],
      eventIndex: {},
      highlightMap: {},
      highlightTimers: {},
      eventSource: null,
      retryTimer: null,
      retryAttempts: 0,
      maxRetryAttempts: 10,
      baseRetryDelay: 1000,
      lastEventId: null,
      tableHeight: 'auto'
    };
  },
  async mounted() {
    await this.fetchTraceHistory();
    this.connectSSE();
    this.updateTableHeight();
    window.addEventListener('resize', this.updateTableHeight);
  },
  beforeUnmount() {
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }
    if (this.retryTimer) {
      clearTimeout(this.retryTimer);
      this.retryTimer = null;
    }
    this.retryAttempts = 0;
    window.removeEventListener('resize', this.updateTableHeight);
  },
  methods: {
    updateTableHeight() {
      this.$nextTick(() => {
        const el = this.$refs.scrollEl;
        if (!el || typeof window === 'undefined') return;
        const viewportHeight = window.innerHeight || document.documentElement.clientHeight;
        const offsetTop = el.getBoundingClientRect().top;
        const height = Math.max(viewportHeight - offsetTop, 0);
        this.tableHeight = `${height}px`;
      });
    },
    async fetchTraceHistory() {
      try {
        const res = await axios.get('/api/log-history');
        const logs = res.data?.data?.logs || [];
        const traces = logs.filter((item) => item.type === 'trace');
        this.processNewTraces(traces);
      } catch (err) {
        console.error('Failed to fetch trace history:', err);
      }
    },
    connectSSE() {
      if (this.eventSource) {
        this.eventSource.close();
        this.eventSource = null;
      }

      const token = localStorage.getItem('token');

      this.eventSource = new EventSourcePolyfill('/api/live-log', {
        headers: {
          Authorization: token ? `Bearer ${token}` : ''
        },
        heartbeatTimeout: 300000,
        withCredentials: true
      });

      this.eventSource.onopen = () => {
        this.retryAttempts = 0;
        if (!this.lastEventId) {
          this.fetchTraceHistory();
        }
      };

      this.eventSource.onmessage = (event) => {
        try {
          if (event.lastEventId) {
            this.lastEventId = event.lastEventId;
          }

          const payload = JSON.parse(event.data);
          if (payload?.type !== 'trace') {
            return;
          }
          this.processNewTraces([payload]);
        } catch (e) {
          console.error('Failed to parse trace payload:', e);
        }
      };

      this.eventSource.onerror = (err) => {
        if (this.eventSource) {
          this.eventSource.close();
          this.eventSource = null;
        }

        if (this.retryAttempts >= this.maxRetryAttempts) {
          console.error('Trace stream reached max retry attempts.');
          return;
        }

        const delay = Math.min(
          this.baseRetryDelay * Math.pow(2, this.retryAttempts),
          30000
        );

        if (this.retryTimer) {
          clearTimeout(this.retryTimer);
          this.retryTimer = null;
        }

        this.retryTimer = setTimeout(async () => {
          this.retryAttempts++;
          if (!this.lastEventId) {
            await this.fetchTraceHistory();
          }
          this.connectSSE();
        }, delay);
      };
    },
    processNewTraces(newTraces) {
      if (!newTraces || newTraces.length === 0) return;

      let hasUpdate = false;
      const touched = new Set();
      newTraces.forEach((trace) => {
        if (!trace.span_id) return;
        const recordKey = `${trace.time}-${trace.span_id}-${trace.action}`;
        let event = this.eventIndex[trace.span_id];
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
            hasAgentPrepare: trace.action === 'astr_agent_prepare'
          };
          this.eventIndex[trace.span_id] = event;
          this.events.push(event);
          hasUpdate = true;
        }

        const exists = event.records.some((item) => item.key === recordKey);
        if (exists) return;

        event.records.push({
          time: trace.time,
          action: trace.action,
          fieldsText: this.formatFields(trace.fields),
          timeLabel: this.formatTime(trace.time),
          key: recordKey
        });
        if (trace.action === 'astr_agent_prepare') {
          event.hasAgentPrepare = true;
        }
        if (!event.first_time || trace.time < event.first_time) {
          event.first_time = trace.time;
        }
        if (!event.last_time || trace.time > event.last_time) {
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
      });

      if (hasUpdate) {
        this.events.forEach((event) => {
          event.records.sort((a, b) => b.time - a.time);
        });
        this.events.sort((a, b) => b.first_time - a.first_time);
        if (this.events.length > this.maxItems) {
          const overflow = this.events.length - this.maxItems;
          const removed = this.events.splice(this.maxItems, overflow);
          removed.forEach((event) => {
            delete this.eventIndex[event.span_id];
          });
        }
        touched.forEach((spanId) => {
          this.pulseEvent(spanId);
        });
      }
    },
    scrollToBottom() {
      const el = this.$refs.scrollEl;
      if (!el) return;
      el.scrollTop = el.scrollHeight;
    },
    toggleEvent(spanId) {
      const event = this.eventIndex[spanId];
      if (!event) return;
      event.collapsed = !event.collapsed;
    },
    showMore(spanId) {
      const event = this.eventIndex[spanId];
      if (!event) return;
      event.visibleCount = Math.min(event.records.length, event.visibleCount + 20);
    },
    pulseEvent(spanId) {
      if (!spanId) return;
      if (this.highlightTimers[spanId]) {
        clearTimeout(this.highlightTimers[spanId]);
      }
      this.highlightMap = { ...this.highlightMap, [spanId]: true };
      const remove = setTimeout(() => {
        const next = { ...this.highlightMap };
        delete next[spanId];
        this.highlightMap = next;
        const timers = { ...this.highlightTimers };
        delete timers[spanId];
        this.highlightTimers = timers;
      }, 1200);
      this.highlightTimers = { ...this.highlightTimers, [spanId]: remove };
    },
    getVisibleRecords(event) {
      if (!event.records.length) return [];
      return event.records.slice(0, event.visibleCount);
    },
    formatTime(ts) {
      if (!ts) return '';
      const date = new Date(ts * 1000);
      const base = date.toLocaleString();
      const ms = String(date.getMilliseconds()).padStart(3, '0');
      return `${base}.${ms}`;
    },
    shortSpan(spanId) {
      if (!spanId) return '';
      return spanId.slice(0, 8);
    },
    formatFields(fields) {
      if (!fields) return '';
      try {
        const text = JSON.stringify(fields, null, 2);
        if (text.length > 2000) {
          return `${text}`;
        }
        return text;
      } catch (e) {
        return String(fields);
      }
    }
  }
};
</script>

<style scoped>
.trace-wrapper {
  height: 100%;
}

.trace-table {
  background: transparent;
  border-radius: 0;
  padding: 0;
  height: 100%;
  overflow-y: auto;
  color: #2b3340;
  font-family: 'Fira Code', monospace;
}

.trace-row {
  display: grid;
  grid-template-columns: 200px 100px 300px 90px 180px 140px 200px 1fr;
  gap: 12px;
}

.trace-group {
  border-bottom: 1px solid rgba(15, 23, 42, 0.08);
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
  color: #6b7280;
  border-bottom: 1px solid rgba(15, 23, 42, 0.12);
  padding-bottom: 10px;
}

.trace-cell {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 12px;
}

.event-title {
  font-weight: 600;
  color: #1f2937;
}

.event-meta {
  font-size: 12px;
  color: #6b7280;
  margin-top: 4px;
}

.event-sub {
  font-size: 12px;
  color: #4b5563;
  margin-top: 2px;
  word-break: break-word;
}

.event-sub.outline {
  color: #6b7280;
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

.trace-cell.fields pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  color: #4b5563;
}

.trace-empty {
  padding: 24px;
  text-align: center;
  color: #6b7280;
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
  color: #6b7280;
  font-size: 11px;
}

.trace-record-action {
  color: #1f2937;
  font-weight: 600;
  font-size: 11px;
}

.trace-record-fields {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  color: #4b5563;
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
