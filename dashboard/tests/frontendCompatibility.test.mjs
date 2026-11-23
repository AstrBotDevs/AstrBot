import { flushPromises, mount } from "@vue/test-utils";
import { createPinia } from "pinia";
import { beforeEach, expect, test, vi } from "vitest";
import { createVuetify } from "vuetify";
import * as components from "vuetify/components";
import { VFileInput, VSelect } from "vuetify/components";
import { initI18n } from "../src/i18n/composables.ts";
import { mountDashboard } from "./helpers/components.mjs";

const api = vi.hoisted(() => ({
  version: vi.fn(),
  versions: vi.fn(),
  changelog: vi.fn(),
  get: vi.fn(),
  backup: {
    initUpload: vi.fn(),
    uploadChunk: vi.fn(),
    completeUpload: vi.fn(),
    abortUpload: vi.fn(),
    statusUpload: vi.fn(),
  },
}));
vi.mock("@/api/v1", () => ({
  statsApi: { version: api.version },
  changelogApi: { listVersions: api.versions, get: api.changelog },
  backupApi: api.backup,
  pluginApi: {},
  providerApi: {},
  configProfileApi: {},
  t2iApi: {},
}));
vi.mock("@/utils/request", () => ({
  default: { get: api.get },
  isAxiosError: () => false,
  resolveApiUrl: (path) => path,
}));
vi.mock("@/stores/customizer", () => ({ useCustomizerStore: () => ({ uiTheme: "BlueBusinessLightTheme" }) }));
vi.mock("@/components/shared/LazyMonacoEditor", () => ({
  LazyMonacoEditor: {
    name: "VueMonacoEditor",
    props: ["value", "theme", "language"],
    emits: ["update:value"],
    template: "<pre>{{ value }}</pre>",
  },
}));
vi.mock("markstream-vue", () => ({
  enableKatex: vi.fn(),
  enableMermaid: vi.fn(),
  MarkdownRender: { template: "<div />" },
}));

import ConfigProfileMenu from "../src/components/config/ConfigProfileMenu.vue";
import AstrBotConfig from "../src/components/shared/AstrBotConfig.vue";
import BackupDialog from "../src/components/shared/BackupDialog.vue";
import ChangelogDialog from "../src/components/shared/ChangelogDialog.vue";
import ConfigItemRenderer from "../src/components/shared/ConfigItemRenderer.vue";
import { readConfigInfoList } from "../src/utils/configProfile.ts";
import MessageStat from "../src/views/dashboards/default/components/MessageStat.vue";

const ok = (data) => ({ data: { status: "ok", data } });
beforeEach(async () => {
  api.version.mockReset().mockResolvedValue(ok({ version: "4.25.0" }));
  api.versions.mockReset().mockResolvedValue(ok({ versions: ["4.25.0", "4.24.0"] }));
  api.changelog.mockReset().mockResolvedValue(ok({ content: "Release notes" }));
  api.get.mockReset().mockResolvedValue(ok({ message_time_series: [] }));
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
});

function mountFramework(component, options = {}) {
  return mount(component, {
    attachTo: document.body,
    ...options,
    global: {
      plugins: [createPinia(), createVuetify({ components })],
      stubs: {
        apexchart: true,
        WaitingForRestart: true,
        VDialog: { template: "<div><slot /></div>" },
        ...options.global?.stubs,
      },
    },
  });
}

test("real VSelect keeps string version values and labels aligned", async () => {
  const wrapper = mountFramework(ChangelogDialog, { props: { modelValue: false } });
  await flushPromises();
  await wrapper.setProps({ modelValue: true });
  await flushPromises();
  const select = wrapper.findComponent(VSelect);
  expect(select.text()).toContain("v4.25.0");
  expect(select.text()).not.toContain("undefined");
  select.vm.menu = true;
  await flushPromises();
  let previousVersion;
  await vi.waitFor(() => {
    previousVersion = [...document.querySelectorAll(".v-overlay .v-list-item")].find((item) =>
      item.textContent.includes("v4.24.0"),
    );
    expect(previousVersion).toBeDefined();
  });
  previousVersion.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  await flushPromises();
  expect(api.changelog).toHaveBeenLastCalledWith("4.24.0");
  expect(select.text()).toContain("v4.24.0");
});

