// Author: elecvoid243
// Date: 2026-07-02
// Spec: docs/superpowers/specs/2026-07-02-blocking-interactive-choice-design.md §5.1
//
// 纯函数模块:校验 + 截断 InteractiveChoicePart。v1.0 走 SSE 顶层 type,
// 不再解 plain 文本/拆 tool_call,删除相关辅助函数。

export interface InteractiveChoiceOption {
  id: string;
  label: string;
  description?: string;
  /** 旧 plugin 字段(v0.3),新代码忽略 */
  value?: string;
}

export interface InteractiveChoicePart {
  type: "interactive_choice";
  /** v1.0 必填:后端生成的 request_id,提交时用作路由 */
  request_id: string;
  prompt: string;
  title?: string;
  options: InteractiveChoiceOption[];
  input_placeholder?: string;
  /** v1.0 可选:unix ts,前端可显示倒计时 */
  expires_at?: number;
  [key: string]: unknown;
}

export function isInteractiveChoicePayload(value: unknown): value is InteractiveChoicePart {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const obj = value as Record<string, unknown>;
  return obj.type === "interactive_choice";
}

export function validateInteractiveChoice(obj: unknown): boolean {
  if (!isInteractiveChoicePayload(obj)) return false;
  const part = obj as Record<string, unknown>;
  if (typeof part.request_id !== "string" || !part.request_id.trim()) return false;
  if (typeof part.prompt !== "string" || !part.prompt.trim()) return false;
  if (!Array.isArray(part.options) || part.options.length < 2) return false;
  const seen = new Set<string>();
  for (const opt of part.options) {
    if (!opt || typeof opt !== "object") return false;
    const o = opt as Record<string, unknown>;
    if (typeof o.id !== "string" || !o.id.trim()) return false;
    if (typeof o.label !== "string" || !o.label.trim()) return false;
    if (seen.has(o.id)) return false;
    seen.add(o.id);
  }
  return true;
}

export function truncateInteractiveChoice(part: InteractiveChoicePart): InteractiveChoicePart {
  const LIMITS = { PROMPT_MAX: 200, TITLE_MAX: 30, LABEL_MAX: 30, DESC_MAX: 200, PLACEHOLDER_MAX: 60 };
  let mutated = false;
  const out: InteractiveChoicePart = { ...part };
  if (out.prompt.length > LIMITS.PROMPT_MAX) {
    out.prompt = out.prompt.slice(0, LIMITS.PROMPT_MAX);
    mutated = true;
  }
  if (typeof out.title === "string" && out.title.length > LIMITS.TITLE_MAX) {
    out.title = out.title.slice(0, LIMITS.TITLE_MAX);
    mutated = true;
  }
  if (typeof out.input_placeholder === "string" && out.input_placeholder.length > LIMITS.PLACEHOLDER_MAX) {
    out.input_placeholder = out.input_placeholder.slice(0, LIMITS.PLACEHOLDER_MAX);
    mutated = true;
  }
  if (Array.isArray(out.options)) {
    const newOpts: InteractiveChoiceOption[] = [];
    for (const opt of out.options) {
      const o: InteractiveChoiceOption = { ...opt };
      if (o.label.length > LIMITS.LABEL_MAX) {
        o.label = o.label.slice(0, LIMITS.LABEL_MAX);
        mutated = true;
      }
      if (typeof o.description === "string" && o.description.length > LIMITS.DESC_MAX) {
        o.description = o.description.slice(0, LIMITS.DESC_MAX);
        mutated = true;
      }
      newOpts.push(o);
    }
    out.options = newOpts;
  }
  return mutated ? out : part;
}

export function getOptionSubmitText(opt: InteractiveChoiceOption): string {
  if (typeof opt.value === "string" && opt.value.length > 0) return opt.value;
  const id = typeof opt.id === "string" ? opt.id : "";
  const label = typeof opt.label === "string" ? opt.label : "";
  if (id && label) return `${id}. ${label}`;
  if (label) return label;
  return id;
}

/**
 * Recover an `InteractiveChoicePart` from a plain-text part whose
 * `text` field accidentally contains the OLD plugin wire format.
 *
 * Background: the round-1 fix changed the plugin to emit
 * `type: "plain" + chain_type: "interactive_choice"` (data = JSON
 * string of the v1.0 envelope). Pre-fix `BotMessageAccumulator.add_plain`
 * had no such branch, so the JSON string was *appended to the bot
 * message's pending text* and persisted as a plain-text part. After
 * the chat_service is upgraded, NEW conversations persist a proper
 * `interactive_choice` part instead — but OLD conversations still
 * have the JSON in their plain-text parts.
 *
 * This helper is the defensive one-time migration that turns those
 * stale plain-text parts into real `InteractiveChoicePart`s so a hard
 * refresh renders the box at the original chronological position
 * (not at the page tail via orphan-injection).
 *
 * Args:
 *   text: The plain text to scan. The function only fires when the
 *     text actually contains a wire-format JSON object — narrative
 *     text is left alone.
 *
 * Returns:
 *   The recovered `InteractiveChoicePart` (validated + truncated) or
 *   `null` when no wire-format JSON is present.
 */
