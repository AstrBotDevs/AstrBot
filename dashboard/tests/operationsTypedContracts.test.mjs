import { flushPromises, mount } from "@vue/test-utils";
import { createPinia } from "pinia";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { createVuetify } from "vuetify";
import * as components from "vuetify/components";
import { VSelect } from "vuetify/components";
import { initI18n } from "../src/i18n/composables.ts";
import { mountDashboard } from "./helpers/components.mjs";

const fixtures = vi.hoisted(() => ({
  logs: { history: vi.fn(), liveUrl: vi.fn(() => "/api/v1/logs/live") },
  plugins: { list: vi.fn() },
  stats: { storage: vi.fn(), cleanupStorage: vi.fn() },
  request: { get: vi.fn(), post: vi.fn() },
  toast: vi.fn(),
  streams: [],
}));

vi.mock("@/api/v1", () => ({ logApi: fixtures.logs, pluginApi: fixtures.plugins, statsApi: fixtures.stats }));
vi.mock("@/utils/request", () => ({ default: fixtures.request }));
vi.mock("@/stores/toast", () => ({ useToastStore: () => ({ add: fixtures.toast }) }));
vi.mock("@/stores/customizer", () => ({ useCustomizerStore: () => ({ uiTheme: "BlueBusinessLightTheme" }) }));
vi.mock("event-source-polyfill", () => ({
  EventSourcePolyfill: class {
    constructor(url, options) {
      this.url = url;
      this.options = options;
      this.close = vi.fn();
      this.onopen = null;
      this.onmessage = null;
      this.onerror = null;
      fixtures.streams.push(this);
    }
  },
}));

import ConsoleDisplayer from "../src/components/shared/ConsoleDisplayer.vue";
import MigrationDialog from "../src/components/shared/MigrationDialog.vue";
import StorageCleanupPanel from "../src/components/shared/StorageCleanupPanel.vue";

const ok = (data, message = null) => ({ data: { status: "ok", data, message } });
const status = (total = 3072) => ({
  total_bytes: total,
  logs: { size_bytes: 1024, file_count: 2, path: "/logs", exists: true },
  cache: { size_bytes: 2048, file_count: 3, path: "/cache", exists: true },
  traces: { size_bytes: 0, file_count: 0, path: "/traces", exists: false },
});
const log = (time, data, extra = {}) => ({ time, data, level: "INFO", ...extra });
const mountSimple = async (component, options = {}) => {
  const result = await mountDashboard(component, {
    ...options,
    global: {
      ...options.global,
      renderStubDefaultSlot: false,
      stubs: {
        VCardSubtitle: true,
        VExpansionPanels: true,
        VExpansionPanel: true,
        VExpansionPanelTitle: true,
        VExpansionPanelText: true,
        WaitingForRestart: true,
      },
    },
  });
  await flushPromises();
  return result;
};

beforeEach(() => {
  fixtures.streams.length = 0;
  for (const group of [fixtures.logs, fixtures.plugins, fixtures.stats, fixtures.request]) {
    for (const method of Object.values(group)) method.mockReset();
  }
  fixtures.toast.mockReset();
  fixtures.logs.liveUrl.mockReturnValue("/api/v1/logs/live");
  fixtures.logs.history.mockResolvedValue(ok({ logs: [] }));
  fixtures.plugins.list.mockResolvedValue(ok([]));
  fixtures.stats.storage.mockResolvedValue(ok(status()));
  fixtures.stats.cleanupStorage.mockResolvedValue(ok({ status: status(0), removed_bytes: 3072, processed_files: 5 }));
  fixtures.request.get.mockResolvedValue(ok({ platforms: [] }));
  fixtures.request.post.mockResolvedValue(ok({}, "Migration completed"));
  vi.spyOn(console, "log").mockImplementation(() => undefined);
  vi.spyOn(console, "info").mockImplementation(() => undefined);
  vi.spyOn(console, "warn").mockImplementation(() => undefined);
  vi.spyOn(console, "error").mockImplementation(() => undefined);
});

