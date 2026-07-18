# CodeMirror 6 文件编辑器替换 ShikiEditor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用 CodeMirror 6 编辑器替换 ShikiEditor overlay，消除工作区文件编辑与 .gitignore 编辑的输入回显延迟。

**Architecture:** 新建自包含 `CodeMirrorEditor.vue`（API 与 ShikiEditor 逐一对齐），配套懒加载语言映射 util `codemirrorLanguages.ts`；两处调用方（GitIgnoreEditor / FileBrowserFilePreview）近替换式切换；ShikiEditor 成为死代码后删除。

**Tech Stack:** Vue 3.3 `<script setup>` + TypeScript、CodeMirror 6（@codemirror/* ^6）、Vuetify 3.7（useTheme）、vitest + happy-dom + @vue/test-utils。

**Worktree:** `F:\github\Astrbot\.worktrees\feat-codemirror-file-editor`（分支 `feat/codemirror-file-editor`，基于 `all`）。以下所有路径均相对该 worktree 根目录。

**Spec:** `docs/superpowers/specs/2026-07-18-codemirror-file-editor-design.md`

## Global Constraints

- 所有源码注释用 **English**；组件/spec 头部注释含 `Author: elecvoid243` + 日期。
- 不改 `CodemirrorHost.vue` / `DocumentEditor.vue`（文件管理页零回归）。
- 不改只读预览的 Shiki 管线（`FileBrowserCodeView`、`utils/shiki.js` 保留）。
- pnpm 严格 node_modules：源码中直接 import 的包必须是 `dashboard/package.json` 的**直接依赖**。
- vitest include 仅 `src/**/*.spec.ts`（`dashboard/tests/*.test.mjs` 不由 vitest 运行）。
- 提交信息用 conventional commits（English）。
- 组件契约（与 ShikiEditor 对齐，调用方依赖此契约）：
  - props: `modelValue: string`（dirty 基线，echo 须忽略）、`filePath: string`（仅取扩展名）
  - emits: `update:modelValue(v)`、`dirty-change(dirty)`（**仅 clean↔dirty 翻转时触发**）
  - expose: `getValue(): string`、`focus(): void`
- 字体指标：`ui-monospace, monospace` / 12.5px / line-height 1.55；根元素须撑满父容器（两处调用方分别以 `flex:1` 拉伸或定高包裹）。
- 计划偏差备忘：spec §11 写「新增 13 个依赖」，实际需要 **14 个**——`@codemirror/language` 必须列为直接依赖（pnpm 下直接 import 需要），它本已作为传递依赖存在，bundle 无增量。

---

### Task 1: 新增 CodeMirror 依赖

**Files:**
- Modify: `dashboard/package.json`（dependencies +14）
- Modify: `dashboard/pnpm-lock.yaml`（pnpm add 自动更新）

**Interfaces:**
- Consumes: 无
- Produces: 后续任务可直接 import 的 14 个包：`@codemirror/language`、`@codemirror/lang-python`、`@codemirror/lang-javascript`、`@codemirror/lang-json`、`@codemirror/lang-yaml`、`@codemirror/lang-css`、`@codemirror/lang-html`、`@codemirror/lang-xml`、`@codemirror/lang-sql`、`@codemirror/lang-rust`、`@codemirror/lang-go`、`@codemirror/lang-cpp`、`@codemirror/legacy-modes`、`@codemirror/theme-one-dark`

- [ ] **Step 1: pnpm add（在 worktree 的 dashboard 目录）**

```cmd
cd /d F:\github\Astrbot\.worktrees\feat-codemirror-file-editor\dashboard
pnpm add @codemirror/language @codemirror/lang-python @codemirror/lang-javascript @codemirror/lang-json @codemirror/lang-yaml @codemirror/lang-css @codemirror/lang-html @codemirror/lang-xml @codemirror/lang-sql @codemirror/lang-rust @codemirror/lang-go @codemirror/lang-cpp @codemirror/legacy-modes @codemirror/theme-one-dark
```

Expected: 全部解析到 ^6.x，`pnpm-lock.yaml` 更新；无 peer 依赖报错。

- [ ] **Step 2: 验证既有测试基线仍为绿色**

```cmd
cd /d F:\github\Astrbot\.worktrees\feat-codemirror-file-editor\dashboard
pnpm test
```

Expected: PASS（与加依赖前的基线一致）。

- [ ] **Step 3: Commit**

```cmd
cd /d F:\github\Astrbot\.worktrees\feat-codemirror-file-editor
git add dashboard/package.json dashboard/pnpm-lock.yaml
git commit -m "feat(dashboard): add CodeMirror 6 language packs for the file editor"
```

---

### Task 2: 语言映射 util `codemirrorLanguages.ts`

**Files:**
- Create: `dashboard/src/utils/codemirrorLanguages.ts`
- Test: `dashboard/src/utils/codemirrorLanguages.spec.ts`

**Interfaces:**
- Consumes: Task 1 的语言包
- Produces（Task 3 依赖的准确签名）:
  - `export type CmLanguageKey = "python" | "javascript" | "jsx" | "typescript" | "tsx" | "json" | "yaml" | "shell" | "css" | "html" | "xml" | "markdown" | "sql" | "rust" | "go" | "cpp" | "diff"`
  - `export function languageKeyForPath(filePath: string): CmLanguageKey | null`
  - `export function loadLanguage(key: CmLanguageKey): Promise<LanguageSupport>`（按 key 缓存 Promise；失败后清除缓存允许重试）

- [ ] **Step 1: 写失败测试 `dashboard/src/utils/codemirrorLanguages.spec.ts`**

```ts
// Author: elecvoid243, 2026-07-18
// codemirrorLanguages unit tests: the extension->key map is pure;
// loadLanguage tests use the real language packs (parser-only code,
// no DOM needed) and verify LanguageSupport instances + caching.
import { describe, expect, it } from "vitest";
import { LanguageSupport } from "@codemirror/language";
import {
  languageKeyForPath,
  loadLanguage,
} from "@/utils/codemirrorLanguages";

describe("languageKeyForPath", () => {
  it("maps core extensions to their language keys", () => {
    expect(languageKeyForPath("a/b/main.py")).toBe("python");
    expect(languageKeyForPath("x.TS")).toBe("typescript");
    expect(languageKeyForPath("comp.tsx")).toBe("tsx");
    expect(languageKeyForPath("comp.jsx")).toBe("jsx");
    expect(languageKeyForPath("data.json")).toBe("json");
    expect(languageKeyForPath("ci.yml")).toBe("yaml");
    expect(languageKeyForPath("run.sh")).toBe("shell");
    expect(languageKeyForPath("App.vue")).toBe("html");
    expect(languageKeyForPath("icon.svg")).toBe("xml");
    expect(languageKeyForPath("README.md")).toBe("markdown");
    expect(languageKeyForPath("q.sql")).toBe("sql");
    expect(languageKeyForPath("lib.rs")).toBe("rust");
    expect(languageKeyForPath("main.go")).toBe("go");
    expect(languageKeyForPath("a.c")).toBe("cpp");
    expect(languageKeyForPath("a.hpp")).toBe("cpp");
    expect(languageKeyForPath("fix.patch")).toBe("diff");
  });

  it("returns null for unmapped or extension-less paths", () => {
    expect(languageKeyForPath(".gitignore")).toBeNull();
    expect(languageKeyForPath("notes.ini")).toBeNull();
    expect(languageKeyForPath("Makefile")).toBeNull();
    expect(languageKeyForPath("")).toBeNull();
  });
});

describe("loadLanguage", () => {
  it("loads a real LanguageSupport and caches the promise", async () => {
    const a = loadLanguage("python");
    const b = loadLanguage("python");
    expect(a).toBe(b); // same cached promise
    const support = await a;
    expect(support).toBeInstanceOf(LanguageSupport);
  });

  it("loads StreamLanguage-backed keys (shell/diff)", async () => {
    await expect(loadLanguage("shell")).resolves.toBeInstanceOf(
      LanguageSupport,
    );
    await expect(loadLanguage("diff")).resolves.toBeInstanceOf(
      LanguageSupport,
    );
  });
});
```

- [ ] **Step 2: 运行确认失败**

```cmd
cd /d F:\github\Astrbot\.worktrees\feat-codemirror-file-editor\dashboard
pnpm vitest run src/utils/codemirrorLanguages.spec.ts
```

Expected: FAIL（模块 `@/utils/codemirrorLanguages` 不存在）。

- [ ] **Step 3: 实现 `dashboard/src/utils/codemirrorLanguages.ts`**

```ts
// Author: elecvoid243, 2026-07-18
// Spec: docs/superpowers/specs/2026-07-18-codemirror-file-editor-design.md §4
// Extension -> CodeMirror language key map + lazy language-pack loaders.
// Every loader is a dynamic import so no language pack enters the initial
// bundle; resolved LanguageSupport instances are cached per key. Unmapped
// extensions return null -> the editor mounts as plain text (e.g. .gitignore).

import {
  LanguageSupport,
  StreamLanguage,
} from "@codemirror/language";

export type CmLanguageKey =
  | "python"
  | "javascript"
  | "jsx"
  | "typescript"
  | "tsx"
  | "json"
  | "yaml"
  | "shell"
  | "css"
  | "html"
  | "xml"
  | "markdown"
  | "sql"
  | "rust"
  | "go"
  | "cpp"
  | "diff";

const EXT_TO_KEY: Record<string, CmLanguageKey> = {
  ".py": "python",
  ".js": "javascript",
  ".mjs": "javascript",
  ".cjs": "javascript",
  ".jsx": "jsx",
  ".ts": "typescript",
  ".tsx": "tsx",
  ".json": "json",
  ".yaml": "yaml",
  ".yml": "yaml",
  ".sh": "shell",
  ".bash": "shell",
  ".zsh": "shell",
  ".css": "css",
  ".html": "html",
  ".htm": "html",
  // Approximation: template highlights well; <script> coloring is coarse.
  ".vue": "html",
  ".xml": "xml",
  ".svg": "xml",
  ".md": "markdown",
  ".sql": "sql",
  ".rs": "rust",
  ".go": "go",
  // lang-cpp also covers plain C.
  ".c": "cpp",
  ".h": "cpp",
  ".cpp": "cpp",
  ".cc": "cpp",
  ".cxx": "cpp",
  ".hpp": "cpp",
  ".c++": "cpp",
  ".diff": "diff",
  ".patch": "diff",
};

/**
 * Resolve a file path to a CM language key (extension-only, case-insensitive).
 * Returns null for unmapped extensions -> caller edits as plain text.
 */
