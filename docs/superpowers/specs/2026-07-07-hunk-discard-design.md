# Dashboard GitDiff 侧栏「按 Hunk 丢弃」按钮 — 设计文档

| 项目 | 内容 |
|------|------|
| 主题 | 在 GitDiff 侧栏的每个 hunk 旁放置「丢弃此 hunk」按钮，按 hunk 粒度精确回滚未提交改动 |
| 日期 | 2026-07-07（创建） |
| 作者 | elecvoid243 |
| 状态 | Design — 待用户 review |
| 关联插件 | `astrbot_plugin_spcode_toolkit` v2.16.0（**源码路径**：`F:\github\astrbot_plugin_spcode_toolkit`） |
| 关联端点 | `POST /spcode/file-discard-hunk`（定义见 `astrbot_plugin_spcode_toolkit/docs/api/webapi-file-discard-hunk-api.md`） |
| 关联代码 | `dashboard/src/components/chat/message_list_comps/DiffPreview.vue`、`GitDiffFileItem.vue`、`GitDiffBodyContent.vue`、`GitDiffSidebar.vue` |
| 前置 spec | `docs/superpowers/specs/2026-06-17-chatui-git-diff-sidebar-design.md`（GitDiff 侧栏基础结构）、`docs/superpowers/specs/2026-06-22-chatui-git-diff-file-restore-design.md`（整文件级 restore 实现，本 spec 复刻其 composable 模式） |

---

## 1. 背景与目标

### 1.1 现状

上一份 spec（`2026-06-22`）已交付 **整文件级** restore 按钮（位于 `GitDiffFileItem.vue` 的 file row 右侧，icon `mdi-restore`）：点击 → 确认弹窗 → `POST /spcode/file-restore` → 整文件从 HEAD 覆盖。

但用户反馈："只想丢弃这一个 hunk 的改动（比如某次 AI 改坏了 5 行中的 2 行），其他 3 行和上下文我都想保留。"——当前**唯一**的精细化操作是手动跑 `git checkout -p`，对 WebChat 用户门槛太高。

### 1.2 痛点

1. 想**部分回滚**一个文件中的某个 hunk，UI 上无对应操作
2. 整文件 restore 粒度太粗，误伤无辜改动
3. 现有 stage/unstage 按钮只能**保留**改动，无法**撤销**改动
4. 用户场景：AI 改了一处但破坏了三处，AI 没法自纠 → 用户只能切到 IDE 手动 `git checkout -p`，严重打断 WebChat 协作流

### 1.3 目标

在 **每个 hunk 头部**（hunk header 行）旁放置一个**「丢弃此 hunk」**按钮：

1. 点击 → 二次确认（无 Modal，倒计时 3s 内再次点击才执行）→ `POST /spcode/file-discard-hunk` → 该 hunk 改动被精确回滚，**其他 hunk 与未触及内容完全保留**
2. 支持 `unstaged` / `staged` / `all` 三个 scope（后端按 `git status --porcelain` X/Y 列自动判定，前端无需路由）
3. 成功后自动 refresh 整个 `git-diff`，UI 上该 hunk 消失
4. 错误归因明确（39 个 reason 全 i18n，参考 `webapi-file-discard-hunk-api.md §3.4.3`）
5. 零侵入其他 4 个 DiffPreview callsite（`ToolCallCard` / `FilePatchPanel` / `FileDiffResult` / `ThemeAwareMarkdownCodeBlock`）

### 1.4 非目标

- ❌ **不**修改 spcode 插件代码（端点已就绪，spec 在 `astrbot_plugin_spcode_toolkit/docs/superpowers/specs/2026-07-06-file-discard-hunk-design.md`）
- ❌ **不**修改 AstrBot 核心（后端、协议、消息总线）
- ❌ **不**实现多 hunk 批量 discard（一次请求 = 单文件单 patch；批量留给后续迭代）
- ❌ **不**实现 discard 的「撤销」按钮（后端无对应端点，且 git 已真正回滚，撤销需整文件 restore）
- ❌ **不**支持新文件 / 二进制文件的 hunk discard（API 会拒，前端不暴露按钮）
- ❌ **不**写 Vitest 单元测试（沿用姊妹 spec §1.4 决定：dashboard 尚未配置 vitest；用 `pnpm typecheck` + `pnpm lint` + 手动验证 §7.2 端到端验收清单）
- ❌ **不**重构 DiffPreview 的 split 模式（hunk header 在 split 模式行 ~473 与 ~567 复用，prop 透传即可，不重复实现）

---

## 2. 设计决策（已与用户确认）

