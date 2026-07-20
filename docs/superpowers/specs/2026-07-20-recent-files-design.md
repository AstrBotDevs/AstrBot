# Design: 工作区 Recent Files — 最近打开文件列表

> Author: elecvoid243 · 2026-07-20
> Status: approved (brainstorming session 2026-07-20, 选项 a：Files view 顶部嵌入 + 默认折叠)
> Scope: dashboard only（纯前端，无后端/插件改动）

## 1. 目标

在工作区文件浏览器（Files view）里提供「最近打开文件」的可视化列表，
让用户能快速回到上次没看完的代码文件，无需重新导航目录。

非目标（YAGNI，**明确放弃**避免范围蔓延）：
- **不做 Pinned Files（pin/star 功能）**
- **不做 Quick Open 集成**（属 A1；本次只暴露 composable 给将来 A1 复用）
- **不做「文件不存在自动 prune」**——现有 FileBrowserView 路径已能报错，先让用户撞错再说
- **不做服务端同步 / 多端共享**（4.x 路线）
- **不持久化折叠状态**——每次进入 sidebar 默认折叠（与 sidebar 内已有 fullscreen 不持久化策略一致）
- **不暴露容量上限配置**（写死 50 条；不在 UI 暴露「Clear All」之外的高级项）

## 2. 方案（已选）

新增一个 composable（数据层）+ 一个组件（UI 层），在 `FileBrowserView`
左栏 FileTreeList **顶部**嵌入一个**默认折叠**的 Recent Files 块。

被否方案：
- **B（viewMode 加第 5 个 tab "Recent"）**—— 占用顶部 tab 资源，
  与现有 files/diff/history/docs 抢位置；浏览文件阶段用户不会主动切到它。
- **C（只做 store/composable，UI 完全留给 A1 Quick Open）**—— A1
  还没排期，价值兑现被无限推迟；当前 sidebar 完全有能力容纳一个轻量折叠块。

## 3. 组件与职责

| 单元 | 路径 | 职责 |
|---|---|---|
| `useRecentFiles` composable | `dashboard/src/composables/useRecentFiles.ts`（新） | 纯数据：读 / 删 / 清、按 worktree 分桶、50 条上限、同 path 去重；不感知 sidebar |
| `<RecentFilesBlock>` 组件 | `dashboard/src/components/chat/message_list_comps/RecentFilesBlock.vue`（新） | 纯 UI：折叠块、列表、× 按钮、Clear 链接、empty 占位 |
| `GitDiffSidebar.vue`（增） | 同文件 | 一个 `watch` 做 recordOpen；把 `<RecentFilesBlock>` 透传给 `FileBrowserView` |
| `FileBrowserView.vue`（增） | 同文件 | 在左栏 FileTreeList 上方嵌入 `<RecentFilesBlock>`；接收 currentRoot + recents props |

边界（KISS）：
- composable 接收 `worktree: Ref<string | null>`，输出 `{ entries, recordOpen, remove, clear }`——只依赖传进来的 ref，不耦合 sidebar
- RecentFilesBlock 接收 `{ entries, currentRoot }` props + `select`/`remove`/`clear` 事件——不耦合 composable 实现
- 两个单元可独立阅读与单元测试

## 4. 数据模型

```ts
type RecentEntry = { path: string; openedAt: number /* unix ms */ };

interface RecentBucket { entries: RecentEntry[]; }
```

### 4.1 存储

- `localStorage["spcode.recentFiles.<bucketKey>"] = JSON.stringify(RecentBucket)`
- `<bucketKey>` = FNV-1a 32 位 hash 的 8 字符 hex（inline 函数，~10 行，纯同步）
  - 选 FNV-1a 而非 SHA-1：浏览器原生 SubtleCrypto 只支持 SHA-256+ 且是异步，会破坏同步桶键计算；引入 sha1 npm 包违反「无新增依赖」
  - 不把 worktreeRoot 明文当 key：localStorage 在用户本机本就明文，这里仅做「key 不超 64 字符」的实用主义；安全敏感字段用 hash 而非明文以避免 path 字符触发 localStorage 配额统计困惑
