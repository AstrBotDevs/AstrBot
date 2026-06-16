# Dashboard ChatUI「加载项目目录」按钮 — 设计文档

| 项目 | 内容 |
|------|------|
| 主题 | Dashboard ChatUI 联动 spcode 插件的「加载项目目录」按钮 |
| 日期 | 2026-06-16 |
| 作者 | elecvoid243 |
| 状态 | Draft — 待用户审阅（v2：修复 spec 评审指出的实质性问题） |
| 关联插件 | `astrbot_plugin_spcode_toolkit`（路径：`F:\github\astrbot_plugin_spcode_toolkit`） |
| 关联代码 | `dashboard/src/components/chat/*`、`dashboard/src/composables/useMessages.ts`、`astrbot/dashboard/api/extensions.py` |

---

## 1. 背景与目标

### 1.1 现状

AstrBot 的 WebChat 仪表盘（dashboard）已经具备以下相关能力：

- **ChatInput.vue**：底部 `+` 按钮可弹出菜单（已含上传文件、配置切换、流式开关三项）
- **spcode 插件**（`astrbot_plugin_spcode_toolkit`）：通过指令 `/project load <directory>` 一键加载代码工程到当前会话
- **后端 API**：
  - `GET /api/commands`：返回所有已注册指令（含 `plugin` / `effective_command` / `type` / `enabled` 字段）
  - `POST /api/chat`：通用消息发送通道（与手动键入文本完全等价）

### 1.2 痛点

spcode 的 `/project load <directory>` 要求用户**手动键入完整绝对路径**。浏览器沙箱无法让 web 应用拿到任意磁盘的绝对路径，Chrome 的 `showDirectoryPicker` 也只返回文件夹名而非完整路径。因此：

1. ChatUI 中没有引导入口，新手用户难以发现该能力
2. 即使用户知道命令，每次都要手敲完整路径
3. 已用过的合法路径无法复用，需要重新输入或记忆

### 1.3 目标

在 ChatUI 中**新增一个轻量入口**，让用户能：

1. 在 ChatInput 旁的 `+` 菜单里看到「加载项目目录」项（仅当 spcode 的 `project load` 指令可用时显示）
2. 点击后弹出对话框，输入绝对路径并提交，**等价于手动键入 `/project load <path>`**
3. 对话框提供「最近使用」下拉，展示历史合法路径（点击可一键填入）

### 1.4 非目标

- ❌ **不**修改 spcode 插件代码
- ❌ **不**修改 AstrBot 核心（后端、协议、消息总线）
- ❌ **不**实现图形化文件夹树浏览
- ❌ **不**做已加载项目的状态追踪 / 徽章 / 卸载按钮
- ❌ **不**改动现有 Project 体系（`ProjectList` / `ProjectDialog` / `ProjectView`）的数据模型与行为
- ❌ **不**在客户端做路径安全校验（spcode 内部已用 `_is_path_safe`）
- ❌ **不**写 Vitest 单元测试（dashboard 尚未配置 vitest；用 `pnpm typecheck` + `pnpm lint` + 手动验证）

---

## 2. 设计决策（已与用户确认）

| # | 决策点 | 选择 | 理由 |
|---|--------|------|------|
| 1 | 按钮放置位置 | **C**：ChatInput 内 `+` 菜单的新条目 | 与现有元操作（上传/配置/流式）同级，不破坏侧边栏简洁度 |
| 2 | 加载后菜单项行为 | **A**：始终显示同一项 | 不做状态追踪（无后端状态查询 API）；spcode 已拦截重复 load |
| 3 | 路径历史存储 | **A**：localStorage（key=`chatui.spcode.projectPathHistory`，容量 10） | 跨设备无意义（路径指向本地）；与 `TODO_BAR_POS_KEY` 模式一致；隐私模式 `try/catch` 兜底 |
| 4 | 路径何时记入历史 | **A**：提交时即记入 | KISS 原则；用户输入本身就是合法意图；区分成功/失败需观察 SSE 流，与"零状态追踪"设计冲突 |
| 5 | 用户确认后如何执行 | **A**：复用现有 `sendCurrentMessage` 流程（`draft` 赋值 + emit `send`） | 自动继承 session 创建 / 流式传输 / 中断等所有现有行为；不引入新的发送路径 |
| 6 | 代码组织 | **B**：抽成独立组件；纯函数 helpers 内联到组件文件（不开 composable） | 关注点分离；helpers 仅 1 处使用，遵循 AGENTS.md「inline-first」 |