test("real VSelect shows object time-range labels and requests their numeric interval", async () => {
  const wrapper = mountFramework(MessageStat);
  await flushPromises();
  const select = wrapper.findComponent(VSelect);
  expect(select.text()).toContain(wrapper.vm.timeRanges[0].label);
  select.vm.menu = true;
  await flushPromises();
  let nextRange;
  await vi.waitFor(() => {
    nextRange = [...document.querySelectorAll(".v-overlay .v-list-item")].find((item) =>
      item.textContent.includes(wrapper.vm.timeRanges[1].label),
    );
    expect(nextRange).toBeDefined();
  });
  nextRange.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  await flushPromises();
  expect(api.get).toHaveBeenLastCalledWith("/api/stat/get?offset_sec=259200");
  expect(select.text()).toContain(wrapper.vm.timeRanges[1].label);
});

test("backup file input normalizes scalar, array, and clear events", async () => {
  const wrapper = mountFramework(BackupDialog);
  await wrapper.vm.open();
  await flushPromises();
  await wrapper.findAll('[role="tab"]')[1].trigger("click");
  await flushPromises();
  const input = wrapper.findComponent(VFileInput);
  expect(input.exists()).toBe(true);
  const first = new File(["backup"], "first.zip", { type: "application/zip" });
  const second = new File(["backup2"], "second.zip", { type: "application/zip" });
  for (const [value, expected] of [
    [first, first],
    [[first, second], first],
    [[], null],
    [undefined, null],
    [null, null],
  ]) {
    input.vm.$emit("update:modelValue", value);
    await flushPromises();
    expect(input.props("modelValue")).toBe(expected);
  }
  expect(api.backup.initUpload).not.toHaveBeenCalled();
});

test("configuration controls receive values with the shape required by their domain", async () => {
  const { wrapper } = await mountDashboard(ConfigItemRenderer, {
    props: {
      modelValue: "invalid scalar",
      itemMeta: { _special: "select_agent_configs", type: "list" },
    },
  });
  const selector = () => wrapper.findComponent({ name: "AgentConfigSelector" });
  expect(selector().props("modelValue")).toEqual([]);
  await wrapper.setProps({ modelValue: ["default", null, 7, "secondary"] });
  expect(selector().props("modelValue")).toEqual(["default", "secondary"]);
  await wrapper.setProps({ modelValue: "wrong shape", itemMeta: { type: "dict" } });
  expect(wrapper.findComponent({ name: "ObjectEditor" }).props("modelValue")).toEqual({});
});

test("persisted profiles without names remain visible and selectable by ID", async () => {
  const persisted = { id: "profile-1", path: "abconf_profile-1.json", plugin_field: { enabled: true } };
  const items = readConfigInfoList([persisted, null, { name: "missing ID" }]);
  expect(items).toEqual([{ ...persisted, name: "profile-1" }]);
  const { wrapper } = await mountDashboard(ConfigProfileMenu, { props: { items, modelValue: "profile-1" } });

  const item = wrapper.find(".config-profile-menu__item");
  expect(item.text()).toContain("profile-1");
  await item.trigger("click");
  expect(wrapper.emitted("select")).toEqual([["profile-1"]]);
});

test("editing an ordinary configuration list preserves existing non-string members", async () => {
  const { wrapper } = await mountDashboard(ConfigItemRenderer, {
    props: { modelValue: [1, "two", false], itemMeta: { type: "list" } },
    global: { stubs: { ListConfigItem: false } },
  });
  const list = wrapper.findComponent({ name: "ListConfigItem" });
  expect(list.props("modelValue")).toEqual([1, "two", false]);
  list.vm.openDialog();
  list.vm.newItem = "three";
  list.vm.addItem();
  list.vm.confirmDialog();
  await flushPromises();

  expect(wrapper.emitted("update:modelValue")).toEqual([[[1, "two", false, "three"]]]);
});

test("the fullscreen editor switches objects when both use the same field name", async () => {
  const first = { script: "first script" };
  const second = { script: "second script" };
  const { wrapper } = await mountDashboard(AstrBotConfig, {
    props: {
      iterable: first,
      metadataKey: "settings",
      metadata: { settings: { type: "object", items: { script: { type: "text", editor_mode: true } } } },
    },
    global: { stubs: { VueMonacoEditor: false } },
  });
  const field = () => wrapper.findComponent({ name: "ConfigItemRenderer" });
  const editor = () => wrapper.findComponent({ name: "VueMonacoEditor" });
  field().vm.$emit("open-fullscreen");
  await flushPromises();
  expect(editor().props("value")).toBe("first script");
  await wrapper.setProps({ iterable: second });
  field().vm.$emit("open-fullscreen");
  await flushPromises();
  expect(editor().props("value")).toBe("second script");

  editor().vm.$emit("update:value", "edited second script");
  await flushPromises();
  expect(first.script).toBe("first script");
  expect(second.script).toBe("edited second script");
  expect(field().props("modelValue")).toBe("edited second script");
});
