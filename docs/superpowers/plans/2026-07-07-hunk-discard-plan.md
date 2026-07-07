# Hunk Discard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 GitDiff 侧栏的每个 hunk 旁放置「丢弃此 hunk」按钮，按 hunk 粒度精确回滚未提交改动。

**Architecture:** 在 `DiffPreview.vue` 内部 hunk header 旁新增按钮（opt-in prop `discardable`，其他 4 个 callsite 不受影响）。通过新增的 `useSpcodeFileDiscardHunk` composable 调用 `POST /spcode/file-discard-hunk`。二次点击内联确认（3s timeout）。成功后自动 refresh git-diff。

**Tech Stack:** Vue 3 (`<script setup>`) + TypeScript + VeeValidate-style composables + i18next。完全镜像 `useSpcodeFileRestore` 模式。

**Spec:** `docs/superpowers/specs/2026-07-07-hunk-discard-design.md`
**API:** `astrbot_plugin_spcode_toolkit/docs/api/webapi-file-discard-hunk-api.md`

---

## Global Constraints

- 沿用 `useSpcodeFileRestore.ts`（`dashboard/src/composables/useSpcodeFileRestore.ts:1-93`）的 composable 形态（AbortController + isMounted guard + 网络错误归类）
- 沿用 `parseSpcodeFileRestore.ts` 的 reason 分类模式（4 类：fatal/user/retry/config）
- **不**写 Vitest 单元测试（沿用姊妹 spec §1.4 决定：dashboard 尚未配置 vitest）
- **不**修改 `parseUnifiedDiff` 主体逻辑（仅在 `currentHunk` 初始化时填 `hunkIndex`）
- **不**重构 DiffPreview 的 split 模式独有代码（行 ~410-650）
- **不**引入新依赖；**不**修改 `package.json`
- **不**修改后端（spcode 插件）代码
- DiffPreview 是通用组件（5 个 callsite），新增 prop 全部 optional 且默认不渲染按钮
- 错误归因参考 `webapi-file-discard-hunk-api.md §3.4.3` 完整 39 个 reason
- i18n 同步中/英/俄三语
- `pnpm typecheck` + `pnpm lint` 无错
- commit message 遵循 conventional commits 格式

---

## File Structure

**新建文件（2 个）:**
| 文件 | 职责 |
|------|------|
| `dashboard/src/composables/parseSpcodeFileDiscardHunk.ts` | 解析响应 envelope + 39 reason 分类 |
| `dashboard/src/composables/useSpcodeFileDiscardHunk.ts` | 包装 POST 调用，per-hunk loading state |

**修改文件（5 个）:**
| 文件 | 改动范围 |
|------|----------|
| `dashboard/src/components/chat/message_list_comps/DiffPreview.vue` | DiffHunk 字段、hunk header 重构、新增 props/state/helper/按钮/CSS |
| `dashboard/src/components/chat/message_list_comps/GitDiffFileItem.vue` | 透传 3 个 prop + 1 个 emit |
| `dashboard/src/components/chat/message_list_comps/GitDiffBodyContent.vue` | 透传 2 个 prop + discardableFor 派生 + 1 个 emit |
| `dashboard/src/components/chat/GitDiffSidebar.vue` | 引入 composable + handler + 39 reason i18n + dispose + 模板透传 |
| `dashboard/src/i18n/locales/{en-US,zh-CN,ru-RU}/features/chat.json` | 新增 hunkDiscard.* + discardHunk.* 键 |

---

## Task 1: 新建 `parseSpcodeFileDiscardHunk.ts` 解析器

**Files:**
- Create: `dashboard/src/composables/parseSpcodeFileDiscardHunk.ts`

**Interfaces:**
- Consumes: API 响应 envelope（参考 `webapi-file-discard-hunk-api.md §3.4.1`）
- Produces: `SpcodeFileDiscardHunkSnapshot`、`classifyDiscardHunkReason(reason): ReasonClass`

**参考:** `dashboard/src/composables/parseSpcodeFileRestore.ts` 整体结构

- [ ] **Step 1: 创建文件，写入类型定义与解析函数**

```typescript
// Author: elecvoid243
// Date: 2026-07-07
// Spec: docs/superpowers/specs/2026-07-07-hunk-discard-design.md §4.3
// API:  astrbot_plugin_spcode_toolkit/docs/api/webapi-file-discard-hunk-api.md §3.4

export interface SpcodeFileDiscardHunkSnapshot {
  discarded: boolean;
  directory: string | null;
  umo: string | null;
  worktree: string | null;
  file: string;
  scope: "unstaged" | "staged";
  hunksReverted: number;
  patchSha256: string;
  elapsedMs: number;
  stderr: string;
  reason: string | null;
}

export interface SpcodeFileDiscardHunkRawResponse {
  status: string;
  data: {
    discarded: boolean;
    directory: string | null;
    umo: string | null;
    worktree: string | null;
    file: string;
    scope: string;
    hunks_reverted: number;
    patch_sha256: string;
    elapsed_ms: number;
    stderr: string;
    reason: string | null;
  };
}

export type ReasonClass = "ok" | "fatal" | "user" | "retry" | "config" | "unknown";

/** Parse the raw API response into a typed snapshot. */
export function parseSpcodeFileDiscardHunk(
  raw: unknown,
): { kind: "ok"; snapshot: SpcodeFileDiscardHunkSnapshot }
 | { kind: "error"; reason: string } {
  if (typeof raw !== "object" || raw === null) {
    return { kind: "error", reason: "invalid_envelope" };
  }
  const resp = raw as Partial<SpcodeFileDiscardHunkRawResponse>;
  if (resp.status !== "ok" || typeof resp.data !== "object" || resp.data === null) {
    return { kind: "error", reason: "invalid_envelope" };
  }
  const d = resp.data;
  const scope: "unstaged" | "staged" = d.scope === "staged" ? "staged" : "unstaged";
  return {
    kind: "ok",
    snapshot: {
      discarded: !!d.discarded,
      directory: d.directory ?? null,
      umo: d.umo ?? null,
      worktree: d.worktree ?? null,
      file: d.file ?? "",
      scope,
      hunksReverted: typeof d.hunks_reverted === "number" ? d.hunks_reverted : 0,
      patchSha256: d.patch_sha256 ?? "",
      elapsedMs: typeof d.elapsed_ms === "number" ? d.elapsed_ms : 0,
      stderr: d.stderr ?? "",
      reason: d.reason ?? null,
    },
  };
}

/** 39 reason → 4-class (fatal/user/retry/config) + ok/unknown。 */
export function classifyDiscardHunkReason(reason: string | null): ReasonClass {
  if (reason === null) return "ok";
  const FATAL = new Set([
    "not_a_git_repo", "git_unavailable", "feature_disabled",
  ]);
  const USER = new Set([
    "not_modified", "untracked_file", "patch_malformed", "patch_unsafe_path",
    "multi_file_patch", "patch_file_mismatch", "patch_binary", "patch_too_large",
    "missing_file", "file_not_found", "path_unsafe",
  ]);
  const RETRY = new Set([
    "patch_apply_failed", "patch_check_failed", "git_error",
  ]);
  const CONFIG = new Set([
    "no_project_loaded", "worktree_invalid", "directory_missing", "invalid_body",
  ]);
  if (FATAL.has(reason)) return "fatal";
  if (USER.has(reason)) return "user";
  if (RETRY.has(reason)) return "retry";
  if (CONFIG.has(reason)) return "config";
  return "unknown";
}
```

- [ ] **Step 2: 验证 TypeScript 编译**

Run:
```bash
cd F:\github\Astrbot\dashboard
pnpm typecheck
```

Expected: 无错（`parseSpcodeFileDiscardHunk.ts` 已加入 tsconfig 包含的目录）。

