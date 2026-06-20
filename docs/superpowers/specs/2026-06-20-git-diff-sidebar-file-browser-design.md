# Dashboard ChatUI「Git Diff Sidebar File Browser」— 设计文档

| 项目 | 内容 |
|------|------|
| 主题 | 在现有 `GitDiffSidebar` 中新增 **Files 视图**(双栏布局),通过 view-mode 切换器与 Diff 视图并列;Files 视图绑定到当前 worktree,4 个状态(viewMode/selectedWorktree/selectedScope/currentPath)全部 localStorage 持久化 |
| 日期 | 2026-06-20 |
| 作者 | elecvoid243 |
| 状态 | Draft — 待用户审阅 |
| 关联插件 | `astrbot_plugin_spcode_toolkit`(v2.9.0+ 含 `/spcode/file-browser` 端点;spec 见 `astrbot_plugin_spcode_toolkit/docs/superpowers/specs/2026-06-20-file-browser-endpoint-design.md`) |
| 关联端点 | `GET /plugins/extensions/spcode/file-browser` |
| 关联代码 | `dashboard/src/components/chat/GitDiffSidebar.vue`、3 个 spcode composable、`dashboard/src/utils/shiki.js` |
| 前置 spec | `docs/superpowers/specs/2026-06-17-chatui-git-diff-sidebar-design.md`(本 spec 是其 v2 扩展) + `2026-06-18-git-worktree-switcher-design.md` + `2026-06-20-git-diff-scope-switcher-design.md` |
| API 文档 | `astrbot_plugin_spcode_toolkit/docs/api/web-api.md` §3.5 |

---

## 1. 背景与目标

### 1.1 现状

`GitDiffSidebar` 已交付(v 2026-06-17,扩展自 v 2026-06-18 worktree + 2026-06-20 scope),可拖拽侧边栏渲染当前 worktree 的 git diff,支持 `unstaged/staged/all` 三种 scope。

spcode 插件 v2.9.0 新增 `/spcode/file-browser` 端点(无 umo、C 模型、5MB 上限 + 8KB 二进制嗅探),允许前端拉取任意绝对路径的目录列表或文件文本。

**当前痛点**:用户想在 WebChat 里浏览项目结构(不限于 git 改动),必须切到外部文件管理器或 IDE;`GitDiffSidebar` 只能看"git 知道的改动",无法看"项目里其他文件"。

### 1.2 目标

在 `GitDiffSidebar` 中**新增 Files 视图**,与现有 Diff 视图并列:

1. 顶部新增 view-mode 切换器(📁 Files / 📊 Diff),pill 样式
2. Files 视图为**双栏布局**:
   - **左栏**:面包屑 + 单层目录列表(支持目录/文件/symlink 区分 + 大小 + mtime)
   - **右栏**:选中文件的内容预览(Shiki 高亮,与 `astrbot_file_read_tool` 工具结果样式一致)
3. **Files 视图绑定到当前 worktree**:worktree tabs 在两种视图下都显示(多 worktree 时),切换 worktree 重置 `currentPath` 到新 worktree 的根
4. **4 个状态全部 localStorage 持久化**:viewMode、selectedWorktree、selectedScope、fileBrowserCurrentPath(打开 sidebar 时按规则校验恢复)
5. 复用现有 GitDiffSidebar 的所有外壳:resize、transition、close、refresh 按钮

### 1.3 非目标(显式不做)

- ❌ **不**修改 spcode 插件后端(`/file-browser` 端点已就绪)
- ❌ **不**实现写操作(无新建/删除/重命名/修改 — file-browser 是只读)
- ❌ **不**递归目录浏览(单层 + 手动逐层展开,符合端点契约)
- ❌ **不**实现文件搜索/过滤/全局快捷键
- ❌ **不**实现多 tab 文件预览(同时打开多个文件预览)
- ❌ **不**实现拖拽上传、文件下载
- ❌ **不**修改现有 `GitDiffSidebar` 的 Diff 视图行为(scope/worktree 仅做小幅适配)
- ❌ **不**修改 spcode 端点契约、API 路径、参数

---

## 2. 设计决策(已与用户确认)

| # | 决策点 | 选择 | 理由 |
|---|--------|------|------|
| 1 | 集成方式 | **方案 B**:`GitDiffSidebar` 内嵌 view-mode tab 切换器(同外壳、双模式) | 复用 resize/transition/header;用户明确说"给 GitDiffSidebar 添加功能";与 `TodoSidebar/ReasoningSidebar` 互斥的复杂度不再增加 |
| 2 | Files 视图布局 | **双栏**(左目录列表 + 右文件预览) | 匹配用户提供的预览图设计语言;左目录导航 + 右预览符合 IDE 习惯 |
| 3 | Files 视图根路径 | **绑定到当前 worktree**(`selectedWorktree ?? mainWorktreeRoot`) | 用户选择"Files 视图绑定到当前 worktree";让 worktree 切换在 Files 视图下也有意义 |
| 4 | worktree tabs 可见性 | **两种视图下都显示**(仅多 worktree 时) | 用户在 Files 视图下可直接切换 worktree,无需先切到 Diff 视图 |
| 5 | Files 视图下切换 worktree | **重置 `currentPath` 到新 worktree 根** | 与 Diff 视图切换 worktree 重置 scope 的行为一致;用户当前浏览位置丢失是新工作上下文的合理代价 |
| 6 | viewMode 持久化 | **持久化**到 localStorage | 用户明确要求"记住上次选择" |
| 7 | selectedWorktree 持久化 | **持久化**到 localStorage | 用户要求"持久化也要包括" |
| 8 | selectedScope 持久化 | **持久化**到 localStorage | 用户要求"持久化也要包括" |
| 9 | fileBrowserCurrentPath 持久化 | **持久化**到 localStorage(debounce 300ms) | 用户要求"持久化也要包括";debounce 避免快速导航时 thrashing |
| 10 | 默认 viewMode | **`'files'`** | 更通用;首次访问用户最可能想"看看项目里有什么" |
| 11 | 默认 selectedWorktree | **`null`**(主 worktree) | 与现有 diff 行为一致 |
| 12 | 默认 selectedScope | **`'unstaged'`** | 与现有 diff 行为一致;spcode v3.1 默认 |
| 13 | 默认 currentPath | **(当前根路径)** | 项目未加载时为空字符串,加载后取根 |
| 14 | currentPath 加载时校验 | **必须以当前根路径开头**(Windows 路径归一化) | 防止持久化路径指向已切换的项目或 worktree |
| 15 | localStorage 不可用处理 | **静默降级**,全部用默认值,不抛错 | 隐私模式 / quota 满时优雅运行 |
| 16 | 跨标签页 storage 事件同步 | **不做** | 单 tab 场景为主;监听 storage 事件增加复杂度,避免 |

---

## 3. 架构与文件改动

### 3.1 架构原则

- **零后端改动**:完全复用 spcode 现有 `/spcode/file-browser` 端点
- **零 spcode 改动**:通过标准 HTTP endpoint 调用
- **零 `DiffPreview.vue` / `Shiki` 改动**:作为工具复用,样式零侵入
- **零 `useSpcodeProjectStatus.ts` / `useSpcodeWorktrees.ts` 改动**:composable 保持原状,sidebar 内部组合
- **Inline-first**:helper 函数写在 composable / 组件文件顶部,不强行抽公共文件
- **AGENTS.md 适用条款**:Google-style docstring(TSDoc)、英文注释、conventional commit messages;`pathlib` / `ruff` 不适用
- **状态机复用**:`useSpcodeGitDiff` 的 `idle/loading/ok/error` 模式,`useSpcodeFileBrowser` 同构

