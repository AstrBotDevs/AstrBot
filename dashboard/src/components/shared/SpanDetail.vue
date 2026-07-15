<script setup>
defineOptions({ name: 'SpanDetail' });

import { ref, computed } from 'vue';
import VueJsonPretty from 'vue-json-pretty';
import 'vue-json-pretty/lib/styles.css';

const props = defineProps({
  span: {
    type: Object,
    default: null
  }
});

// Threshold: strings longer than this are considered "long" and collapsed by default
const LONG_STRING_THRESHOLD = 200;

// Track which long-string fields are expanded, keyed by "section.fieldPath"
const expandedFields = ref(new Set());

function toggleField(key) {
  if (expandedFields.value.has(key)) {
    expandedFields.value.delete(key);
  } else {
    expandedFields.value.add(key);
  }
  // Trigger reactivity
  expandedFields.value = new Set(expandedFields.value);
}

/**
 * Split a data object into:
 *   - shortFields: fields safe for vue-json-pretty (non-long-string values)
 *   - longFields:  long string fields rendered separately with collapse/expand
 */
function splitFields(obj) {
  if (!obj || typeof obj !== 'object') return { shortFields: null, longFields: [] };
  const shortFields = {};
  const longFields = [];
  for (const [key, value] of Object.entries(obj)) {
    if (typeof value === 'string' && value.length > LONG_STRING_THRESHOLD) {
      longFields.push({ key, value });
    } else {
      shortFields[key] = value;
    }
  }
  return {
    shortFields: Object.keys(shortFields).length > 0 ? shortFields : null,
    longFields,
  };
}

// Computed splits for each section
const inputSplit = computed(() => splitFields(props.span?.input));
const outputSplit = computed(() => splitFields(props.span?.output));
const metaSplit = computed(() => splitFields(props.span?.meta));

function formatJson(obj) {
  if (!obj || Object.keys(obj).length === 0) return null;
  return JSON.stringify(obj, null, 2);
}

function formatDuration(ms) {
  if (ms == null) return null;
  if (ms < 1000) return `${ms.toFixed(1)}ms`;
  return `${(ms / 1000).toFixed(3)}s`;
}

function formatTime(ts) {
  if (!ts) return null;
  return new Date(ts * 1000).toLocaleString();
}

async function copyText(text) {
  if (!text) return;
  try { await navigator.clipboard.writeText(text); } catch {}
}

function statusColor(status) {
  if (status === 'ok')       return 'success';
  if (status === 'error')    return 'error';
  if (status === 'filtered') return 'warning';
  return 'default';
}

const SPAN_TYPE_META = {
  root:           { icon: 'mdi-ray-start-arrow', color: '#5c6bc0' },
  pipeline_stage: { icon: 'mdi-filter-outline',  color: '#78909c' },
  llm_agent:      { icon: 'mdi-robot-outline',   color: '#7c4dff' },
  llm_call:       { icon: 'mdi-brain',           color: '#ab47bc' },
  tool_call:      { icon: 'mdi-tools',           color: '#ef6c00' },
  plugin_handler: { icon: 'mdi-puzzle-outline',  color: '#00897b' }
};

function spanMeta(type) {
  return SPAN_TYPE_META[type] || { icon: 'mdi-circle-small', color: '#9e9e9e' };
}

function truncateStr(str, len = 120) {
  if (str.length <= len) return str;
  return str.slice(0, len) + '…';
}

function hasData(obj) {
  return obj && typeof obj === 'object' && Object.keys(obj).length > 0;
}
</script>

