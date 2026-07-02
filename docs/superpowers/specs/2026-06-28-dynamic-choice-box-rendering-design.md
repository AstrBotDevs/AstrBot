# Dynamic Choice Box Rendering — Design Spec

> ⚠️ **DEPRECATED (2026-07-02)**: This spec describes v0.3 软阻塞式实现,已被 v1.0 真阻塞式替代。v1.0 spec 见 `2026-07-02-blocking-interactive-choice-design.md`。本文档保留作为历史记录,不再代表当前实现。

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
- **后端**：本期不增加新的 `MessageComponent`——工具 result 走 framework 默认的 `Plain` 包装(见 §6 数据流)。
- **翻译位置（明确）**：在 `dashboard/src/composables/useMessages.ts` 的 `normalizePartsInternal` 中**新增 type 翻译**，分两步：
  1. **解包**：如果 part 的 `type === "plain"` 且 `text` 字符串以 `"{"` 开头**且** `JSON.parse(text)` 成功且解析结果含 `type === "interactive_choice"`，**用解析后的对象替换原 part**（不保留外层 plain 包装）。否则保留原 plain 文本继续走默认渲染。
  2. **字段校验**：解包后（或原 part 本身就是 `interactive_choice`）按 §3.2 规则校验 `prompt` / `options` / `id` 等字段。合法则**透传**（不动字段），非法则**降级为 unknown-part**。
- **来源说明**：解包步骤是 `AskUserChoiceTool`（见 §11）返回 JSON 字符串后被 framework 默认 `Plain` 包装导致的——解包是它的反向操作。这是 v1 唯一需要的后端→前端翻译点。
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
| `options` | ✓ | 2 ~ 10 个 | 少于 2 / 非数组 / 任意元素缺 `id` 或 `label` 或 `value` → 降级为 unknown-part |
| `options[].id` | ✓ | — | 必填,前端用作 :key;**id 重复或为空字符串时也降级为 unknown-part**(避免 Vue :key 冲突) |
| `options[].label` | ✓ | 30 字 | 前端截断 |
| `options[].description` | ✗ | 200 字 | 前端截断 |
| `options[].value` | ✓ | 不限 | 不截断(交给 LLM 读) |
| `input_placeholder` | ✗ | 60 字 | 前端截断;空时使用默认 "或输入自定义内容..." |

> **关于截断的重复约束**：工具层 (§11.2 #4) 也会对 `description` / `input_placeholder` 截断以节省 token,前端截断是**防御性兜底**(应对非 `ask_user_choice` 来源的 part)。两层不冲突: 工具层先截,前端再截不会恢复原文。

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
  /** 父组件判定:本选项框之后是否出现了新 user message(即"被绕过") */
  isIgnored?: boolean;
}>();

