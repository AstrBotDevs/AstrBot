# Dashboard ChatUI 联动 spcode 插件的"选择文件夹"按钮 — 设计文档

| 项目 | 内容 |
|------|------|
| 主题 | Dashboard ChatUI 联动 spcode 插件的"选择文件夹"按钮 |
| 日期 | 2026-06-14 |
| 作者 | elecvoid243 |
| 状态 | Draft — 待用户审阅 |
| 关联插件 | `astrbot_plugin_spcode_toolkit`（路径：`F:\github\astrbot_plugin_spcode_toolkit`） |
| 关联代码 | `dashboard/src/components/chat/*`、`astrbot/dashboard/routes/{chat,command}.py` |

---

## 1. 背景与目标

### 1.1 现状

AstrBot 的 WebChat 仪表盘（dashboard）已经具备以下相关能力：

- **ChatInput.vue**：底部 `+` 按钮可弹出菜单（已含上传文件、配置切换、流式开关三项）
- **Project 体系**（`ProjectList` / `ProjectDialog` / `ProjectView`）：位于**左侧侧边栏**，仅承载"项目"这个**纯元数据**概念（`title` / `emoji` / `description`），**不绑定磁盘路径**
- **spcode 插件**（`astrbot_plugin_spcode_toolkit`）：通过指令 `/project load <directory>` 实现"一键加载代码工程到当前会话"，联动 agentsmd + codegraph 索引
- **后端 API**：
  - `GET /api/commands`：返回所有已注册指令（含 `plugin_name` / `effective_command` / `enabled` 字段）
  - `POST /api/chat`：通用消息发送通道（与手动键入文本完全等价）

### 1.2 痛点

spcode 的 `/project load <directory>` 要求用户**手动键入完整绝对路径**。在 ChatUI 中没有引导入口，新手用户难以发现该能力。

### 1.3 目标

在 ChatUI 中**新增一个轻量入口**，让用户能：
1. 在 ChatInput 旁的 `+` 菜单里看到"选择文件夹"项（仅当 spcode 的 `project load` 指令可用时显示）
2. 点击后弹出对话框，输入绝对路径并提交，**等价于手动键入 `/project load <path>`**
3. 加载成功后，在 ChatInput 内显示"已加载项目：xxx"徽章，可一键卸载

### 1.4 非目标

- ❌ **不**修改 spcode 插件代码
- ❌ **不**修改 AstrBot 核心（后端、协议、消息总线）
- ❌ **不**支持 Firefox / Safari（仅 Chrome / Edge；理由：浏览器沙箱无法让 web 应用拿到任意磁盘的绝对路径）
- ❌ **不**实现图形化文件夹树浏览（仅文本输入绝对路径）
- ❌ **不**改动现有 Project 体系（`ProjectList` / `ProjectDialog` / `ProjectView`）的数据模型与行为
- ❌ **不**持久化加载状态（刷新页面后状态丢失，需重新加载）

---

## 2. 设计决策（已与用户确认）

| # | 决策点 | 选择 | 理由 |
|---|--------|------|------|
| 1 | 按钮可见性 | **A**：仅当 `/api/commands` 中 spcode 的 `project load` 指令存在且 `enabled === true` | 插件被禁用时按钮自动消失，避免误导 |
| 2 | 加载指令是否进聊天流 | **A**：作为普通用户消息显示 | 与手动键入完全等价，最简单 |
| 3 | 是否显示"已加载"徽章 | **A**：显示 | 提供状态可见性 |
| 4 | 徽章位置 | **B**：ChatInput 内部、textarea 之上、附件预览区旁 | 与"已加载资源"语义同级 |
| 5 | 徽章卸载操作 | **A**：hover 出现 × 按钮触发 `/project unload` | 形成操作闭环 |
| 6 | 命令前缀探测 | **A**：从 `wakePrefixes.value[0]` 动态取 | 自动适配未来多前缀 |
| 7 | 文件夹选择 UI | **A 增强版**：v-dialog + 文本输入框 | web 沙箱限制下最务实的方案 |
| 8 | "浏览"按钮 | **B**：取消 | showDirectoryPicker 在 web 侧无法获得磁盘绝对路径 |

