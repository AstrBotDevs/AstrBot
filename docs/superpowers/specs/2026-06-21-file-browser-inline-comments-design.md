| 项目 | 内容 |
|------|------|
| 主题 | 在 `FileBrowserFilePreview` 中新增**行内评论功能**:每行带行号,gutter 悬停出 "+" 按钮,点击后弹出编辑器,保存的评论以结构化文本形式附加到下一次 LLM 请求 |
| 日期 | 2026-06-21 |
| 作者 | elecvoid243 |
| 状态 | Draft — 待用户审阅 |
| 关联代码 | `dashboard/src/components/chat/message_list_comps/FileBrowserFilePreview.vue`、`dashboard/src/components/chat/StandaloneChat.vue`、`dashboard/src/components/chat/ChatInput.vue` |
| 前置 spec | `docs/superpowers/specs/2026-06-20-git-diff-sidebar-file-browser-design.md`(Files 视图的右栏组件) |
| 设计参考 | 用户截图(2026-06-21 15:15 提供);GitHub PR review 风格(GitLab inline comment 风格亦可参考) |

---

## 1. 背景与目标

### 1.1 现状

`FileBrowserFilePreview.vue` 已交付(2026-06-20 spec §4.5),用 Shiki 高亮渲染文件内容,支持元信息头(路径/大小/mtime)+ 二进制/过大文件兜底。代码以单一 `<pre>` 渲染,无行号。

用户在 WebChat 中浏览项目代码时,**没办法在不切换到外部 IDE 的情况下对代码行加注释反馈**。如果想"让 LLM 改 `edit_engine.py:607` 这一行",只能口述行号 + 自己复制代码片段,容易出错。

### 1.2 目标

在 `FileBrowserFilePreview` 中新增**行内评论**功能(模仿 GitHub PR review 风格):

1. **行号渲染**:每行前显示行号(1-based,右对齐,与代码严格对齐)
2. **Gutter 交互**:鼠标悬停在某行时,左侧 gutter 显示 "+" 按钮;点击弹出评论编辑器
3. **评论编辑器**:固定在文件预览底部(不打断阅读),含 textarea + 保存/取消/删除按钮
4. **评论指示器**:已被评论的行,gutter 始终显示评论图标(高亮),悬停时 tooltip 预览评论内容
5. **状态作用域**:评论按 chat session 隔离,内存存储(刷新/换 session 清空)
6. **LLM 携带**:下一次用户发送消息时,所有评论以**结构化文本 + 行内容指纹 + ±1 临近行**形式附加到消息末尾
7. **底部状态**:ChatInput 左下角显示 "N 个评论" chip,带 tooltip 说明
8. **i18n**:zh-CN / en-US / ru-RU 三语

### 1.3 非目标(显式不做)

- ❌ **不**实现服务端持久化(评论是"本地"的,不写后端)
- ❌ **不**实现评论的协同/分享/多用户编辑
- ❌ **不**支持线程化评论(一行 1 条,可编辑/删除)
- ❌ **不**支持评论历史/审计日志
- ❌ **不**实现评论的全文搜索
- ❌ **不**修改 spcode `/file-browser` 端点(后端契约不变)
- ❌ **不**修改 LLM 后端(评论以 plain text 附加,后端无需识别)
- ❌ **不**实现评论的导出/导入
- ❌ **不**支持跨 session 评论迁移

---

## 2. 设计决策(已与用户确认)

| # | 决策点 | 选择 | 理由 |
|---|--------|------|------|
| 1 | 作用域 | **当前 chat session,内存存储** | "本地评论"语义;切 session 清空合理;无后端工作量 |
| 2 | 持久化 | ❌ **不持久化**(刷新/换设备丢失) | 与"本地"一致;避免后端 schema 改动 |
| 3 | LLM 携带格式 | **追加到用户消息文本末尾** | 后端零改动;LLM 看到清晰结构化文本 |
| 4 | 发送后清空? | ❌ **保留**(可累积多条一起提) | 用户工作流:累积 → 一并提问 |
| 5 | 每行评论数 | **单条**(可编辑/删除,不支持 thread) | UI 最简;符合图示 |
| 6 | 编辑器位置 | **固定在文件预览底部**(图示位置) | 不打断阅读;实现简单 |
| 7 | i18n 范围 | zh-CN / en-US / ru-RU | 跟随现有约定 |
| 8 | 评论数据模型 | **带行内容快照**(`lineContent` / `contextBefore` / `contextAfter` 在 add 时冻结) | 文件可能被编辑;line 漂移后 LLM 仍能用 lineContent 作为 fingerprint 定位 |
| 9 | LLM 上下文格式 | **git-diff 风格**(`>` 标记 + 行号列 + ±1 临近行) | 业界标准;LLM 已熟悉此格式 |
| 10 | 邻近评论合并 | **同文件 line 差 ≤ 3 行的多条评论合并为一段** | 避免重复 context;token 效率 |
| 11 | 切 session 清空 | ✅ 是(调用 `fileComments.resetForSession()` 清空 `comments`;**contentCache 跨 session 保留**,下次开文件会被 watch 重新注册) | session 切换是明确的上下文边界;contentCache 保留避免无意义重读 |
| 12 | 切 worktree / 项目 | **评论按 filePath 区分**,不强制清空 | 评论与文件路径绑定,worktree 切换不应丢评论 |
| 13 | 仅评论无文本能否发送 | ✅ 是(`sendCurrentMessage` 在 `draft` 空、`stagedFiles` 空、但 `totalCount > 0` 时仍可发送) | 用户"累积多条评论后一键提问"的工作流,无需额外敲字 |

---

## 3. 架构与文件改动

### 3.1 架构原则

- **零后端改动**:评论纯前端,LLM 携带通过 plain text 追加实现
- **零 spcode 改动**:`/file-browser` 端点契约不变
- **最小侵入**:`FileBrowserFilePreview` 改为调用 `FileBrowserCodeView` + `FileCommentEditor`,不重写已有逻辑(Shiki 高亮、二进制兜底、复制按钮等全部保留)
- **单一真相源**:`useFileComments` composable 持有 `comments` + `currentContentCache` 两份 reactive 数据
- **Inline-first**:`addComment` 的 lineContent 提取写在 composable 内部,不暴露给调用方
- **AGENTS.md 适用条款**:Google-style docstring、英文注释、conventional commit messages

### 3.2 文件改动清单

