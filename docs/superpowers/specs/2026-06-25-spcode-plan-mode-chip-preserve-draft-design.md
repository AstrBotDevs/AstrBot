# Spcode Plan/Build Chip — 保留输入框草稿

| 项目 | 内容 |
|------|------|
| 主题 | 修复 `SpcodePlanModeChip` 点击时清空用户输入框草稿的 bug:点击 chip 只切换 plan/build 模式,用户已输入的文字、staged 图片/文件/音频、pending file comments 全部保留在框内,bot 只收到裸的 `/plan` 或 `/build` 命令 |
| 日期 | 2026-06-25 |
| 作者 | elecvoid243 |
| 状态 | Draft — 待 review |
| 修订 | v1.0 |
| 关联代码(前端) | `dashboard/src/components/chat/SpcodePlanModeChip.vue`<br>`dashboard/src/components/chat/ChatInput.vue`<br>`dashboard/src/components/chat/Chat.vue` (3 mount 点)<br>`dashboard/src/components/chat/StandaloneChat.vue` (1 mount 点) |
| 关联代码(后端) | 无改动(spcode 插件 `/plan` / `/build` 路由与 `_plan_filter_tools` 钩子不变) |
| 前置 spec | 无(纯前端 UX 修复) |
| 配套文档 | `dashboard/src/composables/useSpcodePlanMode.ts`(状态来源,本方案只消费) |

---

## 1. 背景与目标

### 1.1 现状

`SpcodePlanModeChip`(`dashboard/src/components/chat/SpcodePlanModeChip.vue`)是一个 toggle 风格的 chip,挂在 `ChatInput` 状态栏右上角,跟 `SpcodeProjectIndicator`、`GitDiffChip` 并列。它通过 `emit("toggle")` 通知 `ChatInput`。

`ChatInput.handlePlanModeToggle()` 当前实现(`ChatInput.vue:1057-1072`):

```ts
function handlePlanModeToggle(): void {
  const isPlan = spcodePlanMode.status.value.active === true;
  const cmd = isPlan ? "/build" : "/plan";
  spcodePlanMode.setActive(!isPlan);   // 乐观翻转 chip
  localPrompt.value = cmd;             // ❌ 把用户输入框的文字覆盖成 /plan
  emit("send");                        // 触发父级 sendCurrentMessage
}
```

父级 `StandaloneChat.sendCurrentMessage()`(`StandaloneChat.vue:321-357`):

```ts
const userText = draft.value.trim();   // 此时 draft 已经是 /plan,被覆盖了
const commentText = fileComments.formatForLLM();
const fullText = [userText, commentText].filter(Boolean).join("\n\n");
const parts = buildOutgoingParts(fullText);
...
draft.value = "";                       // ❌ 发送后再次清空输入框
clearStaged({ revokeUrls: false });
```

### 1.2 Bug 描述

如果用户在输入框里**已经输入了一些文字**(例如 `fix the login bug`),点击 chip 后会发生:

1. `localPrompt.value = cmd` 立即把文字覆盖为 `/plan`,用户看到输入框一闪(原文 → `/plan`)
2. `emit("send")` 触发父级 `sendCurrentMessage`
3. 父级 `draft.value = ""` 在发送后把输入框清空
4. **结果**:用户辛苦打的字被吞掉,光标位置丢失,如果在 IME 合成中还会触发 IME 状态错乱

如果 staged 了图片/文件/音频,这些资产也会被一起发出去,而不是保留给用户后续使用——这违反了"chip 是模式开关,跟内容无关"的语义。

### 1.3 目标

1. 点击 chip 时,bot 只收到裸的 `/plan` 或 `/build` 命令(单条 plain text 消息)
2. 用户输入框里**已输入的文字、staged 图片/音频/文件、pending file comments 100% 保留**
3. 保持 chip 现有"一键切换"哲学(不要求用户再按一次 Enter 确认)
4. 保持 spcode plan/build 状态机的语义不变(`useSpcodePlanMode().setActive` 乐观翻转 + `refresh()` 权威纠偏)
5. 流式响应中点击 chip 仍然能发新命令(spcode 插件后端对 `/plan` 幂等,自然不会状态错乱)