| # | 决策点 | 选择 | 理由 |
|---|--------|------|------|
| 1 | 按钮位置 | **A.1 DiffPreview 内部**（hunk header 内） | 物理位置是硬约束（用户明确"放在每个 hunk 显示旁边"）；hunk header 是 DiffPreview 内部 DOM，外部无法精准锚定；`commentable` prop 已破"纯渲染"边界，先例一致；其他 4 个 callsite 通过 opt-in prop 零影响 |
| 2 | opt-in 机制 | `discardable?: boolean` 默认 `false` + `onDiscardHunk?: Function` 透传 | 4 个无关 callsite 不传任何 prop → 按钮不渲染；只有 `GitDiffFileItem` 传 `:discardable="canDiscard(file)"` + `:on-discard-hunk="..."` |
| 3 | 确认方式 | **C 二次点击内联确认** | 比 Modal 流畅、零打断；比单击安全、可视化好；符合 hunk 级操作「频次高、风险中」的定位；与 file-restore 的 Modal 区分（粒度不同） |
| 4 | scope 支持范围 | `unstaged` + `staged` + `all` 全开 | 后端 `git status --porcelain` X/Y 列已能自动判定（API §4.1）；前端无需做 scope 路由，简化逻辑 |
| 5 | 按钮样式 | 24×18 hover 渐显 + warning 橙黄 + icon `mdi-content-cut` + 二次确认态 icon `mdi-alert-circle` + 脉冲动画 | 与 file-restore（primary 蓝、`mdi-restore`）视觉对仗；颜色区分动作强度（橙=警示，区别于整文件恢复的"中性"蓝） |
| 6 | loading state | **每 hunk 独立**（`Set<"file#hunkIndex">`） | 多 hunk 可并行丢弃，互不阻塞；与 `gitStage.isStaging: Ref<Set<string>>` 模式一致 |
| 7 | 成功后行为 | 自动 refresh 整个 `git-diff` | 简化状态管理（不维护"局部移除"的状态机）；API 校验保证一致性；UI 上该 hunk 消失是预期行为 |
| 8 | 新文件 / 二进制 | **隐藏按钮** | API 会拒（`untracked_file` / `patch_binary`），不暴露给用户；新文件通过 `isNewFile` prop 判断（已有，GitDiffFileItem 传入），二进制文件由 `file.isBinary` 判定 |
| 9 | hunk header DOM 变化 | `<button class="hunk-header">` → `<div role="button" tabindex=0>` | 解决 HTML5 button-in-button 禁止问题（参考 `GitDiffFileItem.vue` 注释里提到的 "outer row <button> -> <div role="button" tabindex=0>" 模式，行 4-9）；同时该重构**也为 file-restore 未来按钮**铺路 |
| 10 | patch_text 重建方式 | 在 `DiffPreview` 内新增 `buildHunkPatchText(filePath, hunkIndex)` helper，用 `parseUnifiedDiff(content, Infinity)` 取完整解析；按 `hunk.header` 文本去 full 列表里查找 | 避免 `parsedHunks` 30 行截断导致 patch 不完整；避免逐字段重建引入的 `U+2212` vs `-` 字符 bug；不修改 `parseUnifiedDiff` 主体逻辑 |
| 11 | 截断 hunk 索引 | 给 `DiffHunk` 接口加 `hunkIndex: number` 字段，记录 full 解析时的索引 | 当 `parsedHunks` 被 `maxLines` 截断时，截断版与 full 版的 hunk 数量与索引一致（`parsedHunks[i].hunkIndex === i`）；cross-reference 稳 |
| 12 | 确认态 timeout | 3 秒内未再点击 → 自动恢复原状；切 file/切 scope 也清空 | 避免残留"Confirm?"态；setTimeout 句柄存在组件 state 里，onBeforeUnmount 清理 |
| 13 | 错误处理 | 39 个 reason 全 i18n + 4 类（fatal/user/retry/config）snackbar 等级 | 与 `file-restore` 错误处理完全对齐；参考 `webapi-file-discard-hunk-api.md §3.5.2` |

---

## 3. 架构与文件改动

### 3.1 架构原则

- **零后端改动**：完全复用 spcode v2.16.0 新增的 `POST /spcode/file-discard-hunk` 端点
- **复用 file-restore 模式**：`useSpcodeFileDiscardHunk` composable 完全镜像 `useSpcodeFileRestore`（行 1-93）的形态，包括 AbortController / isMounted guard / 网络错误归类
- **严格 opt-in**：DiffPreview 是通用组件（5 个 callsite），新增 prop 全部 optional 且默认不渲染按钮
- **最小侵入**：不修改 `parseUnifiedDiff` 主体；不修改现有 `commentable` / `comments` 行为；不修改 split 模式独有逻辑

### 3.2 调用链