export function languageKeyForPath(filePath: string): CmLanguageKey | null {
  const m = String(filePath || "").match(/\.([\w+]+)$/i);
  if (!m) return null;
  return EXT_TO_KEY["." + m[1].toLowerCase()] ?? null;
}

const loaders: Record<CmLanguageKey, () => Promise<LanguageSupport>> = {
  python: async () => (await import("@codemirror/lang-python")).python(),
  javascript: async () =>
    (await import("@codemirror/lang-javascript")).javascript(),
  jsx: async () =>
    (await import("@codemirror/lang-javascript")).javascript({ jsx: true }),
  typescript: async () =>
    (await import("@codemirror/lang-javascript")).javascript({
      typescript: true,
    }),
  tsx: async () =>
    (await import("@codemirror/lang-javascript")).javascript({
      jsx: true,
      typescript: true,
    }),
  json: async () => (await import("@codemirror/lang-json")).json(),
  yaml: async () => (await import("@codemirror/lang-yaml")).yaml(),
  shell: async () =>
    new LanguageSupport(
      StreamLanguage.define(
        (await import("@codemirror/legacy-modes/mode/shell")).shell,
      ),
    ),
  css: async () => (await import("@codemirror/lang-css")).css(),
  html: async () => (await import("@codemirror/lang-html")).html(),
  xml: async () => (await import("@codemirror/lang-xml")).xml(),
  markdown: async () => (await import("@codemirror/lang-markdown")).markdown(),
  sql: async () => (await import("@codemirror/lang-sql")).sql(),
  rust: async () => (await import("@codemirror/lang-rust")).rust(),
  go: async () => (await import("@codemirror/lang-go")).go(),
  cpp: async () => (await import("@codemirror/lang-cpp")).cpp(),
  diff: async () =>
    new LanguageSupport(
      StreamLanguage.define(
        (await import("@codemirror/legacy-modes/mode/diff")).diff,
      ),
    ),
};