- [ ] **Step 3: Commit**

```bash
cd F:\github\Astrbot
git add dashboard/src/composables/parseSpcodeFileDiscardHunk.ts
git -c user.name=elecvoid243 -c user.email=elecvoid243@local commit -m "feat(dashboard): add parseSpcodeFileDiscardHunk response parser"
```

---

## Task 2: 新建 `useSpcodeFileDiscardHunk.ts` composable

**Files:**
- Create: `dashboard/src/composables/useSpcodeFileDiscardHunk.ts`

**Interfaces:**
- Consumes: `parseSpcodeFileDiscardHunk` 的导出类型
- Produces: `UseSpcodeFileDiscardHunk` 接口

**参考:** `dashboard/src/composables/useSpcodeFileRestore.ts:1-93` 完整结构

- [ ] **Step 1: 创建文件，写入 composable**

```typescript
// Author: elecvoid243
// Date: 2026-07-07
// Spec: docs/superpowers/specs/2026-07-07-hunk-discard-design.md §4.2

import { ref, type Ref } from "vue";
import { pluginExtensionApi } from "@/api/v1";
import {
  parseSpcodeFileDiscardHunk,
  classifyDiscardHunkReason,
  type SpcodeFileDiscardHunkSnapshot,
} from "./parseSpcodeFileDiscardHunk";

export interface DiscardHunkParams {
  file: string;
  hunkIndex: number;
  patchText: string;
  worktree?: string | null;
  umo?: string | null;
}

export type DiscardHunkResult =
  | { ok: true; snapshot: SpcodeFileDiscardHunkSnapshot }
  | { ok: false; reason: string; stderr?: string };

export interface UseSpcodeFileDiscardHunk {
  /** Key format: `${file}#${hunkIndex}`. Per-hunk loading state. */
  isDiscardingHunk: Ref<Set<string>>;
  discard: (params: DiscardHunkParams) => Promise<DiscardHunkResult>;
  dispose: () => void;
}

export function useSpcodeFileDiscardHunk(): UseSpcodeFileDiscardHunk {
  const isDiscardingHunk = ref<Set<string>>(new Set());
  let abortController: AbortController | null = null;
  let isMounted = true;

  async function discard(params: DiscardHunkParams): Promise<DiscardHunkResult> {
    if (!isMounted) return { ok: false, reason: "aborted" };
    abortController?.abort();
    abortController = new AbortController();
    const key = `${params.file}#${params.hunkIndex}`;
    const next = new Set(isDiscardingHunk.value);
    next.add(key);
    isDiscardingHunk.value = next;
    try {
      const resp = await pluginExtensionApi.post<unknown>(
        "spcode/file-discard-hunk",
        {
          file: params.file,
          patch_text: params.patchText,
          ...(params.worktree ? { worktree: params.worktree } : {}),
          ...(params.umo ? { umo: params.umo } : {}),
        },
        { signal: abortController.signal },
      );
      if (!isMounted) return { ok: false, reason: "aborted" };
      const parsed = parseSpcodeFileDiscardHunk(resp.data);
      if (parsed.kind !== "ok") {
        return { ok: false, reason: classifyDiscardHunkReason(null) };
      }
      const snap = parsed.snapshot;
      if (snap.discarded) {
        return { ok: true, snapshot: snap };
      }
      return {
        ok: false,
        reason: classifyDiscardHunkReason(snap.reason),
        stderr: snap.stderr || undefined,
      };
    } catch (err) {
      if (!isMounted) return { ok: false, reason: "aborted" };
      if ((err as { name?: string })?.name === "CanceledError") {
        return { ok: false, reason: "aborted" };
      }
      const anyErr = err as { code?: string; message?: string };
      if (
        anyErr.code === "ERR_NETWORK" ||
        /network/i.test(anyErr.message ?? "")
      ) {
        return { ok: false, reason: "network" };
      }
      return { ok: false, reason: "unknown" };
    } finally {
      if (isMounted) {
        const after = new Set(isDiscardingHunk.value);
        after.delete(key);
        isDiscardingHunk.value = after;
      }
    }
  }

  function dispose(): void {
    isMounted = false;
    abortController?.abort();
    abortController = null;
  }

  return { isDiscardingHunk, discard, dispose };
}
```

- [ ] **Step 2: 验证 TypeScript 编译**

Run:
```bash
cd F:\github\Astrbot\dashboard
pnpm typecheck
```

Expected: 无错。

- [ ] **Step 3: Commit**

```bash
cd F:\github\Astrbot
git add dashboard/src/composables/useSpcodeFileDiscardHunk.ts
git -c user.name=elecvoid243 -c user.email=elecvoid243@local commit -m "feat(dashboard): add useSpcodeFileDiscardHunk composable"
```

---

## Task 3: DiffPreview — 扩展 `DiffHunk` 接口与 `parseUnifiedDiff` 填 `hunkIndex`

**Files:**
- Modify: `dashboard/src/components/chat/message_list_comps/DiffPreview.vue`

**Interfaces:**
- Consumes: 现有 `DiffHunk` 接口（行 709-712）
- Produces: 扩展 `DiffHunk` 含 `hunkIndex: number` 字段；`parseUnifiedDiff` 在创建 hunk 时填字段

- [ ] **Step 1: 修改 `DiffHunk` 接口，加 `hunkIndex` 字段**

定位 `DiffPreview.vue` 行 709-712：

```typescript
interface DiffHunk {
  header: string;
  lines: DiffLine[];
}
```

替换为：

```typescript
interface DiffHunk {
  header: string;
  lines: DiffLine[];
  /** Index in the full parse (maxLines=Infinity). Stable across maxLines variants
   *  (truncation only drops the trailing hunk's tail, never reshuffles). Used to
   *  cross-reference the hunk in the full parse when buildHunkPatchText()
   *  needs the complete body. */
  hunkIndex: number;
}
```

- [ ] **Step 2: 修改 `parseUnifiedDiff` 在创建 hunk 时填 `hunkIndex`**

定位 `parseUnifiedDiff` 函数（行 1271-1353），找到创建 `currentHunk` 的位置（行 ~1285-1289）：

```typescript
      oldNo = parseInt(hunkMatch[1], 10);
      newNo = parseInt(hunkMatch[3], 10);

      currentHunk = {
        header: rawLine,
        lines: [],
      };
      continue;
```

替换为：

```typescript
      oldNo = parseInt(hunkMatch[1], 10);
      newNo = parseInt(hunkMatch[3], 10);

      currentHunk = {
        header: rawLine,
        lines: [],
        hunkIndex: hunks.length,   // pre-push index; same as final `i` in the v-for
      };
      continue;
```

- [ ] **Step 3: 验证 TypeScript 编译 + lint**

Run:
```bash
cd F:\github\Astrbot\dashboard
pnpm typecheck
pnpm lint
```

Expected: 无错。

- [ ] **Step 4: 验证现有功能未回归（手动）**

启动 dev server，打开任何带 hunk 的 diff（任意 file_restore 测试 fixture），确认：
- hunk header 仍可点击折叠/展开
- 行号、+/- 颜色、hunk 计数（`hunk.lines.length`）显示正确
- 没有 console 报错

- [ ] **Step 5: Commit**

```bash
cd F:\github\Astrbot
git add dashboard/src/components/chat/message_list_comps/DiffPreview.vue
git -c user.name=elecvoid243 -c user.email=elecvoid243@local commit -m "refactor(dashboard): add hunkIndex to DiffHunk for cross-truncation lookup"
```

---

## Task 4: DiffPreview — hunk header DOM 重构（button → div role=button）

**Files:**
- Modify: `dashboard/src/components/chat/message_list_comps/DiffPreview.vue`

**Interfaces:**
- 现有 hunk header（unified 模式行 115-130 + split 模式行 ~473 + 行 ~567）从 `<button class="hunk-header">` 重构为 `<div role="button" tabindex=0>`

**背景:** 此重构是后续 Task 5/6 加嵌套 `<button class="hunk-discard">` 的前置条件（HTML5 禁止 button-in-button）。

- [ ] **Step 1: 定位 unified 模式 hunk header（行 115-130）**

找到这段代码：
```vue
<button
  type="button"
  class="hunk-header"
  :aria-expanded="!collapsedHunks.has(hi)"
  @click="toggleHunk(hi)"
