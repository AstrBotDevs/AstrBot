<script setup>
import {
  Activity,
  Bot,
  Box,
  Check,
  ChevronDown,
  Clock3,
  Hash,
  Heart,
  LoaderCircle,
  Pause,
  Play,
  PlugZap,
  Puzzle,
  RefreshCw,
  Search,
  Send,
  UserRound,
  Workflow,
  Wrench,
  X,
} from "@lucide/vue";
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { EventSourcePolyfill } from "event-source-polyfill";
import { logApi, traceApi, pluginApi, sessionApi } from "@/api/v1";
import { useModuleI18n } from "@/i18n/composables";
import { getPlatformIcon } from "@/utils/platformUtils";
import defaultPluginIcon from "/favicon.svg";
import TraceMessagePreview from "./TraceMessagePreview.vue";

const { tm } = useModuleI18n("features/trace");
const { tm: configTm } = useModuleI18n("features/config");
const props = defineProps({
  recordingEnabled: { type: Boolean, default: true },
  recordingBusy: { type: Boolean, default: false },
});
const emit = defineEmits(["toggle-recording"]);
const maxItems = 300;
const events = ref([]);
const selectedSpanId = ref(null);
const searchText = ref("");
const filtersOpen = ref(false);
const selectedFilters = ref([]);
const loading = ref(true);
const historyBusy = ref(false);
const detailBusy = ref(false);
const historyError = ref("");
const detailError = ref("");
const totalRecords = ref(0);
const historyPage = ref(1);
const pageSize = ref(50);
const storageWarning = ref(false);
let metadataLoaded = false;
let historyRequest = 0;
let detailRequest = 0;
let queryTimer = null;
const clockNow = ref(Date.now() / 1000);
const durationTimer = ref(null);
const connected = ref(false);
const recordingLabel = computed(() => !props.recordingEnabled ? tm("controls.start") : connected.value ? tm("controls.pauseButton") : tm("connecting"));
const eventSource = ref(null);
const retryTimer = ref(null);
const retryAttempts = ref(0);
const lastEventId = ref(null);
const maxRetryAttempts = 10;
const baseRetryDelay = 1000;
let hasOpenedStream = false;
const eventIndex = new Map();
const umoNames = ref({});
const plugins = ref({});
const failedPluginLogos = reactive(new Set());
const failedPlatformLogos = reactive(new Set());
const handlerDetails = reactive({});
const expandedGroups = reactive(new Set());
const expandedAgents = reactive(new Set());
const expandedDetails = reactive(new Set());
const enteringTraceIds = reactive(new Set());
const traceEnterTimers = new Map();
const traceListElement = ref(null);
const pendingTraceEntryIds = new Set();
let traceEntryFrame = null;
let traceListAnimation = null;

const actionLabels = {
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
      event.plugin_names,
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
    const previous = eventIndex.get(selectedSpanId.value);
    if (previous?.model_version === 3) previous.records = [];
    selectedSpanId.value = null;
  }
});

const traceRows = computed(() => filteredEvents.value.map((event) => ({
  event,
  duration: formatDuration(Math.max(0, ((event.completed ? event.last_time : Math.max(clockNow.value, event.last_time)) - event.first_time) * 1000)),
  spans: event.span_count ?? timelineRecords(event).length,
})));

const traceHeaders = computed(() => [
  { title: tm("columns.status"), key: "status", width: 120 },
  { title: tm("columns.platform"), key: "platform", width: 80, minWidth: 80, headerProps: { class: "text-no-wrap" } },
  { title: tm("columns.timestamp"), key: "timestamp", width: 200, minWidth: 200 },
  { title: tm("columns.duration"), key: "duration", width: 120 },
  { title: tm("columns.message"), key: "message", minWidth: 240 },
  { title: tm("columns.category"), key: "category", width: 220, minWidth: 220, headerProps: { class: "text-no-wrap" } },
  { title: "UMO", key: "umo", minWidth: 240 },
  { title: tm("columns.sender"), key: "sender", minWidth: 120 },
  { title: "Spans", key: "spans", width: 80 },
]);

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

const selectedTokenUsage = computed(() => {
  const latest = new Map();
  for (const record of selectedEvent.value?.records || []) {
    if (record.action !== "astr_agent_complete" && record.kind !== "agent") continue;
    const usage = record.fields?.stats?.token_usage;
    if (!usage || !["input_other", "input_cached", "output"].every((key) => Number.isSafeInteger(usage[key]) && usage[key] >= 0)) continue;
    // Runner stats are cumulative snapshots, not per-request deltas.
    latest.set(record.owner_span_id || record.operation_span_id || "root", usage);
  }
  if (!latest.size) return null;
  let input = 0, output = 0, cached = 0;
  for (const usage of latest.values()) {
    input += usage.input_other + usage.input_cached;
    output += usage.output;
    cached += usage.input_cached;
  }
  const total = input + output;
  return total > 0 ? { total, input, output, cached } : null;
});

const selectedRecords = computed(() => selectedEvent.value ? timelineRecords(selectedEvent.value) : []);

const timelineGroups = computed(() => {
  const groups = [];
  const records = selectedRecords.value;
  const parents = new Map();
  const agents = new Map();
  records.forEach((record, index) => {
    if (record.operation_span_id && record.parent_span_id !== undefined) {
      parents.set(record.operation_span_id, record.parent_span_id);
    }
    if (record.action === "agent_start" && record.operation_span_id) {
      agents.set(record.operation_span_id, index);
    }
  });
  for (const [index, record] of records.entries()) {
    const ancestors = [];
    const visited = new Set(record.operation_span_id ? [record.operation_span_id] : []);
    let ancestor = record.owner_span_id || parents.get(record.operation_span_id);
    while (ancestor && !visited.has(ancestor)) {
      visited.add(ancestor);
      if (agents.has(ancestor) && agents.get(ancestor) < index) ancestors.unshift(ancestor);
      ancestor = parents.get(ancestor);
    }
    // Responses stay on the main line even when their owning Agent is folded.
    if (record.kind === "response") ancestors.length = 0;
    const agentId = record.action === "agent_start" ? record.operation_span_id : null;
    const type = `${record.action}:${recordLabel(record)}:${ancestors.join(":")}:${agentId || ""}`;
    const fields = record.fields || {};
    const category = record.kind === "plugin_handler" ? fields.handler_category || (
      fields.handler_type === "OnCallingFuncToolEvent" ? "llm_tool" :
      fields.handler_type && fields.handler_type !== "AdapterMessageEvent" ? "hook" : "listener"
    ) : null;
    const previous = groups[groups.length - 1];
    // Only adjacent records are grouped, preserving the execution order.
    if (previous?.type === type) {
      previous.records.push(record);
    } else {
      groups.push({ key: record.key, type, records: [record], ancestors, agentId, category });
    }
  }
  return groups;
});