const cache = new Map<CmLanguageKey, Promise<LanguageSupport>>();

/**
 * Lazily import + instantiate the language pack for a key. The promise is
 * cached per key; a rejected load is evicted so a later attempt can retry
 * (the caller falls back to plain text for the current session on failure).
 */
export function loadLanguage(key: CmLanguageKey): Promise<LanguageSupport> {
  const hit = cache.get(key);
  if (hit) return hit;
  const p = loaders[key]();
  cache.set(key, p);
  p.catch(() => cache.delete(key));
  return p;
}
```

- [ ] **Step 4: 运行确认通过**

```cmd
cd /d F:\github\Astrbot\.worktrees\feat-codemirror-file-editor\dashboard
pnpm vitest run src/utils/codemirrorLanguages.spec.ts
```

Expected: PASS（2 suites / 4 tests）。

- [ ] **Step 5: Commit**

```cmd
cd /d F:\github\Astrbot\.worktrees\feat-codemirror-file-editor
git add dashboard/src/utils/codemirrorLanguages.ts dashboard/src/utils/codemirrorLanguages.spec.ts
git commit -m "feat(dashboard): add lazy CodeMirror language mapping for file editing"
```

---

### Task 3: `CodeMirrorEditor.vue` 组件

**Files:**
- Create: `dashboard/src/components/chat/message_list_comps/CodeMirrorEditor.vue`
- Test: `dashboard/src/components/chat/message_list_comps/CodeMirrorEditor.spec.ts`

**Interfaces:**
- Consumes: Task 2 的 `languageKeyForPath` / `loadLanguage`；Task 1 的 CM 核心包 + `@codemirror/theme-one-dark`
- Produces（Task 4/5 依赖的准确契约）:
  - default export Vue 组件 `CodeMirrorEditor`
  - props: `{ modelValue: string; filePath: string }`
  - emits: `(e: "update:modelValue", v: string)`、`(e: "dirty-change", dirty: boolean)`（仅翻转）
  - expose: `getValue(): string`、`focus(): void`
  - CM 核心模块加载失败时内部降级为原生 textarea（契约不变）

- [ ] **Step 1: 写失败测试 `dashboard/src/components/chat/message_list_comps/CodeMirrorEditor.spec.ts`**

策略：vitest 中 mock `@codemirror/state` 使其 import 抛错 → 组件走**原生 textarea 降级路径**，在 happy-dom 中确定性地验证完整契约（镜像被删 ShikiEditor.spec.ts 的断言面）。真实 CM 路径由 Task 6 手测清单覆盖。

```ts
// Author: elecvoid243, 2026-07-18
// CodeMirrorEditor unit tests: @codemirror/state is mocked to throw on
// import, forcing the component's plain-textarea fallback path. That path
// implements the FULL public contract (update:modelValue, transition-only
// dirty-change, echo suppression, external adoption, getValue/focus), so
// it is tested deterministically in happy-dom. The real CM mount path is
// covered by the manual checklist (plan Task 6).
import { flushPromises, mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";

vi.mock("@codemirror/state", () => {
  throw new Error("CM unavailable in unit tests");
});

import CodeMirrorEditor from "./CodeMirrorEditor.vue";

async function mountEditor(modelValue = "") {
  const w = mount(CodeMirrorEditor, {
    props: { modelValue, filePath: "test.txt" },
  });
  // Let the failed dynamic import settle so the fallback textarea renders.
  await flushPromises();
  return w;
}

describe("CodeMirrorEditor (textarea fallback)", () => {
  it("typing emits update:modelValue and getValue returns the buffer", async () => {
    const w = await mountEditor("ab");
    const ta = w.find("textarea");
    expect(ta.exists()).toBe(true);
    expect((ta.element as HTMLTextAreaElement).value).toBe("ab");
    await ta.setValue("abc");
    expect(w.emitted("update:modelValue")?.at(-1)).toEqual(["abc"]);
    expect(w.vm.getValue()).toBe("abc");
  });

  it("emits dirty-change only on transitions (clean->dirty->clean)", async () => {
    const w = await mountEditor("");
    const ta = w.find("textarea");
    await ta.setValue("x");
    await ta.setValue("xy");
    expect(w.emitted("dirty-change")).toEqual([[true]]);
    await ta.setValue("");
    expect(w.emitted("dirty-change")).toEqual([[true], [false]]);
  });

  it("ignores echo prop updates but adopts external replacements", async () => {
    const w = await mountEditor("ab");
    const ta = w.find("textarea");
    await ta.setValue("abc");
    // Echo: parent mirrors our own emission back — buffer must stay.
    await w.setProps({ modelValue: "abc" });
    expect((ta.element as HTMLTextAreaElement).value).toBe("abc");
    // External replacement (file reloaded) — buffer adopts it and the
    // dirty baseline resets (dirty-change flips back to clean).
    await w.setProps({ modelValue: "zzz" });
    expect((ta.element as HTMLTextAreaElement).value).toBe("zzz");
    expect(w.vm.getValue()).toBe("zzz");
    expect(w.emitted("dirty-change")?.at(-1)).toEqual([false]);
  });

  it("exposes focus() without throwing", async () => {
    const w = await mountEditor("x");
    expect(() => w.vm.focus()).not.toThrow();
  });
});
```

- [ ] **Step 2: 运行确认失败**

```cmd
cd /d F:\github\Astrbot\.worktrees\feat-codemirror-file-editor\dashboard
pnpm vitest run src/components/chat/message_list_comps/CodeMirrorEditor.spec.ts
```

Expected: FAIL（组件 `./CodeMirrorEditor.vue` 不存在）。

- [ ] **Step 3: 实现 `dashboard/src/components/chat/message_list_comps/CodeMirrorEditor.vue`**

```vue
<!-- Author: elecvoid243
     Date: 2026-07-18
     Spec: docs/superpowers/specs/2026-07-18-codemirror-file-editor-design.md
     CodeMirror 6 file editor — drop-in replacement for the former
     ShikiEditor overlay (identical props/emits/expose contract).

     Why CM6: the Shiki overlay painted text through a debounced
     highlight layer (transparent textarea on top), which forced a
     200ms+ echo delay on every keystroke and re-tokenized the whole
     document per pause. CM6 renders text directly with incremental
     parsing + a virtual viewport, so typing echo is immediate even
     on large files.

     Contract notes (callers rely on these):
     - The per-keystroke buffer lives INSIDE this component; parents
       never listen to update:modelValue (GitIgnoreEditor /
       FileBrowserFilePreview only use dirty-change + getValue()).
     - dirty-change fires ONLY on clean<->dirty transitions.
     - modelValue is the authoritative baseline: external replacements
       are adopted; own echoes (=== lastEmitted) are ignored.
     - If the CM core modules fail to load, the component silently
       degrades to a plain textarea implementing the same contract. -->
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useTheme } from "vuetify";
import { languageKeyForPath, loadLanguage } from "@/utils/codemirrorLanguages";