---

## 3. 架构与文件改动

### 3.1 架构原则

- **零后端改动**：完全复用 `/api/chat`、`/api/commands` 现有 endpoint
- **零 spcode 改动**：通过 `/project load <path>` 标准消息触发
- **零新依赖**：仅用 Vue 3 Composition API + Vuetify 现有组件
- **零现有组件破坏**：所有改动收敛在 1 个新组件 + 1 个现有组件（ChatInput）小幅接入 + i18n key
- **Inline-first**：helpers 直接写在组件文件顶部，不开新 composable

### 3.2 文件改动清单

| 层级 | 文件 | 性质 | 说明 |
|------|------|------|------|
| 新增 | `dashboard/src/components/chat/ProjectLoadMenuItem.vue` | 新组件 | 菜单条目 + 路径输入对话框（v-dialog）；组件内联 4 个纯函数 helpers |
| 改动 | `dashboard/src/components/chat/ChatInput.vue` | 修改 | 接入新组件；复用现有 `allCommands` / `wakePrefixes` 状态 |
| 改动 | `dashboard/src/i18n/locales/zh-CN/features/chat.json` | 修改 | 新增 i18n key |
| 改动 | `dashboard/src/i18n/locales/en-US/features/chat.json` | 修改 | 新增 i18n key |
| 改动 | `dashboard/src/i18n/locales/ru-RU/features/chat.json` | 修改 | 新增 i18n key |
| **后端** | **无任何改动** | ✅ | — |
| **spcode** | **无任何改动** | ✅ | — |
| **Chat.vue** | **无任何改动** | ✅ | 完全复用 `sendCurrentMessage`，无需新增事件 |
| **useMessages.ts** | **无任何改动** | ✅ | — |

### 3.3 改动量估算

- 新增代码：~250 行（`ProjectLoadMenuItem.vue`，含 4 个 inline helpers + dialog UI）
- 改动现有代码：~10 行（ChatInput 加 1 个 import + 1 个 menu item 条件渲染）
- 风险面：仅前端 1 个新组件，零破坏性改动

---

## 4. 组件结构

### 4.1 ChatInput 内部新增部分（伪代码）

在 `+` 菜单（`StyledMenu`）内，于「上传文件」与 `<ConfigSelector />` 之间插入：

```vue
<StyledMenu activator="+">
  <!-- 现有：上传文件 -->
  <v-list-item @click="triggerImageInput">...</v-list-item>

  <!-- 新增：spcode 项目加载（条件渲染）
       ProjectLoadMenuItem 内部用 <v-list-item> 渲染菜单条目:
         prepend icon = mdi-folder-open-outline
         title       = tm("spcodeProjectLoad.menuItem")
       与上方"上传文件"项的 <v-list-item class="styled-menu-item" rounded="md" @click="...">
       风格保持一致；icon 选用 open 状态以暗示"打开一个目录"而非新建。 -->
  <ProjectLoadMenuItem
    v-if="isProjectLoadAvailable(allCommands)"
    :commands="allCommands"
    :wake-prefixes="wakePrefixes"
    @submit="handleProjectLoadSubmit"
  />

  <!-- 现有：ConfigSelector + StreamingToggle -->
  <ConfigSelector ... />
  <v-list-item @click="$emit('toggleStreaming')">...</v-list-item>
</StyledMenu>
```

`handleProjectLoadSubmit(text: string)` 在 ChatInput 内部：

```typescript
function handleProjectLoadSubmit(text: string) {
  // 1) 复用现有 send 流程: 把命令填入 draft, 触发 send
  //    同步执行, Vue 3 v-model:prompt 在同一 tick 内更新父组件 draft
  localPrompt.value = text;     // 同步触发 update:prompt 事件 → Chat.vue 更新 draft
  emit("send");                  // 触发 Chat.vue 的 sendCurrentMessage
}
```

**关键事实**（已与代码核对）：
- `localPrompt` 的 setter 是同步的，立即触发 `update:prompt` 上抛
- Chat.vue 通过 `v-model:prompt="draft"` 接收，`draft.value` 同步更新
- 之后 emit `send` 时，`sendCurrentMessage` 内部读 `draft.value` 已是新值
- **sessionId 不存在时**，`sendCurrentMessage` 内部自动 `await newSession()`（`Chat.vue:1227`）
- 整个流程不需要在 `ProjectLoadMenuItem` 内部关心 `sendMessageStream` 的具体签名