- `currentRoot` 为 `null`（无 worktree）→ composable 全部读写都是 no-op；RecentFilesBlock 用 `v-if` 不渲染
- 复用 sidebar 现有的 `safeGetItem` / `safeSetItem`；JSON.parse 包 try/catch

### 4.2 容量与排序

- 每桶 **50 条上限**（克制，对比 VSCode 默认 1000）
- LIFO：按 `openedAt` 倒序排列；列表头 = 最新
- 溢出按 `openedAt` 升序丢弃旧条目

### 4.3 写入规则（`recordOpen(path)`）

```
recordOpen(path):
  if worktree == null:                       return  // no worktree
  if !path.startsWith(worktree + sep):       return  // path 越界（防污染）
  bucket = loadBucket(worktree)
  bucket.entries = bucket.entries.filter(e => e.path !== path)  // 去重
  bucket.entries.unshift({ path, openedAt: Date.now() })         // LIFO
  bucket.entries = bucket.entries.slice(0, MAX_ENTRIES)         // trim
  saveBucket(worktree, bucket)
```

### 4.4 删除 / 清空

- `remove(path)`: filter 该 path → 持久化（频度低，无 debounce）
- `clear()`: 将当前桶 `entries = []` → 持久化
- `clear` 在 UI 层需二次确认（不强制，但 spec 要求有 confirm dialog）

### 4.5 跨 worktree 隔离

- composable 内部 `watch(worktree)` 切桶；读写自动落到当前桶
- 切换到新工作区 → 老桶数据保留在 localStorage；新桶无历史则显示空
- 同样**不主动 prune 老桶**——用户可能在多个工作区之前反复跳，每个都该有自己的 Recent

## 5. UI（`<RecentFilesBlock>`）

### 5.1 默认态：折叠

```
┌────────────────────────────────────┐
│ ⏱  Recent Files (3)             ▸ │
└────────────────────────────────────┘
```

- 标题含条目数；chevron 指示折叠方向
- 点击整行（标题栏）→ 展开

### 5.2 展开态

```
┌───────────────────────────────────────────┐
│ ⏱  Recent Files (8)             Clear  ▾  │
│ ───────────────────────────────────────── │
│  📄  README.md                       ×   │
│      docs/                                  │
│  📄  main.py                           ×   │
│      src/                                   │
│  📄  schema.sql                         ×   │
│      migrations/                            │
│  📄  routes.ts                          ×   │
│      src/api/                               │
│  📄  app.pyx                            ×   │
│      src/                                   │
│  + 3 more →                                 │
└───────────────────────────────────────────┘
```

- 顶部标题栏：
  - 左：`⏱ Recent Files (count)`
  - 右：`Clear` 文本链接（点击 → 二次确认 dialog）
  - 点击空白处 → 折叠
- 默认**最多显示前 5 条**；超出显示 `+{N} more →`
- `+N more` 行为：未来接 A1 Quick Open（按住 Ctrl+P）；本次点击弹 toast：
  `按住 Ctrl+P 快速跳转所有文件`
- 每行结构：
  - mdi-clock-outline icon（与目录树 file-icon 同套）
  - **basename**（主色，14px），父目录路径（淡色 12px，整体不可换行省略）
  - hover 整行背景轻高亮 + 右端出现 × icon 按钮
- 每行点击 → `select` 事件 → FileBrowserView 复用既有 `navigateToFile(path)` 路径
- × 按钮点击 → `remove` 事件（不冒泡到行点击；用 `event.stopPropagation`）
- 空列表（在 worktree 已绑但无历史）：显示居中淡灰文字「无最近文件」

### 5.3 折叠状态不持久化

每次 sidebar 实例 mount → RecentFilesBlock 默认折叠，不读写 localStorage。
（保持 session 轻启动；用户主动 toggle 是临时偏好，不跨会话保留。）

### 5.4 与现有 UI 的一致性