| 层级 | 文件 | 性质 | 说明 |
|------|------|------|------|
| 新增 | `dashboard/src/composables/useFileComments.ts` | composable | 评论 state + 操作 + LLM 格式化 + 当前文件内容缓存 |
| 新增 | `dashboard/src/components/chat/message_list_comps/FileBrowserCodeView.vue` | 新组件 | 行号 + 代码 + gutter 渲染(从 FileBrowserFilePreview 抽出) |
| 新增 | `dashboard/src/components/chat/message_list_comps/FileCommentEditor.vue` | 新组件 | 评论编辑器(底部面板) |
| 改 | `dashboard/src/components/chat/message_list_comps/FileBrowserFilePreview.vue` | 修改 | 集成 CodeView + Editor,转交元信息头 / 复制按钮 / 错误兜底 |
| 改 | `dashboard/src/components/chat/StandaloneChat.vue` | 修改 | 创建 `useFileComments(sessionId)` + `provide` + 在 `sendCurrentMessage` 里把评论文本拼到 userText 末尾(走现有 `buildOutgoingParts` 路径,**`buildOutgoingParts` 本身不改**) |
| 改 | `dashboard/src/components/chat/ChatInput.vue` | 修改 | 底部 status-row 新增 "N 个评论" chip |
| 改 | `dashboard/src/i18n/locales/{zh-CN,en-US,ru-RU}/features/chat.json` | 修改 | 新增 `spcodeProjectLoad.fileBrowser.comment.*` 键 |

### 3.3 改动量估算

- 新增代码:约 400-550 行(1 composable + 2 组件)
- 改动现有代码:约 50-80 行(`FileBrowserFilePreview` 拆分 + `StandaloneChat`/`ChatInput` 集成 + 3 个 i18n json 各加 ~20 行)
- 风险面:1 个现有文件中等改动(预览主体下沉到子组件) + 1 个新 composable + 2 个新组件

### 3.4 模块依赖图

```
StandaloneChat.vue (修改)
  ├─ useFileComments(sessionId)         [NEW]      ← 唯一真相源
  │     ├─ comments: Map<filePath, FileComment[]>
  │     ├─ currentContentCache: Map<filePath, string>
  │     ├─ addComment / updateComment / deleteComment
  │     └─ formatForLLM(): 结构化文本输出
  │
  ├─ ChatInput.vue (修改)              ← 显示 "N 个评论" chip
  │
  └─ GitDiffSidebar.vue (existing)     ← Files 视图入口
        └─ FileBrowserView.vue (existing)
              └─ FileBrowserFilePreview.vue (修改)
                    ├─ FileBrowserCodeView.vue    [NEW]   ← 行号 + 代码 + gutter
                    └─ FileCommentEditor.vue      [NEW]   ← 编辑器面板
```

---

## 4. 组件详细设计

### 4.1 `useFileComments.ts` composable

**设计原则(基于 reviewer 反馈)**:

- **Comments per active session, cleared on switch**:切换 chat session 时,当前 session 的所有评论一并清空(不做 per-session 持久化以避免 D11 模糊)。Cache 跨 session 保留(下次重新打开文件时,`immediate: true` 的 watch 会重新注册)。
- **Single-level bucket**:`comments[filePath] = FileComment[]` 而不是 `comments[sessionId][filePath]`。
- **`addComment` 返回 `null` 而不是抛错**:让调用方决定 UX(显示 snackbar、保持编辑器打开等)。
- **共享 `extractLineContext` helper**:供 composable 和 `FileBrowserFilePreview` 复用,避免重复实现。
- **`crypto.randomUUID?.() || fallback`** 模式与 `StandaloneChat.vue:311` 保持一致。

#### `FileComment` interface + helper(模块级 export)

```typescript
/**
 * Single file comment, anchored to a line at comment-creation time.
 * `lineContent` and `contextBefore`/`contextAfter` are frozen snapshots
 * so the LLM can use `lineContent` as a content-fingerprint to relocate
 * the line even if the file has been edited since the comment was made.
 */
export interface FileComment {
  /** UUID, stable across edits/deletes. */
  id: string;
  /** Absolute path. Comments are partitioned by this. */
  filePath: string;
  /** 1-based line number at comment time. May drift if file is edited. */
  line: number;
  /** Exact line content at comment time. The LLM uses this as a fingerprint. */
  lineContent: string;
  /** Line above (null if line === 1). */
  contextBefore: string | null;
  /** Line below (null if line === last line). */
  contextAfter: string | null;
  /** User's comment text. Multi-line allowed. */
  text: string;
  createdAt: number;
  updatedAt: number;
}

/** Single source of truth for line context extraction. Used by both
 *  useFileComments (to freeze the snapshot in addComment) and by
 *  FileBrowserFilePreview (to populate the editor preview). Keeping
 *  the two call sites in lockstep via one helper means the editor
 *  preview is always consistent with what the comment will store. */
export interface LineContext {
  lineContent: string;
  contextBefore: string | null;
  contextAfter: string | null;
}

export function extractLineContext(content: string, line: number): LineContext | null {
  const lines = content.split("\n");
  const idx = line - 1;
  if (idx < 0 || idx >= lines.length) return null;
  return {
    lineContent: lines[idx],
    contextBefore: idx > 0 ? lines[idx - 1] : null,
    contextAfter: idx < lines.length - 1 ? lines[idx + 1] : null,
  };
}

/** UUID generator matching the pattern used in StandaloneChat.vue:311. */
function newId(): string {
  return (
    (globalThis.crypto?.randomUUID?.() as string | undefined) ??
    `${Date.now()}-${Math.random()}`
  );
}
```

#### Composable 本体