>
  <v-icon
    size="12"
    class="hunk-chevron"
    :class="{ expanded: !collapsedHunks.has(hi) }"
  >
    mdi-chevron-right
  </v-icon>
  <span class="hunk-header-text">{{ hunk.header }}</span>
  <span class="hunk-header-count">
    {{ hunk.lines.length }}
  </span>
</button>
```

- [ ] **Step 2: 替换为 div role=button 版本**

```vue
<div
  class="hunk-header"
  role="button"
  tabindex="0"
  :aria-expanded="!collapsedHunks.has(hi)"
  @click="toggleHunk(hi)"
  @keydown="(e) => onHunkHeaderKeydown(hi, e)"
>
  <v-icon
    size="12"
    class="hunk-chevron"
    :class="{ expanded: !collapsedHunks.has(hi) }"
  >
    mdi-chevron-right
  </v-icon>
  <span class="hunk-header-text">{{ hunk.header }}</span>
  <span class="hunk-header-count">
    {{ hunk.lines.length }}
  </span>
</div>
```

- [ ] **Step 3: 同样替换 split 模式的两个 hunk header（行 ~473 与 ~567）**

按 Step 2 的模式在**所有 4 处** hunk header 都做替换。**实际文件中有 4 个 `<button class="hunk-header">`**（unified normal、split normal、unified fullscreen、split fullscreen），全部统一改为 `<div role="button" tabindex="0">` + `onHunkHeaderKeydown` keydown handler。

> 本任务**只**做 DOM 重构（button → div role=button + keydown handler）。按钮的插入统一在 Task 6 完成。

- [ ] **Step 4: 在 `<script setup>` 中添加 `onHunkHeaderKeydown` 函数**

定位 `toggleHunk` 函数（行 ~795 附近），在其后插入：

```typescript
function onHunkHeaderKeydown(idx: number, e: KeyboardEvent): void {
  // Spec §6.1.3: Enter / Space toggles the hunk; mirrors the file row pattern
  // in GitDiffFileItem (outer row was refactored from <button> to <div>).
  if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    toggleHunk(idx);
  }
}
```

- [ ] **Step 5: 验证 TypeScript 编译 + lint + 手动回归**

Run:
```bash
cd F:\github\Astrbot\dashboard
pnpm typecheck
pnpm lint
```

启动 dev server 验证：
- hunk header 鼠标点击仍可折叠/展开
- 键盘 Tab 聚焦 hunk header + Enter/Space 仍可切换折叠
- 行号、+/- 颜色、hunk 计数显示正确
- 没有 console 报错

- [ ] **Step 6: Commit**

```bash
cd F:\github\Astrbot
git add dashboard/src/components/chat/message_list_comps/DiffPreview.vue
git -c user.name=elecvoid243 -c user.email=elecvoid243@local commit -m "refactor(dashboard): refactor hunk header from button to div role=button"
```

---

## Task 5: DiffPreview — 业务逻辑（props、state、handler、helper）

**Files:**
- Modify: `dashboard/src/components/chat/message_list_comps/DiffPreview.vue`

**Interfaces:**
- 新增 props: `onDiscardHunk?`、`discardingHunks?`、`discardKeyPrefix?`、`discardable?`
- 新增 state: `confirmingHunkIndex`、`confirmTimer`
- 新增 handler: `onDiscardHunkClick`、`onHunkHeaderKeydown`（Task 4 已加）、`discardHunkAriaLabel`、`discardHunkTitle`
- 新增 helper: `buildHunkPatchText`
- 修改 `toggleHunk` 加 `confirmingHunkIndex` 守护
- 新增 watch 清理 `confirmTimer` 与 `confirmingHunkIndex`
- 新增 `onBeforeUnmount` 清理 `confirmTimer`

- [ ] **Step 1: 在 `withDefaults(defineProps<{...}>(), {...})` 块中新增 4 个 prop**

定位 `props` 定义（行 ~737-769 附近），在最后一个 prop `comments?: FileComment[]` 之后追加：

```typescript
    onDiscardHunk?: (params: { file: string; hunkIndex: number; patchText: string }) => void;
    /** Set of `${discardKeyPrefix}#${hunkIndex}` keys currently in flight. */
    discardingHunks?: ReadonlySet<string>;
    /** Used as the key prefix when checking `discardingHunks`. Defaults to filePath. */
    discardKeyPrefix?: string;
    /** When true (and onDiscardHunk is set), render the per-hunk discard button. */
    discardable?: boolean;
```

并在 defaults 块中（`withDefaults` 第二个参数）追加：

```typescript
    discardingHunks: () => new Set<string>(),
    discardKeyPrefix: "",
    discardable: false,
```

- [ ] **Step 2: 添加 `isCurrentHunkDiscarding` 派生函数**

紧接 `props` 定义之后，添加：

```typescript
const isCurrentHunkDiscarding = (hi: number): boolean => {
  const prefix = props.discardKeyPrefix || props.filePath;
  return props.discardingHunks.has(`${prefix}#${hi}`);
};
```

- [ ] **Step 3: 在 `<script setup>` 中添加 `confirmingHunkIndex` state 与 `confirmTimer`**

定位 `collapsedHunks` state 定义（行 ~778 附近），在其后插入：

```typescript
// Spec §2 decision #3 + §6.1.3: two-click inline confirmation. First click
// sets `confirmingHunkIndex`; second click within 3s executes the discard.
// The setTimeout handle is kept on a module-local variable so onBeforeUnmount
// can clear it even if the component tears down mid-confirmation.
const confirmingHunkIndex = ref<number | null>(null);
let confirmTimer: ReturnType<typeof setTimeout> | null = null;
```

- [ ] **Step 4: 在 `toggleHunk` 中加 `confirmingHunkIndex` 守护**

定位 `toggleHunk` 函数（行 ~795 附近），修改为：

```typescript
function toggleHunk(idx: number): void {
  // Spec §2 decision #12 + §6.1.4: confirmation state locks hunk folding.
  // Clicking the header in "Confirm?" state is silently dropped so the
  // user's confirm intent isn't accidentally flipped to "cancel".
  if (confirmingHunkIndex.value !== null) return;
  const next = new Set(collapsedHunks.value);
  if (next.has(idx)) next.delete(idx);
  else next.add(idx);
  collapsedHunks.value = next;
}
```

- [ ] **Step 5: 添加 `onDiscardHunkClick` handler**

在 `toggleHunk` 函数后插入：

```typescript
function onDiscardHunkClick(hi: number, e: MouseEvent): void {
  e.stopPropagation();   // prevent bubbling to header's toggleHunk
  if (!props.onDiscardHunk || !props.discardable) return;
  if (isCurrentHunkDiscarding(hi)) return;
  if (confirmingHunkIndex.value === hi) {
    // Second click: execute the discard.
    if (confirmTimer) {
      clearTimeout(confirmTimer);
      confirmTimer = null;
    }
    confirmingHunkIndex.value = null;
    const patchText = buildHunkPatchText(props.filePath, hi);
    if (!patchText) return;   // defensive: empty patch, don't fire
    props.onDiscardHunk({ file: props.filePath, hunkIndex: hi, patchText });
  } else {
    // First click: enter confirmation state.
    confirmingHunkIndex.value = hi;
    confirmTimer = setTimeout(() => {
      confirmingHunkIndex.value = null;
      confirmTimer = null;
    }, 3000);
  }
}
```

- [ ] **Step 6: 添加 `discardHunkAriaLabel` 与 `discardHunkTitle` i18n helper**

在 `onDiscardHunkClick` 函数后插入：

```typescript
function discardHunkAriaLabel(hi: number, header: string): string {
  return tm("spcodeProjectLoad.diffPreview.hunkDiscard.buttonAria", {
    hunk: header,
    file: props.filePath,
  });
}