- 折叠块风格沿用 sidebar 内既有 `.section-header` 视觉（FileTreeList / DocumentTreePanel 顶栏）
- icon 用 `mdi-clock-outline` 与 `mdi-file-outline`，全部已在 `@mdi/font` subset 内（构建时已处理 subset）
- Clear 链接、`+N more`、× 按钮沿用 Vuetify `variant="text"` + `density="compact"`

## 6. 接线点

### 6.1 `GitDiffSidebar.vue` 新增

```ts
import { useRecentFiles } from "@/composables/useRecentFiles";

const recentFiles = useRecentFiles(currentRoot);

// 打开文件 → 记录（含切换 worktree 时被清空的 path）
watch(
  [fileBrowserPreviewPath, currentRoot],
  ([newPath, root]) => {
    if (!newPath || !root) return;
    const sep = root.includes("\\") ? "\\" : "/";
    if (!newPath.startsWith(root + sep) && newPath !== root) return;
    recentFiles.recordOpen(newPath);
  },
);
```

并把 `<RecentFilesBlock>` 经由新增 props 透传到 `FileBrowserView`：
- `:recent-entries="recentFiles.entries.value"`
- `clear-recent-open` dialog state + handler

### 6.2 `FileBrowserView.vue` 新增

```vue
<template>
  <div class="file-browser-left">
    <RecentFilesBlock
      v-if="currentRoot"
      :entries="recentEntries"
      :current-root="currentRoot"
      @select="onRecentSelect"
      @remove="onRecentRemove"
      @clear="confirmClearRecentOpen = true"
    />
    <!-- 既有的 <FileTreeList> 保持不变，紧接其后 -->
  </div>
</template>
```

`onRecentSelect(path)`：走既有 `navigateToFile(path)` / 等价于 `setSearchTarget(path)`：
将 `fileBrowserPreviewPath = path` + `fileBrowserCurrentPath = dirOf(path)`，
触发 FileBrowser 既有 fetch 流程。
`onRecentRemove(path)`：调 composable `remove(path)`（props 已传 ref，自取）。

### 6.3 二次确认（Clear）

复用 sidebar 既有 `v-dialog` 模式（与现有 delete-file / restore-confirm 同形）：

```vue
<v-dialog v-model="confirmClearRecentOpen" max-width="420">
  <v-card>
    <v-card-title class="text-h3 pa-4 pb-0 pl-6">
      {{ tm("spcodeProjectLoad.fileBrowser.recentFiles.clearConfirmTitle") }}
    </v-card-title>
    <v-card-text class="pt-4">
      {{ tm("spcodeProjectLoad.fileBrowser.recentFiles.clearConfirmMessage") }}
    </v-card-text>
    <v-card-actions class="pa-4 pt-0">
      <v-spacer />
      <v-btn variant="text" @click="confirmClearRecentOpen = false">
        {{ tm("spcodeProjectLoad.fileBrowser.editor.cancel") }}
      </v-btn>
      <v-btn variant="text" color="error" @click="onConfirmClearRecent">
        {{ tm("spcodeProjectLoad.fileBrowser.recentFiles.clear") }}
      </v-btn>
    </v-card-actions>
  </v-card>
</v-dialog>
```

## 7. 状态与边界

| 情况 | 处理 |
|---|---|
| `currentRoot` 为 null | composable 读写 no-op；`<RecentFilesBlock v-if>` 不渲染 |
| 同 path 重复 recordOpen | 去重 + 更新 `openedAt` → 移到头部 |
| localStorage 抛错（quota / 私密浏览） | `safeSetItem` 已 silent catch；Recent 退化为 no-op |
| localStorage 返回非法 JSON | `loadBucket` 内 `try/catch` 返回空 entries |
| 跨 worktree 切换 | composable 内部 watch 切桶；读 / 写立刻基于新桶；老桶数据保留 |
| 50 条溢出 | recordOpen 后 `slice(0, 50)`，超出按 `openedAt` 升序丢弃 |
| 点击 Recent 里已被删/改名文件 | 走 FileBrowserView 既有 reason → error 占位（与打开 sidebar 文件树里任意文件同路径） |
| 当前 preview 打开的是 `null` | watch 早返，不记录（避免 dir-only 状态污染 Recent） |

