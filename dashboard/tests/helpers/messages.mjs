import { vi } from "vitest";
import { inject, ref } from "vue";
import { chatApi } from "../../src/api/v1.ts";
import { useMessages } from "../../src/composables/useMessages.ts";
import { viewActionKey } from "../../src/utils/chatViews.ts";
import { mountComposable } from "./mountComposable.mjs";

export function historyResponse(history = [], overrides = {}) {
  return {
    data: {
      status: "ok",
      data: {
        history,
        threads: [],
        active_runs: [],
        page: 1,
        page_size: 50,
        total: history.length,
        has_more: false,
        ...overrides,
      },
    },
  };
}

export function mountMessages(options = {}) {
  let action;
  const currentSessionId = ref("session");
  const getSession = vi.spyOn(chatApi, "getSession").mockResolvedValue(historyResponse());
  const app = mountComposable(() => useMessages({ currentSessionId, ...options }), {
    childSetup: () => {
      action = inject(viewActionKey);
    },
  });
  return { ...app, messages: app.result, action, currentSessionId, getSession };
}