### 3.2 文件改动清单

| 层级 | 文件 | 性质 | 说明 |
|------|------|------|------|
| 新增 | `dashboard/src/composables/parseSpcodeFileBrowser.ts` | 纯函数模块 | 三态判别(directory / file / symlink) + 严格类型守卫(见 §4.2) |
| 新增 | `dashboard/src/composables/useSpcodeFileBrowser.ts` | composable | fetch + 状态机 + AbortController + dispose(**不轮询**,按需) |
| 新增 | `dashboard/src/components/chat/message_list_comps/FileBrowserView.vue` | 新组件 | Files 视图主组件(双栏容器,协调左/右子组件) |
| 新增 | `dashboard/src/components/chat/message_list_comps/FileBrowserEntryList.vue` | 新组件 | 左栏:目录列表渲染 + 点击导航 |
| 新增 | `dashboard/src/components/chat/message_list_comps/FileBrowserBreadcrumb.vue` | 新组件 | 面包屑(可点击路径段) |
| 新增 | `dashboard/src/components/chat/message_list_comps/FileBrowserFilePreview.vue` | 新组件 | 右栏:Shiki 高亮 + 元信息 + 错误兜底 |
| 改动 | `dashboard/src/components/chat/GitDiffSidebar.vue` | 修改 | 加 view-mode tabs + worktree tabs 提升到顶层 + 持久化 hooks + Files 视图条件渲染 + localStorage 监听 |
| 改动 | `dashboard/src/i18n/locales/{zh-CN,en-US,ru-RU}/features/chat.json` | 修改 | 新增 `spcodeProjectLoad.fileBrowser.*` 键(见 §7) |

> **测试文件**:沿用姊妹 spec 决定不写 Vitest(dashboard 尚未配置);依赖 `pnpm typecheck` + `pnpm lint` + 手动跑 §9 端到端验收清单

### 3.3 改动量估算

- 新增代码:~700-900 行(2 个 composable/parse + 4 个组件)
- 改动现有代码:~80-120 行(`GitDiffSidebar.vue` 结构调整 + 持久化逻辑 + 3 个 i18n json 各加 ~40 行)
- 风险面:1 个现有文件中等改动 + 4 个新组件 + 1 个新 composable;无破坏性 diff 行为

### 3.4 模块依赖图

```
GitDiffSidebar.vue (修改)
  ├─ GitDiffBodyContent.vue           (existing, Diff 视图用)
  │     └─ GitDiffFileItem.vue
  │
  ├─ FileBrowserView.vue              [NEW]
  │     ├─ FileBrowserBreadcrumb.vue  [NEW]
  │     ├─ FileBrowserEntryList.vue   [NEW]
  │     └─ FileBrowserFilePreview.vue [NEW]
  │           └─ shiki.js             (existing, ensureShikiLanguages + renderShikiCode)
  │
  ├─ useSpcodeGitDiff.ts              (existing, Diff 视图用)
  ├─ useSpcodeFileBrowser.ts          [NEW]
  ├─ useSpcodeWorktrees.ts            (existing,两种视图共享)
  └─ useSpcodeProjectStatus.ts        (existing,两种视图共享)
```

---

## 4. 组件详细设计

### 4.1 `parseSpcodeFileBrowser.ts`(纯函数模块)

#### 类型定义

```typescript
// Author: elecvoid243, 2026-06-20
// Spec: docs/superpowers/specs/2026-06-20-git-diff-sidebar-file-browser-design.md §4.1
// 与 spcode 插件 file-browser 端点契约一一对应;后端 spec 见
// astrbot_plugin_spcode_toolkit/docs/superpowers/specs/2026-06-20-file-browser-endpoint-design.md §3.5

/** 单层目录列表的 entry 项;目录/文件/symlink 三态 */
export interface SpcodeFileBrowserEntry {
  /** 该项的绝对路径(round-trip) */
  path: string;
  /** basename(原始字符串,不做转义) */
  name: string;
  /** "directory" / "file" / "symlink" — 注意:symlink 不跟随,后端显式标注 */
  type: "directory" | "file" | "symlink";
  /** 字节数;目录为 null;symlink 为 lstat().st_size(target 字符串字节长度) */
  size: number | null;
  /** mtime(unix 秒);lstat 失败时为 null */
  mtime: number | null;
  /** 是否符号链接 — 与 type 配合:type === "symlink" 时 is_symlink 必为 true */
  is_symlink: boolean;
  /** 仅 symlink:target 字符串(原始终端) */
  target?: string;
  /** 仅 symlink:target 是否存在(用于"悬空链接"红标) */
  target_exists?: boolean;
}

/** 目录响应快照 */
export interface SpcodeFileBrowserDirectorySnapshot {
  meta: {
    /** 当前路径(用户最近一次传入的 path) */
    path: string;
    /** 返回的 entry 数(过滤隐藏后,可能 < 实际目录项数) */
    entryCount: number;
    /** 是否因 > 1000 项被截断 */
    truncated: boolean;
    /** 后端硬上限 = 1000 */
    maxEntries: number;
    /** 后端 reason;成功 = null;截断 = "directory_listing_truncated" */
    reason: string | null;
    /** 拉取耗时(毫秒,后端给) */
    elapsedMs: number;
    /** 前端拉取时间戳 */
    fetchedAt: number;
  };
  /** 排序后的 entry 列表(目录 → 文件 → symlink) */
  entries: SpcodeFileBrowserEntry[];
}

/** 文件响应快照 */
export interface SpcodeFileBrowserFileSnapshot {
  meta: {
    path: string;
    name: string;
    /** 字节数(无论 reason 都返回) */
    size: number;
    mtime: number | null;
    /** 5 MB */
    maxBytes: number;
    /** "utf-8" / null(过大/二进制时) */
    encoding: "utf-8" | null;
    /** false / true / null(read_text 抛异常时为 null,前端统一按"无法显示"处理) */
    isBinary: boolean | null;
    /** 后端 reason;成功 = null;过大 = "file_too_large";二进制 = "binary_file" */
    reason: string | null;
    elapsedMs: number;
    fetchedAt: number;
  };
  /** 文本时为字符串;过大/二进制/异常时为 null */
  content: string | null;
}

/** symlink 响应快照(顶层 symlink,即 path 本身是 symlink) */
export interface SpcodeFileBrowserSymlinkSnapshot {
  meta: {
    path: string;
    name: string;
    size: number;
    mtime: number | null;
    isSymlink: true;
    target: string;
    targetExists: boolean;
    elapsedMs: number;
    fetchedAt: number;
  };
}

/** 后端 raw 响应(三态判别) */
export interface SpcodeFileBrowserRawResponse {
  type: "file" | "directory" | "symlink" | null;
  path: string;
  name: string;
  size: number;
  mtime: number | null;
  is_symlink: boolean;
  // file
  encoding?: "utf-8" | null;
  is_binary?: boolean | null;
  content?: string | null;
  max_bytes?: number;
  // directory
  entry_count?: number;
  truncated?: boolean;
  max_entries?: number;
  entries?: Array<{
    path: string;
    name: string;
    type: "directory" | "file" | "symlink";
    size: number | null;
    mtime: number | null;
    is_symlink: boolean;
    target?: string;
    target_exists?: boolean;
  }>;
  // symlink
  target?: string;
  target_exists?: boolean;
  // 错误 reason
  reason: string | null;
  elapsed_ms: number;
}

/** 统一快照 — 用 kind 做判别式 union */
export type SpcodeFileBrowserSnapshot =
  | { kind: "directory"; snapshot: SpcodeFileBrowserDirectorySnapshot }
  | { kind: "file"; snapshot: SpcodeFileBrowserFileSnapshot }
  | { kind: "symlink"; snapshot: SpcodeFileBrowserSymlinkSnapshot };
```

