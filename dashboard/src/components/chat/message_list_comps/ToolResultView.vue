<template>
  <div class="tool-result-view">
    <!-- ── file_read_tool ──────────────────────────────────────── -->
    <template v-if="toolName === 'astrbot_file_read_tool'">
      <div class="result-header">
        <v-icon size="14" class="result-header-icon">mdi-file-document-outline</v-icon>
        <span class="result-header-text">{{ readFilePath }}</span>
        <span v-if="readFileRange" class="result-header-meta">{{ readFileRange }}</span>
      </div>
      <div
        v-if="shikiReady && detectedLanguage !== 'text'"
        class="result-code result-code-shiki"
        v-html="highlightedCode"
      ></div>
      <pre v-else class="result-code">{{ readFileContent }}</pre>
    </template>

    <!-- ── file_write_tool ─────────────────────────────────────── -->
    <template v-else-if="toolName === 'astrbot_file_write_tool'">
      <div class="result-status" :class="resultOk ? 'success' : 'error'">
        <v-icon size="16">{{ resultOk ? 'mdi-check-circle' : 'mdi-alert-circle' }}</v-icon>
        <span>{{ resultOk ? writeFilePath : resultText }}</span>
      </div>
    </template>

    <!-- ── grep_tool ───────────────────────────────────────────── -->
    <template v-else-if="toolName === 'astrbot_grep_tool'">
      <div v-if="grepLines.length" class="result-header">
        <v-icon size="14" class="result-header-icon">mdi-magnify</v-icon>
        <span class="result-header-text">Found {{ grepLines.length }} match(es)</span>
      </div>
      <div v-if="grepLines.length" class="grep-results">
        <div
          v-for="(line, i) in grepLines"
          :key="i"
          class="grep-line"
        >
          <span v-if="line.file" class="grep-file">{{ line.file }}</span>
          <span v-if="line.lineno" class="grep-lineno">{{ line.lineno }}</span>
          <span class="grep-text">{{ line.text }}</span>
        </div>
      </div>
      <div v-if="grepTruncated" class="result-truncated">{{ grepTruncated }}</div>
    </template>

    <!-- ── execute_shell ───────────────────────────────────────── -->
    <template v-else-if="toolName === 'astrbot_execute_shell'">
      <div class="shell-result">
        <div class="shell-row">
          <span class="shell-label">Stdout</span>
          <pre class="shell-value" v-text="shellStdout"></pre>
        </div>
        <div v-if="shellStderr" class="shell-row shell-stderr">
          <span class="shell-label">Stderr</span>
          <pre class="shell-value shell-stderr-text" v-text="shellStderr"></pre>
        </div>
        <div class="shell-row">
          <span class="shell-label">Exit code</span>
          <span class="shell-exit-code" :class="shellExitCodeVal === 0 ? 'success' : 'error'">{{ shellExitCodeVal }}</span>
        </div>
      </div>
      <div v-if="shellExtra" class="shell-extra-text">{{ shellExtra }}</div>
    </template>

    <!-- ── fallback ────────────────────────────────────────────── -->
    <template v-else>
      <pre class="result-raw">{{ formattedResult }}</pre>
    </template>

    <!-- ── shared [SYSTEM NOTICE] suffix (exclude shell which handles it separately) ── -->
    <div v-if="resultSuffix && toolName !== 'astrbot_execute_shell'" class="result-suffix">{{ resultSuffix }}</div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import {
  ensureShikiLanguages,
  escapeHtml,
  renderShikiCode,
} from "@/utils/shiki";

const props = defineProps<{
  toolName: string;
  result: string;
  toolArgs?: Record<string, any>;
}>();

// ── Shiki syntax highlighting ─────────────────────────────────────

const EXT_TO_LANG: Record<string, string> = {
  ".py": "python",
  ".js": "javascript",
  ".mjs": "javascript",
  ".cjs": "javascript",
  ".ts": "typescript",
  ".tsx": "tsx",
  ".jsx": "jsx",
  ".vue": "vue",
  ".json": "json",
  ".yaml": "yaml",
  ".yml": "yaml",
  ".sh": "bash",
  ".bash": "bash",
  ".zsh": "bash",
  ".css": "css",
  ".html": "html",
  ".htm": "html",
  ".xml": "xml",
  ".svg": "xml",
  ".md": "markdown",
  ".sql": "sql",
  ".java": "java",
  ".ini": "ini",
  ".diff": "diff",
  ".patch": "diff",
  ".ps1": "powershell",
  ".dockerfile": "dockerfile",
  ".txt": "text",
  // C / C++ / Go / Rust
  ".c": "c",
  ".h": "c",
  ".cpp": "cpp",
  ".cc": "cpp",
  ".cxx": "cpp",
  ".hpp": "cpp",
  ".c++": "cpp",
  ".go": "go",
  ".rs": "rust",
};