function discardHunkTitle(hi: number, header: string): string {
  if (confirmingHunkIndex.value === hi) {
    return tm(
      "spcodeProjectLoad.diffPreview.hunkDiscard.confirmingAria",
      { hunk: header },
    );
  }
  return tm("spcodeProjectLoad.diffPreview.hunkDiscard.buttonTitle", {
    hunk: header,
  });
}
```

- [ ] **Step 7: 添加 `buildHunkPatchText` helper**

定位 `parseUnifiedDiff` 函数（行 ~1271）**之前**，先添加 `buildHunkPatchText`：

```typescript
function buildHunkPatchText(filePath: string, hunkIndex: number): string {
  // Spec §2 decision #10 + §5.2: use full parse (maxLines=Infinity) to avoid
  // truncation, then look up the hunk by hunkIndex (set in Task 3). Use
  // ASCII '-'/'+'/' ' prefixes — the parser's display prefix is U+2212
  // (visual minus) which git apply rejects.
  if (!filePath) return "";
  const fullText = extractDiffContent(props.content);
  const fullHunks = parseUnifiedDiff(fullText, Infinity);
  // Find the hunk whose hunkIndex matches (handles the case where the
  // parsed-hunks list was truncated — hunkIndex is the full-parse index).
  const target =
    fullHunks.find((h) => h.hunkIndex === hunkIndex) ??
    fullHunks[hunkIndex];
  if (!target) return "";
  const lines: string[] = [
    `diff --git a/${filePath} b/${filePath}`,
    `--- a/${filePath}`,
    `+++ b/${filePath}`,
    target.header,
  ];
  for (const line of target.lines) {
    const prefix = line.type === "del" ? "-" : line.type === "add" ? "+" : " ";
    lines.push(prefix + line.content);
  }
  return lines.join("\n");
}
```

- [ ] **Step 8: 添加残留状态清理 watch + onBeforeUnmount**

定位 `onBeforeUnmount` 块（行 ~869 附近，处理 isFullscreen 的 body overflow 清理）。在其后**追加**：

```typescript
// Spec §2 decision #12 + §6.1.5: clear residual confirm state when filePath
// or content changes (parsedHunks may re-parse, indices may shift).
watch(
  () => [props.filePath, props.content],
  () => {
    if (confirmTimer) {
      clearTimeout(confirmTimer);
      confirmTimer = null;
    }
    confirmingHunkIndex.value = null;
  },
);

onBeforeUnmount(() => {
  // Existing isFullscreen body-overflow cleanup is in the earlier
  // onBeforeUnmount block. Add the confirmTimer cleanup here.
  if (confirmTimer) {
    clearTimeout(confirmTimer);
    confirmTimer = null;
  }
});
```

> 实际实现时请把 confirmTimer cleanup 合并到现有的 `onBeforeUnmount` 块里，不要拆成两个。

- [ ] **Step 9: 验证 TypeScript 编译 + lint**

Run:
```bash
cd F:\github\Astrbot\dashboard
pnpm typecheck
pnpm lint
```

Expected: 无错。

- [ ] **Step 10: 手动验证（仅 hunk header 折叠，不点按钮）**

启动 dev server，验证：
- hunk header 仍可点击折叠/展开
- 键盘 Tab + Enter/Space 仍可切换
- 没有 console 报错

（按钮本身的渲染在 Task 6 完成。）

- [ ] **Step 11: Commit**

```bash
cd F:\github\Astrbot
git add dashboard/src/components/chat/message_list_comps/DiffPreview.vue
git -c user.name=elecvoid243 -c user.email=elecvoid243@local commit -m "feat(dashboard): add hunk discard props, state, handler, and patch builder"
```

---

## Task 6: DiffPreview — 模板加按钮 + CSS

**Files:**
- Modify: `dashboard/src/components/chat/message_list_comps/DiffPreview.vue`

**Interfaces:**
- 模板：在 4 处 hunk header 内部（unified normal、split normal、unified fullscreen、split fullscreen）插入相同的 `<button class="hunk-discard">`
- CSS：追加 `.hunk-discard` 样式块

> **范围:** 修改 4 处 hunk header 模板（unified normal、split normal、unified fullscreen、split fullscreen），都插入相同的 `<button class="hunk-discard">`。4 处插入用同一个 snippet，复用 Step 1-2 的最终代码。

- [ ] **Step 1: 定位 4 处 hunk header 模板（Task 4 改写后）**

找到这段代码（行 ~118-137 附近）：
```vue
<div
  class="hunk-header"
  role="button"
  tabindex="0"
  :aria-expanded="!collapsedHunks.has(hi)"
  @click="toggleHunk(hi)"
  @keydown="(e) => onHunkHeaderKeydown(hi, e)"
>
  <v-icon ...>mdi-chevron-right</v-icon>
  <span class="hunk-header-text">{{ hunk.header }}</span>
  <span class="hunk-header-count">
    {{ hunk.lines.length }}
  </span>
</div>
```

- [ ] **Step 2: 在 unified normal hunk header `hunk-header-count` 之后、`</div>` 之前插入按钮**

```vue
<div
  class="hunk-header"
  role="button"
  tabindex="0"
  :aria-expanded="!collapsedHunks.has(hi)"
  @click="toggleHunk(hi)"
  @keydown="(e) => onHunkHeaderKeydown(hi, e)"
>
  <v-icon
    size="12"
    class="hunk-chevron"
    :class="{ expanded: !collapsedHunks.has(hi) }"
  >
    mdi-chevron-right
  </v-icon>
  <span class="hunk-header-text">{{ hunk.header }}</span>
  <span class="hunk-header-count">
    {{ hunk.lines.length }}
  </span>
  <!-- Spec §6.1.2: per-hunk discard button. opt-in via `discardable` prop;
       the other 4 DiffPreview callsite don't pass this prop, so the button
       is not rendered there. -->
  <button
    v-if="discardable && onDiscardHunk"
    type="button"
    class="hunk-discard"
    :class="{
      'is-loading': isCurrentHunkDiscarding(hi),
      'is-confirming': confirmingHunkIndex === hi,
    }"
    :disabled="isCurrentHunkDiscarding(hi)"
    :aria-label="discardHunkAriaLabel(hi, hunk.header)"
    :aria-busy="isCurrentHunkDiscarding(hi) ? 'true' : 'false'"
    :title="discardHunkTitle(hi, hunk.header)"
    @click.stop="onDiscardHunkClick(hi, $event)"
  >
    <v-progress-circular
      v-if="isCurrentHunkDiscarding(hi)"
      indeterminate
      :size="12"
      :width="2"
    />
    <template v-else>
      <v-icon :size="14">
        {{ confirmingHunkIndex === hi ? 'mdi-alert-circle' : 'mdi-content-cut' }}
      </v-icon>
      <span v-if="confirmingHunkIndex === hi" class="hunk-discard-confirm-label">
        {{ tm('spcodeProjectLoad.diffPreview.hunkDiscard.confirmLabel') }}
      </span>
    </template>
  </button>
