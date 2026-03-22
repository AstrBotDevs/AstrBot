<script setup>
import TraceDisplayer from "@/components/shared/TraceDisplayer.vue";
import SpanTree from "@/components/shared/SpanTree.vue";
import SpanDetail from "@/components/shared/SpanDetail.vue";
import { useModuleI18n } from "@/i18n/composables";
import { ref, onMounted, computed } from "vue";
import axios from "axios";

const { tm } = useModuleI18n("features/trace");

const traceEnabled = ref(false);
const loading = ref(false);
const traceDisplayerKey = ref(0);
const excludedTypes = ref([]); // Inverse filter: items in this list are hidden
const expandSignal = ref(0);
const collapseSignal = ref(0);

const SPAN_TYPES = [
  { id: "pipeline_stage", label: "Pipeline", color: "#78909c" },
  { id: "llm_agent", label: "Agent", color: "#7c4dff" },
  { id: "llm_call", label: "LLM", color: "#ab47bc" },
  { id: "tool_call", label: "Tool", color: "#ef6c00" },
  { id: "plugin_handler", label: "Plugin", color: "#00897b" },
];

function toggleType(typeId) {
  const idx = excludedTypes.value.indexOf(typeId);
  if (idx > -1) excludedTypes.value.splice(idx, 1);
  else excludedTypes.value.push(typeId);
}

// two-panel state
const selectedTraceId = ref(null);
const traceDetail = ref(null);
const detailLoading = ref(false);
const selectedSpan = ref(null);
const detailDrawerOpen = ref(false);
const clearDialog = ref(false);
const clearLoading = ref(false);
const listPanelWidth = ref(380);
const treePanelWidth = ref(300);

const startDraggingList = (e) => {
  const startX = e.clientX;
  const startWidth = listPanelWidth.value;
  const onMouseMove = (ee) => {
    listPanelWidth.value = Math.max(
      200,
      Math.min(800, startWidth + (ee.clientX - startX)),
    );
  };
  const onMouseUp = () => {
    window.removeEventListener("mousemove", onMouseMove);
    window.removeEventListener("mouseup", onMouseUp);
    document.body.style.cursor = "";
  };
  window.addEventListener("mousemove", onMouseMove);
  window.addEventListener("mouseup", onMouseUp);
  document.body.style.cursor = "col-resize";
};

const startDraggingTree = (e) => {
  const startX = e.clientX;
  const startWidth = treePanelWidth.value;
  const onMouseMove = (ee) => {
    treePanelWidth.value = Math.max(
      150,
      Math.min(600, startWidth + (ee.clientX - startX)),
    );
  };
  const onMouseUp = () => {
    window.removeEventListener("mousemove", onMouseMove);
    window.removeEventListener("mouseup", onMouseUp);
    document.body.style.cursor = "";
  };
  window.addEventListener("mousemove", onMouseMove);
  window.addEventListener("mouseup", onMouseUp);
  document.body.style.cursor = "col-resize";
};

const fetchTraceSettings = async () => {
  try {
    const res = await axios.get("/api/trace/settings");
    if (res.data?.status === "ok") {
      traceEnabled.value = res.data.data?.trace_enable ?? false;
    }
  } catch (err) {
    console.error("Failed to fetch trace settings:", err);
  }
};

const updateTraceSettings = async () => {
  loading.value = true;
  try {
    await axios.post("/api/trace/settings", {
      trace_enable: traceEnabled.value,
    });
    traceDisplayerKey.value += 1;
  } catch (err) {
    console.error("Failed to update trace settings:", err);
  } finally {
    loading.value = false;
  }
};

const selectTrace = async (traceId) => {
  if (selectedTraceId.value === traceId) {
    // deselect on second click
    selectedTraceId.value = null;
    traceDetail.value = null;
    selectedSpan.value = null;
    detailDrawerOpen.value = false;
    return;
  }
  selectedTraceId.value = traceId;
  selectedSpan.value = null;
  detailDrawerOpen.value = true;
  traceDetail.value = null;
  detailLoading.value = true;
  try {
    const res = await axios.get("/api/trace/detail", {
      params: { trace_id: traceId },
    });
    if (res.data?.status === "ok") {
      traceDetail.value = res.data.data;
    }
  } catch (err) {
    console.error("Failed to load trace detail:", err);
  } finally {
    detailLoading.value = false;
  }
};