---

## 3. 架构与文件改动

### 3.1 架构原则

- **零后端改动**：完全复用 `/api/chat`、`/api/commands` 现有 endpoint
- **零 spcode 改动**：通过 `/project load <path>` 标准消息触发
- **零新依赖**：仅用 Vue 3 Composition API + Vuetify 现有组件
- **零现有组件破坏**：所有改动收敛在 `ChatInput.vue` + 新增 2 个子组件 + 1 个 composable + i18n key

### 3.2 文件改动清单

| 层级 | 文件 | 性质 | 说明 |
|------|------|------|------|
| 新增 | `dashboard/src/components/chat/ProjectFolderPicker.vue` | 新组件 | "选择文件夹"对话框（路径输入 + 提交） |
| 新增 | `dashboard/src/components/chat/ProjectLoadedBadge.vue` | 新组件 | 加载状态徽章（含 hover 卸载） |
| 新增 | `dashboard/src/composables/useSpcodeProject.ts` | 新 composable | 集中管理"检测 + 加载状态机 + 解析" |
| 改动 | `dashboard/src/components/chat/ChatInput.vue` | 修改 | 接入 composable + 渲染两个新组件 + + 菜单新增项 |
| 改动 | `dashboard/src/i18n/locales/zh-CN/features/chat.json` | 修改 | 新增 i18n key |
| 改动 | `dashboard/src/i18n/locales/en-US/features/chat.json` | 修改 | 新增 i18n key |
| **后端** | **无任何改动** | ✅ | — |
| **spcode** | **无任何改动** | ✅ | — |

### 3.3 改动量估算

- 新增代码：~300 行（含注释）
- 改动现有代码：~50 行（仅 ChatInput.vue）
- 风险面：仅前端 1 个组件 + 1 个 composable

---

## 4. 组件结构

### 4.1 ChatInput 内部新增部分（伪代码）

```vue
<ChatInput>
  <!-- 现有引用预览区 / 附件预览区 -->
  <div class="reply-preview" v-if="props.replyTo">...</div>
  <div class="attachments-preview" v-if="hasStagedAttachments">...</div>

  <!-- 新增：已加载项目徽章(条件渲染) -->
  <ProjectLoadedBadge
    v-if="hasSpcodeCommand && currentLoadedPath"
    :path="currentLoadedPath"
    @unload="handleUnload"
  />

  <!-- 现有 textarea -->
  <textarea v-model="localPrompt" ... />

  <!-- 现有操作栏 + 菜单 -->
  <div class="input-action-bar">
    <StyledMenu activator="+">
      <v-list-item>Upload</v-list-item>

      <!-- 新增菜单项(条件渲染) -->
      <v-list-item v-if="hasSpcodeCommand" @click="openFolderPicker">
        <v-icon>mdi-folder-plus-outline</v-icon>
        {{ tm("input.selectFolder") }}
      </v-list-item>

      <ConfigSelector />
      <StreamingToggle />
    </StyledMenu>
  </div>

  <!-- 新增：文件夹选择对话框(条件渲染) -->
  <ProjectFolderPicker
    v-if="hasSpcodeCommand"
    v-model:open="pickerOpen"
    @submit="handleFolderSubmit"
  />
</ChatInput>
```

### 4.2 组件 Props/Emits 接口

```typescript
// ProjectFolderPicker.vue
interface Props {
  open: boolean;          // v-model:open
}
interface Emits {
  'update:open': [boolean];
  submit: [path: string]; // 用户提交路径
}

// ProjectLoadedBadge.vue
interface Props {
  path: string;           // 完整绝对路径(内部用 basename 展示)
}
interface Emits {
  unload: [];             // 用户点击 × 卸载按钮
}
```

---

## 5. 状态管理（`useSpcodeProject` composable）

### 5.1 接口定义

