# Design: CodeMirror 6 文件编辑器替换 ShikiEditor（消除输入回显延迟）

> Author: elecvoid243 · 2026-07-18
> Status: approved (brainstorming session 2026-07-18, 语言范围选项 1：核心语言集 + 纯文本兜底)
> Scope: dashboard only（纯前端组件替换，无后端/插件改动）

## 1. 目标

消除「工作区」文件浏览器编辑与「Git变更」.gitignore 编辑的**输入回显延迟**
（用户敲键到字符显形有 200ms+ 固定延迟），同时保留语法高亮能力。

根因（诊断于 2026-07-18）：`ShikiEditor` 采用 overlay 架构——透明 textarea
（`color: transparent`）叠在 Shiki 高亮层之上，**可见文字只能来自高亮层**；
而高亮更新被 200ms 防抖 + `requestIdleCallback` 推迟，回显因此被强制延迟。
叠加每次高亮 = 全文 TextMate 分词（双主题）+ `v-html` 全量 DOM 重建阻塞主线程。

非目标（YAGNI）：不改只读预览的 Shiki 管线（FileBrowserCodeView 等）；不改
DocumentEditor/文件管理页；不做搜索替换/代码折叠/小地图等 CM 扩展；不追求
全语言高亮对齐（verilog/matlab/powershell 等保持纯文本）。

## 2. 方案（已选）

新建自包含组件 `CodeMirrorEditor.vue`，API 面与 `ShikiEditor` 完全对齐，
两处调用方近替换式切换；`ShikiEditor.vue` 成为死代码后删除。

被否方案：
- B（保留 overlay，「先单色即时、停顿后精染」两阶段渲染）——打字期颜色褪为
  单色，体验割裂；全文 innerHTML 重建对大文件仍有布局开销；IME 问题依旧。
- C（微调：IME composition 处理 + 降低高亮阈值）——只要「文字透明 + 高亮延迟」
  架构不变，回显延迟必然存在，治标不治本。

## 3. 组件与职责

| 单元 | 职责 | 依赖 |
|---|---|---|
| `CodeMirrorEditor.vue`（新，~200 行） | CM6 挂载/销毁、懒加载语言与主题、暗色响应、echo 抑制、dirty 翻转检测、CM 失败内部降级原生 textarea | 下述 util；`@codemirror/*` |
| `utils/codemirrorLanguages.ts`（新，~90 行） | 扩展名 → CM 语言 key 映射；语言包动态 import（懒加载，不进首屏 bundle） | `@codemirror/lang-*`、`@codemirror/legacy-modes` |
| `GitIgnoreEditor.vue`（改 ~3 行） | `<ShikiEditor>` → `<CodeMirrorEditor>`，props/events 不变 | — |
| `FileBrowserFilePreview.vue`（改 ~3 行） | 同上 | — |
| `CodemirrorHost.vue` | **不动**（DocumentEditor 零回归风险） | — |

`CodeMirrorEditor` 可独立理解与测试：内容经 `modelValue` 进、`update:modelValue`
+ `dirty-change`（仅翻转）出、`getValue()/focus()` 暴露，不感知 git/文件系统。

对外契约（与 ShikiEditor 逐一对齐）：

```
props:  { modelValue: string   —— 权威基线（dirty 基准），外部替换被采纳、自身 echo 被忽略
          filePath: string     —— 仅取扩展名做语言检测 }
emits:  { "update:modelValue"(v)   —— 每次文档变更
          "dirty-change"(dirty)    —— 仅 clean↔dirty 翻转时触发 }
expose: { getValue(): string, focus(): void }
```

## 4. 语言支持（选项 1：核心语言集 + 纯文本兜底）

| 扩展名 | CM 语言 | 包 |
|---|---|---|
| .py | python | `@codemirror/lang-python` |
| .js/.mjs/.cjs | javascript | `@codemirror/lang-javascript` |
| .jsx / .ts / .tsx | javascript(jsx/ts) | 同上 |
| .json | json | `@codemirror/lang-json` |
| .yaml/.yml | yaml | `@codemirror/lang-yaml` |
| .sh/.bash/.zsh | shell (StreamLanguage) | `@codemirror/legacy-modes` |
| .css | css | `@codemirror/lang-css` |
| .html/.htm/.vue | html（.vue 为近似：template 良好、script 内染色粗略） | `@codemirror/lang-html` |
| .xml/.svg | xml | `@codemirror/lang-xml` |
| .md | markdown | `@codemirror/lang-markdown`（已有） |
| .sql | sql | `@codemirror/lang-sql` |
| .rs | rust | `@codemirror/lang-rust` |
| .go | go | `@codemirror/lang-go` |
| .c/.h/.cpp/.cc/.cxx/.hpp/.c++ | cpp（覆盖 C） | `@codemirror/lang-cpp` |
| .diff/.patch | diff (StreamLanguage) | `@codemirror/legacy-modes` |
| 其余（.gitignore/.ini/.v/.sv/.m/.ps1/dockerfile/.txt…） | 无语言 = 纯文本 | — |