```
┌──────────────────────────────────────────────────────────────┐
│ GitDiffSidebar (parent)                                       │
│   ├─ useSpcodeFileDiscardHunk()  ← NEW composable             │
│   ├─ isDiscardingHunk: Ref<Set<string>>   (key = file#hi)     │
│   ├─ onDiscardHunk(file, hunkIndex, patchText)                │
│   └─ :discarding-hunks + :on-discard-hunk 透传                 │
└──────────────┬───────────────────────────────────────────────┘
               │ :on-discard-hunk + :discarding-hunks (Set<string>)
               ▼
┌──────────────────────────────────────────────────────────────┐
│ GitDiffBodyContent (middle)                                   │
│   ├─ discardableFor(file) 派生（!isNewFile && !isBinary       │
│   │   && filePath && spcodeStatus.loaded && spcodeStatus.umo) │
│   └─ 透传到 GitDiffFileItem                                    │
└──────────────┬───────────────────────────────────────────────┘
               │ :on-discard-hunk + :discardable + :discarding-hunks
               ▼
┌──────────────────────────────────────────────────────────────┐
│ GitDiffFileItem.vue (file row)                                │
│   └─ 透传到 DiffPreview（用 file.path 作为 key prefix）         │
└──────────────┬───────────────────────────────────────────────┘
               │ :on-discard-hunk + :discardable + :discarding-hunks
               │  + :discard-key-prefix (= file.path)
               ▼
┌──────────────────────────────────────────────────────────────┐
│ DiffPreview.vue (leaf)                                        │
│   ├─ hunk header <button> → <div role="button"> (重构)        │
│   ├─ new <button class="hunk-discard"> inline in header       │
│   ├─ buildHunkPatchText(filePath, hunkIndex) helper            │
│   ├─ 二次点击确认状态 (confirmingHunkIndex + 3s timeout)       │
│   └─ hunk 折叠在确认态被锁（避免误切折叠）                      │
└──────────────────────────────────────────────────────────────┘
```

### 3.3 文件改动清单

| # | 文件 | 改动类型 | 描述 |
|---|------|----------|------|
| 1 | `dashboard/src/composables/useSpcodeFileDiscardHunk.ts` | **NEW** | composable 包装 `POST /spcode/file-discard-hunk`，完全镜像 `useSpcodeFileRestore.ts`（行 1-93）的形态 |
| 2 | `dashboard/src/composables/parseSpcodeFileDiscardHunk.ts` | **NEW** | 解析响应 envelope 字段（`discarded` / `scope` / `hunks_reverted` / `stderr` / `reason` 等），分类映射 39 个 reason |
| 3 | `dashboard/src/components/chat/message_list_comps/DiffPreview.vue` | **MODIFY** | ① 改 hunk header 为 `div role=button`；② 新增 3 个 prop；③ 新增 `buildHunkPatchText` helper；④ 新增 `confirmingHunkIndex` state + timeout 清理；⑤ 模板加按钮 + CSS |
| 4 | `dashboard/src/components/chat/message_list_comps/GitDiffFileItem.vue` | **MODIFY** | ① 新增 3 个 prop 透传；② emit `discard-hunk` 事件 |
| 5 | `dashboard/src/components/chat/message_list_comps/GitDiffBodyContent.vue` | **MODIFY** | ① 新增 2 个 prop 透传 + `discardableFor(file)` 派生；② emit `discard-hunk` 事件 |
| 6 | `dashboard/src/components/chat/GitDiffSidebar.vue` | **MODIFY** | ① 引入 `useSpcodeFileDiscardHunk` composable；② 新增 `onDiscardHunk` handler（含 39 reason snackbar）；③ 透传 prop；④ `dispose()` 加新 composable |
| 7 | `dashboard/src/i18n/locales/{en-US,zh-CN,ru-RU}/features/chat.json` | **MODIFY** | 新增 `spcodeProjectLoad.diffPreview.hunkDiscard.*` 与 `spcodeProjectLoad.diffSidebar.discardHunk.*` 键（中/英/俄三语同步） |

### 3.4 不改动的文件

- ❌ `parseSpcodeGitDiff.ts` —— `spcode-git-diff` 端点响应解析器，与 discard 无关
- ❌ `useSpcodeFileRestore.ts` —— 整文件级 restore 独立 composable
- ❌ `useSpcodeGitStage.ts` / `useSpcodeGitUnstage.ts` —— stage/unstage 与 discard 互不干涉
- ❌ DiffPreview 的 split 模式独有代码（行 ~410-650）—— split 模式 hunk header 复用 unified 模式模板，prop 透传即可
- ❌ 其他 4 个 DiffPreview callsite（`ToolCallCard.vue` / `FilePatchPanel.vue` / `FileDiffResult.vue` / `ThemeAwareMarkdownCodeBlock.vue`）—— 不传 prop 即无按钮

---

## 4. 数据模型

### 4.1 `DiffHunk` 扩展

```typescript
// DiffPreview.vue 行 709-712 现有
interface DiffHunk {
  header: string;
  lines: DiffLine[];
  // ── 新增（spec 2026-07-07 §2 决策 #11）──
  /** Index in the full parse (maxLines=Infinity). Same as the parsed-hunks
   *  index when no truncation occurs. Used to cross-reference the hunk in
   *  the full parse when buildHunkPatchText() needs the complete body. */
  hunkIndex: number;
}
```

`parseUnifiedDiff` 修改：在 `currentHunk` 初始化时填 `hunkIndex: hunks.length`（push 前的索引）。

### 4.2 `useSpcodeFileDiscardHunk` 接口

完全镜像 `useSpcodeFileRestore.ts` 的形态：

```typescript
// dashboard/src/composables/useSpcodeFileDiscardHunk.ts
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

export function useSpcodeFileDiscardHunk(): UseSpcodeFileDiscardHunk { /* ... */ }
```