function detectLanguage(filePath: string): string {
  const m = filePath.match(/\.([\w]+)$/i);
  if (!m) return "text";
  const key = "." + m[1].toLowerCase();
  return EXT_TO_LANG[key] || "text";
}

const shikiHighlighter = ref<any>(null);
const shikiReady = ref(false);

// ── helpers ──────────────────────────────────────────────────────

const rawResult = computed(() => (props.result ?? "").trim());

// Strip [SYSTEM NOTICE] suffix for all non-shell templates.
// Shell uses rawResult directly via brace-tracking in shellParsed.
const resultText = computed(() => {
  const text = rawResult.value;
  const idx = text.search(/\[SYSTEM NOTICE\]/i);
  if (idx < 0) return text;
  return text.slice(0, idx).trim();
});

const resultSuffix = computed(() => {
  const text = rawResult.value;
  const idx = text.search(/\[SYSTEM NOTICE\]/i);
  if (idx < 0) return null;
  return text.slice(idx).trim();
});

const resultOk = computed(() => {
  const t = resultText.value.toLowerCase();
  return t.includes("success") || t.includes("successfully") || t.startsWith("file written") || t.startsWith("file uploaded") || t.startsWith("file downloaded");
});

const formattedResult = computed(() => {
  if (!resultText.value) return "";
  try {
    return JSON.stringify(JSON.parse(resultText.value), null, 2);
  } catch {
    return resultText.value;
  }
});

// ── file_read_tool ──────────────────────────────────────────────