const timelineRows = computed(() => {
  const rows = [];
  const agentErrors = new Map();
  const agentMetadata = new Map();
  for (const group of timelineGroups.value) {
    for (const id of group.ancestors) {
      agentErrors.set(id, (agentErrors.get(id) || 0) + group.records.filter((record) => record.fields.status === "error").length);
    }
    // Attribute metadata to the nearest Agent, including through plugin/tool spans.
    const owner = group.ancestors.at(-1);
    if (!owner) continue;
    if (!agentMetadata.has(owner)) agentMetadata.set(owner, { models: [], personas: [], toolCalls: 0 });
    const metadata = agentMetadata.get(owner);
    for (const record of group.records) {
      if (record.action === "astr_agent_prepare") {
        const provider = record.fields.chat_provider;
        if (provider?.model && !metadata.models.some((model) => model.id === provider.model && model.provider === provider.id)) {
          metadata.models.push({ id: provider.model, provider: provider.id || "" });
        }
        const persona = record.fields.persona_id;
        if (persona && !metadata.personas.includes(persona)) metadata.personas.push(persona);
      }
      if (record.action === "agent_tool_call") metadata.toolCalls += 1;
    }
  }
  for (const group of timelineGroups.value) {
    if (group.ancestors.some((id) => !expandedAgents.has(id))) continue;
    const depth = group.ancestors.length;
    const detailsExpanded = expandedDetails.has(group.key);
    if (group.records.length === 1) {
      const agentId = group.agentId;
      rows.push({ key: group.key, record: group.records[0], category: group.category, depth,
        agentId, agentInfo: agentId ? agentMetadata.get(agentId) : null,
        expanded: agentId ? expandedAgents.has(agentId) : detailsExpanded,
        detailsExpanded, errors: agentId ? (agentErrors.get(agentId) || 0) + Number(group.records[0].fields.status === "error") : 0 });
      continue;
    }
    const expanded = expandedGroups.has(group.key);
    const errors = group.records.filter((record) => record.fields.status === "error").length;
    const plugins = [...new Set(group.records.map((record) =>
      record.fields.plugin_display_name || record.fields.plugin,
    ).filter(Boolean))].join(", ");
    const metadata = [...new Set(group.records.filter((record) =>
      record.action === "agent_start",
    ).map((record) => recordSubtitle(record)))];
    rows.push({ key: `${group.key}:group`, record: group.records[0], group, expanded, errors, plugins, metadata, category: group.category, depth });
    if (expanded) {
      for (const record of group.records) {
        const detailsExpanded = expandedDetails.has(record.key);
        rows.push({ key: record.key, record, nested: true, depth: depth + 1,
          category: group.category, detailsExpanded, expanded: detailsExpanded });
      }
    }
  }
  return rows;
});

watch(selectedSpanId, () => {
  expandedGroups.clear();
  expandedAgents.clear();
  expandedDetails.clear();
});

