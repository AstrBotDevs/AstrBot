# Dynamic Choice Box Rendering — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 AstrBot WebChat 前端实现"动态选项框渲染"——LLM 通过调用 `ask_user_choice` 工具输出结构化 `InteractiveChoicePart` JSON,前端 `normalizePartsInternal` 解包 + 校验,`<InteractiveChoiceBox>` 组件动态渲染;用户点击选项或输入文本后以纯文本 user message 回传 LLM。

**Architecture:**
- **解析层**：抽取纯函数模块 `parseInteractiveChoice.ts`(`unwrapInteractiveChoice` + `validateInteractiveChoice` + `truncateInteractiveChoice`),镜像既有 `parseSpcode*.ts` 同构模式,可被 `node --test` 独立单测
- **集成层**：`useMessages.normalizePartsInternal` 调上述纯函数做解包+校验,非法 part 降级为 `unknown-part`(`{ type: "plain", text: JSON.stringify(part) }`)
- **组件层**：`<InteractiveChoiceBox>` 4 状态机(`pending` / `submitted_via_option` / `submitted_via_input` / `ignored`),`isIgnored` 由 `ChatMessageList` 按 messages 数组顺序计算
- **插件脚手架**：独立仓库 `astrbot_plugin_choice_ui`(v1 仅 choice_tool.py + main.py + metadata.yaml,无完整插件工程)

**Tech Stack:** Vue 3.3.4 + Vuetify 3.7.11 + TypeScript + vue-i18n 11 + Node.js 内建 `node --test` + Python 3.10+ (plugin)

**前置 spec:** `docs/superpowers/specs/2026-06-28-dynamic-choice-box-rendering-design.md` (已通过 4 轮 review loop, APPROVED)

---

## File Structure

### 新增文件

| 文件 | 职责 |
|------|------|
| `dashboard/src/composables/parseInteractiveChoice.ts` | 纯函数:`isInteractiveChoicePayload(value)` / `unwrapInteractiveChoice(part)` / `validateInteractiveChoice(obj)` / `truncateInteractiveChoice(part)` |
| `dashboard/tests/parseInteractiveChoice.test.mjs` | `node --test` 单元测试:解包(合法/非法 JSON/非 plain)、校验(缺字段/id 重复/options 数量)、截断(超长字符串) |
| `dashboard/src/components/chat/message_list_comps/InteractiveChoiceBox.vue` | 选项框组件(4 状态机 + 提交 emit + a11y + i18n) |
| `astrbot_plugin_choice_ui/choice_tool.py` | `AskUserChoiceTool(FunctionTool)` 完整定义(见 spec §11.1) |
| `astrbot_plugin_choice_ui/main.py` | 插件入口,`add_llm_tool(AskUserChoiceTool())` 一行 |
| `astrbot_plugin_choice_ui/metadata.yaml` | 插件元数据(name/version/astrbot_version) |

### 修改文件

| 文件 | 改动 |
|------|------|
| `dashboard/src/composables/useMessages.ts` | `MessagePart` interface 增 `interactive_choice` 字段;`normalizePartsInternal` 调 `parseInteractiveChoice.unwrapInteractiveChoice` + `validateInteractiveChoice`,非 `interactive_choice` 时回退默认 `return { ...part }` 行为 |
| `dashboard/src/components/chat/ChatMessageList.vue` | import `InteractiveChoiceBox`;v-else-if 链(`unknown-part` **之前**)加 `<InteractiveChoiceBox v-else-if="part.type === 'interactive_choice'" ... />`;`onInteractiveChoiceSubmit(text)` handler 调 `sendMessage({ text })`;`isInteractiveChoiceIgnored(msg)` helper 按 messages 数组顺序判定 |
| `dashboard/src/i18n/locales/zh-CN/features/chat.json` | `interactiveChoice.*` 5 keys |
| `dashboard/src/i18n/locales/en-US/features/chat.json` | `interactiveChoice.*` 5 keys |
| `dashboard/src/i18n/locales/ru-RU/features/chat.json` | `interactiveChoice.*` 5 keys |

> **关于 Vue 组件测试**:项目无 Vue 组件测试框架(见 spec §12 类似说明)。`<InteractiveChoiceBox>` 走手动冒烟测试覆盖,纯函数逻辑在 `parseInteractiveChoice.ts` 单测覆盖。

> **关于 `MessageList.vue` (deprecated)**:v1 不修改,见 spec §5.2。

---

## Chunk 1: 解析层 (TDD)

### Task 1: 准备工作

**Files:**
- (无文件改动,仅 git 操作)

- [ ] **Step 1: 确认 `master` 分支 HEAD 包含 spec commits**

```bash
cd /d F:\github\Astrbot
git log --oneline -8
```

Expected: 顶部应包含 `f337b4f13 docs(spec): fix Json/Plain wording drift in §2.3 and §8.2` 及之前的 5 条 spec commits。

- [ ] **Step 2: 创建 worktree**

```bash
cd /d F:\github\Astrbot
git worktree add .worktrees/feat-choice-box -b feat/dynamic-choice-box master
```

Expected: worktree 创建在 `.worktrees/feat-choice-box/`,基于 `master` 分支。

- [ ] **Step 3: 在 worktree 中确认状态**

```bash
cd .worktrees/feat-choice-box
git status
git branch --show-current
```

Expected: `On branch feat/dynamic-choice-box`,working tree clean。

> **后续所有命令**都假定你在 `.worktrees/feat-choice-box/` 目录下执行,使用 `@test-driven-development` 技能。

---

### Task 2: TDD 解析层 — 写测试 (parseInteractiveChoice.test.mjs)

**Files:**
- Create: `dashboard/tests/parseInteractiveChoice.test.mjs`

- [ ] **Step 1: 写失败的测试**

完整内容写入 `dashboard/tests/parseInteractiveChoice.test.mjs`:

```javascript
// Author: elecvoid243
// Date: 2026-06-28
// Spec: docs/superpowers/specs/2026-06-28-dynamic-choice-box-rendering-design.md §2.3 / §3.2 / §7
//
// 测试 parseInteractiveChoice.ts 的纯函数:解包(unwrap) + 校验(validate) + 截断(truncate)。
// 覆盖 spec §3.2 字段约束、§7 错误处理。
import assert from "node:assert/strict";
import test from "node:test";

import {
  isInteractiveChoicePayload,
  unwrapInteractiveChoice,
  validateInteractiveChoice,
  truncateInteractiveChoice,
} from "../src/composables/parseInteractiveChoice.ts";

// ─── 公共 fixture ─────────────────────────────────────────────
const validOption = { id: "a", label: "GPT-4", description: "更强但更慢", value: "gpt-4" };
const validPart = {
  type: "interactive_choice",
  prompt: "请选择下一步使用的模型:",
  options: [validOption, { id: "b", label: "GPT-4 mini", value: "gpt-4-mini" }],
};

// ─── isInteractiveChoicePayload ──────────────────────────────
test("isInteractiveChoicePayload: 合法 InteractiveChoicePart 返回 true", () => {
  assert.equal(isInteractiveChoicePayload(validPart), true);
});

test("isInteractiveChoicePayload: 缺 type 字段返回 false", () => {
  assert.equal(isInteractiveChoicePayload({ prompt: "x", options: [validOption] }), false);
});

test("isInteractiveChoicePayload: type 不是 interactive_choice 返回 false", () => {
  assert.equal(isInteractiveChoicePayload({ type: "plain", text: "hi" }), false);
  assert.equal(isInteractiveChoicePayload({ type: "tool_call" }), false);
});

test("isInteractiveChoicePayload: 非对象(null / string / array)返回 false", () => {
  assert.equal(isInteractiveChoicePayload(null), false);
  assert.equal(isInteractiveChoicePayload("string"), false);
  assert.equal(isInteractiveChoicePayload([1, 2]), false);
});

// ─── unwrapInteractiveChoice ──────────────────────────────────
test("unwrapInteractiveChoice: plain + JSON 字符串前缀 { 解包为 InteractiveChoicePart", () => {
  const part = { type: "plain", text: JSON.stringify(validPart) };
  const result = unwrapInteractiveChoice(part);
  assert.deepEqual(result, validPart);
});

test("unwrapInteractiveChoice: 原生 interactive_choice part 透传", () => {
  const result = unwrapInteractiveChoice(validPart);
  assert.deepEqual(result, validPart);
});

test("unwrapInteractiveChoice: 普通 plain 文本不改动", () => {
  const part = { type: "plain", text: "hello world" };
  assert.deepEqual(unwrapInteractiveChoice(part), part);
});

test("unwrapInteractiveChoice: plain 但 JSON.parse 失败保留原 part(见 spec §7)", () => {
  const part = { type: "plain", text: '{ "type": "interactive_choice", "broken' };
  assert.deepEqual(unwrapInteractiveChoice(part), part);
});

test("unwrapInteractiveChoice: plain 但解析后 type 不是 interactive_choice 保留原 part", () => {
  const part = { type: "plain", text: '{"type":"other","foo":1}' };
  assert.deepEqual(unwrapInteractiveChoice(part), part);
});

test("unwrapInteractiveChoice: plain 但 text 不以 { 开头保留原 part", () => {
  const part = { type: "plain", text: "not json" };
  assert.deepEqual(unwrapInteractiveChoice(part), part);
});

test("unwrapInteractiveChoice: 非 plain / 非 interactive_choice 原样返回(图片等不重写)", () => {
  const imagePart = { type: "image", url: "http://x" };
  assert.deepEqual(unwrapInteractiveChoice(imagePart), imagePart);
});

// ─── validateInteractiveChoice ────────────────────────────────
test("validateInteractiveChoice: 合法 part 返回 true", () => {
  assert.equal(validateInteractiveChoice(validPart), true);
});

test("validateInteractiveChoice: 缺 prompt 返回 false", () => {
  assert.equal(validateInteractiveChoice({ type: "interactive_choice", options: [validOption] }), false);
});

test("validateInteractiveChoice: prompt 为空字符串返回 false", () => {
  assert.equal(validateInteractiveChoice({ type: "interactive_choice", prompt: "", options: [validOption] }), false);
});

test("validateInteractiveChoice: 缺 options 返回 false", () => {
  assert.equal(validateInteractiveChoice({ type: "interactive_choice", prompt: "x" }), false);
});

test("validateInteractiveChoice: options 只有一个元素返回 false(spec §3.2 至少 2 个)", () => {
  assert.equal(
    validateInteractiveChoice({ type: "interactive_choice", prompt: "x", options: [validOption] }),
    false,
  );
});

test("validateInteractiveChoice: options 元素缺 id 返回 false", () => {
  const bad = { type: "interactive_choice", prompt: "x", options: [{ label: "x", value: "y" }] };
  assert.equal(validateInteractiveChoice(bad), false);
});

test("validateInteractiveChoice: options 元素缺 label 返回 false", () => {
  const bad = { type: "interactive_choice", prompt: "x", options: [{ id: "a", value: "y" }] };
  assert.equal(validateInteractiveChoice(bad), false);
});

test("validateInteractiveChoice: options 元素缺 value 返回 false", () => {
  const bad = { type: "interactive_choice", prompt: "x", options: [{ id: "a", label: "y" }] };
  assert.equal(validateInteractiveChoice(bad), false);
});

test("validateInteractiveChoice: id 重复返回 false(spec §3.2)", () => {
  const bad = {
    type: "interactive_choice",
    prompt: "x",
    options: [
      { id: "a", label: "A", value: "1" },
      { id: "a", label: "B", value: "2" },
    ],
  };
  assert.equal(validateInteractiveChoice(bad), false);
});

test("validateInteractiveChoice: id 为空字符串返回 false", () => {
  const bad = {
    type: "interactive_choice",
    prompt: "x",
    options: [
      { id: "", label: "A", value: "1" },
      { id: "b", label: "B", value: "2" },
    ],
  };
  assert.equal(validateInteractiveChoice(bad), false);
});

// ─── truncateInteractiveChoice ───────────────────────────────
test("truncateInteractiveChoice: prompt 超 200 字截断", () => {
  const long = "a".repeat(300);
  const result = truncateInteractiveChoice({ type: "interactive_choice", prompt: long, options: [validOption] });
  assert.equal(result.prompt.length, 200);
});

test("truncateInteractiveChoice: title 超 30 字截断", () => {
  const result = truncateInteractiveChoice({ ...validPart, title: "a".repeat(50) });
  assert.equal(result.title.length, 30);
});

test("truncateInteractiveChoice: option.label 超 30 字截断", () => {
  const opt = { ...validOption, label: "a".repeat(60) };
  const result = truncateInteractiveChoice({ ...validPart, options: [opt] });
  assert.equal(result.options[0].label.length, 30);
});

test("truncateInteractiveChoice: option.description 超 200 字截断", () => {
  const opt = { ...validOption, description: "a".repeat(300) };
  const result = truncateInteractiveChoice({ ...validPart, options: [opt] });
  assert.equal(result.options[0].description.length, 200);
});

test("truncateInteractiveChoice: input_placeholder 超 60 字截断", () => {
  const result = truncateInteractiveChoice({ ...validPart, input_placeholder: "a".repeat(100) });
  assert.equal(result.input_placeholder.length, 60);
});

test("truncateInteractiveChoice: value 不截断", () => {
  const longValue = "a".repeat(1000);
  const result = truncateInteractiveChoice({
    ...validPart,
    options: [{ ...validOption, value: longValue }],
  });
  assert.equal(result.options[0].value.length, 1000);
});

test("truncateInteractiveChoice: 短字段不动", () => {
  const result = truncateInteractiveChoice(validPart);
  assert.equal(result, validPart);  // 不可变:如果未截断,返回原对象
});
```