### 4.3 `parseSpcodeFileDiscardHunk` 解析规则

`SpcodeFileDiscardHunkSnapshot` 字段直接对应 API 响应 `data` 对象（见 `webapi-file-discard-hunk-api.md §3.4.1`）：

```typescript
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
```

`classifyDiscardHunkReason` 把 39 个 reason 归为 4 类（fatal/user/retry/config），与 `parseSpcodeFileRestore.ts:5-9` 的 `classifyReason` 模式一致。完整 39 reason 列表见 `webapi-file-discard-hunk-api.md §3.4.3`。

---

## 5. 关键交互

### 5.1 二次点击内联确认流程

```
T+0s    用户 hover hunk header
        └─ 按钮 opacity 0 → 1 (12ms transition)

T+0s    用户单击「丢弃」按钮 (hunk 3, README.md)
        ├─ emit('discard-hunk', ...) 不触发
        ├─ confirmingHunkIndex.value = 3
        ├─ confirmTimer = setTimeout(() => reset, 3000)
        └─ 按钮进入 .is-confirming 态：
           ├─ icon: mdi-content-cut → mdi-alert-circle
           ├─ 显示文字 "确认丢弃?" (仅当按钮足够宽时)
           ├─ 背景 脉冲动画 (1s 循环)
           └─ hunk header 折叠被锁 (toggleHunk 入口守护)

T+0~3s  用户再次单击 (同一按钮)
        ├─ clearTimeout(confirmTimer)
        ├─ confirmingHunkIndex.value = null
        ├─ patchText = buildHunkPatchText(filePath, hunkIndex=3)
        └─ emit('discard-hunk', { file, hunkIndex, patchText })
           ├─ GitDiffFileItem 透传
           ├─ GitDiffBodyContent 透传
           └─ GitDiffSidebar.onDiscardHunk:
              ├─ fileDiscardHunk.isDiscardingHunk.add("README.md#3")
              ├─ await fileDiscardHunk.discard({ file, hunkIndex, patchText, umo, worktree })
              │   └─ POST /spcode/file-discard-hunk
              ├─ 成功 → snackbar "已丢弃 1 个 hunk" + composable.refresh()
              └─ 失败 → snackbar (按 reason 分类)
                 └─ fileDiscardHunk.isDiscardingHunk.delete("README.md#3")

T+0~3s  用户单击其他位置 / 切文件 / 切 scope
        └─ 残留 confirmingHunkIndex 立即清空 (watch filePath / selectedScope)
           └─ 残留 confirmTimer onBeforeUnmount 时清理

T+3s    未再点击 → setTimeout 触发
        └─ confirmingHunkIndex.value = null (恢复原状)
```

### 5.2 `buildHunkPatchText(filePath, hunkIndex)` 算法

```typescript
function buildHunkPatchText(filePath: string, hunkIndex: number): string {
  // 1. 完整解析（不被 maxLines 截断）
  const fullText = extractDiffContent(props.content);
  const fullHunks = parseUnifiedDiff(fullText, Infinity);

  // 2. 跨 maxLines 定位同一 hunk（按 header 文本匹配，header 在单文件内唯一）
  const target = fullHunks.find((h) => h.hunkIndex === hunkIndex) ?? fullHunks[hunkIndex];
  if (!target) return "";

  // 3. 组装 patch（用 ASCII prefix，规避 parser 的 U+2212 视觉减号）
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

**关键不变量**：
- `parseUnifiedDiff` 单次扫描时为每个 hunk 分配 `hunkIndex = hunks.length`（push 前的索引）
- 在 `maxLines=Infinity` 与 `maxLines=30` 两次解析下，前 N 个 hunk 的 `hunkIndex` 一致
- 截断只影响**最后一个** hunk（被切断尾巴），不会影响前面 hunk 的完整性
- `find` + fallback 双保险：若 `hunkIndex` 找不到（极端 case：full 解析失败），回退到 `fullHunks[hunkIndex]` 数组访问，至少不会 crash

### 5.3 错误分类与 snackbar 等级

`classifyDiscardHunkReason` 分类规则（参考 `webapi-file-discard-hunk-api.md §3.5.2`）：

| 分类 | reason 集合 | snackbar 等级 | 文案 |
|------|------------|--------------|------|
| `fatal` | `not_a_git_repo`, `git_unavailable`, `feature_disabled` | `error` | 🛑 致命错误：{reason} — 联系管理员 |
| `user` | `not_modified`, `untracked_file`, `patch_malformed`, `patch_unsafe_path`, `multi_file_patch`, `patch_file_mismatch`, `patch_binary`, `patch_too_large`, `missing_file`, `file_not_found`, `path_unsafe` | `warning` | ⚠️ {reason} :{stderr 关键行} + 操作指引 |
| `retry` | `patch_apply_failed`, `patch_check_failed`, `git_error` | `info` | 🔄 {reason} — 文件可能已同步，刷新 diff 后重试 |
| `config` | `no_project_loaded`, `worktree_invalid`, `directory_missing`, `invalid_body` | `warning` | ⚙️ 配置错误：{reason} — 请重新加载项目 / 选择 worktree |
| `unknown` | 其他 | `error` | 未知错误：{reason} |

---

## 6. 组件级实现细节

### 6.1 `DiffPreview.vue` 改动

#### 6.1.1 Props 新增

```typescript
const props = withDefaults(
  defineProps<{
    // ... 现有 9 个 prop ...
    onDiscardHunk?: (params: { file: string; hunkIndex: number; patchText: string }) => void;
    /** Set of `${discardKeyPrefix}#${hunkIndex}` keys currently in flight. */
    discardingHunks?: ReadonlySet<string>;
    /** Used as the key prefix when checking `discardingHunks`. Defaults to filePath. */
    discardKeyPrefix?: string;
    discardable?: boolean;       // 默认 false；true 时才渲染按钮
  }>(),
  {
    // ... 现有 defaults ...
    discardable: false,
    discardingHunks: () => new Set<string>(),
    discardKeyPrefix: "",
  },
);

