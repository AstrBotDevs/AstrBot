# AI-Generated Commit Message Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an "AI generate" button + 中文/EN language toggle to `GitCommitDialog.vue` that drafts a Conventional Commits message from the current staged changes via the spcode plugin's `POST /spcode/btw` endpoint.

**Architecture:** A pure, unit-tested prompt-builder module embeds the fresh staged diff (fetched on click via `GET /spcode/git-diff?scope=staged`) into a bilingual prompt; a generic `useSpcodeBtw` composable (mirroring `useSpcodeGitCommit`) calls the btw endpoint; `GitCommitDialog` orchestrates inline and fills the result into its existing textarea. The btw endpoint mounts no LLM tools, so all change content must travel inside the prompt text.

**Tech Stack:** Vue 3 `<script setup>` + Vuetify 3, TypeScript, axios (`pluginExtensionApi`), Node v24 `node --test` (type-stripping) for pure-module tests.

**Spec:** `docs/superpowers/specs/2026-07-17-commit-message-ai-generate-design.md`

## Global Constraints

- **Worktree root (all paths below are relative to it):** `F:\github\Astrbot\.worktrees\feat-commit-msg-ai-generate` — do NOT edit the main checkout at `F:\github\Astrbot`.
- Author header on every new file: `// Author: elecvoid243` + `// Date: 2026-07-17`.
- The btw HTTP response body is `ApiEnvelope` → `data` = plugin envelope `{reply?, has_context?, reason, stderr, elapsed_ms}`. Success = `reason === null` AND non-empty `reply`. There is **no** `success` flag in the real payload (the v2.20 doc's `success`/`data` framing is approximate; `tools/webapi/_helpers.py::_make_envelope` + `btw.py` are canonical).
- btw request timeout: `30_000` ms.
- Diff embed budget: `DIFF_CHAR_BUDGET = 6000` chars.
- Language persistence key: `astrbot.spcode.gitDiffSidebar.commitMsgLang` (repo `localStorage` namespace convention; supersedes the spec's `spcode:commit-msg-lang` — spec file updated accordingly).
- localStorage access must be wrapped in try/catch (private-mode safe), mirroring `safeGetItem`/`safeSetItem` in `GitDiffSidebar.vue`.
- i18n keys go under `spcodeProjectLoad.diffSidebar.gitWorkflow.commit.dialog.*` in all three locales (zh-CN, en-US, ru-RU).
- Commit messages: conventional commits, English (e.g. `feat: add ...`).
- Do NOT modify: the spcode plugin backend, `useSpcodeGitCommit.ts`, `GitCommitBar.vue`, any openapi generated client.
- Test runner facts: `node --test tests/<file>.test.mjs` from `dashboard/` (Node v24 strips types); vitest (`pnpm test`) only covers `src/**/*.spec.ts` and is untouched by this plan.

## File Structure

| File | Responsibility |
|------|----------------|
| `dashboard/src/composables/commitMessagePrompt.ts` *(new)* | Pure bilingual prompt builder (no Vue/axios imports) |
| `dashboard/tests/commitMessagePrompt.test.mjs` *(new)* | `node --test` unit tests for the builder |
| `dashboard/src/composables/useSpcodeBtw.ts` *(new)* | `POST /spcode/btw` wrapper: `{isGenerating, ask, cancel, dispose}` |
| `dashboard/src/i18n/locales/{zh-CN,en-US,ru-RU}/features/chat.json` *(modified)* | New dialog keys (`generate*`, `lang*`, `generateError.*`) |
| `dashboard/src/components/chat/message_list_comps/GitCommitDialog.vue` *(modified)* | Toggle + button UI, `onGenerate()` orchestration, cancel/unmount abort |
| `dashboard/src/components/chat/GitDiffSidebar.vue` *(modified)* | Pass `:umo` / `:worktree` to `<GitCommitDialog>` |

---

### Task 1: Prompt builder module + tests (TDD)

**Files:**
- Create: `dashboard/src/composables/commitMessagePrompt.ts`
- Test: `dashboard/tests/commitMessagePrompt.test.mjs`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: `CommitMessageLanguage = "zh" | "en"`, `CommitMessagePromptFile {path: string; status: string; additions: number; deletions: number}`, `CommitMessagePromptInput {language; files; rawDiff: string | null}`, `DIFF_CHAR_BUDGET: 6000`, `buildCommitMessagePrompt(input: CommitMessagePromptInput): string` — consumed by Task 4 and the test below.

- [ ] **Step 1: Write the failing test**

Create `dashboard/tests/commitMessagePrompt.test.mjs`:

```javascript
// Author: elecvoid243
// Date: 2026-07-17
// Spec: docs/superpowers/specs/2026-07-17-commit-message-ai-generate-design.md §Testing
//
// Verifies the bilingual commit-message prompt builder. Imports the
// .ts source directly; Node v24 strips types at import time.

import assert from "node:assert/strict";
import test from "node:test";

import {
  buildCommitMessagePrompt,
  DIFF_CHAR_BUDGET,
} from "../src/composables/commitMessagePrompt.ts";

const files = [
  { path: "src/auth.py", status: "M", additions: 42, deletions: 7 },
  { path: "tests/test_x.py", status: "A", additions: 18, deletions: 0 },
];

test("zh prompt: instruction, stats and diff sections", () => {
  const p = buildCommitMessagePrompt({
    language: "zh",
    files,
    rawDiff: "diff --git a/src/auth.py b/src/auth.py\n+line",
  });
  assert.match(p, /Conventional Commits/);
  assert.match(p, /72/);
  assert.match(p, /只返回 commit message 文本本身/);
  assert.ok(p.includes("src/auth.py (M, +42/-7)"));
  assert.ok(p.includes("tests/test_x.py (A, +18/-0)"));
  assert.ok(p.includes("diff --git a/src/auth.py"));
  assert.ok(!p.includes("(diff 已截断)"));
});

test("en prompt: instruction, stats and diff sections", () => {
  const p = buildCommitMessagePrompt({
    language: "en",
    files,
    rawDiff: "diff --git a/src/auth.py b/src/auth.py\n+line",
  });
  assert.match(p, /Conventional Commits/);
  assert.match(p, /at most 72 characters/);
  assert.match(p, /Write the message in English/);
  assert.match(p, /no Markdown code fences/);
  assert.ok(p.includes("src/auth.py (M, +42/-7)"));
  assert.ok(p.includes("diff --git a/src/auth.py"));
  assert.ok(!p.includes("(diff truncated)"));
});

test("diff longer than DIFF_CHAR_BUDGET is cut with marker", () => {
  const long = "x".repeat(DIFF_CHAR_BUDGET + 500);
  const zh = buildCommitMessagePrompt({ language: "zh", files, rawDiff: long });
  assert.ok(zh.includes("(diff 已截断)"));
  assert.ok(zh.includes("x".repeat(DIFF_CHAR_BUDGET)));
  assert.ok(!zh.includes("x".repeat(DIFF_CHAR_BUDGET + 1)));
  const en = buildCommitMessagePrompt({ language: "en", files, rawDiff: long });
  assert.ok(en.includes("(diff truncated)"));
});

test("null/empty diff: section omitted, stats-only note present", () => {
  const zh = buildCommitMessagePrompt({ language: "zh", files, rawDiff: null });
  assert.ok(!zh.includes("diff 内容:"));
  assert.ok(zh.includes("请仅根据文件统计推断改动意图"));
  const en = buildCommitMessagePrompt({ language: "en", files, rawDiff: "" });
  assert.ok(!en.includes("Diff:"));
  assert.ok(en.includes("infer the intent from the file stats only"));
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /d F:\github\Astrbot\.worktrees\feat-commit-msg-ai-generate\dashboard && node --test tests/commitMessagePrompt.test.mjs`
Expected: FAIL — `ERR_MODULE_NOT_FOUND` for `../src/composables/commitMessagePrompt.ts`.

- [ ] **Step 3: Write minimal implementation**

Create `dashboard/src/composables/commitMessagePrompt.ts`:

```typescript
// Author: elecvoid243
// Date: 2026-07-17
// Spec: docs/superpowers/specs/2026-07-17-commit-message-ai-generate-design.md §4.2
//
// Pure builder for the commit-message-generation prompt sent to
// POST /spcode/btw. No Vue / no axios — importable by node --test
// (see tests/commitMessagePrompt.test.mjs). The btw endpoint mounts
// no LLM tools, so everything the model knows about the change must
// be embedded in this prompt text.

export type CommitMessageLanguage = "zh" | "en";

export interface CommitMessagePromptFile {
  path: string;
  status: string;
  additions: number;
  deletions: number;
}

export interface CommitMessagePromptInput {
  language: CommitMessageLanguage;
  files: CommitMessagePromptFile[];
  rawDiff: string | null;
}

/**
 * Character budget for the embedded diff section. The backend git-diff
 * endpoint already truncates at its own byte cap; this second cap keeps
 * the btw prompt within a size the LLM can digest cheaply.
 */
export const DIFF_CHAR_BUDGET = 6000;

/**
 * Build the single-turn user prompt for commit message generation.
 *
 * Args:
 *   input: target language, staged file stats, and the raw unified
 *     diff text (null/empty when the backend shipped no patch, e.g.
 *     binary-only changes).
 *
 * Returns:
 *   The complete prompt string: instruction + full file-stat list +
 *   (optionally truncated) diff section.
 */
export function buildCommitMessagePrompt(
  input: CommitMessagePromptInput,
): string {
  const stats = input.files
    .map((f) => `${f.path} (${f.status}, +${f.additions}/-${f.deletions})`)
    .join("\n");

  const rawDiff = input.rawDiff?.trim() ?? "";
  const hasDiff = rawDiff.length > 0;
  const truncated = rawDiff.length > DIFF_CHAR_BUDGET;
  const diffText = truncated ? rawDiff.slice(0, DIFF_CHAR_BUDGET) : rawDiff;

  if (input.language === "zh") {
    const parts = [
      "根据以下 git 暂存区(staged)改动,生成一条 Conventional Commits 风格的 commit message。",
      "要求:",
      "1. 格式为 <type>(<可选 scope>): <subject>,type 从 feat/fix/docs/style/refactor/perf/test/build/ci/chore/revert 中选择;",
      "2. 首行(subject)不超过 72 个字符;",
      "3. message 用中文书写;",
      "4. 如改动较复杂,可在首行后空一行,用简短的要点列表补充说明;",
      "5. 只返回 commit message 文本本身,不要输出任何解释、前后缀或 Markdown 代码块。",
      "",
      "变更文件统计:",
      stats,
    ];
    if (hasDiff) {
      parts.push("", "diff 内容:", diffText + (truncated ? "\n……(diff 已截断)" : ""));
    } else {
      parts.push("", "(无可用 diff 文本,请仅根据文件统计推断改动意图。)");
    }
    return parts.join("\n");
  }

  const parts = [
    "Based on the following git staged changes, generate a Conventional Commits style commit message.",
    "Requirements:",
    "1. Format: <type>(<optional scope>): <subject>, where type is one of feat/fix/docs/style/refactor/perf/test/build/ci/chore/revert;",
    "2. The subject line must be at most 72 characters;",
    "3. Write the message in English;",
    "4. For complex changes, you may add a blank line after the subject followed by a short bullet list;",
    "5. Return only the commit message text itself — no explanations, no prefixes, no Markdown code fences.",
    "",
    "Changed files:",
    stats,
  ];
  if (hasDiff) {
    parts.push("", "Diff:", diffText + (truncated ? "\n...(diff truncated)" : ""));
  } else {
    parts.push("", "(No diff text available; infer the intent from the file stats only.)");
  }
  return parts.join("\n");
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /d F:\github\Astrbot\.worktrees\feat-commit-msg-ai-generate\dashboard && node --test tests/commitMessagePrompt.test.mjs`
Expected: PASS — 4 tests, `fail 0`.

- [ ] **Step 5: Commit**

```bash
cd /d F:\github\Astrbot\.worktrees\feat-commit-msg-ai-generate
git add dashboard/src/composables/commitMessagePrompt.ts dashboard/tests/commitMessagePrompt.test.mjs
git commit -m "feat: add bilingual commit message prompt builder"
```

---

### Task 2: `useSpcodeBtw` composable

**Files:**
- Create: `dashboard/src/composables/useSpcodeBtw.ts`

**Interfaces:**
- Consumes: `pluginExtensionApi.post` from `@/api/v1` (returns `AxiosResponse<ApiEnvelope<T>>`; inner payload at `resp.data.data`).
- Produces: `BtwParams {prompt: string; umo?: string | null}`, `BtwResult = {ok: true; reply: string; hasContext: boolean} | {ok: false; reason: string}`, `UseSpcodeBtw {isGenerating: Ref<boolean>; ask; cancel; dispose}`, `useSpcodeBtw(): UseSpcodeBtw` — consumed by Task 4. `reason` values: backend ReasonCode (`invalid_body` | `no_provider` | `empty_response` | `llm_error`) | `network` | `aborted` | `unknown`.

- [ ] **Step 1: Write the composable**

Create `dashboard/src/composables/useSpcodeBtw.ts`:

```typescript
// Author: elecvoid243
// Date: 2026-07-17
// Spec: docs/superpowers/specs/2026-07-17-commit-message-ai-generate-design.md §4.1
// API doc: astrbot_plugin_spcode_toolkit docs/api/v2.20-btw-frontend.md
//
// Vue composable wrapping POST /spcode/btw — a one-shot, side-effect-free
// LLM endpoint ("by the way"). Lifecycle mirrors useSpcodeGitCommit.ts:
// single in-flight call, AbortController, isMounted guard.
//
// Response shape note: the HTTP body is ApiEnvelope whose `data` is the
// plugin envelope (see _make_envelope in the plugin): {reply?,
// has_context?, reason, stderr, elapsed_ms}. Success is indicated by
// `reason === null` plus a non-empty `reply` — NOT by a `success` flag
// (the v2.20 doc's success/data framing is approximate; the plugin code
// is canonical).

import { ref } from "vue";
import { pluginExtensionApi } from "@/api/v1";

export interface BtwParams {
  prompt: string;
  umo?: string | null;
}

export type BtwResult =
  | { ok: true; reply: string; hasContext: boolean }
  | { ok: false; reason: string };

export interface UseSpcodeBtw {
  isGenerating: import("vue").Ref<boolean>;
  ask: (params: BtwParams) => Promise<BtwResult>;
  /** Abort the in-flight request; the composable stays usable afterwards. */
  cancel: () => void;
  /** Unmount hook: abort in-flight and stop all further state writes. */
  dispose: () => void;
}

// Raw shape of the plugin envelope's data field (see _make_envelope).
interface SpcodeBtwRawData {
  reply?: string;
  has_context?: boolean;
  reason: string | null;
  elapsed_ms?: number;
}

// Endpoint doc §4.2: show a spinner immediately, give up after 30 s.
const BTW_TIMEOUT_MS = 30_000;

export function useSpcodeBtw(): UseSpcodeBtw {
  const isGenerating = ref(false);
  let abortController: AbortController | null = null;
  let isMounted = true;

  async function ask(params: BtwParams): Promise<BtwResult> {
    if (!isMounted) return { ok: false, reason: "aborted" };
    abortController?.abort();
    abortController = new AbortController();
    isGenerating.value = true;
    try {
      const resp = await pluginExtensionApi.post<SpcodeBtwRawData>(
        "spcode/btw",
        {
          prompt: params.prompt,
          ...(params.umo ? { umo: params.umo } : {}),
        },
        { signal: abortController.signal, timeout: BTW_TIMEOUT_MS },
      );
      if (!isMounted) return { ok: false, reason: "aborted" };
      const data = resp.data?.data;
      if (!data) return { ok: false, reason: "unknown" };
      const reply = typeof data.reply === "string" ? data.reply.trim() : "";
      if (data.reason === null && reply.length > 0) {
        return { ok: true, reply, hasContext: data.has_context === true };
      }
      // Failure: reason carries the backend ReasonCode. A null reason
      // with an empty reply is folded into empty_response defensively
      // (backend normally reports empty_response itself).
      return { ok: false, reason: data.reason ?? "empty_response" };
    } catch (err) {
      if (!isMounted) return { ok: false, reason: "aborted" };
      if ((err as { name?: string })?.name === "CanceledError") {
        return { ok: false, reason: "aborted" };
      }
      const anyErr = err as { code?: string; message?: string };
      if (
        anyErr.code === "ERR_NETWORK" ||
        anyErr.code === "ECONNABORTED" || // axios timeout
        /network|timeout/i.test(anyErr.message ?? "")
      ) {
        return { ok: false, reason: "network" };
      }
      return { ok: false, reason: "unknown" };
    } finally {
      if (isMounted) isGenerating.value = false;
    }
  }

  function cancel(): void {
    abortController?.abort();
    abortController = null;
  }

  function dispose(): void {
    isMounted = false;
    cancel();
  }

  return { isGenerating, ask, cancel, dispose };
}
```

- [ ] **Step 2: Typecheck**

Run: `cd /d F:\github\Astrbot\.worktrees\feat-commit-msg-ai-generate\dashboard && npx vue-tsc --noEmit`
Expected: no output, exit code 0 (may take 1-2 minutes).

- [ ] **Step 3: Commit**

```bash
cd /d F:\github\Astrbot\.worktrees\feat-commit-msg-ai-generate
git add dashboard/src/composables/useSpcodeBtw.ts
git commit -m "feat: add useSpcodeBtw composable for /spcode/btw endpoint"
```

---

### Task 3: i18n keys (zh-CN / en-US / ru-RU)

**Files:**
- Modify: `dashboard/src/i18n/locales/zh-CN/features/chat.json` (dialog block at ~line 605)
- Modify: `dashboard/src/i18n/locales/en-US/features/chat.json` (dialog block at ~line 605)
- Modify: `dashboard/src/i18n/locales/ru-RU/features/chat.json` (dialog block at ~line 534)

**Interfaces:**
- Consumes: nothing.
- Produces: keys `spcodeProjectLoad.diffSidebar.gitWorkflow.commit.dialog.{generate, generateAria, langZh, langEn, langToggleAria, generateError.{no_provider, empty_response, llm_error, network, diff_fetch_failed, unknown}}` — consumed by Task 4's template via `tm()`.

- [ ] **Step 1: zh-CN**

In `dashboard/src/i18n/locales/zh-CN/features/chat.json`, find the commit dialog block (contains `"submitShortcutHint": "Ctrl+Enter 提交"`) and replace:

```json
            "submitShortcutHint": "Ctrl+Enter 提交"
```

with:

```json
            "submitShortcutHint": "Ctrl+Enter 提交",
            "generate": "AI 生成",
            "generateAria": "用 AI 生成 commit message",
            "langZh": "中文",
            "langEn": "EN",
            "langToggleAria": "生成语言",
            "generateError": {
              "no_provider": "AI 服务暂不可用，请稍后再试",
              "empty_response": "AI 没有返回内容，请重试",
              "llm_error": "AI 服务异常，请稍后重试",
              "network": "网络错误，请稍后重试",
              "diff_fetch_failed": "无法获取暂存区改动，请重试",
              "unknown": "生成失败，请重试"
            }
```

- [ ] **Step 2: en-US**

In `dashboard/src/i18n/locales/en-US/features/chat.json`, find `"submitShortcutHint": "Ctrl+Enter to commit"` and replace:

```json
            "submitShortcutHint": "Ctrl+Enter to commit"
```

with:

```json
            "submitShortcutHint": "Ctrl+Enter to commit",
            "generate": "Generate",
            "generateAria": "Generate commit message with AI",
            "langZh": "中文",
            "langEn": "EN",
            "langToggleAria": "Message language",
            "generateError": {
              "no_provider": "AI service unavailable, please try again later",
              "empty_response": "AI returned nothing, please retry",
              "llm_error": "AI service error, please retry later",
              "network": "Network error, please retry later",
              "diff_fetch_failed": "Failed to load staged changes, please retry",
              "unknown": "Generation failed, please retry"
            }
```

- [ ] **Step 3: ru-RU**

In `dashboard/src/i18n/locales/ru-RU/features/chat.json`, find `"submitShortcutHint": "Ctrl+Enter — закоммитить"` and replace:

```json
            "submitShortcutHint": "Ctrl+Enter — закоммитить"
```

with:

```json
            "submitShortcutHint": "Ctrl+Enter — закоммитить",
            "generate": "Сгенерировать",
            "generateAria": "Сгенерировать сообщение коммита с помощью ИИ",
            "langZh": "中文",
            "langEn": "EN",
            "langToggleAria": "Язык сообщения",
            "generateError": {
              "no_provider": "Сервис ИИ недоступен, попробуйте позже",
              "empty_response": "ИИ ничего не вернул, повторите попытку",
              "llm_error": "Ошибка сервиса ИИ, повторите позже",
              "network": "Сетевая ошибка, повторите позже",
              "diff_fetch_failed": "Не удалось загрузить изменения, повторите попытку",
              "unknown": "Не удалось сгенерировать, повторите попытку"
            }
```

- [ ] **Step 4: Validate all three JSON files parse**

Run (from `dashboard/`):

```bash
cd /d F:\github\Astrbot\.worktrees\feat-commit-msg-ai-generate\dashboard
node -e "for (const l of ['zh-CN','en-US','ru-RU']) { JSON.parse(require('fs').readFileSync('src/i18n/locales/'+l+'/features/chat.json','utf8')); console.log(l, 'ok'); }"
```

Expected:
```
zh-CN ok
en-US ok
ru-RU ok
```

- [ ] **Step 5: Commit**

```bash
cd /d F:\github\Astrbot\.worktrees\feat-commit-msg-ai-generate
git add dashboard/src/i18n/locales/zh-CN/features/chat.json dashboard/src/i18n/locales/en-US/features/chat.json dashboard/src/i18n/locales/ru-RU/features/chat.json
git commit -m "feat: add i18n keys for AI commit message generation"
```

---

### Task 4: `GitCommitDialog.vue` — toggle + button + orchestration

**Files:**
- Modify: `dashboard/src/components/chat/message_list_comps/GitCommitDialog.vue`

**Interfaces:**
- Consumes (from earlier tasks):
  - `buildCommitMessagePrompt(input)` from `@/composables/commitMessagePrompt` (Task 1)
  - `useSpcodeBtw()` → `{isGenerating, ask, cancel, dispose}`, `BtwResult` (Task 2)
  - i18n keys from Task 3
  - `parseSpcodeGitDiff`, `SpcodeGitDiffRawResponse`, `SpcodeGitDiffSnapshot` from `@/composables/parseSpcodeGitDiff` (existing)
  - `pluginExtensionApi` from `@/api/v1` (existing)
  - `useI18n` from `@/i18n/composables` (existing; `locale: ComputedRef<"zh-CN" | "en-US" | "ru-RU">`)
- Produces: new required props `umo: string | null`, `worktree: string | null` — wired by Task 5.

- [ ] **Step 1: Extend the `<script setup>` imports and props**

Replace:

```typescript
import { computed, ref, watch } from "vue";
import { useModuleI18n } from "@/i18n/composables";
```

with:

```typescript
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useI18n, useModuleI18n } from "@/i18n/composables";
import { pluginExtensionApi } from "@/api/v1";
import {
  parseSpcodeGitDiff,
  type SpcodeGitDiffRawResponse,
  type SpcodeGitDiffSnapshot,
} from "@/composables/parseSpcodeGitDiff";
import { buildCommitMessagePrompt } from "@/composables/commitMessagePrompt";
import { useSpcodeBtw } from "@/composables/useSpcodeBtw";
```

Replace the props block:

```typescript
const props = defineProps<{
  modelValue: boolean;
  stagedFiles: string[];
  isCommitting: boolean;
  /** Last failure reason + stderr; dialog stays open on failure so
   *  the user can edit message and retry (spec §3.3.4). */
  lastError?: { reason: string; stderr: string };
}>();
```

with:

```typescript
const props = defineProps<{
  modelValue: boolean;
  stagedFiles: string[];
  isCommitting: boolean;
  /** Last failure reason + stderr; dialog stays open on failure so
   *  the user can edit message and retry (spec §3.3.4). */
  lastError?: { reason: string; stderr: string };
  /** Current session origin; forwarded to the git-diff and btw calls. */
  umo: string | null;
  /** Selected worktree path (null = primary); forwarded to git-diff. */
  worktree: string | null;
}>();
```

- [ ] **Step 2: Add generation state + `onGenerate()` (script)**

Replace the existing modelValue watch:

```typescript
// Reset message + lastError every time the dialog opens.
watch(
  () => props.modelValue,
  (open) => {
    if (open) {
      message.value = "";
    }
  },
);
```

with:

```typescript
// Reset message + lastError + generate error every time the dialog opens.
watch(
  () => props.modelValue,
  (open) => {
    if (open) {
      message.value = "";
      generateErrorKey.value = null;
    }
  },
);

// ── AI commit-message generation (spec 2026-07-17 §4.3) ────────────
const { locale } = useI18n();
const btw = useSpcodeBtw();

// Persisted language for the generated message. Mirrors the sidebar's
// safeGetItem/safeSetItem convention: never throw, invalid values fall
// back to the default (zh when the UI locale is zh-CN, else en).
const COMMIT_MSG_LANG_KEY = "astrbot.spcode.gitDiffSidebar.commitMsgLang";
type MsgLang = "zh" | "en";

function loadMsgLang(): MsgLang {
  try {
    const v = localStorage.getItem(COMMIT_MSG_LANG_KEY);
    if (v === "zh" || v === "en") return v;
  } catch {
    /* localStorage may be unavailable (private mode) — fall through */
  }
  return locale.value === "zh-CN" ? "zh" : "en";
}

const msgLanguage = ref<MsgLang>(loadMsgLang());
watch(msgLanguage, (v) => {
  try {
    localStorage.setItem(COMMIT_MSG_LANG_KEY, v);
  } catch {
    /* no-op */
  }
});

// i18n key suffix of the last generate failure; null = no error.
const generateErrorKey = ref<string | null>(null);

// Set by onCancel so a late git-diff/btw resolution never overwrites a
// closed dialog's state (btw itself is aborted via btw.cancel()).
let generateAborted = false;

const canGenerate = computed(
  () =>
    props.stagedFiles.length > 0 &&
    !!props.umo &&
    !props.isCommitting &&
    !btw.isGenerating.value,
);

async function onGenerate(): Promise<void> {
  if (!canGenerate.value || !props.umo) return;
  generateAborted = false;
  generateErrorKey.value = null;
  // 1. Fetch the fresh staged diff — the btw endpoint mounts no LLM
  //    tools, so the change content must be embedded in the prompt.
  let snapshot: SpcodeGitDiffSnapshot;
  try {
    const resp = await pluginExtensionApi.get<SpcodeGitDiffRawResponse>(
      "spcode/git-diff",
      {
        params: {
          umo: props.umo,
          scope: "staged",
          ...(props.worktree ? { worktree: props.worktree } : {}),
        },
      },
    );
    const data = resp.data?.data;
    if (!data) throw new Error("empty git-diff response");
    snapshot = parseSpcodeGitDiff(data);
  } catch {
    if (!generateAborted) generateErrorKey.value = "diff_fetch_failed";
    return;
  }
  if (generateAborted) return;
  // 2. Build the bilingual prompt and ask btw.
  const prompt = buildCommitMessagePrompt({
    language: msgLanguage.value,
    files: snapshot.files,
    rawDiff: snapshot.rawDiff,
  });
  const result = await btw.ask({ prompt, umo: props.umo });
  if (result.ok) {
    message.value = result.reply;
    return;
  }
  if (result.reason === "aborted") return; // dialog cancelled mid-flight
  generateErrorKey.value =
    result.reason === "no_provider" ||
    result.reason === "empty_response" ||
    result.reason === "llm_error" ||
    result.reason === "network"
      ? result.reason
      : "unknown";
}

onBeforeUnmount(() => {
  btw.dispose();
});
```

- [ ] **Step 3: Abort generation on cancel (script)**

Replace:

```typescript
function onCancel(): void {
  if (props.isCommitting) return;
  emit("cancel");
  emit("update:modelValue", false);
}
```

with:

```typescript
function onCancel(): void {
  if (props.isCommitting) return;
  // Abort any in-flight generation; unlike commit-in-flight, generation
  // never blocks closing (btw is side-effect-free).
  generateAborted = true;
  btw.cancel();
  emit("cancel");
  emit("update:modelValue", false);
}
```

- [ ] **Step 4: Label-row template (toggle + button)**

Replace:

```html
        <label class="commit-message-label">
          {{ tm("spcodeProjectLoad.diffSidebar.gitWorkflow.commit.dialog.messageLabel") }}
        </label>
```

with:

```html
        <div class="commit-message-label-row">
          <label class="commit-message-label">
            {{ tm("spcodeProjectLoad.diffSidebar.gitWorkflow.commit.dialog.messageLabel") }}
          </label>
          <div class="commit-generate-controls">
            <v-btn-toggle
              v-model="msgLanguage"
              mandatory
              density="compact"
              variant="tonal"
              :aria-label="tm('spcodeProjectLoad.diffSidebar.gitWorkflow.commit.dialog.langToggleAria')"
            >
              <v-btn value="zh" size="x-small">
                {{ tm("spcodeProjectLoad.diffSidebar.gitWorkflow.commit.dialog.langZh") }}
              </v-btn>
              <v-btn value="en" size="x-small">
                {{ tm("spcodeProjectLoad.diffSidebar.gitWorkflow.commit.dialog.langEn") }}
              </v-btn>
            </v-btn-toggle>
            <v-btn
              variant="text"
              size="small"
              color="primary"
              prepend-icon="mdi-auto-fix"
              :loading="btw.isGenerating.value"
              :disabled="!canGenerate"
              :aria-label="tm('spcodeProjectLoad.diffSidebar.gitWorkflow.commit.dialog.generateAria')"
              @click="onGenerate"
            >
              {{ tm("spcodeProjectLoad.diffSidebar.gitWorkflow.commit.dialog.generate") }}
            </v-btn>
          </div>
        </div>
```

- [ ] **Step 5: Inline generate-error line (template)**

Replace:

```html
        <div :class="charCounterClass()">
          {{ tm("spcodeProjectLoad.diffSidebar.gitWorkflow.commit.dialog.charCounter", { count: rawLength }) }}
        </div>
```

with:

```html
        <div :class="charCounterClass()">
          {{ tm("spcodeProjectLoad.diffSidebar.gitWorkflow.commit.dialog.charCounter", { count: rawLength }) }}
        </div>
        <div v-if="generateErrorKey" class="commit-generate-error">
          {{ tm(`spcodeProjectLoad.diffSidebar.gitWorkflow.commit.dialog.generateError.${generateErrorKey}`) }}
        </div>
```

- [ ] **Step 6: Styles**

Append to the `<style scoped>` block (right after the existing `.commit-message-label` rule):

```css
.commit-message-label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 4px;
}
.commit-message-label-row .commit-message-label {
  margin-bottom: 0;
}
.commit-generate-controls {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}
.commit-generate-error {
  margin-top: 4px;
  font-size: 12px;
  color: rgb(var(--v-theme-error));
}
```

- [ ] **Step 7: Typecheck**

Run: `cd /d F:\github\Astrbot\.worktrees\feat-commit-msg-ai-generate\dashboard && npx vue-tsc --noEmit`
Expected: **FAIL** with one error at `GitDiffSidebar.vue` — `GitCommitDialog` is missing required props `umo` and `worktree` (Task 5 adds them). Any OTHER error means this task has a bug; fix before proceeding.

- [ ] **Step 8: Commit**

```bash
cd /d F:\github\Astrbot\.worktrees\feat-commit-msg-ai-generate
git add dashboard/src/components/chat/message_list_comps/GitCommitDialog.vue
git commit -m "feat: add AI generate button with language toggle to GitCommitDialog"
```

---

### Task 5: `GitDiffSidebar.vue` prop wiring + final verification

**Files:**
- Modify: `dashboard/src/components/chat/GitDiffSidebar.vue` (~line 3512, the `<GitCommitDialog>` usage)

**Interfaces:**
- Consumes: `GitCommitDialog`'s new required props (Task 4); `spcodeStatus` (`useSpcodeProjectStatus`, already in sidebar scope; `spcodeStatus.status.value.umo: string | null`) and `selectedWorktree: Ref<string | null>` (already in sidebar scope, template auto-unwraps).
- Produces: nothing new (final task).

- [ ] **Step 1: Pass the new props**

Replace:

```html
        <!-- Spec §6.4: 提交弹窗。 -->
        <GitCommitDialog
          v-model="commitDialogOpen"
          :staged-files="Array.from(stagedFiles)"
          :is-committing="gitCommit.isCommitting.value"
          :last-error="commitLastError ?? undefined"
          @confirm="onConfirmCommit"
          @cancel="onCancelCommit"
        />
```

with:

```html
        <!-- Spec §6.4: 提交弹窗。 -->
        <GitCommitDialog
          v-model="commitDialogOpen"
          :staged-files="Array.from(stagedFiles)"
          :is-committing="gitCommit.isCommitting.value"
          :last-error="commitLastError ?? undefined"
          :umo="spcodeStatus.status.value.umo"
          :worktree="selectedWorktree"
          @confirm="onConfirmCommit"
          @cancel="onCancelCommit"
        />
```

- [ ] **Step 2: Full typecheck**

Run: `cd /d F:\github\Astrbot\.worktrees\feat-commit-msg-ai-generate\dashboard && npx vue-tsc --noEmit`
Expected: no output, exit code 0.

- [ ] **Step 3: Run the whole node --test suite (regression)**

Run: `cd /d F:\github\Astrbot\.worktrees\feat-commit-msg-ai-generate\dashboard && node --test tests/`
Expected: PASS — all tests `fail 0` (including the 4 new `commitMessagePrompt` tests).

- [ ] **Step 4: Commit**

```bash
cd /d F:\github\Astrbot\.worktrees\feat-commit-msg-ai-generate
git add dashboard/src/components/chat/GitDiffSidebar.vue
git commit -m "feat: pass umo and worktree props to GitCommitDialog"
```

- [ ] **Step 5: Manual QA checklist (report to user, no commit)**

With the dev dashboard (`pnpm dev`) against a live AstrBot + spcode plugin:

1. Stage files → open commit dialog → `中文 | EN` toggle + `✨ AI 生成` visible on the label row.
2. Generate in 中文 → textarea filled with a Conventional Commits zh message; editable; `提交` works end-to-end.
3. Generate in EN → English message; reload page → toggle still on EN (localStorage).
4. Click generate twice quickly → only one in-flight (button loading/disabled).
5. Cancel dialog mid-generation → closes immediately, no late overwrite, no console errors.
6. No staged files → generate button disabled.
7. (If feasible) disable the LLM provider → inline `no_provider` error line under the char counter.

---

## Self-Review Notes

- **Spec coverage:** Goal/UI (T4), language toggle + persistence (T4 Step 2), prompt builder + budget (T1), useSpcodeBtw + 30 s timeout + error mapping (T2), i18n 3 locales (T3), sidebar wiring (T5), error matrix (T2 mapping + T4 Step 2 `generateErrorKey` whitelist), tests (T1 + T5 Steps 2-3), YAGNI items untouched. Spec §4.4 (sidebar) ↔ Task 5. All covered.
- **Deviation from spec (documented):** localStorage key uses the repo namespace `astrbot.spcode.gitDiffSidebar.commitMsgLang` instead of `spcode:commit-msg-lang` (spec file updated in the same commit as this plan).
- **Type consistency:** `BtwResult`/`ask`/`cancel`/`dispose` (T2) match usage in T4; `buildCommitMessagePrompt` input type accepts `SpcodeGitDiffFile[]` structurally (`status: FileStatus` ⊂ `string`); `SpcodeGitDiffSnapshot` import in T4 matches the existing export in `parseSpcodeGitDiff.ts`.
- **Known acceptable gap:** Task 4's typecheck intentionally fails until Task 5 wires the required props (noted in T4 Step 7).