function timelineRecords(event) {
  const records = [];
  for (const record of event.records) {
    if (["stage_start", "stage_end", "pipeline_start", "wake_evaluated", "sel_persona"].includes(record.action)) continue;
    if (record.action === "response_ready" && event.records.some((item) => item.action === "response_sent")) continue;
    if (record.action === "handler_end" || record.action === "agent_end") {
      const startAction = record.action === "handler_end" ? "handler_start" : "agent_start";
      const start = [...records].reverse().find((item) =>
        item.action === startAction && !item.completed &&
        (item.operation_span_id && record.operation_span_id
          ? item.operation_span_id === record.operation_span_id
          : item.fields.handler_full_name === record.fields.handler_full_name),
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
    return event.has_models ?? event.records.some((record) => record.kind === "agent" ||
      ["astr_agent_prepare", "astr_agent_complete"].includes(record.action));
  }
  if (filter === "plugins") {
    return event.has_plugins ?? event.records.some((record) => record.kind === "plugin_handler");
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

function normalizeTracePayload(payload) {
  const summary = payload.trace;
  const attrs = summary.attributes || {};
  const finished = summary.state !== "running";
  const time = Number(payload.time_unix_nano || summary.updated_time_unix_nano || summary.start_time_unix_nano) / 1e9;
  const meta = {
    span_id: summary.trace_id, name: summary.name, model_version: 3,
    umo: attrs["astrbot.umo"] || "", sender_name: attrs["astrbot.sender_name"] || "",
    message_type: attrs["astrbot.message_type"] || attrs["astrbot.umo"]?.split(":")[1] || "",
    message_outline: attrs["astrbot.message_outline"] || "",
    plugin_names: attrs["astrbot.plugins"] || "",
    platform_id: attrs["astrbot.platform_id"] || "",
    platform_name: attrs["astrbot.platform_name"] || "",
    time: Number(summary.start_time_unix_nano) / 1e9,
    last_time: Number(summary.end_time_unix_nano) / 1e9 || time,
    completed: finished, status: summary.has_errors ? "error" : finished ? "success" : "running",
    has_models: summary.has_models, has_plugins: summary.has_plugins,
    has_commands: summary.has_commands ?? (payload.spans
      ? payload.spans.some((span) => span.attributes?.["astrbot.handler_category"] === "command")
      : undefined),
    span_count: summary.span_count, truncated: summary.truncated,
    model_updated_ns: String(summary.updated_time_unix_nano || summary.start_time_unix_nano),
  };
  const records = [];
  const spans = payload.spans || (payload.span ? [payload.span] : []);
  const items = [
    ...spans.map((span) => ({ span })),
    ...spans.flatMap((span) => (span.events || []).map((event) => ({ event }))),
    ...(payload.event ? [{ event: payload.event }] : []),
  ];
  for (const item of items) {
    const model = item.span || item.event;
    const inspectedModel = item.span ? { ...model, events: undefined } : model;
    const fields = {};
    for (const [key, value] of Object.entries(model.attributes || {})) {
      if (!key.startsWith("astrbot.")) continue;
      const name = key.slice(8);
      fields[name] = value;
      if (["chat_provider", "stats", "tools", "tool_name"].includes(name) && typeof value === "string") {
        try { fields[name] = JSON.parse(value); } catch { /* Plain text is valid. */ }
      }
    }
    if (item.event) {
      records.push({
        span_id: summary.trace_id, record_id: model.event_id,
        owner_span_id: model.span_id,
        action: model.name, time: Number(model.time_unix_nano) / 1e9,
        fields, kind: fields.kind, model: inspectedModel,
      });
      continue;
    }
    const root = model.span_id === summary.root_span_id;
    // Read legacy action metadata only when an old span has no call type.
    const kind = root ? "message" : fields.kind || {
      handler_start: "plugin_handler", agent_start: "agent", agent_tool_call: "tool",
    }[fields.action];
    const transitions = {
      message: ["event_received", "pipeline_end"],
      plugin_handler: ["handler_start", "handler_end"],
      agent: ["agent_start", "agent_end"],
      tool: ["agent_tool_call", "agent_tool_result"],
    };
    const [action, endAction] = transitions[kind] || [];
    if (!action) continue;
    delete fields.action;
    delete fields.end_action;
    delete fields.duration_ms;
    const started = Number(model.start_time_unix_nano) / 1e9;
    records.push({
      span_id: summary.trace_id, record_id: model.span_id + ":start",
      operation_span_id: model.span_id, parent_span_id: model.parent_span_id,
      action, time: started,
      fields: { ...fields, kind, status: "running" },
      kind, model: inspectedModel,
    });
    if (model.end_time_unix_nano) {
      const ended = Number(model.end_time_unix_nano) / 1e9;
      records.push({
        span_id: summary.trace_id, record_id: model.span_id + ":end",
        operation_span_id: model.span_id, parent_span_id: model.parent_span_id,
        action: endAction,
        time: ended, kind,
        fields: { ...fields, duration_ms: Math.max(0, Number(BigInt(model.end_time_unix_nano) - BigInt(model.start_time_unix_nano)) / 1e6),
          status: model.status?.code === 2 ? "error" : "success",
          error: model.status?.message || fields.error },
        model: inspectedModel,
      });
    }
  }
  return { meta, records };
}

function processNewTraces(newTraces) {
  if (!Array.isArray(newTraces)) return;
  for (const packet of newTraces) {
    const normalized = packet?.trace ? normalizeTracePayload(packet) : null;
    const trace = normalized?.meta || packet;
    if (!trace?.span_id) continue;
    if (["stage_start", "stage_end", "pipeline_start", "wake_evaluated"].includes(trace.action)) continue;
    let event = eventIndex.get(trace.span_id);
    if (!event) {
      event = reactive({
        span_id: trace.span_id, name: trace.name || "AstrMessageEvent",
        umo: trace.umo || "", sender_name: trace.sender_name || "",
        message_outline: trace.message_outline || "",
        platform_id: "", platform_name: "", platform_icon: "",
        first_time: trace.time || Date.now() / 1000,
        last_time: trace.time || Date.now() / 1000,
        status: "running", completed: false, records: [],
      });
      eventIndex.set(trace.span_id, event);
      events.value.unshift(event);
    }
    if (normalized) {
      if (!event.model_updated_ns || trace.model_updated_ns.padStart(20, "0") >= event.model_updated_ns.padStart(20, "0")) {
        Object.assign(event, trace);
        event.first_time = trace.time;
        event.platform_icon = getPlatformIcon(trace.platform_name) || "";
      }
    } else {
      event.umo = event.umo || trace.umo || "";
      event.message_type = trace.fields?.message_type || event.message_type || event.umo.split(":")[1] || "";
      event.sender_name = event.sender_name || trace.sender_name || "";
      event.message_outline = event.message_outline || trace.message_outline || "";
      event.platform_id = trace.fields?.platform_id || event.platform_id;
      if (trace.fields?.platform_name) {
        event.platform_name = trace.fields.platform_name;
        event.platform_icon = getPlatformIcon(event.platform_name) || "";
      }
      event.first_time = Math.min(event.first_time, trace.time || event.first_time);
      event.last_time = Math.max(event.last_time, trace.time || event.last_time);
    }
    // Only the inspected trace retains span bodies. Other live packets update
    // bounded list summaries; history is paged independently from SQLite.
    const records = normalized
      ? selectedSpanId.value === trace.span_id || packet.spans ? normalized.records : []
      : [trace];
    for (const record of records) {
      const recordKey = record.record_id || `${trace.span_id}:${record.sequence ?? record.time}:${record.action}`;
      const value = { ...record, key: recordKey, kind: record.kind || record.fields?.kind, fields: record.fields || {} };
      const existing = event.records.findIndex((item) => item.key === recordKey);
      if (existing === -1) event.records.push(value);
      else event.records[existing] = value;
      if (!normalized) {
        if (record.action === "pipeline_end") event.completed = true;
        if (record.status === "error" || record.fields?.status === "error") event.status = "error";
        else if (record.action === "pipeline_end") event.status = event.status === "error" ? "error" : "success";
      }
    }
    event.records.sort((a, b) => (a.time || 0) - (b.time || 0));
  }
  events.value.sort((a, b) => b.first_time - a.first_time);
  if (events.value.length > maxItems) {
    const removed = events.value.splice(maxItems);
    removed.forEach((event) => eventIndex.delete(event.span_id));
  }
}

async function fetchTraceHistory(reset = true, reloadMetadata = false, animateNew = false) {
  const request = ++historyRequest;
  const knownTraceIds = new Set(eventIndex.keys());
  historyBusy.value = true;
  historyError.value = "";
  if (!metadataLoaded || reloadMetadata) {
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
    metadataLoaded = true;
  }
  try {
    const response = await traceApi.history({
      limit: pageSize.value, page: historyPage.value,
      query: searchText.value.trim().slice(0, 256),
      errors: selectedFilters.value.includes("errors"),
      models: selectedFilters.value.includes("models"),
      plugins: selectedFilters.value.includes("plugins"),
    });
    if (request !== historyRequest) return;
    if (response.data?.status !== "ok") throw new Error("Trace history request failed");
    const data = response.data.data;
    const serverTraceIds = new Set((data.traces || []).map((trace) => trace.trace_id));
    const liveTraceIds = new Set(
      [...eventIndex.keys()].filter((traceId) => !knownTraceIds.has(traceId)),
    );
    const keep = new Set([...serverTraceIds, ...liveTraceIds]);
    const newTraceIds = (data.traces || [])
      .map((trace) => trace.trace_id)
      .filter((traceId) => traceId && !eventIndex.has(traceId));
    const isDefaultFirstPage = historyPage.value === 1
      && !normalizedSearch.value
      && selectedFilters.value.length === 0;
    processNewTraces((data.traces || []).map((trace) => ({ trace })));
    events.value = events.value.filter((event) => keep.has(event.span_id));
    if (isDefaultFirstPage) events.value = events.value.slice(0, pageSize.value);
    const indexedIds = new Set(keep);
    if (selectedSpanId.value) indexedIds.add(selectedSpanId.value);
    for (const id of eventIndex.keys()) if (!indexedIds.has(id)) eventIndex.delete(id);
    if (animateNew && isDefaultFirstPage) {
      const animatedTraceIds = [];
      for (const traceId of newTraceIds) {
        if (!eventIndex.has(traceId)) continue;
        animatedTraceIds.push(traceId);
        enteringTraceIds.add(traceId);
        const timer = setTimeout(() => {
          enteringTraceIds.delete(traceId);
          traceEnterTimers.delete(traceId);
        }, 300);
        traceEnterTimers.set(traceId, timer);
      }
      animateTraceListInsertion(animatedTraceIds);
    }
    totalRecords.value = (data.total || 0)
      + [...liveTraceIds].filter((traceId) => !serverTraceIds.has(traceId)).length;
    historyPage.value = data.page || historyPage.value;
    storageWarning.value = Boolean(data.storage?.error || data.storage?.dropped);
    if (reset && selectedSpanId.value) loadTraceDetail(selectedSpanId.value);
  } catch (error) {
    if (request === historyRequest) historyError.value = tm("history.loadFailed");
    console.error("Failed to fetch trace history:", error);
  } finally {
    if (request === historyRequest) {
      historyBusy.value = false;
      loading.value = false;
    }
  }
}

async function loadTraceDetail(traceId) {
  const request = ++detailRequest;
  detailBusy.value = true;
  detailError.value = "";
  try {
    const response = await traceApi.detail(traceId);
    if (request !== detailRequest || selectedSpanId.value !== traceId) return;
    if (response.data?.status !== "ok") throw new Error("Trace detail request failed");
    processNewTraces([response.data.data]);
  } catch (error) {
    if (request === detailRequest && selectedSpanId.value === traceId) detailError.value = tm("history.detailFailed");
    console.error("Failed to fetch trace details:", error);
  } finally {
    if (request === detailRequest) detailBusy.value = false;
  }
}

watch([searchText, selectedFilters], () => {
  historyPage.value = 1;
  if (queryTimer) clearTimeout(queryTimer);
  queryTimer = setTimeout(() => fetchTraceHistory(), 250);
}, { deep: true });

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
    const shouldReconcile = hasOpenedStream
      || retryAttempts.value > 0
      || Boolean(historyError.value);
    connected.value = true;
    retryAttempts.value = 0;
    hasOpenedStream = true;
    if (shouldReconcile) fetchTraceHistory();
  };
  source.onmessage = (event) => {
    if (event.lastEventId) lastEventId.value = event.lastEventId;
    try {
      const payload = JSON.parse(event.data);
      if (payload?.type === "trace") {
        const traceId = payload.trace?.trace_id || payload.span?.trace_id || payload.span_id;
        const wasKnown = eventIndex.has(traceId);
        const canInsertLive = historyPage.value === 1
          && !normalizedSearch.value
          && selectedFilters.value.length === 0;
        if (wasKnown || canInsertLive) {
          processNewTraces([payload]);
          if (!wasKnown && eventIndex.has(traceId)) {
            enteringTraceIds.add(traceId);
            const timer = setTimeout(() => {
              enteringTraceIds.delete(traceId);
              traceEnterTimers.delete(traceId);
            }, 300);
            traceEnterTimers.set(traceId, timer);
            totalRecords.value += 1;
            animateTraceListInsertion([traceId]);
          }
        }
        if (payload.storage_accepted === false) storageWarning.value = true;
      }
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
  const previous = eventIndex.get(previousSpanId);
  if (previous?.model_version === 3 && previousSpanId !== spanId) previous.records = [];
  selectedSpanId.value = spanId;
  if (spanId && eventIndex.get(spanId)?.model_version === 3) loadTraceDetail(spanId);
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
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${month}-${day} ${date.toLocaleTimeString([], { hour12: false })}.${String(date.getMilliseconds()).padStart(3, "0")}`;
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
    return "";
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
  return "";
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
  try {
    return JSON.stringify(safeFields, null, 2);
  } catch {
    return String(fields);
  }
}

/**
 * Slides the current row group down before revealing newly inserted rows.
 *
 * Args:
 *   insertedIds: Trace IDs inserted by the current list update.
 *
 * Returns:
 *   Nothing.
 */
function animateTraceListInsertion(insertedIds) {
  for (const traceId of insertedIds) pendingTraceEntryIds.add(traceId);
  if (traceEntryFrame !== null) return;
  traceEntryFrame = requestAnimationFrame(async () => {
    traceEntryFrame = null;
    const currentIds = [...pendingTraceEntryIds];
    pendingTraceEntryIds.clear();
    const tbody = traceListElement.value?.querySelector(".trace-list-table tbody");
    if (
      !tbody
      || !currentIds.length
      || window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
    ) return;
    const currentTransform = getComputedStyle(tbody).transform;
    const currentY = currentTransform === "none"
      ? 0
      : new DOMMatrixReadOnly(currentTransform).m42;
    await nextTick();
    const insertedHeight = currentIds.reduce((height, traceId) => {
      const row = traceListElement.value?.querySelector(`[data-trace-id="${traceId}"]`);
      return height + (row?.getBoundingClientRect().height || 0);
    }, 0);
    if (!insertedHeight) return;
    traceListAnimation?.cancel();
    tbody.style.transform = `translateY(${currentY - insertedHeight}px)`;
    void tbody.offsetHeight;
    const animation = tbody.animate(
      [
        { transform: `translateY(${currentY - insertedHeight}px)` },
        { transform: "translateY(0)" },
      ],
      {
        duration: 240,
        easing: "cubic-bezier(0.2, 0, 0, 1)",
        fill: "forwards",
      },
    );
    traceListAnimation = animation;
    animation.onfinish = () => {
      if (traceListAnimation !== animation) return;
      tbody.style.removeProperty("transform");
      animation.cancel();
      traceListAnimation = null;
    };
  });
}

onMounted(async () => {
  durationTimer.value = setInterval(() => { clockNow.value = Date.now() / 1000; }, 1000);
  const initialHistory = fetchTraceHistory();
  connectSSE();
  await initialHistory;
});

onBeforeUnmount(() => {
  historyRequest++;
  detailRequest++;
  if (queryTimer) clearTimeout(queryTimer);
  if (durationTimer.value) clearInterval(durationTimer.value);
  eventSource.value?.close();
  if (retryTimer.value) clearTimeout(retryTimer.value);
  for (const timer of traceEnterTimers.values()) clearTimeout(timer);
  traceEnterTimers.clear();
  pendingTraceEntryIds.clear();
  if (traceEntryFrame !== null) cancelAnimationFrame(traceEntryFrame);
  traceListAnimation?.cancel();
  traceListElement.value?.querySelector("tbody")?.style.removeProperty("transform");
});
</script>

<template>
  <v-defaults-provider :defaults="{ VSelect: { menuProps: { contentClass: 'trace-menu' } } }">
  <div class="trace-explorer">
    <div class="trace-explorer-toolbar">
      <v-btn
        class="filter-toggle-btn"
        size="small"
        variant="tonal"
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
        <input v-model="searchText" :placeholder="tm('search', { count: totalRecords })" :aria-label="tm('search', { count: totalRecords })" />
        <button v-if="searchText" type="button" class="icon-button" :aria-label="tm('clearSearch')" @click="clearSearch">
          <X :size="15" aria-hidden="true" />
        </button>
      </div>
      <v-btn
        class="trace-recording-btn"
        size="small"
        variant="tonal"
        :loading="recordingBusy"
        :disabled="recordingBusy"
        :aria-pressed="recordingEnabled"
        :aria-label="tm(recordingEnabled ? 'controls.pause' : 'controls.resume')"
        :title="tm(recordingEnabled ? 'controls.pause' : 'controls.resume')"
        @click="emit('toggle-recording')"
      >
        <component :is="!recordingEnabled ? Play : connected ? Pause : LoaderCircle" :size="16" :class="{ 'trace-connecting-icon': recordingEnabled && !connected }" aria-hidden="true" />
        {{ recordingLabel }}
      </v-btn>
      <v-btn
        class="refresh-button"
        size="small"
        variant="tonal"
        :loading="historyBusy"
        :disabled="historyBusy"
        :aria-label="tm('refresh')"
        :title="tm('refresh')"
        @click="fetchTraceHistory(true, true, true)"
      >
        <RefreshCw :size="16" aria-hidden="true" />
        <span>{{ tm("refresh") }}</span>
      </v-btn>
    </div>

    <v-alert v-if="historyError" type="error" variant="tonal" density="compact">{{ historyError }}</v-alert>
    <v-alert v-if="storageWarning" type="warning" variant="tonal" density="compact">{{ tm("history.storageWarning") }}</v-alert>
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
      <section ref="traceListElement" class="trace-list" :aria-label="tm('traceList')">
        <div v-if="loading" class="trace-empty-state">{{ tm("loading") }}</div>
        <v-data-table-server
          v-else
          class="trace-list-table"
          :headers="traceHeaders"
          :items="traceRows"
          item-value="event.span_id"
          :page="historyPage"
          :items-per-page="pageSize"
          :items-length="totalRecords"
          :items-per-page-options="[25, 50, 100]"
          :items-per-page-text="tm('pagination.perPage')"
          :page-text="tm('pagination.range')"
          :no-data-text="tm('empty')"
          @update:options="({ page, itemsPerPage }) => {
            if (page === historyPage && itemsPerPage === pageSize) return;
            historyPage = itemsPerPage !== pageSize ? 1 : page;
            pageSize = itemsPerPage;
            selectEvent(null);
            fetchTraceHistory();
          }"
          :mobile="false"
          hover
          :row-props="({ item }) => ({
            class: {
              'trace-list-row': true,
              selected: item.event.span_id === selectedSpanId,
              'trace-list-row--entering': enteringTraceIds.has(item.event.span_id),
            },
            'data-trace-id': item.event.span_id,
            'aria-selected': item.event.span_id === selectedSpanId,
            tabindex: 0,
            onAnimationend: (event) => {
              if (event.target !== event.currentTarget) return;
              const timer = traceEnterTimers.get(item.event.span_id);
              if (timer) clearTimeout(timer);
              traceEnterTimers.delete(item.event.span_id);
              enteringTraceIds.delete(item.event.span_id);
            },
            onKeydown: (event) => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                selectEvent(item.event.span_id);
              }
            },
          })"
          @click:row="(_, { item }) => selectEvent(item.event.span_id)"
          fixed-header
          height="100%"
          disable-sort
        >
          <template #header.spans><span :title="tm('columns.spansHint')">Spans</span></template>
          <template #item.status="{ item: { event } }">
            <v-chip size="small" variant="flat" :color="event.status === 'error' ? 'error' : event.status === 'success' ? 'success' : '#1976D2'">{{ statusLabel(event) }}</v-chip>
          </template>
          <template #item.platform="{ item: { event } }">
            <span class="trace-item-platform" :title="event.platform_id || event.platform_name">
              <img v-if="event.platform_icon && !failedPlatformLogos.has(event.platform_icon)" :src="event.platform_icon" :alt="event.platform_name" @error="failedPlatformLogos.add(event.platform_icon)" />
              <Activity v-else :size="16" aria-hidden="true" />
            </span>
          </template>
          <template #item.timestamp="{ item: { event } }">
            <span class="text-no-wrap">{{ formatTime(event.first_time) }}</span>
          </template>
          <template #item.duration="{ item }">
            <span class="text-no-wrap">{{ item.duration }}</span>
          </template>
          <template #item.message="{ item: { event } }">
            <span class="trace-cell-text" :title="event.message_outline || tm('untitled')">{{ event.message_outline || tm("untitled") }}</span>
          </template>
          <template #item.category="{ item: { event } }">
            <div class="trace-category-chips">
              <v-chip v-if="matchesFilter(event, 'models')" size="small" variant="flat" color="#1976D2">{{ tm("classification.agent") }}</v-chip>
              <v-chip v-if="event.has_commands ?? event.records.some((record) => record.kind === 'plugin_handler' && record.fields.handler_category === 'command')" size="small" variant="flat" color="#2E7D32">{{ tm("classification.command") }}</v-chip>
              <v-chip v-if="event.message_type === 'GroupMessage'" size="small" variant="tonal">{{ tm("classification.group") }}</v-chip>
              <v-chip v-else-if="event.message_type === 'FriendMessage'" size="small" variant="tonal">{{ tm("classification.private") }}</v-chip>
            </div>
          </template>
          <template #item.umo="{ item: { event } }">
            <v-tooltip :text="event.umo" location="top" content-class="trace-tooltip">
              <template #activator="{ props }">
                <span v-bind="props" class="trace-cell-text" :class="{ 'trace-hover-name': umoNames[event.umo] && umoNames[event.umo] !== event.umo }">{{ umoNames[event.umo] || event.umo || "-" }}</span>
              </template>
            </v-tooltip>
          </template>
          <template #item.sender="{ item: { event } }">
            <span class="trace-cell-text" :title="event.sender_name">{{ event.sender_name || "-" }}</span>
          </template>
          <template #item.spans="{ item }">
            <span :title="tm('columns.spansHint')">{{ item.spans }}</span>
          </template>
        </v-data-table-server>
      </section>

      <main v-if="selectedEvent" class="trace-detail" @keydown.esc.stop="selectEvent(null)">
        <div class="trace-detail-header">
          <div class="trace-detail-summary">
            <div class="trace-detail-kicker"><span class="trace-status-badge" :class="statusClass(selectedEvent)">{{ statusLabel(selectedEvent) }}</span><span>{{ shortSpan(selectedEvent.span_id) }}</span></div>
            <TraceMessagePreview :key="selectedEvent.span_id" class="trace-message-title" tag="h2" :lines="2" :text="selectedEvent.message_outline || tm('untitled')" />
            <div class="trace-detail-meta">
            <p class="trace-detail-meta-row" aria-label="UMO">
              <Hash :size="14" aria-hidden="true" />
              <v-tooltip :text="selectedEvent.umo" location="top" content-class="trace-tooltip">
                <template #activator="{ props }">
                  <span v-bind="props" :class="{ 'trace-hover-name': umoNames[selectedEvent.umo] && umoNames[selectedEvent.umo] !== selectedEvent.umo }">{{ umoNames[selectedEvent.umo] || selectedEvent.umo || "-" }}</span>
                </template>
              </v-tooltip>
            </p>
            <p class="trace-detail-meta-row" :aria-label="tm('columns.sender')">
              <UserRound :size="14" aria-hidden="true" />
              <span>{{ selectedEvent.sender_name || "-" }}</span>
            </p>
            </div>
          </div>
          <div class="trace-detail-actions">
            <div class="trace-detail-time">{{ formatTime(selectedEvent.first_time) }}</div>
            <button type="button" class="icon-button" :aria-label="tm('closeDetails')" @click="selectEvent(null)"><X :size="17" aria-hidden="true" /></button>
          </div>
        </div>

        <v-alert v-if="selectedEvent.truncated" class="mt-3" type="warning" variant="tonal" density="compact">{{ tm("history.truncated") }}</v-alert>
        <div v-if="detailBusy" class="trace-empty-state" aria-live="polite"><LoaderCircle :size="20" class="trace-connecting-icon" /><span>{{ tm("loading") }}</span></div>
        <v-alert v-if="detailError" class="mt-3" type="error" variant="tonal" density="compact">
          {{ detailError }}
          <v-btn size="small" variant="text" @click="loadTraceDetail(selectedSpanId)">{{ tm("refresh") }}</v-btn>
        </v-alert>
        <div v-if="!detailBusy && !detailError" class="trace-stat-grid" :class="{ 'has-tokens': matchesFilter(selectedEvent, 'models') }">
          <div class="trace-stat"><Clock3 :size="15" /><span>{{ tm("duration") }}</span><strong>{{ selectedStats.duration }}</strong></div>
          <div class="trace-stat"><PlugZap :size="15" /><span>{{ tm("handlers") }}</span><strong>{{ selectedStats.handlers }}</strong></div>
          <div class="trace-stat"><Send :size="15" /><span>{{ tm("responses") }}</span><strong>{{ selectedStats.responses }}</strong></div>
          <v-tooltip v-if="matchesFilter(selectedEvent, 'models')" location="top" content-class="trace-tooltip">
            <template #activator="{ props }">
              <div v-bind="props" class="trace-stat" tabindex="0"><Hash :size="15" /><span>{{ tm("tokens.title") }}</span><strong>{{ selectedTokenUsage ? selectedTokenUsage.total >= 1000000 ? (selectedTokenUsage.total / 1000000).toFixed(2) + " M" : (selectedTokenUsage.total / 1000).toFixed(2) + " k" : "—" }}</strong></div>
            </template>
            <div class="trace-token-breakdown">{{ selectedTokenUsage ? tm('tokens.breakdown', { input: selectedTokenUsage.input.toLocaleString(), output: selectedTokenUsage.output.toLocaleString(), cached: selectedTokenUsage.cached.toLocaleString() }) : tm('tokens.unavailable') }}</div>
          </v-tooltip>
        </div>

        <div class="trace-timeline">
          <div v-for="(row, index) in timelineRows" :key="row.key" class="timeline-record" :class="{ 'timeline-group': row.group, 'timeline-nested': row.nested, 'timeline-agent': row.agentId }" :style="{ '--timeline-depth': row.depth }">
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
                type="button"
                class="timeline-row-toggle"
                :aria-expanded="row.expanded"
                :aria-label="row.agentId ? tm('compact.toggleAgent', { action: tm(row.expanded ? 'collapse' : 'expand') }) : undefined"
                @click="row.group
                  ? row.expanded ? expandedGroups.delete(row.group.key) : expandedGroups.add(row.group.key)
                  : row.agentId
                    ? row.expanded ? expandedAgents.delete(row.agentId) : expandedAgents.add(row.agentId)
                    : row.expanded ? expandedDetails.delete(row.record.key) : expandedDetails.add(row.record.key)"
              >
                <div class="timeline-heading">
                  <span class="timeline-title">
                    <strong>{{ row.record.kind === 'plugin_handler' ? tm('compact.pluginHandler')
                      : row.record.action === 'agent_start' ? tm('compact.agentExecution')
                      : row.record.action === 'event_received' ? tm('actions.eventReceived')
                      : recordLabel(row.record, Boolean(row.group)) }}</strong>
                    <template v-if="row.agentInfo">
                      <v-tooltip v-for="model in row.agentInfo.models" :key="model.id + ':' + model.provider" location="top" content-class="trace-tooltip">
                        <template #activator="{ props }">
                          <v-chip v-bind="props" class="timeline-metadata-chip" size="x-small" variant="tonal"><template #prepend><Box :size="12" aria-hidden="true" /></template>{{ model.id }}</v-chip>
                        </template>
                        <div>{{ model.id }}</div>
                        <div v-if="model.provider">{{ tm("chips.provider", { id: model.provider }) }}</div>
                      </v-tooltip>
                      <v-chip v-for="persona in row.agentInfo.personas" :key="persona" class="timeline-metadata-chip" size="x-small" variant="tonal" :title="tm('chips.persona', { id: persona })"><template #prepend><Heart :size="12" aria-hidden="true" /></template>{{ persona }}</v-chip>
                      <v-chip v-if="row.agentInfo.toolCalls" class="timeline-metadata-chip" size="x-small" variant="tonal"><template #prepend><Wrench :size="12" aria-hidden="true" /></template>{{ tm("chips.toolCalls", { count: row.agentInfo.toolCalls }) }}</v-chip>
                    </template>
                    <v-chip v-if="row.category" size="x-small" variant="tonal">{{ tm(`handlerCategories.${row.category}`) }}</v-chip>
                    <span v-if="row.group" class="timeline-group-count">{{ tm("groups.count", { count: row.group.records.length }) }}</span>
                    <span v-if="row.record.action === 'agent_start'" class="timeline-duration">{{ formatDuration(row.record.completed ? row.record.fields.duration_ms || 0 : Math.max(0, (clockNow - row.record.time) * 1000)) }}</span>
                    <span v-if="row.errors" class="timeline-group-errors">{{ tm("groups.errors", { count: row.errors }) }}</span>
                  </span>
                  <span class="timeline-heading-actions">
                    <time :title="formatTime(row.record.time)">+{{ formatDuration(Math.max(0, (row.record.time - selectedEvent.first_time) * 1000)) }}</time>
                    <ChevronDown :size="14" class="timeline-expansion-icon" :class="{ 'is-collapsed': !row.expanded }" aria-hidden="true" />
                  </span>
                </div>
              </button>
              <div v-if="row.group" class="timeline-subtitle timeline-group-summary">
                  <v-chip v-if="row.plugins" class="timeline-metadata-chip" size="x-small" variant="tonal" :title="row.plugins"><template #prepend><Puzzle :size="12" aria-hidden="true" /></template>{{ row.plugins }}</v-chip>
                  <v-chip v-for="label in row.metadata" :key="label" class="timeline-metadata-chip" size="x-small" variant="tonal">{{ label }}</v-chip>
              </div>
              <template v-else v-for="record in [row.record]" :key="record.key">
              <div v-if="record.kind === 'plugin_handler'" class="timeline-subtitle">
                <v-tooltip :text="record.fields.plugin" location="top" content-class="trace-tooltip">
                  <template #activator="{ props }">
                    <v-chip v-bind="props" class="trace-hover-name timeline-metadata-chip" size="x-small" variant="tonal"><template #prepend><Puzzle :size="12" aria-hidden="true" /></template>{{ record.fields.plugin_display_name || record.fields.plugin || "Plugin" }}</v-chip>
                  </template>
                </v-tooltip>
                ·
                <v-tooltip location="top" content-class="trace-tooltip" @update:model-value="(open) => open && loadHandlerDescription(record)">
                  <template #activator="{ props }">
                    <span v-bind="props" class="trace-hover-name" tabindex="0">{{ record.fields.handler }}</span>
                  </template>
                  <div class="trace-handler-description">
                    <template v-if="!handlerDetails[record.fields.plugin] || handlerDetails[record.fields.plugin].status === 'loading'">{{ tm("handlerDescription.loading") }}</template>
                    <template v-else-if="handlerDetails[record.fields.plugin].status === 'error'">{{ tm("handlerDescription.loadFailed") }}</template>
                    <template v-else>{{ handlerDetails[record.fields.plugin].descriptions[record.fields.handler_full_name || record.fields.handler] || tm("handlerDescription.empty") }}</template>
                  </div>
                </v-tooltip>
                <span v-if="record.fields.handler_type && record.fields.handler_type !== 'AdapterMessageEvent'"> · {{ record.fields.handler_type }}</span>
                <span v-if="record.fields.duration_ms != null"> · {{ formatDuration(record.fields.duration_ms) }}</span>
              </div>
              <div v-else-if="record.kind === 'response'" class="timeline-subtitle">
                <TraceMessagePreview v-if="record.fields.message" class="trace-response-outline" :text="record.fields.message" />
              </div>
              <div v-else-if="record.action === 'agent_start'" class="timeline-subtitle">
                <v-chip class="timeline-metadata-chip" size="x-small" variant="tonal">{{ recordSubtitle(record) }}</v-chip>
              </div>
              <div v-else-if="record.action === 'event_received'" class="timeline-subtitle">
                <v-chip v-if="record.fields.platform_id" class="timeline-metadata-chip" size="x-small" variant="tonal" :title="record.fields.platform_id">{{ record.fields.platform_id }}</v-chip>
                <TraceMessagePreview v-if="record.fields.message" class="trace-response-outline" :text="record.fields.message" />
              </div>
              <div v-else-if="recordSubtitle(record)" class="timeline-subtitle">{{ recordSubtitle(record) }}</div>
              <details v-if="row.agentId && row.expanded" class="timeline-fields"><summary>{{ tm("compact.rawData") }}</summary><pre>{{ formatFields(record.model || record.fields) }}</pre></details>
              <div v-else-if="row.detailsExpanded" class="timeline-fields"><pre>{{ formatFields(record.model || record.fields) }}</pre></div>
              </template>
            </div>
          </div>
        </div>
      </main>
    </div>
    </div>
  </div>
  </v-defaults-provider>
</template>

<style scoped>
.trace-detail-meta { display: grid; gap: 5px; }
.trace-detail-meta-row { align-items: flex-start; display: flex; gap: 7px; }
.trace-detail-meta-row > svg { flex: 0 0 auto; margin-top: 1px; }
.trace-detail-meta-row > span { min-width: 0; }
.trace-explorer :deep(button), .trace-explorer :deep(input), .trace-explorer :deep(select), .trace-explorer :deep(textarea), .trace-explorer :deep(.v-btn), .trace-explorer :deep(.v-chip), .trace-explorer :deep(.v-field), .trace-explorer :deep(.v-table) { font-family: inherit; }
:global(.trace-tooltip) { font-family: system-ui, sans-serif; }
:global(.trace-menu) { font-family: system-ui, sans-serif; }
.trace-response-outline { background: rgba(var(--v-theme-on-surface), 0.035); border-radius: 6px; color: rgb(var(--v-theme-on-surface)); font-size: 12px; margin-top: 7px; overflow-wrap: anywhere; padding: 8px 10px; white-space: pre-wrap; }
.trace-hover-name { text-decoration-line: underline; text-decoration-style: dotted; text-underline-offset: 4px; cursor: help; }
.trace-handler-description { max-width: min(400px, calc(100vw - 48px)); max-height: 320px; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; }
.timeline-plugin-logo { border-radius: 50%; height: 19px; object-fit: contain; width: 19px; }
.timeline-platform-logo { height: 19px; object-fit: contain; width: 19px; }
.timeline-icon-stack { display: block; height: 26px; position: relative; width: 26px; }
.timeline-icon-stack.is-stacked { margin-top: 6px; }
.is-stacked .timeline-icon { background: linear-gradient(var(--timeline-icon-background), var(--timeline-icon-background)), rgb(var(--v-theme-surface)); left: calc(var(--stack-index) * 3px); position: absolute; top: calc(var(--stack-index) * -3px); z-index: calc(3 - var(--stack-index)); }
.timeline-row-toggle { background: transparent; border: 0; border-radius: 4px; color: inherit; cursor: pointer; display: block; min-height: 28px; padding: 0; text-align: left; width: 100%; }
.timeline-row-toggle:hover { background: rgba(var(--v-theme-on-surface), 0.035); }
.timeline-row-toggle:focus-visible { outline: 2px solid rgb(var(--v-theme-primary)); outline-offset: 3px; }
.timeline-title { align-items: center; display: flex; flex-wrap: wrap; gap: 5px 7px; min-width: 0; }
.timeline-heading-actions { align-items: center; display: inline-flex; flex: 0 0 auto; gap: 10px; }
.timeline-duration { color: var(--trace-muted); font-size: 11px; font-variant-numeric: tabular-nums; }
.timeline-group-count { background: rgba(var(--v-theme-on-surface), 0.06); border-radius: 4px; color: var(--trace-muted); font-size: 10px; padding: 1px 5px; white-space: nowrap; }
.timeline-group-errors { color: rgb(var(--v-theme-error)); font-size: 11px; white-space: nowrap; }
.timeline-group-summary { align-items: center; display: flex; flex-wrap: wrap; gap: 6px 10px; }
.timeline-metadata-chip { max-width: 100%; vertical-align: middle; }
.timeline-metadata-chip :deep(.v-chip__prepend) { margin-inline-end: 5px; }
.timeline-title .timeline-metadata-chip { max-width: 200px; }
.timeline-metadata-chip :deep(.v-chip__content) { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.timeline-expansion-icon { color: var(--trace-muted); transition: transform 0.15s ease; }
.timeline-expansion-icon.is-collapsed { transform: rotate(-90deg); }
.trace-explorer { --trace-border: rgba(var(--v-theme-on-surface), 0.1); --trace-muted: rgba(var(--v-theme-on-surface), 0.58); --trace-control-background: rgba(var(--v-theme-on-surface), 0.06); font-family: system-ui, sans-serif; background: transparent; border: 0; border-radius: 0; display: flex; flex-direction: column; height: 100%; min-height: 0; overflow: hidden; }
.trace-explorer-toolbar { align-items: center; border-bottom: 1px solid var(--trace-border); display: flex; gap: 10px; min-height: 50px; padding: 8px 12px; }
.trace-explorer-toolbar :deep(.v-btn) { background: var(--trace-control-background); height: 36px; }
.trace-explorer-toolbar :deep(.v-btn__underlay) { display: none; }
.filter-toggle-btn { flex: 0 0 auto; }
.trace-explorer-toolbar :deep(.v-btn__content) { gap: 6px; }
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
.trace-search { align-items: center; background: var(--trace-control-background); border: 1px solid transparent; border-radius: 7px; color: var(--trace-muted); display: flex; flex: 1; gap: 8px; height: 36px; min-width: 0; padding: 0 10px; }
.trace-search:focus-within { border-color: rgba(var(--v-theme-primary), 0.6); }
.trace-search input { background: transparent; border: 0; color: rgb(var(--v-theme-on-surface)); font-size: 12px; min-width: 0; outline: 0; width: 100%; }
.icon-button { align-items: center; background: transparent; border: 0; border-radius: 5px; color: var(--trace-muted); cursor: pointer; display: inline-flex; justify-content: center; padding: 4px; }
.icon-button:hover { background: rgba(var(--v-theme-on-surface), 0.08); color: rgb(var(--v-theme-on-surface)); }
.trace-recording-btn { flex: 0 0 auto; white-space: nowrap; }
.refresh-button { flex: 0 0 auto; white-space: nowrap; }
.trace-connecting-icon { animation: trace-connecting-spin 1s linear infinite; }
@keyframes trace-connecting-spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .trace-connecting-icon { animation: none; } }
.trace-explorer-body { display: flex; flex: 1; min-height: 0; min-width: 0; overflow: hidden; position: relative; }
.trace-list { display: flex; flex-direction: column; flex: 1; isolation: isolate; min-height: 0; min-width: 0; overflow: hidden; }
.has-detail .trace-list { border-right: 1px solid var(--trace-border); }
.trace-list-table { --v-table-header-height: 40px; background: transparent; border-radius: 0; flex: 1; min-height: 0; height: 100%; }
.trace-list-table :deep(.v-table__wrapper) { overflow-anchor: none; scrollbar-gutter: stable; }
.trace-list-table :deep(th), .trace-list-table :deep(td) { font-size: 13px; }
.trace-list-table :deep(.trace-list-row--entering) { animation: trace-row-enter 240ms cubic-bezier(0.2, 0, 0, 1) both; }
@keyframes trace-row-enter { from { opacity: 0; } to { opacity: 1; } }
.trace-list-table :deep(.trace-list-row.selected) { background: rgba(var(--v-theme-primary), 0.1); }
.trace-list-table :deep(.trace-list-row:focus-visible) { outline: 2px solid rgb(var(--v-theme-primary)); outline-offset: -2px; }
.trace-cell-text { display: block; max-width: 320px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.trace-category-chips { align-items: center; display: flex; flex-wrap: nowrap; gap: 6px; }
.trace-item-platform { align-items: center; color: var(--trace-muted); display: inline-flex; height: 20px; justify-content: center; vertical-align: middle; width: 20px; }
.trace-item-platform img { height: 20px; object-fit: contain; width: 20px; }
.trace-detail { background: rgb(var(--v-theme-surface)); flex: 0 0 58%; max-width: 850px; min-height: 0; min-width: 360px; overflow: auto; padding: 18px 22px 28px; }
.trace-detail-actions { align-items: center; display: flex; flex: 0 0 auto; gap: 8px; }
.trace-detail-header { align-items: flex-start; display: flex; gap: 16px; justify-content: space-between; }
.trace-detail-kicker { align-items: center; color: var(--trace-muted); display: flex; font-size: 10px; gap: 8px; text-transform: uppercase; }
.trace-detail-summary { flex: 1; min-width: 0; } .trace-message-title { font-size: 17px; font-weight: 650; margin: 8px 0 4px; } .trace-detail-header p { color: var(--trace-muted); font-size: 11px; margin: 0; overflow-wrap: anywhere; }
.trace-detail-time { color: var(--trace-muted); font-family: inherit; font-size: 11px; white-space: nowrap; }
.trace-status-badge { border-radius: 999px; font-size: 10px; padding: 3px 7px; text-transform: none; } .trace-status-badge.is-live { background: rgba(25, 118, 210, 0.14); color: #1976D2; } .trace-status-badge.is-success { background: rgba(34, 197, 94, 0.14); color: #22c55e; } .trace-status-badge.is-error { background: rgba(239, 68, 68, 0.14); color: #ef4444; }
.trace-stat-grid { display: grid; gap: 8px; grid-template-columns: repeat(3, minmax(0, 1fr)); margin: 18px 0 22px; }
.trace-stat-grid.has-tokens { grid-template-columns: repeat(4, minmax(0, 1fr)); }
.trace-token-breakdown { white-space: pre-line; }
.trace-stat { background: rgba(var(--v-theme-on-surface), 0.04); border: 0; border-radius: 8px; display: grid; gap: 4px; grid-template-columns: 16px 1fr; padding: 9px 10px; } .trace-stat svg { color: var(--trace-muted); grid-row: span 2; margin-top: 2px; } .trace-stat span { color: var(--trace-muted); font-size: 10px; } .trace-stat strong { font-size: 13px; font-weight: 650; }
.trace-timeline { max-width: 900px; } .timeline-record { display: grid; gap: 12px; grid-template-columns: 26px minmax(0, 1fr); margin-left: calc(min(var(--timeline-depth, 0), 3) * 18px); min-height: 44px; padding-top: 8px; } .timeline-rail { align-items: center; display: flex; flex-direction: column; }
.timeline-icon { --timeline-icon-background: rgba(var(--v-theme-on-surface), 0.035); align-items: center; background: var(--timeline-icon-background); border: 1px solid var(--trace-border); border-radius: 50%; display: inline-flex; height: 26px; justify-content: center; width: 26px; z-index: 1; } .timeline-icon.is-system { color: var(--trace-muted); } .timeline-icon.is-plugin, .timeline-icon.is-agent { color: rgb(var(--v-theme-primary)); } .timeline-icon.is-response { color: rgb(var(--v-theme-success)); } .timeline-icon.is-error { --timeline-icon-background: rgba(var(--v-theme-error), 0.08); color: rgb(var(--v-theme-error)); }
.timeline-line { background: var(--trace-border); flex: 1; width: 1px; } .timeline-content { min-width: 0; padding-bottom: 10px; } .timeline-heading { align-items: center; display: flex; gap: 10px; justify-content: space-between; } .timeline-heading strong { font-size: 13px; font-weight: 600; overflow-wrap: anywhere; } .timeline-heading time { color: var(--trace-muted); font-family: inherit; font-size: 11px; font-variant-numeric: tabular-nums; white-space: nowrap; } .timeline-subtitle { color: var(--trace-muted); font-size: 11px; line-height: 1.5; margin-top: 5px; overflow-wrap: anywhere; }
.timeline-fields { margin-top: 7px; } .timeline-fields summary { color: var(--trace-muted); cursor: pointer; font-size: 11px; } .timeline-fields pre { background: rgba(var(--v-theme-on-surface), 0.035); border-radius: 6px; color: var(--trace-muted); font-size: 11px; line-height: 1.5; margin: 6px 0 0; max-height: 280px; overflow: auto; padding: 10px; white-space: pre-wrap; word-break: break-word; }
@media (pointer: coarse) { .timeline-row-toggle { min-height: 44px; } }
@media (prefers-reduced-motion: reduce) {
  .timeline-expansion-icon { transition: none; }
  .trace-list-table :deep(.trace-list-row--entering) { animation: none; }
}
.trace-empty-state { align-items: center; color: var(--trace-muted); display: flex; flex-direction: column; font-size: 12px; gap: 8px; justify-content: center; min-height: 180px; }
@media (max-width: 1100px) { .trace-detail { border-left: 1px solid var(--trace-border); bottom: 0; box-shadow: -8px 0 24px rgba(0, 0, 0, 0.12); max-width: none; min-width: 0; position: absolute; right: 0; top: 0; width: min(760px, 90%); z-index: 1; } }
@media (max-width: 900px) { .trace-filter-panel { bottom: 0; box-shadow: 8px 0 24px rgba(0, 0, 0, 0.18); left: 0; max-width: 85%; position: absolute; top: 0; width: 220px; z-index: 3; } .trace-filter-backdrop { background: rgba(var(--v-theme-on-surface), 0.12); border: 0; display: block; inset: 0; position: absolute; z-index: 2; } .trace-detail { padding: 15px; } .trace-stat-grid, .trace-stat-grid.has-tokens { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 640px) { .trace-explorer-toolbar { flex-wrap: wrap; } .filter-toggle-btn { order: 1; } .trace-search { flex: 1 1 160px; max-width: none; order: 1; } .trace-recording-btn { order: 2; } .refresh-button { margin-left: auto; order: 2; } .trace-detail { width: 100%; } .trace-detail-time { display: none; } }
</style>