- [ ] **Step 2: 运行测试,确认全部失败**

```bash
cd /d F:\github\Astrbot\.worktrees\feat-choice-box\dashboard
node --test tests/parseInteractiveChoice.test.mjs
```

Expected: **全部失败**,错误信息类似 `Cannot find module '../src/composables/parseInteractiveChoice.ts'`(因为文件还没创建)。

---

### Task 3: 实现 parseInteractiveChoice.ts

**Files:**
- Create: `dashboard/src/composables/parseInteractiveChoice.ts`

- [ ] **Step 1: 写最小实现**

完整内容写入 `dashboard/src/composables/parseInteractiveChoice.ts`:

```typescript
// Author: elecvoid243
// Date: 2026-06-28
// Spec: docs/superpowers/specs/2026-06-28-dynamic-choice-box-rendering-design.md §2.3 / §3.2 / §7
//
// 纯函数模块:把"工具返回 JSON → 前端 InteractiveChoicePart"的翻译逻辑全部内聚到这里,
// 不依赖 Vue / pinia / axios,确保可被 node --test 独立单测。
// 镜像既有 parseSpcodeFileRestore.ts + useSpcodeFileRestore.ts 同构模式。

// ─── 类型定义 ─────────────────────────────────────────────────

/** InteractiveChoicePart 的最小类型。完整字段见 spec §3.1。 */
export interface InteractiveChoiceOption {
  id: string;
  label: string;
  description?: string;
  value: string;
}

export interface InteractiveChoicePart {
  type: "interactive_choice";
  prompt: string;
  title?: string;
  options: InteractiveChoiceOption[];
  input_placeholder?: string;
  [key: string]: unknown;
}

/** 任意 MessagePart 的最小契约(避免 import useMessages 引起循环依赖) */
export interface MaybePlainPart {
  type?: string;
  text?: string;
  [key: string]: unknown;
}

// ─── 解包:判断 payload 是否是 InteractiveChoicePart ───────────

/**
 * 检查某个对象是否是合法的 InteractiveChoicePart 形态。
 * 仅做"类型字段存在性"判断,**不**做字段校验(校验见 validateInteractiveChoice)。
 */
export function isInteractiveChoicePayload(value: unknown): value is InteractiveChoicePart {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const obj = value as Record<string, unknown>;
  return obj.type === "interactive_choice";
}

// ─── 解包:plain 文本 → InteractiveChoicePart ────────────────

/**
 * 把 MessagePart 数组中的某一项尽可能解包成 InteractiveChoicePart。
 *
 * 规则(spec §2.3 / §7):
 * - 原生 `type === "interactive_choice"` → 透传
 * - `type === "plain"` 且 text 以 "{" 开头 → JSON.parse,成功且结果是 InteractiveChoicePart → 替换
 * - 其他(普通文本、图片、工具调用等) → 原样返回,不重写
 * - JSON.parse 失败 → **保留原 plain 文本**(不降级为 unknown-part,避免误吃文本,spec §7)
 */
export function unwrapInteractiveChoice<T extends MaybePlainPart>(part: T): T | InteractiveChoicePart {
  if (part.type === "interactive_choice") {
    return part as unknown as InteractiveChoicePart;
  }
  if (part.type === "plain" && typeof part.text === "string" && part.text.startsWith("{")) {
    let parsed: unknown;
    try {
      parsed = JSON.parse(part.text);
    } catch {
      // 解析失败(spec §7):保留原 plain 文本,不重写
      return part;
    }
    if (isInteractiveChoicePayload(parsed)) {
      return parsed;
    }
  }
  return part;
}

// ─── 校验:字段是否满足 spec §3.2 约束 ────────────────────────

/**
 * 校验 InteractiveChoicePart 的字段是否满足 spec §3.2 约束。
 * 失败时返回 false(spec §2.3 步骤 2:非法则降级为 unknown-part)。
 */
export function validateInteractiveChoice(obj: unknown): boolean {
  if (!isInteractiveChoicePayload(obj)) return false;

  const part = obj as Record<string, unknown>;
  const prompt = part.prompt;
  if (typeof prompt !== "string" || !prompt.trim()) return false;

  const options = part.options;
  if (!Array.isArray(options) || options.length < 2) return false;

  const seenIds = new Set<string>();
  for (const opt of options) {
    if (!opt || typeof opt !== "object") return false;
    const o = opt as Record<string, unknown>;
    const id = o.id;
    const label = o.label;
    const value = o.value;
    if (typeof id !== "string" || !id.trim()) return false;
    if (typeof label !== "string" || !label.trim()) return false;
    if (typeof value !== "string") return false;
    if (seenIds.has(id)) return false;
    seenIds.add(id);
  }
  return true;
}

// ─── 截断:防御性兜底,工具层已截但前端再截一次(spec §3.2 footnote) ─

/**
 * 截断超长字段(spec §3.2 长度上限 + 末尾 footnote 双重截断策略)。
 * 不可变:未发生截断时返回原对象(优化 + 便于测试 deepEqual)。
 */
export function truncateInteractiveChoice(part: InteractiveChoicePart): InteractiveChoicePart {
  const PROMPT_MAX = 200;
  const TITLE_MAX = 30;
  const LABEL_MAX = 30;
  const DESC_MAX = 200;
  const PLACEHOLDER_MAX = 60;

  let mutated = false;
  const out: InteractiveChoicePart = { ...part };

  if (out.prompt.length > PROMPT_MAX) {
    out.prompt = out.prompt.slice(0, PROMPT_MAX);
    mutated = true;
  }
  if (typeof out.title === "string" && out.title.length > TITLE_MAX) {
    out.title = out.title.slice(0, TITLE_MAX);
    mutated = true;
  }
  if (typeof out.input_placeholder === "string" && out.input_placeholder.length > PLACEHOLDER_MAX) {
    out.input_placeholder = out.input_placeholder.slice(0, PLACEHOLDER_MAX);
    mutated = true;
  }
  if (Array.isArray(out.options)) {
    const newOptions: InteractiveChoiceOption[] = [];
    for (const opt of out.options) {
      let optMutated = false;
      const o: InteractiveChoiceOption = { ...opt };
      if (o.label.length > LABEL_MAX) {
        o.label = o.label.slice(0, LABEL_MAX);
        optMutated = true;
      }
      if (typeof o.description === "string" && o.description.length > DESC_MAX) {
        o.description = o.description.slice(0, DESC_MAX);
        optMutated = true;
      }
      newOptions.push(o);
      if (optMutated) mutated = true;
    }
    out.options = newOptions;
  }
  return mutated ? out : part;
}
```

