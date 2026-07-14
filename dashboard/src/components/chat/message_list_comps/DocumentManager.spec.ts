// DocumentManager fullscreen state + Esc wiring.
//
// Mounts the real DocumentManager with a heavy-stub strategy: the
// children that fetch from the backend (FileBrowserTree, DocumentEditor,
// DocumentHistoryPanel, DocumentViewModeTab, FileBrowserCodeView, etc.)
// are stubbed to a no-op div. The point of these tests is to assert
// the fullscreen state behavior, not to render the full tree.

import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import { nextTick, ref } from "vue";
import DocumentManager from "./DocumentManager.vue";

const stubs = {
  FileBrowserTree: { template: "<div />" },
  DocumentEditor: { template: "<div />" },
  DocumentHistoryPanel: { template: "<div />" },
  DocumentViewModeTab: { template: "<div />" },
  DocumentTreePanel: { template: "<div />" },
  DocumentPathBar: { template: "<div />" },
  FileBrowserCodeView: { template: "<div />" },
  FileCommentEditor: { template: "<div />" },
  FileBrowserBreadcrumb: { template: "<div />" },
  DiffPreview: { template: "<div />" },
  MarkdownView: { template: "<div />" },
  "v-icon": { template: "<i />" },
};

describe("DocumentManager fullscreen state", () => {
  it("toggles isFullscreen when the fullscreen button is clicked", async () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const wrapper = mount(DocumentManager as any, {
      // cast: DocumentManager requires gitLog/gitShow in defineProps;
      // only state-handler behavior is exercised here, so the
      // composable-shaped objects are stubbed with empty refs.
      props: {
        umo: "test",
        worktree: null,
        projectRoot: null,
        gitLog: { state: ref({ kind: "idle" }), filter: ref({}), refresh: () => Promise.resolve() },
        gitShow: { cached: ref(new Set()), getState: () => ({ kind: "idle" }) },
      },
      global: { stubs },
    });
    await nextTick();
    const vm = wrapper.vm as unknown as {
      isFullscreen: boolean;
      toggleFullscreen: () => void;
    };
    expect(vm.isFullscreen).toBe(false);
    vm.toggleFullscreen();
    expect(vm.isFullscreen).toBe(true);
    vm.toggleFullscreen();
    expect(vm.isFullscreen).toBe(false);
  });

  it("Esc exits fullscreen when fullscreen is on", async () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const wrapper = mount(DocumentManager as any, {
      props: {
        umo: "test",
        worktree: null,
        projectRoot: null,
        gitLog: { state: ref({ kind: "idle" }), filter: ref({}), refresh: () => Promise.resolve() },
        gitShow: { cached: ref(new Set()), getState: () => ({ kind: "idle" }) },
      },
      global: { stubs },
    });
    await nextTick();
    const vm = wrapper.vm as unknown as {
      isFullscreen: boolean;
      toggleFullscreen: () => void;
    };
    vm.toggleFullscreen();
    expect(vm.isFullscreen).toBe(true);
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    await nextTick();
    expect(vm.isFullscreen).toBe(false);
  });

  it("Esc is a no-op when fullscreen is off (does not throw)", async () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const wrapper = mount(DocumentManager as any, {
      props: {
        umo: "test",
        worktree: null,
        projectRoot: null,
        gitLog: { state: ref({ kind: "idle" }), filter: ref({}), refresh: () => Promise.resolve() },
        gitShow: { cached: ref(new Set()), getState: () => ({ kind: "idle" }) },
      },
      global: { stubs },
    });
    await nextTick();
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    await nextTick();
    const vm = wrapper.vm as unknown as { isFullscreen: boolean };
    expect(vm.isFullscreen).toBe(false);
  });
});