### 1.4 非目标(显式不做)

- ❌ **不**修改 spcode 插件后端的 `/plan` / `/build` 路由或 `_plan_filter_tools` 钩子
- ❌ **不**改变 `useSpcodePlanMode` singleton 的状态机与刷新策略
- ❌ **不**改 `SpcodePlanModeChip` 的视觉(颜色 / icon / label / tooltip)— chip 仍然反映 `useSpcodePlanMode.status.value.active`
- ❌ **不**做 staged 内容是否发送的"二次确认"(用户已选 A:全部保留)
- ❌ **不**改 IME 合成期间的 click 行为(点击是用户主动操作,不需要 defer)
- ❌ **不**改 `sendCurrentMessage` 函数本身(它仍然处理"按 Enter 发草稿"的主路径)
- ❌ **不**改 ChatInput 的现有 emits 列表语义(只新增,不替换)

---

## 2. 设计决策(已与用户确认)

| # | 决策点 | 选择 | 理由 |
|---|--------|------|------|
| 1 | 点击时 bot 实际收到什么 | **只发裸命令 `/plan` 或 `/build`**(不拼接用户草稿) | chip 是模式开关,跟用户草稿语义无关;用户希望先切到 plan 让 bot 做计划,再自己按 Enter 发真实请求 |
| 2 | 用户草稿与 staged 内容处理 | **完全不动**(文字 / 图片 / 音频 / 文件 / pending comments 全部留在原位) | chip 的语义是"切模式",不是"发送";与方案 1 一致 |
| 3 | 流式响应中点击 chip | **允许,照常发新命令** | spcode 插件对 `/plan` 幂等;现有 `useSpcodePlanMode().refresh()` 在 stream end 时自动拉权威状态纠偏 |
| 4 | 实现路径 | **方案 1(推荐):ChatInput 新增 `send-command` 事件,父级发"裸"消息** | 唯一不引入 UI 闪烁/状态错位的方案;`send-command` 与现有 `send` 是两条独立契约,语义清晰 |
| 5 | 父级函数命名 | `sendCommandMessage(text: string)` | 与现有 `sendCurrentMessage()` 形成"send 草稿" vs "send 裸命令"对偶 |
| 6 | `sendCommandMessage` 内部 part 构造 | `[{ type: "plain", text }]` | 严格不混入草稿或 staged 内容;只走 plain text 通道 |
| 7 | `sendCommandMessage` 是否清空输入框 | **不**清空 | 主诉求;任何写 `draft.value = ""` 的代码都是反模式 |
| 8 | `sendCommandMessage` 是否 clearStaged | **不**调用 | 同上;staged 内容保留 |
| 9 | `sendCommandMessage` 是否抢回焦点 | **不** | 用户在编辑框里,chip 在右上角,不需要 focus 回弹;不打断 IME |
| 10 | ChatInput emit 新签名 | `(e: 'send-command', text: string): void` | 与现有 `(e: 'send'): void` 对偶;`text` 是必传参数 |
| 11 | 受影响的 mount 点 | **3 个**:`Chat.vue:308` (ProjectView 内) / `Chat.vue:457` (默认 chat) / `StandaloneChat.vue:141` (standalone) | 全部需要 `@send-command` 监听,否则 Vue runtime warning(不致命但难看) |
| 12 | `useSpcodePlanMode` 乐观翻转位置 | **保留**在 `handlePlanModeToggle` 内 | chip 视觉立刻响应,跟"命令何时被 bot 确认"解耦 |
| 13 | 错误处理 | 不新增;沿用现有 SSE/WebSocket 错误流(失败时 bot 气泡显示错误,`setActive` 乐观翻转靠下次 `refresh()` 自然回滚) | 现有架构已经兜底 |
| 14 | `onStreamEnd` 自动纠偏 | **保留**不动 | spcode 插件的 plan 状态权威源是后端,`Chat.vue` 的 session watcher / `useMessages` 的 `onStreamEnd` 已经在调 `refresh()`,本次改动不需要新增钩子 |
| 15 | 国际化文案 | **不新增**;`SpcodePlanModeChip` 的 active/inactive label 与 tooltip 不变 | 修复 bug 不引入新文案 |