- [ ] **Step 2: 运行测试,确认全部通过**

```bash
cd /d F:\github\Astrbot\.worktrees\feat-choice-box\dashboard
node --test tests/parseInteractiveChoice.test.mjs
```

Expected: **27 tests pass** (与 Task 2 测试列表的 27 个 test() 块对应)。

- [ ] **Step 3: 跑 typecheck 确认类型正确**

```bash
cd /d F:\github\Astrbot\.worktrees\feat-choice-box\dashboard
npm run typecheck
```

Expected: **无 error**(可能有其他无关 warning,但不应有 `parseInteractiveChoice.ts` 相关的错误)。

- [ ] **Step 4: Commit**

```bash
cd /d F:\github\Astrbot\.worktrees\feat-choice-box
git add dashboard/src/composables/parseInteractiveChoice.ts dashboard/tests/parseInteractiveChoice.test.mjs
git commit -m "feat(dashboard): add parseInteractiveChoice pure functions with tests"
```

---

### Task 4: 在 useMessages.normalizePartsInternal 集成解包 + 校验

**Files:**
- Modify: `dashboard/src/composables/useMessages.ts:1300-1318` (normalizePartsInternal 函数体)

- [ ] **Step 1: 阅读当前 normalizePartsInternal 实现**

确认现有函数签名 + 行为不变基础(参考 spec §2.3):

```typescript
function normalizePartsInternal(parts: unknown): MessagePart[] {
  if (typeof parts === "string") {
    return parts ? [{ type: "plain", text: parts }] : [];
  }
  if (!Array.isArray(parts)) return [];
  return parts.map((part: any) => {
    if (!part || typeof part !== "object") {
      return { type: "plain", text: String(part ?? "") };
    }
    if (part.type === "reasoning") {
      return {
        ...part,
        type: "think",
        think: String(part.think ?? part.text ?? ""),
      };
    }
    return { ...part };
  });
}
```

- [ ] **Step 2: 集成解包 + 校验 + 截断**

**修改位置**:`useMessages.ts` 文件顶部 import 块新增:

```typescript
import {
  unwrapInteractiveChoice,
  validateInteractiveChoice,
  truncateInteractiveChoice,
} from "./parseInteractiveChoice";
```

**修改位置**:`normalizePartsInternal` 函数体,把最后的 `return { ...part };` 替换为:

```typescript
function normalizePartsInternal(parts: unknown): MessagePart[] {
  if (typeof parts === "string") {
    return parts ? [{ type: "plain", text: parts }] : [];
  }
  if (!Array.isArray(parts)) return [];
  return parts.map((part: any) => {
    if (!part || typeof part !== "object") {
      return { type: "plain", text: String(part ?? "") };
    }
    if (part.type === "reasoning") {
      return {
        ...part,
        type: "think",
        think: String(part.think ?? part.text ?? ""),
      };
    }
    // ① 解包(plain 文本内嵌 JSON / 透传原生 interactive_choice)
    const unwrapped = unwrapInteractiveChoice(part);
    // ② 如果解包后是 InteractiveChoicePart,走校验 + 截断
    if (isInteractiveChoicePayload(unwrapped)) {
      if (!validateInteractiveChoice(unwrapped)) {
        // 非法(spec §2.3 步骤 2):降级为 unknown-part
        return { type: "plain", text: JSON.stringify(unwrapped) };
      }
      return truncateInteractiveChoice(unwrapped);
    }
    return { ...part };
  });
}
```

并 import `isInteractiveChoicePayload`:

```typescript
import {
  isInteractiveChoicePayload,
  unwrapInteractiveChoice,
  validateInteractiveChoice,
  truncateInteractiveChoice,
} from "./parseInteractiveChoice";
```

- [ ] **Step 3: 跑 typecheck**

```bash
cd /d F:\github\Astrbot\.worktrees\feat-choice-box\dashboard
npm run typecheck
```

Expected: **无 error**。

- [ ] **Step 4: 跑解析层单测确认没破坏**

```bash
cd /d F:\github\Astrbot\.worktrees\feat-choice-box\dashboard
node --test tests/parseInteractiveChoice.test.mjs
```

Expected: **27 tests pass**。

- [ ] **Step 5: 跑 lint**

```bash
cd /d F:\github\Astrbot\.worktrees\feat-choice-box\dashboard
npm run lint
```

Expected: **无 error**(可能有其他无关 warning)。

- [ ] **Step 6: Commit**

```bash
cd /d F:\github\Astrbot\.worktrees\feat-choice-box
git add dashboard/src/composables/useMessages.ts
git commit -m "feat(dashboard): wire parseInteractiveChoice into normalizePartsInternal"
```

---

## Chunk 2: i18n + 组件 + 集成

### Task 5: 加 i18n keys (3 locales)

**Files:**
- Modify: `dashboard/src/i18n/locales/zh-CN/features/chat.json`
- Modify: `dashboard/src/i18n/locales/en-US/features/chat.json`
- Modify: `dashboard/src/i18n/locales/ru-RU/features/chat.json`

- [ ] **Step 1: 在 zh-CN locale 加 `interactiveChoice` 命名空间**

在文件**末尾**(最后一个 `}` 之前)追加:

```json
  "interactiveChoice": {
    "alreadyChosen": "已选择",
    "alreadyInput": "已输入",
    "ignored": "已忽略",
    "submit": "提交",
    "defaultPlaceholder": "或输入自定义内容..."
  },
```

> **说明**:用 2 空格缩进匹配既有 locale 文件风格;实际缩进请按文件现有结构(打开 `chat.json` 末尾确认)。

