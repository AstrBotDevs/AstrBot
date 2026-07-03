<script setup>
import { logApi } from '@/api/v1';
import { EventSourcePolyfill } from 'event-source-polyfill';
import { useModuleI18n } from '@/i18n/composables';

const { tm } = useModuleI18n('features/trace');
</script>

<template>
  <div class="trace-wrapper">
    <div class="trace-table" ref="scrollEl" :style="{ height: tableHeight }">

      <!-- Main Agent Section -->
      <section class="trace-section main-section">
        <div class="section-header">
          <span class="section-title main">{{ tm('mainTitle') }}</span>
          <span class="section-count main">{{ mainEvents.length }}</span>
        </div>
        <div class="trace-row trace-header">
          <div class="trace-cell time">Time</div>
          <div class="trace-cell span">Event ID</div>
          <div class="trace-cell umo">UMO</div>
          <div class="trace-cell sender">Sender</div>
          <div class="trace-cell outline">Outline</div>
          <div class="trace-cell fields"></div>
        </div>
        <div v-for="event in mainEvents" :key="event.span_id"
             class="trace-group"
             :class="{ highlight: highlightMap[event.span_id] }"
             :data-span-id="event.span_id">
          <div class="trace-row main">
            <div class="trace-cell time cell-text">{{ formatTime(event.first_time) }}</div>
            <div class="trace-cell span" :title="event.span_id">
              <div class="event-title cell-text">{{ shortSpan(event.span_id) }}</div>
            </div>
            <div class="trace-cell umo cell-text">{{ event.umo }}</div>
            <div class="trace-cell sender">
              <div class="event-sub sender-text">{{ event.sender_name || '-' }}</div>
            </div>
            <div class="trace-cell outline">
              <div class="event-sub outline">{{ event.message_outline || '-' }}</div>
            </div>
            <div class="trace-cell fields event-controls">
              <v-btn size="x-small" variant="text" color="primary"
                     @click="toggleEvent(event.span_id)">
                {{ event.collapsed ? 'Expand' : 'Collapse' }}
                <span v-if="event.hasAgentPrepare" class="agent-dot" />
              </v-btn>
            </div>
          </div>
          <div v-if="!event.collapsed" class="trace-records">
            <div class="trace-record" v-for="record in getVisibleRecords(event)" :key="record.key"
                 :data-record-key="record.key">
              <div class="trace-record-time">{{ record.timeLabel }}</div>
              <div class="trace-record-action">{{ record.action }}</div>
              <pre class="trace-record-fields">{{ record.fieldsText }}</pre>
            </div>
            <div class="event-more" v-if="event.visibleCount < event.records.length">
              <v-btn size="x-small" variant="tonal" color="primary"
                     @click="showMore(event.span_id)">
                Show more
              </v-btn>
            </div>
          </div>
        </div>
        <div v-if="mainEvents.length === 0" class="trace-empty">
          {{ tm('mainEmpty') }}
        </div>
      </section>

      <hr v-if="subagentEvents.length > 0 && mainEvents.length > 0"
          class="section-divider" />

      <!-- SubAgent Section -->
      <section class="trace-section sub-section">
        <div class="section-header">
          <span class="section-title sub">{{ tm('subTitle') }}</span>
          <span class="section-count sub">{{ subagentEvents.length }}</span>
        </div>
        <div class="trace-row trace-header sub">
          <div class="trace-cell parent">Parent</div>
          <div class="trace-cell time">Time</div>
          <div class="trace-cell span">Event ID</div>
          <div class="trace-cell umo">UMO</div>
          <div class="trace-cell sender">Sender</div>
          <div class="trace-cell outline">Outline</div>
          <div class="trace-cell fields"></div>
        </div>
        <div v-for="event in subagentEvents" :key="event.span_id"
             class="trace-group sub"
             :class="{ highlight: highlightMap[event.span_id] }"
             :data-span-id="event.span_id">
          <div class="trace-row sub">
            <div class="trace-cell parent">
              <a v-if="event.parent_span_id" href="#"
                 class="parent-link"
                 :title="`Parent span: ${event.parent_span_id}`"
                 @click.prevent="jumpToCaller(event)">
                <span class="parent-arrow">↳</span>
                <span class="parent-id">{{ shortSpan(event.parent_span_id) }}</span>
              </a>
              <span v-else class="parent-none">—</span>
            </div>
            <div class="trace-cell time cell-text">{{ formatTime(event.first_time) }}</div>
            <div class="trace-cell span" :title="event.span_id">
              <div class="event-title cell-text">
                <span v-if="isBackgroundSubagent(event)" class="agent-badge bg">BG</span>
                {{ shortSpan(event.span_id) }}
              </div>
            </div>
            <div class="trace-cell umo cell-text">{{ event.umo }}</div>
            <div class="trace-cell sender">
              <div class="event-sub sender-text">{{ event.sender_name || '-' }}</div>
            </div>
            <div class="trace-cell outline">
              <div class="event-sub outline">{{ event.message_outline || '-' }}</div>
            </div>
            <div class="trace-cell fields event-controls">
              <v-btn size="x-small" variant="text" color="primary"
                     @click="toggleEvent(event.span_id)">
                {{ event.collapsed ? 'Expand' : 'Collapse' }}
                <span v-if="event.hasAgentPrepare" class="agent-dot" />
              </v-btn>
            </div>
          </div>
          <div v-if="!event.collapsed" class="trace-records">
            <div class="trace-record" v-for="record in getVisibleRecords(event)" :key="record.key"
                 :data-record-key="record.key">
              <div class="trace-record-time">{{ record.timeLabel }}</div>
              <div class="trace-record-action">{{ record.action }}</div>
              <pre class="trace-record-fields">{{ record.fieldsText }}</pre>
            </div>
            <div class="event-more" v-if="event.visibleCount < event.records.length">
              <v-btn size="x-small" variant="tonal" color="primary"
                     @click="showMore(event.span_id)">
                Show more
              </v-btn>
            </div>
          </div>
        </div>
        <div v-if="subagentEvents.length === 0" class="trace-empty">
          {{ tm('subEmpty') }}
        </div>
      </section>

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
  computed: {
    mainEvents() {
      return this.events.filter(this.isMainSpan);
    },
    subagentEvents() {
      return this.events.filter(this.isSubagentSpan);
    },
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
    isMainSpan(e) {
      return !e.parent_span_id && e.name === 'AstrMessageEvent';
    },
    isSubagentSpan(e) {
      return /^SubAgent[A-Za-z]*:/.test(e.name || '')
          || (!!e.parent_span_id && !this.isMainSpan(e));
    },
    isBackgroundSubagent(e) {
      return /^SubAgentBackground:/.test(e.name || '');
    },
    shortSpan(id) {
      if (!id) return '';
      return id.slice(0, 8);
    },
    jumpToCaller(subagentEvent) {
      const parentId = subagentEvent.parent_span_id;
      if (!parentId) return;
      const mainEvent = this.eventIndex[parentId];
      if (!mainEvent) {
        console.warn('[TraceDisplayer] Parent trace has been cleared:', parentId);
        alert(this.tm('parentMissing'));
        return;
      }
      mainEvent.collapsed = false;
      this.pulseEvent(parentId);
      this.$nextTick(() => {
        const el = this.$refs.scrollEl?.querySelector(
          `.main-section [data-span-id="${parentId}"]`
        );
        el?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      });
    },
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
        const res = await logApi.history();
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

      this.eventSource = new EventSourcePolyfill(logApi.liveUrl(), {
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
            parent_span_id: trace.parent_span_id || null,
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
    formatFields(fields) {
      if (!fields) return '';
      try {
        return JSON.stringify(fields, null, 2);
      } catch (e) {
        return String(fields);
      }
    }
  }
};
</script>

<style scoped>
.trace-wrapper { height: 100%; }

.trace-table {
  background: transparent;
  border-radius: 0;
  padding: 0;
  height: 100%;
  overflow-y: auto;
  color: #2b3340;
  font-family: 'Fira Code', monospace;
}

/* 段间分隔符 */
.section-divider {
  border: none;
  height: 1px;
  margin: 20px 0 4px;
  background: rgba(15, 23, 42, 0.12);
  border-radius: 1px;
}
:global(.is-dark) .section-divider {
  background: rgba(226, 232, 240, 0.18);
}

/* Section headers */
.section-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 14px 0 8px;
  border-bottom: 1px solid rgba(15, 23, 42, 0.08);
  margin: 16px 0 8px;
}
.section-title { font-weight: 600; font-size: 14px; }
.section-title.main { color: #2563eb; }
.section-title.sub  { color: #16a34a; }
.section-count {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  color: #fff;
  font-weight: 600;
}
.section-count.main { background: #2563eb; }
.section-count.sub  { background: #16a34a; }

/* Trace rows */
.trace-row {
  display: grid;
  grid-template-columns: 180px 100px minmax(320px, 1fr) 130px 240px 100px;
  gap: 12px;
}
.trace-row.sub {
  grid-template-columns: 105px 150px 110px minmax(240px, 1fr) 100px 264px 80px;
}
.trace-row.trace-header {
  font-weight: 600;
  color: #6b7280;
  border-bottom: 1px solid rgba(15, 23, 42, 0.12);
  padding-bottom: 10px;
}

/* Cells */
.trace-cell {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  min-width: 0;
}
.trace-cell.outline {
  white-space: normal;
  word-break: break-word;
}
.cell-text { font-size: 12px; }
.event-title { font-weight: 600; color: #1f2937; }
.event-sub { font-size: 12px; color: #4b5563; margin-top: 2px; word-break: break-word; }
.event-sub.outline { color: #6b7280; }
.event-sub.sender-text {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.event-controls { display: flex; justify-content: flex-end; }

/* SubAgent 专属 */
.trace-section.sub .trace-group.sub {
  border-left: 3px solid #16a34a;
  border-bottom: 1px solid rgba(15, 23, 42, 0.08);
  background: transparent;
  padding: 8px 0 8px 8px;
  transition: background 0.3s;
}
.trace-section.sub .trace-row.trace-header.sub {
  font-weight: 600;
  color: #6b7280;
}
.trace-section.sub .trace-group.highlight {
  background: rgba(22, 163, 74, 0.08);
}

.agent-dot {
  display: inline-block;
  width: 8px; height: 8px;
  border-radius: 50%;
  background: #22c55e;
  margin-left: 6px;
  vertical-align: middle;
}

.agent-badge {
  display: inline-block;
  color: #fff;
  font-size: 9px;
  font-weight: 700;
  padding: 1px 5px;
  border-radius: 3px;
  margin-right: 6px;
  vertical-align: middle;
  letter-spacing: 0.3px;
}
.agent-badge.bg { background: #f59e0b; }

.parent-link {
  color: #16a34a;
  text-decoration: underline;
  text-decoration-color: rgba(22, 163, 74, 0.4);
  font-family: 'Fira Code', monospace;
  font-size: 12px;
  cursor: pointer;
}
.parent-link:hover { text-decoration-color: #16a34a; }
.parent-arrow { color: #16a34a; margin-right: 2px; font-weight: bold; }
.parent-none  { color: #9ca3af; }

/* Expanded records */
.trace-records { padding: 4px 0 2px 0; }
.trace-record {
  display: grid;
  grid-template-columns: 200px 120px 1fr;
  gap: 8px;
  padding: 2px 0;
}
.trace-record-time { color: #6b7280; font-size: 11px; }
.trace-record-action { color: #1f2937; font-weight: 600; font-size: 11px; }
.trace-record-fields {
  margin: 0; white-space: pre-wrap; word-break: break-word;
  color: #4b5563; font-size: 10px;
}
.event-more { display: flex; justify-content: center; padding: 6px 0 2px; }

/* Group */
.trace-group {
  border-bottom: 1px solid rgba(15, 23, 42, 0.08);
  background: transparent;
  padding: 8px 0;
}
.trace-group.highlight {
  background: rgba(59, 130, 246, 0.08);
  transition: background 0.6s ease;
}

.trace-empty {
  padding: 24px;
  text-align: center;
  color: #6b7280;
}

@media (max-width: 1200px) {
  .trace-row {
    grid-template-columns: 130px 70px minmax(220px, 1fr) 90px 140px 70px;
  }
  .trace-row.sub {
    grid-template-columns: 95px 130px 90px minmax(160px, 1fr) 85px 200px 70px;
  }
  .trace-cell.fields {
    grid-column: 1 / -1;
  }
}
</style>