---

## 3. 数据流与状态

### 3.1 旧数据流(有 bug)

```
[用户在输入框打"fix the login bug"]

SpcodePlanModeChip.onClick()
  └─ emit("toggle")

ChatInput.handlePlanModeToggle()
  ├─ spcodePlanMode.setActive(!isPlan)        [chip 立刻变色 ✅]
  ├─ localPrompt.value = "/plan"              [❌ 输入框变 /plan]
  ├─ emit("update:prompt", "/plan")           [父级 draft.value = "/plan"]
  └─ emit("send")

StandaloneChat.sendCurrentMessage() {
  const userText = draft.value.trim();        // "/plan" ← 用户的字没了
  const parts = buildOutgoingParts("/plan");
  const { botRecord } = createLocalExchange(...);
  draft.value = "";                            // ❌ 输入框清空
  clearStaged(...);                            // ❌ staged 也清空
  sendMessageStream({ parts });                // bot 收到 /plan
}

结果:用户输入框显示空,staged 资产被发出去,用户的字丢了
```

### 3.2 新数据流(本次方案)

```
[用户在输入框打"fix the login bug",staged 一张图]

SpcodePlanModeChip.onClick()
  └─ emit("toggle")

ChatInput.handlePlanModeToggle() {
  const isPlan = spcodePlanMode.status.value.active === true;
  const cmd = isPlan ? "/build" : "/plan";
  spcodePlanMode.setActive(!isPlan);           // [chip 立刻变色 ✅]
  emit("send-command", cmd);                   // ✅ 只发事件,不动 localPrompt
  // localPrompt / draft / staged / fileComments 全部原样
}

StandaloneChat @send-command="sendCommandMessage"

async function sendCommandMessage(text: string) {
  const sessionId = await ensureSession();
  const messageId = crypto.randomUUID?.() || `${Date.now()}-${Math.random()}`;
  const parts: MessagePart[] = [{ type: "plain", text }];   // ✅ 只有命令
  const { botRecord } = createLocalExchange({ sessionId, messageId, parts });
  const selection = inputRef.value?.getCurrentSelection();
  sendMessageStream({                          // ✅ bot 收到 /plan
    sessionId, messageId, parts,
    transport: transportMode.value,
    enableStreaming: enableStreaming.value,
    selectedProvider: selection?.providerId || "",
    selectedModel: selection?.modelName || "",
    botRecord,
  });
  // ❌ 不写 draft.value
  // ❌ 不调用 clearStaged
  // ❌ 不调用 focusChatInput
  // ❌ 不调用 scrollToBottom(用户视线还在输入框)
}

结果:用户输入框依然显示"fix the login bug",staged 图片保留,bot 收到一条 /plan 消息
```

### 3.3 状态机不变量

| 状态 | 谁负责 | 何时被读 / 被写 |
|------|--------|-----------------|
| `props.prompt` (ChatInput 的草稿) | 用户输入、`update:prompt` emit、IME 合成 | 点击 chip 不再写它 |
| `spcodePlanMode.status.value.active` | `setActive()` 写、`refresh()` 写、`reset()` 写 | chip 视觉;点击 chip 时乐观翻转 |
| `useMessages.activeConnections[sessionId]` | 父级 `sendMessageStream` / `sendCommandMessage` 写 | 决定 `isRunning` / `disabled` 视觉 |
| bot 端的 plan 状态(权威源) | spcode 插件后端 | `useSpcodePlanMode().refresh()` 拉取,纠偏本地 |

---

## 4. 组件契约

### 4.1 `ChatInput.vue` 改动

#### 4.1.1 `defineEmits` 新增一条

```ts
const emit = defineEmits<{
  "update:prompt": [value: string];
  send: [];
  stop: [];
  toggleStreaming: [];
  removeImage: [index: number];
  removeAudio: [];
  removeFile: [index: number];
  startRecording: [];
  stopRecording: [];
  pasteImage: [event: ClipboardEvent];
  fileSelect: [files: FileList];
  clearReply: [];
  openLiveMode: [];
  "open-diff-sidebar": [];
  // ↓ NEW
  "send-command": [text: string];
}>();
```