- [ ] **Step 2: 在 en-US locale 加相同 keys**

```json
  "interactiveChoice": {
    "alreadyChosen": "Chosen",
    "alreadyInput": "Custom input",
    "ignored": "Ignored",
    "submit": "Submit",
    "defaultPlaceholder": "Or type your own..."
  },
```

- [ ] **Step 3: 在 ru-RU locale 加相同 keys**

```json
  "interactiveChoice": {
    "alreadyChosen": "Выбрано",
    "alreadyInput": "Свой вариант",
    "ignored": "Игнорировано",
    "submit": "Отправить",
    "defaultPlaceholder": "Или введите свой вариант..."
  },
```

> **翻译备注**:俄语翻译为机器直译,后续如需润色,可在本任务外另开 PR。

- [ ] **Step 4: 跑 typecheck 确认 i18n 类型正确**

```bash
cd /d F:\github\Astrbot\.worktrees\feat-choice-box\dashboard
npm run typecheck
```

Expected: **无 error**(i18n 类型在 vue-i18n 是松散的,新增 key 不会引发类型错误)。

- [ ] **Step 5: Commit**

```bash
cd /d F:\github\Astrbot\.worktrees\feat-choice-box
git add dashboard/src/i18n/locales/
git commit -m "feat(dashboard): add interactiveChoice i18n keys for zh-CN/en-US/ru-RU"
```

---

### Task 6: 创建 InteractiveChoiceBox 组件

**Files:**
- Create: `dashboard/src/components/chat/message_list_comps/InteractiveChoiceBox.vue`

- [ ] **Step 1: 写组件完整代码**

完整内容写入 `dashboard/src/components/chat/message_list_comps/InteractiveChoiceBox.vue`:

```vue
<!--
  Author: elecvoid243
  Date: 2026-06-28
  Spec: docs/superpowers/specs/2026-06-28-dynamic-choice-box-rendering-design.md §4

  InteractiveChoiceBox: 动态渲染 LLM ask_user_choice 工具输出的选项框。
  4 状态机(pending / submitted_via_option / submitted_via_input / ignored) + a11y。
-->
<template>
  <div
    class="interactive-choice-box"
    :class="{
      'is-pending': state === 'pending',
      'is-submitted': state === 'submitted_via_option' || state === 'submitted_via_input',
      'is-ignored': state === 'ignored',
      'is-dark': isDark,
    }"
    :aria-live="state === 'ignored' ? 'polite' : undefined"
  >
    <!-- Header: title + prompt -->
    <div v-if="state !== 'ignored'" class="choice-header">
      <v-icon v-if="state === 'pending'" size="16" class="choice-header-icon">mdi-help-circle-outline</v-icon>
      <v-icon v-else size="16" class="choice-header-icon">mdi-check-circle</v-icon>
      <div class="choice-header-text">
        <div v-if="part.title" class="choice-title">{{ part.title }}</div>
        <div class="choice-prompt">{{ part.prompt }}</div>
      </div>
    </div>
    <div v-else class="choice-header choice-header--ignored">
      <v-icon size="16" class="choice-header-icon">mdi-eye-off-outline</v-icon>
      <span class="choice-ignored-label">{{ tm("interactiveChoice.ignored") }}</span>
      <span v-if="part.prompt" class="choice-prompt choice-prompt--muted">{{ part.prompt }}</span>
    </div>

    <!-- Pending: 选项按钮 + 自由输入 -->
    <template v-if="state === 'pending'">
      <div class="choice-options">
        <button
          v-for="opt in part.options"
          :key="opt.id"
          type="button"
          class="choice-option-button"
          :aria-label="ariaLabelForOption(opt)"
          @click="onOptionClick(opt.value)"
        >
          <span class="choice-option-label">{{ opt.label }}</span>
          <span v-if="opt.description" class="choice-option-description">
            {{ opt.description }}
          </span>
        </button>
      </div>
      <div class="choice-input-row">
        <textarea
          v-model="freeText"
          class="choice-input"
          :placeholder="inputPlaceholderResolved"
          rows="2"
          @keydown.enter.exact.prevent="onInputSubmit"
        />
        <v-btn
          class="choice-submit-button"
          color="primary"
          variant="tonal"
          size="small"
          :disabled="!freeText.trim()"
          @click="onInputSubmit"
        >
          {{ tm("interactiveChoice.submit") }}
        </v-btn>
      </div>
    </template>

    <!-- 已选择(已提交且来源是 option) -->
    <template v-else-if="state === 'submitted_via_option'">
      <div class="choice-result">
        <span class="choice-result-label">{{ tm("interactiveChoice.alreadyChosen") }}:</span>
        <span class="choice-result-value">{{ submittedLabel }}</span>
      </div>
    </template>

    <!-- 已输入(已提交且来源是 textarea) -->
    <template v-else-if="state === 'submitted_via_input'">
      <div class="choice-result">
        <span class="choice-result-label">{{ tm("interactiveChoice.alreadyInput") }}:</span>
        <span class="choice-result-value">{{ submittedLabel }}</span>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import { useModuleI18n } from "@/i18n/composables";
import type { InteractiveChoicePart, InteractiveChoiceOption } from "@/composables/parseInteractiveChoice";

const props = defineProps<{
  part: InteractiveChoicePart;
  isDark?: boolean;
  isIgnored?: boolean;
}>();

const emit = defineEmits<{
  submit: [text: string];
}>();

const { tm } = useModuleI18n("features/chat");

// ── 内部状态 ─────────────────────────────────────────────────
const submittedValue = ref<string | null>(null);
const submittedKind = ref<"option" | "input" | null>(null);  // 用于确定"已选择"还是"已输入"
const freeText = ref("");

// ── 派生状态机 ───────────────────────────────────────────────
type State = "pending" | "submitted_via_option" | "submitted_via_input" | "ignored";

const state = computed<State>(() => {
  if (props.isIgnored && submittedValue.value === null) return "ignored";
  if (submittedValue.value === null) return "pending";
  return submittedKind.value === "option" ? "submitted_via_option" : "submitted_via_input";
});

const submittedLabel = computed(() => {
  if (submittedValue.value === null) return "";
  if (submittedKind.value === "option") {
    // 找到 option.label 用于展示(value 是面向 LLM 的,label 才是面向用户的)
    const opt = props.part.options.find((o) => o.value === submittedValue.value);
    return opt?.label ?? submittedValue.value;
  }
  return submittedValue.value;
});

const inputPlaceholderResolved = computed(
  () => props.part.input_placeholder || tm("interactiveChoice.defaultPlaceholder"),
);

// ── 提交逻辑 ────────────────────────────────────────────────
function onOptionClick(value: string) {
  if (state.value !== "pending") return;  // 防御性:已提交态禁止
  submittedValue.value = value;
  submittedKind.value = "option";
  emit("submit", value);
}

function onInputSubmit() {
  const text = freeText.value.trim();
  if (!text || state.value !== "pending") return;
  submittedValue.value = text;
  submittedKind.value = "input";
  emit("submit", text);
}

function ariaLabelForOption(opt: InteractiveChoiceOption): string {
  return opt.description ? `${opt.label} — ${opt.description}` : opt.label;
}
</script>

<style scoped>
.interactive-choice-box {
  margin: 8px 0;
  padding: 12px 14px;
  border-radius: 10px;
  background: rgba(var(--v-theme-primary), 0.04);
  border: 1px solid rgba(var(--v-theme-primary), 0.18);
  max-width: min(560px, 100%);
}

.interactive-choice-box.is-submitted,
.interactive-choice-box.is-ignored {
  opacity: 0.6;
  background: transparent;
  border-color: rgba(var(--v-theme-on-surface), 0.12);
}

.interactive-choice-box.is-dark {
  background: rgba(var(--v-theme-primary), 0.08);
  border-color: rgba(var(--v-theme-primary), 0.28);
}

.choice-header {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 10px;
  color: rgb(var(--v-theme-on-surface));
}

.choice-header-icon {
  margin-top: 2px;
  color: rgb(var(--v-theme-primary));
  flex-shrink: 0;
}

.choice-header-text {
  min-width: 0;
  flex: 1;
}

.choice-title {
  font-size: 13px;
  font-weight: 600;
  line-height: 1.3;
  margin-bottom: 2px;
}

.choice-prompt {
  font-size: 14px;
  line-height: 1.45;
  word-break: break-word;
}

.choice-prompt--muted {
  font-size: 12px;
  opacity: 0.7;
}

.choice-header--ignored {
  color: rgba(var(--v-theme-on-surface), 0.6);
}

.choice-ignored-label {
  font-size: 13px;
  font-weight: 600;
  margin-right: 6px;
}

.choice-options {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 12px;
}

.choice-option-button {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  padding: 9px 12px;
  border: 1px solid rgba(var(--v-theme-primary), 0.32);
  border-radius: 8px;
  background: rgb(var(--v-theme-surface));
  color: rgb(var(--v-theme-on-surface));
  cursor: pointer;
  text-align: left;
  font: inherit;
  transition: background 0.12s ease, border-color 0.12s ease;
}

.choice-option-button:hover {
  background: rgba(var(--v-theme-primary), 0.08);
  border-color: rgb(var(--v-theme-primary));
}

.choice-option-label {
  font-size: 14px;
  font-weight: 500;
  line-height: 1.35;
}

.choice-option-description {
  font-size: 12px;
  line-height: 1.4;
  opacity: 0.7;
  white-space: pre-wrap;
}

.choice-input-row {
  display: flex;
  gap: 8px;
  align-items: flex-end;
}

.choice-input {
  flex: 1;
  min-height: 0;
  padding: 8px 10px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.18);
  border-radius: 8px;
  background: rgb(var(--v-theme-surface));
  color: rgb(var(--v-theme-on-surface));
  font: inherit;
  font-size: 13px;
  line-height: 1.4;
  resize: vertical;
  outline: none;
}

.choice-input:focus {
  border-color: rgb(var(--v-theme-primary));
}

.choice-submit-button {
  flex-shrink: 0;
  min-height: 36px;
  padding: 0 14px;
}

.choice-result {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
}

.choice-result-label {
  color: rgba(var(--v-theme-on-surface), 0.6);
  font-weight: 500;
}

.choice-result-value {
  color: rgb(var(--v-theme-on-surface));
  font-weight: 500;
  word-break: break-word;
}

.is-ignored .choice-option-button,
.is-submitted .choice-option-button {
  pointer-events: none;
  opacity: 0.6;
}
</style>
```

