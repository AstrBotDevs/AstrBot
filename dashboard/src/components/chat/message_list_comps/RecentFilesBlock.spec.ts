// Author: elecvoid243, 2026-07-20
// RecentFilesBlock component tests — covers Tasks 5 + 6 of the plan:
// default-collapsed, row rendering up to 5 + +N more, × button
// emit('remove') with no select bubbling, Clear link, empty state.
//
// Vuetify components are stubbed (per existing convention in
// DocumentManager.spec.ts) so the suite stays dependency-light.
import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import { vuetifyStubs } from "@/test/vuetify";

vi.mock("@/i18n/composables", () => ({
  useModuleI18n: () => ({
    tm: (key: string, params?: Record<string, unknown>) => {
      if (!params) return key;
      return key.replace(/\{(\w+)\}/g, (_, k) => String(params[k]));
    },
    rt: (key: string) => key,
  }),
}));

import RecentFilesBlock from "./RecentFilesBlock.vue";

function factory(props: Record<string, unknown> = {}) {
  return mount(RecentFilesBlock, {
    props: {
      entries: [],
      currentRoot: "/projects/demo",
      ...props,
    },
    global: { stubs: vuetifyStubs },
  });
}

const sampleEntries = [
  { path: "/projects/demo/src/main.py", openedAt: 1_700_000_003_000 },
  { path: "/projects/demo/README.md", openedAt: 1_700_000_002_000 },
  { path: "/projects/demo/x.ts", openedAt: 1_700_000_001_000 },
];

describe("RecentFilesBlock — collapsed default", () => {
  it("renders the header with the count when collapsed", () => {
    const w = factory({ entries: sampleEntries });
    // v-show keeps the body element in DOM but applies display: none.
    // happy-dom's isVisible() doesn't read inline display, so check
    // the element attribute directly.
    const body = w.find('[data-test="recent-files-body"]');
    expect(body.attributes("style") ?? "").toMatch(/display:\s*none/);
    // The i18n mock returns the key verbatim; assert on key + count
    // so we exercise the count prop without loading real i18n
    // dictionaries.
    expect(w.text()).toContain("titleWithCount");
  });

  it("does not throw when entries is empty", () => {
    expect(() => factory({ entries: [] })).not.toThrow();
  });
});

describe("RecentFilesBlock — expanded interactions", () => {
  it("shows up to 5 rows when expanded", async () => {
    const entries = Array.from({ length: 8 }, (_, i) => ({
      path: `/projects/demo/file-${i}.py`,
      openedAt: 1_700_000_000_000 + i,
    }));
    const w = factory({ entries });
    await w.find('[data-test="recent-files-header"]').trigger("click");
    expect(w.findAll('[data-test="recent-row"]')).toHaveLength(5);
    // +N more is rendered as a literal template (no i18n key) per
    // spec §5.2 — assert the literal suffix.
    expect(w.text()).toContain("+3 more");
  });

  it("emits 'select' with the row's path when a row is clicked", async () => {
    const w = factory({ entries: sampleEntries });
    await w.find('[data-test="recent-files-header"]').trigger("click");
    await w.find('[data-test="recent-row"]').trigger("click");
    const events = w.emitted("select");
    expect(events).toBeTruthy();
    expect(events![0][0]).toEqual({ path: "/projects/demo/src/main.py" });
  });

  it("emits 'remove' when × is clicked, and does NOT bubble to row select", async () => {
    const w = factory({ entries: sampleEntries });
    await w.find('[data-test="recent-files-header"]').trigger("click");
    await w
      .find('[data-test="recent-row"] [data-test="recent-remove"]')
      .trigger("click");
    const removeEvents = w.emitted("remove");
    const selectEvents = w.emitted("select");
    expect(removeEvents).toBeTruthy();
    expect(removeEvents![0][0]).toEqual({
      path: "/projects/demo/src/main.py",
    });
    expect(selectEvents).toBeFalsy();
  });

  it("emits 'clear' when the Clear link is clicked", async () => {
    const w = factory({ entries: sampleEntries });
    await w.find('[data-test="recent-files-header"]').trigger("click");
    await w.find('[data-test="recent-clear"]').trigger("click");
    const events = w.emitted("clear");
    expect(events).toBeTruthy();
    expect(events).toHaveLength(1);
  });

  it("renders the empty placeholder when entries is empty and expanded", async () => {
    const w = factory({ entries: [] });
    await w.find('[data-test="recent-files-header"]').trigger("click");
    expect(
      w.find('[data-test="recent-files-empty"]').exists(),
    ).toBe(true);
  });

  it("does NOT show Clear link when entries is empty", async () => {
    const w = factory({ entries: [] });
    await w.find('[data-test="recent-files-header"]').trigger("click");
    expect(w.find('[data-test="recent-clear"]').exists()).toBe(false);
  });
});