const emit = defineEmits<{
  submit: [text: string];  // 用户提交后向上抛"将要发往 LLM 的文本"
}>();
```

**组件内部只管理一个状态**:`submittedValue: string | null`
- `null` → 渲染"待选" UI
- 非空 → 渲染"已选择/已输入"只读态
- `isIgnored === true` → 强制渲染"已忽略"只读态(覆盖 submittedValue)

**ignored 信号协议（明确）**：
- 父组件 `ChatMessageList.vue` 在 `renderBlocks(msg)` 渲染时，对每个 `interactive_choice` part 计算一个 `isIgnored` 布尔值
- 计算规则:在 `messages` 数组中,**当前 msg 之后** 是否存在 `type === "user"` 的 `ChatRecord`
- 如果 `isIgnored === true` 且组件当前为 `pending` 态 → 渲染"已忽略"标签
- 如果 `isIgnored === true` 且组件已经 submitted → 保持 submitted 视觉(用户已选择胜过"被忽略")

> 父组件的"之后存在 user message"判断基于消息数组顺序,不需要额外的 store / event bus。这是 v1 唯一的状态传递通道。

### 4.3 Layout

**待选态 (`pending`)**:
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

**已选态 (`submitted_via_option`)**:
```
┌────────────────────────────────────┐(opacity 0.6)
│ ✓ 已选择: {label}                  │
│   prompt 文案(淡显)               │
└────────────────────────────────────┘
```

**已输入态 (`submitted_via_input`)**:
```
┌────────────────────────────────────┐(opacity 0.6)
│ ✓ 已输入: {text}                   │
│   prompt 文案(淡显)               │
└────────────────────────────────────┘
```

**已忽略态 (`ignored`)**:
```
┌────────────────────────────────────┐(淡化,无 opacity)
│ — 已忽略                           │
│   prompt 文案(淡显)               │
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
function onInteractiveChoiceSubmit(text: string) {
  // 走标准 user message 通道 — 不带任何隐藏标记
  sendMessage({ text });
}
```

**关键点**: 纯文本回传在代码里的具体实现就是把 `option.value` / 用户输入文本塞进 `sendChatMessage` 的 `message` 字段。LLM 仅凭上下文(刚问过问题)推断这是对工具调用的回应。

### 4.6 与 ChatInput 的协作

选项框存在期间,`ChatInput` 仍可用——用户在 textarea 打字并按 Enter 会走标准 send 路径,**不经过 InteractiveChoiceBox**。

这意味着两条提交路径并存:
- 路径 1: 用户**点按钮或提交 InteractiveChoiceBox 内的 textarea** → `InteractiveChoiceBox` 触发 `submit` 事件 → 选项框变只读(`submitted_via_option` 或 `submitted_via_input`)
- 路径 2: 用户**在 ChatInput 自己打字** → `ChatInput` 触发标准 send → 父组件检测到"本选项框之后出现新 user message" → 通过 `isIgnored` prop 把选项框切到"已忽略"态

**半输入态的处置（明确）**: 如果用户在 `InteractiveChoiceBox` 的 textarea 打了字但**未点提交**就跑去 `ChatInput` 发消息——那段半输入文本**静默丢弃,不弹确认**。理由:选项框是 stateless UI,半输入文本对 LLM 无意义,弹确认会增加用户认知负担。如果未来需要,会改用 `beforeunload` + 显式确认,本期不做。

**为什么允许路径 2 存在**: 模拟自然对话——用户可能看完选项后想补充自己的想法;选项框不会强制消失,而是自然进入"已忽略"态。

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

**A11y 细节（明确）**:
- `pending` 态: 按钮 `aria-disabled="false"`,可 Tab 聚焦
- `submitted_*` 态: 按钮加 `aria-disabled="true"` + `tabindex="-1"`,Tab 键跳过;但 `aria-label` 仍可被屏幕阅读器朗读("已选择: {label}")
- `ignored` 态: 整卡片加 `aria-live="polite"` 公告"选项已被忽略"

**XSS / 转义（明确）**:
- 所有用户可见文本(`prompt` / `title` / `label` / `description` / `value`)在 Vue 模板中用默认 `{{ }}` 插值,Vue 自动转义 HTML
- **禁用 `v-html`**: 即使 description 想支持 markdown,本期也只展示纯文本
- 用户输入文本在 `submitted_via_input` 态显示时同样走 `{{ }}`,不解析为 HTML
- 未来如需支持 markdown description,会单独 spec,使用 v-text + 单独的 markdown sanitizer

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
| `dashboard/src/components/chat/ChatMessageList.vue` | 加 v-else-if 分支 + `onInteractiveChoiceSubmit` handler + `isIgnored` 计算 |
| `dashboard/src/components/chat/MessageList.vue` | **不修改**——该组件为 deprecated legacy 路径(`MessageListDEPRECATED.vue` 提示),其维护已冻结;v1 仅在 `ChatMessageList.vue` 实现 |
| `dashboard/src/i18n/locales/features/chat.zh-CN.json` (或对应文件) | 新增 i18n keys |
| `dashboard/src/i18n/locales/features/chat.en-US.json` | 新增 i18n keys |

### 5.3 New plugin (separate repo)

| 路径 | 作用 |
| --- | --- |
| `astrbot_plugin_choice_ui/choice_tool.py` | `AskUserChoiceTool(FunctionTool)` 定义 — 详见 §11 |
| `astrbot_plugin_choice_ui/main.py` | 插件入口,`self.context.add_llm_tool(AskUserChoiceTool())` 一行注册 |
| `astrbot_plugin_choice_ui/metadata.yaml` | 插件元数据(name/display_name/version/astrbot_version) |
| `astrbot_plugin_choice_ui/README.md` | 安装说明 + LLM 提示("如何在 prompt 里让 LLM 知道这个工具") |

### 5.4 Tool: `ask_user_choice` (独立插件, spec 见 §11)

AstrBot v1 不内置该工具;它以**独立插件**形式提供(`astrbot_plugin_choice_ui`),插件仓库维护者实现 `AskUserChoiceTool(FunctionTool)` 并通过 `self.context.add_llm_tool(...)` 注册。详见 §11 工具定义。

---

## 6. Data flow

```
LLM (agent runner)
  ↓ 调 ask_user_choice 工具
Tool Result (from `ask_user_choice`): JSON 字符串,形如 `{"type":"interactive_choice", ...}`
  ↓ framework 默认 Plain 包装成 MessagePart
