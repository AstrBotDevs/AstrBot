# Dynamic Choice Box Rendering — Design Spec

| Field | Value |
| --- | --- |
| Spec author | elecvoid243 |
| Created at | 2026-06-28 17:01 (CST) |
| Status | Draft — pending user review |
| Brainstormed via | `using-superpowers` → `brainstorming` |

---

## 1. Goal

让 LLM 在需要人类审批/确认时，通过调用工具输出一个**结构化的"选项框"中间格式**；WebChat 前端拿到中间格式后**动态渲染**为一个可交互的选项卡，用户点击选项（或输入自定义文本）后，**以普通 user message 形式**回传给 LLM。

### Non-goals (out of scope for v1)

- 嵌套 / 多步骤复合选项
- 多选模式
- 风险等级 / 推荐项标记
- 选项倒计时 / 自动过期
- Tool-result 通道回传（即不引入"工具挂起等用户"机制）
- 非 WebChat 平台（先做 webchat，其他 platform 后续适配）

---

## 2. Background

### 2.1 Why this matters

当前 WebChat 前端只支持"纯文本回复 + 工具调用结果展示"。当 LLM 需要做"是否执行危险操作"这种**人类审批**决策时，它只能输出自然语言——用户必须把 LLM 文字"翻译"成回复（比如手动打"是"或"否"），既不直观也容易出错（错别字、误判意图）。

### 2.2 Current architecture (recap)

- 前端消息模型 (`dashboard/src/composables/useMessages.ts`)：`MessagePart` 是 `type`-driven 判别联合，目前 type 包括 `plain/think/reply/image/record/video/file/tool_call`。
- `ChatMessageList.vue` 用 v-if/v-else-if 链按 `part.type` 路由到不同渲染分支；未识别 type 落到 `unknown-part` 兜底。
- 后端 `BaseMessageComponent` (`astrbot/core/message/components.py`) 是所有消息组件基类；`FunctionTool` 工具的 result 通过 `tool` role 消息回到 LLM 上下文。
- 用户消息通过 `sendChatMessage({message: string | MessagePart[]})` 发送。

### 2.3 Extension strategy (chosen via brainstorming)

- **前端**：`MessagePart` 增加新 type `interactive_choice`；`ChatMessageList.vue` v-else-if 链中加一个分支路由到新组件。
- **后端**：本期不增加新的 `MessageComponent`——工具 result 走通用的 `Json` 组件即可（webchat 平台侧做 type 翻译，把 `Json.data` 解析为 `InteractiveChoicePart`）。
- **回传路径**：纯文本——把 `option.value` 或用户输入文本原样塞进 `sendChatMessage`，走标准 user message 通道，**不携带** `tool_call_id` 之类的隐含标记。

---

## 3. Design — Intermediate Format

### 3.1 TypeScript-style schema (canonical)

```ts
interface InteractiveChoicePart {
  type: "interactive_choice";        // 固定值,前端靠它路由

  // ① 提问文案(显示在选项框顶部)
  prompt: string;                    // 例: "请选择下一步要使用的模型:"

  // ② 可选标题(比如 "模型选择" / "操作确认" / "危险操作确认")
  title?: string;

  // ③ 选项列表(单选,所以 length >= 2)
  options: ChoiceOption[];

  // ④ 可选:自由输入的占位符文本
  input_placeholder?: string;        // 例: "或输入你想用的模型名..."
}

interface ChoiceOption {
  id: string;          // 唯一 ID,仅供前端 :key,不发给 LLM
  label: string;       // 按钮上显示的文字(面向用户)
  description?: string;// hover / 展开时显示的说明(面向用户)
  value: string;       // 选中后真正发给 LLM 的文本(面向 LLM)
}
```

### 3.2 Field constraints

| 字段 | 必填 | 长度上限 | 越界处理 |
| --- | --- | --- | --- |
| `type` | ✓ | — | 固定值 |
| `prompt` | ✓ | 200 字 | 前端截断 |
| `title` | ✗ | 30 字 | 前端截断 |
| `options` | ✓ | 2 ~ 10 个 | 少于 2 视为非法,前端降级为 unknown-part |
| `options[].id` | ✓ | — | 必填,前端用作 :key |
| `options[].label` | ✓ | 30 字 | 前端截断 |
| `options[].description` | ✗ | 200 字 | 前端截断 |
| `options[].value` | ✓ | 不限 | 不截断(交给 LLM 读) |
| `input_placeholder` | ✗ | 60 字 | 前端截断;空时使用默认 "或输入自定义内容..." |

### 3.3 Placement

`InteractiveChoicePart` 总是**追加在** LLM 的 plain text 回复之后,作为 `message[]` 数组中的**新一段**。LLM 仍然可以先输出一段自然语言引导(plain text part),然后紧跟一个 `interactive_choice` part。

### 3.4 Implicit design decisions (any can be vetoed)

- **没有 `tool_call_id`**: 因为是纯文本回传,不需要关联
- **没有"是否必选"标志**: 永远允许"自定义输入"(等同 0 号隐含选项)
- **没有"默认选项"**: 避免 LLM 替用户决策
- **没有"超时"字段**: 交给上层策略(session 过期、checkpoint 失效);前端不做倒计时
- **没有"取消"语义**: 用户永远可以无视选项框直接打字发新消息

