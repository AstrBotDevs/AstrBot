// Author: askuserchoice_f1_impl
// Date: 2026-07-19
//
// Completeness test for the `interactiveChoice.cancelled` i18n key
// (ask_user_choice v1.2 dashboard work — Phase 2 / Task F1).
//
// The new "已取消" / "Cancelled" / "Отменено" key is consumed by the
// InteractiveChoiceBox state machine once a server-side
// `interactive_choice_resolved { reason: "cancelled" }` SSE event
// arrives (see Phase 1 plugin PR #1). This test pins that all three
// locale tables ship the key so the box never renders a
// "[MISSING: interactiveChoice.cancelled]" placeholder in any
// supported UI language.

import { describe, expect, it } from "vitest";
import chatZh from "./locales/zh-CN/features/chat.json";
import chatEn from "./locales/en-US/features/chat.json";
import chatRu from "./locales/ru-RU/features/chat.json";

const localizations: Array<[string, Record<string, unknown>]> = [
  ["zh-CN", chatZh as unknown as Record<string, unknown>],
  ["en-US", chatEn as unknown as Record<string, unknown>],
  ["ru-RU", chatRu as unknown as Record<string, unknown>],
];

describe("interactiveChoice i18n completeness", () => {
  for (const [locale, dict] of localizations) {
    it(`${locale} defines interactiveChoice.cancelled`, () => {
      const interactiveChoice = dict.interactiveChoice as
        | Record<string, unknown>
        | undefined;
      expect(
        interactiveChoice,
        `${locale} missing interactiveChoice block`,
      ).toBeDefined();
      expect(
        typeof interactiveChoice?.cancelled,
        `${locale} missing interactiveChoice.cancelled string`,
      ).toBe("string");
    });
  }
});