const readFilePath = computed(() => {
  // Prefer tool args when available
  if (props.toolArgs?.path) return String(props.toolArgs.path);
  // Try to parse from a formatted header like "path (lines 0-50, 82 lines total)"
  const m = resultText.value.match(/^(.+?)\s*\(/m);
  if (m) return m[1];
  // fallback: first line of raw content
  return resultText.value.split("\n")[0]?.slice(0, 120) || "";
});

const readFileRange = computed(() => {
  // Build from args when offset/limit are provided
  if (props.toolArgs) {
    const offset = props.toolArgs.offset;
    const limit = props.toolArgs.limit;
    if (offset !== undefined || limit !== undefined) {
      const parts: string[] = [];
      if (offset !== undefined && offset !== null) parts.push(`offset ${offset}`);
      if (limit !== undefined && limit !== null) parts.push(`limit ${limit}`);
      if (parts.length) return parts.join(", ");
    }
  }
  // Fallback: parse from a formatted header
  const m = resultText.value.match(/\((Lines?\s+[\d–\-]+)/i);
  return m ? m[1] : "";
});

const readFileContent = computed(() => {
  const lines = resultText.value.split("\n");
  // Detect if the first non-empty line looks like a path+range header
  // e.g. "F:/path/to/file (Lines 0-50, 82 lines total)"
  const firstLine = lines[0]?.trim() || "";
  const hasHeader =
    /^.+?\s*\((Lines?\s+[\d–\-]+)/i.test(firstLine);
  if (hasHeader) {
    // Strip the header line and any following blank separator
    let i = 1;
    while (i < lines.length && !lines[i].trim()) i++;
    return lines.slice(i).join("\n");
  }
  // No recognizable header — show full content as-is
  return resultText.value;
});

// ── Shiki highlighting (file_read_tool) ──────────────────────────

const detectedLanguage = computed(() =>
  detectLanguage(readFilePath.value),
);

const highlightedCode = computed(() => {
  if (!shikiReady.value || !shikiHighlighter.value) return "";
  const lang = detectedLanguage.value;
  const code = readFileContent.value;
  if (!code) return "";
  try {
    return renderShikiCode(
      shikiHighlighter.value,
      code,
      lang,
      // ToolResultView doesn't receive isDark directly; Shiki's
      // default dual-theme (light/dark) output works through CSS
      // media queries, so we pass "auto" here.
      "auto",
    );
  } catch (err) {
    console.error("Failed to highlight code with Shiki:", err);
    return `<pre><code>${escapeHtml(code)}</code></pre>`;
  }
});

onMounted(async () => {
  try {
    shikiHighlighter.value = await ensureShikiLanguages();
    shikiReady.value = true;
  } catch (err) {
    console.error("Failed to initialize Shiki:", err);
  }
});

// ── file_write_tool ─────────────────────────────────────────────

const writeFilePath = computed(() => {
  const m = resultText.value.match(/^File written successfully:\s*(.+)/i);
  if (m) return m[1];
  return resultText.value;
});

// ── grep_tool ──────────────────────────────────────────────────

const grepLines = computed(() => {
  const lines = resultText.value.split("\n");
  const parsed: Array<{ file?: string; lineno?: string; text: string }> = [];
  for (const line of lines) {
    if (!line.trim()) continue;
    if (line.startsWith("[Truncated")) continue;
    // Try "file:lineno:text" pattern
    const m = line.match(/^(.+?):(\d+):(.*)$/);
    if (m) {
      parsed.push({ file: m[1], lineno: m[2], text: m[3] });
    } else {
      // Try "file-path:text" or "file:text" (ripgrep with -n)
      const m2 = line.match(/^(.+?):(\d+)[:\-](.*)$/);
      if (m2) {
        parsed.push({ file: m2[1], lineno: m2[2], text: m2[3] });
      } else {
        parsed.push({ text: line });
      }
    }
  }
  return parsed;
});

const grepTruncated = computed(() => {
  const m = resultText.value.match(/\[Truncated.+\]/);
  return m ? m[0] : "";
});

// ── execute_shell ──────────────────────────────────────────────

const shellParsed = computed(() => {
  // Extract JSON from text that may have trailing non-JSON content (e.g. [SYSTEM NOTICE]).
  const text = rawResult.value;
  const start = text.indexOf("{");
  if (start < 0) {
    return { json: null, extra: text };
  }
  // Track brace depth to find the matching closing brace
  let depth = 0;
  let end = -1;
  for (let i = start; i < text.length; i++) {
    if (text[i] === "{") depth++;
    else if (text[i] === "}") {
      depth--;
      if (depth === 0) {
        end = i + 1;
        break;
      }
    }
  }
  if (end < 0) {
    return { json: null, extra: text };
  }
  const jsonStr = text.slice(start, end);
  const extraStr = text.slice(end).trim();
  try {
    const parsed = JSON.parse(jsonStr);
    if (parsed && typeof parsed === "object") {
      return { json: parsed, extra: extraStr || null };
    }
  } catch {
    // not valid JSON
  }
  return { json: null, extra: text };
});

const shellStdout = computed(() => {
  if (shellParsed.value?.json && "stdout" in shellParsed.value.json) {
    return shellParsed.value.json.stdout;
  }
  return resultText.value;
});

const shellStderr = computed(() => {
  return shellParsed.value?.json?.stderr || "";
});

const shellExitCodeVal = computed(() => {
  if (shellParsed.value?.json && "exit_code" in shellParsed.value.json) {
    return shellParsed.value.json.exit_code;
  }
  return null;
});

const shellExtra = computed(() => {
  return shellParsed.value?.extra || null;
});

</script>

<style scoped>
.tool-result-view {
  font-size: 12px;
  line-height: 1.5;
}

/* ── Header ─────────────────────────────────────────────────── */

.result-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
  padding: 4px 8px;
  border-radius: 4px;
  background: rgba(var(--v-theme-on-surface), 0.04);
  font-size: 11.5px;
}

.result-header-icon {
  color: rgba(var(--v-theme-on-surface), 0.5);
  flex-shrink: 0;
}

.result-header-text {
  font-weight: 600;
  color: rgba(var(--v-theme-on-surface), 0.75);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}

.result-header-meta {
  color: rgba(var(--v-theme-on-surface), 0.45);
  flex-shrink: 0;
  margin-left: auto;
}

/* ── Code block ──────────────────────────────────────────────── */

.result-code {
  margin: 0;
  padding: 8px 10px;
  border-radius: 4px;
  background: rgba(var(--v-theme-on-surface), 0.04);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 11.5px;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 300px;
  overflow-y: auto;
}

/* Shiki 高亮容器 — 继承 code block 布局，清除 Shiki 默认样式 */
.result-code-shiki {
  padding: 0;
  border-radius: 6px;
  overflow: hidden;
}

.result-code-shiki :deep(pre.shiki) {
  margin: 0;
  padding: 10px 12px;
  border-radius: 6px;
  overflow: auto;
  max-height: 300px;
  font-size: 11.5px;
  line-height: 1.55;
  tab-size: 4;
}

.result-code-shiki :deep(pre.shiki code) {
  display: block;
  padding: 0;
  background: transparent;
  font-family: inherit;
  font-size: inherit;
  line-height: inherit;
}

/* ── Shell result ─────────────────────────────────────────── */

.shell-result {
  border: 1px solid rgba(var(--v-theme-on-surface), 0.1);
  border-radius: 4px;
  overflow: hidden;
}

.shell-row {
  display: flex;
  align-items: flex-start;
  padding: 3px 8px;
  font-size: 11px;
  line-height: 1.55;
}

.shell-row + .shell-row {
  border-top: 1px solid rgba(var(--v-theme-on-surface), 0.06);
}

.shell-label {
  flex-shrink: 0;
  width: 64px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 11px;
  font-weight: 600;
  color: rgba(var(--v-theme-on-surface), 0.5);
  padding-right: 8px;
}

.shell-value {
  flex: 1;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), 0.8);
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
  padding: 0;
  max-height: 200px;
  overflow-y: auto;
}