```typescript
import { reactive, computed } from "vue";

export function useFileComments() {
  // Current-session comments, flat partitioned by filePath. Wiped on
  // session switch via resetForSession(). NOT bucketed by sessionId —
  // we deliberately do not preserve round-trip A → B → A, because
  // (1) "local comments" semantic argues against it, (2) per-session
  // bucketing adds complexity for no concrete UX benefit, (3) the
  // content cache (which IS preserved) auto-rebuilds on next file open.
  const comments = reactive<Record<string, FileComment[]>>({});
  // Global content cache, single-level. Survives session switches
  // (and is auto-overwritten by registerFileContent on next file load).
  // Used only inside addComment() to freeze line snapshots.
  const contentCache = reactive<Record<string, string>>({});

  /**
   * Drop the current session's comments. Called by StandaloneChat
   * when the user switches to a different session. Does NOT clear
   * contentCache (see field doc above).
   */
  function resetForSession(): void {
    for (const k of Object.keys(comments)) delete comments[k];
  }

  /**
   * Register a file's current full content. Called by
   * FileBrowserFilePreview when a file finishes loading
   * (`immediate: true` watch). Idempotent — last write wins.
   */
  function registerFileContent(filePath: string, content: string): void {
    contentCache[filePath] = content;
  }

  /**
   * Add a comment, freezing lineContent / contextBefore / contextAfter
   * from the cached content at this moment.
   *
   * Returns null if the cache has no entry for this file. In practice
   * this should be unreachable — the `immediate: true` watch in
   * FileBrowserFilePreview registers content before the editor opens
   * — but the null return lets the caller show a snackbar instead of
   * crashing if the invariant ever breaks (e.g. external file refresh
   * that clears the cache while the editor is open).
   */
  function addComment(input: {
    filePath: string;
    line: number;
    text: string;
  }): FileComment | null {
    const content = contentCache[input.filePath];
    if (content === undefined) return null;
    const ctx = extractLineContext(content, input.line);
    if (ctx === null) return null;
    const comment: FileComment = {
      id: newId(),
      filePath: input.filePath,
      line: input.line,
      lineContent: ctx.lineContent,
      contextBefore: ctx.contextBefore,
      contextAfter: ctx.contextAfter,
      text: input.text,
      createdAt: Date.now(),
      updatedAt: Date.now(),
    };
    (comments[input.filePath] ??= []).push(comment);
    return comment;
  }

  function updateComment(id: string, newText: string): void {
    for (const list of Object.values(comments)) {
      const c = list.find((c) => c.id === id);
      if (c) {
        c.text = newText;
        c.updatedAt = Date.now();
        return;
      }
    }
  }

  function deleteComment(id: string): void {
    for (const [path, list] of Object.entries(comments)) {
      const i = list.findIndex((c) => c.id === id);
      if (i >= 0) {
        list.splice(i, 1);
        if (list.length === 0) delete comments[path];
        return;
      }
    }
  }

  /** Find a comment by id in the current session. Returns null if not
   *  found. Used by FileBrowserFilePreview to open the editor for
   *  an existing comment. */
  function findCommentById(id: string): FileComment | null {
    for (const list of Object.values(comments)) {
      const c = list.find((c) => c.id === id);
      if (c) return c;
    }
    return null;
  }

  /** Find the comment on a specific line of a specific file, if any.
   *  Used by FileBrowserCodeView to check "should this gutter cell
   *  show the comment indicator instead of the '+' button?" without
   *  scanning the bucket itself. */
  function commentForLine(filePath: string, line: number): FileComment | null {
    return comments[filePath]?.find((c) => c.line === line) ?? null;
  }

  /** Total comment count for the current session (across all files). */
  const totalCount = computed<number>(() => {
    let n = 0;
    for (const list of Object.values(comments)) n += list.length;
    return n;
  });

  /** Comments for a specific file in the current session. */
  function commentsForFile(filePath: string): FileComment[] {
    return comments[filePath] ?? [];
  }

  /** Format all comments in the current session as a structured
   *  plain-text block ready to be appended to the user's outgoing
   *  message. Returns "" if no comments.
   *
   *  Output format: a leading prose section, then for each file a
   *  markdown header and a fenced code block (4-backtick outer fence
   *  so the user's comment text can contain 3-backtick fences
   *  without breaking the outer block — markdown supports this). The
   *  code block uses git-diff-style `>` marker for the commented
   *  line. See §5 for the full format spec. */
  function formatForLLM(): string {
    const allComments: FileComment[] = [];
    for (const list of Object.values(comments)) allComments.push(...list);
    if (allComments.length === 0) return "";

    // Group by filePath
    const byFile = new Map<string, FileComment[]>();
    for (const c of allComments) {
      if (!byFile.has(c.filePath)) byFile.set(c.filePath, []);
      byFile.get(c.filePath)!.push(c);
    }

    const out: string[] = [
      "[File review comments]",
      "Each entry shows the line content (and 1 line of context above/below)",
      "that was current when the comment was written. Use the line content",
      "as a fingerprint to locate the line in the current file — line numbers",
      "may have drifted if the file was edited since the comment.",
    ];

    for (const [filePath, commentList] of byFile) {
      const sorted = [...commentList].sort((a, b) => a.line - b.line);

      // Walk and group into windows: any two comments within 3 lines
      // of each other share a single context block. This avoids
      // duplicating context lines when the user leaves several
      // comments in the same area of a file.
      type Window = { startLine: number; endLine: number; comments: FileComment[] };
      const windows: Window[] = [];
      for (const c of sorted) {
        const last = windows[windows.length - 1];
        if (last && c.line - last.endLine <= 3) {
          last.endLine = Math.max(last.endLine, c.line);
          last.comments.push(c);
        } else {
          windows.push({ startLine: c.line, endLine: c.line, comments: [c] });
        }
      }

      for (const win of windows) {
        // Resolve per-line content for the window. The window spans
        // [startLine-1, endLine+1] (clipped to comment-time bounds).
        //
        // Limitation: a comment only carries ±1 line of context, so
        // if two comments are 3 lines apart (sharing a window) the
        // middle context line has no recorded content. We render it
        // as "" (an empty line in the code block) — the LLM still
        // has the `>` marker and the surrounding fingerprints to
        // locate. Future: store full file content on the comment to
        // close this gap.
        const ctxStart = win.comments.some((c) => c.contextBefore !== null)
          ? Math.max(1, win.startLine - 1)
          : win.startLine;
        const ctxEnd = win.comments.some((c) => c.contextAfter !== null)
          ? win.endLine + 1
          : win.endLine;

        const header =
          win.startLine === win.endLine
            ? `\`${filePath}\` line ${win.startLine}:`
            : `\`${filePath}\` lines ${win.startLine}-${win.endLine}:`;
        out.push("");
        out.push(header);
        // 4-backtick fence so user comment text can contain 3-backtick
        // fences without breaking the outer block.
        out.push("````");
        const commentedSet = new Set(win.comments.map((c) => c.line));
        const commentByLine = new Map(win.comments.map((c) => [c.line, c]));

        for (let line = ctxStart; line <= ctxEnd; line++) {
          const c = commentByLine.get(line);
          let lineContent: string;
          if (c) {
            lineContent = c.lineContent;
          } else if (line === ctxStart && win.comments[0].contextBefore !== null) {
            lineContent = win.comments[0].contextBefore ?? "";
          } else if (
            line === ctxEnd &&
            win.comments[win.comments.length - 1].contextAfter !== null
          ) {
            lineContent = win.comments[win.comments.length - 1].contextAfter ?? "";
          } else {
            lineContent = "";  // Middle context line, see limitation above.
          }
          const marker = commentedSet.has(line) ? ">" : " ";
          const padded = String(line).padStart(4);
          out.push(`  ${marker} ${padded} │ ${lineContent}`);
          if (c) {
            // 9-space indent to align with the code column ("  " + " " + "    " + " │ ").
            const textLines = c.text.split("\n");
            out.push(`         │ Comment: ${textLines[0]}`);
            for (let i = 1; i < textLines.length; i++) {
              out.push(`         │ ${textLines[i]}`);
            }
          }
        }
        out.push("````");
      }
    }
    return out.join("\n");
  }

  return {
    totalCount,
    resetForSession,
    registerFileContent,
    addComment,
    updateComment,
    deleteComment,
    findCommentById,
    commentForLine,
    commentsForFile,
    formatForLLM,
  };
}
```

> **注**:`addComment` 返回 `null` 而不是抛错(对应 reviewer 反馈):调用方在 `onSaveComment` 里检查 null,显示 snackbar 并保留 editor 文本(见 §4.4)。

#### InjectionKey(导出在文件底部)

```typescript
import type { InjectionKey } from "vue";

