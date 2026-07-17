# 文档管理页面搜索功能 设计文档

- 作者: elecvoid243
- 日期: 2026-07-17
- 状态: 已批准（用户在对话中确认 Q1A / Q2A / Q3A 全部按推荐）

## 1. 背景与目标

工作区页面（Files 视图，`GitDiffSidebar` + `FileBrowserView` + `SearchPanel`）已有成熟的文件搜索：
工具栏放大镜切换 → 顶部输入框（300ms 防抖）→ 结果面板替换文件区 → 点击结果打开文件并跳转到命中行。

文档管理页面（`viewMode === "docs"`，`DocumentManager.vue`）没有搜索能力。目标：**以最小改动复用现有
SearchPanel 组件与搜索 composable，为文档管理页面提供与工作区一致的搜索体验**，搜索范围限定在
docs 根目录内。

关键前置事实（勘察结论）：

- 后端 `spcode/file-search` 与 `spcode/file-name-search` 均已支持 `path_filter` 请求字段
  （含 4 步安全校验 + Python 端前缀二次确认），**后端零改动**。
- 前端 `useSpcodeFileSearch` 的 `SearchOptions.pathFilter` 已存在，但防抖重发（`_query` watcher）
  只携带 `_lastUmo/_lastWorktree`，会丢失 pathFilter —— 需要补一行缓存。
- `DocumentManager` 的 raw 视图复用 `FileBrowserCodeView`，其 `scrollToLine` prop 的 watcher
  监听 `[scrollToLine, filePath, highlightedHtml]`，内容加载完成后也会补滚 —— 天然支持跳行。
- "docs" 是 `GitDiffSidebar` 的顶层 viewMode（非 files 子标签），工作区搜索工具栏
  `v-if="viewMode === 'files'"` 在 docs 模式下不渲染，**无双搜索栏冲突**；其全局
  Cmd/Ctrl+F 处理器也显式跳过非 files 视图，不会误触发。

## 2. 已确认的决策

| # | 决策点 | 结论 |
|---|--------|------|
| Q1 | 搜索范围 | 仅 docs 根目录（`path_filter = docsRoot`）。符合文档管理语义；结果必然可在管理器内打开 |
| Q2 | 内容命中展示 | 打开文档并自动切到 **raw 视图** 跳转命中行（渲染视图是 Markdown HTML，无行号概念）；文件名模式无行号，直接打开 |
| Q3 | 面板形态 | 完全镜像工作区：搜索面板替换整个内容区（breadcrumb 保留），点击结果 → 关闭面板 + 展示文档 |

补充细节决策：

- `searchOpen` **不持久化**（每次进入 docs 视图默认关闭），与 `isFullscreen` 的处理一致；
  区别于 GitDiffSidebar 的 localStorage 持久化 —— 避免用户再次进入时面对搜索面板而非文档树。
- i18n **复用现有键** `spcodeProjectLoad.diffSidebar.search.button` / `.placeholder`，不新增词条。
- Cmd/Ctrl+F 快捷键与 Esc 关闭在 DocumentManager 内自行注册 window 监听（组件仅在 docs 视图挂载，
  卸载即清理，不与 GitDiffSidebar 的处理器冲突）。

## 3. 变更清单

### 3.1 `dashboard/src/composables/useSpcodeFileSearch.ts`（~4 行）

- 新增模块级 `let _lastPathFilter: string | undefined;`
- `_search()` 在捕获 `_lastUmo/_lastWorktree` 的同一位置捕获 `_lastPathFilter = opts.pathFilter;`
  （位于空 pattern 提前返回之前，保证 priming 调用也能更新它）
- `_query` 防抖 watcher 重发时携带 `pathFilter: _lastPathFilter`

### 3.2 `dashboard/src/components/chat/message_list_comps/SearchPanel.vue`（~3 行）

- props 新增可选 `pathFilter?: string | null`（默认 undefined，工作区现有用法不受影响）
- setup 中的 priming 调用 `search({ umo, worktree, pattern: "" })` 追加 `pathFilter: props.pathFilter ?? undefined`

### 3.3 `dashboard/src/components/chat/message_list_comps/DocumentManager.vue`（主体）

**script：**

- 导入 `SearchPanel`、`useSpcodeFileSearch`
- 新增状态：
  - `searchOpen = ref(false)`（不持久化）
  - `searchScrollToLine = ref<number | null>(null)`
  - `searchInputRef = ref<HTMLInputElement | null>(null)`
  - 从 composable 解构共享 `query` / `search`
- `primeDocsSearch()`：`search({ umo: props.umo, worktree: props.worktree, pattern: "", pathFilter: docsRoot.value })`
  （镜像 GitDiffSidebar 的 `primeFileSearch`；空 pattern 调用只更新上下文缓存，不发网络请求）