- [ ] **Step 2: 跑 typecheck 确认组件类型正确**

```bash
cd /d F:\github\Astrbot\.worktrees\feat-choice-box\dashboard
npm run typecheck
```

Expected: **无 error**。如出现 import 路径错误,检查 `@/i18n/composables` 与 `@/composables/parseInteractiveChoice` 实际是否解析(看项目 `tsconfig.json` 路径别名设置)。

- [ ] **Step 3: 跑 lint**

```bash
cd /d F:\github\Astrbot\.worktrees\feat-choice-box\dashboard
npm run lint
```

Expected: **无 error**(可能有 style 警告,可手动微调或加 `// eslint-disable-next-line` 注释)。

- [ ] **Step 4: Commit**

```bash
cd /d F:\github\Astrbot\.worktrees\feat-choice-box
git add dashboard/src/components/chat/message_list_comps/InteractiveChoiceBox.vue
git commit -m "feat(dashboard): add InteractiveChoiceBox component with 4-state machine"
```

---

### Task 7: 在 ChatMessageList 集成 InteractiveChoiceBox

**Files:**
- Modify: `dashboard/src/components/chat/ChatMessageList.vue` (v-else-if 链 + handler + ignored helper)

- [ ] **Step 1: import InteractiveChoiceBox**

在 ChatMessageList.vue 的 `<script setup>` import 块中(参考现有 `import ToolCallCard from "@/components/chat/message_list_comps/ToolCallCard.vue";`),新增:

```typescript
import InteractiveChoiceBox from "@/components/chat/message_list_comps/InteractiveChoiceBox.vue";
```

- [ ] **Step 2: 在 v-else-if 链中加分支**

定位到现有 v-else-if 链,寻找:

```vue
<div v-else-if="part.type === 'tool_call'" class="tool-call-block">
  ...
</div>
```

在 `</div>` 之后(也就是 tool_call 之后,`<div v-else class="unknown-part">` 之前),新增:

```vue
<InteractiveChoiceBox
  v-else-if="part.type === 'interactive_choice'"
  :part="part"
  :is-dark="isDark"
  :is-ignored="isInteractiveChoiceIgnored(msg)"
  @submit="onInteractiveChoiceSubmit"
/>
```

- [ ] **Step 3: 加 handler + ignored helper**

在 `<script setup>` 的 `function` 区域(参考 `isUserMessage` 位置),新增:

```typescript
function onInteractiveChoiceSubmit(text: string) {
  // 走标准 user message 通道(纯文本回传,见 spec §4.5)
  sendMessage({ text });
}

/**
 * 判定本 bot message 之后是否出现了 user message(用于 InteractiveChoiceBox 的 isIgnored)。
 * 基于 messages 数组顺序,不需要额外 store / event bus(spec §4.2 ignored 信号协议)。
 */
function isInteractiveChoiceIgnored(message: ChatRecord): boolean {
  const idx = props.messages.findIndex((m) => m === message);
  if (idx < 0) return false;
  for (let i = idx + 1; i < props.messages.length; i += 1) {
    if (isUserMessage(props.messages[i])) return true;
  }
  return false;
}
```

> **关于 `sendMessage`**:该函数在 `useMessages` composable 中已定义,需要 import 或通过 props/emit 间接使用。打开 `useMessages.ts` 查看 `send` / `sendMessage` 的实际暴露方式,如果未在 ChatMessageList 的 import 链中,需要从 `useMessages` 解构。

- [ ] **Step 4: 跑 typecheck + lint**

```bash
cd /d F:\github\Astrbot\.worktrees\feat-choice-box\dashboard
npm run typecheck
npm run lint
```

Expected: **无 error**。

- [ ] **Step 5: 跑 build 确认能编译**

```bash
cd /d F:\github\Astrbot\.worktrees\feat-choice-box\dashboard
npm run build 2>&1 | tail -30
```

Expected: build 成功,无 vue-tsc / vite 错误。

- [ ] **Step 6: Commit**

```bash
cd /d F:\github\Astrbot\.worktrees\feat-choice-box
git add dashboard/src/components/chat/ChatMessageList.vue
git commit -m "feat(dashboard): wire InteractiveChoiceBox into ChatMessageList with isIgnored protocol"
```

---

### Task 8: 手测冒烟(InteractiveChoiceBox 4 状态)

> **说明**:项目无 Vue 组件测试框架,本任务为手动验证。

- [ ] **Step 1: 启动 dev server**

```bash
cd /d F:\github\Astrbot\.worktrees\feat-choice-box\dashboard
npm run dev
```

Expected: Vite dev server 启动在 `http://localhost:3000`(或类似端口)。

- [ ] **Step 2: 在浏览器打开 webchat**

打开 AstrBot webchat UI,打开一个会话。

- [ ] **Step 3: 触发 InteractiveChoicePart part**

**临时方案**:在 `useMessages.normalizePartsInternal` 中**临时**插入一段硬编码 part 用于手测(后续移除):

```typescript
// 仅手测用:在 return truncateInteractiveChoice(unwrapped); 之后追加 ↓
if (Math.random() < 0.3) {  // 30% 概率出现,方便手测
  parts.push({
    type: "interactive_choice",
    prompt: "请选择下一步使用的模型:",
    title: "模型选择",
    options: [
      { id: "a", label: "GPT-4", description: "更强但更慢", value: "gpt-4" },
      { id: "b", label: "GPT-4 mini", value: "gpt-4-mini" },
      { id: "c", label: "本地模型", value: "local" },
    ],
    input_placeholder: "或输入自定义模型名",
  });
}
```

刷新页面,发任意消息,等待 bot 回复 → 30% 概率出现选项框。

- [ ] **Step 4: 验证 4 状态**

| 操作 | 期望视觉 |
|------|---------|
| 初始 | 选项框在 `pending` 态:3 个按钮 + textarea + 提交按钮 |
| 点 "GPT-4" 按钮 | 立即切到 `submitted_via_option` 态:"已选择: GPT-4",整卡灰显,按钮不可点 |
| (新会话)输入文本到 textarea,点提交 | 切到 `submitted_via_input` 态:"已输入: <文本>" |
| (新会话)在 ChatInput 自己打字发消息 | 选项框变 `ignored` 态:显示"已忽略"标签 |
| (新会话)同一 message 内有 2 个 interactive_choice part(临时硬编码) | 两个选项框独立渲染,各自 `pending` |

- [ ] **Step 5: 验证非法 part 降级**

把临时硬编码改为非法形态:

```typescript
parts.push({
  type: "interactive_choice",
  prompt: "缺 options",
} as any);
```

刷新 + 触发,期望:**降级为 `unknown-part`**,显示 JSON 文本(原 `unknown-part` 兜底)。

- [ ] **Step 6: 验证 plain 文本 + 嵌入式 JSON 解包**

把临时硬编码改为:

```typescript
parts.push({
  type: "plain",
  text: JSON.stringify({
    type: "interactive_choice",
    prompt: "解包测试",
    options: [
      { id: "x", label: "X", value: "x" },
      { id: "y", label: "Y", value: "y" },
    ],
  }),
});
```

期望:选项框正常渲染(`normalizePartsInternal` 解包成功)。

- [ ] **Step 7: 验证 JSON.parse 失败回退**

把临时硬编码改为:

```typescript
parts.push({ type: "plain", text: '{ "type": "interactive_choice", "broken' });
```

期望:**保留原 plain 文本**继续渲染(不是 `unknown-part`),且浏览器控制台有 warn。

- [ ] **Step 8: 移除手测临时硬编码**

**重要**:把 Task 8 Step 3 临时插入的代码完全移除,确认 `normalizePartsInternal` 回到原状。

- [ ] **Step 9: Commit(可选,如临时代码已 stash)**

如果 Step 8 是直接修改后 commit,跳过本步;如改用 stash,需要 pop 后确认 working tree 干净。

- [ ] **Step 10: 跑全套单测 + typecheck + lint 收尾**

```bash
cd /d F:\github\Astrbot\.worktrees\feat-choice-box\dashboard
node --test tests/parseInteractiveChoice.test.mjs
npm run typecheck
npm run lint
npm run build 2>&1 | tail -10
```

Expected: **27 tests pass**,**无 error**。

---

## Chunk 3: ask_user_choice 插件脚手架(独立仓库)

> **本 Chunk 不在前述 worktree 中**——`astrbot_plugin_choice_ui` 是独立仓库,见 spec §5.3。**做法**:在 `AstrbotWorkSpace` 下另建目录(参考 AGENTS.md "默认工作目录"),或 clone 一个新仓库。

### Task 9: 准备插件目录