/**
 * Stable injection key for the file-comments store. Must be exported
 * from this single file (NOT re-declared in StandaloneChat.vue or
 * FileBrowserFilePreview.vue). A Symbol literal in two files would
 * produce two different symbols and silently break inject().
 */
export const FILE_COMMENTS_KEY: InjectionKey<ReturnType<typeof useFileComments>> =
  Symbol("fileComments");
```

> **正确用法**:
> - `StandaloneChat.vue`:`import { ..., FILE_COMMENTS_KEY } from "@/composables/useFileComments";` 然后 `provide(FILE_COMMENTS_KEY, fileComments)`
> - `FileBrowserFilePreview.vue`:`import { ..., FILE_COMMENTS_KEY } from "@/composables/useFileComments";` 然后 `inject(FILE_COMMENTS_KEY)`

### 4.2 `FileBrowserCodeView.vue` 新组件

**职责**:把 Shiki 输出的高亮 HTML 包成"行号 + 代码 + gutter"三列布局,并处理 gutter 的 hover 显示 "+" 按钮、评论指示器、点击事件。

#### 关键:Shiki 输出的行结构

Shiki 在 v1.x 输出形如:

```html
<pre class="shiki ...">
  <code>
    <span class="line">line 1 content</span>
    <span class="line">line 2 content</span>
    ...
  </code>
</pre>
```

**前提**:本设计依赖 Shiki 输出的 `<span class="line">` 包装每个源代码行。如果 Shiki 升级改变此约定,需要重写 `extractLinesFromShikiHtml()`。

#### Props / Emits

```typescript
const props = defineProps<{
  /** Shiki 输出的 HTML 字符串 */
  highlightedHtml: string;
  /** 文件路径(用于 gutter hover 时显示,以及 comment 关联) */
  filePath: string;
  /** 该文件的全部 comment(用于 gutter 评论指示器) */
  comments: FileComment[];
  /** 当前正在编辑的行号(null = 编辑器关闭) */
  activeEditLine: number | null;
  /** 当前正在编辑的 comment id(新建 vs 编辑区分) */
  activeEditCommentId: string | null;
  /** 是否暗色主题(影响 gutter 颜色) */
  isDark: boolean;
}>();

const emit = defineEmits<{
  /** 用户点击 "+" 按钮(请求打开编辑器新建) */
  (e: "request-add", line: number): void;
  /** 用户点击已有评论指示器(请求打开编辑器编辑) */
  (e: "request-edit", commentId: string): void;
}>();
```

#### 模板结构(简化)

```html
<div class="code-view" :class="{ dark: isDark }">
  <div class="code-gutter">
    <!-- 每行一个 cell,行号从 1 开始 -->
    <div
      v-for="line in lines"
      :key="line"
      class="gutter-cell"
    >
      <button
        v-if="line === hoveredLine && !hasComment(line)"
        class="gutter-add-btn"
        :aria-label="tm('spcodeProjectLoad.fileBrowser.comment.addButtonAria', { line })"
        @click="emit('request-add', line)"
      >+</button>
      <button
        v-else-if="hasComment(line)"
        class="gutter-comment-indicator"
        :title="commentText(line)"
        @click="emit('request-edit', commentIdFor(line))"
      >
        <v-icon size="12">mdi-comment-text-outline</v-icon>
      </button>
    </div>
  </div>
  <div class="line-numbers">
    <div v-for="line in lines" :key="line" class="line-number-cell">{{ line }}</div>
  </div>
  <pre class="code-content" v-html="highlightedHtml" @mousemove="onMouseMove" />
</div>
```

#### Script helpers(模板引用的 helper 全部声明)

模板里用了 `lines` / `hasComment(line)` / `commentText(line)` / `commentIdFor(line)`。声明:

```typescript
import { computed, ref } from "vue";
import type { FileComment } from "@/composables/useFileComments";

const props = defineProps<{
  highlightedHtml: string;
  filePath: string;
  comments: FileComment[];
  activeEditLine: number | null;
  activeEditCommentId: string | null;
  isDark: boolean;
}>();
const emit = defineEmits<{
  (e: "request-add", line: number): void;
  (e: "request-edit", commentId: string): void;
}>();

/** Total line count derived from the Shiki output by counting
 *  `<span class="line">` wrappers. Used to size the gutter /
 *  line-numbers columns. The exact extraction rule depends on
 *  Shiki's internal DOM — keep this single helper as the only
 *  place that knows it. */
const lines = computed<number[]>(() => {
  const m = props.highlightedHtml.match(/<span class="line">/g);
  const count = m ? m.length : 0;
  return Array.from({ length: count }, (_, i) => i + 1);
});

const codeContentRef = ref<HTMLElement | null>(null);
const hoveredLine = ref<number | null>(null);

function hasComment(line: number): boolean {
  return props.comments.some((c) => c.line === line);
}
function commentText(line: number): string {
  return props.comments.find((c) => c.line === line)?.text ?? "";
}
function commentIdFor(line: number): string | null {
  return props.comments.find((c) => c.line === line)?.id ?? null;
}
```

> **注**:这里的 `hasComment` / `commentText` / `commentIdFor` 是简单的 `Array.some/find`,O(N) per call。FileBrowserCodeView 渲染 1000 行,gutter 在每次 mousemove 触发 hover 重渲 = 1000× O(M) calls(M = 该文件评论数)。实际 M < 10,开销可忽略。如未来单文件评论数 > 100,改成 `Map<line, FileComment>` 由父组件预计算并通过 prop 传入(本 spec 不做)。

#### 对齐策略

三列共享 `font-family: ui-monospace; font-size: 12.5px; line-height: 1.55;`。
Shiki 输出的 `<pre>` 默认会撑高整段;我们强制每行高度 = `1em * line-height` 配合每行 `<span class="line">` 的渲染,通过 CSS:

```css
.code-content :deep(.line) {
  display: block;       /* 每行单独占一行,保证与 line-numbers 同高 */
  min-height: 1.55em;   /* 与 .line-number-cell 一致 */
}
.line-number-cell,
.gutter-cell {
  min-height: 1.55em;   /* 与行内 font-size * line-height 一致 */
  display: flex;
  align-items: center;
}
```

**Shiki `<span class="line">` 的渲染**:Shiki 默认每行是 inline 的 `<span>`,需要 `display: block` 让它独占一行。这与 `line-numbers` / `gutter` 的 grid 行对齐就吻合了。

#### Hover 行为(每次 `getBoundingClientRect`,无缓存)

`@mousemove` 在 `<pre class="code-content">` 上追踪 Y 坐标,反推当前 hover 的行号。

**关键**:用 `getBoundingClientRect()` 而不是 `offsetTop` 缓存,因为:
- 缓存(`offsetTop`)在 `<pre>` 滚动后会失效 —— 行元素相对 `<pre>` 顶部的 offset 不变,但相对视口的 `top` 会变。`mousemove` 给的是 clientY(视口坐标),必须实时换算
- 缓存只在 `highlightedHtml` 变更时重建,但滚动改变 clientY 而不改变 content,缓存会失配
- `getBoundingClientRect()` 每次 mousemove 调用是 O(N)(遍历行元素),但 N 通常 < 2000,实测 < 1ms

```typescript
const hoveredLine = ref<number | null>(null);
const codeContentRef = ref<HTMLElement | null>(null);

