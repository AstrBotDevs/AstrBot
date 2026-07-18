// Author: elecvoid243, 2026-07-18
// CodeMirrorEditor unit tests: @codemirror/state is mocked to throw on
// import, forcing the component's plain-textarea fallback path. That path
// implements the FULL public contract (update:modelValue, transition-only
// dirty-change, echo suppression, external adoption, getValue/focus), so
// it is tested deterministically in happy-dom. The real CM mount path is
// covered by the manual checklist (plan Task 6).
import { flushPromises, mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";

vi.mock("@codemirror/state", () => {
  throw new Error("CM unavailable in unit tests");
});

import CodeMirrorEditor from "./CodeMirrorEditor.vue";

async function mountEditor(modelValue = "") {
  const w = mount(CodeMirrorEditor, {
    props: { modelValue, filePath: "test.txt" },
  });
  // Let the failed dynamic import settle so the fallback textarea renders.
  await flushPromises();
  return w;
}

describe("CodeMirrorEditor (textarea fallback)", () => {
  it("typing emits update:modelValue and getValue returns the buffer", async () => {
    const w = await mountEditor("ab");
    const ta = w.find("textarea");
    expect(ta.exists()).toBe(true);
    expect((ta.element as HTMLTextAreaElement).value).toBe("ab");
    await ta.setValue("abc");
    expect(w.emitted("update:modelValue")?.at(-1)).toEqual(["abc"]);
    expect(w.vm.getValue()).toBe("abc");
  });

  it("emits dirty-change only on transitions (clean->dirty->clean)", async () => {
    const w = await mountEditor("");
    const ta = w.find("textarea");
    await ta.setValue("x");
    await ta.setValue("xy");
    expect(w.emitted("dirty-change")).toEqual([[true]]);
    await ta.setValue("");
    expect(w.emitted("dirty-change")).toEqual([[true], [false]]);
  });

  it("ignores echo prop updates but adopts external replacements", async () => {
    const w = await mountEditor("ab");
    const ta = w.find("textarea");
    await ta.setValue("abc");
    // Echo: parent mirrors our own emission back — buffer must stay.
    await w.setProps({ modelValue: "abc" });
    expect((ta.element as HTMLTextAreaElement).value).toBe("abc");
    // External replacement (file reloaded) — buffer adopts it and the
    // dirty baseline resets (dirty-change flips back to clean).
    await w.setProps({ modelValue: "zzz" });
    expect((ta.element as HTMLTextAreaElement).value).toBe("zzz");
    expect(w.vm.getValue()).toBe("zzz");
    expect(w.emitted("dirty-change")?.at(-1)).toEqual([false]);
  });

  it("exposes focus() without throwing", async () => {
    const w = await mountEditor("x");
    expect(() => w.vm.focus()).not.toThrow();
  });
});