#### 4.1.2 `handlePlanModeToggle` 改为

```ts
function handlePlanModeToggle(): void {
  const isPlan = spcodePlanMode.status.value.active === true;
  const cmd = isPlan ? "/build" : "/plan";
  spcodePlanMode.setActive(!isPlan);
  emit("send-command", cmd);  // ← 替换掉原 localPrompt.value = cmd + emit("send")
}
```

模板侧不动(`<SpcodePlanModeChip @toggle="handlePlanModeToggle" />`)。

### 4.2 `Chat.vue` 改动

#### 4.2.1 3 个 `<ChatInput>` mount 各加一条监听

`Chat.vue:308` (ProjectView 内) / `Chat.vue:457` (默认 chat):

```vue
<ChatInput
  ...
  @send="sendCurrentMessage"
  @send-command="sendCommandMessage"   ← NEW
  ...
/>
```

#### 4.2.2 新增 `sendCommandMessage` 函数

放在 `sendCurrentMessage` 旁边(同 `script setup` 内,`Chat.vue:1376` 后):

```ts
/**
 * Send a bare chat command (e.g. /plan, /build) without touching the
 * user's draft, staged attachments, or pending file comments.
 *
 * Used by ChatInput's plan/build chip (SpcodePlanModeChip), which
 * semantically only flips the spcode plan/build mode and should not
 * disturb whatever the user is composing. The command is dispatched
 * as a plain-text message through the same sendMessageStream pipeline
 * the main send path uses, so the bot-side interceptor (/plan,
 * /build handler) sees an identical wire format.
 */
async function sendCommandMessage(text: string): Promise<void> {
  const sessionId = currSessionId.value || (await newSession());
  const messageId = crypto.randomUUID?.() || `${Date.now()}-${Math.random()}`;
  const parts: MessagePart[] = [{ type: "plain", text }];
  const selection = inputRef.value?.getCurrentSelection();
  const { botRecord } = createLocalExchange({ sessionId, messageId, parts });
  sendMessageStream({
    sessionId,
    messageId,
    parts,
    transport: transportMode.value,
    enableStreaming: enableStreaming.value,
    selectedProvider: selection?.providerId || "",
    selectedModel: selection?.modelName || "",
    botRecord,
  });
}
```

注:不写 `sending.value = true` 切换;不重置 `draft` / `replyTarget`;不调 `clearStaged`;不调 `focusChatInput`;不调 `scrollToBottom`。这五个"省略"是与 `sendCurrentMessage` 的关键差异。

### 4.3 `StandaloneChat.vue` 改动

#### 4.3.1 1 个 `<ChatInput>` mount 加监听

`StandaloneChat.vue:141` 附近:

```vue
<ChatInput
  ...
  @send="sendCurrentMessage"
  @send-command="sendCommandMessage"   ← NEW
  ...
/>
```

#### 4.3.2 新增 `sendCommandMessage` 函数

放在 `sendCurrentMessage` 旁边(`StandaloneChat.vue:357` 后):

```ts
/**
 * See Chat.vue's docstring for the rationale. This is the
 * standalone-composer counterpart: send a bare command, leave the
 * user's draft / staged assets / pending comments alone.
 */
async function sendCommandMessage(text: string): Promise<void> {
  const sessionId = await ensureSession();
  const messageId = crypto.randomUUID?.() || `${Date.now()}-${Math.random()}`;
  const parts: MessagePart[] = [{ type: "plain", text }];
  const selection = inputRef.value?.getCurrentSelection();
  const { botRecord } = createLocalExchange({ sessionId, messageId, parts });
  sendMessageStream({
    sessionId,
    messageId,
    parts,
    transport: transportMode.value,
    enableStreaming: enableStreaming.value,
    selectedProvider: selection?.providerId || "",
    selectedModel: selection?.modelName || "",
    botRecord,
  });
}
```

注意:`StandaloneChat.sendCurrentMessage` 不重置 `sending` 标志(用的是 `initializing`),`sendCommandMessage` 同样不切这个 flag——命令发送不阻塞用户继续编辑,与"`sendCurrentMessage` 之后焦点回到输入框"语义不同。