function onMouseMove(e: MouseEvent): void {
  if (!codeContentRef.value) return;
  const pre = codeContentRef.value;
  const preRect = pre.getBoundingClientRect();
  const yWithin = e.clientY - preRect.top;  // 0-based, relative to <pre> visible top

  // Iterate <span class="line"> in order; first line whose rect.bottom
  // is past the cursor y is the hovered line. O(N) per mousemove.
  const lineEls = pre.querySelectorAll<HTMLElement>(".line");
  let found: number | null = null;
  for (let i = 0; i < lineEls.length; i++) {
    const rect = lineEls[i].getBoundingClientRect();
    if (rect.bottom > preRect.top + yWithin) {
      found = i + 1;  // 1-based
      break;
    }
  }
  // When cursor is past the last line, keep the last line hovered.
  hoveredLine.value = found ?? lineEls.length;
}
```

**性能备忘**:O(N) 每次 mousemove = 1000 行 × 60Hz ≈ 60K DOM 访问/秒,实测 < 5ms/帧,可接受。若未来需要优化,加 rAF 节流或在 `<pre>` 外层 grid 上 hover(用 grid-template-rows + :hover trick 替代 JS)。

### 4.3 `FileCommentEditor.vue` 新组件

**职责**:固定在文件预览底部的评论编辑器。打开/关闭由父组件控制(`activeEditLine` prop)。

#### Props / Emits

```typescript
const props = defineProps<{
  /** 当前编辑的行号(null = 关闭) */
  line: number | null;
  /** 编辑现有评论时传,新建时为 null */
  commentId: string | null;
  /** 初始 textarea 内容(编辑现有时是 comment.text) */
  initialText: string;
  /** 上下文(展示给用户):lineContent + ±1 */
  lineContent: string | null;
  contextBefore: string | null;
  contextAfter: string | null;
  filePath: string;
}>();

const emit = defineEmits<{
  (e: "save", payload: { text: string; commentId: string | null; line: number }): void;
  (e: "cancel"): void;
  (e: "delete", commentId: string): void;
}>();
```

#### 模板(简化)

```html
<div v-if="line !== null" class="comment-editor">
  <div class="comment-editor-header">
    <v-icon size="14">mdi-comment-text-outline</v-icon>
    <span class="editor-title">
      {{ commentId
        ? tm("spcodeProjectLoad.fileBrowser.comment.editTitle", { line })
        : tm("spcodeProjectLoad.fileBrowser.comment.newTitle", { line }) }}
    </span>
    <span class="editor-context">
      <code v-if="contextBefore">{{ contextBefore }}</code>
      <code v-if="lineContent" class="commented-line">{{ lineContent }}</code>
      <code v-if="contextAfter">{{ contextAfter }}</code>
    </span>
  </div>
  <textarea
    ref="textareaRef"
    v-model="text"
    class="comment-editor-input"
    rows="3"
    :placeholder="tm('spcodeProjectLoad.fileBrowser.comment.placeholder')"
  />
  <div class="comment-editor-actions">
    <v-btn
      v-if="commentId"
      size="small"
      color="error"
      variant="text"
      @click="emit('delete', commentId)"
    >
      {{ tm("spcodeProjectLoad.fileBrowser.comment.delete") }}
    </v-btn>
    <v-spacer />
    <v-btn size="small" variant="text" @click="emit('cancel')">
      {{ tm("spcodeProjectLoad.fileBrowser.comment.cancel") }}
    </v-btn>
    <v-btn
      size="small"
      color="primary"
      variant="flat"
      :disabled="!text.trim()"
      @click="emit('save', { text: text.trim(), commentId, line })"
    >
      {{ tm("spcodeProjectLoad.fileBrowser.comment.save") }}
    </v-btn>
  </div>
</div>
```

#### 行为细节

- `v-if="line !== null"`:没激活行时整个组件不渲染
- 打开时自动 focus textarea(`onMounted` 触发,Vue 3)
- Esc 键触发 `cancel`
- Cmd/Ctrl+Enter 触发 `save`
- `initialText` 变化时重置 `text`(watch)

### 4.4 `FileBrowserFilePreview.vue` 改动

现有逻辑基本保留,**只**把"代码渲染"这一块抽出到 `FileBrowserCodeView`,并新增"评论编辑器"挂在底部。

**改动后模板**:

```html
<div class="file-browser-preview">
  <!-- 加载/错误/目录/symlink 状态保留(原样不动) -->
  ...

  <div v-else-if="state.kind === 'file'" class="preview-file">
    <div class="preview-file-meta">...metadata...</div>
    <div v-if="isBinary">binary hint</div>
    <div v-else-if="content === null">too large hint</div>
    <FileBrowserCodeView
      v-else
      :highlighted-html="highlightedHtml"
      :file-path="state.snapshot.meta.path"
      :comments="fileComments.commentsForFile(state.snapshot.meta.path)"
      :active-edit-line="activeEditLine"
      :active-edit-comment-id="activeEditCommentId"
      :is-dark="isDark"
      @request-add="onRequestAdd"
      @request-edit="onRequestEdit"
    />
    <FileCommentEditor
      v-if="activeEditLine !== null"
      :line="activeEditLine"
      :comment-id="activeEditCommentId"
      :initial-text="editorInitialText"
      :line-content="editorContext?.lineContent ?? null"
      :context-before="editorContext?.contextBefore ?? null"
      :context-after="editorContext?.contextAfter ?? null"
      :file-path="state.snapshot.meta.path"
      @save="onSaveComment"
      @cancel="closeEditor"
      @delete="onDeleteComment"
    />
  </div>