```typescript
// dashboard/src/composables/useSpcodeProject.ts
import { computed, ref, type ComputedRef, type Ref } from 'vue';

export interface SpcodeProjectApi {
  // 1. 能力检测
  hasSpcodeCommand: ComputedRef<boolean>;
  
  // 2. per-session 加载状态
  loadedBySession: Ref<Record<string, string>>;
  
  // 3. 当前 session 的加载状态
  currentLoadedPath: ComputedRef<string | null>;
  
  // 4. UI 控制
  pickerOpen: Ref<boolean>;
  
  // 5. 行为
  openPicker(): void;
  submitPath(path: string): Promise<void>;
  unload(): Promise<void>;
  
  // 6. 副作用 hook
  observeAgentMessage(text: string): void;
}

export function useSpcodeProject(
  sessionIdRef: Ref<string | null>,
  sendMessageStream: (opts: { text: string }) => Promise<void>,
  allCommands: Ref<Array<{
    plugin_name: string;
    effective_command: string;
    enabled: boolean;
  }>>,
): SpcodeProjectApi;
```

### 5.2 关键状态计算

```typescript
// 检测 spcode 激活: 1) 存在 project load 指令 2) 启用中
const hasSpcodeCommand = computed(() => {
  return allCommands.value.some(cmd => 
    cmd.enabled
    && /spcode/i.test(cmd.plugin_name)
    && /(^|\s)project\s+load(\s|$)/.test(cmd.effective_command)
  );
});

// 当前 session 已加载路径
const currentLoadedPath = computed(() => {
  const sid = sessionIdRef.value;
  if (!sid) return null;
  return loadedBySession.value[sid] ?? null;
});
```

### 5.3 行为实现

```typescript
async function submitPath(path: string): Promise<void> {
  const trimmed = path.trim();
  if (!trimmed) return;
  const prefix = wakePrefixes.value[0] ?? '/';
  const message = `${prefix}project load ${trimmed}`;
  await sendMessageStream({ text: message });
  pickerOpen.value = false;
}

async function unload(): Promise<void> {
  const prefix = wakePrefixes.value[0] ?? '/';
  const message = `${prefix}project unload`;
  await sendMessageStream({ text: message });
}

function observeAgentMessage(text: string): void {
  // 1. 匹配加载成功(来自 spcode main.py:1170-1177 的输出)
  //    "✅ 项目已加载: <path>\n已自动进行如下步骤:..."
  const loadMatch = text.match(/✅ 项目已加载: (.+?)(?:\n|$)/);
  if (loadMatch && sessionIdRef.value) {
    loadedBySession.value = {
      ...loadedBySession.value,
      [sessionIdRef.value]: loadMatch[1].trim(),
    };
    return;
  }
  
  // 2. 匹配卸载成功
  if (/✅ 项目已卸载/.test(text) && sessionIdRef.value) {
    const sid = sessionIdRef.value;
    const { [sid]: _, ...rest } = loadedBySession.value;
    loadedBySession.value = rest;
  }
}
```

### 5.4 状态转移图

```
[IDLE] 
  --(用户提交路径)--> [AWAITING_RESULT]
                            |
                  (spcode 回显 ✅)         (spcode 回显 ❌)
                          ↓                       ↓
                      [LOADED]                [IDLE] (无变化)
                          |
                  (用户点 × 卸载)
                          ↓
                      [AWAITING_UNLOAD]
                          |
                  (spcode 回显 ✅ 项目已卸载)
                          ↓
                       [IDLE]
```

### 5.5 状态持久化

- `loadedBySession` 仅在内存中维护，**不写 localStorage**
- 切换 session：自动从 `loadedBySession[newSessionId]` 读取
- 刷新页面：状态丢失（可接受 —— 与 spcode 后端实际状态可能不一致，但下次操作时会被 spcode 的"重复 load 拦截"提示覆盖）

---

## 6. 关键交互时序

### 6.1 首次进入 ChatInput（spcode 激活）