const props = defineProps<{
  /** Authoritative loaded content (the dirty baseline). Set once per
   *  editing session; external replacements are adopted, own echoes
   *  are ignored. */
  modelValue: string;
  /** Only the extension is used (CM language detection). */
  filePath: string;
}>();
const emit = defineEmits<{
  (e: "update:modelValue", v: string): void;
  /** Fires ONLY on clean<->dirty transitions (buffer vs modelValue). */
  (e: "dirty-change", dirty: boolean): void;
}>();

// Dark-mode detection via Vuetify (reactive, hot-swapped through a CM
// Compartment). Falls back to light when no Vuetify app is injected
// (unit tests mount the component bare).
let isDark = ref(false);
try {
  const theme = useTheme();
  isDark = computed(() => theme.current.value.dark);
} catch {
  // No Vuetify in context — stay on the light theme.
}

const hostEl = ref<HTMLElement | null>(null);
const textareaRef = ref<HTMLTextAreaElement | null>(null);
/** True when the CM core modules failed to load -> plain textarea. */
const cmFailed = ref(false);

// CM view instance. Typed as any to keep this file free of CM type
// imports; the few fields touched (destroy / state.doc / dispatch /
// focus) are stable across CM6 minor versions.
let view: any = null;
/** Last content WE emitted upward; a modelValue update equal to this
 *  is our own echo and must not reset the buffer. */
