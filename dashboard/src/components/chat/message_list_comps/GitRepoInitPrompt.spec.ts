// Author: elecvoid243, 2026-07-16
import { describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";

// `useModuleI18n` is the entry point used by the SUT; mock it so the test
// is self-contained and does not depend on the real translation tables.
// The mock returns the key plus any params as `k=v` pairs so assertions
// about rendered text can verify the substitution happened.
const tmMock = vi.fn(
  (key: string, params?: Record<string, string | number>) => {
    if (!params) return key;
    return Object.entries(params).reduce(
      (acc, [k, v]) => `${acc} ${k}=${String(v)}`,
      key,
    );
  },
);
vi.mock("@/i18n/composables", () => ({
  useModuleI18n: () => ({ tm: tmMock, getRaw: vi.fn() }),
}));

import GitRepoInitPrompt from "./GitRepoInitPrompt.vue";

// Vuetify is not loaded in unit tests; stub the components we use so
// the test output stays free of "Failed to resolve component" warnings.
const vuetifyStubs = {
  "v-icon": { template: "<i />" },
  "v-progress-circular": { template: "<i />" },
};

function mountPrompt(props: Record<string, unknown> = {}) {
  return mount(GitRepoInitPrompt, {
    props: {
      directory: "D:/tmp",
      isSubmitting: false,
      lastError: null,
      ...props,
    },
    global: { stubs: vuetifyStubs },
  });
}

describe("GitRepoInitPrompt", () => {
  it("renders the directory path in the body", () => {
    const w = mountPrompt({ directory: "D:/tmp/foo" });
    expect(w.text()).toContain("D:/tmp/foo");
  });

  it("emits 'confirm' when the primary button is clicked", async () => {
    const w = mountPrompt();
    await w.find('[data-testid="repo-init-confirm"]').trigger("click");
    expect(w.emitted("confirm")).toBeTruthy();
  });

  it("emits 'cancel' when the secondary button is clicked", async () => {
    const w = mountPrompt();
    await w.find('[data-testid="repo-init-cancel"]').trigger("click");
    expect(w.emitted("cancel")).toBeTruthy();
  });

  it("disables both buttons while isSubmitting is true", () => {
    const w = mountPrompt({ isSubmitting: true });
    const btns = w.findAll("button");
    expect(btns.length).toBeGreaterThan(0);
    expect(btns.every((b) => b.attributes("disabled") !== undefined)).toBe(true);
  });

  it("renders lastError.stderr when provided", () => {
    const w = mountPrompt({
      lastError: { reason: "directory_not_empty", stderr: "fatal: not empty" },
    });
    expect(w.find('[data-testid="repo-init-error"]').exists()).toBe(true);
    expect(w.text()).toContain("fatal: not empty");
  });

  it("does not render the lastError block when lastError is null", () => {
    const w = mountPrompt({ lastError: null });
    expect(w.find('[data-testid="repo-init-error"]').exists()).toBe(false);
  });
});