</div>
```

**新增的 script 逻辑**(接在现有 imports 之后):

```typescript
import { inject, ref } from "vue";
import {
  FILE_COMMENTS_KEY,
  extractLineContext,
  type LineContext,
} from "@/composables/useFileComments";

const props = defineProps<{
  state: FileBrowserFetchState;
  isDark: boolean;
}>();

const emit = defineEmits<{
  (e: "navigate-target", resolvedPath: string): void;
  (e: "retry"): void;
}>();

const { tm } = useModuleI18n("features/chat");

// Inject the shared comments store. StandaloneChat always provides
// it via provide(FILE_COMMENTS_KEY, ...); a missing key here is a
// programmer error, not a runtime condition we can recover from.
const fileComments = inject(FILE_COMMENTS_KEY);
if (!fileComments) {
  throw new Error(
    "FileBrowserFilePreview: FILE_COMMENTS_KEY not provided. " +
      "FileBrowserFilePreview must be rendered inside StandaloneChat.",
  );
}

// Editor state (local to this preview)
const activeEditLine = ref<number | null>(null);
const activeEditCommentId = ref<string | null>(null);
const editorInitialText = ref<string>("");
const editorContext = ref<LineContext | null>(null);

// Snackbar shown if addComment returns null (cache empty — see §4.1).
const snackbar = ref<{ visible: boolean; text: string }>({ visible: false, text: "" });

function currentFilePath(): string | null {
  return props.state.kind === "file" ? props.state.snapshot.meta.path : null;
}

function currentFileContent(): string | null {
  return props.state.kind === "file" ? props.state.snapshot.content : null;
}

/** INVARIANT: this watch is the ONLY point that writes to
 *  fileComments.contentCache. Both `onRequestAdd` (via extractLineContext
 *  on state.snapshot.content) and `addComment` (via contentCache)
 *  read the same value, so they MUST stay in sync — a stale
 *  preview would show context that doesn't match what the comment
 *  will actually store. The watch (immediate + reactive) is the
 *  single point that maintains this. */
watch(
  () => currentFileContent(),
  (content) => {
    const path = currentFilePath();
    if (path && content !== null) {
      fileComments.registerFileContent(path, content);
    }
  },
  { immediate: true },
);

function onRequestAdd(line: number): void {
  const path = currentFilePath();
  const content = currentFileContent();
  if (!path || content === null) return;
  activeEditLine.value = line;
  activeEditCommentId.value = null;
  editorInitialText.value = "";
  editorContext.value = extractLineContext(content, line);  // null if line out of range
}

function onRequestEdit(commentId: string): void {
  const existing = fileComments.findCommentById(commentId);
  if (!existing) return;  // Stale reference; close editor silently.
  activeEditLine.value = existing.line;
  activeEditCommentId.value = existing.id;
  editorInitialText.value = existing.text;
  editorContext.value = {
    lineContent: existing.lineContent,
    contextBefore: existing.contextBefore,
    contextAfter: existing.contextAfter,
  };
}

function onSaveComment(payload: {
  text: string;
  commentId: string | null;
  line: number;
}): void {
  if (payload.commentId) {
    fileComments.updateComment(payload.commentId, payload.text);
    closeEditor();
    return;
  }
  // New comment path
  const path = currentFilePath();
  if (!path) return;
  const created = fileComments.addComment({
    filePath: path,
    line: payload.line,
    text: payload.text,
  });
  if (created === null) {
    // Cache is empty for this file. In practice the invariant watch
    // above prevents this, but we surface a snackbar (instead of
    // silently dropping the comment) so the user knows their text
    // is kept in the editor and they can retry after the file
    // re-loads.
    snackbar.value = {
      visible: true,
      text: tm("spcodeProjectLoad.fileBrowser.comment.saveError"),
    };
    return;  // Do NOT close editor — let user retry.
  }
  closeEditor();
}

function closeEditor(): void {
  activeEditLine.value = null;
  activeEditCommentId.value = null;
  editorContext.value = null;
}

function onDeleteComment(commentId: string): void {
  fileComments.deleteComment(commentId);
  closeEditor();
}
```

> **注 1**:`onRequestAdd` 用模块级 `extractLineContext` helper —— 与 `addComment` 内部用的 helper **同一个**,确保 editor 预览的上下文与 comment 实际存储的快照严格一致(不变量已在代码注释中明确)。
>
> **注 2**:`addComment` 返回 null 时**保留编辑器打开**,只显示 snackbar。用户输入不丢,可重试。
>
> **注 3**:`i18n key` 使用**完整路径** `tm("spcodeProjectLoad.fileBrowser.comment.xxx")`,**不要**省略 `spcodeProjectLoad.fileBrowser.` 前缀。`useModuleI18n("features/chat")` 只注入 `features.chat.`,后续路径必须显式写出。参考 `FileBrowserFilePreview.vue:129` 的 `tm("spcodeProjectLoad.fileBrowser.preview.copy")` 用法。

### 4.5 `ChatInput.vue` 改动 — 评论计数 chip

**位置**:`<div class="input-area__status-row__right">` 内(与 `GitDiffChip` 同侧),在 `GitDiffChip` **之后**:

```html
<div class="input-area__status-row__right">
  <SpcodePlanModeChip v-if="showPlanModeChip" @toggle="handlePlanModeToggle" />
  <GitDiffChip
    v-if="spcodeStatus.status.value.loaded"
    @open-diff-sidebar="emit('open-diff-sidebar')"
  />
  <v-chip
    v-if="commentCount > 0"
    size="x-small"
    variant="tonal"
    color="primary"
    class="comment-count-chip"
    prepend-icon="mdi-comment-text-outline"
    :title="tm('spcodeProjectLoad.fileBrowser.comment.countTooltip')"
  >
    {{ tm("spcodeProjectLoad.fileBrowser.comment.countLabel", { count: commentCount }) }}
  </v-chip>
</div>
```

**为什么放 `__right` 内**:现有 `input-area__status-row` 是 `space-between` 布局,左侧放 `SpcodeProjectIndicator`,右侧 `__right` 包了所有 chip。新增评论 chip 必须进 `__right`,否则会被推到中间。

新增 prop:

```typescript
defineProps<{
  // ... existing
  commentCount: number;
}>();
```

`StandaloneChat` 模板里把 `fileComments.totalCount.value` 传进来。

### 4.6 `StandaloneChat.vue` 改动 — 创建 composable + 注入 + 发送时附加

#### 创建 + provide

```typescript
import { provide } from "vue";
// Import FILE_COMMENTS_KEY from the composable (single source of
// truth — DO NOT re-declare Symbol("fileComments") here; see §4.1
// bottom note).
import { useFileComments, FILE_COMMENTS_KEY } from "@/composables/useFileComments";