let lastEmitted: string | null = null;
let lastDirty = false;
let destroyed = false;

// Buffer for the textarea fallback path (the CM path keeps its buffer
// inside the EditorView document).
const buffer = ref(props.modelValue);

function checkDirty(doc: string): void {
  const d = doc !== props.modelValue;
  if (d !== lastDirty) {
    lastDirty = d;
    emit("dirty-change", d);
  }
}

onMounted(async () => {
  if (!hostEl.value) return;
  try {
    const [
      { EditorState, Compartment },
      { EditorView, keymap, lineNumbers, highlightActiveLine },
      { defaultKeymap, history, historyKeymap, indentWithTab },
      { indentUnit, syntaxHighlighting, defaultHighlightStyle },
      { oneDark },
    ] = await Promise.all([
      import("@codemirror/state"),
      import("@codemirror/view"),
      import("@codemirror/commands"),
      import("@codemirror/language"),
      import("@codemirror/theme-one-dark"),
    ]);
    if (destroyed || !hostEl.value) return;

    const themeComp = new Compartment();
    const langComp = new Compartment();
    const themeExt = (dark: boolean) =>
      dark
        ? oneDark
        : syntaxHighlighting(defaultHighlightStyle, { fallback: true });

    // Font metrics + sizing mirror the former ShikiEditor / the
    // read-only FileBrowserCodeView so edit <-> preview stays visually
    // continuous. Colors come from oneDark / defaultHighlightStyle.
    const baseTheme = EditorView.theme({
      "&": { height: "100%", fontSize: "12.5px" },
      ".cm-scroller": {
        fontFamily: "ui-monospace, monospace",
        lineHeight: "1.55",
      },
      ".cm-gutters": { backgroundColor: "transparent", border: "none" },
    });

    const state = EditorState.create({
      doc: props.modelValue,
      extensions: [
        lineNumbers(),
        highlightActiveLine(),
        history(),
        indentUnit.of("  "),
        keymap.of([...defaultKeymap, ...historyKeymap, indentWithTab]),
        baseTheme,
        themeComp.of(themeExt(isDark.value)),
        langComp.of([]),
        EditorView.updateListener.of((u: any) => {
          if (!u.docChanged) return;
          const doc = u.state.doc.toString();
          lastEmitted = doc;
          emit("update:modelValue", doc);
          checkDirty(doc);
        }),
      ],
    });
    view = new EditorView({ state, parent: hostEl.value });
    lastEmitted = props.modelValue;

    // Hot-swap the theme when the Vuetify dark flag flips.
    watch(isDark, (dark) => {
      if (!view) return;
      view.dispatch({ effects: themeComp.reconfigure(themeExt(dark)) });
    });

    // Lazy-load the language pack; failure degrades to plain text.
    const key = languageKeyForPath(props.filePath);
    if (key) {
      try {
        const support = await loadLanguage(key);
        if (!destroyed && view) {
          view.dispatch({ effects: langComp.reconfigure(support) });
        }
      } catch (err) {
        console.warn(
          `CodeMirror language "${key}" failed to load; editing as plain text:`,
          err,
        );
      }
    }
  } catch (err) {
    console.error(
      "CodeMirror init failed; falling back to plain textarea:",
      err,
    );
    cmFailed.value = true;
  }
});