### 4.2 ProjectLoadMenuItem 接口

```typescript
// ProjectLoadMenuItem.vue
interface Props {
  commands: CommandItem[];       // 来自 ChatInput.allCommands
  wakePrefixes: string[];        // 来自 ChatInput.wakePrefixes
}
interface Emits {
  submit: [text: string];        // 提交完整命令文本（已含 wake prefix + 路径）
}

// 键盘 UX: v-dialog 内包一个 <v-form @submit.prevent="onConfirm">，
// 包裹 path <v-text-field>。这样用户在输入框中按 Enter 时会触发表单 submit
// （即"加载"按钮的点击），而不是被 v-dialog 默认行为吞掉或提交 native form 刷新页面。
// 取消按钮或 ESC 键由 v-dialog 内置处理（关闭对话框，不触发 submit）。
```

### 4.3 Inline helpers（组件文件顶部，private，不导出）

```typescript
// 在 ProjectLoadMenuItem.vue <script setup> 顶部

const HISTORY_KEY = "chatui.spcode.projectPathHistory";
const HISTORY_CAP = 10;
const RECENT_DROPDOWN_COUNT = 5;
const SPCODE_PLUGIN = "astrbot_plugin_spcode_toolkit";  // 来自 metadata.yaml: name

function isProjectLoadAvailable(commands: Array<{
  plugin?: string;
  effective_command?: string;
  type?: string;
  enabled?: boolean;
}>): boolean {
  return commands.some(cmd =>
    cmd.enabled
    && cmd.plugin === SPCODE_PLUGIN
    && cmd.effective_command === "project load"
    && cmd.type === "sub_command"  // 防御性: 与 spcode 的 command_group("project").command("load") 对应
  );
}

function getPathHistory(): string[] {
  try {
    const raw = localStorage.getItem(HISTORY_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter((p): p is string => typeof p === "string") : [];
  } catch {
    return [];  // 隐私模式 / 损坏数据兜底
  }
}

function addToPathHistory(path: string): void {
  const trimmed = path.trim();
  if (!trimmed) return;
  const current = getPathHistory();
  // 去重(同 path 不重复),最新在前,截断到 HISTORY_CAP
  const deduped = [trimmed, ...current.filter(p => p !== trimmed)].slice(0, HISTORY_CAP);
  try {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(deduped));
  } catch {
    // 写入失败(quota 等)静默
  }
}

function buildLoadCommand(wakePrefix: string, path: string): string {
  // 防御性 fallback: wakePrefixes 未来若被清空,仍使用 "/" 而非拼出 "undefinedproject load ..."
  const prefix = wakePrefix || "/";
  // spcode 的 strip_surrounding_quotes 会处理首尾成对引号
  // 客户端不做自动引号包裹(避免和 spcode 内部行为分叉)
  // 含空格的路径由用户自行加引号
  return `${prefix}project load ${path.trim()}`;
}
```

---

## 5. 关键交互时序

### 5.1 首次进入 ChatInput（spcode 激活）

```
ChatInput mount
  → fetchCommands() → allCommands.value = [...]  (含 spcode 的 project load 子命令)
  → isProjectLoadAvailable(allCommands) = true
  → ProjectLoadMenuItem 渲染 ✅
```

### 5.2 用户提交路径

```
用户点击 [+] → [📁 加载项目目录]
  → ProjectLoadMenuItem 内部 openDialog()
  → getPathHistory() → 历史数组（取前 RECENT_DROPDOWN_COUNT=5 条显示于下拉）
  → 用户在文本框输入 "/new/proj"（或从下拉选一项）并点"确认"
  → addToPathHistory('/new/proj')   // 即时记入
  → buildLoadCommand('/', '/new/proj') → '/project load /new/proj'
  → emit('submit', '/project load /new/proj')
  → ChatInput.handleProjectLoadSubmit(text)
  → localPrompt.value = text   →  update:prompt emit  →  Chat.vue draft.value = text
  → emit('send')
  → Chat.vue.sendCurrentMessage()
      → sessionId 不存在时 await newSession()
      → outgoingParts = [{ type: 'plain', text: '/project load /new/proj' }]
      → sendMessageStream({ sessionId, messageId, parts, transport, ... })
  → 聊天流出现用户消息: "/project load /new/proj"
  → spcode 流式回显 3 步进度
```