## 8. 错误处理

| 场景 | 表现 |
|---|---|
| localStorage 写入失败 | silent no-op，主流程不受影响 |
| localStorage 读取返回非法 JSON | 视为空 entries，不抛错 |
| recordOpen 传入非 worktree 内路径 | 静默忽略（绝对 path 防污染） |
| FNV-1a 实现异常（Js 类型边界） | catch 后退回 `encodeURIComponent(worktreeRoot).slice(0, 32)` 作 key |

## 9. i18n

新增键全部挂在 `spcodeProjectLoad.fileBrowser.recentFiles.*`：
- `title` = "Recent Files"
- `titleWithCount` = "Recent Files ({count})"
- `empty` = "无最近文件"
- `more` = "+{n} more"
- `clear` = "清空"
- `clearConfirmTitle` = "清空最近文件"
- `clearConfirmMessage` = "确定要清空当前工作区的所有最近打开文件吗？此操作不影响其他工作区。"
- `removeTooltip` = "从最近文件移除"
- `quickOpenToast` = "按住 Ctrl+P 快速跳转所有文件"

双语同步更新到 `dashboard/src/i18n/zh-CN/...` 与 `en-US/...`。

## 10. 测试

### 10.1 Composable（`useRecentFiles.spec.ts`）

| 用例 | 期望 |
|---|---|
| 空桶初始化 → recordOpen 1 条 | entries 长度 1，oponedAt≈now，bucket key 正确 |
| recordOpen 后 entries 顺序 | 新条在 `[0]` |
| 重复 recordOpen 同一 path | entries 长度不变，oponedAt 更新，位置在头 |
| 累积 51 条后 recordOpen | entries 长度 50，最旧的被丢弃 |
| recordOpen 非 worktree 内路径 | 无变化（no-op） |
| currentRoot = null | 所有读写调用均返回原状 / 不抛错 |
| remove 单条 | entries 移除该 path，持久化 |
| clear | entries 长度 0，持久化 |
| watch(worktree) 切换到新桶 | 新桶空（首次）；写新桶不影响老桶 |
| 同时写两个不同 path 到同一桶 | 顺序按 recordOpen 时间倒序 |

### 10.2 Component（`RecentFilesBlock.spec.ts`）

| 用例 | 期望 |
|---|---|
| 默认 mount → 显示折叠态 | 看到 `(count)` 标题，不显示列表行 |
| 点击标题 → 展开列表 | 5 条行渲染，超出显示 `+N more` |
| 点击 × 按钮 → remove 事件 + 不冒泡到 select | emit('remove', path) 被调用一次 |
| 点击行 → select 事件 | emit('select', path) 被调用一次 |
| 点击 Clear 链接 → clear 事件 | emit('clear') |
| entries=[] 展开态 | 显示「无最近文件」占位 |
| currentRoot 变更 | 标题前缀/路径显示相应更新 |

## 11. 改动清单

1. `dashboard/src/composables/useRecentFiles.ts`（新，~90 行）
2. `dashboard/src/components/chat/message_list_comps/RecentFilesBlock.vue`（新，~120 行）
3. `dashboard/src/components/chat/GitDiffSidebar.vue`（增 ~6 行：import + watch + props 透传）
4. `dashboard/src/components/chat/message_list_comps/FileBrowserView.vue`（增 ~10 行：嵌入块 + 事件接线 + dialog 状态）
5. `dashboard/tests/composables/useRecentFiles.spec.ts`（新）
6. `dashboard/tests/components/RecentFilesBlock.spec.ts`（新）
7. `dashboard/src/i18n/{zh-CN,en-US}/...`（新增 9 个键的双语 entry）
8. **无新增 package.json 依赖**

## 12. 元信息

- 估计代码量：~180 行净增（composable ~90 + 组件 ~120 - import/空行）
- 不改变现有 sidebar API 形态
- 不引入新 npm 依赖
- 浏览频次：用户每次打开文件后立即被记录；UI 默认折叠后零首屏干扰
- 为将来的 A1 Quick Open 准备好 composable 接口
