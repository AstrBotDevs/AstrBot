<script setup>
import { ChevronDown, ChevronRight } from "@lucide/vue";
import { logApi } from "@/api/v1";
import { useModuleI18n } from "@/i18n/composables";
import { EventSourcePolyfill } from "event-source-polyfill";

const { tm } = useModuleI18n("features/trace");
</script>

<template>
  <div class="trace-wrapper">
    <div ref="scrollEl" class="trace-table">
      <div class="trace-row trace-header">
        <div class="trace-cell time">{{ tm("table.time") }}</div>
        <div class="trace-cell span">{{ tm("table.eventId") }}</div>
        <div class="trace-cell umo">UMO</div>
        <div class="trace-cell sender">{{ tm("table.sender") }}</div>
        <div class="trace-cell outline">{{ tm("table.outline") }}</div>
        <div class="trace-cell fields"></div>
      </div>
      <div
        class="trace-group"
        :class="{ highlight: highlightMap[event.span_id] }"
        v-for="event in events"
        :key="event.span_id"
      >
        <div class="trace-row trace-event">
          <div class="trace-cell time" :data-label="tm('table.time')">
            {{ formatTime(event.first_time) }}
          </div>
          <div
            class="trace-cell span"
            :data-label="tm('table.eventId')"
            :title="event.span_id"
          >
            <div class="event-title">
              {{ shortSpan(event.span_id) }}
            </div>
          </div>
          <div class="trace-cell umo" data-label="UMO">{{ event.umo }}</div>
          <div class="trace-cell sender" :data-label="tm('table.sender')">
            <div
              class="event-sub"
              style="
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
              "
            >
              {{ event.sender_name || "-" }}
            </div>
          </div>
          <div class="trace-cell outline" :data-label="tm('table.outline')">
            <div class="event-sub outline">
              {{ event.message_outline || "-" }}
            </div>
          </div>
          <div class="trace-cell fields event-controls">
            <v-btn
              class="event-toggle"
              size="x-small"
              variant="text"
              color="primary"
              :aria-label="event.collapsed ? tm('expand') : tm('collapse')"
              @click="toggleEvent(event.span_id)"
            >
              <component
                :is="event.collapsed ? ChevronRight : ChevronDown"
                :size="13"
                :stroke-width="2"
                aria-hidden="true"
              />
              <span>{{ event.collapsed ? tm("expand") : tm("collapse") }}</span>
              <span v-if="event.hasAgentPrepare" class="agent-dot" />
            </v-btn>
          </div>
        </div>
        <div class="trace-records" v-if="!event.collapsed">
          <div
            class="trace-record"
            v-for="record in getVisibleRecords(event)"
            :key="record.key"
          >
            <div class="trace-record-time">{{ record.timeLabel }}</div>
            <div class="trace-record-action">{{ record.action }}</div>
            <pre class="trace-record-fields">{{ record.fieldsText }}</pre>
          </div>
          <div
            class="event-more"
            v-if="event.visibleCount < event.records.length"
          >
            <v-btn
              size="x-small"
              variant="tonal"
              color="primary"
              @click="showMore(event.span_id)"
            >
              {{ tm("showMore") }}
            </v-btn>
          </div>
        </div>
      </div>
      <div v-if="events.length === 0" class="trace-empty">
        {{ tm("empty") }}
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: "TraceDisplayer",
  props: {
    autoScroll: {
      type: Boolean,
      default: true,
    },
    maxItems: {
      type: Number,
      default: 300,
    },
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
    };
  },
  async mounted() {
    await this.fetchTraceHistory();
    this.connectSSE();
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
  },
  methods: {
    async fetchTraceHistory() {
      try {
        const res = await logApi.history();
        const logs = res.data?.data?.logs || [];
        const traces = logs.filter((item) => item.type === "trace");
        this.processNewTraces(traces);
      } catch (err) {
        console.error("Failed to fetch trace history:", err);
      }
    },
    connectSSE() {
      if (this.eventSource) {
        this.eventSource.close();
        this.eventSource = null;
      }

      const token = localStorage.getItem("token");

      this.eventSource = new EventSourcePolyfill(logApi.liveUrl(), {
        headers: {
          Authorization: token ? `Bearer ${token}` : "",
        },
        heartbeatTimeout: 300000,
        withCredentials: true,
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
          if (payload?.type !== "trace") {
            return;
          }
          this.processNewTraces([payload]);
        } catch (e) {
          console.error("Failed to parse trace payload:", e);
        }
      };

      this.eventSource.onerror = (err) => {
        if (this.eventSource) {
          this.eventSource.close();
          this.eventSource = null;
        }

        if (this.retryAttempts >= this.maxRetryAttempts) {
          console.error("Trace stream reached max retry attempts.");
          return;
        }

        const delay = Math.min(
          this.baseRetryDelay * Math.pow(2, this.retryAttempts),
          30000,
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
            hasAgentPrepare: trace.action === "astr_agent_prepare",
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
          key: recordKey,
        });
        if (trace.action === "astr_agent_prepare") {
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
      event.visibleCount = Math.min(
        event.records.length,
        event.visibleCount + 20,
      );
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
      if (!ts) return "";
      const date = new Date(ts * 1000);
      const base = date.toLocaleString();
      const ms = String(date.getMilliseconds()).padStart(3, "0");
      return `${base}.${ms}`;
    },
    shortSpan(spanId) {
      if (!spanId) return "";
      return spanId.slice(0, 8);
    },
    formatFields(fields) {
      if (!fields) return "";
      try {
        const text = JSON.stringify(fields, null, 2);
        if (text.length > 2000) {
          return `${text}`;
        }
        return text;
      } catch (e) {
        return String(fields);
      }
    },
  },
};
</script>