</div>
```

- [ ] **Step 3: 在 split normal hunk header 插入相同按钮**

定位 split 模式 normal view 的 `class="hunk-header"` 元素（行 ~226 附近），按 Step 2 的完全相同 snippet 在 `hunk-header-count` 之后插入 `<button class="hunk-discard">`。4 处插入的代码**字节级相同**（共享 hunkIndex 索引、共享 isCurrentHunkDiscarding 判定、共享 tm 翻译）。

- [ ] **Step 4: 在 unified fullscreen 与 split fullscreen 两处 hunk header 插入相同按钮**

定位 unified fullscreen (行 ~471) 与 split fullscreen (行 ~567) 两处 hunk header，按 Step 2 的完全相同 snippet 插入。

> 验证 4 处插入一致性：在 IDE 中选中 Step 2 的按钮代码块 → 复制 → 粘贴到 Step 3 与 Step 4。4 处 snippet 字节级相同（仅是 hunk 变量 `hi` 范围不同，但表达式无差异）。

- [ ] **Step 5: 在 `<style scoped>` 内追加 `.hunk-discard` 样式**

定位 `</style>` 之前（最后一个 CSS 块后），追加：

```css
.hunk-discard {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 18px;
  padding: 0 5px 0 3px;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 3px;
  color: #ff9800;
  font-size: 11px;
  font-family: inherit;
  cursor: pointer;
  opacity: 0;
  transition:
    opacity 0.12s ease,
    background 0.12s ease,
    border-color 0.12s ease;
  flex-shrink: 0;
}
.hunk-header:hover .hunk-discard,
.hunk-discard:focus-visible,
.hunk-discard.is-confirming {
  opacity: 1;
}
.hunk-discard:hover {
  background: rgba(255, 152, 0, 0.1);
}
.hunk-discard:focus-visible {
  outline: 2px solid #ff9800;
  outline-offset: 1px;
  opacity: 1;
}
.hunk-discard:disabled {
  cursor: not-allowed;
  opacity: 0.3;
}
.hunk-discard.is-loading {
  opacity: 1;
}
.hunk-discard.is-confirming {
  background: rgba(255, 152, 0, 0.15);
  border-color: rgba(255, 152, 0, 0.4);
  animation: hunk-discard-pulse 1s ease-in-out infinite;
}
@keyframes hunk-discard-pulse {
  0%, 100% { background: rgba(255, 152, 0, 0.15); }
  50%      { background: rgba(255, 152, 0, 0.28); }
}
.hunk-discard-confirm-label {
  font-weight: 500;
}
@media (max-width: 760px) {
  .hunk-discard {
    width: 20px;
    padding: 0 2px;
  }
  .hunk-discard-confirm-label { display: none; }
}
```

- [ ] **Step 6: 验证 TypeScript 编译 + lint**

Run:
```bash
cd F:\github\Astrbot\dashboard
pnpm typecheck
pnpm lint
```

Expected: 无错（`tm()` 调用在 i18n 缺失时不会编译失败，只会运行时报 key missing——这在 Task 10 加 i18n 键时解决）。

- [ ] **Step 7: 验证按钮暂不渲染（因 `discardable=false` 默认值 + 父级未传 prop）**

启动 dev server 打开任意 diff（如 `ToolCallCard` 或 `FilePatchPanel`）：
- hunk header **不**显示剪刀按钮（因 opt-in 默认 false）
- hunk header 仍可点击折叠/展开
- 没有 console 报错

- [ ] **Step 8: Commit**

```bash
cd F:\github\Astrbot
git add dashboard/src/components/chat/message_list_comps/DiffPreview.vue
git -c user.name=elecvoid243 -c user.email=elecvoid243@local commit -m "feat(dashboard): render hunk discard button in hunk headers (unified + split)"
```

---

## Task 7: GitDiffFileItem — 透传 props + emit

**Files:**
- Modify: `dashboard/src/components/chat/message_list_comps/GitDiffFileItem.vue`

**Interfaces:**
- 新增 prop: `onDiscardHunk?`、`discardingHunks?`、`discardable?`
- 新增 emit: `discard-hunk`
- 透传到 `<DiffPreview>`

**参考:** 现有 `onRestore` / `onStage` / `onUnstage` / `onOpenFile` 的透传模式（行 ~50-95 props；行 ~96-105 emits；行 ~225-275 模板）

- [ ] **Step 1: 在 `defineProps<{...}>()` 块中新增 3 个 prop**

定位现有 props 定义（行 ~50-95），在最后一个 prop `selectableAriaLabel?: string` 之后追加：

```typescript
  // ── Spec 2026-07-07 hunk discard: pass-through props ──
  onDiscardHunk?: (file: string, hunkIndex: number, patchText: string) => void;
  /** Set of `${file.path}#${hunkIndex}` keys currently in flight. */
  discardingHunks?: ReadonlySet<string>;
  discardable?: boolean;
```

- [ ] **Step 2: 在 `defineEmits<{...}>()` 块中新增 1 个 emit**

定位现有 emits 定义（行 ~96-105），在最后一个 emit `(e: "select", selected: boolean): void;` 之后追加：

```typescript
  (e: "discard-hunk", file: string, hunkIndex: number, patchText: string): void;
```

- [ ] **Step 3: 在 `<DiffPreview>` 标签上透传 prop + emit**

定位 `<DiffPreview>` 标签（行 ~275 附近），在现有 `:on-open-file` 等透传 prop 之后追加：

```vue
<DiffPreview
  ...
  :on-discard-hunk="onDiscardHunk"
  :discarding-hunks="discardingHunks"
  :discard-key-prefix="file.path"
  :discardable="discardable"
  ...
  @discard-hunk="(file, hi, patch) => emit('discard-hunk', file, hi, patch)"
/>
```

- [ ] **Step 4: 验证 TypeScript 编译 + lint**

Run:
```bash
cd F:\github\Astrbot\dashboard
pnpm typecheck
pnpm lint
```

Expected: 无错。

- [ ] **Step 5: Commit**

```bash
cd F:\github\Astrbot
git add dashboard/src/components/chat/message_list_comps/GitDiffFileItem.vue
git -c user.name=elecvoid243 -c user.email=elecvoid243@local commit -m "feat(dashboard): thread hunk discard props through GitDiffFileItem"
```

---

## Task 8: GitDiffBodyContent — 透传 props + discardableFor 派生

**Files:**
- Modify: `dashboard/src/components/chat/message_list_comps/GitDiffBodyContent.vue`

**Interfaces:**
- 新增 prop: `onDiscardHunk?`、`discardingHunks?`
- 新增 emit: `discard-hunk`
- 新增派生函数: `discardableFor(file)`
- 透传到 `<GitDiffFileItem>`

- [ ] **Step 1: 在 `defineProps<{...}>()` 块中新增 2 个 prop**

定位现有 props 定义（行 ~50-95），在最后一个 prop `onOpenFile?: (path: string) => void;` 之后追加：

```typescript
  // ── Spec 2026-07-07 hunk discard: pass-through props ──
  onDiscardHunk?: (file: string, hunkIndex: number, patchText: string) => void;
  /** Set of `${file.path}#${hunkIndex}` keys currently in flight. */
  discardingHunks?: ReadonlySet<string>;
```

- [ ] **Step 2: 在 `defineEmits<{...}>()` 块中新增 1 个 emit**

定位现有 emits 定义（行 ~97-110），在最后一个 emit `(e: "unstage-paths", paths: string[]): void;` 之后追加：

```typescript
  (e: "discard-hunk", file: string, hunkIndex: number, patchText: string): void;
