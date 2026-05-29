<template>
  <div
    class="diff-preview"
    :class="{ 'is-dark': isDark, collapsed: isCollapsed }"
  >
    <!-- Summary header — always visible, clickable to toggle -->
    <button
      v-if="summary || filePath || statsText"
      type="button"
      class="diff-header"
      @click="toggleCollapsed"
    >
      <div class="diff-header-left">
        <v-icon size="16" class="diff-header-icon">mdi-file-document-edit-outline</v-icon>
        <span v-if="filePath" class="diff-file-path">{{ filePath }}</span>
      </div>
      <div class="diff-header-right">
        <span v-if="statsText" class="diff-stats">{{ statsText }}</span>
        <v-icon
          v-if="collapsible"
          size="18"
          class="diff-chevron"
          :class="{ expanded: !isCollapsed }"
        >
          mdi-chevron-right
        </v-icon>
      </div>
    </button>

    <!-- Summary text (e.g. "Replaced 1 occurrence(s)...") -->
    <div v-if="summary && !isCollapsed" class="diff-summary-text">
      {{ summary }}
    </div>

    <!-- Diff hunks — hidden when collapsed -->
    <div v-if="!isCollapsed" class="diff-body">
      <div v-if="truncated" class="diff-truncation-warning">
        ⚠ Diff truncated (showing first {{ maxChars.toLocaleString() }} characters)
      </div>

      <div
        v-for="(hunk, hi) in parsedHunks"
        :key="hi"
        class="diff-hunk"
      >
        <div class="hunk-header">
          @@ {{ hunk.header }} @@
        </div>
        <div
          v-for="(line, li) in hunk.lines"
          :key="li"
          class="diff-line"
          :class="line.type"
        >
          <span class="line-number old">{{ line.oldNo }}</span>
          <span class="line-number new">{{ line.newNo }}</span>
          <span class="line-prefix">{{ line.prefix }}</span>
          <span class="line-content">{{ line.content }}</span>
        </div>
      </div>

      <div v-if="collapsedOverflow > 0" class="diff-overflow-bar">
        <button type="button" class="diff-show-more" @click="showAllLines = true">
          Show all {{ totalLines.toLocaleString() }} lines
          ({{ collapsedOverflow }} more)
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";

// ── Types ──────────────────────────────────────────────────────────

interface DiffLine {
  type: "add" | "del" | "ctx" | "header-file";
  prefix: string;
  content: string;
  oldNo: string;
  newNo: string;
}

interface DiffHunk {
  header: string;
  lines: DiffLine[];
}

// ── Props ──────────────────────────────────────────────────────────

const props = withDefaults(
  defineProps<{
    content: string;
    filePath?: string;
    summary?: string;
    maxLines?: number;
    maxChars?: number;
    collapsible?: boolean;
    isDark?: boolean;
  }>(),
  {
    filePath: "",
    summary: "",
    maxLines: 30,
    maxChars: 2000,
    collapsible: true,
    isDark: false,
  },
);

// ── State ──────────────────────────────────────────────────────────

const isCollapsed = ref(false);
const showAllLines = ref(false);
const effectiveMaxLines = computed(() =>
  showAllLines.value ? Infinity : props.maxLines,
);

const toggleCollapsed = () => {
  if (props.collapsible) {
    isCollapsed.value = !isCollapsed.value;
  }
};

// ── Parse unified diff ─────────────────────────────────────────────

const parsedHunks = computed<DiffHunk[]>(() => {
  const text = extractDiffContent(props.content);
  return parseUnifiedDiff(text, effectiveMaxLines.value);
});

const totalLines = computed(() =>
  parsedHunks.value.reduce((sum, h) => sum + h.lines.length, 0),
);

const truncated = computed(() => {
  const raw = extractDiffContent(props.content);
  return raw.length > props.maxChars;
});

const collapsedOverflow = computed(() => {
  if (showAllLines.value) return 0;
  const fullHunks = parseUnifiedDiff(
    extractDiffContent(props.content),
    Infinity,
  );
  const fullTotal = fullHunks.reduce((sum, h) => sum + h.lines.length, 0);
  return Math.max(0, fullTotal - totalLines.value);
});

// ── Stats ──────────────────────────────────────────────────────────