### 5.3 spcode 被禁用

```
用户禁用 spcode 插件
  → 下次 fetchCommands() 后 allCommands 中无 project load
  → isProjectLoadAvailable = false
  → ProjectLoadMenuItem 不渲染 ✅
```

### 5.4 流式响应中用户提交

| 子场景 | 行为 |
|--------|------|
| 按钮可点 | 用户可在 streaming 中点 [+] → [加载项目目录]（按钮未受 `disabled` 状态控制） |
| 对话框打开 | v-dialog 正常显示 |
| 提交 | `sendCurrentMessage` 不检查 `isRunning`；新 user message 追加，**spcode handler 自行处理并发**（per-umo 状态由 spcode 内部维护） |
| 视觉 | 用户消息和 bot 响应同时出现在聊天流中（与手动键入行为完全一致） |

> **注**：`sendCurrentMessage` 不拦截并发是**有意为之**——它与"手动键入"路径完全相同，不应在 [+] 菜单引入新行为。

### 5.5 错误处理

| 场景 | 处理 |
|------|------|
| 路径为空 | 提交按钮 `:disabled="!path.trim()"` |
| 路径含前后空格 | `addToPathHistory` / `buildLoadCommand` 入口 `trim()` |
| 路径不存在/不安全 | spcode 内部 `_is_path_safe` 拦截；UI 层不处理，spcode 会以聊天消息返回错误 |
| localStorage 不可用 | `try/catch` 静默降级：历史下拉为空，但提交仍可用 |
| 用户在 welcome 状态（首条消息） | `sendCurrentMessage` 自动 `await newSession()`；首条消息即是命令，正常进入聊天流 |
| 用户切换 wake_prefix 配置后 | 后续命令使用新前缀；历史/对话框无影响 |
| 用户切换 wake_prefix 配置后**立即**点击加载 | `wakePrefixes` 由 `fetchCommands()` 同步更新，下一次 `isProjectLoadAvailable` / `buildLoadCommand` 用新值 |

### 5.6 安全边界

- **不读取/不上传**任何文件内容，仅发送文本命令
- **不重复**做路径安全校验（避免与 spcode 内部 `_is_path_safe` 行为分叉）
- localStorage 内容**只**用于前端建议，不参与安全决策

---

## 6. 国际化

新增 i18n key（zh-CN / en-US / ru-RU 三份文件）：

```jsonc
"spcodeProjectLoad": {
  "menuItem": "加载项目目录",                 // en-US: "Load Project Directory"
  "dialog": {
    "title": "加载项目目录",                  // en-US: "Load Project Directory"
    "pathLabel": "项目路径",                  // en-US: "Project Path"
    "pathPlaceholder": "例如 /Users/me/projects/my-app",  // en-US: "e.g. /Users/me/projects/my-app"
    "pathHint": "提示：含空格的路径请用英文双引号包裹",  // en-US: "Hint: wrap paths with spaces in double quotes"
    "historyLabel": "最近使用",               // en-US: "Recent"
    "historyEmpty": "暂无历史路径",            // en-US: "No history"
    "submit": "加载",                         // en-US: "Load"
    "cancel": "取消"                          // en-US: "Cancel"
  }
}
```

> **i18n key 命名决策**：保留 `spcodeProjectLoad`（plugin-machine-name 风格）。理由：(1) 显式表明与 spcode 插件的耦合，未来改名时 grep 友好；(2) 与 `commandSuggestion` / `project` / `todo` 等现有命名风格不冲突。

---

## 7. 验证方案

### 7.1 静态校验

```bash
cd dashboard
pnpm typecheck
pnpm lint
```

### 7.2 手动验证 checklist