MessagePart: { type: "plain", text: '{"type":"interactive_choice", ...}' }
  ↓ 通过 webchat 通道到达 `useMessages.normalizePartsInternal`
  ↓ 步骤 1 解包: 检测 `text` 以 "{" 开头 → JSON.parse → 替换 part
  ↓ 步骤 2 校验: 按 §3.2 规则 → 透传(合法) / 降级为 unknown-part(非法)
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
| 同一消息内出现两个 `interactive_choice` part | 两者**独立**渲染、独立状态(每个 part 都是一个 `<InteractiveChoiceBox>` 实例,各自管理 `submittedValue`);LLM 一次调用工具不应产生两个 part,这是异常路径但前端需正确处理 |
| 同一会话内出现多个 `interactive_choice` (跨消息) | 每条 bot message 独立判断 `isIgnored`;新消息中的选项框独立 `pending`,**不**继承上一条的 `submittedValue` |
| 工具返回的 JSON `JSON.parse` 失败(版本不兼容 / schema 漂移) | 解包步骤 1 中 `JSON.parse` 抛异常 → **保留原 plain 文本继续渲染**(不降级为 unknown-part,避免误把"半合法"文本吃掉);控制台 warn 提示前端检测到 `interactive_choice` 但 JSON 解析失败 |

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

### 8.2 测试 fixture（明确）

```ts
// 输入:工具返回的 JSON 字符串(经 framework Plain 包装后到达前端,见 §6)
const fixtureInput = {
  type: "interactive_choice",
  prompt: "请选择下一步使用的模型",
  title: "模型选择",
  options: [
    { id: "a", label: "GPT-4", description: "更强但更慢", value: "gpt-4" },
    { id: "b", label: "GPT-4 mini", value: "gpt-4-mini" },
    { id: "c", label: "本地模型", value: "local" },
  ],
  input_placeholder: "或输入自定义模型名",
};

// 期望输出:normalizePartsInternal 透传该对象,不做字段变换
const expectedOutput = { ...fixtureInput };

// 非法 fixture (降级为 unknown-part)
const invalidInput = {
  type: "interactive_choice",
  prompt: "请选择",          // 缺 options
};
// expectedOutput -> { type: "plain", text: JSON.stringify(invalidInput) }
```

### 8.3 手动验证 (与未来 `ask_user_choice` 工具联调时)

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
- `dashboard/src/components/chat/MessageList.vue` — legacy/deprecated 路径,v1 不修改(与 §5.2 一致)
- `dashboard/src/composables/useMessages.ts` — `MessagePart` / `messageBlocks` / `normalizePartsInternal`
- `dashboard/src/components/chat/message_list_comps/ToolCallCard.vue` — 视觉风格参考(灰底卡片)
- `astrbot/core/message/components.py` — `BaseMessageComponent` / `Json` 组件
- `astrbot/core/agent/message.py` — LLM tool call 数据结构
- `astrbot/api/__init__.py` — `FunctionTool` 基类(插件作者继承)

---

## 11. Appendix — `AskUserChoiceTool` 完整定义

> 独立插件 `astrbot_plugin_choice_ui` 的核心实现。本 spec 不定义插件脚手架,只定义工具类。

### 11.1 工具类