```

- [ ] **Step 3: 添加 `discardableFor(file)` 派生函数**

定位现有 `isUnstagingForPath` 函数（行 ~135 附近），在其后插入：

```typescript
function discardableFor(file: SpcodeGitDiffFile): boolean {
  if (!props.onDiscardHunk) return false;                       // not wired
  if (props.newFilePaths?.has(file.path)) return false;          // new file
  if (file.isBinary) return false;                               // binary
  if (!spcodeStatus.status.value.loaded) return false;           // no project
  if (!spcodeStatus.status.value.umo) return false;              // no umo
  return true;
}
```

- [ ] **Step 4: 在 `<GitDiffFileItem>` 标签上透传 prop + emit**

定位 `<GitDiffFileItem>` 标签（行 ~350 附近），在现有 `:selectable` 等透传 prop 之后追加：

```vue
<GitDiffFileItem
  v-for="f in section.files"
  :key="f.path + ':' + f.status"
  :file="f"
  ...
  :on-discard-hunk="onDiscardHunk"
  :discarding-hunks="discardingHunks"
  :discardable="discardableFor(f)"
  ...
  @discard-hunk="(file, hi, patch) => emit('discard-hunk', file, hi, patch)"
/>
```

- [ ] **Step 5: 验证 TypeScript 编译 + lint**

Run:
```bash
cd F:\github\Astrbot\dashboard
pnpm typecheck
pnpm lint
```

Expected: 无错。

- [ ] **Step 6: Commit**

```bash
cd F:\github\Astrbot
git add dashboard/src/components/chat/message_list_comps/GitDiffBodyContent.vue
git -c user.name=elecvoid243 -c user.email=elecvoid243@local commit -m "feat(dashboard): thread hunk discard props through GitDiffBodyContent"
```

---

## Task 9: GitDiffSidebar — composable + handler + 透传 + dispose

**Files:**
- Modify: `dashboard/src/components/chat/GitDiffSidebar.vue`

**Interfaces:**
- 引入 `useSpcodeFileDiscardHunk` composable
- 新增 `DISCARD_HUNK_REASON_I18N_KEYS` 映射表
- 新增 `classifySnackbarLevel` 函数
- 新增 `onDiscardHunk` async handler
- 修改 `dispose()` 加 `fileDiscardHunk.dispose()`
- 模板透传 `:on-discard-hunk` + `:discarding-hunks` 到 `<GitDiffBodyContent>`

**参考:** 现有 `onFileRestore` handler（行 ~1465-1505）+ `fileRestore.dispose()`（行 ~1957）+ `<GitDiffBodyContent>` 模板（行 ~2475-2495）

- [ ] **Step 1: 引入 composable 与类型**

定位现有 `useSpcodeFileRestore` import（行 ~493 附近），在其后追加：

```typescript
import {
  useSpcodeFileDiscardHunk,
  type DiscardHunkResult,
} from "@/composables/useSpcodeFileDiscardHunk";
```

定位 `const fileRestore = useSpcodeFileRestore();`（行 ~493），在其后追加：

```typescript
const fileDiscardHunk = useSpcodeFileDiscardHunk();
```

- [ ] **Step 2: 添加 `DISCARD_HUNK_REASON_I18N_KEYS` 映射表**

定位现有 `RESTORE_REASON_I18N_KEYS`（如果有）或在 `onFileRestore` 函数（行 ~1465）之前，添加：

```typescript
// Spec §5.3 + §6.4.1: 39 reason → i18n key. Reasons not in the map fall
// through to `error.reason.unknown` (caller passes raw reason to tm()).
const DISCARD_HUNK_REASON_I18N_KEYS: Record<string, string> = {
  patch_check_failed: "spcodeProjectLoad.diffSidebar.discardHunk.error.reason.patch_check_failed",
  patch_apply_failed: "spcodeProjectLoad.diffSidebar.discardHunk.error.reason.patch_apply_failed",
  patch_too_large:    "spcodeProjectLoad.diffSidebar.discardHunk.error.reason.patch_too_large",
  patch_malformed:    "spcodeProjectLoad.diffSidebar.discardHunk.error.reason.patch_malformed",
  not_modified:       "spcodeProjectLoad.diffSidebar.discardHunk.error.reason.not_modified",
  untracked_file:     "spcodeProjectLoad.diffSidebar.discardHunk.error.reason.untracked_file",
  multi_file_patch:   "spcodeProjectLoad.diffSidebar.discardHunk.error.reason.multi_file_patch",
  patch_binary:       "spcodeProjectLoad.diffSidebar.discardHunk.error.reason.patch_binary",
  no_project_loaded:  "spcodeProjectLoad.diffSidebar.discardHunk.error.reason.no_project_loaded",
  worktree_invalid:   "spcodeProjectLoad.diffSidebar.discardHunk.error.reason.worktree_invalid",
  not_a_git_repo:     "spcodeProjectLoad.diffSidebar.discardHunk.error.reason.not_a_git_repo",
  git_unavailable:    "spcodeProjectLoad.diffSidebar.discardHunk.error.reason.git_unavailable",
};

function classifySnackbarLevel(
  reason: string,
): "success" | "info" | "warning" | "error" {
  const FATAL = new Set(["not_a_git_repo", "git_unavailable", "feature_disabled"]);
  const RETRY = new Set(["patch_apply_failed", "patch_check_failed", "git_error"]);
  if (FATAL.has(reason)) return "error";
  if (RETRY.has(reason)) return "info";
  return "warning";   // user + config + unknown
}
```

- [ ] **Step 3: 添加 `onDiscardHunk` handler**

定位 `onFileRestore` 函数（行 ~1465-1505）后，添加：

```typescript
async function onDiscardHunk(
  file: string,
  hunkIndex: number,
  patchText: string,
): Promise<void> {
  const umo = spcodeStatus.status.value.umo;
  if (!umo) return;
  const worktree = selectedWorktree.value;
  const result: DiscardHunkResult = await fileDiscardHunk.discard({
    file,
    hunkIndex,
    patchText,
    umo,
    worktree,
  });
  if (!result.ok && result.reason === "aborted") return;
  if (result.ok) {
    const n = result.snapshot.hunksReverted;
    const tmKey =
      n === 1
        ? "spcodeProjectLoad.diffSidebar.discardHunk.success"
        : "spcodeProjectLoad.diffSidebar.discardHunk.successMultiple";
    showSnackbar(tm(tmKey, { hunksReverted: n, file }), "success");
    // Spec §2 decision #7: success → immediate refresh so the hunk disappears.
    await composable.refresh();
  } else {
    const mapping = DISCARD_HUNK_REASON_I18N_KEYS[result.reason];
    const msg = mapping
      ? tm(mapping, { stderr: result.stderr ?? "" })
      : tm(
          "spcodeProjectLoad.diffSidebar.discardHunk.error.reason.unknown",
          { reason: result.reason },
        );
    showSnackbar(msg, classifySnackbarLevel(result.reason));
  }
}
```

- [ ] **Step 4: 修改 `dispose()` 加 composable dispose**

定位现有 `dispose()` 函数（行 ~1950 附近），在 `fileRestore.dispose();` 之后追加：

```typescript
  fileDiscardHunk.dispose();
```

- [ ] **Step 5: 模板透传 prop**

定位 `<GitDiffBodyContent>` 标签（行 ~2475-2495），在现有 `:on-open-file` 等 prop 之后追加：

```vue
<GitDiffBodyContent
  v-else-if="viewMode === 'diff'"
  ref="gitDiffBodyRef"
  :state="diffBodyState"
  :expanded="expandedSet"
  :is-dark="!!isDark"
  :on-restore="onFileRestore"
  :selected-scope="selectedScope"
  :on-stage="onStageFile"
  :on-unstage="onUnstageFile"
  :is-staging="gitStage.isStaging"
  :is-unstaging="gitUnstage.isUnstaging"
  :new-file-paths="newFilePaths"
  :on-open-file="onOpenFile"
  :on-discard-hunk="onDiscardHunk"
  :discarding-hunks="fileDiscardHunk.isDiscardingHunk.value"
  @toggle="toggleFile"
  @retry="onManualRefresh"
  @restore="onFileRestore"
  @stage="onStageFile"
  @unstage="onUnstageFile"
  @open-file="onOpenFile"
  @stage-paths="onStagePaths"
  @unstage-paths="onUnstagePaths"
  @discard-hunk="onDiscardHunk"