- [ ] spcode 启用时，`+` 菜单出现「加载项目目录」
- [ ] spcode 禁用时，该菜单项消失
- [ ] 点击菜单项，对话框打开，路径输入框为空
- [ ] 历史下拉显示已有历史（最多 5 条）
- [ ] 点击历史项，输入框自动填充
- [ ] 输入空路径时，提交按钮 disabled
- [ ] 输入合法路径并提交，对话框关闭，聊天流出现 `/project load <path>` 用户消息
- [ ] spcode 成功回显（3 步进度 + ✅ 加载成功）
- [ ] 再次打开对话框，新提交的路径出现在历史下拉顶部
- [ ] 历史超过 10 条时，旧的被丢弃
- [ ] localStorage 中存在 `chatui.spcode.projectPathHistory` 键
- [ ] 隐私模式下打开（localStorage 抛错），提交仍可用，历史下拉为空
- [ ] 切换 wake_prefix 配置后，提交的命令使用新前缀
- [ ] 切换到俄语 / 英语后，菜单项和对话框文案正确
- [ ] **流式响应中点 [+] → [加载项目目录] → 提交**：新 user message 正常追加，与手动键入行为一致
- [ ] **无任何会话时（welcome 状态）点提交**：自动 newSession，首条消息正常发出
- [ ] 现有 ChatInput 的所有功能（文件上传、配置切换、流式开关、消息发送）不受影响
- [ ] 现有 ProjectList / ProjectDialog / ProjectView 行为不变

### 7.3 回归

- 现有所有 chat 组件渲染、命令提示、消息流不受影响
- 现有 ProjectList / ProjectDialog / ProjectView 行为不变
- 路径历史是新增 localStorage key，不影响任何已有 key

---

## 8. 风险与缓解

| 风险 | 严重度 | 缓解措施 |
|------|--------|----------|
| 浏览器沙箱无法取得绝对路径 | 中 | 已规避：纯文本输入，不依赖 `showDirectoryPicker` |
| 用户输入了 `_is_path_safe` 不允许的目录 | 低 | spcode 返回明确错误消息，UI 层不更新任何状态 |
| 多个 dashboard tab 各自维护 | 低 | 各 tab 独立读 localStorage；后端真实状态以 spcode 为准；无需协调 |
| spcode 改名后菜单项消失 | 低 | 与现有"命令被禁用"行为一致；用户可在 spcode 配置中恢复 |
| localStorage 数据损坏 | 低 | `try/catch` + `Array.isArray` + 类型守卫 |
| `wakePrefixes` 多值场景（未来） | 低 | 当前用 `wakePrefixes[0]` + `|| "/"` 兜底；若多值场景出现，可扩展为「按顺序尝试」策略 |
| **共享浏览器场景**：多用户共用同一台机器浏览 dashboard 时，路径历史在 localStorage 是共享的（不过 history 只在当前用户设备上持久化时才有意义） | 低（v1 接受） | v1 不做 user-scoped 命名空间；如未来多人共用浏览器成为问题，再按 `getStoredDashboardUsername()` 模式加命名空间 |
| 流式响应中点提交 | 低 | spcode per-umo 状态由 spcode 内部维护；前端不拦截并发，与手动键入行为完全一致 |

---

## 9. 实施后续

1. 通过 spec 评审（本文档）
2. 调用 `writing-plans` skill 制定详细实施计划
3. 按计划实现 → `pnpm typecheck` + `pnpm lint` → 手动验证 checklist → 提 PR

---

## 附录 A：相关代码位置速查

- ChatInput.vue：`dashboard/src/components/chat/ChatInput.vue`（`+` 菜单在第 178-217 行附近；`localPrompt` computed 在 524-527 行附近）
- Chat.vue：`dashboard/src/components/chat/Chat.vue`（`sendCurrentMessage` 在 1218-1275 行；`newSession` 在 633 行导入）
- `useMessages.sendMessageStream`：`dashboard/src/composables/useMessages.ts:331-371`（signature: `{ sessionId, messageId, parts, transport, ... }`）
- `useMessages.MessagePart`：`dashboard/src/composables/useMessages.ts:7-30`（`{ type, text?, ... }`）
- spcode `/project load` 实现：`F:\github\astrbot_plugin_spcode_toolkit\main.py:1099-1178`
- spcode `metadata.yaml`：`F:\github\astrbot_plugin_spcode_toolkit\metadata.yaml:1`（`name: astrbot_plugin_spcode_toolkit`）
- `commandApi.list()`：`dashboard/src/api/v1.ts:894-903` + 后端 `astrbot/dashboard/api/extensions.py:89-95`
- `CommandItem` 类型：`dashboard/src/components/extension/componentPanel/types.ts`（`plugin` / `effective_command` / `type` / `enabled` 字段）

---

*本文档由 brainstorming skill 协作生成，作者 elecvoid243，2026-06-16。*