describe("ConsoleDisplayer with typed logs and installed Vuetify slots", () => {
  test("Vuetify 4 renders plugin item subtitles, selects the display name, and clears the filter", async () => {
    fixtures.logs.history.mockResolvedValue(ok({ logs: [log(1, "plugin message", { plugin_name: "alpha" })] }));
    fixtures.plugins.list.mockResolvedValue(ok([{ name: "alpha", display_name: "Alpha Plugin" }]));
    vi.stubGlobal(
      "ResizeObserver",
      class {
        observe = vi.fn();
        unobserve = vi.fn();
        disconnect = vi.fn();
      },
    );
    vi.stubGlobal("visualViewport", {
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      width: 1024,
      height: 768,
      offsetTop: 0,
      offsetLeft: 0,
      pageTop: 0,
      pageLeft: 0,
      scale: 1,
    });
    await initI18n("en-US");
    const wrapper = mount(ConsoleDisplayer, {
      attachTo: document.body,
      props: { workspaceMode: true },
      global: { plugins: [createPinia(), createVuetify({ components })] },
    });
    await flushPromises();
    await wrapper.setData({ filtersOpen: true });
    const select = wrapper.findAllComponents(VSelect)[0];
    select.vm.menu = true;
    await flushPromises();
    let option;
    await vi.waitFor(() => {
      option = [...document.querySelectorAll(".v-overlay .v-list-item")].find((item) =>
        item.textContent.includes("Alpha Plugin"),
      );
      expect(option).toBeDefined();
    });
    expect(option.querySelector(".v-list-item-subtitle").textContent).toBe("alpha");
    option.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await flushPromises();
    expect(wrapper.vm.selectedPlugin).toBe("alpha");
    expect(select.find(".v-select__selection-text").text()).toBe("Alpha Plugin");
    await select.find(".v-field__clearable .v-icon").trigger("click");
    await flushPromises();
    expect(wrapper.vm.selectedPlugin).toBeNull();
    expect(wrapper.find(".console-term").text()).toContain("plugin message");
  });

  test("malformed logs do not enter the cache, text is escaped, and history remains bounded", async () => {
    const { vm, wrapper } = await mountSimple(ConsoleDisplayer);
    await wrapper.setData({ maxLogCacheLength: 2 });
    vm.processNewLogs([
      { time: 0, data: "missing level" },
      log(1, "<img src=x onerror=alert(1)>"),
      log(2, "second"),
      log(2, "second"),
    ]);
    expect(vm.localLogCache).toHaveLength(2);
    expect(wrapper.find(".console-term").text()).toContain("<img src=x onerror=alert(1)>");
    expect(wrapper.find(".console-term img").exists()).toBe(false);
    vm.processNewLogs([log(3, "third")]);
    expect(vm.localLogCache.map((item) => item.time)).toEqual([2, 3]);
    expect(wrapper.find(".console-term").text()).not.toContain("onerror");
  });

  test("late initialization cannot open a stream after component teardown", async () => {
    let finishHistory;
    fixtures.logs.history.mockReturnValueOnce(
      new Promise((resolve) => {
        finishHistory = resolve;
      }),
    );
    const { wrapper } = await mountSimple(ConsoleDisplayer);
    wrapper.unmount();
    finishHistory(ok({ logs: [] }));
    await flushPromises();
    expect(fixtures.streams).toHaveLength(0);
  });

  test("stream failures schedule a bounded retry which is cancelled by unmount", async () => {
    const { wrapper, vm } = await mountSimple(ConsoleDisplayer);
    vi.useFakeTimers();
    fixtures.streams[0].onerror({ status: 401 });
    expect(fixtures.streams[0].close).toHaveBeenCalledTimes(1);
    expect(vm.retryTimer).not.toBeNull();
    wrapper.unmount();
    await vi.advanceTimersByTimeAsync(30000);
    expect(fixtures.streams).toHaveLength(1);
    expect(vi.getTimerCount()).toBe(0);
  });
});