---

## 5. 错误处理与并发

### 5.1 错误流

| 失败点 | 现有行为 | 本方案行为 |
|--------|----------|------------|
| `ensureSession()` 抛错 | `sendCurrentMessage` 中由 try/catch 兜底,console.error | `sendCommandMessage` 同样让异常上抛,bot 气泡区不会变;前端 console 报错 |
| SSE 连接失败 | bot 气泡追加错误信息,`activeConnections` 清掉 | 同左(`sendMessageStream` 内部 .catch 处理) |
| spcode 插件后端拒绝 `/plan` | bot 端不切换;`useSpcodePlanMode().refresh()` 下次拉回正确状态 | **不变**——本次不引入新错误路径 |
| 用户在响应中连点 3 次 chip | 3 条 `/plan` 消息排队发送 | 3 条 `/plan` / `/build` 消息发送(等价于状态切换 3 次);spcode 后端幂等,最终态正确;`refresh()` 在每次 stream end 后拉权威值 |

### 5.2 乐观翻转与权威纠偏

```
点击 chip
  ├─ setActive(!isPlan)              [本地 ref 立刻翻]
  ├─ emit("send-command", cmd)       [新事件]
  └─ sendCommandMessage
        └─ sendMessageStream("/plan")  [bot 端处理]

[几秒后 bot 响应回包]
  └─ onStreamEnd(sessionId)
        └─ useSpcodePlanMode().refresh()  [拉权威状态]
              └─ 覆盖 status.value(包括 allActiveCount 派生)

如果 bot 端拒绝(网络错误)→ refresh() 拉到 active=false → chip 视觉回滚
如果 bot 端接受 → refresh() 拉到 active=true → chip 视觉与新值一致
```

与现状一致;本次改动**不**修改 `useSpcodePlanMode` 任何方法。

### 5.3 与现有 race condition 的关系

`handlePlanModeToggle` 的 `setActive` 在 emit 之前同步执行,确保 chip 在父级 `sendCommandMessage` 启动网络请求之前已经变色——视觉反馈无延迟。`emit("send-command")` 同步派发后,Vue 同步传播到父级监听器,父级 `await ensureSession()` 是异步的,但 `setActive` 不依赖它。这与原 `localPrompt.value = cmd` + `emit("send")` 的同步时序完全一致。

---

## 6. 兼容性

| 兼容性维度 | 影响 |
|------------|------|
| spcode 插件后端 | **零**改动;`/plan` / `/build` 路由接到的 wire 格式不变(plain text 消息) |
| `useSpcodePlanMode` composable | **零**改动;`status` / `setActive` / `refresh` / `reset` 行为完全保留 |
| `SpcodePlanModeChip` 组件 | **零**改动;它仍然只 emit `toggle`,对 `localPrompt` 无感知 |
| `ChatInput` 现有 emits | **零**删除;`send-command` 是新增 |
| 其他把 `<ChatInput>` 当宿主的组件 | 需补 `@send-command` 监听(本 spec 覆盖 3 个 mount 点;若有第 4 个,需另行加) |
| 其它 panel(右侧 sidebar、thread panel) | **零**影响 |

---

## 7. 测试计划

### 7.1 手工 e2e(主要验收路径)