#### 解析器

```typescript
export function parseSpcodeFileBrowser(
  data: SpcodeFileBrowserRawResponse,
): SpcodeFileBrowserSnapshot {
  // 三态判别(与 spec §5 一致)
  if (data.type === null) {
    // 真错误 — throw 给 composable 统一处理
    throw new FileBrowserParseError(data.reason ?? "unknown");
  }
  const fetchedAt = Date.now();
  if (data.type === "directory") {
    return {
      kind: "directory",
      snapshot: {
        meta: {
          path: data.path,
          entryCount: data.entry_count ?? 0,
          truncated: data.truncated ?? false,
          maxEntries: data.max_entries ?? 1000,
          reason: data.reason ?? null,
          elapsedMs: data.elapsed_ms ?? 0,
          fetchedAt,
        },
        entries: Array.isArray(data.entries) ? data.entries.map(normalizeEntry) : [],
      },
    };
  }
  if (data.type === "file") {
    return {
      kind: "file",
      snapshot: {
        meta: {
          path: data.path,
          name: data.name,
          size: data.size ?? 0,
          mtime: data.mtime ?? null,
          maxBytes: data.max_bytes ?? 5 * 1024 * 1024,
          encoding: data.encoding ?? null,
          isBinary: data.is_binary ?? null,
          reason: data.reason ?? null,
          elapsedMs: data.elapsed_ms ?? 0,
          fetchedAt,
        },
        content: data.content ?? null,
      },
    };
  }
  // type === "symlink"
  return {
    kind: "symlink",
    snapshot: {
      meta: {
        path: data.path,
        name: data.name,
        size: data.size ?? 0,
        mtime: data.mtime ?? null,
        isSymlink: true,
        target: data.target ?? "",
        targetExists: data.target_exists ?? false,
        elapsedMs: data.elapsed_ms ?? 0,
        fetchedAt,
      },
    },
  };
}

class FileBrowserParseError extends Error {
  constructor(public reason: string) {
    super(`file-browser parse error: ${reason}`);
    this.name = "FileBrowserParseError";
  }
}
```

### 4.2 `useSpcodeFileBrowser.ts`(composable)

```typescript
// Author: elecvoid243, 2026-06-20
// Spec: docs/superpowers/specs/2026-06-20-git-diff-sidebar-file-browser-design.md §4.2

import { ref, watch, toValue, type Ref, type MaybeRef } from "vue";
import { pluginExtensionApi } from "@/api/v1";

export type FileBrowserFetchState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "directory"; snapshot: SpcodeFileBrowserDirectorySnapshot }
  | { kind: "file"; snapshot: SpcodeFileBrowserFileSnapshot }
  | { kind: "symlink"; snapshot: SpcodeFileBrowserSymlinkSnapshot }
  | { kind: "error"; reason: string; previousSnapshot?: ... };

export interface UseSpcodeFileBrowser {
  state: Ref<FileBrowserFetchState>;
  refresh: (path: string) => Promise<void>;
  dispose: () => void;
}

/**
 * Composable for file-browser endpoint.
 *
 * Per spcode file-browser spec §3.5.1: this composable does NOT depend on umo
 * (the endpoint is stateless and accepts absolute path).
 *
 * Unlike useSpcodeGitDiff, this composable does NOT poll — file content is
 * loaded on demand (user clicks directory / file). Callers invoke refresh(path)
 * explicitly; the composable also auto-refreshes when the pathRef changes.
 *
 * The composable is per-instance (not module-level singleton), matching
 * useSpcodeGitDiff pattern. GitDiffSidebar instantiates one and disposes it
 * in onBeforeUnmount.
 */
export function useSpcodeFileBrowser(
  pathRef: MaybeRef<string>,
): UseSpcodeFileBrowser {
  const state = ref<FileBrowserFetchState>({ kind: "idle" });
  let abortController: AbortController | null = null;
  let isMounted = true;

  async function refresh(targetPath?: string): Promise<void> {
    if (!isMounted) return;
    const path = targetPath ?? toValue(pathRef);
    if (!path) {
      // 空路径视同未传,后端会返回 path_not_found;前端先短路避免无效请求
      const prev = state.value.kind === "ok-kind" ? state.value.snapshot : undefined;
      state.value = { kind: "error", reason: "path_not_found", previousSnapshot: prev };
      return;
    }
    abortController?.abort();
    abortController = new AbortController();
    const isFirst = !["directory", "file", "symlink"].includes(state.value.kind);
    if (isFirst) state.value = { kind: "loading" };
    try {
      const resp = await pluginExtensionApi.get<{ data: SpcodeFileBrowserRawResponse }>(
        "spcode/file-browser",
        { params: { path }, signal: abortController.signal },
      );
      if (!isMounted) return;
      const data = resp.data?.data;
      if (!data) throw new Error("empty response data");
      const snapshot = parseSpcodeFileBrowser(data);
      state.value = snapshot;
    } catch (err) {
      if (!isMounted) return;
      if ((err as { name?: string })?.name === "CanceledError") return;
      if (err instanceof FileBrowserParseError) {
        // data.type === null 的真错误
        const prev = state.value.kind === "directory" || state.value.kind === "file" || state.value.kind === "symlink"
          ? state.value.snapshot : undefined;
        state.value = { kind: "error", reason: err.reason, previousSnapshot: prev };
        return;
      }
      const prev = state.value.kind === "directory" || state.value.kind === "file" || state.value.kind === "symlink"
        ? state.value.snapshot : undefined;
      state.value = { kind: "error", reason: classifyError(err), previousSnapshot: prev };
    }
  }

  // pathRef 变化时自动刷新(同 useSpcodeGitDiff 的 watcher 模式)
  watch(
    () => toValue(pathRef),
    () => { if (isMounted) void refresh(); },
    { flush: "post" },
  );

  function dispose(): void {
    isMounted = false;
    abortController?.abort();
    abortController = null;
  }

  return { state, refresh, dispose };
}

function classifyError(err: unknown): string {
  if (typeof err === "object" && err !== null) {
    const anyErr = err as { code?: string; message?: string };
    if (anyErr.code === "ERR_NETWORK" || /network/i.test(anyErr.message ?? "")) {
      return "network";
    }
  }
  return "unknown";
}
```

### 4.3 `FileBrowserView.vue` 主组件

