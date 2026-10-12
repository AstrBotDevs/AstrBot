<script setup>
import {
  Activity,
  Bot,
  Check,
  ChevronDown,
  Clock3,
  PlugZap,
  RefreshCw,
  Search,
  Send,
  Workflow,
  X,
} from "@lucide/vue";
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { EventSourcePolyfill } from "event-source-polyfill";
import { logApi, pluginApi, sessionApi } from "@/api/v1";
import { useModuleI18n } from "@/i18n/composables";
import { getPlatformIcon } from "@/utils/platformUtils";
import defaultPluginIcon from "/favicon.svg";

const { tm } = useModuleI18n("features/trace");
const { tm: configTm } = useModuleI18n("features/config");
const maxItems = 300;
const events = ref([]);
const selectedSpanId = ref(null);
const searchText = ref("");
const filtersOpen = ref(false);
const selectedFilters = ref([]);
const loading = ref(true);
const clockNow = ref(Date.now() / 1000);
const durationTimer = ref(null);
const connected = ref(false);
const eventSource = ref(null);
const retryTimer = ref(null);
const retryAttempts = ref(0);
const lastEventId = ref(null);
const maxRetryAttempts = 10;
const baseRetryDelay = 1000;
const eventIndex = new Map();
const umoNames = ref({});
const plugins = ref({});
const failedPluginLogos = reactive(new Set());
const failedPlatformLogos = reactive(new Set());
const handlerDetails = reactive({});
const expandedGroups = reactive(new Set());

const actionLabels = {
  sel_persona: "selectPersona",
  event_received: "eventReceived",
  pipeline_start: "pipelineStart",
  pipeline_end: "pipelineEnd",
  stage_start: "stageStart",
  stage_end: "stageEnd",
  handler_start: "handlerStart",
  handler_end: "handlerEnd",
  agent_start: "agentStart",
  agent_end: "agentEnd",
  astr_agent_prepare: "agentPrepare",
  astr_agent_complete: "agentComplete",
  agent_tool_call: "agentToolCall",
  agent_tool_result: "agentToolResult",
  response_ready: "responseReady",
  response_sent: "responseSent",
};

const actionIcons = {
  event_received: Activity,
  pipeline_start: Workflow,
  pipeline_end: Check,
  stage_start: Workflow,
  stage_end: Check,
  agent_start: Bot,
  agent_end: Check,
  astr_agent_prepare: Bot,
  astr_agent_complete: Check,
  agent_tool_call: Workflow,
  agent_tool_result: Check,
  response_ready: Send,
  response_sent: Send,
};

const selectedEvent = computed(() => {
  if (!selectedSpanId.value) return null;
  return eventIndex.get(selectedSpanId.value) || null;
});

const normalizedSearch = computed(() => searchText.value.trim().toLowerCase());

