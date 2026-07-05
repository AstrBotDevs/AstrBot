// Author: elecvoid243
// Date: 2026-07-05
// Plan: docs/superpowers/plans/2026-07-05-interactive-choice-history-roundtrip.md
// §2.4 Amendment F — extract the `normalizePartsInternal` helper
// from `useMessages.ts` into its own leaf module so the unit test
// (which runs under bare node) can exercise the
// ask_user_choice history-reload filter without pulling in
// `@/api` (Vite alias, unresolvable from node).
//
// All other behaviour of `normalizePartsInternal` is preserved
// bit-for-bit; only the location has changed. The export is named
// `normalizeMessageParts` to match the existing public surface.

import {
  isInteractiveChoicePayload,
  validateInteractiveChoice,
  truncateInteractiveChoice,
} from "./parseInteractiveChoice.ts";
import { ASK_USER_CHOICE_TOOL_NAME } from "./askUserChoiceToolFilter.ts";

export interface MessagePart {
  type: string;
  [key: string]: unknown;
}

export function normalizeMessageParts(parts: unknown): MessagePart[] {
  if (typeof parts === "string") {
    return parts ? [{ type: "plain", text: parts }] : [];
  }
  if (!Array.isArray(parts)) return [];
  // Author: elecvoid243
  // Date: 2026-07-05
  // Plan: docs/superpowers/plans/2026-07-05-interactive-choice-history-roundtrip.md
  // §2.4 Amendment F — Defensively strip `ask_user_choice` tool_call
  // parts while loading history. New writes (post-fix) will not
  // contain them (see chat_service._store_tool_call), but
  // pre-existing data may still have them and the backend cannot
  // retroactively rewrite stored messages.
  const hasInteractiveChoice = parts.some(
    (p) =>
      p &&
      typeof p === "object" &&
      (p as { type?: unknown }).type === "interactive_choice",
  );
  // Map-and-filter pipeline: first normalise each part, then drop the
  // `tool_call` parts belonging to `ask_user_choice` when the
  // message also carries an `interactive_choice` part.
  const normalized = parts.map((part: any) => {
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
    // ① v1.0 schema:InteractiveChoicePart 已通过 SSE 顶层 type 到达,
    //    不再解 plain 文本/拆 tool_call(见 parseInteractiveChoice 模块注释)。
    // ② 校验 + 截断(防御性兜底,后端已截过一遍)
    if (isInteractiveChoicePayload(part)) {
      if (!validateInteractiveChoice(part)) {
        // 非法:降级为 plain JSON(spec §2.3 步骤 2),与 v0.3 行为一致
        return { type: "plain", text: JSON.stringify(part) };
      }
      return truncateInteractiveChoice(part);
    }
    return { ...part };
  });
  if (!hasInteractiveChoice) return normalized;
  // Defensive filter — drop ask_user_choice tool_call entries from
  // the historical payload so pre-fix messages (saved before the
  // backend filter landed) do not show a phantom "tool" entry next
  // to the InteractiveChoiceBox after a hard refresh.
  return normalized.flatMap((part) => {
    if (!part || (part as { type?: unknown }).type !== "tool_call") {
      return [part];
    }
    const rawToolCalls = (part as { tool_calls?: unknown }).tool_calls;
    if (!Array.isArray(rawToolCalls)) return [part];
    const filteredToolCalls = rawToolCalls.filter(
      (tc) => !tc || tc.name !== ASK_USER_CHOICE_TOOL_NAME,
    );
    if (filteredToolCalls.length === rawToolCalls.length) return [part];
    if (filteredToolCalls.length === 0) return [];
    return [{ ...(part as object), tool_calls: filteredToolCalls }];
  });
}