// 派生：当前 hunk 是否在请求中
const isCurrentHunkDiscarding = (hi: number): boolean => {
  const prefix = props.discardKeyPrefix || props.filePath;
  return props.discardingHunks.has(`${prefix}#${hi}`);
};
```

#### 6.1.2 hunk header DOM 重构（unified 模式，行 115-130）

```vue
<!-- 旧 -->
<button type="button" class="hunk-header" ...>
  <v-icon ...>mdi-chevron-right</v-icon>
  <span class="hunk-header-text">{{ hunk.header }}</span>
  <span class="hunk-header-count">{{ hunk.lines.length }}</span>
</button>

<!-- 新 -->
<div
  class="hunk-header"
  role="button"
  tabindex="0"
  :aria-expanded="!collapsedHunks.has(hi)"
  @click="toggleHunk(hi)"
  @keydown="onHunkHeaderKeydown"
>
  <v-icon size="12" class="hunk-chevron" :class="{ expanded: !collapsedHunks.has(hi) }">
    mdi-chevron-right
  </v-icon>
  <span class="hunk-header-text">{{ hunk.header }}</span>
  <span class="hunk-header-count">{{ hunk.lines.length }}</span>
  <!-- 新增：丢弃按钮（opt-in） -->
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
    <v-progress-circular v-if="isCurrentHunkDiscarding(hi)" indeterminate :size="12" :width="2" />
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

split 模式两处 hunk header（行 ~473 与 ~567）使用**同一**模板片段（`<div class="hunk-header" ...>` 内部含相同的按钮），不重复实现。

#### 6.1.3 新增 state 与 handler

```typescript
const confirmingHunkIndex = ref<number | null>(null);
let confirmTimer: ReturnType<typeof setTimeout> | null = null;

function onDiscardHunkClick(hi: number, e: MouseEvent): void {
  e.stopPropagation();   // 防止冒泡到 header 的 toggleHunk
  if (!props.onDiscardHunk || !props.discardable) return;
  if (isCurrentHunkDiscarding(hi)) return;
  if (confirmingHunkIndex.value === hi) {
    // 第二次点击 → 真正执行
    if (confirmTimer) { clearTimeout(confirmTimer); confirmTimer = null; }
    confirmingHunkIndex.value = null;
    const patchText = buildHunkPatchText(props.filePath, hi);
    if (!patchText) return;   // 防御：empty patch 不发
    props.onDiscardHunk({ file: props.filePath, hunkIndex: hi, patchText });
  } else {
    // 第一次点击 → 进入确认态
    confirmingHunkIndex.value = hi;
    confirmTimer = setTimeout(() => {
      confirmingHunkIndex.value = null;
      confirmTimer = null;
    }, 3000);
  }
}

function onHunkHeaderKeydown(e: KeyboardEvent): void {
  if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    if (confirmingHunkIndex.value !== null) return;   // 确认态锁定
    toggleHunk(/* hi 由 @click 提供；这里需要从 data-hi 读取或重构 */);
  }
}

function discardHunkAriaLabel(hi: number, header: string): string {
  return tm('spcodeProjectLoad.diffPreview.hunkDiscard.buttonAria', {
    hunk: header,
    file: props.filePath,
  });
}

function discardHunkTitle(hi: number, header: string): string {
  if (confirmingHunkIndex.value === hi) {
    return tm('spcodeProjectLoad.diffPreview.hunkDiscard.confirmingAria', { hunk: header });
  }
  return tm('spcodeProjectLoad.diffPreview.hunkDiscard.buttonTitle', { hunk: header });
}
```

**注意**：`onHunkHeaderKeydown` 重构时需保留原 `toggleHunk(hi)` 的 `hi` 参数传递路径——行 119 旧版本用 `@click="toggleHunk(hi)"` 闭包，新版本需要在 keydown handler 里拿到 `hi`。两种方案：

- **方案 1**：在 `onHunkHeaderKeydown(hi: number, e: KeyboardEvent)` 里显式传 hi
- **方案 2**：用 `data-hi` 属性 + `e.currentTarget`

**推荐方案 1**（更显式，与现有 `@click` 模式一致）。Keydown 改写为 `@keydown="(e) => onHunkHeaderKeydown(hi, e)"` 或类似 inline 形式。

