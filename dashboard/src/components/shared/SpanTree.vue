<script setup>
defineOptions({ name: "SpanTree" });

const props = defineProps({
  span: {
    type: Object,
    required: true,
  },
  depth: {
    type: Number,
    default: 0,
  },
  // Array of booleans: for each ancestor depth, whether a vertical line should pass through
  treeLines: {
    type: Array,
    default: () => [],
  },
  // Whether this span is the last child among its siblings
  isLast: {
    type: Boolean,
    default: true,
  },
  // Currently selected span id for highlight
  selectedSpanId: {
    type: String,
    default: null,
  },
  // Signals for expand/collapse all
  expandSignal: {
    type: Number,
    default: 0,
  },
  collapseSignal: {
    type: Number,
    default: 0,
  },
});

const emit = defineEmits(["select"]);

import { ref, watch } from "vue";

const expanded = ref(true);

watch(
  () => props.expandSignal,
  () => {
    if (props.span.children?.length) expanded.value = true;
  },
);

watch(
  () => props.collapseSignal,
  () => {
    if (props.depth > 0) expanded.value = false;
  },
);

function toggleExpand() {
  if (props.span.children?.length) {
    expanded.value = !expanded.value;
  }
}

function selectSpan() {
  emit("select", props.span);
}

const SPAN_TYPE_META = {
  root: { icon: "mdi-ray-start-arrow", color: "#5c6bc0" },
  pipeline_stage: { icon: "mdi-filter-outline", color: "#78909c" },
  llm_agent: { icon: "mdi-robot-outline", color: "#7c4dff" },
  llm_call: { icon: "mdi-brain", color: "#ab47bc" },
  tool_call: { icon: "mdi-tools", color: "#ef6c00" },
  plugin_handler: { icon: "mdi-puzzle-outline", color: "#00897b" },
};

function spanMeta(type) {
  return SPAN_TYPE_META[type] || { icon: "mdi-circle-small", color: "#9e9e9e" };
}

function statusColor(status) {
  if (status === "ok") return "success";
  if (status === "error") return "error";
  if (status === "filtered") return "warning";
  return "default";
}