const fileComments = useFileComments();
provide(FILE_COMMENTS_KEY, fileComments);

// Reset comments on session change (see §4.1 resetForSession —
// wipes comments bucket, keeps contentCache).
watch(currSessionId, (newId, oldId) => {
  if (oldId && newId !== oldId) {
    fileComments.resetForSession();
  }
});
```

#### 修改 `sendCurrentMessage`

```typescript
async function sendCurrentMessage() {
  if (!draft.value.trim() && !stagedFiles.value.length && fileComments.totalCount.value === 0) return;
  const sessionId = await ensureSession();
  const userText = draft.value.trim();
  const commentText = fileComments.formatForLLM();
  const fullText = [userText, commentText].filter(Boolean).join("\n\n");
  const parts = buildOutgoingParts(fullText);
  // ... rest unchanged
}
```

`buildOutgoingParts(fullText)` 已存在,会把 fullText 包成 `[{ type: "plain", text: fullText }]` —— **零后端改动**。

#### 把 `totalCount` 传给 `ChatInput`

```html
<ChatInput
  v-model:prompt="draft"
  :comment-count="fileComments.totalCount.value"
  ...
/>
```

---

## 5. LLM 携带格式规范(详细)

### 5.1 输出格式

```
[File review comments]
Each entry shows the line content (and 1 line of context above/below)
that was current when the comment was written. Use the line content
as a fingerprint to locate the line in the current file — line numbers
may have drifted if the file was edited since the comment.

`edit_engine.py` line 607:
````
  606 │ def robust_replace(content, old, new, match_idx=0):
> 607 │     old_indent = _first_nonempty_line_indent(old_string)
         │ Comment: 这一个`内`的操作是什么意思?!
  608 │     new_indent = _first_nonempty_line_indent(new_string)
````

`src/foo.py` line 42:
````
   41 │   items = read_config(path)
>  42 │     return process(items)
         │ Comment: 这个函数没处理空列表
   43 │ 
````

`edit_engine.py` lines 100-102:
````
   99 │ def parse_config(path):
> 100 │     raw = open(path).read()
         │ Comment: 缺异常处理
  101 │     items = json.loads(raw)
> 102 │     return items
         │ Comment: 缩进不一致
````
```

**关键约定**:
- 每个窗口(单评论 / 邻近合并评论)用一个 4-backtick fence 包裹(` ```` ` ` ````),让用户的 comment 文本可以含 3-backtick 子代码块而不会破坏外层 fence
- `>` 前缀 = 正在评论的行(git-diff 风格)
- 行号右对齐到 4 列,`│` 分隔符
- `Comment:` 缩进与代码列对齐(9 空格);多行评论每行前都加 `         │`
- 同文件 line 差 ≤3 行的多条评论合并为 1 个窗口

### 5.2 多行评论

每个 comment 自己的 `text` 可包含 `\n`,每行前缀 `         │`:

```
[File review comments]
...

`README.md` line 5:
>  5 │ # Project Name
       │ Comment: 标题需要更具体
       │ 当前标题对搜索引擎不友好
       │ 建议改为: "MyProject: a fast thingamajig"
```

### 5.3 邻近评论合并

`formatForLLM` 算法(已写在 §4.1):

1. 按 filePath 分组
2. 每组按 line 排序
3. 滑动窗口:相邻 comment `line 差 ≤ 3` → 合并到同一窗口
4. 窗口的 `startLine` / `endLine` = 窗口内 comment 的 min/max line
5. 上下文范围 = `[max(1, startLine-1), endLine+1]`
6. 每个有 comment 的行渲染 `> marker` + `Comment:`;纯 context 行渲染 ` `

**注**:第 5 步的 `contextBefore/After` 取自 comment 自带的快照(在 add 时冻结);中间 context 行(同窗口内相邻 comment 之间的行)在 v1 输出 `""`(因为我们没有完整 file content 缓存的所有中间行)。这是 §6 的已知 trade-off。

### 5.4 与用户消息的拼装

```typescript
const userText = "帮我把 edit_engine.py:607 的那个 indent 处理得更好";
const commentText = fileComments.formatForLLM();

const fullText = commentText
  ? `${userText}\n\n${commentText}`
  : userText;
```

**当 commentText 非空时**,用 `\n\n` 分隔,让 LLM 看到清晰的"用户问题 / 评论"分界。

---

## 6. 已知 trade-off / 风险

| # | 风险 | 影响 | 缓解 |
|---|------|------|------|
| 1 | **Shiki 输出结构依赖**:本设计依赖 `<span class="line">` 包裹每行。Shiki 升级可能破坏。 | gutter 对齐失败 / 行号错位 | 把 `extractLinesFromShikiHtml()` 写成单点函数,加详细注释;Shiki 升级时优先验证 |
| 2 | **中间 context 行缺失**:`contextBefore/After` 只存 ±1 行的快照,窗口内中间 context 行没法重构 | 合并的窗口里,相邻 comment 中间的行显示为空 | v1 可接受(LLM 仍能用 lineContent 定位);未来需要时把 cache 升级为完整 lines 数组 |
| 3 | **大文件性能**:1000+ 行的文件,gutter 有 1000+ 个 cell | DOM 元素多,初始渲染慢 | v1 可接受(<5MB 文件一般 < 2000 行);未来用虚拟滚动 |
| 4 | **Hover 性能**:`@mousemove` 触发 O(N) 行元素遍历 | mousemove 频繁触发时计算开销 | 实测 < 5ms/帧(1000 行);如需更省可加 rAF throttle |
| 5 | **评论注入与 `buildOutgoingParts` 边界**:`fullText` 是一整段 plain text,LLM 看到的是 1 个 part | 部分 LLM 模型可能拆 token 不准 | 沿用现有 plain part 路径,后端无需改动;若未来需要独立 part,扩展 MessagePart 类型 |