---

## 4. Design — Frontend Rendering

### 4.1 Routing

`ChatMessageList.vue` v-else-if 链**末尾**新增一个分支(在 `unknown-part` 兜底**之前**):

```vue
<!-- 现有 -->
<div v-else-if="part.type === 'tool_call'" class="tool-call-block">...</div>

<!-- 新增 -->
<InteractiveChoiceBox
  v-else-if="part.type === 'interactive_choice'"
  :part="part"
  :is-dark="isDark"
  @submit="onInteractiveChoiceSubmit($event, msg)"
/>

<!-- 兜底 -->
<div v-else class="unknown-part">...</div>
```

新组件位置:`dashboard/src/components/chat/message_list_comps/InteractiveChoiceBox.vue`,与 `ToolCallCard.vue` 同级。

### 4.2 Component contract

```ts
// InteractiveChoiceBox.vue
const props = defineProps<{
  part: InteractiveChoicePart;
  isDark?: boolean;
}>();

const emit = defineEmits<{
  submit: [text: string];  // 用户提交后向上抛"将要发往 LLM 的文本"
}>();
```

**组件内部只管理一个状态**:`submittedValue: string | null`
- `null` → 渲染"待选" UI
- 非空 → 渲染"已选择/已输入"只读态

### 4.3 Layout (待选态)

```
┌────────────────────────────────────┐
│ [icon] title(可选)                 │
│         prompt 文案                │
├────────────────────────────────────┤
│  ⓵ label                       ▾  │
│     └ description(hover 展开)     │
│  ⓶ label                       ▾  │
│  ⓷ label                       ▾  │
├────────────────────────────────────┤
│  [textarea, placeholder]      │
│              [   提交  ]         │
└────────────────────────────────────┘
```

### 4.4 State machine

| 状态 | 触发 | 视觉 | 是否可再次点击 |
| --- | --- | --- | --- |
| `pending` | 初始 | 上方布局 | ✓ |
| `submitted_via_option` | 点按钮 | 顶部 ✓ + "已选择: {label}" + 整卡灰显 | ✗ |
| `submitted_via_input` | 提交 textarea | 顶部 ✓ + "已输入: {text}" + 整卡灰显 | ✗ |
| `ignored` | 用户在 ChatInput 自行打字并发送 | 淡化的"已忽略"标签 + 整卡灰显 | ✗ |

**为什么"已提交后不可改"**: 避免用户反复改选择导致 LLM 上下文矛盾;想改直接发新消息说"改成 B"。

### 4.5 Submit handling (core logic)

在 `ChatMessageList.vue` (或其父容器如 `Chat.vue`) 中:

```ts
function onInteractiveChoiceSubmit(text: string, sourceMsg: ChatRecord) {
  // 走标准 user message 通道 — 不带任何隐藏标记
  sendMessage({ text });
}
```

**关键点**: 纯文本回传在代码里的具体实现就是把 `option.value` / 用户输入文本塞进 `sendChatMessage` 的 `message` 字段。LLM 仅凭上下文(刚问过问题)推断这是对工具调用的回应。

### 4.6 与 ChatInput 的协作

选项框存在期间,`ChatInput` 仍可用——用户在 textarea 打字并按 Enter 会走标准 send 路径,**不经过 InteractiveChoiceBox**。

这意味着两条提交路径并存:
- 路径 1: 用户**点按钮** → InteractiveChoiceBox 提交 → 选项框变只读(`submitted_via_option`)
- 路径 2: 用户**自己打字** → ChatInput 提交 → 选项框变"已忽略"(`ignored`)

**为什么允许路径 2 存在**: 模拟自然对话——用户可能看完选项后想补充自己的想法;选项框不会强制消失。

### 4.7 i18n & accessibility

复用 `useModuleI18n("features/chat")`,新增 keys:

| key | 中文 | English |
| --- | --- | --- |
| `interactiveChoice.alreadyChosen` | 已选择 | Chosen |
| `interactiveChoice.alreadyInput` | 已输入 | Custom input |
| `interactiveChoice.ignored` | 已忽略 | Ignored |
| `interactiveChoice.submit` | 提交 | Submit |
| `interactiveChoice.defaultPlaceholder` | 或输入自定义内容... | Or type your own... |

每个按钮带 `aria-label`,内容含 `label` + `description`(若存在)。

### 4.8 Visual style

- 卡片样式,圆角 10px,边框色沿用 `--chat-border`
- 待选态: 浅色主色调背景 (`rgba(var(--v-theme-primary), 0.04)`)
- 已选/已输入态: 整卡灰显(`opacity: 0.6`),顶部加 ✓ 图标(主色)
- 已忽略态: 整卡淡化 + 顶部"已忽略"徽章
- 区别于 `ToolCallCard`(灰色) — 选项框带主色强调,提示"需要用户操作"

---

## 5. Components & Files

### 5.1 New files