describe("migration result and platform selection", () => {
  test("group selection posts the exact adapter map and resolves the successful result", async () => {
    fixtures.request.get.mockResolvedValueOnce(
      ok({
        platforms: [
          { id: "qq-one", type: "aiocqhttp", platform_type: "qq" },
          { id: "qq-two", type: "aiocqhttp", platform_type: "qq" },
          { id: "telegram", type: "telegram" },
        ],
      }),
    );
    const { vm } = await mountSimple(MigrationDialog);
    const result = vm.open();
    await flushPromises();
    vm.selectedPlatforms.qq = "qq-two";
    await vm.handleMigration();
    expect(fixtures.request.post).toHaveBeenCalledExactlyOnceWith("/api/update/migration", {
      platform_id_map: {
        qq: { platform_id: "qq-two", platform_type: "qq" },
        telegram: { platform_id: "telegram", platform_type: "telegram" },
      },
    });
    expect(vm.migrationCompleted).toBe(true);
    vm.handleClose();
    await expect(result).resolves.toEqual({ success: true, message: "Migration completed" });
  });

  test("a rejected migration shows its response message without replay and can still be cancelled", async () => {
    const { vm } = await mountSimple(MigrationDialog);
    const result = vm.open();
    await flushPromises();
    fixtures.request.post.mockRejectedValueOnce({ response: { data: { message: "Migration is unavailable" } } });
    await vm.handleMigration();
    expect(vm.error).toBe("Migration is unavailable");
    expect(vm.migrating).toBe(false);
    expect(fixtures.request.post).toHaveBeenCalledTimes(1);
    vm.handleCancel();
    await expect(result).resolves.toEqual({ success: false, cancelled: true });
  });
});

describe("storage cleanup counters and response boundaries", () => {
  test("trace cleanup keeps its explicit confirmation and reports returned trace counts", async () => {
    const confirm = vi.fn().mockResolvedValue(true);
    const { vm } = await mountSimple(StorageCleanupPanel, { global: { provide: { $confirm: confirm } } });
    fixtures.stats.cleanupStorage.mockResolvedValueOnce(
      ok({
        status: status(1024),
        removed_bytes: 2048,
        processed_files: 0,
        removed_traces: 7,
      }),
    );
    await vm.cleanupStorage("traces");
    expect(confirm).toHaveBeenCalledTimes(1);
    expect(fixtures.stats.cleanupStorage).toHaveBeenCalledExactlyOnceWith("traces");
    expect(vm.storageStatus.total_bytes).toBe(1024);
    expect(fixtures.toast.mock.lastCall[0].message).toContain("7");
    expect(fixtures.toast.mock.lastCall[0].color).toBe("success");
    expect(vm.cleaningTarget).toBe("");
  });

  test("declining cleanup does not send a mutation request", async () => {
    const confirm = vi.fn().mockResolvedValue(false);
    const { vm } = await mountSimple(StorageCleanupPanel, { global: { provide: { $confirm: confirm } } });
    await vm.cleanupStorage("all");
    expect(fixtures.stats.cleanupStorage).not.toHaveBeenCalled();
    expect(vm.storageStatus.total_bytes).toBe(3072);
  });

  test("malformed storage counters retain the previous status and report an error", async () => {
    const { vm } = await mountSimple(StorageCleanupPanel);
    fixtures.stats.storage.mockResolvedValueOnce(ok({ logs: { size_bytes: "invalid" } }));
    await vm.loadStorageStatus();
    expect(vm.storageStatus.total_bytes).toBe(3072);
    expect(fixtures.toast.mock.lastCall[0]).toMatchObject({
      color: "error",
      message: "Invalid storage status response",
    });
    expect(vm.statusLoading).toBe(false);
  });
});