```
ChatInput mount
  → fetchCommands() → allCommands.value = [...]
  → hasSpcodeCommand.value = true
  → + 菜单渲染时,"选择文件夹"项显示 ✅
  → ProjectLoadedBadge 不渲染(currentLoadedPath = null)
```

### 6.2 用户加载项目

```
用户点击 [📁 选择文件夹]
  → pickerOpen.value = true → v-dialog 打开
  → 用户在文本框输入 "C:\Users\me\projects\my-app" 并提交
  → submitPath("C:\\Users\\me\\projects\\my-app")
  → sendMessageStream({ text: "/project load C:\\Users\\me\\projects\\my-app" })
  → 聊天流出现用户消息: "/project load C:\Users\me\projects\my-app"
  → spcode 流式回显 3 步进度
  → observeAgentMessage() 每次 spcode 输出时调用
  → 末尾正则匹配命中: ✅ 项目已加载: C:\Users\me\projects\my-app
  → loadedBySession.value[sessionId] = "C:\\Users\\me\\projects\\my-app"
  → currentLoadedPath 更新
  → ProjectLoadedBadge 渲染 "📁 my-app" ✅
```

### 6.3 用户卸载项目

```
用户 hover [📁 my-app] → 显示 [×] 按钮
  → 点击 [×]
  → unload()
  → sendMessageStream({ text: "/project unload" })
  → spcode 回显 "✅ 项目已卸载"
  → observeAgentMessage 匹配到卸载成功
  → delete loadedBySession.value[sessionId]
  → ProjectLoadedBadge 自动消失 ✅
```

### 6.4 切换 session

```
currSessionId 变化
  → currentLoadedPath = computed 自动切换到 loadedBySession[newSessionId]
  → 徽章自动显示/隐藏 ✅
```

### 6.5 spcode 被禁用

```
用户禁用 spcode 插件
  → 下次 fetchCommands() 后 allCommands 中无 project load
  → hasSpcodeCommand = false
  → + 菜单中"选择文件夹"项消失 ✅
  → ProjectLoadedBadge 也消失 ✅
```

---

## 7. 错误处理与边界

### 7.1 错误矩阵

| 触发条件 | 检测点 | 行为 |
|---------|--------|------|
| 路径为空 | `submitPath` 入口 | 提交按钮 disabled |
| 路径含前后空格 | 提交前 `trim()` | 自动 trim |
| 路径含未配对引号 | spcode 内部 `strip_surrounding_quotes` 已处理 | dashboard 无需处理 |
| 路径不存在/不安全 | spcode `_is_path_safe` 校验 | spcode 回显 `❌ 路径不允许: <reason>`，前端不更新 loadedBySession |
| 当前会话已加载其他项目 | spcode 重复 load 拦截 | spcode 回显 `❌ 当前会话已加载项目: ...`，前端不更新 |
| `agentsmd_enabled` / `codegraph_enabled` 为 false | spcode 内部 | spcode 回显 `❌ /project 命令要求 ... 都为 true`，前端不更新 |
| 用户取消 dialog | v-dialog 默认行为 | `pickerOpen = false`，无副作用 |
| 多个 dashboard tab 同时打开 | 浏览器侧 | 各 tab 独立维护 loadedBySession 内存副本；后端真实状态以 spcode 为准；可能出现 tab A 徽章显示但 tab B 不显示的短暂不一致（**可接受，刷新即可**） |
| 服务端 SSE 中断 | 现有 `sendMessageStream` 已有重试 | 与手动发消息行为一致 |
| `wakePrefixes` 尚未 fetch 完成 | `wakePrefixes.value[0] ?? "/"` | 默认 fallback 为 `/` |

### 7.2 正则稳健性

匹配 spcode 末尾的成功消息（`main.py:1170-1177`）：
```python
yield event.plain_result(
    f"✅ 项目已加载: {target}\n"
    f"已自动进行如下步骤:\n"
    ...
)
```
- 使用正则：`/✅ 项目已加载: (.+?)(?:\n|$)/`
- 捕获组 1 即为绝对路径
- 仅在 `sessionIdRef.value` 上下文匹配，避免误抓