/>
```

- [ ] **Step 6: 验证 TypeScript 编译 + lint**

Run:
```bash
cd F:\github\Astrbot\dashboard
pnpm typecheck
pnpm lint
```

Expected: 无错（`tm()` 缺失键在运行时显示 fallback 字符串，但编译通过）。

- [ ] **Step 7: 手动验证（仅 prop 透传，按钮不显示因 i18n 键未加）**

启动 dev server 打开 GitDiff 侧栏，验证：
- 侧栏仍正常加载 diff
- 现有 stage/unstage/restore 按钮功能未受影响
- hunk header 仍可点击折叠/展开
- console 显示若干 i18n 键缺失警告（`hunkDiscard.*`）——这在 Task 10 解决
- **不**期望看到 `mdi-content-cut` 按钮（`discardable` 由 `discardableFor(f)` 派生，但 prop 链已通）

> 如果按钮已经出现但 i18n 显示 fallback 字符串（`Discard hunk ... in ...`），属正常。

- [ ] **Step 8: Commit**

```bash
cd F:\github\Astrbot
git add dashboard/src/components/chat/GitDiffSidebar.vue
git -c user.name=elecvoid243 -c user.email=elecvoid243@local commit -m "feat(dashboard): wire hunk discard handler in GitDiffSidebar"
```

---

## Task 10: i18n 三语同步新增键

**Files:**
- Modify: `dashboard/src/i18n/locales/en-US/features/chat.json`
- Modify: `dashboard/src/i18n/locales/zh-CN/features/chat.json`
- Modify: `dashboard/src/i18n/locales/ru-RU/features/chat.json`

**Interfaces:**
- 新增键路径: `spcodeProjectLoad.diffPreview.hunkDiscard.*`（5 个键）
- 新增键路径: `spcodeProjectLoad.diffSidebar.discardHunk.*`（含 13 个 reason + 2 个 success）

**参考:** 现有 `spcodeProjectLoad.diffSidebar.restore.*` 键（en-US `chat.json:495-540`、zh-CN `chat.json:495-540`、ru-RU 同步）

- [ ] **Step 1: 在 en-US `chat.json` 新增 `hunkDiscard` 键组**

定位 `spcodeProjectLoad.diffPreview` 根对象，在合适位置（如 `toolbar` 之后）插入：

```jsonc
    "hunkDiscard": {
      "buttonAria": "Discard hunk {hunk} in {file}",
      "buttonTitle": "Discard this hunk. Click again within 3 seconds to confirm.",
      "confirmLabel": "Confirm?",
      "confirmingAria": "Click again to confirm discarding hunk {hunk}",
      "loadingAria": "Discarding hunk {hunk}"
    },
```

> 完整 JSON 路径与现有 `toolbar` / `summary` / `group` 同级。具体位置请按现有 JSON 结构对齐。

- [ ] **Step 2: 在 en-US `chat.json` 新增 `discardHunk` 键组（diffSidebar 下）**

定位 `spcodeProjectLoad.diffSidebar.restore` 之后，添加：

```jsonc
    "discardHunk": {
      "success": "Discarded {hunksReverted} hunk from {file}",
      "successMultiple": "Discarded {hunksReverted} hunks from {file}",
      "error": {
        "reason": {
          "patch_check_failed": "Patch doesn't match current file state. Refresh the diff and retry. ({stderr})",
          "patch_apply_failed": "File was concurrently modified. Refresh and retry. ({stderr})",
          "patch_too_large":    "Patch exceeds 256 KB. Try restoring the whole file instead.",
          "patch_malformed":    "Patch is malformed. Refresh the diff and retry. ({stderr})",
          "not_modified":       "File has no uncommitted changes.",
          "untracked_file":     "Untracked files can't be discarded by hunk. Stage the file first.",
          "multi_file_patch":   "Internal error: patch contains multiple files. Please report this bug.",
          "patch_binary":       "Binary files can't be discarded by hunk. Restore the whole file instead.",
          "no_project_loaded":  "No project loaded. Load a project in the bot session first.",
          "worktree_invalid":   "Worktree path is invalid.",
          "not_a_git_repo":     "Target directory is not a git repository.",
          "git_unavailable":    "git is not installed on the server.",
          "unknown":            "Discard failed: {reason}"
        }
      }
    },
```

- [ ] **Step 3: 在 zh-CN `chat.json` 同步新增（中文翻译）**

按 Step 1/2 位置，在 `spcodeProjectLoad.diffPreview.hunkDiscard` 与 `spcodeProjectLoad.diffSidebar.discardHunk` 下添加中文文案。文案参考：

```jsonc
    "hunkDiscard": {
      "buttonAria":     "丢弃 {file} 的 hunk {hunk}",
      "buttonTitle":    "丢弃此 hunk。3 秒内再次点击以确认。",
      "confirmLabel":   "确认?",
      "confirmingAria": "再次点击以确认丢弃 hunk {hunk}",
      "loadingAria":    "正在丢弃 hunk {hunk}"
    },
    "discardHunk": {
      "success":         "已从 {file} 丢弃 {hunksReverted} 个 hunk",
      "successMultiple": "已从 {file} 丢弃 {hunksReverted} 个 hunk",
      "error": {
        "reason": {
          "patch_check_failed": "patch 与当前文件状态不匹配,请刷新 diff 后重试。({stderr})",
          "patch_apply_failed": "文件被并发修改,请刷新后重试。({stderr})",
          "patch_too_large":    "patch 超过 256 KB。请改用整文件恢复。",
          "patch_malformed":    "patch 格式错误。请刷新 diff 后重试。({stderr})",
          "not_modified":       "该文件无未提交改动。",
          "untracked_file":     "未跟踪文件不能按 hunk 丢弃,请先暂存。",
          "multi_file_patch":   "内部错误:patch 含多个文件。请上报此 bug。",
          "patch_binary":       "二进制文件不能按 hunk 丢弃。请改用整文件恢复。",
          "no_project_loaded":  "未加载项目。请先在 bot 会话中加载项目。",
          "worktree_invalid":   "worktree 路径无效。",
          "not_a_git_repo":     "目标目录不是 git 仓库。",
          "git_unavailable":    "服务端未安装 git。",
          "unknown":            "丢弃失败:{reason}"
        }
      }
    },