const statsText = computed(() => {
  let adds = 0;
  let dels = 0;
  for (const hunk of parsedHunks.value) {
    for (const line of hunk.lines) {
      if (line.type === "add") adds++;
      if (line.type === "del") dels++;
    }
  }
  if (adds === 0 && dels === 0) return "";
  return `+${adds} −${dels}`;
});

// ── Helpers ────────────────────────────────────────────────────────

function extractDiffContent(raw: string): string {
  // If the text contains a ```diff ... ``` block, extract its content
  const blockMatch = raw.match(/```diff\s*\n?([\s\S]*?)```/);
  if (blockMatch) return blockMatch[1];

  // Otherwise, try to strip leading "Diff:" / "Edited ..." lines
  const diffIdx = raw.indexOf("@@");
  if (diffIdx >= 0) return raw.slice(diffIdx);

  return raw;
}

function parseUnifiedDiff(text: string, maxLines: number): DiffHunk[] {
  const lines = text.split("\n");
  const hunks: DiffHunk[] = [];
  let currentHunk: DiffHunk | null = null;
  let totalLines = 0;
  let oldNo = 0;
  let newNo = 0;

  // Try to parse --- / +++ file headers to get old/new line numbers
  for (const rawLine of lines) {
    if (totalLines >= maxLines) break;

    const hunkMatch = rawLine.match(
      /^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@(.*)$/,
    );
    if (hunkMatch) {
      // Flush previous hunk
      if (currentHunk) hunks.push(currentHunk);

      oldNo = parseInt(hunkMatch[1], 10);
      newNo = parseInt(hunkMatch[3], 10);

      currentHunk = {
        header: rawLine.replace(/^@@\s+/, "").replace(/\s+@@.*$/, "").trim(),
        lines: [],
      };
      continue;
    }

    if (!currentHunk) continue;

    const ch = rawLine[0];
    let type: DiffLine["type"];
    let prefix: string;
    let content: string;

    if (ch === "+") {
      type = "add";
      prefix = "+";
      content = rawLine.slice(1);
    } else if (ch === "-") {
      type = "del";
      prefix = "−";
      content = rawLine.slice(1);
    } else if (ch === " ") {
      type = "ctx";
      prefix = " ";
      content = rawLine.slice(1);
    } else if (rawLine === "\\ No newline at end of file") {
      type = "ctx";
      prefix = " ";
      content = rawLine;
    } else {
      // Could be --- or +++ header lines; skip or treat as ctx
      if (rawLine.startsWith("---") || rawLine.startsWith("+++")) continue;
      type = "ctx";
      prefix = " ";
      content = rawLine;
    }

    const line: DiffLine = {
      type,
      prefix,
      content,
      oldNo: type === "add" ? "" : String(oldNo),
      newNo: type === "del" ? "" : String(newNo),
    };

    if (type !== "add") oldNo++;
    if (type !== "del") newNo++;

    currentHunk.lines.push(line);
    totalLines++;
  }

  if (currentHunk) hunks.push(currentHunk);
  return hunks;
}
</script>

<style scoped>
.diff-preview {
  --diff-add-bg: rgba(70, 200, 70, 0.12);
  --diff-add-border: rgba(70, 200, 70, 0.35);
  --diff-del-bg: rgba(255, 100, 100, 0.12);
  --diff-del-border: rgba(255, 100, 100, 0.35);
  --diff-hunk-bg: #e8f0fe;
  --diff-hunk-border: rgba(100, 150, 220, 0.3);
  --diff-line-no: rgba(0, 0, 0, 0.35);
  --diff-border: rgba(0, 0, 0, 0.08);

  margin: 4px 0;
  border: 1px solid var(--diff-border);
  border-radius: 8px;
  overflow: hidden;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 12px;
  line-height: 1.55;
}

.diff-preview.is-dark {
  --diff-add-bg: rgba(70, 200, 70, 0.16);
  --diff-add-border: rgba(70, 200, 70, 0.3);
  --diff-del-bg: rgba(255, 100, 100, 0.16);
  --diff-del-border: rgba(255, 100, 100, 0.3);
  --diff-hunk-bg: rgba(100, 150, 255, 0.12);
  --diff-hunk-border: rgba(100, 150, 255, 0.2);
  --diff-line-no: rgba(255, 255, 255, 0.35);
  --diff-border: rgba(255, 255, 255, 0.1);
}

/* ── Header ─────────────────────────────────────────────────────── */

