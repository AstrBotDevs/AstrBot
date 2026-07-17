// Author: elecvoid243, 2026-07-17
import { describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";

// Same self-contained i18n mock as GitRepoInitPrompt.spec.ts: returns
// the key (plus k=v params) so text assertions verify substitution.
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

import GitIgnoreEditor from "./GitIgnoreEditor.vue";

const vuetifyStubs = {
  "v-icon": { template: "<i />" },
  // Render a real <button> so click + disabled flow through.
  // `emits: ["click"]` is REQUIRED: without it the parent's @click
  // listener falls through onto the native <button> as an attrs
  // listener AND fires via $emit — double-invoking the handler.
  "v-btn": {
    props: ["disabled", "loading"],
    emits: ["click"],
    template:
      '<button :disabled="disabled || loading" @click="$emit(\'click\')"><slot /></button>',
  },
  // ShikiEditor is a heavy async child (Shiki highlighter); stub it.
  ShikiEditor: { props: ["modelValue", "filePath"], template: "<div />" },
};

const PREFIX = "spcodeProjectLoad.diffSidebar.gitWorkflow.gitignore";

function mountEditor(props: Record<string, unknown> = {}) {
  return mount(GitIgnoreEditor, {
    props: {
      modelValue: "",
      isNewFile: false,
      isDirty: false,
      isSaving: false,
      saveError: null,
      loadError: null,
      ...props,
    },
    global: { stubs: vuetifyStubs },
  });
}

describe("GitIgnoreEditor", () => {
  it("renders the .gitignore title and the new-file hint when isNewFile", () => {
    const w = mountEditor({ isNewFile: true });
    expect(w.text()).toContain(".gitignore");
    expect(w.text()).toContain(`${PREFIX}.newFileHint`);
  });

  it("hides the new-file hint for an existing file", () => {
    const w = mountEditor({ isNewFile: false });
    expect(w.text()).not.toContain(`${PREFIX}.newFileHint`);
  });

  it("clean cancel emits cancel on the first click", async () => {
    const w = mountEditor({ isDirty: false });
    await w.find('[data-testid="gitignore-cancel"]').trigger("click");
    expect(w.emitted("cancel")).toBeTruthy();
  });

  it("dirty cancel arms confirmation first, emits on second click", async () => {
    const w = mountEditor({ isDirty: true });
    const btn = w.find('[data-testid="gitignore-cancel"]');
    await btn.trigger("click");
    expect(w.emitted("cancel")).toBeFalsy();
    expect(w.text()).toContain(`${PREFIX}.confirmDiscard`);
    await btn.trigger("click");
    expect(w.emitted("cancel")).toBeTruthy();
  });

  it("save click emits save", async () => {
    const w = mountEditor({ isDirty: true });
    await w.find('[data-testid="gitignore-save"]').trigger("click");
    expect(w.emitted("save")).toBeTruthy();
  });

  it("renders the inline save error bar", () => {
    const w = mountEditor({ saveError: "boom" });
    expect(w.find('[data-testid="gitignore-error"]').text()).toContain("boom");
  });

  it("load error swaps the body for a retry button", async () => {
    const w = mountEditor({ loadError: "nope" });
    expect(w.text()).toContain("nope");
    await w.find('[data-testid="gitignore-retry"]').trigger("click");
    expect(w.emitted("retry")).toBeTruthy();
  });
});