```vue
<!-- Author: elecvoid243, 2026-06-20
     Spec: docs/superpowers/specs/2026-06-20-git-diff-sidebar-file-browser-design.md §4.3 -->
<script setup lang="ts">
import { computed, watch } from "vue";
import { useModuleI18n } from "@/i18n/composables";
import { useSpcodeProjectStatus } from "@/composables/useSpcodeProjectStatus";
import { useSpcodeWorktrees } from "@/composables/useSpcodeWorktrees";
import { useSpcodeFileBrowser } from "@/composables/useSpcodeFileBrowser";
import FileBrowserBreadcrumb from "./FileBrowserBreadcrumb.vue";
import FileBrowserEntryList from "./FileBrowserEntryList.vue";
import FileBrowserFilePreview from "./FileBrowserFilePreview.vue";

const props = defineProps<{
  currentPath: string;
  isDark?: boolean;
}>();
const emit = defineEmits<{ (e: "navigate", path: string): void }>();

const { tm } = useModuleI18n("features/chat");
const spcodeStatus = useSpcodeProjectStatus();
const worktreesComposable = useSpcodeWorktrees();

const fileBrowserComposable = useSpcodeFileBrowser(
  computed(() => props.currentPath),
);

const mainWorktreePath = computed(() => {
  const s = worktreesComposable.state.value;
  if (s.kind !== "ok") return null;
  return s.snapshot.worktrees.find((w) => w.isMain)?.path ?? null;
});

// 在 Files 视图下,响应 worktree 切换时父组件会重置 currentPath
// 此处仅做渲染分发
</script>

<template>
  <div class="file-browser-view">
    <!-- 项目未加载时占位 -->
    <div v-if="!spcodeStatus.status.value.loaded" class="file-browser-empty">
      <v-icon size="36" color="grey">mdi-folder-open-outline</v-icon>
      <span class="empty-text">{{ tm("spcodeProjectLoad.fileBrowser.placeholder") }}</span>
    </div>

    <template v-else>
      <!-- 顶部:面包屑 -->
      <FileBrowserBreadcrumb
        :current-path="currentPath"
        :root-path="rootPath"
        @navigate="(p) => emit('navigate', p)"
      />

      <!-- 主体:双栏 -->
      <div class="file-browser-body">
        <!-- 左栏:目录列表 -->
        <FileBrowserEntryList
          :state="fileBrowserComposable.state.value"
          :current-path="currentPath"
          @navigate="(p) => emit('navigate', p)"
        />

        <!-- 分隔线 -->
        <div class="file-browser-divider" />

        <!-- 右栏:文件预览 -->
        <FileBrowserFilePreview
          :state="fileBrowserComposable.state.value"
          :is-dark="!!isDark"
        />
      </div>
    </template>
  </div>
</template>

<style scoped>
.file-browser-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
.file-browser-body {
  display: flex;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
.file-browser-divider {
  width: 1px;
  background: rgba(var(--v-theme-on-surface), 0.1);
  flex-shrink: 0;
}
.file-browser-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 32px 16px;
  min-height: 200px;
  color: rgba(var(--v-theme-on-surface), 0.6);
}
.empty-text { font-size: 14px; }
</style>
```

### 4.4 `FileBrowserEntryList.vue` 左栏

渲染当前目录的 `entries[]`,处理 3 种 type + 截断 warning + 加载/错误态。

```vue
<!-- Author: elecvoid243, 2026-06-20 -->
<script setup lang="ts">
import { computed } from "vue";
import { useModuleI18n } from "@/i18n/composables";
import type { FileBrowserFetchState } from "@/composables/useSpcodeFileBrowser";

const props = defineProps<{
  state: FileBrowserFetchState;
  currentPath: string;
}>();
const emit = defineEmits<{ (e: "navigate", path: string): void }>();
const { tm } = useModuleI18n("features/chat");

const entries = computed(() => {
  if (props.state.kind === "directory") return props.state.snapshot.entries;
  return [];
});
const truncated = computed(() => {
  return props.state.kind === "directory" && props.state.snapshot.meta.truncated;
});

const TYPE_ICONS: Record<string, { icon: string; color: string }> = {
  directory: { icon: "mdi-folder", color: "primary" },
  file: { icon: "mdi-file-document-outline", color: "grey" },
  symlink: { icon: "mdi-link-variant", color: "info" },
};

function handleClick(entry: SpcodeFileBrowserEntry): void {
  // 悬空 symlink:点击无效(仅显示提示)
  if (entry.type === "symlink" && entry.target_exists === false) return;
  emit("navigate", entry.path);
}
</script>

<template>
  <div class="file-browser-entry-list">
    <div v-if="truncated" class="file-browser-truncated-warning">
      {{ tm("spcodeProjectLoad.fileBrowser.truncated") }}
    </div>

    <div v-if="state.kind === 'loading'" class="file-browser-loading">
      <v-progress-circular indeterminate :size="20" />
      <span>{{ tm("spcodeProjectLoad.fileBrowser.loading") }}</span>
    </div>

    <div v-else-if="entries.length === 0 && state.kind === 'directory'" class="file-browser-empty-dir">
      <v-icon size="24" color="grey">mdi-folder-open-outline</v-icon>
      <span>{{ tm("spcodeProjectLoad.fileBrowser.empty") }}</span>
    </div>

    <ul v-else class="file-browser-entries">
      <li
        v-for="entry in entries"
        :key="entry.path"
        class="file-browser-entry"
        :class="{
          'is-symlink': entry.type === 'symlink',
          'is-dangling': entry.type === 'symlink' && entry.target_exists === false,
        }"
        @click="handleClick(entry)"
      >
        <v-icon :size="16" :color="TYPE_ICONS[entry.type]?.color ?? 'grey'">
          {{ TYPE_ICONS[entry.type]?.icon ?? "mdi-help" }}
        </v-icon>
        <span class="entry-name">{{ entry.name }}</span>
        <span v-if="entry.type === 'symlink' && entry.target" class="entry-symlink-target">
          → {{ entry.target }}
        </span>
        <span v-if="entry.size !== null && entry.type === 'file'" class="entry-size">
          {{ formatBytes(entry.size) }}
        </span>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.file-browser-entry-list {
  flex: 0 0 40%;
  min-width: 140px;
  overflow-y: auto;
  padding: 4px 0;
  background: rgba(var(--v-theme-on-surface), 0.02);
}
.file-browser-truncated-warning {
  padding: 6px 12px;
  background: rgba(255, 193, 7, 0.12);
  color: rgb(255, 152, 0);
  font-size: 11px;
  border-bottom: 1px solid rgba(255, 193, 7, 0.3);
}
.file-browser-loading,
.file-browser-empty-dir {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 16px 12px;
  color: rgba(var(--v-theme-on-surface), 0.6);
  font-size: 12px;
}
.file-browser-entries {
  list-style: none;
  margin: 0;
  padding: 0;
}
.file-browser-entry {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  font-size: 12.5px;
  cursor: pointer;
  font-family: ui-monospace, monospace;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.04);
}
.file-browser-entry:hover {
  background: rgba(var(--v-theme-on-surface), 0.06);
}
.file-browser-entry.is-dangling {
  opacity: 0.5;
  cursor: not-allowed;
  color: rgb(248, 81, 73);
}
.entry-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.entry-symlink-target {
  color: rgba(var(--v-theme-on-surface), 0.5);
  font-size: 10.5px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 60px;
}
.entry-size {
  color: rgba(var(--v-theme-on-surface), 0.5);
  font-size: 10.5px;
  flex-shrink: 0;
}
</style>
```

### 4.5 `FileBrowserFilePreview.vue` 右栏

复用 Shiki 高亮,与 `ToolResultView.vue` 的 `astrbot_file_read_tool` 分支同源。