匹配卸载成功：
```python
# spcode 的 project_unload 末尾输出(预期):
# "✅ 项目已卸载"
```
- 使用正则：`/✅ 项目已卸载/`
- 不需要捕获组

### 7.3 安全边界

- 绝对路径由用户自行负责输入正确性
- 服务端 spcode 已用 `_is_path_safe` + `file_remove_blacklist` 校验，前端**不重复**校验
- dashboard **不读取/不上传**任何文件内容，仅发送文本命令

### 7.4 性能与内存

- `loadedBySession` 是普通 `Record<sessionId, path>`，按 session 数量级 O(N) 增长
- 单用户正常使用 session 数 < 100，**内存可忽略**
- 不做主动清理

### 7.5 可访问性

- 徽章按钮 `<button>` 元素，带 `aria-label`
- v-dialog 用 Vuetify 内置 focus trap
- 路径输入框 `<v-text-field>` 自带 label

### 7.6 国际化

> **注：** dashboard 的 i18n 按 locale 拆分（`zh-CN.json` / `en-US.json` 各自独立），下方仅展示 key 列表；实施时拆开填入各自文件。

新增 i18n key 列表：

```jsonc
// 通用 key（两个 locale 都需要）
{
  "input.selectFolder": "选择文件夹",          // en-US: "Select Folder"
  "input.folderPathLabel": "项目文件夹绝对路径", // en-US: "Project Folder Absolute Path"
  "input.folderPathPlaceholder": "例如: C:\\Users\\me\\projects\\my-app", // en-US: "e.g. C:\\Users\\me\\projects\\my-app"
  "input.folderPathSubmit": "加载项目",          // en-US: "Load Project"
  "input.folderPathCancel": "取消",             // en-US: "Cancel"
  "input.projectUnload": "卸载",                // en-US: "Unload"
  "input.projectLoadError": "项目加载失败，请查看聊天流" // en-US: "Project load failed, see chat stream"
}
```

---

## 8. 测试方案

### 8.1 测试层级

| 层级 | 范围 | 工具 |
|------|------|------|
| 单元测试 | `useSpcodeProject` composable 纯逻辑 | Vitest |
| 组件测试 | `ProjectFolderPicker` / `ProjectLoadedBadge` | @vue/test-utils |
| 手动验证 | 端到端流程 | 真机 + dev server |

### 8.2 单元测试用例

```typescript
// useSpcodeProject.spec.ts
describe('hasSpcodeCommand detection', () => {
  it('returns true when project load exists and enabled', () => {});
  it('returns false when command is disabled', () => {});
  it('returns false when plugin is not spcode', () => {});
  it('returns false when command is not "project load"', () => {});
});

describe('observeAgentMessage state transitions', () => {
  it('captures path from success message', () => {});
  it('does NOT capture path from error message', () => {});
  it('clears path on unload success', () => {});
  it('is per-session isolated', () => {});
  it('handles multi-line messages', () => {});
});

describe('submitPath / unload', () => {
  it('trims whitespace before sending', () => {});
  it('uses wakePrefixes[0] as prefix', () => {});
  it('falls back to "/" when wakePrefixes is empty', () => {});
  it('closes picker on submit', () => {});
  it('does nothing on empty path', () => {});
});
```

### 8.3 组件测试用例

```typescript
// ProjectFolderPicker.spec.ts
describe('ProjectFolderPicker', () => {
  it('submits trimmed path');
  it('disables submit when path empty');
  it('emits submit with path on Enter');
  it('emits update:open=false on cancel');
});

// ProjectLoadedBadge.spec.ts
describe('ProjectLoadedBadge', () => {
  it('renders path with folder emoji');
  it('shows × button on hover');
  it('emits unload on × click');
  it('displays basename of full path');
});
```

### 8.4 手动验证 checklist