<template>
  <div v-if="span" class="span-detail">
    <!-- ── Header ──────────────────────────────────────────────────────── -->
    <div class="sd-header">
      <div class="sd-title-row">
        <div class="sd-item-badge">
          <v-icon :style="{ color: spanMeta(span.span_type).color }" size="12">
            {{ spanMeta(span.span_type).icon }}
          </v-icon>
        </div>
        <span class="sd-title">{{ span.name }}</span>
      </div>

      <div v-if="formatTime(span.started_at)" class="sd-timestamp">
        {{ formatTime(span.started_at) }}
      </div>

      <div class="sd-badges-row">
        <v-chip
          size="x-small"
          :color="statusColor(span.status)"
          variant="tonal"
          rounded="pill"
          class="sd-status-chip"
        >{{ span.status }}</v-chip>

        <span v-if="formatDuration(span.duration_ms)" class="sd-badge">
          {{ formatDuration(span.duration_ms) }}
        </span>

        <div v-if="span.meta?.input_tokens != null" class="sd-tokens-tag">
          <v-icon size="11" color="grey" class="mr-1">mdi-arrow-up-bold-outline</v-icon>
          <span>{{ span.meta.input_tokens }}</span>
          <v-icon size="11" color="grey" class="ml-2 mr-1">mdi-arrow-down-bold-outline</v-icon>
          <span>{{ span.meta.output_tokens }}</span>
          <span class="ml-1">tokens</span>
        </div>

        <span class="sd-badge sd-badge-type">{{ span.span_type }}</span>
      </div>
    </div>

    <!-- ── Stacked sections ──────────────────────────────────────────── -->
    <div class="sd-body">
      <!-- Input -->
      <div class="sd-section">
        <div class="sd-section-hd">
          <span class="sd-section-label">Input</span>
          <v-btn
            v-if="hasData(span.input)"
            icon="mdi-content-copy"
            size="x-small"
            variant="text"
            density="compact"
            class="sd-copy"
            @click="copyText(formatJson(span.input))"
          />
        </div>
        <div class="sd-section-bd">
          <template v-if="hasData(span.input)">
            <!-- Short fields rendered via vue-json-pretty -->
            <div v-if="inputSplit.shortFields" class="sd-json-wrapper">
              <vue-json-pretty
                :data="inputSplit.shortFields"
                :deep="1"
                :show-double-quotes="true"
                :show-length="true"
                :collapsed-on-click-brackets="true"
                theme="monikai"
              />
            </div>
            <!-- Long string fields rendered as collapsible blocks -->
            <div
              v-for="field in inputSplit.longFields"
              :key="'input-' + field.key"
              class="sd-long-field"
            >
              <div
                class="sd-long-field-header"
                @click="toggleField('input.' + field.key)"
              >
                <v-icon size="14" class="sd-long-field-arrow">
                  {{ expandedFields.has('input.' + field.key) ? 'mdi-chevron-down' : 'mdi-chevron-right' }}
                </v-icon>
                <span class="sd-long-field-key">"{{ field.key }}"</span>
                <span class="sd-long-field-meta">string · {{ field.value.length }} chars</span>
                <v-btn
                  icon="mdi-content-copy"
                  size="x-small"
                  variant="text"
                  density="compact"
                  class="sd-copy sd-long-field-copy"
                  @click.stop="copyText(field.value)"
                />
              </div>
              <div v-if="!expandedFields.has('input.' + field.key)" class="sd-long-field-preview">
                {{ truncateStr(field.value) }}
              </div>
              <pre v-else class="sd-long-field-full">{{ field.value }}</pre>
            </div>
          </template>
          <span v-else class="sd-nil">No input data</span>
        </div>
      </div>

      <!-- Output -->
      <div class="sd-section">
        <div class="sd-section-hd">
          <span class="sd-section-label">Output</span>
          <v-btn
            v-if="hasData(span.output)"
            icon="mdi-content-copy"
            size="x-small"
            variant="text"
            density="compact"
            class="sd-copy"
            @click="copyText(formatJson(span.output))"
          />
        </div>
        <div class="sd-section-bd">
          <template v-if="hasData(span.output)">
            <div v-if="outputSplit.shortFields" class="sd-json-wrapper">
              <vue-json-pretty
                :data="outputSplit.shortFields"
                :deep="1"
                :show-double-quotes="true"
                :show-length="true"
                :collapsed-on-click-brackets="true"
                theme="monikai"
              />
            </div>
            <div
              v-for="field in outputSplit.longFields"
              :key="'output-' + field.key"
              class="sd-long-field"
            >
              <div
                class="sd-long-field-header"
                @click="toggleField('output.' + field.key)"
              >
                <v-icon size="14" class="sd-long-field-arrow">
                  {{ expandedFields.has('output.' + field.key) ? 'mdi-chevron-down' : 'mdi-chevron-right' }}
                </v-icon>
                <span class="sd-long-field-key">"{{ field.key }}"</span>
                <span class="sd-long-field-meta">string · {{ field.value.length }} chars</span>
                <v-btn
                  icon="mdi-content-copy"
                  size="x-small"
                  variant="text"
                  density="compact"
                  class="sd-copy sd-long-field-copy"
                  @click.stop="copyText(field.value)"
                />
              </div>
              <div v-if="!expandedFields.has('output.' + field.key)" class="sd-long-field-preview">
                {{ truncateStr(field.value) }}
              </div>
              <pre v-else class="sd-long-field-full">{{ field.value }}</pre>
            </div>
          </template>
          <span v-else class="sd-nil">No output data</span>
        </div>
      </div>

      <!-- Metadata -->
      <div class="sd-section">
        <div class="sd-section-hd">
          <span class="sd-section-label">Metadata</span>
          <v-btn
            v-if="hasData(span.meta)"
            icon="mdi-content-copy"
            size="x-small"
            variant="text"
            density="compact"
            class="sd-copy"
            @click="copyText(formatJson(span.meta))"
          />
        </div>
        <div class="sd-section-bd">
          <template v-if="hasData(span.meta)">
            <div v-if="metaSplit.shortFields" class="sd-json-wrapper">
              <vue-json-pretty
                :data="metaSplit.shortFields"
                :deep="1"
                :show-double-quotes="true"
                :show-length="true"
                :collapsed-on-click-brackets="true"
                theme="monikai"
              />
            </div>
            <div
              v-for="field in metaSplit.longFields"
              :key="'meta-' + field.key"
              class="sd-long-field"
            >
              <div
                class="sd-long-field-header"
                @click="toggleField('meta.' + field.key)"
              >
                <v-icon size="14" class="sd-long-field-arrow">
                  {{ expandedFields.has('meta.' + field.key) ? 'mdi-chevron-down' : 'mdi-chevron-right' }}
                </v-icon>
                <span class="sd-long-field-key">"{{ field.key }}"</span>
                <span class="sd-long-field-meta">string · {{ field.value.length }} chars</span>
                <v-btn
                  icon="mdi-content-copy"
                  size="x-small"
                  variant="text"
                  density="compact"
                  class="sd-copy sd-long-field-copy"
                  @click.stop="copyText(field.value)"
                />
              </div>
              <div v-if="!expandedFields.has('meta.' + field.key)" class="sd-long-field-preview">
                {{ truncateStr(field.value) }}
              </div>
              <pre v-else class="sd-long-field-full">{{ field.value }}</pre>
            </div>
          </template>
          <span v-else class="sd-nil">No metadata</span>
        </div>
      </div>
    </div>
  </div>

  <!-- Placeholder -->
  <div v-else class="sd-placeholder">
    <v-icon size="36" color="grey-lighten-1">mdi-cursor-default-click-outline</v-icon>
    <div class="sd-placeholder-text">Select a span to view details</div>
  </div>