```python
"""astrbot_plugin_choice_ui/choice_tool.py

ask_user_choice 工具:让 LLM 在需要人类审批时输出结构化选项框。
返回 JSON 字符串,由前端 useMessages.normalizePartsInternal 透传/降级。
"""

from __future__ import annotations

import json
from typing import Any

from astrbot.api import FunctionTool


class AskUserChoiceTool(FunctionTool):
    """Ask the user to choose one of N options (with optional free text).

    When to use: 你即将执行一个不可逆/敏感/代价高的操作,
    或者你需要在多个候选方案中让用户拍板。

    Returns: JSON 字符串,结构与前端 InteractiveChoicePart 一一对应
    (见 §3.1)。
    """

    name = "ask_user_choice"
    description = (
        "向用户呈现一个可交互的选项框,用户点击其中某个选项(或输入自定义文本) "
        "后,选择结果会作为下一轮 user message 返回给你。"
        "适用场景:1) 需要用户对敏感/不可逆操作授权;2) 在多个候选方案中让用户拍板。"
        "选项不少于 2 个、不多于 10 个;用户可以无视预设选项直接输入自定义文本。"
    )

    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "提问文案,显示在选项框顶部,例如: '请选择下一步使用的模型:'",
            },
            "options": {
                "type": "array",
                "minItems": 2,
                "maxItems": 10,
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {
                            "type": "string",
                            "description": "选项的唯一 ID,仅供前端 key 使用,不会发给 LLM",
                        },
                        "label": {
                            "type": "string",
                            "description": "按钮上显示的文字(面向用户)",
                        },
                        "description": {
                            "type": "string",
                            "description": "选项的补充说明,hover 展开,面向用户",
                        },
                        "value": {
                            "type": "string",
                            "description": "选中后回传给 LLM 的文本(面向 LLM)",
                        },
                    },
                    "required": ["id", "label", "value"],
                },
                "description": "2-10 个候选选项,单选",
            },
            "title": {
                "type": "string",
                "description": "可选的选项框标题,例如: '模型选择' / '操作确认'",
            },
            "input_placeholder": {
                "type": "string",
                "description": "自由输入框的占位符,例如: '或输入你想用的模型名...'",
            },
        },
        "required": ["prompt", "options"],
    }

    async def call(
        self,
        context,  # AstrBot Context,保留以便未来扩展(persona / 权限检查等)
        **kwargs: Any,
    ) -> str:
        prompt: str = (kwargs.get("prompt") or "").strip()
        options: list[dict[str, Any]] = kwargs.get("options") or []
        title: str | None = kwargs.get("title")
        input_placeholder: str | None = kwargs.get("input_placeholder")

        # ① 软错误:参数不合法 → 返回"错误:..."纯文本,
        #    让 LLM 看到错误信息并自行重试,避免工具异常打断整条链路
        if not prompt:
            return "错误:prompt 必填且不能为空。"
        if not isinstance(options, list) or not (2 <= len(options) <= 10):
            return "错误:options 必须是包含 2-10 个元素的数组。"

        # ② 逐项校验 option;遇到不合法项直接报错误(整体拒绝,不走部分)
        normalized_options: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for idx, opt in enumerate(options):
            if not isinstance(opt, dict):
                return f"错误:options[{idx}] 不是 object。"
            oid = str(opt.get("id") or "").strip()
            label = str(opt.get("label") or "").strip()
            value = opt.get("value")
            if not oid or not label or value is None:
                return f"错误:options[{idx}] 缺 id/label/value。"
            if oid in seen_ids:
                return f"错误:options 中存在重复的 id: {oid!r}。"
            seen_ids.add(oid)
            normalized_options.append(
                {
                    "id": oid,
                    "label": label[:30],  # 截断,见 §3.2
                    # 修正:`opt.get(key, default)` 只在 key 缺失时用 default;
                    # 当 LLM 显式传 `null` 时会回 None,然后 str(None)="None"。
                    # 这里改用 `or ""` 让 None/空字符串都归一为 ""。
                    "description": (
                        (opt.get("description") or "")[:200] or None
                    ),
                    "value": str(value),
                }
            )

        # ③ 构造 InteractiveChoicePart;None 字段清理掉
        payload: dict[str, Any] = {
            "type": "interactive_choice",
            "prompt": prompt[:200],
            "options": normalized_options,
        }
        if title and title.strip():
            payload["title"] = title.strip()[:30]
        if input_placeholder and input_placeholder.strip():
            payload["input_placeholder"] = input_placeholder.strip()[:60]

        # ④ 返回 JSON 字符串 — framework 走默认 Plain 包装,
        #    前端 normalizePartsInternal 检测 "{" 开头 + type 字段后展平
        return json.dumps(payload, ensure_ascii=False)


# ── 注册方式(插件 main.py 示意,仅 1 行) ────────────────────────
# from .choice_tool import AskUserChoiceTool
# self.context.add_llm_tool(AskUserChoiceTool())
```

### 11.2 设计决策(可推翻)

1. **`context` 参数保留**(v1 不用)— 未来可基于 persona 决定是否提供该工具
2. **校验失败返回"错误:..."字符串**而不抛异常 — 工具异常会让 LLM 上下文丢失错误现场,软错误让 LLM 自己重试
3. **option 重复 id 直接拒绝整次调用**,不做去重 — 避免 LLM 误以为"重复就覆盖"
4. **description / input_placeholder 在工具层就截断**,而不是留给前端 — 减少 tool result 体积,省 token
5. **`title` 可选,空时不输出该字段**(避免 `title: null` 污染 JSON)
6. **不做"是否必选"语义** — spec 已明确:用户永远可以无视选项框自己打字

### 11.3 与 spec 其他章节的对应

| 工具约束 | spec 章节 |
| --- | --- |
| `prompt` 必填,200 字截断 | §3.2 字段约束 |
| `options` 2-10 个,每项必填 id/label/value | §3.2 字段约束 |
| `id` 重复时拒绝 | §3.2 + §7 错误处理 |
| `title` 可选,30 字截断 | §3.2 字段约束 |
| `input_placeholder` 可选,60 字截断 | §3.2 字段约束 |
| 返回 JSON 字符串,framework 走 Plain 包装 | §2.3 + §6 数据流 |
| 前端 `normalizePartsInternal` 展平 | §2.3 翻译位置 |