新增依赖（全部 `^6`，与现有 `@codemirror/state ^6.4.1` 等同大版本对齐）：
lang-python、lang-javascript、lang-json、lang-yaml、lang-css、lang-html、
lang-xml、lang-sql、lang-rust、lang-go、lang-cpp、legacy-modes，
以及暗色主题 `@codemirror/theme-one-dark`。

语言加载模式：每个语言 key 对应一个 `() => import("@codemirror/lang-x")` 的
动态入口，命中即加载并缓存 Promise；未命中（纯文本）不加载任何语言包。

## 5. 主题（明/暗）

- 组件内部用 Vuetify `useTheme()` 响应式检测暗色（`theme.current.value.dark`），
  通过 CM `Compartment` 热切换，**不改任何父组件的 isDark props 链**。
- 暗色：`@codemirror/theme-one-dark`（theme + HighlightStyle 一体）。
- 亮色：CM 官方 `defaultHighlightStyle`（`@codemirror/language`）+ minimal
  `EditorView.theme`（字体/行高/背景对齐 Vuetify surface）。
- 字体指标对齐现状（编辑⇄预览视觉连续）：`ui-monospace, monospace` / 12.5px /
  行高 1.55；容器 `height: 100%`，透传 class（`preview-editor-body` 等）。

## 6. 编辑行为

- 行号 gutter：保留（CM 标准能力；ShikiEditor 无行号——有意的小改进）。
- Tab = 缩进 2 空格：`indentUnit.of("  ")` + `indentWithTab` keymap，对齐
  ShikiEditor 的 Tab 行为。
- 撤销历史：`history()` + `historyKeymap`（CM 标准）。
- IME 中文输入：CM6 原生处理 composition（overlay 方案未处理的额外收益）。
- 每按键状态不出组件（uncontrolled buffer + echo 抑制，沿用 CodemirrorHost
  已验证的 `lastEmittedValue` 模式）：重型父组件（GitDiffSidebar 等）不进按键
  渲染路径；`dirty-change` 仅翻转时触发，工具条每编辑会话最多重渲染两次。
- 外部 `modelValue` 替换（重载文件）→ 全量替换 doc 并复位基线；自身 echo 忽略。
- CM 模块加载失败（极端情况）→ 组件内部降级为原生 textarea（同契约），
  调用方无感知。

## 7. 状态与边界

- 2MB 编辑上限、二进制/历史版本只读等 `canEdit` 逻辑**不变**（FileBrowserFilePreview）。
- .gitignore 无对应语言 → 纯文本编辑（与现状 Shiki 表现一致：Shiki 对其也按
  text 处理）。
- 大文件：CM6 虚拟视口只渲染可见行，数万行文件输入延迟依然平坦——这是相对
  overlay 方案的结构性优势。
- 卸载：`view.destroy()`；语言/主题加载中的异步回调在卸载后不得触碰 view
  （以 token/flag 防竞争）。

## 8. 错误处理

| 场景 | 表现 |
|---|---|
| 语言包加载失败（网络/打包异常） | 降级为该文件纯文本编辑，console.warn，不打断编辑 |
| CM6 核心模块加载失败 | 组件内部切换为原生 textarea（同 props/emits/expose 契约） |
| 主题检测失败 | 回退亮色主题 |

## 9. i18n

无新增键（组件无用户可见文案；工具条文案归调用方，沿用既有键）。

## 10. 测试

1. `pnpm build`（含 vue-tsc 类型检查）通过；既有 `dashboard/tests` 全绿。
2. 手测清单：
   - 工作区编辑 .py / .md / .json / .yaml：打字回显即时、高亮正确、保存/取消/dirty 圆点正常
   - Git变更页 .gitignore：同上（纯文本）
   - 明/暗主题切换：编辑器配色跟随，无需刷新
   - 中文 IME 输入：composition 正常、无吞字
   - 大文件（~90KB / 数千行）：连续打字流畅、滚动流畅
   - Tab 缩进、Ctrl+Z 撤销、行号显示

## 11. 改动清单

1. `dashboard/package.json` + lockfile：新增 13 个 `@codemirror/*` 依赖
2. `dashboard/src/utils/codemirrorLanguages.ts`（新）
3. `dashboard/src/components/chat/message_list_comps/CodeMirrorEditor.vue`（新）
4. `dashboard/src/components/chat/message_list_comps/GitIgnoreEditor.vue`（换组件）
5. `dashboard/src/components/chat/message_list_comps/FileBrowserFilePreview.vue`（换组件）
6. `dashboard/src/components/chat/message_list_comps/ShikiEditor.vue`（删除）