```vue
<!-- Author: elecvoid243, 2026-06-20 -->
<script setup lang="ts">
import { computed, ref, onMounted, watch } from "vue";
import { useModuleI18n } from "@/i18n/composables";
import { ensureShikiLanguages, renderShikiCode, escapeHtml } from "@/utils/shiki";
import type { FileBrowserFetchState } from "@/composables/useSpcodeFileBrowser";

const props = defineProps<{
  state: FileBrowserFetchState;
  isDark: boolean;
}>();
const { tm } = useModuleI18n("features/chat");

const shikiHighlighter = ref<any>(null);
const shikiReady = ref(false);
onMounted(async () => {
  try {
    shikiHighlighter.value = await ensureShikiLanguages();
    shikiReady.value = true;
  } catch (err) {
    console.error("Shiki init failed:", err);
  }
});

// Shiki 与 useSpcodeGitDiff.ts 同源的 detectLanguage 函数
function detectLanguage(path: string): string {
  const EXT_TO_LANG: Record<string, string> = {
    ".py":"python",".js":".mjs":".cjs":"javascript",".ts":"typescript",".tsx":"tsx",".jsx":"jsx",
    ".vue":"vue",".json":"json",".yaml":".yml":"yaml",".sh":".bash":".zsh":"bash",
    ".css":"css",".html":".htm":"html",".xml":"xml",".md":"markdown",".sql":"sql",
    ".c":".h":"c",".cpp":".cc":".cxx":".hpp":"cpp",".go":"go",".rs":"rust",".diff":".patch":"diff",
  };
  const m = path.match(/\.([\w]+)$/i);
  if (!m) return "text";
  return EXT_TO_LANG["." + m[1].toLowerCase()] || "text";
}

const highlightedHtml = computed(() => {
  if (props.state.kind !== "file" || !props.state.snapshot.content) return "";
  if (!shikiReady.value || !shikiHighlighter.value) {
    return `<pre><code>${escapeHtml(props.state.snapshot.content)}</code></pre>`;
  }
  try {
    return renderShikiCode(
      shikiHighlighter.value,
      props.state.snapshot.content,
      detectLanguage(props.state.snapshot.meta.path),
      "auto",  // 双主题自适应
    );
  } catch (err) {
    console.error("Shiki render failed:", err);
    return `<pre><code>${escapeHtml(props.state.snapshot.content)}</code></pre>`;
  }
});

async function copyContent(): Promise<void> {
  if (props.state.kind !== "file" || !props.state.snapshot.content) return;
  try {
    await navigator.clipboard.writeText(props.state.snapshot.content);
    // 简单提示:1.5s 后按钮文本恢复
    copyFeedback.value = tm("spcodeProjectLoad.fileBrowser.preview.copySuccess");
    setTimeout(() => { copyFeedback.value = ""; }, 1500);
  } catch (err) {
    console.error("Copy failed:", err);
  }
}
const copyFeedback = ref("");

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}
function formatMtime(mtime: number | null): string {
  if (!mtime) return "—";
  return new Date(mtime * 1000).toLocaleString();
}
</script>

<template>
  <div class="file-browser-preview">
    <!-- 加载中 -->
    <div v-if="state.kind === 'loading'" class="preview-center">
      <v-progress-circular indeterminate :size="24" />
      <span>{{ tm("spcodeProjectLoad.fileBrowser.loading") }}</span>
    </div>

    <!-- 错误 -->
    <div v-else-if="state.kind === 'error'" class="preview-center">
      <v-icon size="32" color="error">mdi-alert-circle-outline</v-icon>
      <div class="preview-error-title">{{ tm("spcodeProjectLoad.fileBrowser.error.loadFailedTitle") }}</div>
      <div class="preview-error-detail">
        {{ localizedReason(state.reason) }}
      </div>
    </div>

    <!-- 目录状态(左栏负责列表渲染,右栏只显示提示) -->
    <div v-else-if="state.kind === 'directory'" class="preview-center">
      <v-icon size="32" color="grey">mdi-folder-multiple-outline</v-icon>
      <span class="preview-hint">{{ tm("spcodeProjectLoad.fileBrowser.preview.selectFromLeft") }}</span>
    </div>

    <!-- symlink 状态(顶层 symlink,即 path 本身是 symlink) -->
    <div v-else-if="state.kind === 'symlink'" class="preview-center">
      <v-icon size="32" color="info">mdi-link-variant</v-icon>
      <div class="preview-symlink-info">
        <div class="preview-symlink-target">{{ state.snapshot.meta.target }}</div>
        <div v-if="!state.snapshot.meta.targetExists" class="preview-symlink-dangling">
          {{ tm("spcodeProjectLoad.fileBrowser.entryType.dangling") }}
        </div>
      </div>
    </div>

    <!-- 文件 -->
    <div v-else-if="state.kind === 'file'" class="preview-content">
      <div class="preview-header">
        <div class="preview-title">
          <v-icon size="16">mdi-file-document-outline</v-icon>
          <span class="preview-name">{{ state.snapshot.meta.name }}</span>
          <span class="preview-size">{{ formatBytes(state.snapshot.meta.size) }}</span>
        </div>
        <v-btn
          v-if="state.snapshot.content"
          size="x-small"
          variant="text"
          @click="copyContent"
        >
          <v-icon size="14">mdi-content-copy</v-icon>
          {{ copyFeedback || tm("spcodeProjectLoad.fileBrowser.preview.copy") }}
        </v-btn>
      </div>
      <div class="preview-meta">
        <span>{{ state.snapshot.meta.path }}</span>
        <span>·</span>
        <span>{{ formatMtime(state.snapshot.meta.mtime) }}</span>
        <span v-if="state.snapshot.meta.encoding">· {{ state.snapshot.meta.encoding }}</span>
      </div>

      <!-- 特殊 reason 状态 -->
      <div v-if="state.snapshot.meta.reason === 'binary_file'" class="preview-binary">
        <v-icon size="32">mdi-file-cancel-outline</v-icon>
        <div>{{ tm("spcodeProjectLoad.fileBrowser.preview.binary") }}</div>
      </div>
      <div v-else-if="state.snapshot.meta.reason === 'file_too_large'" class="preview-binary">
        <v-icon size="32">mdi-database-alert</v-icon>
        <div>
          {{ tm("spcodeProjectLoad.fileBrowser.preview.tooLarge", {
            size: formatBytes(state.snapshot.meta.size),
          }) }}
        </div>
      </div>

      <!-- 文本内容(Shiki 高亮) -->
      <div v-else-if="state.snapshot.content" class="preview-code" v-html="highlightedHtml" />
    </div>

    <!-- idle 初始态 -->
    <div v-else class="preview-center">
      <v-icon size="32" color="grey">mdi-file-search-outline</v-icon>
      <span class="preview-hint">{{ tm("spcodeProjectLoad.fileBrowser.preview.selectFromLeft") }}</span>
    </div>
  </div>
</template>

<style scoped>
.file-browser-preview {
  flex: 1;
  min-width: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}
.preview-center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 32px 16px;
  min-height: 200px;
  color: rgba(var(--v-theme-on-surface), 0.6);
  text-align: center;
}
.preview-error-title { font-weight: 600; font-size: 14px; }
.preview-error-detail { font-size: 12.5px; }
.preview-hint { font-size: 13px; }
.preview-content {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
}
.preview-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px 4px;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  position: sticky;
  top: 0;
  background: rgb(var(--v-theme-surface));
  z-index: 1;
}
.preview-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-family: ui-monospace, monospace;
  font-size: 13px;
}
.preview-name { font-weight: 500; }
.preview-size {
  color: rgba(var(--v-theme-on-surface), 0.6);
  font-size: 11px;
  font-weight: normal;
}
.preview-meta {
  padding: 0 14px 8px;
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), 0.55);
  display: flex;
  gap: 6px;
  font-family: ui-monospace, monospace;
  word-break: break-all;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.05);
}
.preview-code {
  padding: 8px 0;
  font-size: 12.5px;
  overflow-x: auto;
}
/* Shiki 输出已有自己的样式;此处仅调 padding 防止过宽 */
.preview-code :deep(pre) {
  padding: 8px 14px;
  margin: 0;
  font-family: ui-monospace, monospace;
  font-size: 12.5px;
  line-height: 1.55;
  background: transparent !important;
}
.preview-binary {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 32px 16px;
  color: rgba(var(--v-theme-on-surface), 0.6);
  font-size: 13px;
}
.preview-symlink-info {
  font-family: ui-monospace, monospace;
  font-size: 13px;
  text-align: center;
}
.preview-symlink-target { color: rgb(var(--v-theme-info)); }
.preview-symlink-dangling {
  color: rgb(248, 81, 73);
  font-size: 12px;
  margin-top: 6px;
}
</style>
```