| 路径 | 作用 |
| --- | --- |
| `dashboard/src/components/chat/message_list_comps/InteractiveChoiceBox.vue` | 选项框组件 |

### 5.2 Modified files

| 路径 | 修改 |
| --- | --- |
| `dashboard/src/composables/useMessages.ts` | 在 `MessagePart` interface 上扩展 `interactive_choice` 字段(`prompt`/`title`/`options`/`input_placeholder`);`isEmptyPlainPart`/`isThinkingPart` 等 helper 中**不**把 `interactive_choice` 当作"thinking"或"empty" |
| `dashboard/src/components/chat/ChatMessageList.vue` | 加 v-else-if 分支 + `onInteractiveChoiceSubmit` handler |
| `dashboard/src/components/chat/MessageList.vue` | 同步同样的 v-else-if 分支(legacy 路径) |
| `dashboard/src/i18n/locales/features/chat.zh-CN.json` (或对应文件) | 新增 i18n keys |
| `dashboard/src/i18n/locales/features/chat.en-US.json` | 新增 i18n keys |

### 5.3 Tool that produces the format (out of scope for v1, but documented)

AstrBot 可在后续提供一个内置 `ask_user_choice` 工具,接收 `prompt + options` 参数,返回 `InteractiveChoicePart` JSON。v1 仅做前端渲染,工具由调用方(插件 / agent runner)自行实现并以 `Json` 组件输出。

---

## 6. Data flow

```
LLM (agent runner)
  ↓ 调 ask_user_choice 工具
Tool Result: { type: "interactive_choice", prompt: "...", options: [...] }
  ↓ 通过 webchat 平台转成 MessagePart
WebChat Frontend
  ↓ ChatMessageList 路由到 InteractiveChoiceBox
InteractiveChoiceBox (待选态)
  ↓ 用户点按钮 / 提交 textarea
emit('submit', option.value | inputText)
  ↓ ChatMessageList.onInteractiveChoiceSubmit
sendMessage({ text })
  ↓ useMessages.send() → POST /api/chat
Backend LLM
  ↓ 收到普通 user message,从上下文推断这是对上一步提问的回应
下一轮回复
```

---

## 7. Error handling

| 场景 | 处理 |
| --- | --- |
| 后端返回非法 part (缺 `prompt` / `options` 为空 / 长度 < 2) | 前端降级为 `unknown-part`(显示 JSON) |
| `options.length > 10` | 前端只渲染前 10 个,控制台 warn |
| 极端长 `value` / `prompt` | 截断(见 3.2 表) |
| 用户在 `pending` 状态下关闭页面 | 无副作用——选项框是 stateless UI,后端无挂起任务 |
| 同一消息内出现两个 `interactive_choice` part | 两者独立渲染、独立状态(都允许用户操作) |

---

## 8. Testing

### 8.1 Unit tests (Vitest)

- `InteractiveChoiceBox.vue`:
  - 初始渲染包含 `prompt` 和所有 `options`
  - 点按钮 → emit `submit` 且携带正确 `value`
  - textarea 输入 + 点提交 → emit `submit` 且携带输入文本
  - 已提交态下按钮不可点击(`pointer-events: none`)
  - 忽略态下显示"已忽略"徽章
- `useMessages.ts`:
  - `normalizePartsInternal` 不会把 `interactive_choice` 误转为 `plain`/`think`
  - `isEmptyPlainPart` / `isThinkingPart` 对 `interactive_choice` 返回 false

### 8.2 手动验证 (与未来 `ask_user_choice` 工具联调时)

- LLM 输出 → 工具返回 `interactive_choice` → 前端正确渲染
- 点选项 → 后端收到纯文本 user message → LLM 正确理解
- 输入自定义文本 → 同上
- 用户在选项框 `pending` 时自己打字发新消息 → 选项框变"已忽略"

---

## 9. Open questions / future extensions

1. **多选模式** — 当前 v1 不支持,中间格式加 `selection_mode: "single" | "multiple"`
2. **风险等级** — `ChoiceOption.risk_level: "safe" | "warning" | "danger"`,前端给危险项加红框
3. **推荐项标记** — `ChoiceOption.recommended: boolean`,默认选中该按钮
4. **多步骤嵌套** — `ChoiceOption.nested: InteractiveChoicePart`,点 A 后弹出二级选项框
5. **超时** — `expires_at: number`,前端倒计时
6. **非 WebChat 平台** — 把 `InteractiveChoicePart` 降级为纯文本(列出选项 + 提示用户回复数字)

---

## 10. References

- `dashboard/src/components/chat/ChatMessageList.vue` — 现有 v-if/v-else-if 路由链
- `dashboard/src/components/chat/MessageList.vue` — legacy 路径,需同步
- `dashboard/src/composables/useMessages.ts` — `MessagePart` / `messageBlocks` / `normalizePartsInternal`
- `dashboard/src/components/chat/message_list_comps/ToolCallCard.vue` — 视觉风格参考(灰底卡片)
- `astrbot/core/message/components.py` — `BaseMessageComponent` / `Json` 组件
- `astrbot/core/agent/message.py` — LLM tool call 数据结构