</template>

<style scoped>
.span-detail {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

/* ── Header ─────────────────────────────────────────────────────────── */
.sd-header {
  padding: 16px 20px;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* Title row */
.sd-title-row {
  display: flex;
  align-items: flex-start;
  gap: 7px;
}

/* ItemBadge-style icon box */
.sd-item-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 6px;
  border: 1.5px solid rgba(var(--v-theme-on-surface), 0.14);
  background: rgb(var(--v-theme-surface));
  flex-shrink: 0;
  margin-top: 2px;
}

.sd-title {
  font-size: 16px;
  font-weight: 600;
  font-family: 'JetBrains Mono', 'Fira Code', ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
  color: rgba(var(--v-theme-on-surface), 0.9);
  line-height: 1.5;
  word-break: break-all;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* Timestamp row */
.sd-timestamp {
  font-size: 14px;
  color: rgba(var(--v-theme-on-surface), 0.45);
  padding-left: 30px;
}

/* Badges row */
.sd-badges-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding-left: 30px;
}

.sd-status-chip {
  font-size: 11px !important;
  height: 20px !important;
}

.sd-badge {
  display: inline-flex;
  align-items: center;
  font-size: 12px;
  font-weight: 500;
  color: rgba(var(--v-theme-on-surface), 0.65);
  background: rgba(var(--v-theme-on-surface), 0.06);
  border: 1px solid rgba(var(--v-theme-on-surface), 0.10);
  border-radius: 6px;
  padding: 2px 10px;
  white-space: nowrap;
  line-height: 1.6;
}

.sd-badge-type {
  font-family: 'JetBrains Mono', 'Fira Code', ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
  font-size: 10px;
}

.sd-tokens-tag {
  display: inline-flex;
  align-items: center;
  font-size: 12px;
  font-weight: 500;
  color: rgba(var(--v-theme-on-surface), 0.65);
  background: rgba(var(--v-theme-on-surface), 0.06);
  border: 1px solid rgba(var(--v-theme-on-surface), 0.10);
  border-radius: 6px;
  padding: 2px 10px;
  white-space: nowrap;
  line-height: 1.6;
}

/* ── Scrollable body ─────────────────────────────────────────────────── */
.sd-body {
  flex: 1;
  overflow-y: auto;
}

/* ── Section ─────────────────────────────────────────────────────────── */
.sd-section {
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.06);
}