#### 6.1.4 toggleHunk 守护

```typescript
function toggleHunk(idx: number): void {
  // 确认态锁定：避免用户在 "Confirm?" 态点 header 切换折叠，把确认态搞丢
  if (confirmingHunkIndex.value !== null) return;
  const next = new Set(collapsedHunks.value);
  if (next.has(idx)) next.delete(idx);
  else next.add(idx);
  collapsedHunks.value = next;
}
```

#### 6.1.5 残留状态清理

```typescript
// 切 file / props.content 变化时清空残留确认态
watch(
  () => [props.filePath, props.content],
  () => {
    if (confirmTimer) { clearTimeout(confirmTimer); confirmTimer = null; }
    confirmingHunkIndex.value = null;
  },
);

onBeforeUnmount(() => {
  if (confirmTimer) clearTimeout(confirmTimer);
  // 保留现有 isFullscreen 的 body overflow 清理
});
```

### 6.2 `GitDiffFileItem.vue` 改动

#### 6.2.1 Props 新增

```typescript
const props = defineProps<{
  // ... 现有 14 个 prop ...
  onDiscardHunk?: (file: string, hunkIndex: number, patchText: string) => void;
  discardingHunks?: ReadonlySet<string>;
  discardable?: boolean;
}>();
```

#### 6.2.2 emits 新增

```typescript
const emit = defineEmits<{
  // ... 现有 emits ...
  (e: "discard-hunk", file: string, hunkIndex: number, patchText: string): void;
}>();
```

#### 6.2.3 透传到 DiffPreview

`GitDiffFileItem` 透传时把 `file.path` 作为 `discardKeyPrefix` 传入，DiffPreview 用 `${prefix}#${hi}` 查 Set：

```vue
<DiffPreview
  :on-discard-hunk="onDiscardHunk"
  :discarding-hunks="discardingHunks"
  :discard-key-prefix="file.path"
  :discardable="discardable"
  ...
/>
```

### 6.3 `GitDiffBodyContent.vue` 改动

#### 6.3.1 Props 新增

```typescript
const props = defineProps<{
  // ... 现有 12 个 prop ...
  onDiscardHunk?: (file: string, hunkIndex: number, patchText: string) => void;
  /** Set of `${file}#${hunkIndex}` keys currently in flight. */
  discardingHunks?: ReadonlySet<string>;
}>();
```

#### 6.3.2 emits 新增

```typescript
const emit = defineEmits<{
  // ... 现有 emits ...
  (e: "discard-hunk", file: string, hunkIndex: number, patchText: string): void;
}>();
```

#### 6.3.3 `discardableFor(file)` 派生

```typescript
import { useSpcodeProjectStatus } from "@/composables/useSpcodeProjectStatus";

const spcodeStatus = useSpcodeProjectStatus();

function discardableFor(file: SpcodeGitDiffFile): boolean {
  if (!props.onDiscardHunk) return false;
  if (props.newFilePaths?.has(file.path)) return false;     // 新文件
  if (file.isBinary) return false;                            // 二进制
  if (!spcodeStatus.status.value.loaded) return false;        // 项目未加载
  if (!spcodeStatus.status.value.umo) return false;           // 无 umo
  return true;
}
```

#### 6.3.4 透传到 GitDiffFileItem

```vue
<GitDiffFileItem
  v-for="f in section.files"
  :key="f.path + ':' + f.status"
  :file="f"
  ...
  :on-discard-hunk="onDiscardHunk"
  :discarding-hunks="discardingHunks"
  :discardable="discardableFor(f)"
  @discard-hunk="(file, hi, patch) => emit('discard-hunk', file, hi, patch)"
  ...
/>
```

> **KISS 提醒**：`discardingHunks` 整体透传即可。`GitDiffFileItem` 不在 hunk 粒度上感知，hunkIndex 留给 DiffPreview 内部用 `${file.path}#${hi}` 查 Set。

### 6.4 `GitDiffSidebar.vue` 改动

#### 6.4.1 composable 引入与 handler