### 4.6 `FileBrowserBreadcrumb.vue`

```vue
<!-- Author: elecvoid243, 2026-06-20 -->
<script setup lang="ts">
import { computed } from "vue";
import { useModuleI18n } from "@/i18n/composables";

const props = defineProps<{
  currentPath: string;
  rootPath: string | null;
}>();
const emit = defineEmits<{ (e: "navigate", path: string): void }>();
const { tm } = useModuleI18n("features/chat");

// 拆分路径为可点击段;root 为特殊段(项目根,不可点击或点击回到根)
const segments = computed(() => {
  if (!props.currentPath || !props.rootPath) return [];
  const normalizedCurrent = props.currentPath.replace(/\\/g, "/");
  const normalizedRoot = props.rootPath.replace(/\\/g, "/").replace(/\/$/, "");

  // 计算 relative path
  let relative: string;
  if (normalizedCurrent === normalizedRoot) {
    relative = "";
  } else if (normalizedCurrent.startsWith(normalizedRoot + "/")) {
    relative = normalizedCurrent.slice(normalizedRoot.length + 1);
  } else {
    return [];  // 越界,空数组
  }

  // 拆分
  const parts = relative.split("/").filter(Boolean);
  const result: Array<{ name: string; path: string; isRoot: boolean }> = [
    { name: tm("spcodeProjectLoad.fileBrowser.breadcrumbRoot"), path: normalizedRoot, isRoot: true },
  ];
  let acc = normalizedRoot;
  for (const p of parts) {
    acc += "/" + p;
    result.push({ name: p, path: acc, isRoot: false });
  }
  return result;
});
</script>

<template>
  <nav class="file-browser-breadcrumb" v-if="segments.length > 0">
    <template v-for="(seg, i) in segments" :key="seg.path">
      <button
        type="button"
        class="breadcrumb-segment"
        :class="{ 'is-current': i === segments.length - 1 }"
        :title="seg.path"
        @click="emit('navigate', seg.path)"
      >
        {{ seg.name }}
      </button>
      <span v-if="i < segments.length - 1" class="breadcrumb-sep">/</span>
    </template>
  </nav>
</template>

<style scoped>
.file-browser-breadcrumb {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 2px;
  padding: 8px 14px;
  font-size: 12px;
  font-family: ui-monospace, monospace;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  background: rgba(var(--v-theme-on-surface), 0.025);
  flex-shrink: 0;
  min-height: 32px;
}
.breadcrumb-segment {
  background: transparent;
  border: 0;
  padding: 2px 4px;
  border-radius: 3px;
  cursor: pointer;
  color: rgba(var(--v-theme-on-surface), 0.7);
  font: inherit;
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.breadcrumb-segment:hover {
  background: rgba(var(--v-theme-on-surface), 0.08);
  color: rgb(var(--v-theme-on-surface));
}
.breadcrumb-segment.is-current {
  color: rgb(var(--v-theme-on-surface));
  font-weight: 500;
  cursor: default;
}
.breadcrumb-segment.is-current:hover { background: transparent; }
.breadcrumb-sep {
  color: rgba(var(--v-theme-on-surface), 0.4);
  user-select: none;
}
</style>
```

---

## 5. GitDiffSidebar.vue 修改

### 5.1 新增状态(顶部 setup 块)

```typescript
// ── View mode (Files vs Diff) ────────────────────────────────
type ViewMode = "files" | "diff";
const VIEW_MODE_STORAGE_KEY = "astrbot.spcode.gitDiffSidebar.viewMode";
const VALID_VIEW_MODES: ReadonlyArray<ViewMode> = ["files", "diff"];

function loadViewMode(): ViewMode {
  try {
    const raw = localStorage.getItem(VIEW_MODE_STORAGE_KEY);
    if (raw && (VALID_VIEW_MODES as ReadonlyArray<string>).includes(raw)) {
      return raw as ViewMode;
    }
  } catch { /* localStorage 不可用 */ }
  return "files";  // 默认 Files 视图(更通用)
}
function persistViewMode(mode: ViewMode): void {
  try { localStorage.setItem(VIEW_MODE_STORAGE_KEY, mode); } catch { /* 静默降级 */ }
}
const viewMode = ref<ViewMode>(loadViewMode());
function onViewModeChange(mode: ViewMode): void {
  if (mode === viewMode.value) return;
  viewMode.value = mode;
  persistViewMode(mode);
  // 模式切换的副作用:启动/停止 diff 轮询
  if (mode === "diff") {
    if (props.modelValue && isMounted) composable.startPolling(10_000);
  } else {
    composable.stopPolling();
  }
}

// ── File browser state ────────────────────────────────────────
const CURRENT_PATH_STORAGE_KEY = "astrbot.spcode.gitDiffSidebar.fileBrowserCurrentPath";
const persistedCurrentPath = ref<string | null>(null);
try { persistedCurrentPath.value = localStorage.getItem(CURRENT_PATH_STORAGE_KEY); } catch {}

let persistCurrentPathTimer: ReturnType<typeof setTimeout> | null = null;
function persistCurrentPath(path: string): void {
  // Debounce 300ms 避免快速导航时 thrashing
  if (persistCurrentPathTimer) clearTimeout(persistCurrentPathTimer);
  persistCurrentPathTimer = setTimeout(() => {
    try { localStorage.setItem(CURRENT_PATH_STORAGE_KEY, path); } catch {}
  }, 300);
}

const fileBrowserCurrentPath = ref<string>("");
const fileBrowserComposable = useSpcodeFileBrowser(
  computed(() => fileBrowserCurrentPath.value),
);

const mainWorktreePath = computed(
  () => worktreeList.value.find((w) => w.isMain)?.path ?? null,
);
const currentWorktreeRoot = computed(
  () => selectedWorktree.value ?? mainWorktreePath.value,
);

// 校验 currentPath 是否在当前根目录下
function validateCurrentPath(
  persisted: string | null,
  root: string | null,
): string {
  if (!root) return "";  // 项目未加载
  if (!persisted) return root;
  const normPersisted = persisted.replace(/\\/g, "/");
  const normRoot = root.replace(/\\/g, "/").replace(/\/$/, "");
  if (normPersisted === normRoot || normPersisted.startsWith(normRoot + "/")) {
    return persisted;
  }
  return root;  // 越界 → 重置
}

// 当 worktree 列表就绪后,校验持久化的 worktree 和 currentPath
watch(
  () => worktreesComposable.state.value,
  (s) => {
    if (s.kind !== "ok") return;
    const wtList = s.snapshot.worktrees;
    // 校验 selectedWorktree
    if (selectedWorktree.value && !wtList.some((w) => w.path === selectedWorktree.value)) {
      selectedWorktree.value = null;
    }
    // 校验 currentPath
    const root = selectedWorktree.value ?? wtList.find((w) => w.isMain)?.path ?? null;
    fileBrowserCurrentPath.value = validateCurrentPath(persistedCurrentPath.value, root);
  },
  { immediate: true },
);

// 当 selectedWorktree 变化时,重置 currentPath
watch(
  selectedWorktree,
  (newVal) => {
    if (viewMode.value !== "files") return;
    const root = newVal ?? mainWorktreePath.value;
    if (root) {
      fileBrowserCurrentPath.value = root;
      persistCurrentPath(root);
    }
  },
);

// 持久化 currentPath(在变化时 debounce 写入)
watch(
  fileBrowserCurrentPath,
  (newPath) => { if (newPath) persistCurrentPath(newPath); },
);
```

