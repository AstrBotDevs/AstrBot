# Design: Git 变更页 .gitignore 编辑器

> Author: elecvoid243 · 2026-07-17
> Status: approved (brainstorming session 2026-07-17, entry-point option A)
> Scope: dashboard only（复用既有后端端点，无插件改动）

## 1. 目标

在 GitDiffSidebar 的「Git变更」子页面内闭环编辑仓库根的 `.gitignore`：
看 diff → 发现该加忽略规则 → 就地编辑保存 → 列表自动刷新，全程不离开 diff 页。

非目标（YAGNI）：模板/snippets 辅助、多 .gitignore（子目录）编辑、ignore 规则校验。

## 2. 方案（已选 A）

侧栏 header 在 `viewMode === 'diff'` 时显示 `.gitignore` 按钮（图标 + 文字，刷新按钮旁）。
点击在侧栏内容区打开**页内覆盖层编辑器**；保存走既有 `POST /spcode/file-write`。

被否方案：B（diff body 内工具行 + 居中 dialog —— 侧栏宽度下对话框编辑器局促）；
C（跳转工作区 tab —— 打断动线且丢失 diff 页滚动/选中状态）。

## 3. 组件与职责

| 单元 | 职责 | 依赖 |
|---|---|---|
| `GitIgnoreEditor.vue`（新，~150 行） | 覆盖层 UI：顶部工具条（文件名 / dirty 圆点 / 保存 / 取消）+ `ShikiEditor` 主体 + 内联错误条 + 新建提示 | props: `modelValue`(open)、`content`、`isSaving`、`saveError`、`isNewFile`；emits: `save(content)`、`cancel` |
| `GitDiffSidebar.vue`（装配，~80 行） | 状态（open / buffer / dirty / saveError / isNewFile）+ 读取编排 + 保存编排 + 刷新链路 | 下述 composable |
| `useSpcodeFileWrite`（已有） | `POST /spcode/file-write` 覆写（不存在即创建） | — |
| 读取：一次性 `/spcode/file-browser` 调用 | 取 `<worktree>/.gitignore` 内容 | 先例：`useSpcodeNewFileLineCounts.ts:126` 同模式单文件读取 |

`GitIgnoreEditor` 可独立理解与测试：给内容进、`save`/`cancel` 出，不感知 git。

## 4. 数据流

```
打开  → GET /spcode/file-browser { path: <worktreeRoot>/.gitignore }（绝对路径；
        先例 useSpcodeNewFileLineCounts.ts:125 仅传 path）
        成功 → buffer = content（isNewFile=false）
        path_not_found → buffer = ""，isNewFile=true（工具条显"将新建文件"，非错误）
        其他失败 → 覆盖层内错误条 + 重试
编辑  → dirty = buffer !== 已加载内容
保存  → useSpcodeFileWrite.save({ path: ".gitignore", content: buffer })
        （repo 相对路径；composable 自动附 umo/worktree）
成功  → 关闭覆盖层 + snackbar 成功 + 并行刷新 gitStatus.refresh() / composable.refresh()
失败  → 内联错误条（覆盖层不关、buffer 不丢）
```

## 5. 状态与边界

- 保存成功**自动关闭**编辑器。
- dirty 时点「取消」→ 按钮切换为「确认放弃？」二次点击态（3s 或点击他处复位）；clean 时直接关。
- 覆盖层打开期间切 tab / 关侧栏 → v-if 卸载直接销毁，不挽留（与 DocumentEditor 宽松语义一致）。
- `selectedWorktree` 变化 → 关闭覆盖层（buffer 属于旧 worktree）。
- 移动端：覆盖层铺满侧栏，无额外适配（侧栏本身已全宽）。

## 6. 错误处理

| 场景 | 表现 |
|---|---|
| 读取失败（除 path_not_found） | 覆盖层内错误条 + 重试按钮 |
| 保存失败（reason 透传：permission_denied / path_unsafe / network / unknown 等） | 编辑器内联错误条，snackbar 不出 |
| 保存成功 | snackbar success「.gitignore 已保存」 |

## 7. i18n

仅 zh-CN（spcodeProjectLoad 段落的既有惯例，en/zh-TW 走回退）。
键位 `spcodeProjectLoad.diffSidebar.gitWorkflow.gitignore.*`：
`openButton` / `title` / `newFileHint` / `save` / `cancel` / `confirmDiscard` /
`saveSuccess` / `loadError` / `retry` / `saveError`（含 {reason}）。

## 8. 测试

组件测试（镜像 `GitRepoInitPrompt.spec.ts` 风格）：
1. 打开 → 渲染工具条 + 编辑器；isNewFile 时显示新建提示
2. dirty 时点取消 → 出现「确认放弃？」；二次点击 → emit cancel
3. clean 时点取消 → 直接 emit cancel
4. 保存中 → 保存按钮 loading；saveError prop → 内联错误条渲染

## 9. 改动清单

1. `message_list_comps/GitIgnoreEditor.vue`（新）
2. `GitDiffSidebar.vue`：header 按钮 + 状态与编排 + 覆盖层挂载 + worktree watcher
3. `i18n/locales/zh-CN/features/chat.json`：一组键
4. `GitIgnoreEditor.spec.ts`（新）