```typescript
import { useSpcodeFileDiscardHunk, type DiscardHunkResult } from "@/composables/useSpcodeFileDiscardHunk";

// ... 在 fileRestore 声明后追加 ...
const fileDiscardHunk = useSpcodeFileDiscardHunk();

// 39 reason → i18n key 映射
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
  // ... 其余 28 个 reason 都映射到 generic fallback ...
};

function classifySnackbarLevel(reason: string): "success" | "info" | "warning" | "error" {
  // 同 file-restore 的 4 分类
  const FATAL = new Set(["not_a_git_repo", "git_unavailable", "feature_disabled"]);
  const USER  = new Set(["not_modified", "untracked_file", "patch_malformed", "patch_unsafe_path",
                         "multi_file_patch", "patch_file_mismatch", "patch_binary", "patch_too_large",
                         "missing_file", "file_not_found", "path_unsafe"]);
  const RETRY = new Set(["patch_apply_failed", "patch_check_failed", "git_error"]);
  if (FATAL.has(reason)) return "error";
  if (RETRY.has(reason)) return "info";
  return "warning";   // user + config + unknown
}

async function onDiscardHunk(file: string, hunkIndex: number, patchText: string) {
  const umo = spcodeStatus.status.value.umo;
  if (!umo) return;
  const worktree = selectedWorktree.value;

  const key = `${file}#${hunkIndex}`;
  const result: DiscardHunkResult = await fileDiscardHunk.discard({
    file, hunkIndex, patchText, umo, worktree,
  });

  if (!result.ok && result.reason === "aborted") return;
  if (result.ok) {
    const n = result.snapshot.hunksReverted;
    const tmKey = n === 1
      ? "spcodeProjectLoad.diffSidebar.discardHunk.success"
      : "spcodeProjectLoad.diffSidebar.discardHunk.successMultiple";
    showSnackbar(
      tm(tmKey, { hunksReverted: n, file }),
      "success",
    );
    await composable.refresh();
  } else {
    const mapping = DISCARD_HUNK_REASON_I18N_KEYS[result.reason];
    const msg = mapping
      ? tm(mapping, { stderr: result.stderr ?? "" })
      : tm("spcodeProjectLoad.diffSidebar.discardHunk.error.reason.unknown", { reason: result.reason });
    showSnackbar(msg, classifySnackbarLevel(result.reason));
  }
  // key 会被 fileDiscardHunk.discard() 内部 add/delete，无需手动管理
}
```

#### 6.4.2 dispose

```typescript
function dispose() {
  // ... 现有 dispose 链 ...
  fileRestore.dispose();
  fileDiscardHunk.dispose();   // 新增
  // ...
}
```

#### 6.4.3 模板透传

`fileDiscardHunk.isDiscardingHunk` 是 `Ref<Set<string>>`（键 = `${file}#${hunkIndex}`），直接透传到下层即可：

```vue
<GitDiffBodyContent
  ...
  :on-discard-hunk="onDiscardHunk"
  :discarding-hunks="fileDiscardHunk.isDiscardingHunk.value"
  @discard-hunk="onDiscardHunk"
  ...
/>
```

### 6.5 CSS（`DiffPreview.vue` 末尾 `<style scoped>` 内追加）

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
  color: #ff9800;          /* warning 橙黄 */
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
  .hunk-discard-confirm-label { display: none; }   /* 移动端不显示文字 */
}
```

---

## 7. i18n 键

在 `dashboard/src/i18n/locales/{en-US,zh-CN,ru-RU}/features/chat.json` 同步新增以下键。完整 39 reason 的 i18n 文案示例见 §5.3，下表只列主键：

### 7.1 主键（3 个语种同步）

```jsonc
// 路径：spcodeProjectLoad.diffPreview.hunkDiscard.*
{
  "buttonAria":     "Discard hunk {hunk} in {file}",
  "buttonTitle":    "Discard this hunk. Click again within 3 seconds to confirm.",
  "confirmLabel":   "Confirm?",
  "confirmingAria": "Click again to confirm discarding hunk {hunk}",
  "loadingAria":    "Discarding hunk {hunk}",
}