.diff-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 8px 12px;
  background: rgba(0, 0, 0, 0.02);
  border: 0;
  cursor: pointer;
  font: inherit;
  color: inherit;
  user-select: none;
}

.diff-preview.is-dark .diff-header {
  background: rgba(255, 255, 255, 0.03);
}

.diff-header:hover {
  background: rgba(0, 0, 0, 0.05);
}

.diff-preview.is-dark .diff-header:hover {
  background: rgba(255, 255, 255, 0.06);
}

.diff-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.diff-header-right {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.diff-header-icon {
  color: rgba(var(--v-theme-on-surface), 0.55);
  flex-shrink: 0;
}

.diff-file-path {
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: rgba(var(--v-theme-on-surface), 0.8);
}

.diff-stats {
  font-size: 11px;
  font-weight: 600;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  color: rgba(var(--v-theme-on-surface), 0.55);
  white-space: nowrap;
}

.diff-chevron {
  color: rgba(var(--v-theme-on-surface), 0.45);
  transition: transform 0.2s ease;
}

.diff-chevron.expanded {
  transform: rotate(90deg);
}

/* ── Summary text ────────────────────────────────────────────────── */

.diff-summary-text {
  padding: 4px 12px 8px;
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), 0.55);
  font-family: inherit;
}

/* ── Body ────────────────────────────────────────────────────────── */

.diff-body {
  border-top: 1px solid var(--diff-border);
}

.diff-truncation-warning {
  padding: 6px 12px;
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), 0.55);
  background: rgba(var(--v-theme-warning), 0.08);
  border-bottom: 1px solid var(--diff-border);
}

/* ── Hunk ────────────────────────────────────────────────────────── */

.diff-hunk + .diff-hunk {
  border-top: 1px solid rgba(var(--v-theme-on-surface), 0.04);
}

.hunk-header {
  padding: 4px 12px;
  font-size: 11px;
  font-weight: 600;
  color: rgba(var(--v-theme-on-surface), 0.55);
  background: var(--diff-hunk-bg);
  border-bottom: 1px solid var(--diff-hunk-border);
}

/* ── Diff line ───────────────────────────────────────────────────── */

.diff-line {
  display: flex;
  align-items: baseline;
  padding: 1px 12px;
  min-height: 20px;
  transition: background 0.1s ease;
}

.diff-line:hover {
  filter: brightness(0.94);
}

.diff-preview.is-dark .diff-line:hover {
  filter: brightness(1.15);
}

.diff-line.add {
  background: var(--diff-add-bg);
  border-left: 3px solid var(--diff-add-border);
}

.diff-line.del {
  background: var(--diff-del-bg);
  border-left: 3px solid var(--diff-del-border);
}

.diff-line.ctx {
  border-left: 3px solid transparent;
}

/* ── Line numbers ────────────────────────────────────────────────── */

.line-number {
  width: 36px;
  flex-shrink: 0;
  text-align: right;
  padding-right: 8px;
  color: var(--diff-line-no);
  user-select: none;
}

.line-number.new {
  padding-right: 0;
  padding-left: 8px;
}

/* ── Prefix and content ──────────────────────────────────────────── */

.line-prefix {
  width: 14px;
  flex-shrink: 0;
  text-align: center;
  font-weight: 700;
  user-select: none;
}

.diff-line.add .line-prefix {
  color: #2da44e;
}

.diff-preview.is-dark .diff-line.add .line-prefix {
  color: #57ab5a;
}

.diff-line.del .line-prefix {
  color: #cf222e;
}

.diff-preview.is-dark .diff-line.del .line-prefix {
  color: #f47067;
}

.line-content {
  white-space: pre-wrap;
  word-break: break-all;
  min-width: 0;
  padding-left: 4px;
}

/* ── Show more ───────────────────────────────────────────────────── */

.diff-overflow-bar {
  border-top: 1px solid var(--diff-border);
  padding: 6px 12px;
}

.diff-show-more {
  background: none;
  border: 0;
  padding: 0;
  font: inherit;
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), 0.5);
  cursor: pointer;
}

.diff-show-more:hover {
  color: rgba(var(--v-theme-on-surface), 0.75);
  text-decoration: underline;
}

/* ── Collapsed state ─────────────────────────────────────────────── */

.diff-preview.collapsed .diff-body,
.diff-preview.collapsed .diff-summary-text {
  display: none;
}
</style>