- [ ] spcode 启用时，+ 菜单出现"选择文件夹"
- [ ] spcode 禁用时，该菜单项消失
- [ ] 输入合法路径并提交，聊天流出现 `/project load <path>` 用户消息
- [ ] spcode 成功回显后，徽章出现并显示文件夹名（basename）
- [ ] hover 徽章出现 × 按钮，点击触发 `/project unload`，徽章消失
- [ ] 切换 session，徽章按新 session 状态正确显示/隐藏
- [ ] 输入空路径时，提交按钮 disabled
- [ ] 输入含前后空格，提交时自动 trim
- [ ] spcode 返回错误（路径不允许/已加载）时，徽章不显示
- [ ] 修改 wake_prefix 配置后，前端仍能正确构造命令前缀
- [ ] 同时打开两个 dashboard tab，徽章行为独立（不互相干扰）
- [ ] i18n 在 zh-CN / en-US 切换正常
- [ ] 刷新页面后，徽章状态丢失（符合预期）

### 8.5 回归测试

- 现有 ChatInput 的所有功能（文件上传、配置切换、流式开关、消息发送）不受影响
- 现有 ProjectList / ProjectDialog / ProjectView 行为不变

---

## 9. 风险与缓解

| 风险 | 严重度 | 缓解措施 |
|------|--------|---------|
| 浏览器不支持 showDirectoryPicker（已规避：不使用） | — | 改用纯文本输入 |
| Firefox/Safari 上体验不完整 | 中 | 暂不支持（本期仅 Chrome/Edge） |
| 用户输入了不在 `_is_path_safe` 白名单的目录 | 低 | spcode 返回明确错误消息，前端不更新状态 |
| 重复 load 同一会话 | 低 | spcode 已拦截，前端不更新状态 |
| 多个 tab 状态不一致 | 低 | 接受 / 刷新即可解决 |
| spcode 卸载命令的实际输出文本与正则不匹配 | 中 | 实施前需在 spcode main.py 确认 `project_unload` 末尾实际输出（spec 假设为 `✅ 项目已卸载`） |

---

## 10. 实施前需确认的开放问题

1. **spcode `project_unload` 末尾的实际输出文本**：spec 假设为 `✅ 项目已卸载`，但需要在实施前打开 `main.py` 第 1180 行附近确认实际输出
2. **wake_prefix 多值场景**：spec 当前用 `wakePrefixes.value[0]`，是否合理需用户确认（用户已选 A）
3. **i18n 翻译精度**：spec 列出的是中英文混合占位符，需要正式翻译

---

## 11. 实施后续

1. 通过 spec 评审（本文档）
2. 调用 `writing-plans` skill 制定详细实施计划
3. 按计划实现 → 手动验证 checklist → 提 PR

---

## 附录 A：相关代码位置速查

- ChatInput.vue：`dashboard/src/components/chat/ChatInput.vue:1-?`（编辑器底部 + 菜单）
- Chat.vue：`dashboard/src/components/chat/Chat.vue:299-337`（ProjectView 内的 ChatInput 引用）
- 现有 Project 体系：`dashboard/src/components/chat/{ProjectList,ProjectDialog,ProjectView}.vue`
- spcode `/project load` 实现：`F:\github\astrbot_plugin_spcode_toolkit\main.py:1099-1178`
- spcode `/project unload` 实现：`F:\github\astrbot_plugin_spcode_toolkit\main.py:1180-?`
- `useMessages.sendMessageStream`：`dashboard/src/composables/useMessages.ts:393`
- `chat_send` endpoint：`astrbot/dashboard/routes/open_api.py:145`
- `get_commands` endpoint：`astrbot/dashboard/routes/command.py:33`

## 附录 B：i18n 文件路径

- `dashboard/src/i18n/locales/zh-CN/features/chat.json`
- `dashboard/src/i18n/locales/en-US/features/chat.json`
- 完整 locale 列表可通过 `dashboard/src/i18n/locales/` 目录确认

---

*本文档由 brainstorming skill 协作生成，作者 elecvoid243，2026-06-14。*