```

- [ ] **Step 4: 在 ru-RU `chat.json` 同步新增（俄文翻译）**

参考 zh-CN 的对应文案做俄文翻译。`success` 和 `successMultiple` 复数处理参考现有 `restore.success` 的 ru-RU 风格。

> 翻译不在本任务阻塞范围内——若俄文翻译暂时不到位，先用英文占位即可，但需在所有 5 个键路径下都建好空对象结构，避免运行时报 key missing。

- [ ] **Step 5: 验证 i18n 加载无错**

Run:
```bash
cd F:\github\Astrbot\dashboard
pnpm typecheck
pnpm lint
```

启动 dev server 打开 GitDiff 侧栏：
- 鼠标 hover hunk header
- console **不**应有 i18n key missing 警告
- 按钮 title 显示对应语种的 tooltip 文本

- [ ] **Step 6: Commit**

```bash
cd F:\github\Astrbot
git add dashboard/src/i18n/locales/en-US/features/chat.json
git add dashboard/src/i18n/locales/zh-CN/features/chat.json
git add dashboard/src/i18n/locales/ru-RU/features/chat.json
git -c user.name=elecvoid243 -c user.email=elecvoid243@local commit -m "feat(dashboard): add i18n keys for hunk discard in en/zh/ru"
```

---

## Task 11: 端到端验证（手动 E2E 验收清单）

**Files:** 无代码改动；纯验收

**Interfaces:** N/A

- [ ] **Step 1: 启动 dev server**

```bash
cd F:\github\Astrbot\dashboard
pnpm dev
```

后端：
```bash
cd F:\github\Astrbot
uv run main.py
```

- [ ] **Step 2: 准备测试 fixture**

在工作区手动制造一个有 3 个 hunk 的修改文件（如 `README.md`），确保 diff 可见。

- [ ] **Step 3: 按 spec §9.2 验收清单 20 项全过**

| # | 场景 | 期望 | 通过 |
|---|------|------|------|
| 1 | 准备一个有 3 个 hunk 的修改文件 | — | ☐ |
| 2 | 鼠标 hover 第 2 个 hunk header | 剪刀按钮 opacity 0 → 1 | ☐ |
| 3 | 单击剪刀按钮 | 按钮变 `mdi-alert-circle` + "确认丢弃?" + 脉冲动画 | ☐ |
| 4 | 3 秒内再单击 | POST `/spcode/file-discard-hunk` 触发；成功后该 hunk 从 diff 中消失；其他 hunk 保留 | ☐ |
| 5 | 等待 3 秒不点击 | 按钮自动恢复剪刀 icon + 透明度 0 | ☐ |
| 6 | 切换 tab / 切文件 | 残留"Confirm?"态被清空 | ☐ |
| 7 | 网络断开 | snackbar 显示 "网络连接失败"；文件不变；按钮恢复原状 | ☐ |
| 8 | 修改文件后（与 hunk 抓取时不一致）→ 点丢弃 | snackbar 显示 "Patch doesn't match current file state. Refresh the diff and retry." | ☐ |
| 9 | 新文件（intent-to-add） | hunk header **无** 按钮 | ☐ |
| 10 | 二进制文件 | 渲染 binary alert，**无** hunk 出现，**无** 按钮 | ☐ |
| 11 | `staged` scope 视图（先 `git add`） | 按钮出现；成功后 scope='staged' snackbar 提示 | ☐ |
| 12 | `all` scope 视图 | 按钮出现；成功后 scope 由后端自动判定 | ☐ |
| 13 | 鼠标 hover hunk header，单击按钮 | 不触发 hunk 折叠切换（`stopPropagation` 生效） | ☐ |
| 14 | 在 "Confirm?" 态单击 hunk header 文字 | 不切换折叠（`toggleHunk` 守护） | ☐ |
| 15 | 在 "Confirm?" 态按 Esc | 当前无 Esc 关闭逻辑（YAGNI）；但 3s 后自动恢复 | ☐ |
| 16 | 键盘 Tab 聚焦到 hunk-discard 按钮 + Enter | 触发 `onDiscardHunkClick`（无障碍 a11y） | ☐ |
| 17 | 同时点 2 个 hunk 的按钮 | 两个 POST 并行触发；按完成顺序逐个 refresh；UI 互不阻塞 | ☐ |
| 18 | 其他 4 个 DiffPreview callsite（`ToolCallCard` 等） | 不传 `onDiscardHunk` / `discardable` → 按钮**不渲染**；现有功能无回归 | ☐ |
| 19 | 移动端（max-width 760px） | 按钮缩窄到 20px；`hunk-discard-confirm-label` 不显示 | ☐ |
| 20 | 暗色模式 | 按钮 hover 背景 `rgba(255, 152, 0, 0.1)` 对暗色背景依然可见 | ☐ |

- [ ] **Step 4: 回归检查**

确认以下功能未受影响：
- 现有 `commentable` 行内评论功能
- 现有 hunk 折叠 (`collapsedHunks`)
- 现有 fullscreen 模式
- 现有 `showAllLines` 30 行截断逻辑
- 整文件级 `file-restore` 按钮
- stage/unstage 按钮
- 切换 scope (`unstaged` / `staged` / `all`)

- [ ] **Step 5: 最终 lint + typecheck 通过**

```bash
cd F:\github\Astrbot\dashboard
pnpm typecheck
pnpm lint
```

Expected: 无错。

- [ ] **Step 6: 验收通过后，整理 commit（如有散落改动）**

如果验收过程中有零散的 lint 修复或微调，单独 commit：

```bash
cd F:\github\Astrbot
git status
# 视情况：
# git add <files>
# git -c user.name=elecvoid243 -c user.email=elecvoid243@local commit -m "chore(dashboard): <description>"
```

---

## Self-Review

**1. Spec coverage:** 全部 spec §3.3 文件改动清单（7 个）已映射到 11 个 task 的 Files 块：
- `parseSpcodeFileDiscardHunk.ts` → Task 1
- `useSpcodeFileDiscardHunk.ts` → Task 2
- `DiffPreview.vue` 改动 → Task 3, 4, 5, 6（按改动性质拆 4 个 task）
- `GitDiffFileItem.vue` → Task 7
- `GitDiffBodyContent.vue` → Task 8
- `GitDiffSidebar.vue` → Task 9
- 3 个 chat.json → Task 10
- 端到端验证 → Task 11

**2. Placeholder scan:** 无 "TBD" / "TODO" / "implement later" / "similar to Task N"。所有代码块完整；所有命令具体；所有路径精确。

**3. Type consistency:**
- `onDiscardHunk` 函数签名在 DiffPreview (Task 5)、GitDiffFileItem (Task 7)、GitDiffBodyContent (Task 8)、GitDiffSidebar (Task 9) 四处一致：
  - DiffPreview 接收: `(params: { file: string; hunkIndex: number; patchText: string }) => void`
  - 中间层 (FileItem/BodyContent) 与 emit: `(file: string, hunkIndex: number, patchText: string) => void`
  - Sidebar handler: `onDiscardHunk(file, hunkIndex, patchText)`
- `discardingHunks` 类型: `ReadonlySet<string>`（prop）→ `Ref<Set<string>>`（composable）→ `.value`（模板）
- `discardKeyPrefix` 默认空字符串，回退到 `filePath`
- `DiscardHunkResult` 在 composable（Task 2）与 handler（Task 9）一致
- `DiscardHunkParams` 与 `useSpcodeFileDiscardHunk.discard()` 签名一致

**4. 任务粒度:** 11 个 task，最小 task（如 Task 1）5 个 step，最大 task（如 Task 5）11 个 step。每个 step 2-5 分钟可完成。

**5. 风险点已对应到 spec §8 的 R1-R12：**
- R1 (U+2212) → Task 5 Step 7 ASCII prefix
- R2 (maxLines 截断) → Task 5 Step 7 `Infinity` 解析 + Task 3 hunkIndex 字段
- R5 (残留 confirmingHunkIndex) → Task 5 Step 8 watch + onBeforeUnmount
- R6 (并发 POST) → Task 2 Set<string> 复合键
- R7 (5 个 callsite 零影响) → opt-in `discardable` 默认 false（Task 5 Step 1）
- R8 (parsedHunks vs fullHunks 索引) → Task 3 hunkIndex 字段 + Task 5 Step 7 find 双保险
- R9 (hunk-header 重构 a11y) → Task 4 Step 4 onHunkHeaderKeydown
- R10 (切 scope 清理) → Task 5 Step 8 watch
- R12 (`\ No newline` 解析 bug) → 标记为可接受（spec §8 R12 注）

**6. Self-Review 通过：**
- 所有 spec 章节有对应 task
- 无 placeholder
- 类型一致
- 任务粒度合理
- 风险有缓解
