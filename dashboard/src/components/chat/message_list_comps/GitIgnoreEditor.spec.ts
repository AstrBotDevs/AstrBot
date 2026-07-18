// Author: elecvoid243, 2026-07-17
// 2026-07-18: rewrote for the new initial-content / save(payload)
// contract. Uses a CodeMirrorEditor stub mirroring the real contract
// (uncontrolled buffer, transition-only dirty-change, getValue
// expose); dirtiness is driven by typing into the stub's textarea.
import { describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";

// Self-contained i18n mock (returns the key + k=v params).
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

// CodeMirrorEditor stub: mirrors the real component's contract
// (uncontrolled buffer, transition-only dirty-change, getValue expose)
// while staying a cheap <textarea> for happy-dom. Defined INSIDE the
// factory because vi.mock is hoisted above top-level consts (TDZ).
vi.mock("./CodeMirrorEditor.vue", async () => {
  const { computed, defineComponent, ref, watch } = await import("vue");
  const CodeMirrorEditorStub = defineComponent({
    props: {
      modelValue: { type: String, default: "" },
      filePath: { type: String, default: "" },
    },
    emits: ["update:modelValue", "dirty-change"],
    setup(props, { emit, expose }) {
      const buffer = ref(props.modelValue);
      const dirty = computed(() => buffer.value !== props.modelValue);
      watch(dirty, (d) => emit("dirty-change", d));
      function onInput(e: Event) {
        const v = (e.target as HTMLTextAreaElement).value;
        buffer.value = v;
        emit("update:modelValue", v);
      }
      expose({ getValue: () => buffer.value, focus: () => {} });
      return { buffer, onInput };
    },
    template: '<textarea :value="buffer" @input="onInput" />',
  });
  return { default: CodeMirrorEditorStub };
});

import GitIgnoreEditor from "./GitIgnoreEditor.vue";

const vuetifyStubs = {
  "v-icon": { template: "<i />" },
  // Real <button> so click + disabled flow through. `emits: ["click"]`
  // prevents the parent's @click from double-firing (fall-through +
  // $emit).
  "v-btn": {
    props: ["disabled", "loading"],
    emits: ["click"],
    template:
      '<button :disabled="disabled || loading" @click="$emit(\'click\')"><slot /></button>',
  },
};

const PREFIX = "spcodeProjectLoad.diffSidebar.gitWorkflow.gitignore";

function mountEditor(props: Record<string, unknown> = {}) {
  return mount(GitIgnoreEditor, {
    props: {
      initialContent: "",
      isNewFile: false,
      isSaving: false,
      saveError: null,
      loadError: null,
      ...props,
    },
    global: { stubs: vuetifyStubs },
  });
}

async function setEditorDirty(w: ReturnType<typeof mountEditor>): Promise<void> {
  // Type a real keystroke into the stubbed CodeMirrorEditor: the
  // input event updates the editor's internal buffer, the dirty
  // computed flips, and dirty-change fires to the parent.
  const ta = w.find("textarea");
  await ta.setValue("x");
  await w.vm.$nextTick();
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
    const w = mountEditor();
    await w.find('[data-testid="gitignore-cancel"]').trigger("click");
    expect(w.emitted("cancel")).toBeTruthy();
  });

  it("dirty cancel arms confirmation first, emits on second click", async () => {
    const w = mountEditor();
    await setEditorDirty(w);
    const btn = w.find('[data-testid="gitignore-cancel"]');
    await btn.trigger("click");
    expect(w.emitted("cancel")).toBeFalsy();
    expect(w.text()).toContain(`${PREFIX}.confirmDiscard`);
    await btn.trigger("click");
    expect(w.emitted("cancel")).toBeTruthy();
  });

  it("save click emits save WITH the editor buffer as payload", async () => {
    const w = mountEditor();
    await setEditorDirty(w);
    const saveBtn = w.find('[data-testid="gitignore-save"]');
    expect((saveBtn.element as HTMLButtonElement).disabled).toBe(false);
    await saveBtn.trigger("click");
    expect(w.emitted("save")).toEqual([["x"]]);
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