export function tryRecoverInteractiveChoiceFromPlainText(
  text: string,
): InteractiveChoicePart | null {
  if (typeof text !== "string" || !text) return null;
  // Scan for the wire format by looking for a `{` that opens a
  // JSON object containing both `"request_id"` and `"spec"`. The
  // LLM's narrative never produces both keys, so this is safe.
  const startIdx = text.indexOf('{"request_id"');
  if (startIdx < 0) return null;
  // Walk to the matching closing brace so a trailing `}` from
  // unrelated LLM text doesn't break the parse.
  let depth = 0;
  let endIdx = -1;
  for (let i = startIdx; i < text.length; i += 1) {
    const ch = text[i];
    if (ch === "{") depth += 1;
    else if (ch === "}") {
      depth -= 1;
      if (depth === 0) {
        endIdx = i;
        break;
      }
    }
  }
  if (endIdx < 0) return null;
  const jsonStr = text.slice(startIdx, endIdx + 1);
  let parsed: unknown;
  try {
    parsed = JSON.parse(jsonStr);
  } catch {
    return null;
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    return null;
  }
  const obj = parsed as Record<string, unknown>;
  const spec = obj.spec;
  if (!isInteractiveChoicePayload(spec)) return null;
  const outerRequestId =
    typeof obj.request_id === "string" ? obj.request_id.trim() : "";
  if (!outerRequestId) return null;
  const part: InteractiveChoicePart = {
    ...(spec as InteractiveChoicePart),
    request_id: outerRequestId,
  };
  if (typeof obj.expires_at === "number") {
    part.expires_at = obj.expires_at;
  } else {
    delete part.expires_at;
  }
  if (!validateInteractiveChoice(part)) return null;
  return truncateInteractiveChoice(part);
}

/**
 * Migrate a flat parts array in place: any plain-text part whose
 * text accidentally contains the OLD wire format is replaced by a
 * recovered `interactive_choice` part.
 *
 * Returns the same array reference (mutated in place) for ergonomic
 * chaining. Plain-text parts that don't match the wire format are
 * left untouched. Non-plain parts are also untouched.
 *
 * Idempotent — running it twice is a no-op.
 */
export function migrateInteractiveChoicePartsInPlace<
  T extends { type: string; text?: unknown },
>(parts: T[]): T[] {
  if (!Array.isArray(parts)) return parts;
  for (let i = 0; i < parts.length; i += 1) {
    const part = parts[i];
    if (
      part &&
      part.type === "plain" &&
      typeof (part as { text?: unknown }).text === "string"
    ) {
      const recovered = tryRecoverInteractiveChoiceFromPlainText(
        (part as { text: string }).text,
      );
      if (recovered) {
        parts[i] = recovered as unknown as T;
      }
    }
  }
  return parts;
}

/**
 * Convert a raw SSE payload from `webchat_queue_mgr.back_queue` into a
 * fully-validated, truncated `InteractiveChoicePart` ready for
 * `useInteractiveChoiceStore().addChoice(...)`.
 *
 * Wire format (verified from `astrbot_plugin_ask_user_choice/
 * ask_user_choice_tool.py::_push_to_webchat_back_queue`):
 *
 *   {
 *     "type": "interactive_choice",
 *     "data": {
 *       "request_id": "<uuid>",
 *       "spec": {
 *         "type": "interactive_choice",
 *         "prompt": "<text>",
 *         "options": [{ "id": "<id>", "label": "<label>" }, ...]
 *       },
 *       "expires_at": <unix ts>
 *     }
 *   }
 *
 * Returns `null` when the payload does not match the wire format, the
 * spec fails validation, or the request_id is missing/empty. The
 * returned part is already run through :func:`truncateInteractiveChoice`
 * so callers can hand it straight to the Pinia store.
 */
export function interactiveChoicePartFromSsePayload(
  payload: unknown,
): InteractiveChoicePart | null {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    return null;
  }
  const root = payload as Record<string, unknown>;
  if (root.type !== "interactive_choice") return null;
  const data = root.data;
  if (!data || typeof data !== "object" || Array.isArray(data)) return null;
  const dataObj = data as Record<string, unknown>;
  const spec = dataObj.spec;
  if (!isInteractiveChoicePayload(spec)) return null;
  const specPart = spec as InteractiveChoicePart;

  // `data.request_id` is the authoritative id (matches the registry
  // entry the backend will resolve on submit). Fall back to
  // `spec.request_id` only if the outer envelope omits it.
  const outerId =
    typeof dataObj.request_id === "string" && dataObj.request_id.trim()
      ? dataObj.request_id
      : "";
  const innerId =
    typeof specPart.request_id === "string" ? specPart.request_id : "";
  const requestId = outerId || innerId;

  const part: InteractiveChoicePart = {
    ...specPart,
    request_id: requestId,
  };
  if (typeof dataObj.expires_at === "number") {
    part.expires_at = dataObj.expires_at;
  } else {
    delete part.expires_at;
  }
  if (!validateInteractiveChoice(part)) return null;
  return truncateInteractiveChoice(part);
}