// Adopt EXTERNAL modelValue replacements (e.g. the parent reloaded the
// file). Own echoes are ignored — they carry nothing new and would risk
// clobbering keystrokes that arrived between emit and parent re-render.
watch(
  () => props.modelValue,
  (v) => {
    if (v === lastEmitted) return;
    lastEmitted = null;
    if (view) {
      const cur = view.state.doc.toString();
      if (cur !== v) {
        // The dispatch runs the update listener, which re-emits
        // update:modelValue (harmless echo to the parent) and flips
        // dirty back to clean via checkDirty.
        view.dispatch({ changes: { from: 0, to: cur.length, insert: v } });
      } else {
        checkDirty(v);
      }
    } else {
      buffer.value = v;
      checkDirty(v);
    }
  },
);

// ── Textarea fallback path (only when cmFailed) ─────────────────────

function onInput(e: Event): void {
  const v = (e.target as HTMLTextAreaElement).value;
  buffer.value = v;
  lastEmitted = v;
  emit("update:modelValue", v);
  checkDirty(v);
}

function onKeydown(e: KeyboardEvent): void {
  // Insert two spaces instead of moving focus on Tab (mirrors the CM
  // indentWithTab behavior in the fallback path).
  if (e.key !== "Tab") return;
  e.preventDefault();
  const ta = e.target as HTMLTextAreaElement;
  const { selectionStart: s, selectionEnd: end, value } = ta;
  const next = value.slice(0, s) + "  " + value.slice(end);
  buffer.value = next;
  lastEmitted = next;
  emit("update:modelValue", next);
  checkDirty(next);
  requestAnimationFrame(() => {
    ta.selectionStart = ta.selectionEnd = s + 2;
  });
}

function getValue(): string {
  if (view) return view.state.doc.toString();
  return buffer.value;
}

function focus(): void {
  if (view) view.focus();
  else textareaRef.value?.focus();
}
defineExpose({ focus, getValue });

onBeforeUnmount(() => {
  destroyed = true;
  view?.destroy();
  view = null;
});
</script>

<template>
  <div class="cm-file-editor">
    <!-- v-show (not v-if): the mount element must exist before the
         async CM modules resolve; it simply stays empty + hidden on
         the fallback path. -->
    <div v-show="!cmFailed" ref="hostEl" class="cm-file-editor-mount"></div>
    <textarea
      v-if="cmFailed"
      ref="textareaRef"
      :value="buffer"
      class="cm-file-editor-fallback"
      spellcheck="false"
      autocapitalize="off"
      autocomplete="off"
      autocorrect="off"
      wrap="off"
      @input="onInput"
      @keydown="onKeydown"
    ></textarea>
  </div>
</template>