const filteredEvents = computed(() => {
  return events.value.filter((event) => {
    if (!selectedFilters.value.every((filter) => matchesFilter(event, filter))) {
      return false;
    }
    if (!normalizedSearch.value) return true;
    const searchable = [
      event.message_outline,
      event.umo,
      umoNames.value[event.umo],
      event.sender_name,
      ...event.records.map((record) => recordSearchText(record)),
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    return searchable.includes(normalizedSearch.value);
  });
});

const filters = computed(() => [
  { key: "errors", label: tm("filters.errors") },
  { key: "models", label: tm("filters.models") },
  { key: "plugins", label: tm("filters.plugins") },
]);

watch(filteredEvents, (visibleEvents) => {
  if (selectedSpanId.value && !visibleEvents.some((event) => event.span_id === selectedSpanId.value)) {
    selectedSpanId.value = null;
  }
});

const traceRows = computed(() => filteredEvents.value.map((event) => ({
  event,
  duration: formatDuration(Math.max(0, ((event.completed ? event.last_time : Math.max(clockNow.value, event.last_time)) - event.first_time) * 1000)),
  spans: timelineRecords(event).length,
})));

const selectedStats = computed(() => {
  const event = selectedEvent.value;
  if (!event) return { duration: "-", handlers: 0, responses: 0 };
  const duration = Math.max(0, ((event.completed ? event.last_time : Math.max(clockNow.value, event.last_time)) - event.first_time) * 1000);
  return {
    duration: formatDuration(duration),
    handlers: event.records.filter(
      (record) => record.kind === "plugin_handler" && record.action === "handler_start",
    ).length,
    responses: timelineRecords(event).filter((record) => record.kind === "response").length,
  };
});

const selectedRecords = computed(() => selectedEvent.value ? timelineRecords(selectedEvent.value) : []);

const timelineGroups = computed(() => {
  const groups = [];
  for (const record of selectedRecords.value) {
    const type = `${record.action}:${recordLabel(record)}`;
    const previous = groups[groups.length - 1];
    // Only adjacent records are grouped, preserving the execution order.
    if (previous?.type === type) {
      previous.records.push(record);
    } else {
      groups.push({ key: record.key, type, records: [record] });
    }
  }
  return groups;
});

const timelineRows = computed(() => timelineGroups.value.flatMap((group) => {
  if (group.records.length === 1) return [{ key: group.key, record: group.records[0] }];
  const expanded = expandedGroups.has(group.key);
  const errors = group.records.filter((record) => record.fields.status === "error").length;
  const plugins = [...new Set(group.records.map((record) =>
    record.fields.plugin_display_name || record.fields.plugin,
  ).filter(Boolean))].join(", ");
  const metadata = [...new Set(group.records.filter((record) =>
    record.action === "agent_start" || record.kind === "response",
  ).map((record) => record.action === "agent_start"
    ? tm("chips.executionMode", { name: recordSubtitle(record) }) : recordSubtitle(record)))];
  return [
    { key: `${group.key}:group`, record: group.records[0], group, expanded, errors, plugins, metadata },
    ...(expanded ? group.records.map((record) => ({ key: record.key, record, nested: true })) : []),
  ];
}));

watch(selectedSpanId, () => expandedGroups.clear());

function timelineRecords(event) {
  const records = [];
  for (const record of event.records) {
    if (["stage_start", "stage_end", "pipeline_start", "wake_evaluated"].includes(record.action)) continue;
    if (record.action === "response_ready" && event.records.some((item) => item.action === "response_sent")) continue;
    if (record.action === "handler_end" || record.action === "agent_end") {
      const startAction = record.action === "handler_end" ? "handler_start" : "agent_start";
      const start = [...records].reverse().find((item) =>
        item.action === startAction && !item.completed &&
        item.fields.handler_full_name === record.fields.handler_full_name,
      );
      if (start) {
        start.fields = { ...start.fields, ...record.fields };
        start.completed = true;
        continue;
      }
    }
    records.push({ ...record, fields: { ...record.fields } });
  }
  return records;
}

function matchesFilter(event, filter) {
  if (filter === "errors") return event.status === "error";
  if (filter === "models") {
    return event.records.some((record) => record.kind === "agent" ||
      ["astr_agent_prepare", "astr_agent_complete"].includes(record.action));
  }
  if (filter === "plugins") {
    return event.records.some((record) => record.kind === "plugin_handler");
  }
  return true;
}

function recordSearchText(record) {
  return [
    record.action,
    record.kind,
    record.fields?.plugin,
    record.fields?.plugin_display_name,
    record.fields?.handler,
    record.fields?.handler_type,
    record.fields?.stage,
    record.fields?.message,
  ]
    .filter(Boolean)
    .join(" ");
}

function processNewTraces(newTraces) {
  if (!Array.isArray(newTraces)) return;

  for (const trace of newTraces) {
    if (!trace?.span_id) continue;
    if (["stage_start", "stage_end", "pipeline_start", "wake_evaluated"].includes(trace.action)) continue;
    let event = eventIndex.get(trace.span_id);
    if (!event) {
      event = reactive({
        span_id: trace.span_id,
        name: trace.name || "AstrMessageEvent",
        umo: trace.umo || "",
        sender_name: trace.sender_name || "",
        message_outline: trace.message_outline || "",
        platform_id: "",
        platform_name: "",
        platform_icon: "",
        first_time: trace.time || Date.now() / 1000,
        last_time: trace.time || Date.now() / 1000,
        status: "running",
        completed: false,
        records: [],
      });
      eventIndex.set(trace.span_id, event);
      events.value.unshift(event);
    }

    event.umo = event.umo || trace.umo || "";
    event.sender_name = event.sender_name || trace.sender_name || "";
    event.message_outline = event.message_outline || trace.message_outline || "";
    event.platform_id = trace.fields?.platform_id || event.platform_id;
    if (trace.fields?.platform_name) {
      event.platform_name = trace.fields.platform_name;
      event.platform_icon = getPlatformIcon(event.platform_name) || "";
    }
    event.first_time = Math.min(event.first_time, trace.time || event.first_time);
    event.last_time = Math.max(event.last_time, trace.time || event.last_time);

    const recordKey = trace.record_id || `${trace.span_id}:${trace.sequence ?? trace.time}:${trace.action}`;
    if (!event.records.some((record) => record.key === recordKey)) {
      event.records.push({ ...trace, key: recordKey, kind: trace.kind || trace.fields?.kind, fields: trace.fields || {} });
      event.records.sort((a, b) => (a.time || 0) - (b.time || 0));
    }
    if (trace.fields?.message && !event.message_outline && trace.action === "event_received") {
      event.message_outline = trace.fields.message;
    }
    if (trace.action === "pipeline_end") event.completed = true;
    if (trace.status === "error" || trace.fields?.status === "error") {
      event.status = "error";
    } else if (trace.action === "pipeline_end") {
      event.status = event.status === "error" ? "error" : "success";
    }
  }

  events.value.sort((a, b) => b.first_time - a.first_time);
  if (events.value.length > maxItems) {
    const removed = events.value.splice(maxItems);
    removed.forEach((event) => eventIndex.delete(event.span_id));
  }
}

async function fetchTraceHistory() {
  try {
    const response = await pluginApi.list();
    plugins.value = Object.fromEntries(
      (response.data?.data || []).filter((plugin) => plugin.name).map((plugin) => [plugin.name, plugin]),
    );
  } catch (error) {
    console.error("Failed to fetch trace plugin metadata:", error);
  }
  try {
    const response = await sessionApi.activeUmos();
    umoNames.value = Object.fromEntries(
      (response.data?.data?.umo_infos || []).map((info) => [
        info.umo, info.user_alias || info.auto_name || info.display_name || info.umo,
      ]),
    );
  } catch (error) {
    console.error("Failed to fetch session aliases:", error);
  }
  try {
    const response = await logApi.history();
    const logs = response.data?.data?.logs || [];
    processNewTraces(logs.filter((item) => item.type === "trace"));
  } catch (error) {
    console.error("Failed to fetch trace history:", error);
  } finally {
    loading.value = false;
  }
}

function connectSSE() {
  if (eventSource.value) eventSource.value.close();
  const token = localStorage.getItem("token");
  const source = new EventSourcePolyfill(logApi.liveUrl(), {
    headers: { Authorization: token ? `Bearer ${token}` : "" },
    heartbeatTimeout: 300000,
    withCredentials: true,
  });
  eventSource.value = source;
  source.onopen = () => {
    connected.value = true;
    retryAttempts.value = 0;
  };
  source.onmessage = (event) => {
    if (event.lastEventId) lastEventId.value = event.lastEventId;
    try {
      const payload = JSON.parse(event.data);
      if (payload?.type === "trace") processNewTraces([payload]);
    } catch (error) {
      console.error("Failed to parse trace payload:", error);
    }
  };
  source.onerror = () => {
    connected.value = false;
    source.close();
    if (retryAttempts.value >= maxRetryAttempts) return;
    const delay = Math.min(baseRetryDelay * 2 ** retryAttempts.value, 30000);
    if (retryTimer.value) clearTimeout(retryTimer.value);
    retryTimer.value = setTimeout(() => {
      retryAttempts.value += 1;
      connectSSE();
    }, delay);
  };
}

function selectEvent(spanId) {
  const previousSpanId = selectedSpanId.value;
  selectedSpanId.value = spanId;
  nextTick(() => {
    const row = document.querySelector(`[data-trace-id="${spanId || previousSpanId}"]`);
    row?.scrollIntoView({ block: "nearest" });
    if (!spanId) row?.focus();
  });
}

function clearSearch() {
  searchText.value = "";
}

function formatTime(timestamp) {
  if (!timestamp) return "-";
  const date = new Date(timestamp * 1000);
  return `${date.toLocaleTimeString([], { hour12: false })}.${String(date.getMilliseconds()).padStart(3, "0")}`;
}

function formatDuration(duration) {
  if (!Number.isFinite(duration)) return "-";
  if (duration < 1000) return `${Math.round(duration)} ms`;
  return `${(duration / 1000).toFixed(2)} s`;
}

function shortSpan(spanId) {
  return spanId ? spanId.slice(0, 8) : "-";
}

function statusLabel(event) {
  if (event.status === "error") return tm("status.error");
  if (event.status === "success") return tm("status.complete");
  return tm("status.live");
}

function statusClass(event) {
  if (event.status === "error") return "is-error";
  return event.status === "success" ? "is-success" : "is-live";
}

function recordLabel(record, grouped = false) {
  const key = actionLabels[record.action];
  let label = key ? tm(`actions.${key}`) : record.action;
  if (grouped) {
    label = ["handlerStart", "agentStart", "agentToolCall", "agentToolResult", "responseReady", "responseSent"].includes(key)
      ? tm(`groups.${key}`) : tm("groups.repeated", { label });
  }
  if (record.action === "event_received" && record.fields?.platform_id) {
    return `${label} (${record.fields.platform_id})`;
  }
  if (record.action === "handler_start" || record.action === "handler_end") {
    const fields = record.fields || {};
    const category = fields.handler_category || (
      fields.handler_type === "OnCallingFuncToolEvent" ? "llm_tool" :
      fields.handler_type && fields.handler_type !== "AdapterMessageEvent" ? "hook" : null
    );
    return category ? `${label} (${tm(`handlerCategories.${category}`)})` : label;
  }
  return label;
}

async function loadHandlerDescription(record) {
  const plugin = record.fields.plugin;
  if (!plugin || ["loading", "ready"].includes(handlerDetails[plugin]?.status)) return;
  const state = reactive({ status: "loading", descriptions: {} });
  handlerDetails[plugin] = state;
  try {
    const response = await pluginApi.get(plugin);
    if (response.data?.status !== "ok" || !response.data.data) {
      throw new Error("Plugin detail is unavailable");
    }
    const components = response.data.data.components || [];
    const pending = Array.isArray(components) ? [...components] : Object.values(components).flat();
    // Command groups can contain nested handlers, just as in the plugin detail page.
    for (let index = 0; index < pending.length; index++) {
      const component = pending[index];
      if (!component || typeof component !== "object") continue;
      const description = String(component.description || component.desc || "").trim();
      if (component.handler_full_name) state.descriptions[component.handler_full_name] = description;
      if (component.handler_name) state.descriptions[component.handler_name] = description;
      if (Array.isArray(component.subcommands)) pending.push(...component.subcommands);
    }
    state.status = "ready";
  } catch (error) {
    state.status = "error";
    console.error("Failed to fetch trace handler descriptions:", error);
  }
}

function recordSubtitle(record) {
  const fields = record.fields || {};
  if (record.action === "handler_start" || record.action === "handler_end") {
    return `${fields.plugin_display_name || fields.plugin || "Plugin"} · ${fields.handler || "handler"} · ${fields.handler_type || ""}`;
  }
  if (record.action === "stage_start" || record.action === "stage_end") return fields.stage || "";
  if (record.action === "response_sent" || record.action === "response_ready") {
    const source = fields.source;
    if (source?.startsWith("plugin:")) {
      const plugin = source.slice("plugin:".length);
      return tm("chips.pluginSender", { name: plugins.value[plugin]?.display_name || plugin });
    }
    return tm(source === "core" || source === "agent" ? "chips.systemSender" : "chips.unknownSender");
  }
  if (record.action === "agent_start") {
    const runner = fields.runner_type || "local";
    if (runner === "local") return configTm("aiSettings.localSettingsTitle");
    return ["dify", "coze", "dashscope", "deerflow"].includes(runner)
      ? configTm(`aiSettings.runners.${runner}.title`) : runner;
  }
  if (record.action === "agent_tool_call") return fields.tool_name?.name || fields.tool_name || "tool";
  if (record.action === "event_received") return fields.message || "";
  if (record.fields?.error) return record.fields.error;
  return fields.status || "";
}

function recordIcon(record) {
  return actionIcons[record.action] || Activity;
}

function recordClass(record) {
  if (record.fields?.status === "error") return "is-error";
  if (record.kind === "agent") return "is-agent";
  if (record.kind === "plugin_handler") return "is-plugin";
  if (record.action === "response_sent") return "is-response";
  return "is-system";
}

function formatFields(fields) {
  if (!fields || Object.keys(fields).length === 0) return "";
  const safeFields = { ...fields };
  if (typeof safeFields.system_prompt === "string" && safeFields.system_prompt.length > 1200) {
    safeFields.system_prompt = `${safeFields.system_prompt.slice(0, 1200)}…`;
  }
  try {
    return JSON.stringify(safeFields, null, 2);
  } catch {
    return String(fields);
  }
}

onMounted(async () => {
  durationTimer.value = setInterval(() => { clockNow.value = Date.now() / 1000; }, 1000);
  await fetchTraceHistory();
  connectSSE();
});

onBeforeUnmount(() => {
  if (durationTimer.value) clearInterval(durationTimer.value);
  eventSource.value?.close();
  if (retryTimer.value) clearTimeout(retryTimer.value);
});
</script>

<template>
  <div class="trace-explorer">
    <div class="trace-explorer-toolbar">
      <v-btn
        class="filter-toggle-btn"
        size="small"
        :variant="filtersOpen || selectedFilters.length ? 'tonal' : 'text'"
        :aria-expanded="filtersOpen"
        aria-controls="trace-filter-panel"
        @click="filtersOpen = !filtersOpen"
      >
        <v-icon icon="mdi-filter-variant" size="17" />
        <span>{{ tm("filters.button") }}</span>
        <span v-if="selectedFilters.length" class="filter-status-dot" aria-hidden="true" />
      </v-btn>
      <div class="trace-search">
        <Search :size="16" aria-hidden="true" />
        <input v-model="searchText" :placeholder="tm('search')" />
        <button v-if="searchText" type="button" class="icon-button" :aria-label="tm('clearSearch')" @click="clearSearch">
          <X :size="15" aria-hidden="true" />
        </button>
      </div>
      <div class="trace-live-state" :class="{ connected }"><span class="live-dot" />{{ connected ? tm("live") : tm("connecting") }}</div>
      <div class="trace-count">{{ filteredEvents.length }} {{ tm("records") }}</div>
      <button type="button" class="icon-button refresh-button" :aria-label="tm('refresh')" @click="fetchTraceHistory">
        <RefreshCw :size="16" aria-hidden="true" />
      </button>
    </div>

    <div class="trace-workspace">
      <button v-if="filtersOpen" type="button" class="trace-filter-backdrop" :aria-label="tm('filters.close')" @click="filtersOpen = false" />
      <aside v-if="filtersOpen" id="trace-filter-panel" class="trace-filter-panel" :aria-label="tm('filters.title')" @keydown.esc="filtersOpen = false">
        <div class="trace-filter-heading">
          <span>{{ tm("filters.title") }}</span>
          <v-btn v-if="selectedFilters.length" size="small" variant="text" @click="selectedFilters = []">{{ tm("filters.reset") }}</v-btn>
          <button type="button" class="icon-button" :aria-label="tm('filters.close')" @click="filtersOpen = false"><X :size="16" aria-hidden="true" /></button>
        </div>
        <div class="trace-filter-options">
          <label v-for="filter in filters" :key="filter.key" class="trace-filter-option">
            <v-checkbox-btn v-model="selectedFilters" :value="filter.key" :aria-label="filter.label" color="primary" density="compact" hide-details />
            <span>{{ filter.label }}</span>
          </label>
        </div>
        <p class="trace-filter-hint">{{ tm("filters.hint") }}</p>
      </aside>
    <div class="trace-explorer-body" :class="{ 'has-detail': selectedEvent }">
      <section class="trace-list" :aria-label="tm('traceList')">
        <div v-if="loading" class="trace-empty-state">{{ tm("loading") }}</div>
        <div v-else-if="filteredEvents.length === 0" class="trace-empty-state"><Activity :size="22" aria-hidden="true" /><span>{{ tm("empty") }}</span></div>
        <table v-else class="trace-list-table">
          <thead>
            <tr>
              <th scope="col">{{ tm("columns.status") }}</th>
              <th scope="col">{{ tm("columns.platform") }}</th>
              <th scope="col">{{ tm("columns.timestamp") }}</th>
              <th scope="col">{{ tm("columns.duration") }}</th>
              <th scope="col">{{ tm("columns.message") }}</th>
              <th scope="col">UMO</th>
              <th scope="col">{{ tm("columns.sender") }}</th>
              <th scope="col" :title="tm('columns.spansHint')">Spans</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="{ event, duration, spans } in traceRows"
              :key="event.span_id"
              class="trace-list-row"
              :class="{ selected: event.span_id === selectedSpanId }"
              :data-trace-id="event.span_id"
              tabindex="0"
              @click="selectEvent(event.span_id)"
              @keydown.enter="selectEvent(event.span_id)"
              @keydown.space.prevent="selectEvent(event.span_id)"
            >
              <td><v-chip size="x-small" variant="tonal" :color="event.status === 'error' ? 'error' : event.status === 'success' ? 'success' : 'warning'">{{ statusLabel(event) }}</v-chip></td>
              <td class="trace-platform-cell">
                <span class="trace-item-platform" :title="event.platform_id || event.platform_name">
                  <img v-if="event.platform_icon && !failedPlatformLogos.has(event.platform_icon)" :src="event.platform_icon" :alt="event.platform_name" @error="failedPlatformLogos.add(event.platform_icon)" />
                  <Activity v-else :size="16" aria-hidden="true" />
                </span>
              </td>
              <td class="trace-time-cell">{{ formatTime(event.first_time) }}</td>
              <td class="trace-duration-cell">{{ duration }}</td>
              <td class="trace-message-cell" :title="event.message_outline || tm('untitled')">{{ event.message_outline || tm("untitled") }}</td>
              <td class="trace-umo-cell">
                <v-tooltip :text="event.umo" location="top">
                  <template #activator="{ props }">
                    <span v-bind="props" :class="{ 'trace-hover-name': umoNames[event.umo] && umoNames[event.umo] !== event.umo }">{{ umoNames[event.umo] || event.umo || "-" }}</span>
                  </template>
                </v-tooltip>
              </td>
              <td class="trace-sender-cell" :title="event.sender_name">{{ event.sender_name || "-" }}</td>
              <td class="trace-spans-cell" :title="tm('columns.spansHint')">{{ spans }}</td>
            </tr>
          </tbody>
        </table>
      </section>

      <main v-if="selectedEvent" class="trace-detail" @keydown.esc.stop="selectEvent(null)">
        <div class="trace-detail-header">
          <div>
            <div class="trace-detail-kicker"><span class="trace-status-badge" :class="statusClass(selectedEvent)">{{ statusLabel(selectedEvent) }}</span><span>{{ shortSpan(selectedEvent.span_id) }}</span></div>
            <h2>{{ selectedEvent.message_outline || tm("untitled") }}</h2>
            <p>
              <v-tooltip :text="selectedEvent.umo" location="top">
                <template #activator="{ props }">
                  <span v-bind="props" :class="{ 'trace-hover-name': umoNames[selectedEvent.umo] && umoNames[selectedEvent.umo] !== selectedEvent.umo }">{{ umoNames[selectedEvent.umo] || selectedEvent.umo || "-" }}</span>
                </template>
              </v-tooltip>
              · {{ selectedEvent.sender_name || "-" }}
            </p>
          </div>
          <div class="trace-detail-actions">
            <div class="trace-detail-time">{{ formatTime(selectedEvent.first_time) }}</div>
            <button type="button" class="icon-button" :aria-label="tm('closeDetails')" @click="selectEvent(null)"><X :size="17" aria-hidden="true" /></button>
          </div>
        </div>

        <div class="trace-stat-grid">
          <div class="trace-stat"><Clock3 :size="15" /><span>{{ tm("duration") }}</span><strong>{{ selectedStats.duration }}</strong></div>
          <div class="trace-stat"><PlugZap :size="15" /><span>{{ tm("handlers") }}</span><strong>{{ selectedStats.handlers }}</strong></div>
          <div class="trace-stat"><Send :size="15" /><span>{{ tm("responses") }}</span><strong>{{ selectedStats.responses }}</strong></div>
        </div>

        <div class="trace-timeline">
          <div v-for="(row, index) in timelineRows" :key="row.key" class="timeline-record" :class="{ 'timeline-group': row.group, 'timeline-nested': row.nested }">
            <div class="timeline-rail">
              <span class="timeline-icon-stack" :class="{ 'is-stacked': row.group && !row.expanded }">
              <span
                v-for="(record, iconIndex) in row.group && !row.expanded ? row.group.records.slice(0, 3) : [row.record]"
                :key="record.key"
                class="timeline-icon"
                :class="recordClass(record)"
                :style="{ '--stack-index': iconIndex }"
              >
                <img
                  v-if="record.action === 'event_received' && selectedEvent.platform_icon && !failedPlatformLogos.has(selectedEvent.platform_icon)"
                  class="timeline-platform-logo"
                  :src="selectedEvent.platform_icon"
                  alt=""
                  @error="failedPlatformLogos.add(selectedEvent.platform_icon)"
                />
                <img
                  v-else-if="record.kind === 'plugin_handler'"
                  class="timeline-plugin-logo"
                  :src="plugins[record.fields.plugin]?.logo && !failedPluginLogos.has(plugins[record.fields.plugin].logo) ? plugins[record.fields.plugin].logo : defaultPluginIcon"
                  alt=""
                  @error="failedPluginLogos.add(plugins[record.fields.plugin]?.logo)"
                />
                <component v-else :is="recordIcon(record)" :size="14" aria-hidden="true" />
              </span>
              </span>
              <span v-if="index < timelineRows.length - 1" class="timeline-line" />
            </div>
            <div class="timeline-content">
              <button
                v-if="row.group"
                type="button"
                class="timeline-group-toggle"
                :aria-expanded="row.expanded"
                @click="row.expanded ? expandedGroups.delete(row.group.key) : expandedGroups.add(row.group.key)"
              >
                <div class="timeline-heading">
                  <span class="timeline-group-title">
                    <strong>{{ recordLabel(row.record, true) }}</strong>
                    <span class="timeline-group-count">{{ tm("groups.count", { count: row.group.records.length }) }}</span>
                    <span v-if="row.errors" class="timeline-group-errors">{{ tm("groups.errors", { count: row.errors }) }}</span>
                  </span>
                  <time>{{ formatTime(row.record.time) }}</time>
                </div>
                <div class="timeline-subtitle timeline-group-summary">
                  <v-chip v-if="row.plugins" class="timeline-metadata-chip" size="x-small" variant="tonal" color="primary" :title="row.plugins">{{ row.plugins }}</v-chip>
                  <v-chip v-for="label in row.metadata" :key="label" class="timeline-metadata-chip" size="x-small" variant="tonal">{{ label }}</v-chip>
                  <span class="timeline-group-expansion"><ChevronDown :size="13" :class="{ 'is-collapsed': !row.expanded }" aria-hidden="true" />{{ tm(row.expanded ? "collapse" : "expand") }}</span>
                </div>
              </button>
              <template v-else v-for="record in [row.record]" :key="record.key">
              <div class="timeline-heading"><strong>{{ recordLabel(record) }}</strong><time>{{ formatTime(record.time) }}</time></div>
              <div v-if="record.kind === 'plugin_handler'" class="timeline-subtitle">
                <v-tooltip :text="record.fields.plugin" location="top">
                  <template #activator="{ props }">
                    <v-chip v-bind="props" class="trace-hover-name timeline-metadata-chip" size="x-small" variant="tonal" color="primary">{{ record.fields.plugin_display_name || record.fields.plugin || "Plugin" }}</v-chip>
                  </template>
                </v-tooltip>
                ·
                <v-tooltip location="top" @update:model-value="(open) => open && loadHandlerDescription(record)">
                  <template #activator="{ props }">
                    <span v-bind="props" class="trace-hover-name" tabindex="0">{{ record.fields.handler }}</span>
                  </template>
                  <div class="trace-handler-description">
                    <template v-if="!handlerDetails[record.fields.plugin] || handlerDetails[record.fields.plugin].status === 'loading'">{{ tm("handlerDescription.loading") }}</template>
                    <template v-else-if="handlerDetails[record.fields.plugin].status === 'error'">{{ tm("handlerDescription.loadFailed") }}</template>
                    <template v-else>{{ handlerDetails[record.fields.plugin].descriptions[record.fields.handler_full_name || record.fields.handler] || tm("handlerDescription.empty") }}</template>
                  </div>
                </v-tooltip>
                · {{ record.fields.handler_type }}
                <span v-if="record.fields.duration_ms != null"> · {{ formatDuration(record.fields.duration_ms) }}</span>
              </div>
              <div v-else-if="record.kind === 'response'" class="timeline-subtitle">
                <v-chip class="timeline-metadata-chip" size="x-small" variant="tonal" :title="record.fields.source">{{ recordSubtitle(record) }}</v-chip>
                <div v-if="record.fields.message" class="trace-response-outline">{{ record.fields.message }}</div>
              </div>
              <div v-else-if="record.action === 'agent_start'" class="timeline-subtitle">
                <v-chip class="timeline-metadata-chip" size="x-small" variant="tonal" color="primary">{{ tm("chips.executionMode", { name: recordSubtitle(record) }) }}</v-chip>
              </div>
              <div v-else-if="recordSubtitle(record)" class="timeline-subtitle">{{ recordSubtitle(record) }}</div>
              <details v-if="formatFields(record.fields)" class="timeline-fields"><summary>{{ tm("details") }}</summary><pre>{{ formatFields(record.fields) }}</pre></details>
              </template>
            </div>
          </div>
        </div>
      </main>
    </div>
    </div>
  </div>
</template>

<style scoped>
.trace-response-outline { margin-top: 6px; white-space: pre-wrap; overflow-wrap: anywhere; color: rgb(var(--v-theme-on-surface)); }
.trace-hover-name { text-decoration-line: underline; text-decoration-style: dotted; text-underline-offset: 4px; cursor: help; }
.trace-handler-description { max-width: min(400px, calc(100vw - 48px)); max-height: 320px; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; }
.timeline-plugin-logo { border-radius: 50%; height: 19px; object-fit: contain; width: 19px; }
.timeline-platform-logo { height: 19px; object-fit: contain; width: 19px; }
.timeline-icon-stack { display: block; height: 23px; position: relative; width: 23px; }
.timeline-icon-stack.is-stacked { margin-top: 6px; }
.is-stacked .timeline-icon { background: linear-gradient(var(--timeline-icon-background), var(--timeline-icon-background)), rgb(var(--v-theme-surface)); left: calc(var(--stack-index) * 3px); position: absolute; top: calc(var(--stack-index) * -3px); z-index: calc(3 - var(--stack-index)); }
.timeline-group-toggle { background: transparent; border: 0; border-radius: 5px; color: inherit; cursor: pointer; display: block; padding: 0; text-align: left; width: 100%; }
.timeline-group-toggle:hover .timeline-group-expansion { color: rgb(var(--v-theme-primary)); }
.timeline-group-toggle:focus-visible { outline: 2px solid rgb(var(--v-theme-primary)); outline-offset: 4px; }
.timeline-group-title { align-items: center; display: flex; flex-wrap: wrap; gap: 6px; }
.timeline-group-count { background: rgba(var(--v-theme-on-surface), 0.06); border-radius: 4px; color: var(--trace-muted); font-size: 10px; padding: 1px 5px; white-space: nowrap; }
.timeline-group-errors { color: #ef4444; font-size: 10px; white-space: nowrap; }
.timeline-group-summary { align-items: center; display: flex; flex-wrap: wrap; gap: 6px 10px; }
.timeline-metadata-chip { max-width: 100%; vertical-align: middle; }
.timeline-metadata-chip :deep(.v-chip__content) { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.timeline-group-expansion { align-items: center; display: inline-flex; flex: 0 0 auto; font-size: 10px; gap: 3px; }
.timeline-group-expansion svg { transition: transform 0.15s ease; }
.timeline-group-expansion .is-collapsed { transform: rotate(-90deg); }
.timeline-nested .timeline-content { border-left: 2px solid var(--trace-border); padding-left: 10px; }
.trace-explorer { --trace-border: rgba(var(--v-theme-on-surface), 0.1); --trace-muted: rgba(var(--v-theme-on-surface), 0.58); background: rgba(var(--v-theme-on-surface), 0.025); border: 1px solid var(--trace-border); border-radius: 12px; display: flex; flex-direction: column; height: 100%; min-height: 0; overflow: hidden; }
.trace-explorer-toolbar { align-items: center; border-bottom: 1px solid var(--trace-border); display: flex; gap: 10px; min-height: 50px; padding: 8px 12px; }
.filter-toggle-btn { flex: 0 0 auto; }
.filter-toggle-btn :deep(.v-btn__content) { gap: 5px; }
.filter-status-dot { background: rgb(var(--v-theme-primary)); border-radius: 50%; height: 6px; width: 6px; }
.trace-workspace { display: flex; flex: 1; min-height: 0; min-width: 0; overflow: hidden; position: relative; }
.trace-filter-panel { background: rgb(var(--v-theme-surface)); border-right: 1px solid var(--trace-border); flex: 0 0 220px; min-height: 0; overflow: auto; padding: 12px; }
.trace-filter-heading { align-items: center; display: flex; font-size: 13px; font-weight: 650; gap: 4px; min-height: 32px; }
.trace-filter-heading > span { flex: 1; }
.trace-filter-options { border-top: 1px solid var(--trace-border); margin-top: 8px; padding-top: 8px; }
.trace-filter-option { align-items: center; cursor: pointer; display: flex; font-size: 12px; min-height: 32px; }
.trace-filter-option :deep(.v-selection-control) { flex: 0 0 auto; min-height: 32px; }
.trace-filter-hint { color: var(--trace-muted); font-size: 11px; line-height: 1.6; margin: 12px 0 0; }
.trace-filter-backdrop { display: none; }
.trace-search { align-items: center; background: rgba(var(--v-theme-on-surface), 0.06); border: 1px solid transparent; border-radius: 7px; color: var(--trace-muted); display: flex; flex: 1; gap: 8px; max-width: 520px; padding: 7px 9px; }
.trace-search:focus-within { border-color: rgba(var(--v-theme-primary), 0.6); }
.trace-search input { background: transparent; border: 0; color: rgb(var(--v-theme-on-surface)); font-size: 12px; min-width: 0; outline: 0; width: 100%; }
.icon-button { align-items: center; background: transparent; border: 0; border-radius: 5px; color: var(--trace-muted); cursor: pointer; display: inline-flex; justify-content: center; padding: 4px; }
.icon-button:hover { background: rgba(var(--v-theme-on-surface), 0.08); color: rgb(var(--v-theme-on-surface)); }
.trace-live-state, .trace-count { color: var(--trace-muted); font-size: 11px; white-space: nowrap; }
.trace-live-state { align-items: center; display: flex; gap: 6px; }
.live-dot { background: #a1a1aa; border-radius: 50%; height: 6px; width: 6px; }
.trace-live-state.connected .live-dot { background: #22c55e; box-shadow: 0 0 0 3px rgba(34, 197, 94, 0.14); }
.trace-explorer-body { display: flex; flex: 1; min-height: 0; min-width: 0; overflow: hidden; position: relative; }
.trace-list { flex: 1; min-height: 0; min-width: 0; overflow: auto; }
.has-detail .trace-list { border-right: 1px solid var(--trace-border); }
.trace-list-table { border-collapse: separate; border-spacing: 0; font-size: 12px; min-width: 1100px; table-layout: fixed; width: 100%; }
.trace-list-table th { background: rgb(var(--v-theme-surface)); border-bottom: 1px solid var(--trace-border); color: var(--trace-muted); font-size: 11px; font-weight: 600; padding: 11px 12px; position: sticky; text-align: left; top: 0; white-space: nowrap; z-index: 1; }
.trace-list-table th:nth-child(1) { width: 100px; } .trace-list-table th:nth-child(2) { width: 56px; } .trace-list-table th:nth-child(3) { width: 132px; } .trace-list-table th:nth-child(4) { width: 92px; } .trace-list-table th:nth-child(5) { width: 26%; } .trace-list-table th:nth-child(6) { width: 28%; } .trace-list-table th:nth-child(7) { width: 110px; } .trace-list-table th:nth-child(8) { width: 64px; }
.trace-list-table td { border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.06); height: 48px; overflow: hidden; padding: 10px 12px; text-overflow: ellipsis; white-space: nowrap; }
.trace-list-row { cursor: pointer; } .trace-list-row:hover { background: rgba(var(--v-theme-on-surface), 0.045); } .trace-list-row.selected { background: rgba(var(--v-theme-primary), 0.1); } .trace-list-row:focus-visible { outline: 2px solid rgb(var(--v-theme-primary)); outline-offset: -2px; }
.trace-item-platform { align-items: center; color: var(--trace-muted); display: inline-flex; height: 20px; justify-content: center; vertical-align: middle; width: 20px; }
.trace-item-platform img { height: 20px; object-fit: contain; width: 20px; }
.trace-time-cell, .trace-duration-cell, .trace-spans-cell { color: var(--trace-muted); font-family: var(--astrbot-font-cjk-mono), monospace; font-size: 11px; }
.trace-message-cell { font-weight: 500; } .trace-umo-cell, .trace-sender-cell { color: var(--trace-muted); }
.trace-detail { background: rgb(var(--v-theme-surface)); flex: 0 0 58%; max-width: 850px; min-height: 0; min-width: 360px; overflow: auto; padding: 18px 22px 28px; }
.trace-detail-actions { align-items: center; display: flex; flex: 0 0 auto; gap: 8px; }
.trace-detail-header { align-items: flex-start; display: flex; gap: 16px; justify-content: space-between; }
.trace-detail-kicker { align-items: center; color: var(--trace-muted); display: flex; font-size: 10px; gap: 8px; text-transform: uppercase; }
.trace-detail-header h2 { font-size: 17px; font-weight: 650; margin: 8px 0 4px; overflow-wrap: anywhere; } .trace-detail-header p { color: var(--trace-muted); font-size: 11px; margin: 0; }
.trace-detail-time { color: var(--trace-muted); font-family: var(--astrbot-font-cjk-mono), monospace; font-size: 11px; white-space: nowrap; }
.trace-status-badge { border-radius: 999px; font-size: 10px; padding: 3px 7px; text-transform: none; } .trace-status-badge.is-live { background: rgba(245, 158, 11, 0.14); color: #f59e0b; } .trace-status-badge.is-success { background: rgba(34, 197, 94, 0.14); color: #22c55e; } .trace-status-badge.is-error { background: rgba(239, 68, 68, 0.14); color: #ef4444; }
.trace-stat-grid { display: grid; gap: 8px; grid-template-columns: repeat(3, minmax(0, 1fr)); margin: 18px 0 22px; }
.trace-stat { background: rgba(var(--v-theme-on-surface), 0.04); border: 1px solid var(--trace-border); border-radius: 8px; display: grid; gap: 4px; grid-template-columns: 16px 1fr; padding: 9px 10px; } .trace-stat svg { color: var(--trace-muted); grid-row: span 2; margin-top: 2px; } .trace-stat span { color: var(--trace-muted); font-size: 10px; } .trace-stat strong { font-size: 13px; font-weight: 650; }
.trace-timeline { max-width: 900px; } .timeline-record { display: grid; gap: 11px; grid-template-columns: 24px minmax(0, 1fr); min-height: 58px; } .timeline-rail { align-items: center; display: flex; flex-direction: column; }
.timeline-icon { --timeline-icon-background: rgba(var(--v-theme-on-surface), 0.06); align-items: center; background: var(--timeline-icon-background); border: 1px solid var(--trace-border); border-radius: 50%; display: inline-flex; height: 23px; justify-content: center; width: 23px; z-index: 1; } .timeline-icon.is-system { color: var(--trace-muted); } .timeline-icon.is-plugin { --timeline-icon-background: rgba(168, 85, 247, 0.13); color: #a855f7; } .timeline-icon.is-agent { --timeline-icon-background: rgba(59, 130, 246, 0.13); color: #3b82f6; } .timeline-icon.is-response { --timeline-icon-background: rgba(34, 197, 94, 0.13); color: #22c55e; } .timeline-icon.is-error { --timeline-icon-background: rgba(239, 68, 68, 0.13); color: #ef4444; }
.timeline-line { background: var(--trace-border); flex: 1; width: 1px; } .timeline-content { border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.07); min-width: 0; padding: 2px 0 13px; } .timeline-heading { align-items: baseline; display: flex; gap: 10px; justify-content: space-between; } .timeline-heading strong { font-size: 12px; font-weight: 650; } .timeline-heading time { color: var(--trace-muted); font-family: var(--astrbot-font-cjk-mono), monospace; font-size: 10px; white-space: nowrap; } .timeline-subtitle { color: var(--trace-muted); font-size: 11px; line-height: 1.5; margin-top: 4px; overflow-wrap: anywhere; }
.timeline-fields { margin-top: 6px; } .timeline-fields summary { color: var(--trace-muted); cursor: pointer; font-size: 10px; } .timeline-fields pre { background: rgba(var(--v-theme-on-surface), 0.04); border-radius: 6px; color: var(--trace-muted); font-size: 10px; line-height: 1.5; margin: 6px 0 0; max-height: 280px; overflow: auto; padding: 8px; white-space: pre-wrap; word-break: break-word; }
.trace-empty-state { align-items: center; color: var(--trace-muted); display: flex; flex-direction: column; font-size: 12px; gap: 8px; justify-content: center; min-height: 180px; }
@media (max-width: 1100px) { .trace-detail { border-left: 1px solid var(--trace-border); bottom: 0; box-shadow: -8px 0 24px rgba(0, 0, 0, 0.12); max-width: none; min-width: 0; position: absolute; right: 0; top: 0; width: min(760px, 90%); z-index: 1; } }
@media (max-width: 900px) { .trace-filter-panel { bottom: 0; box-shadow: 8px 0 24px rgba(0, 0, 0, 0.18); left: 0; max-width: 85%; position: absolute; top: 0; width: 220px; z-index: 3; } .trace-filter-backdrop { background: rgba(var(--v-theme-on-surface), 0.12); border: 0; display: block; inset: 0; position: absolute; z-index: 2; } .trace-detail { padding: 15px; } .trace-stat-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } .trace-count { display: none; } }
@media (max-width: 640px) { .trace-explorer-toolbar { flex-wrap: wrap; } .filter-toggle-btn { order: 1; } .trace-search { flex: 1 1 160px; max-width: none; order: 1; } .trace-live-state { order: 2; } .refresh-button { margin-left: auto; order: 2; } .trace-detail { width: 100%; } .trace-detail-time { display: none; } }
</style>