### 5.2 顶部 view-mode 切换器(新增)

```html
<div class="git-diff-sidebar-view-mode" role="tablist">
  <button
    type="button"
    role="tab"
    :aria-selected="viewMode === 'files'"
    :class="['view-mode-pill', { 'is-active': viewMode === 'files' }]"
    @click="onViewModeChange('files')"
  >
    <v-icon size="14">mdi-folder-outline</v-icon>
    <span>{{ tm("spcodeProjectLoad.fileBrowser.viewMode.files") }}</span>
  </button>
  <button
    type="button"
    role="tab"
    :aria-selected="viewMode === 'diff'"
    :class="['view-mode-pill', { 'is-active': viewMode === 'diff' }]"
    @click="onViewModeChange('diff')"
  >
    <v-icon size="14">mdi-source-pull</v-icon>
    <span>{{ tm("spcodeProjectLoad.fileBrowser.viewMode.diff") }}</span>
  </button>
</div>
```

### 5.3 worktree tabs 提升到 view-mode 之下(结构调整)

将现有 `git-diff-sidebar-tabs` 容器从"scope bar 之后"提升到"view-mode 之后"位置(让两种视图都能看到)。

### 5.4 主体渲染(根据 viewMode 条件分支)

```html
<div class="git-diff-sidebar-body">
  <FileBrowserView
    v-if="viewMode === 'files'"
    :current-path="fileBrowserCurrentPath"
    :is-dark="isDark"
    @navigate="(p) => (fileBrowserCurrentPath = p)"
  />
  <GitDiffBodyContent
    v-else
    :state="composable.state.value"
    :expanded="expandedSet"
    :is-dark="!!isDark"
    @toggle="toggleFile"
    @retry="onManualRefresh"
  />
</div>
```

### 5.5 onBeforeUnmount 调整

```typescript
onBeforeUnmount(() => {
  onMouseUp();
  composable.dispose();
  worktreesComposable.dispose();
  fileBrowserComposable.dispose();  // 新增
});
```

---

## 6. 状态机与持久化

### 6.1 状态机总览

```
┌─────────────────────────────────────────────────────┐
│ GitDiffSidebar                                       │
│                                                      │
│  viewMode ──────┬── 'files' ── FileBrowserView      │
│                 │                  ↑                  │
│                 │                  │ currentPath      │
│                 │                  │                  │
│                 └── 'diff' ──── GitDiffBodyContent    │
│                                    ↑                  │
│                                    │ snapshot         │
│                                                      │
│  selectedWorktree ─┬── 重置 Files 视图 currentPath    │
│                    └── 重置 Diff 视图 scope (现有)     │
│                                                      │
│  selectedScope ─── 仅 Diff 视图使用                    │
│                                                      │
│  fileBrowserCurrentPath ── 仅 Files 视图使用          │
└─────────────────────────────────────────────────────┘
```

### 6.2 持久化表

| 状态 | localStorage key | 类型 | 写入时机 | 加载时校验 |
|---|---|---|---|---|
| `viewMode` | `astrbot.spcode.gitDiffSidebar.viewMode` | `'files'` \| `'diff'` | 切换时立即 | 白名单 → 默认 `'files'` |
| `selectedWorktree` | `astrbot.spcode.gitDiffSidebar.selectedWorktree` | `string \| null` | 切换时立即 | 必须在当前 worktreeList → `null` |
| `selectedScope` | `astrbot.spcode.gitDiffSidebar.selectedScope` | `'unstaged'` \| `'staged'` \| `'all'` | 切换时立即 | 白名单 → 默认 `'unstaged'` |
| `fileBrowserCurrentPath` | `astrbot.spcode.gitDiffSidebar.fileBrowserCurrentPath` | `string` | 变化时 debounce 300ms | 必须在当前根下 → 根 |

### 6.3 跨项目行为

| 场景 | 持久化值 | 恢复后 |
|---|---|---|
| 同项目,同 worktree,关闭再开 sidebar | `currentPath=/repo/foo` | 恢复 `/repo/foo` ✅ |
| 切换到 worktree | `selectedWorktree=/wt/feat-x` | Files 视图根 = `/wt/feat-x`;currentPath 越界 → 重置为新根 |
| `/project load /other` 切换项目 | 所有持久化值 | viewMode/scope 保留;worktree/currentPath 大概率越界 → 重置 |

### 6.4 错误降级

| 场景 | 行为 |
|---|---|
| `localStorage` 不可用 | 全部 try/catch 静默,值用默认值,功能正常 |
| QuotaExceededError | 同上 |
| 持久化值被外部篡改(白名单失败) | 用默认值 |
| 持久化值被外部篡改(路径越界) | 校验失败用根路径 |

---

## 7. i18n 键(中/英/俄三语)

新增键挂在 `spcodeProjectLoad.fileBrowser.*` 下;zh-CN 完整,en-US/ru-RU 留 TODO 翻译占位(沿用姊妹 spec 做法)。

```jsonc
// zh-CN/features/chat.json
{
  "spcodeProjectLoad": {
    "fileBrowser": {
      "title": "工作区浏览",
      "viewMode": {
        "files": "工作区",
        "diff": "Git Diff"
      },
      "breadcrumbRoot": "项目根",
      "loading": "加载中…",
      "empty": "空目录",
      "placeholder": "请先加载项目",
      "truncated": "⚠ 列表已截断,仅显示前 1000 项",
      "entryType": {
        "directory": "文件夹",
        "file": "文件",
        "symlink": "符号链接",
        "dangling": "悬空链接"
      },
      "preview": {
        "selectFromLeft": "从左侧选择文件以预览",
        "binary": "二进制文件,无法预览",
        "tooLarge": "文件过大 ({size}),无法预览",
        "copy": "复制",
        "copySuccess": "已复制"
      },
      "error": {
        "loadFailedTitle": "无法加载",
        "pathNotFound": "路径不存在",
        "permissionDenied": "权限不足",
        "specialFile": "特殊文件类型,无法预览",
        "network": "网络连接失败",
        "unknown": "加载失败 ({reason})"
      }
    }
  }
}
```

en-US / ru-RU 由实施者按 zh-CN 镜像翻译;本 spec 不强求 commit 时三语同步。