<style scoped>
.cm-file-editor {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.cm-file-editor-mount {
  flex: 1;
  min-height: 0;
}
.cm-file-editor-mount :deep(.cm-editor) {
  height: 100%;
}
.cm-file-editor-fallback {
  flex: 1;
  width: 100%;
  resize: none;
  border: 0;
  outline: none;
  padding: 8px 14px;
  font-family: ui-monospace, monospace;
  font-size: 12.5px;
  line-height: 1.55;
  tab-size: 2;
  background: rgb(var(--v-theme-surface));
  color: rgb(var(--v-theme-on-surface));
}
</style>
```

- [ ] **Step 4: 运行确认通过**

```cmd
cd /d F:\github\Astrbot\.worktrees\feat-codemirror-file-editor\dashboard
pnpm vitest run src/components/chat/message_list_comps/CodeMirrorEditor.spec.ts
```

Expected: PASS（4 tests）。

- [ ] **Step 5: 类型检查**

```cmd
cd /d F:\github\Astrbot\.worktrees\feat-codemirror-file-editor\dashboard
pnpm typecheck
```

Expected: 无新增错误（若有既存错误，对比基线确认非本任务引入）。

- [ ] **Step 6: Commit**

```cmd
cd /d F:\github\Astrbot\.worktrees\feat-codemirror-file-editor
git add dashboard/src/components/chat/message_list_comps/CodeMirrorEditor.vue dashboard/src/components/chat/message_list_comps/CodeMirrorEditor.spec.ts
git commit -m "feat(dashboard): add CodeMirrorEditor file editing component"
```

---

### Task 4: GitIgnoreEditor 切换 + 更新其 spec

**Files:**
- Modify: `dashboard/src/components/chat/message_list_comps/GitIgnoreEditor.vue`（import/ref 类型/template 标签/注释，~5 处）
- Modify: `dashboard/src/components/chat/message_list_comps/GitIgnoreEditor.spec.ts`（mock 目标由 shiki 换成 CodeMirrorEditor stub）

**Interfaces:**
- Consumes: Task 3 的 `CodeMirrorEditor`（契约见 Task 3 Produces）
- Produces: 无新接口

- [ ] **Step 1: 更新 spec 的 mock（先改测试）**

`GitIgnoreEditor.spec.ts`：删除 `vi.mock("@/utils/shiki", ...)` 整块，替换为对 CodeMirrorEditor 的 stub（stub 提供与真实组件一致的契约，textarea 驱动 dirty）：

```ts
// CodeMirrorEditor stub: mirrors the real component's contract
// (uncontrolled buffer, transition-only dirty-change, getValue expose)
// while staying a cheap <textarea> for happy-dom.
vi.mock("./CodeMirrorEditor.vue", async () => {
  const { computed, defineComponent, ref, watch } = await import("vue");
  const CodeMirrorEditorStub = defineComponent({
    props: {
      modelValue: { type: String, default: "" },
      filePath: { type: String, default: "" },
    },
    emits: ["update:modelValue", "dirty-change"],
    setup(props, { emit, expose }) {
      const buffer = ref(props.modelValue);
      const dirty = computed(() => buffer.value !== props.modelValue);
      watch(dirty, (d) => emit("dirty-change", d));
      function onInput(e: Event) {
        const v = (e.target as HTMLTextAreaElement).value;
        buffer.value = v;
        emit("update:modelValue", v);
      }
      expose({ getValue: () => buffer.value, focus: () => {} });
      return { buffer, onInput };
    },
    template: '<textarea :value="buffer" @input="onInput" />',
  });
  return { default: CodeMirrorEditorStub };
});
```

同时：文件头注释中 "Uses the real ShikiEditor with the shiki util mocked" 更新为 "Uses a CodeMirrorEditor stub mirroring the real contract"；import 行补 `defineComponent, computed, ref, watch`（来自 "vue"）；`setEditorDirty` 注释里的 "real ShikiEditor" 改为 "stubbed CodeMirrorEditor"。

- [ ] **Step 2: 运行确认当前失败**

```cmd
cd /d F:\github\Astrbot\.worktrees\feat-codemirror-file-editor\dashboard
pnpm vitest run src/components/chat/message_list_comps/GitIgnoreEditor.spec.ts
```

Expected: FAIL（GitIgnoreEditor.vue 仍 import ShikiEditor；shiki mock 已删，真实 ShikiEditor 挂载会尝试加载真实 Shiki 高亮器 → 报错）。

- [ ] **Step 3: 切换 `GitIgnoreEditor.vue`（精确改动 5 处）**

1. `import ShikiEditor from "./ShikiEditor.vue";` → `import CodeMirrorEditor from "./CodeMirrorEditor.vue";`
2. `const editorRef = ref<InstanceType<typeof ShikiEditor> | null>(null);` → `ref<InstanceType<typeof CodeMirrorEditor> | null>(null)`
3. 注释 `dirtiness arrives on TRANSITIONS only (ShikiEditor dirty-change)` 中 `ShikiEditor` → `CodeMirrorEditor`
4. props 注释 `editing buffer lives INSIDE ShikiEditor (uncontrolled)` 中 `ShikiEditor` → `CodeMirrorEditor`
5. template `<ShikiEditor ... />` → `<CodeMirrorEditor ... />`（属性/事件不变）

- [ ] **Step 4: 运行确认通过**

```cmd
cd /d F:\github\Astrbot\.worktrees\feat-codemirror-file-editor\dashboard
pnpm vitest run src/components/chat/message_list_comps/GitIgnoreEditor.spec.ts
```

Expected: PASS（7 tests）。

- [ ] **Step 5: Commit**

```cmd
cd /d F:\github\Astrbot\.worktrees\feat-codemirror-file-editor
git add dashboard/src/components/chat/message_list_comps/GitIgnoreEditor.vue dashboard/src/components/chat/message_list_comps/GitIgnoreEditor.spec.ts
git commit -m "feat(dashboard): switch gitignore editor to CodeMirrorEditor"
```

---

### Task 5: FileBrowserFilePreview 切换

**Files:**
- Modify: `dashboard/src/components/chat/message_list_comps/FileBrowserFilePreview.vue`（import/ref 类型/template 标签/注释，~5 处）

**Interfaces:**
- Consumes: Task 3 的 `CodeMirrorEditor`
- Produces: 无新接口

- [ ] **Step 1: 精确改动**

1. `import ShikiEditor from "./ShikiEditor.vue";` → `import CodeMirrorEditor from "./CodeMirrorEditor.vue";`
2. `const editorRef = ref<InstanceType<typeof ShikiEditor> | null>(null);` → `ref<InstanceType<typeof CodeMirrorEditor> | null>(null)`
3. 区块注释（~379-389 行）`The editor body is <ShikiEditor>, an overlay that reuses the preview's Shiki pipeline for highlighting.` → `The editor body is <CodeMirrorEditor> (CM6; lazy language packs, dark-aware theme).`；`the per-keystroke buffer lives INSIDE ShikiEditor (uncontrolled textarea)` 中 `ShikiEditor` → `CodeMirrorEditor`
4. template（~1128 行）`<ShikiEditor ... class="preview-editor-body" ... />` → `<CodeMirrorEditor ... />`（属性/事件/class 不变）

- [ ] **Step 2: 全量测试 + 类型检查**

```cmd
cd /d F:\github\Astrbot\.worktrees\feat-codemirror-file-editor\dashboard
pnpm test
pnpm typecheck
```

Expected: vitest 全绿；typecheck 无 `ShikiEditor` 残留引用报错。

- [ ] **Step 3: Commit**

```cmd
cd /d F:\github\Astrbot\.worktrees\feat-codemirror-file-editor
git add dashboard/src/components/chat/message_list_comps/FileBrowserFilePreview.vue
git commit -m "feat(dashboard): switch workspace file editor to CodeMirrorEditor"
```

---

### Task 6: 删除 ShikiEditor + 全量验证

**Files:**
- Delete: `dashboard/src/components/chat/message_list_comps/ShikiEditor.vue`
- Delete: `dashboard/src/components/chat/message_list_comps/ShikiEditor.spec.ts`

**Interfaces:**
- Consumes: 无
- Produces: 无

- [ ] **Step 1: 确认无残留引用**

```cmd
cd /d F:\github\Astrbot\.worktrees\feat-codemirror-file-editor\dashboard
findstr /s /i /m "ShikiEditor" src\*.*
```

Expected: 无输出（若有遗漏文件，先改完再继续）。

- [ ] **Step 2: 删除（git rm 同时暂存）**

```cmd
cd /d F:\github\Astrbot\.worktrees\feat-codemirror-file-editor
git rm dashboard/src/components/chat/message_list_comps/ShikiEditor.vue dashboard/src/components/chat/message_list_comps/ShikiEditor.spec.ts
```

- [ ] **Step 3: 全量验证**

```cmd
cd /d F:\github\Astrbot\.worktrees\feat-codemirror-file-editor\dashboard
pnpm test
pnpm build
```

Expected: vitest 全绿；`pnpm build`（subset-mdi-font + vue-tsc --noEmit + vite build）成功——vite build 同时验证动态 import 的语言包正确分包。

- [ ] **Step 4: Commit**

```cmd
cd /d F:\github\Astrbot\.worktrees\feat-codemirror-file-editor
git commit -m "refactor(dashboard): remove the superseded ShikiEditor overlay component"
```

- [ ] **Step 5: 手测清单（dev server + 真实浏览器）**

```cmd
cd /d F:\github\Astrbot\.worktrees\feat-codemirror-file-editor\dashboard
pnpm dev
```

对照 spec §10：
1. 工作区编辑 `.py` / `.md` / `.json` / `.yaml`：打字回显即时（无 200ms 延迟感）、高亮正确、行号显示、Tab 缩进 2 空格、Ctrl+Z 撤销、dirty 圆点、保存/取消正常
2. Git 变更页 `.gitignore`：纯文本编辑、回显即时、保存后 diff 列表刷新
3. 明/暗主题切换：编辑器配色即时跟随（oneDark ⇄ defaultHighlightStyle）
4. 中文 IME 输入：composition 正常上屏、无吞字
5. 大文件（~90KB / 数千行）：连续打字流畅、滚动流畅
6. 未映射扩展名（如 `.ini`）：纯文本编辑正常

---

## Self-Review 记录

- **Spec 覆盖**：§3 组件契约 → Task 3；§4 语言映射 → Task 2；§5 主题 → Task 3（useTheme + Compartment）；§6 编辑行为 → Task 3（行号/indentWithTab/history/echo 抑制）+ Task 6 手测；§7 边界 → Task 3（destroyed flag）+ Task 6；§8 错误处理 → Task 2（缓存驱逐）/ Task 3（console.warn + cmFailed + try/catch useTheme）；§10 测试 → 各 Task spec + Task 6 手测清单；§11 改动清单 → Task 1-6 全覆盖。
- **Placeholder 扫描**：无 TBD/TODO；所有代码步骤含完整代码。
- **执行偏差记录**：Task 4 中 stub 须定义在 `vi.mock` async 工厂内部（vi.mock 提升导致顶层 const 处于 TDZ）；plan 代码已同步。Task 2 实施中发现 `StreamLanguage.define()` 返回 `Language` 而非 `LanguageSupport`，shell/diff loader 已按 CM6 API 修正为 `new LanguageSupport(StreamLanguage.define(...))`（plan 代码已同步）。
- **类型一致性**：`languageKeyForPath` / `loadLanguage` / `CmLanguageKey`（Task 2 定义 → Task 3 import）；`getValue` / `focus` / `dirty-change`（Task 3 定义 → Task 4/5 调用方 + stub 复刻）；stub 的 props/emits/expose 与真实组件逐一对应。