| # | 场景 | 期望 | 验证方法 |
|---|------|------|----------|
| T1 | 输入框为空,点 chip | bot 收到 `/plan`(或 `/build`),输入框仍为空,chip 变色 | DevTools Network 看到 `POST /chat` body 含 `/plan`;`localPrompt` 仍为 `""` |
| T2 | 输入框有"fix the login bug",点 chip | bot 收到 `/plan`,**输入框文字完整保留** | Network body `/plan` 不含用户文字;UI 输入框显示原文字,光标在原位置 |
| T3 | 输入框有文字 + staged 一张图,点 chip | bot 收到 `/plan`(无图),文字保留,staged 图片保留 | Network body 仅含 plain `/plan`,无 image attachment;`stagedImagesUrl` 不变 |
| T4 | 输入框有文字 + 3 个 pending file comments,点 chip | bot 收到 `/plan`,文字保留,comments 保留 | `fileComments.totalCount` 不变 |
| T5 | 流式响应中点 chip | 启动新流,bot 气泡按时间序出现,文字保留 | DevTools Network 看到两次 `POST /chat` |
| T6 | 连续点 chip 3 次 | bot 收到 3 条命令(乐观翻转 3 次),最终态与最后一次点击一致 | 视觉 chip 颜色:绿→橙→绿(假设从 build 起步) |
| T7 | 切换 session 后看 chip 状态 | chip 状态被 `useSpcodePlanMode().refresh()` 拉回正确值 | DevTools Network `GET /spcode/plan-mode?umo=...` |
| T8 | 输入框 IME 合成中点 chip | 命令照常发,文字不被打断,IME 不错位 | 拼音输入中点击,拼音候选不消失 |
| T9 | 在 ProjectView 内点 chip | 行为同上(ProjectView 内的 ChatInput 走 `Chat.vue:308` mount) | 切到 project 视图后重复 T2 |

### 7.2 自动化测试

- 本次改动**不**新增单元测试。原因:`handlePlanModeToggle` 改动只有 1 行(`emit("send-command", cmd)` 替换 2 行),`sendCommandMessage` 是 4-5 行的胶水代码,价值低于 e2e 验证;现有仓库无 ChatInput 单元测试覆盖,本次不引入新测试基础设施。
- 若后续需要:`handlePlanModeToggle` 可在 jsdom 中通过 mock `useSpcodePlanMode` + 断言 emit 列表来测。

### 7.3 回归检查

- `ruff format .` / `ruff check .` 通过
- `pnpm generate:api` **不**需要跑(无后端契约变更)
- 现有 `LocalRoot.test.ts` / `useSpcodePlanMode.test.ts` 等不受影响(无 import 变更)

---

## 8. 风险与回退

### 8.1 风险

| 风险 | 缓解 |
|------|------|
| 父级 `sendCommandMessage` 漏写(3 个 mount 之一没加 `@send-command`) | 代码 review 检查 + DevTools warning;最坏情况 chip 点击 console 报 "Component emitted event 'send-command' but it is not declared"——不致命 |
| 父级 `sendCommandMessage` 中错误地写了 `draft.value = ""` | review checklist 强调;若发生,功能退化到原 bug 状态(可回退) |
| `ensureSession()` 在新会话路径下耗时较长,导致 chip 点击到 bot 收到命令有 100-300ms 延迟 | 可接受(原 `sendCurrentMessage` 也是同路径);不优化 |
| spcode 插件后端对 `/plan` 的幂等性与本设计假设不一致 | 需要与 spcode 插件后端契约对齐;若发现非幂等,在 chip 端加 `isRunning` 守卫即可,改动局部 |

### 8.2 回退方案

如果上线后出现严重问题,回退 = 把 `ChatInput.handlePlanModeToggle` 改回 3 行原版:

```ts
spcodePlanMode.setActive(!isPlan);
localPrompt.value = cmd;
emit("send");
```

加 revert 父级 3 处 `@send-command` 监听 + 2 个 `sendCommandMessage` 函数。git revert 一次提交即可。

---

## 9. 实施检查表(供 writing-plans 阶段细化)

- [ ] `ChatInput.vue`:`defineEmits` 加 `send-command`;`handlePlanModeToggle` 改 emit
- [ ] `Chat.vue:308` mount 加 `@send-command`
- [ ] `Chat.vue:457` mount 加 `@send-command`
- [ ] `Chat.vue`:在 `sendCurrentMessage` 后新增 `sendCommandMessage` 函数
- [ ] `StandaloneChat.vue:141` mount 加 `@send-command`
- [ ] `StandaloneChat.vue`:在 `sendCurrentMessage` 后新增 `sendCommandMessage` 函数
- [ ] `ruff format .` / `ruff check .` 通过
- [ ] 手工 e2e 9 项全部通过
- [ ] 提交 commit(commit message 建议:`fix(chatui): preserve user draft when toggling spcode plan/build mode`)