// 路径：spcodeProjectLoad.diffSidebar.discardHunk.*
{
  "success":         "Discarded {hunksReverted} hunk from {file}",
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
}
```

中文 / 俄文翻译由实现者按现有 `spcodeProjectLoad.diffSidebar.restore.*` 键的语种对应风格填入（参考 `chat.json:495-540` 的 restore 文案）。

### 7.2 命名约定

- `hunkDiscard.*` 挂在 `diffPreview` 根下（与 `toolbar.*` / `group.*` / `summary.*` 同级），因为按钮在 DiffPreview 内部
- `discardHunk.*` 挂在 `diffSidebar` 根下（与 `restore.*` / `gitWorkflow.*` 同级），因为 snackbar/错误在 GitDiffSidebar 触发
- 命名清晰区分「按钮文本/aria」(`hunkDiscard.*`) 与「操作结果 snackbar」(`discardHunk.*`)

---

## 8. 风险与缓解

| # | 风险 | 缓解 |
|---|------|------|
| R1 | `parseUnifiedDiff` 把 `del` 行 `prefix` 设为 `−`（U+2212 视觉减号），重建 patch_text 时 `git apply` 会拒 | `buildHunkPatchText` 显式用 ASCII `-`/`+`/` `（§6.1.5 算法） |
| R2 | `parsedHunks` 按 `maxLines=30` 截断，丢弃时 hunk 内容不完整 | 重建时用 `parseUnifiedDiff(content, Infinity)` 取完整版；按 `hunkIndex` 跨 reference；`find` + 数组访问双保险（§5.2） |
| R3 | 用户在 `all` 视图丢 hunk 时，可能不明确 scope；后端按 X/Y 列路由，行为符合预期 | 成功 snackbar 展示 `result.snapshot.scope`（unstaged/staged），让用户清楚是回滚了 worktree 还是 index；无需前端做 scope 路由 |
| R4 | 服务端 6 步前置校验失败（39 个 reason） | 用 `DISCARD_HUNK_REASON_I18N_KEYS` 映射表 + `classifySnackbarLevel` 4 类（fatal/user/retry/config）；reason→level 分类参考 `webapi-file-discard-hunk-api.md §3.5.2` |
| R5 | 用户点确认按钮后切到其他 tab/文件 → 残留 `confirmingHunkIndex` | watch `[filePath, content]` 清理；`onBeforeUnmount` 清理 `confirmTimer`（§6.1.5） |
| R6 | 并发点多个 hunk → 多个并发 POST → git 内部状态竞争 | 不在前端串行；后端 `git apply --reverse` 是单文件局部操作，git 自带文件锁；如有问题由后端 reason 反馈（`patch_check_failed` / `patch_apply_failed`） |
| R7 | DiffPreview 多处使用（5 个 callsite） | prop 全部 optional；缺省 `discardable=false` → 无按钮；其他 4 个 callsite 完全不需改 |
| R8 | 截断场景下 `parsedHunks[hi]` 与 `fullHunks[hi]` 不对应 | 给 `DiffHunk` 加 `hunkIndex: number` 字段记录 full 解析时的索引；`buildHunkPatchText` 按 `hunkIndex` 在 full 列表里查找（§5.2） |
| R9 | `hunk-header` 重构为 `<div role="button">` 影响现有键盘交互 | 显式处理 `keydown.enter.space` → 调 `toggleHunk(hi)`（§6.1.3）；与 file row 的 refactor 模式完全一致（参考 `GitDiffFileItem.vue` 行 4-9 注释） |
| R10 | `confirmingHunkIndex` 切 scope 后的清理 | watch `props.content` 触发（hunk 内容变化 → 重建 parsedHunks → 索引失配），立即清空；watch 也覆盖 filePath 变化 |
| R11 | patch_text 超过 256 KB（API 限制） | `parsedHunks` 单 hunk 30 行，full 解析后单 hunk 也通常 < 1 KB；极端 case 触发 `patch_too_large` reason，snackbar 提示改用整文件 restore |
| R12 | `\ No newline at end of file` 解析 bug | parser 行 1293-1296 把 `\` 行设为 `type="ctx", prefix=" ", content=rawLine`，重建会得到 ` \\ No newline at end of file`（两空格）；但 `git apply` 接受这种格式，无功能影响。若严格修，可加 `if (line.content === "\\ No newline at end of file") lines.push(" \\" + line.content);` 但优先级低 |

---

## 9. 测试与验收

### 9.1 自动化测试

- ❌ **不**写 Vitest 单元测试（沿用姊妹 spec §1.4 决定：dashboard 尚未配置 vitest）
- ✅ **`pnpm typecheck`** —— 类型检查无错
- ✅ **`pnpm lint`** —— ruff/eslint 无 warning
- ✅ **`pnpm generate:api`** —— 仅当后端 API schema 变化时（本次无变化）

### 9.2 手动 E2E 验收清单

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

### 9.3 回归检查

- 现有 `commentable` 行内评论功能不受影响（prop 透传不冲突）
- 现有 hunk 折叠 (`collapsedHunks`) 不受影响
- 现有 fullscreen 模式不受影响
- 现有 `showAllLines` 30 行截断逻辑不受影响
- 整文件级 `file-restore` 不受影响（独立 composable）
- stage/unstage 按钮不受影响

---

## 10. 未来扩展（YAGNI 留白）

- 批量多 hunk 一次性 discard（前端循环调 API）
- discard 的「撤销」按钮（需后端新增端点，git 真正回滚后无 native 撤销）
- 跨 worktree 切换的 button 状态保留
- hunk header 旁的「应用 patch」按钮（与 discard 反向）
- DiffPreview 的 split 模式独有 UI（hunk header 视觉优化）
- 新文件场景下的 hunk discard（需后端支持 untracked 文件局部回滚）

---

## 11. 实施步骤（高层）

1. 在 `dashboard/src/composables/` 下新建 `useSpcodeFileDiscardHunk.ts` 与 `parseSpcodeFileDiscardHunk.ts`
2. 在 `DiffPreview.vue` 中：
   - 改 `DiffHunk` 加 `hunkIndex` 字段
   - 改 `parseUnifiedDiff` 填 `hunkIndex`
   - 改 hunk header 为 `<div role="button">`（unified + split 模式）
   - 加 `onDiscardHunk` / `discardingHunks` / `discardKeyPrefix` / `discardable` props
   - 加 `confirmingHunkIndex` state + 3s timer
   - 加 `buildHunkPatchText` helper
   - 加按钮 + CSS
3. `GitDiffFileItem.vue` / `GitDiffBodyContent.vue` 加 prop 透传 + `discardableFor` 派生
4. `GitDiffSidebar.vue` 引入 composable + `onDiscardHunk` handler + 39 reason i18n + dispose
5. i18n 三语同步新增键
6. `pnpm typecheck` / `pnpm lint` 通过
7. 手动 E2E 验收清单 20 项全通过

---

**作者**: elecvoid243
**生成时间**: 2026-07-07 09:54 CST
