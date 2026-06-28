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