function formatDuration(ms) {
  if (ms == null) return "";
  if (ms < 1000) return `${ms.toFixed(0)}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

// ── Plugin tag color ──────────────────────────────────────────────────
// Each plugin name is deterministically mapped to one color from the
// palette via a simple hash, so the same plugin always gets the same
// color within a trace (and across traces).
const PLUGIN_COLORS = [
  {
    bg: "rgba(92,107,192,0.13)",
    border: "rgba(92,107,192,0.32)",
    text: "#5c6bc0",
  }, // indigo
  {
    bg: "rgba(0,137,123,0.13)",
    border: "rgba(0,137,123,0.32)",
    text: "#00897b",
  }, // teal
  {
    bg: "rgba(239,108,0,0.13)",
    border: "rgba(239,108,0,0.32)",
    text: "#e65100",
  }, // orange
  {
    bg: "rgba(171,71,188,0.13)",
    border: "rgba(171,71,188,0.32)",
    text: "#ab47bc",
  }, // purple
  {
    bg: "rgba(30,136,229,0.13)",
    border: "rgba(30,136,229,0.32)",
    text: "#1976d2",
  }, // blue
  {
    bg: "rgba(67,160,71,0.13)",
    border: "rgba(67,160,71,0.32)",
    text: "#388e3c",
  }, // green
  {
    bg: "rgba(229,57,53,0.13)",
    border: "rgba(229,57,53,0.32)",
    text: "#c62828",
  }, // red
  {
    bg: "rgba(255,160,0,0.13)",
    border: "rgba(255,160,0,0.32)",
    text: "#e65100",
  }, // amber
  {
    bg: "rgba(38,166,154,0.13)",
    border: "rgba(38,166,154,0.32)",
    text: "#00796b",
  }, // teal-green
  {
    bg: "rgba(120,144,156,0.13)",
    border: "rgba(120,144,156,0.32)",
    text: "#546e7a",
  }, // blue-grey
];

function strHash(s) {
  let h = 0;
  for (let i = 0; i < s.length; i++)
    h = (Math.imul(31, h) + s.charCodeAt(i)) | 0;
  return Math.abs(h);
}

function pluginTagStyle(name) {
  const c = PLUGIN_COLORS[strHash(name) % PLUGIN_COLORS.length];
  return { background: c.bg, border: `1px solid ${c.border}`, color: c.text };
}
</script>

<template>
  <div class="stn-node">
    <!-- Row -->
    <div
      class="stn-row"
      :class="{
        'stn-selected': span.span_id === selectedSpanId,
        'stn-root': depth === 0,
        'stn-filtered': span.isFiltered,
      }"
      @click="selectSpan"
    >
      <!-- ① Ancestor slots: one 20px slot per ancestor level (depth-1 items) -->
      <div
        v-for="(hasLine, i) in treeLines.slice(0, depth > 0 ? depth - 1 : 0)"
        :key="i"
        class="stn-ancestor-slot"
      >
        <div v-if="hasLine" class="stn-vline-full" />
      </div>

      <!-- ② Current connection slot (only for non-root nodes) -->
      <div v-if="depth > 0" class="stn-conn-slot">
        <div class="stn-vline-top" />
        <div v-if="!isLast" class="stn-vline-bottom" />
        <div class="stn-hline" />
      </div>

      <!-- ③ Type icon badge (LangFuse ItemBadge style) -->
      <div class="stn-type-badge">
        <v-icon :style="{ color: spanMeta(span.span_type).color }" size="11">
          {{ spanMeta(span.span_type).icon }}
        </v-icon>
      </div>

      <!-- ④ Name + metrics -->
      <div class="stn-content">
        <div class="stn-name-row">
          <span class="stn-name">{{ span.name }}</span>
          <v-chip
            v-if="span.status !== 'ok'"
            size="x-small"
            :color="statusColor(span.status)"
            variant="tonal"
            rounded="pill"
            class="stn-status-chip"
            >{{ span.status }}</v-chip
          >
        </div>
        <div
          v-if="
            span.duration_ms != null ||
            span.meta?.input_tokens != null ||
            span.meta?.plugin
          "
          class="stn-metrics-row"
        >
          <span v-if="span.duration_ms != null" class="stn-metric">{{
            formatDuration(span.duration_ms)
          }}</span>
          <div v-if="span.meta?.input_tokens != null" class="stn-tokens-tag">
            <v-icon size="9" color="grey" class="mr-1"
              >mdi-arrow-up-bold-outline</v-icon
            >
            <span>{{ span.meta.input_tokens }}</span>
            <v-icon size="9" color="grey" class="ml-2 mr-1"
              >mdi-arrow-down-bold-outline</v-icon
            >
            <span>{{ span.meta.output_tokens }}</span>
          </div>
          <div
            v-if="span.meta?.plugin"
            class="stn-plugin-tag"
            :style="pluginTagStyle(span.meta.plugin)"
          >
            <v-icon size="9" class="stn-plugin-icon">{{
              span.meta.plugin_type === "builtin"
                ? "mdi-cog-outline"
                : "mdi-puzzle-outline"
            }}</v-icon>
            <span>{{ span.meta.plugin }}</span>
          </div>
        </div>
      </div>

      <!-- ⑤ Expand button on the RIGHT (LangFuse style) -->
      <div
        v-if="span.children?.length"
        class="stn-expand-btn"
        @click.stop="toggleExpand"
      >
        <v-icon
          size="14"
          :style="{
            transform: expanded ? 'rotate(90deg)' : 'rotate(0deg)',
            transition: 'transform 0.15s ease',
          }"
          >mdi-chevron-right</v-icon
        >
      </div>
      <div v-else class="stn-expand-spacer" />
    </div>

    <!-- Children -->
    <div v-if="span.children?.length" v-show="expanded">
      <SpanTree
        v-for="(child, idx) in span.children"
        :key="child.span_id"
        :span="child"
        :depth="depth + 1"
        :tree-lines="[...treeLines, !isLast]"
        :is-last="idx === span.children.length - 1"
        :selected-span-id="selectedSpanId"
        :expand-signal="expandSignal"
        :collapse-signal="collapseSignal"
        @select="$emit('select', $event)"
      />
    </div>
  </div>
</template>

<style scoped>
.stn-node {
  font-size: 14px;
}

/* ── Row ─────────────────────────────────────────────────────────────── */
.stn-row {
  display: flex;
  align-items: center;
  min-height: 38px;
  cursor: pointer;
  transition: background 0.1s;
  border-radius: 4px;
  padding-right: 6px;
  user-select: none;
}

.stn-row:hover {
  background: rgba(var(--v-theme-on-surface), 0.04);
}

.stn-selected {
  background: rgba(var(--v-theme-on-surface), 0.07) !important;
}
.stn-filtered {
  opacity: 0.5;
  filter: grayscale(0.2);
}
.stn-filtered:hover {
  opacity: 0.8;
  filter: grayscale(0);
}

.stn-root > .stn-content > .stn-name-row > .stn-name {
  font-weight: 600;
}

/* ── Tree connector slots ────────────────────────────────────────────── */
/* Each slot is 20px wide, relative-positioned for absolute children */

.stn-ancestor-slot {
  position: relative;
  width: 24px;
  min-height: 38px;
  flex-shrink: 0;
  align-self: stretch;
}

.stn-vline-full {
  position: absolute;
  left: 11px;
  top: 0;
  bottom: 0;
  width: 1px;
  background: rgba(var(--v-theme-on-surface), 0.12);
}

.stn-conn-slot {
  position: relative;
  width: 24px;
  min-height: 38px;
  flex-shrink: 0;
  align-self: stretch;
}

/* Vertical line: top half (from row top to vertical midpoint) */
.stn-vline-top {
  position: absolute;
  left: 11px;
  top: 0;
  height: 50%;
  width: 1px;
  background: rgba(var(--v-theme-on-surface), 0.12);
}

/* Vertical line: bottom half (from midpoint to row bottom) — only if not last sibling */
.stn-vline-bottom {
  position: absolute;
  left: 11px;
  top: 50%;
  bottom: 0;
  width: 1px;
  background: rgba(var(--v-theme-on-surface), 0.12);
}

/* Horizontal line from connector point to icon */
.stn-hline {
  position: absolute;
  left: 11px;
  top: calc(50% - 0.5px);
  width: 13px;
  height: 1px;
  background: rgba(var(--v-theme-on-surface), 0.12);
}

/* ── Type icon badge (LangFuse ItemBadge style) ──────────────────────── */
.stn-type-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 5px;
  border: 1.5px solid rgba(var(--v-theme-on-surface), 0.14);
  background: rgb(var(--v-theme-surface));
  flex-shrink: 0;
  margin-right: 8px;
}

/* ── Content area ────────────────────────────────────────────────────── */
.stn-content {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 3px 0;
}

.stn-name-row {
  display: flex;
  align-items: center;
  gap: 5px;
  min-width: 0;
}

.stn-name {
  font-family: "JetBrains Mono", "Fira Code", ui-monospace, SFMono-Regular,
    Menlo, Monaco, Consolas, "Liberation Mono", monospace;
  font-size: 14px;
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: rgba(var(--v-theme-on-surface), 0.87);
  letter-spacing: -0.01em;
}

.stn-status-chip {
  flex-shrink: 0;
  font-size: 11px !important;
  height: 18px !important;
  padding: 0 6px !important;
}

.stn-metrics-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 1px;
}

.stn-metric {
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.5);
  white-space: nowrap;
}

.stn-tokens-tag {
  display: inline-flex;
  align-items: center;
  font-size: 10px;
  color: rgba(var(--v-theme-on-surface), 0.5);
  background: rgba(var(--v-theme-on-surface), 0.05);
  border: 1px solid rgba(var(--v-theme-on-surface), 0.07);
  padding: 0px 6px;
  border-radius: 4px;
  white-space: nowrap;
  height: 18px;
}

/* ── Expand button (right side, LangFuse style) ──────────────────────── */
.stn-expand-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 4px;
  flex-shrink: 0;
  margin-left: 4px;
  color: rgba(var(--v-theme-on-surface), 0.4);
  cursor: pointer;
  transition:
    background 0.12s,
    color 0.12s;
}

.stn-expand-btn:hover {
  background: rgba(var(--v-theme-primary), 0.1);
  color: rgba(var(--v-theme-on-surface), 0.8);
}

.stn-expand-spacer {
  width: 22px;
  flex-shrink: 0;
  margin-left: 4px;
}

/* ── Plugin tag ──────────────────────────────────────────────────────── */
.stn-plugin-tag {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 10px;
  padding: 0px 6px;
  border-radius: 10px;
  height: 18px;
  white-space: nowrap;
  font-weight: 500;
  letter-spacing: 0.01em;
}

.stn-plugin-icon {
  opacity: 0.8;
}
</style>