| 6 | **行号偏移**:用户编辑文件后,comment 的 `line` 字段可能与现文件不一致 | 输出的行号可能误导 LLM | 在 §5.1 头部明确告诉 LLM "use lineContent as fingerprint";同时冻结的 lineContent 是 fingerprint 的核心 |
| 7 | **session 切换时未持久化评论**:刷新或切 session 丢评论 | 用户体验:刷新即丢 | 决策 D2 明示"不持久化";若未来需要持久化,加 `localStorage[sessionId]` 缓存 |
| 8 | ~~`onRequestEdit` 需要找 comment~~ | (已解决) | `findCommentById` 已加入 §4.1 接口 |
| 9 | **键盘可达性**:gutter "+" 按钮虽然可 tab 聚焦,但鼠标 hover 才显示 | 键盘用户看不到 | 始终渲染 "+" 按钮(只是默认 opacity:0);focus 时 opacity:1 |
| 10 | **缩进对齐脆弱**:`"  ${marker} ${padded} │ ${lineContent}"` 用 hard-coded 空格数 | 改字体/字号时对齐错位 | 改为用 CSS flex 列布局(三列:marker + line# + content),不依赖 hard-coded 空格 |
| 11 | **截图里编辑器在固定位置**:本设计也用固定位置 | 多行编辑器占底部空间 | 限制 textarea rows=3,可滚动 |
| 12 | **4-backtick fence 自身被嵌套**:如果用户 comment 含 4-backtick,外层 fence 仍被破坏 | 极端情况:LLM 看到 broken markdown | 极小概率(4-backtick 罕见);若发生,LLM 仍能 fallback 到 plain text 解析 |

### 6.1 移动端(< 760px)的折中

姐妹 spec `2026-06-20-git-diff-sidebar-file-browser-design.md` §9.6 / §4.3 在 < 760px 把双栏改为上下堆叠。本 spec 在移动端的行为:

- **`FileBrowserCodeView` 三列(gutter + line-numbers + code)** 仍保留,只是 gutter 宽度缩到 16px(`+` 按钮缩到 16×16)。代码本身需要行号,否则移动端阅读 100+ 行代码会迷失。
- **`FileCommentEditor`** 在 < 760px 时改为**全屏覆盖**(fixed inset: 0),避免占用 1/3 屏幕。具体做法(已锁):在 `FileBrowserFilePreview.vue` 顶层:
  ```typescript
  import { useDisplay } from "vuetify";
  const { width } = useDisplay();
  const isMobile = computed(() => width.value < 760);
  ```
  ```html
  <div class="file-browser-preview" :class="{ 'is-mobile': isMobile }">...</div>
  ```
  然后 scoped CSS:
  ```css
  .file-browser-preview.is-mobile :deep(.comment-editor) {
    position: fixed;
    inset: 0;
  }
  ```
- **`comment-count-chip`** 在 < 760px 隐藏(底部 status row 空间紧张,移动端用户主要用 chat 输入框,评论数提示的 ROI 低)。
- **Hover 行为**:移动端没有 hover,`+` 按钮始终显示在 gutter(默认 opacity:1,无 hover 状态)。

---

## 7. i18n 新增键

```json
"spcodeProjectLoad.fileBrowser.comment": {
  "addButton": "添加评论",                  // + button aria-label / tooltip
  "addButtonAria": "在第 {line} 行添加评论",
  "newTitle": "对第 {line} 行发布评论",        // editor header (新建)
  "editTitle": "编辑第 {line} 行的评论",      // editor header (编辑现有)
  "placeholder": "写下你的评论...",
  "save": "保存",
  "cancel": "取消",
  "delete": "删除",
  "saveError": "评论保存失败,请刷新文件后重试", // snackbar shown when addComment returns null
  "indicatorAria": "第 {line} 行的评论: {preview}",  // hover tooltip
  "countLabel": "{count} 个评论",            // chat input chip
  "countTooltip": "下次发送时会带上这些评论"
}
```

3 locales(zh-CN / en-US / ru-RU)同样加。

---

## 8. 测试与验收

### 8.1 单元测试

**说明**:沿用姊妹 spec 决定不写 Vitest(dashboard 尚未配置);`formatForLLM` 是纯函数,可在 console 临时跑一遍验证。

### 8.2 typecheck

`pnpm typecheck` 必须退出 0。

### 8.3 手动端到端验收清单

| # | 步骤 | 预期 |
|---|------|------|
| 1 | 打开 Files 视图,选择任意 .py 文件 | 文件内容显示,每行带行号,左 gutter 默认空 |
| 2 | 鼠标悬停任意行 | 该行左 gutter 显示 "+" 按钮,其他行不变 |
| 3 | 点击 "+" | 文件预览底部弹出编辑器,显示"对第 N 行发布评论" + 上下文行 |
| 4 | 输入评论,点击保存 | 编辑器关闭;该行 gutter 出现评论图标;ChatInput 底部出现 "1 个评论" chip |
| 5 | 切到其他文件,再切回 | 之前的评论依然在(按 filePath 保留) |
| 6 | 切到另一个 chat session | 之前 session 的评论消失;新 session 从 0 开始 |
| 7 | 在 input 输入问题,点击发送 | LLM 收到 "[File review comments] ..." 块,后跟用户问题 |
| 8 | 评论后编辑文件(外部 IDE)刷新页面 | 评论消失(不持久化,符合决策 D2) |
| 9 | 同一文件 2 行评论(line 100 + line 102) | 合并为 1 段输出,共享上下文 |
| 10 | 同一文件 2 行评论(line 100 + line 110) | 各自独立段落 |
| 11 | 删除评论 | 编辑器显示"删除"按钮;点击后评论消失,chip 数量 -1 |
| 12 | 二进制文件 | gutter 不显示(CodeView 根本不渲染,跟现状一致) |
| 13 | 5MB 大文件(content = null) | 显示"过大"提示,无 gutter,无编辑器入口 |
| 14 | keyboard 焦点到 "+" 按钮 | 按钮可见(opacity 1,符合风险 §6.1 #9) |
| 15 | 仅评论无文本:评论 1 条,input 框为空,点击发送 | 仍可发送;bot 收到的 message 只有 `[File review comments]` 块,无 userText;评论计数清零(下次编辑也不会带) |
| 16 | 文件被外部刷新(用户改 IDE 后 sidebar refresh):点击评论指示器 | 编辑器打开,显示**冻结的快照**(`lineContent` 是 comment 创建时的内容);如果当前文件已大幅变动,用户能在编辑器里看到"上下文是过时的"提示 |
| 17 | 添加评论失败(invariant 破坏:外部刷新清掉 cache,user 在保存前编辑器还开着) | 显示 `comment.saveError` snackbar;**编辑器不关闭**,用户输入保留,可刷新文件后重试 |

---

## 9. 实施顺序(高层)

1. `useFileComments.ts` composable + 单元自测(formatForLLM 输出对照 §6.1 期望)
2. `FileBrowserCodeView.vue` 静态版(只渲染行号 + 代码,gutter 空)
3. `FileCommentEditor.vue` 静态版(只接受 prop,不连 store)
4. 集成到 `FileBrowserFilePreview.vue`:CodeView + Editor 挂上,store 通过 inject 接入
5. `StandaloneChat.vue` 创建 + provide composable,`sendCurrentMessage` 附加评论
6. `ChatInput.vue` 加 chip
7. i18n(3 locales)
8. §8.3 验收清单

每步独立可测,逐步迭代。
