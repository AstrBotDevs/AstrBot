<!--
  Author: elecvoid243, 2026-07-02
  SearchPanel — in-sidebar content search results UI.
  Spec: docs/superpowers/specs/2026-07-02-sidebar-search-design.md §4.4

  Notes vs. the brief template:
  - Project pins vue@3.3.4, so `useTemplateRef` (Vue 3.5+) is unavailable;
    fall back to the established `ref<HTMLInputElement | null>(null)` pattern.
  - `useModuleI18n().tm()` is typed as (key, params?) — no `missing` option.
    The error-reason label is built by errorReasonLabel(), which tries the
    per-reason key and falls back to the raw reason string when missing.
    T8 adds the per-reason keys; until then the raw reason is shown.
-->
<script setup lang="ts">
import { ref, watch, nextTick, onMounted } from "vue";
import {
  useSpcodeFileSearch,
  type SearchResult,
} from "@/composables/useSpcodeFileSearch";
import { useModuleI18n } from "@/i18n/composables";

const props = defineProps<{
  modelValue: boolean;
  worktree: string | null;
  umo: string | null;
}>();
const emit = defineEmits<{
  "update:modelValue": [v: boolean];
  "open-file": [p: { path: string; line: number }];
}>();

const { tm } = useModuleI18n("features/chat");
const { state, search, cancel } = useSpcodeFileSearch();

const query = ref("");
const debounceTimer = ref<ReturnType<typeof setTimeout> | null>(null);
const inputRef = ref<HTMLInputElement | null>(null);

// 300ms debounce per spec §4.4
watch(query, (v) => {
  if (debounceTimer.value) clearTimeout(debounceTimer.value);
  if (!v.trim()) {
    cancel();
    state.value = { kind: "idle" };
    return;
  }
  debounceTimer.value = setTimeout(() => {
    void search({
      umo: props.umo,
      worktree: props.worktree,
      pattern: v,
    });
  }, 300);
});

// Focus the input when the panel opens
watch(
  () => props.modelValue,
  async (open) => {
    if (open) {
      await nextTick();
      inputRef.value?.focus();
    }
  },
);

function onClose(): void {
  if (debounceTimer.value) clearTimeout(debounceTimer.value);
  cancel();
  query.value = "";
  state.value = { kind: "idle" };
  emit("update:modelValue", false);
}

function onResultClick(r: SearchResult): void {
  emit("open-file", { path: r.path, line: r.line });
}

function onKeydown(e: KeyboardEvent): void {
  if (e.key === "Escape") {
    e.stopPropagation();
    onClose();
  }
}

// Try the per-reason i18n key (added in T8); fall back to the raw reason
// string when the key is missing so the UI stays useful during development.
function errorReasonLabel(reason: string): string {
  const translated = tm(`spcodeProjectLoad.diffSidebar.search.error.${reason}`);
  if (translated.startsWith("[MISSING:")) return reason;
  return translated;
}

onMounted(() => {
  // Focus on mount if opened
  if (props.modelValue) {
    nextTick(() => inputRef.value?.focus());
  }
});
</script>

<template>
  <div v-if="modelValue" class="search-panel" @keydown="onKeydown">
    <div class="search-panel-input-row">
      <v-icon size="16">mdi-magnify</v-icon>
      <input
        ref="inputRef"
        v-model="query"
        type="text"
        class="search-panel-input"
        :placeholder="tm('spcodeProjectLoad.diffSidebar.search.placeholder')"
        spellcheck="false"
        autocomplete="off"
      />
      <v-icon
        v-if="state.kind === 'loading'"
        size="14"
        class="search-panel-spinner"
      >
        mdi-loading
      </v-icon>
      <v-btn icon="mdi-close" size="x-small" variant="text" @click="onClose" />
    </div>

    <div class="search-panel-status">
      <template v-if="state.kind === 'idle'">
        <span class="text-caption text-medium-emphasis">
          {{ tm("spcodeProjectLoad.diffSidebar.search.hint") }}
        </span>
      </template>
      <template v-else-if="state.kind === 'loading'">
        <span class="text-caption text-medium-emphasis">
          {{ tm("spcodeProjectLoad.diffSidebar.search.searching") }}
        </span>
      </template>
      <template v-else-if="state.kind === 'ok'">
        <span class="text-caption">
          {{
            tm("spcodeProjectLoad.diffSidebar.search.resultCount", {
              count: state.results.length,
            })
          }}
        </span>
        <v-chip
          v-if="state.backend === 'python'"
          size="x-small"
          variant="tonal"
          color="warning"
        >
          {{ tm("spcodeProjectLoad.diffSidebar.search.fallbackHint") }}
        </v-chip>
        <span v-if="state.truncated" class="text-caption text-warning">
          {{ tm("spcodeProjectLoad.diffSidebar.search.truncated") }}
        </span>
      </template>
      <template v-else-if="state.kind === 'error'">
        <span class="text-caption text-error">
          {{ errorReasonLabel(state.reason) }}
        </span>
      </template>
    </div>

    <ul
      v-if="state.kind === 'ok' && state.results.length"
      class="search-panel-results"
    >
      <li
        v-for="(r, i) in state.results"
        :key="i"
        class="search-panel-result"
        @click="onResultClick(r)"
      >
        <div class="search-panel-result-path">
          {{ r.path }}:{{ r.line }}:{{ r.column }}
        </div>
        <pre class="search-panel-result-snippet">{{ r.snippet }}</pre>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.search-panel {
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 50%;
  overflow: hidden;
}
.search-panel-input-row {
  display: flex;
  align-items: center;
  gap: 6px;
}
.search-panel-input {
  flex: 1;
  border: none;
  outline: none;
  background: transparent;
  font-size: 13px;
  color: rgb(var(--v-theme-on-surface));
  font-family: inherit;
}
.search-panel-status {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 18px;
  flex-wrap: wrap;
}
.search-panel-results {
  list-style: none;
  padding: 0;
  margin: 0;
  overflow-y: auto;
  flex: 1;
}
.search-panel-result {
  padding: 4px 6px;
  border-radius: 4px;
  cursor: pointer;
}
.search-panel-result:hover {
  background: rgba(var(--v-theme-on-surface), 0.06);
}
.search-panel-result-path {
  font-family: ui-monospace, SFMono-Regular, monospace;
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), 0.7);
}
.search-panel-result-snippet {
  font-family: ui-monospace, SFMono-Regular, monospace;
  font-size: 12px;
  margin: 2px 0 0 0;
  white-space: pre-wrap;
  word-break: break-all;
  color: rgb(var(--v-theme-on-surface));
}
.search-panel-spinner {
  animation: spin 1s linear infinite;
}
@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}
</style>
