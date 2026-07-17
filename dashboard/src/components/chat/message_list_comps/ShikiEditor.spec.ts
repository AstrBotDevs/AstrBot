// Author: elecvoid243, 2026-07-18
// ShikiEditor unit tests: the real @/utils/shiki module is mocked so
// no actual Shiki highlighter is loaded (keeps the suite fast); the
// tests exercise the editor's OWN logic — uncontrolled textarea,
// echo suppression, dirty transitions, getValue expose.
import { describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";

vi.mock("@/utils/shiki", () => ({
  detectLanguage: vi.fn(() => "plaintext"),
  ensureShikiLanguages: vi.fn(async () => ({})),
  escapeHtml: (s: string) => s,
  renderShikiCode: vi.fn(
    (_h: unknown, code: string) => `<pre><code>${code}</code></pre>`,
  ),
}));

import ShikiEditor from "./ShikiEditor.vue";

function mountEditor(modelValue = "") {
  return mount(ShikiEditor, {
    props: { modelValue, filePath: "test.txt" },
  });
}

describe("ShikiEditor", () => {
  it("typing emits update:modelValue and getValue returns the buffer", async () => {
    const w = mountEditor("ab");
    const ta = w.find("textarea");
    expect((ta.element as HTMLTextAreaElement).value).toBe("ab");
    await ta.setValue("abc");
    expect(w.emitted("update:modelValue")?.at(-1)).toEqual(["abc"]);
    expect(w.vm.getValue()).toBe("abc");
  });

  it("emits dirty-change only on transitions (clean→dirty→clean)", async () => {
    const w = mountEditor("");
    const ta = w.find("textarea");
    await ta.setValue("x");
    await ta.setValue("xy");
    expect(w.emitted("dirty-change")).toEqual([[true]]);
    // Back to the initial content → clean again.
    await ta.setValue("");
    expect(w.emitted("dirty-change")).toEqual([[true], [false]]);
  });

  it("ignores echo prop updates (own emissions) but adopts external ones", async () => {
    const w = mountEditor("ab");
    const ta = w.find("textarea");
    await ta.setValue("abc");
    // Echo: parent mirrors our own emission back — buffer must stay.
    // (Per contract parents must NOT mirror; even if one does, the
    // buffer is protected. The dirty baseline follows modelValue, so
    // a mirror also re-baselines dirty — hence the no-mirror rule.)
    await w.setProps({ modelValue: "abc" });
    expect((ta.element as HTMLTextAreaElement).value).toBe("abc");
    // External replacement (e.g. file reloaded) — buffer adopts it.
    await w.setProps({ modelValue: "zzz" });
    expect((ta.element as HTMLTextAreaElement).value).toBe("zzz");
    expect(w.vm.getValue()).toBe("zzz");
    // New baseline == buffer → clean again.
    expect(w.emitted("dirty-change")?.at(-1)).toEqual([false]);
  });

  it("exposes focus() without throwing", () => {
    const w = mountEditor("x");
    expect(() => w.vm.focus()).not.toThrow();
  });
});