- `watch(searchOpen)`：打开 → re-prime + nextTick 聚焦输入框；关闭 → 清空共享 query（状态回 idle）
- `watch(docsRoot)`：面板打开期间 docsRoot 变化 → re-prime，使后续输入按新范围搜索
- `onSearchInput(e)`：写共享 query（composable 负责防抖）
- `onSearchClose(e)`：`stopPropagation` + 关闭面板
- `onSearchOpenFile({ path, line })`：
  1. `path` 为 repo 相对 POSIX 路径 → 剥离 `docsRoot + "/"` 前缀得到 docsRoot 相对的 `selectedDoc`
     （docsRoot 为项目根 `"."` 时直接使用；不在前缀内的结果防御性忽略）
  2. `selectedRevision = null`（搜索命中的工作区内容不属于任何历史版本）
  3. `selectedDoc = doc`；`searchOpen = false`
  4. `line > 0`：`viewMode = "raw"`，`searchScrollToLine` 先置 null、nextTick 后赋 line
     —— 两步赋值保证 FileBrowserCodeView 的 watcher 必见变化（同行连点 / 组件随视图切换重新挂载
     而 html 已就绪时，无 immediate 的 watch 不会因挂载本身触发）
  5. `line === 0`（文件名模式）：`searchScrollToLine = null`，停留在当前视图模式
- window keydown 监听（onMounted 注册 / onBeforeUnmount 移除）：
  Cmd/Ctrl+F → 切换面板并聚焦；Escape → 焦点不在输入框/面板内时关闭
- raw 视图的 `FileBrowserCodeView` 追加 `:scroll-to-line="searchScrollToLine"`

**template：**

- 在 `<template v-else>`（项目已加载分支）内、`FileBrowserBreadcrumb` 上方新增工具栏行
  `.document-manager__search-toolbar`：放大镜 toggle 按钮（复用 i18n 键）+
  `v-if="searchOpen"` 的文本输入框（`:value + @input`，`@keydown.escape.stop`）
  —— 镜像 `git-diff-sidebar-files-toolbar` 结构，面板展开/收起时工具栏保持可见
- `<SearchPanel v-if="searchOpen" v-model="searchOpen" :worktree="worktree" :umo="umo"
  :path-filter="docsRoot" @open-file="onSearchOpenFile" />`，
  原 `.document-manager__body` 容器改为 `v-else`（面板替换内容区，breadcrumb 保留）

**style：**

- `.document-manager__search-toolbar` / `__search-toggle`（含 `.is-active`）/ `__search-input`，
  视觉规格对齐 `git-diff-sidebar-files-toolbar` 系列样式

## 4. 数据流

```
用户输入 → 共享 query ref（composable 单例）
        → 300ms 防抖 → _search({ umo, worktree, pattern, pathFilter: docsRoot })
        → POST spcode/file-search | spcode/file-name-search（后端 path_filter 限定 docs 目录）
        → SearchPanel 渲染结果（路径均为 repo 相对、位于 docsRoot 内）
点击结果 → SearchPanel emit open-file { path, line }
        → DocumentManager.onSearchOpenFile：剥离 docsRoot 前缀 → selectedDoc
        → line>0 时 viewMode=raw + scrollToLine 两步赋值
        → searchOpen=false → 内容区恢复，raw 视图 CodeView 居中命中行
```

## 5. 错误处理与边界

- 后端 reason 错误（超时 / ripgrep 不可用 / pattern 非法等）：沿用 SearchPanel 现有
  `errorReasonLabel` 渲染，无新增分支。
- 结果路径不在 docsRoot 前缀内（理论上不会发生，后端已限定）：防御性忽略。
- 面板打开期间切换 docsRoot：re-prime，已有结果保留直到下一次输入（与工作区切换 worktree 行为一致）。
- 单例 query 在工作区搜索与文档搜索间共享：任一面板打开时都会 re-prime 自身上下文
  （umo/worktree/pathFilter），后打开者覆盖前者 —— 同一时刻只有一个面板可见，语义正确。

## 6. 测试与验证

- `cd dashboard && pnpm typecheck`（vue-tsc）通过。
- 人工走查清单：
  1. docs 视图打开放大镜 → 输入文件名片段 → 命中文档 → 点击 → 文档在当前视图打开、面板关闭
  2. 切内容模式 → 输入正文关键词 → 点击命中 → 自动切 raw 视图并居中高亮行
  3. 同一行连点两次 → 均能居中（两步赋值生效）
  4. Esc / 再次点击放大镜 / Cmd+Ctrl+F → 面板关闭
  5. 面板打开时修改 docsRoot → 再次输入按新范围搜索
  6. 工作区 files 视图搜索回归：无 pathFilter，行为不变

## 7. 不做的事（YAGNI）

- 不新增后端端点 / 不改动后端（path_filter 已够用）
- 不持久化 searchOpen / query / 结果
- 不为文档搜索新增独立 i18n 词条（复用 diffSidebar.search.*）
- 渲染视图（MarkdownView）不做行定位（HTML 无行号语义）
- 不在文档管理器内提供 regex / 大小写开关（工作区搜索也未暴露，composable 默认 literal + 忽略大小写）