---

## 8. 错误处理(reason 全集对齐)

按 file-browser spec §5.1 的 6 种 reason + 1 种真错误:

| reason | 前端处理 | i18n key |
|---|---|---|
| `path_not_found` | 错误中心 + 重试按钮 | `error.pathNotFound` |
| `permission_denied` | 错误中心 + 重试按钮 | `error.permissionDenied` |
| `special_file` | 错误中心 + 重试按钮 | `error.specialFile` |
| `file_too_large` | 右栏内显示"过大"占位 + size 提示 | `preview.tooLarge` |
| `binary_file` | 右栏内显示"二进制"占位 | `preview.binary` |
| `directory_listing_truncated` | 左栏顶部 warning | `truncated` |
| `null` | 正常 | — |
| 网络错误(axios) | 错误中心 + 重试按钮 | `error.network` |
| 未知错误 | 错误中心 + 重试按钮 | `error.unknown` 模板 |

---

## 9. 端到端验收清单(手动)

> 沿用姊妹 spec 决定不写 Vitest 单元测试(见 §1.3);用手动跑端到端清单验证。

### 9.1 基础功能
- [ ] 打开 sidebar,默认显示 **Files 视图**(双栏布局)
- [ ] 左栏显示项目根目录的子项(目录 → 文件 → symlink 排序正确)
- [ ] 隐藏文件(`.env`、`.git/`)不显示
- [ ] 点击目录 → 左栏切换到该子目录(面包屑更新)
- [ ] 点击文本文件 → 右栏显示 Shiki 高亮内容
- [ ] 点击二进制文件 → 右栏显示"二进制"占位
- [ ] 点击大文件(> 5MB)→ 右栏显示"过大"占位 + size
- [ ] 点击 symlink(指向文件)→ 右栏显示 symlink target + 文件预览
- [ ] 点击悬空 symlink → 点击无效(红标 opacity 0.5)

### 9.2 view-mode 切换
- [ ] 点击 "Git Diff" pill → 视图切换为 Diff,启动 10s 轮询
- [ ] 点击 "工作区" pill → 视图切换为 Files,停止轮询
- [ ] 关闭 sidebar → 重新打开 → 恢复上次 viewMode

### 9.3 worktree 集成
- [ ] 多个 worktree 时,two 视图都显示 worktree tabs
- [ ] Files 视图下点击 feat-x worktree tab → 根路径切换,currentPath 重置
- [ ] 单 worktree 时不显示 worktree tabs
- [ ] Diff 视图下的 worktree 行为保持不变(回归)

### 9.4 持久化
- [ ] 打开 Files 视图 → 浏览到 `/repo/src/components` → 关闭 sidebar
- [ ] 重新打开 sidebar → 自动恢复到 `/repo/src/components`
- [ ] 修改 localStorage 中 `viewMode` 为非法值(如 `xxx`)→ 重启后回退到默认 `files`
- [ ] 修改 localStorage 中 `currentPath` 为越界路径 → 加载时重置为根
- [ ] 切换到 worktree → 关闭 → 重开 → 自动恢复到新 worktree 根
- [ ] `/project load /other` 切换项目 → 自动重置越界的 worktree/currentPath

### 9.5 错误兜底
- [ ] 不存在的路径 → 错误中心 + 重试
- [ ] 权限拒绝的目录 → 错误中心 + 重试
- [ ] 网络断开 → 错误中心 + 重试
- [ ] 5MB 上限的二进制文件 → 显示"二进制/过大"占位,不崩溃

### 9.6 边界 case
- [ ] 项目未加载时打开 sidebar → Files 视图显示"请先加载项目"占位
- [ ] 切换 view-mode 不影响另一个视图的滚动位置(独立)
- [ ] 拖拽 resize 在两种视图下都正常
- [ ] 移动端(< 760px)sidebar 全屏覆盖,双栏变单栏或保持双栏(实施时决定)
- [ ] 大量目录项(> 1000)显示截断 warning

### 9.7 视觉与样式
- [ ] 浅色/深色主题下都正常(Shiki 双主题自适应)
- [ ] 文件预览区有合理的滚动行为(横向超长代码不撑破 sidebar)
- [ ] 复制按钮在复制成功后显示 1.5s 反馈

---

## 10. 实施 checklist

| # | 任务 | 文件 |
|---|------|------|
| 1 | 新增 `parseSpcodeFileBrowser.ts`(纯类型 + 解析器) | `dashboard/src/composables/parseSpcodeFileBrowser.ts` |
| 2 | 新增 `useSpcodeFileBrowser.ts`(composable) | `dashboard/src/composables/useSpcodeFileBrowser.ts` |
| 3 | 新增 `FileBrowserView.vue`(主组件 + 容器) | `dashboard/src/components/chat/message_list_comps/FileBrowserView.vue` |
| 4 | 新增 `FileBrowserEntryList.vue`(左栏) | 同上目录 |
| 5 | 新增 `FileBrowserBreadcrumb.vue`(面包屑) | 同上目录 |
| 6 | 新增 `FileBrowserFilePreview.vue`(右栏 + Shiki) | 同上目录 |
| 7 | 修改 `GitDiffSidebar.vue` — 加 view-mode tabs + 持久化 hooks + Files 视图条件渲染 | `dashboard/src/components/chat/GitDiffSidebar.vue` |
| 8 | 新增 i18n 键(zh-CN 完整) | `dashboard/src/i18n/locales/zh-CN/features/chat.json` |
| 9 | 新增 i18n 键(en-US / ru-RU 翻译) | `dashboard/src/i18n/locales/{en-US,ru-RU}/features/chat.json` |
| 10 | `pnpm typecheck` 全绿 | — |
| 11 | `pnpm lint`(或 `ruff` 等价)全绿 | — |
| 12 | 跑 §9 端到端验收清单,全过 | — |

> **不做的事**(YAGNI 显式列出,reviewer 看到这些视为破坏设计):
> - ❌ 不写 Vitest 单元测试(沿用姊妹 spec 决定)
> - ❌ 不实现多 tab 文件预览
> - ❌ 不实现文件搜索/过滤
> - ❌ 不实现文件下载
> - ❌ 不实现拖拽上传
> - ❌ 不修改 spcode 端点契约
> - ❌ 不递归目录
> - ❌ 不在 Files 视图中支持 worktree 创建/删除
> - ❌ 不做跨标签页 storage 事件同步
> - ❌ 不修改现有 `GitDiffSidebar` 的 Diff 视图核心逻辑(仅结构调整)

---

## 11. 与现有 spec 的关系

| spec | 关系 |
|---|---|
| `2026-06-17-chatui-git-diff-sidebar-design.md` | 本 spec 是其 v2 扩展;保留所有原行为,新增 Files 视图 |
| `2026-06-18-git-worktree-switcher-design.md` | 复用 `useSpcodeWorktrees`;worktree tabs 行为对 Files 视图扩展可见性 |
| `2026-06-20-git-diff-scope-switcher-design.md` | Diff 视图 scope 行为零修改;持久化 scope 是新增 |
| `2026-06-20-file-browser-endpoint-design.md`(在 spcode 插件仓库) | 本 spec 依赖其 `/spcode/file-browser` 端点契约 |

---

**Spec 结束**。下一步:
1. 用户 review 本 spec → 如有修改则改 spec 重新走审查
2. 调用 `writing-plans` 技能输出实现计划