**Files:**
- Create directory: `D:\AstrbotWorkSpace\astrbot_plugin_choice_ui\`(或合适路径)

- [ ] **Step 1: 创建插件目录结构**

```bash
mkdir "D:\AstrbotWorkSpace\astrbot_plugin_choice_ui"
cd "D:\AstrbotWorkSpace\astrbot_plugin_choice_ui"
mkdir choice_ui  # Python package
```

- [ ] **Step 2: 初始化 git**

```bash
cd "D:\AstrbotWorkSpace\astrbot_plugin_choice_ui"
git init
git checkout -b main
```

- [ ] **Step 3: 创建 metadata.yaml**

完整内容写入 `metadata.yaml`:

```yaml
# Author: elecvoid243
# Date: 2026-06-28
# Spec: docs/superpowers/specs/2026-06-28-dynamic-choice-box-rendering-design.md §5.3 + §11
name: astrbot_plugin_choice_ui
display_name: Choice UI
desc: 让 LLM 通过 ask_user_choice 工具向用户呈现可交互选项框(单选 + 自由输入)
version: v0.1.0
author: elecvoid243
repo: https://github.com/elecvoid243/astrbot_plugin_choice_ui
astrbot_version: ">=4.16,<5"
```

- [ ] **Step 4: 创建 .gitignore**

完整内容写入 `.gitignore`:

```
__pycache__/
*.pyc
.idea/
.vscode/
dist/
build/
*.egg-info/
```

---

### Task 10: 实现 choice_tool.py

**Files:**
- Create: `D:\AstrbotWorkSpace\astrbot_plugin_choice_ui\choice_ui\choice_tool.py`

- [ ] **Step 1: 写完整 Python 代码**

完整内容写入 `choice_ui\choice_tool.py`(内容同 spec §11.1,这里省略重复粘贴,直接复制 spec §11.1 即可)。

- [ ] **Step 2: 写 main.py 入口**

完整内容写入 `choice_ui\main.py`:

```python
"""astrbot_plugin_choice_ui 插件入口。

注册 AskUserChoiceTool 到 AstrBot LLM 工具列表。
"""

from __future__ import annotations

from astrbot.api import Plugin

from .choice_tool import AskUserChoiceTool


class ChoiceUIPlugin(Plugin):
    async def initialize(self):
        self.context.add_llm_tool(AskUserChoiceTool())
```

- [ ] **Step 3: 写 README.md**

完整内容写入 `README.md`:

```markdown
# astrbot_plugin_choice_ui

让 LLM 通过 `ask_user_choice` 工具向用户呈现可交互选项框。

## 安装

将本目录放置到 AstrBot 的 `plugins/` 目录下,重启 AstrBot。

## 使用

LLM 会在需要人类审批/选择时自动调用 `ask_user_choice` 工具。工具参数:
- `prompt` (必填):提问文案
- `options` (必填):2-10 个候选选项,每项含 `id` / `label` / `value`(可选 `description`)
- `title` (可选):选项框标题
- `input_placeholder` (可选):自由输入框占位符

## 前端要求

AstrBot WebChat 前端需 >= spec 日期的 dashboard 版本(支持 `interactive_choice` part 渲染)。

## Spec

见上游 AstrBot spec:`docs/superpowers/specs/2026-06-28-dynamic-choice-box-rendering-design.md` §11
```

- [ ] **Step 4: Commit 插件仓库初始版本**

```bash
cd "D:\AstrbotWorkSpace\astrbot_plugin_choice_ui"
git add .
git commit -m "feat: initial ask_user_choice tool scaffolding"
```

---

### Task 11: 端到端验证(可选,需真实 AstrBot 环境)

> **本 Task 是可选的**,需在本地有完整 AstrBot dev 环境才能跑。如果只是验证 dashboard 部分,可跳过。

- [ ] **Step 1: 链接插件到 AstrBot dev 环境**

```bash
# 软链接(假设 AstrBot 在 F:\github\Astrbot)
ln -s "D:\AstrbotWorkSpace\astrbot_plugin_choice_ui" "F:\github\Astrbot\astrbot\plugins\astrbot_plugin_choice_ui"
```

- [ ] **Step 2: 启动 AstrBot**

```bash
cd /d F:\github\Astrbot
uv run main.py
```

- [ ] **Step 3: 在 webchat 触发 LLM 调 ask_user_choice**

通过 system prompt 或 persona 引导 LLM 调工具,例如:

```
当用户问"删除这个文件"时,你必须先调 ask_user_choice 工具确认。
```

- [ ] **Step 4: 验证端到端**

| 操作 | 期望 |
|------|------|
| LLM 调工具 | 前端渲染选项框(见 Task 8 验证) |
| 用户点选项 / 输入文本 | 后端收到纯文本 user message(检查 AstrBot 日志) |
| LLM 收到 user message | 正确理解是上一步的选项结果(从对话上下文) |
| 多次调工具 | 每次独立渲染,各自 pending |

---

## Final Checks

- [ ] **所有单测通过**

```bash
cd /d F:\github\Astrbot\.worktrees\feat-choice-box\dashboard
node --test tests/parseInteractiveChoice.test.mjs
```

Expected: **27 tests pass**。

- [ ] **Typecheck + lint 干净**

```bash
cd /d F:\github\Astrbot\.worktrees\feat-choice-box\dashboard
npm run typecheck
npm run lint
```

Expected: **无 error**。

- [ ] **Build 成功**

```bash
cd /d F:\github\Astrbot\.worktrees\feat-choice-box\dashboard
npm run build 2>&1 | tail -10
```

Expected: build 成功。

- [ ] **Worktree commits 干净**

```bash
cd /d F:\github\Astrbot\.worktrees\feat-choice-box
git log --oneline master..HEAD
```

Expected: 4-5 个 commit(解析层 / i18n / 组件 / 集成 / 可选手测代码清理),都遵循 conventional commits 格式。

- [ ] **Worktree 合并回 master 或开 PR(由执行者选择)**

参考 `superpowers:finishing-a-development-branch` skill。

---

## Notes

- **本计划严格遵循 spec** —— 任何与 spec 不一致的实现,先回到 spec review,再修改本计划。
- **未涉及**:`MessageList.vue` (deprecated,见 spec §5.2)、多选 / 嵌套 / 风险等级(显式 non-goals,见 spec §1)、非 WebChat 平台适配、OpenAPI client 重新生成(本功能不引入新的后端 API)。
- **关于 v-html / markdown description**:spec §4.7 明确禁用 v-html;本计划组件所有动态文本走 `{{ }}` 插值。
- **Plugin 测试**:Task 10 完成后可加 `pytest tests/` 验证 `AskUserChoiceTool.call` 行为(本计划 v1 范围外,后续 PR 可加)。