const closeDetail = () => {
  detailDrawerOpen.value = false;
  selectedTraceId.value = null;
  traceDetail.value = null;
  selectedSpan.value = null;
};

const clearAllTraces = async () => {
  clearLoading.value = true;
  try {
    await axios.delete("/api/trace/clear");
    traceDisplayerKey.value += 1;
    clearDialog.value = false;
    closeDetail();
  } catch (err) {
    console.error("Failed to clear traces:", err);
  } finally {
    clearLoading.value = false;
  }
};

function formatTime(ts) {
  if (!ts) return "-";
  return new Date(ts * 1000).toLocaleString();
}

function formatDuration(ms) {
  if (ms == null) return "-";
  if (ms < 1000) return `${ms.toFixed(0)}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

onMounted(() => {
  fetchTraceSettings();
});

const filteredSpans = computed(() => {
  if (!traceDetail.value?.spans) return null;
  // If nothing is excluded, return everything
  if (excludedTypes.value.length === 0) return traceDetail.value.spans;

  const filterRecursive = (span) => {
    // Process children first
    const newChildren = (span.children || [])
      .map(filterRecursive)
      .filter((c) => c !== null);

    const isExcluded = excludedTypes.value.includes(span.span_type);

    // Keep node if:
    // 1. Its type is NOT excluded
    // 2. OR it has visible children
    // 3. OR it is the root node
    if (!isExcluded || newChildren.length > 0 || span.span_type === "root") {
      return {
        ...span,
        children: newChildren,
        isFiltered: isExcluded && span.span_type !== "root", // root is never "filtered"
      };
    }
    return null;
  };

  return filterRecursive(traceDetail.value.spans);
});
</script>

<template>
  <div class="trace-page">
    <!-- ── header bar ── -->
    <div class="trace-header">
      <div class="trace-info">
        <v-icon size="small" color="info" class="mr-2"
          >mdi-information-outline</v-icon
        >
        <span class="trace-hint">{{ tm("hint") }}</span>
      </div>
      <div class="trace-controls">
        <v-btn
          size="small"
          variant="tonal"
          color="error"
          prepend-icon="mdi-delete-outline"
          @click="clearDialog = true"
          >{{ tm("clearAll") }}</v-btn
        >
        <v-switch
          v-model="traceEnabled"
          :loading="loading"
          :disabled="loading"
          color="primary"
          hide-details
          density="compact"
          class="ml-2"
          @update:model-value="updateTraceSettings"
        >
          <template #label>
            <span class="switch-label">{{
              traceEnabled ? tm("recording") : tm("paused")
            }}</span>
          </template>
        </v-switch>
      </div>
    </div>

    <!-- ── main content: list + detail panel ── -->
    <div class="trace-main">
      <!-- list panel -->
      <div
        class="trace-list-panel"
        :class="{ 'panel-shrunk': detailDrawerOpen }"
        :style="
          detailDrawerOpen ? { width: listPanelWidth + 'px', flex: 'none' } : {}
        "
      >
        <TraceDisplayer
          :key="traceDisplayerKey"
          :selected-trace-id="selectedTraceId"
          @select-trace="selectTrace"
        />
      </div>

      <div
        v-if="detailDrawerOpen"
        class="resizer-v"
        @mousedown="startDraggingList"
      />

      <!-- detail panel -->
      <transition name="slide-detail">
        <div v-if="detailDrawerOpen" class="trace-detail-panel">
          <!-- detail header -->
          <div class="detail-panel-header">
            <template v-if="traceDetail && !detailLoading">
              <div class="detail-hd-main">
                <div class="detail-hd-top">
                  <span class="detail-hd-sender">{{
                    traceDetail.sender_name || "Unknown"
                  }}</span>
                  <span
                    v-if="traceDetail.message_outline"
                    class="detail-hd-outline"
                  >
                    {{ traceDetail.message_outline }}
                  </span>
                </div>
                <div class="detail-hd-badges">
                  <v-chip
                    v-if="traceDetail.status !== 'ok'"
                    size="x-small"
                    :color="
                      traceDetail.status === 'ok'
                        ? 'success'
                        : traceDetail.status === 'error'
                        ? 'error'
                        : 'warning'
                    "
                    variant="tonal"
                    rounded="pill"
                    >{{ traceDetail.status }}</v-chip
                  >
                  <span class="detail-badge">{{
                    formatDuration(traceDetail.duration_ms)
                  }}</span>
                  <span class="detail-badge">{{
                    formatTime(traceDetail.started_at)
                  }}</span>
                  <div
                    v-if="traceDetail.total_input_tokens"
                    class="detail-tokens-tag"
                  >
                    <v-icon size="11" color="grey" class="mr-1"
                      >mdi-arrow-up-bold-outline</v-icon
                    >
                    <span>{{ traceDetail.total_input_tokens }}</span>
                    <v-icon size="11" color="grey" class="ml-2 mr-1"
                      >mdi-arrow-down-bold-outline</v-icon
                    >
                    <span>{{ traceDetail.total_output_tokens }}</span>
                    <span class="ml-1">tokens</span>
                  </div>
                </div>
              </div>
            </template>
            <template v-else>
              <span class="detail-panel-title">Trace Detail</span>
            </template>
            <v-spacer />
            <v-btn
              icon="mdi-close"
              size="small"
              variant="text"
              @click="closeDetail"
            />
          </div>

          <!-- loading -->
          <div v-if="detailLoading" class="detail-loading">
            <v-progress-circular indeterminate color="primary" size="32" />
          </div>

          <template v-else-if="traceDetail">
            <!-- two-sub-panel: span tree + span detail -->
            <div class="detail-body">
              <!-- span tree (left) -->
              <div
                class="span-tree-panel"
                :style="{ width: treePanelWidth + 'px', flex: 'none' }"
              >
                <div class="span-tree-header">
                  <div class="st-header-top">
                    <span>Spans</span>
                    <div class="st-header-actions">
                      <v-btn
                        icon="mdi-unfold-more-horizontal"
                        size="x-small"
                        variant="text"
                        density="compact"
                        @click="expandSignal++"
                      />
                      <v-btn
                        icon="mdi-unfold-less-horizontal"
                        size="x-small"
                        variant="text"
                        density="compact"
                        @click="collapseSignal++"
                      />
                    </div>
                  </div>
                  <div class="span-type-filters">
                    <div
                      v-for="t in SPAN_TYPES"
                      :key="t.id"
                      class="filter-chip"
                      :class="{ inactive: excludedTypes.includes(t.id) }"
                      :style="{ '--chip-color': t.color }"
                      @click="toggleType(t.id)"
                    >
                      {{ t.label }}
                    </div>
                  </div>
                </div>
                <div class="span-tree-scroll">
                  <SpanTree
                    v-if="filteredSpans"
                    :span="filteredSpans"
                    :depth="0"
                    :tree-lines="[]"
                    :is-last="true"
                    :selected-span-id="selectedSpan?.span_id"
                    :expand-signal="expandSignal"
                    :collapse-signal="collapseSignal"
                    @select="selectedSpan = $event"
                  />
                  <div
                    v-else-if="excludedTypes.length > 0"
                    class="no-match-hint"
                  >
                    No matching spans
                  </div>
                </div>
              </div>

              <div class="resizer-v" @mousedown="startDraggingTree" />

              <!-- span detail (right) -->
              <div class="span-detail-panel">
                <SpanDetail :span="selectedSpan" />
              </div>
            </div>
          </template>

          <div v-else class="detail-loading">
            <v-icon color="grey" size="32">mdi-alert-circle-outline</v-icon>
            <div
              class="mt-2"
              style="
                font-size: 13px;
                color: rgba(var(--v-theme-on-surface), 0.4);
              "
            >
              Failed to load trace
            </div>
          </div>
        </div>
      </transition>
    </div>

    <!-- clear confirm dialog -->
    <v-dialog v-model="clearDialog" max-width="400">
      <v-card>
        <v-card-title>{{ tm("clearAll") }}</v-card-title>
        <v-card-text>{{ tm("clearConfirm") }}</v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="clearDialog = false">{{
            tm("cancel")
          }}</v-btn>
          <v-btn
            color="error"
            variant="tonal"
            :loading="clearLoading"
            @click="clearAllTraces"
          >
            {{ tm("confirm") }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script>
export default {
  name: "TracePage",
  components: { TraceDisplayer, SpanTree, SpanDetail },
};
</script>

<style scoped>
.trace-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.trace-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 16px;
  background: rgba(var(--v-theme-primary), 0.04);
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  flex-shrink: 0;
}

.trace-info {
  display: flex;
  align-items: center;
}

.trace-hint {
  font-size: 14px;
  color: rgba(var(--v-theme-on-surface), 0.55);
}

.trace-controls {
  display: flex;
  align-items: center;
  gap: 4px;
}

.switch-label {
  font-size: 14px;
  white-space: nowrap;
}

.trace-main {
  flex: 1;
  display: flex;
  overflow: hidden;
  min-height: 0;
}

.trace-list-panel {
  flex: 1;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  transition: flex 0.25s ease;
}

.trace-list-panel.panel-shrunk {
  flex: 0 0 380px;
}

.trace-detail-panel {
  flex: 1;
  min-width: 0;
  min-height: 0;
  border-left: 1px solid rgba(var(--v-theme-on-surface), 0.1);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.slide-detail-enter-active,
.slide-detail-leave-active {
  transition:
    opacity 0.2s ease,
    transform 0.2s ease;
}

.slide-detail-enter-from,
.slide-detail-leave-to {
  opacity: 0;
  transform: translateX(20px);
}

.detail-panel-header {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 12px 16px 12px 20px;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  flex-shrink: 0;
  min-height: 64px;
}

.detail-hd-main {
  flex: 1;
  min-width: 0;
}

.detail-hd-top {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 5px;
  flex-wrap: wrap;
}

.detail-hd-sender {
  font-size: 16px;
  font-weight: 600;
  color: rgba(var(--v-theme-on-surface), 0.9);
  white-space: nowrap;
}

.detail-hd-outline {
  font-size: 14px;
  color: rgba(var(--v-theme-on-surface), 0.55);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}

.detail-hd-badges {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.detail-badge {
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.55);
  background: rgba(var(--v-theme-on-surface), 0.05);
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  padding: 2px 10px;
  border-radius: 6px;
  white-space: nowrap;
}

.detail-tokens-tag {
  display: inline-flex;
  align-items: center;
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.55);
  background: rgba(var(--v-theme-on-surface), 0.05);
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  padding: 2px 10px;
  border-radius: 6px;
  white-space: nowrap;
}

.detail-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  flex: 1;
  gap: 8px;
}

.detail-body {
  flex: 1;
  display: flex;
  overflow: hidden;
  min-height: 0;
}

.span-tree-panel {
  flex: 0 0 280px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-height: 0;
}

.resizer-v {
  width: 4px;
  cursor: col-resize;
  background: transparent;
  transition: background 0.2s;
  flex-shrink: 0;
  z-index: 10;
  margin: 0 -2px;
}

.resizer-v:hover,
.resizer-v:active {
  background: rgba(var(--v-theme-primary), 0.3);
}

.span-tree-header {
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: rgba(var(--v-theme-on-surface), 0.45);
  padding: 12px 14px 10px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.04);
}

.st-header-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.st-header-actions {
  display: flex;
  gap: 2px;
  opacity: 0.6;
}

.st-header-actions:hover {
  opacity: 1;
}

.span-type-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.filter-chip {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 4px;
  background: var(--chip-color);
  border: 1px solid var(--chip-color);
  color: #fff !important;
  opacity: 0.9;
  cursor: pointer;
  transition: all 0.2s;
  user-select: none;
}

.filter-chip:hover {
  opacity: 1;
}

.filter-chip.inactive {
  background: rgba(var(--v-theme-on-surface), 0.04) !important;
  border-color: rgba(var(--v-theme-on-surface), 0.1) !important;
  color: rgba(var(--v-theme-on-surface), 0.35) !important;
  opacity: 0.7;
}

.no-match-hint {
  padding: 24px;
  text-align: center;
  font-size: 14px;
  color: rgba(var(--v-theme-on-surface), 0.3);
  font-style: italic;
}

.span-tree-scroll {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
  padding: 4px 0;
}

.span-detail-panel {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

@media (max-width: 900px) {
  .trace-list-panel.panel-shrunk {
    display: none;
  }
}

/* ── Custom Scrollbar ── */
:deep(::-webkit-scrollbar) {
  width: 6px;
  height: 6px;
}
:deep(::-webkit-scrollbar-thumb) {
  background: rgba(var(--v-theme-primary), 0.25);
  border-radius: 10px;
  transition: background 0.2s;
}
:deep(::-webkit-scrollbar-thumb:hover) {
  background: rgba(var(--v-theme-primary), 0.5);
}
:deep(::-webkit-scrollbar-track) {
  background: transparent;
}
/* For Firefox */
* {
  scrollbar-width: thin;
  scrollbar-color: rgba(var(--v-theme-primary), 0.25) transparent;
}
</style>