.shell-stderr {
  background: rgba(207, 34, 46, 0.04);
}

.shell-stderr-text {
  color: #cf222e;
}

.shell-exit-code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 11px;
  font-weight: 600;
}

.shell-exit-code.success {
  color: #2da44e;
}

.shell-exit-code.error {
  color: #cf222e;
}

/* ── Terminal block (deprecated, shell now uses .shell-result) ── */
.result-terminal-deprecated {}

/* ── Shell extra text (e.g. [SYSTEM NOTICE]) ────────────── */

.shell-extra-text {
  margin-top: 6px;
  padding: 4px 8px;
  border-radius: 4px;
  background: rgba(var(--v-theme-on-surface), 0.03);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 11px;
  line-height: 1.55;
  color: rgba(var(--v-theme-on-surface), 0.55);
  white-space: pre-wrap;
  word-break: break-word;
}

/* Shared [SYSTEM NOTICE] suffix for non-shell tools */
.result-suffix {
  margin-top: 6px;
  padding: 4px 8px;
  border-radius: 4px;
  background: rgba(var(--v-theme-on-surface), 0.03);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 11px;
  line-height: 1.55;
  color: rgba(var(--v-theme-on-surface), 0.55);
  white-space: pre-wrap;
  word-break: break-word;
}

/* ── Status badge ────────────────────────────────────────────── */

.result-status {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border-radius: 4px;
  font-size: 12px;
}

.result-status.success {
  background: rgba(70, 200, 70, 0.08);
  color: #2da44e;
}

.result-status.error {
  background: rgba(255, 100, 100, 0.08);
  color: #cf222e;
}

/* ── Exit code ───────────────────────────────────────────────── */

.result-exit-code {
  margin-top: 4px;
  padding: 2px 8px;
  border-radius: 3px;
  font-size: 11px;
  font-weight: 600;
  display: inline-block;
}

.result-exit-code.success {
  background: rgba(70, 200, 70, 0.1);
  color: #2da44e;
}

.result-exit-code.error {
  background: rgba(255, 100, 100, 0.1);
  color: #cf222e;
}

/* ── Grep results ────────────────────────────────────────────── */

.grep-results {
  max-height: 300px;
  overflow-y: auto;
}

.grep-line {
  display: flex;
  gap: 0;
  padding: 1px 0;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 11.5px;
  line-height: 1.55;
}

.grep-file {
  color: rgba(var(--v-theme-on-surface), 0.45);
  flex-shrink: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 140px;
  white-space: nowrap;
  padding-right: 4px;
}

.grep-lineno {
  color: rgba(var(--v-theme-on-surface), 0.35);
  flex-shrink: 0;
  min-width: 32px;
  text-align: right;
  padding-right: 6px;
}

.grep-text {
  color: rgba(var(--v-theme-on-surface), 0.8);
  white-space: pre-wrap;
  word-break: break-all;
  min-width: 0;
}

.result-truncated {
  padding: 4px 0;
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), 0.45);
  font-style: italic;
}

/* ── Raw fallback ────────────────────────────────────────────── */

.result-raw {
  margin: 0;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 11.5px;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 300px;
  overflow-y: auto;
  color: rgba(var(--v-theme-on-surface), 0.8);
}
</style>