.sd-section-hd {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 9px 14px 3px;
}

.sd-section-label {
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: rgba(var(--v-theme-on-surface), 0.45);
}

.sd-copy {
  opacity: 0.4;
  transition: opacity 0.15s;
}
.sd-copy:hover {
  opacity: 1;
}

.sd-section-bd {
  padding: 4px 20px 16px;
}

.sd-json-wrapper {
  background: rgba(var(--v-theme-on-surface), 0.03);
  border: 1px solid rgba(var(--v-theme-on-surface), 0.07);
  border-radius: 6px;
  padding: 8px 12px;
  font-family: 'JetBrains Mono', 'Fira Code', ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
}

:deep(.vjs-tree) {
  font-family: inherit !important;
  font-size: 14px !important;
}

:deep(.vjs-key) {
  color: #ab47bc !important;
}

:deep(.vjs-value__string) {
  color: #43a047 !important;
}

:deep(.vjs-value__number) {
  color: #ef6c00 !important;
}

:deep(.vjs-value__boolean) {
  color: #1e88e5 !important;
}

/* ── Long-string collapsible field ───────────────────────────────────── */
.sd-long-field {
  margin-top: 6px;
  background: rgba(var(--v-theme-on-surface), 0.03);
  border: 1px solid rgba(var(--v-theme-on-surface), 0.07);
  border-radius: 6px;
  overflow: hidden;
}

.sd-long-field-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  cursor: pointer;
  user-select: none;
  transition: background 0.12s;
}

.sd-long-field-header:hover {
  background: rgba(var(--v-theme-on-surface), 0.05);
}

.sd-long-field-arrow {
  color: rgba(var(--v-theme-on-surface), 0.45);
  flex-shrink: 0;
}

.sd-long-field-key {
  font-family: 'JetBrains Mono', 'Fira Code', ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
  font-size: 13px;
  font-weight: 600;
  color: #ab47bc;
  flex-shrink: 0;
}

.sd-long-field-meta {
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), 0.4);
  flex-shrink: 0;
  margin-left: auto;
  margin-right: 4px;
}

.sd-long-field-copy {
  flex-shrink: 0;
}

.sd-long-field-preview {
  padding: 0 10px 8px 30px;
  font-family: 'JetBrains Mono', 'Fira Code', ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
  font-size: 12px;
  color: #43a047;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.sd-long-field-full {
  margin: 0;
  padding: 0 10px 10px 30px;
  font-family: 'JetBrains Mono', 'Fira Code', ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
  font-size: 12px;
  color: #43a047;
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.65;
  max-height: 400px;
  overflow-y: auto;
  background: transparent;
  border: none;
}

.sd-nil {
  font-size: 12px;
  font-style: italic;
  color: rgba(var(--v-theme-on-surface), 0.3);
}

/* ── Placeholder ─────────────────────────────────────────────────────── */
.sd-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: 10px;
}

.sd-placeholder-text {
  font-size: 14px;
  color: rgba(var(--v-theme-on-surface), 0.35);
}
</style>