<style scoped>
.trace-wrapper {
  height: 100%;
  min-height: 0;
}

.trace-table {
  color: rgba(var(--v-theme-on-surface), 0.88);
  font-family: SFMono-Regular, Menlo, Monaco, Consolas,
    var(--astrbot-font-cjk-mono), monospace;
  height: 100%;
  overflow: auto;
  padding: 0 4px 4px;
  scrollbar-gutter: stable;
}

.trace-row {
  display: grid;
  gap: 14px;
  grid-template-columns:
    minmax(156px, 1.1fr) 90px minmax(220px, 2fr)
    minmax(100px, 0.8fr) minmax(180px, 1.5fr) 86px;
  min-width: 940px;
}

.trace-group {
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  background: transparent;
  padding: 9px 8px;
  transition: background 0.16s ease;
}

.trace-group:hover {
  background: rgba(var(--v-theme-on-surface), 0.025);
}

.trace-group.highlight {
  background: rgba(59, 130, 246, 0.08);
  transition: background 0.6s ease;
}

.trace-event {
  align-items: center;
}

.trace-header {
  background: var(--trace-card, #f5f6f7);
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  color: rgba(var(--v-theme-on-surface), 0.58);
  font-weight: 650;
  padding: 8px;
  position: sticky;
  top: 0;
  z-index: 2;
}

.trace-cell {
  font-size: 12px;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}

.event-title {
  font-weight: 600;
  color: rgba(var(--v-theme-on-surface), 0.88);
}

.event-meta {
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.62);
  margin-top: 4px;
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

.event-toggle :deep(.v-btn__content) {
  gap: 4px;
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
  color: rgba(var(--v-theme-on-surface), 0.72);
}

.trace-empty {
  padding: 24px;
  text-align: center;
  color: rgba(var(--v-theme-on-surface), 0.62);
}

.trace-record {
  display: grid;
  background: rgba(var(--v-theme-on-surface), 0.025);
  border-radius: 8px;
  gap: 10px;
  grid-template-columns: 180px 150px minmax(0, 1fr);
  margin-top: 4px;
  padding: 8px 10px;
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
  font-size: 11px;
  line-height: 1.5;
}

.event-more {
  display: flex;
  justify-content: center;
  padding: 6px 0 2px;
}

.trace-records {
  padding: 6px 0 2px;
}

@media (max-width: 768px) {
  .trace-table {
    overflow-x: hidden;
    padding: 0 2px 2px;
  }

  .trace-row.trace-header {
    display: none;
  }

  .trace-group {
    border-bottom: 0;
    border-radius: 10px;
    padding: 10px;
  }

  .trace-group + .trace-group {
    margin-top: 6px;
  }

  .trace-event {
    align-items: start;
    display: grid;
    gap: 6px 10px;
    grid-template-areas:
      "outline controls"
      "sender controls"
      "umo umo"
      "time span";
    grid-template-columns: minmax(0, 1fr) auto;
    min-width: 0;
  }

  .trace-cell.time {
    grid-area: time;
  }

  .trace-cell.span {
    grid-area: span;
    text-align: right;
  }

  .trace-cell.umo {
    grid-area: umo;
  }

  .trace-cell.sender {
    grid-area: sender;
  }

  .trace-cell.outline {
    grid-area: outline;
  }

  .trace-cell.fields {
    grid-area: controls;
  }

  .trace-cell.time,
  .trace-cell.span {
    color: rgba(var(--v-theme-on-surface), 0.52);
    font-size: 10px;
  }

  .trace-cell.umo {
    background: rgba(var(--v-theme-on-surface), 0.035);
    border-radius: 6px;
    color: rgba(var(--v-theme-on-surface), 0.62);
    font-size: 10px;
    overflow-wrap: anywhere;
    padding: 5px 7px;
    text-overflow: clip;
    white-space: normal;
  }

  .trace-cell.umo::before {
    content: attr(data-label) " · ";
    font-weight: 650;
  }

  .trace-cell.outline .event-sub {
    color: rgba(var(--v-theme-on-surface), 0.88);
    font-size: 13px;
    font-weight: 600;
    margin: 0;
  }

  .trace-cell.sender .event-sub {
    font-size: 11px;
    margin: 0;
  }

  .event-toggle {
    min-width: 30px;
    padding-inline: 6px;
  }

  .event-toggle span:not(.agent-dot) {
    display: none;
  }

  .trace-record {
    gap: 5px;
    grid-template-columns: 1fr;
    padding: 8px;
  }

  .trace-record-time,
  .trace-record-action {
    font-size: 10px;
  }
}
</style>
