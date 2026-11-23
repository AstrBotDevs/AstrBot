import { flushPromises } from "@vue/test-utils";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { toRaw } from "vue";
import { mountDashboard } from "./helpers/components.mjs";

const api = vi.hoisted(() => ({
  mcp: {
    list: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    setEnabled: vi.fn(),
    test: vi.fn(),
    syncModelScope: vi.fn(),
  },
  skills: {
    list: vi.fn(),
    uploadBatch: vi.fn(),
    delete: vi.fn(),
    setEnabled: vi.fn(),
    download: vi.fn(),
    listFiles: vi.fn(),
    getFile: vi.fn(),
    updateFile: vi.fn(),
    neoCandidates: vi.fn(),
    neoReleases: vi.fn(),
    neoPayload: vi.fn(),
  },
  config: { get: vi.fn() },
}));

vi.mock("@/api/v1", () => ({ mcpApi: api.mcp, skillApi: api.skills, systemConfigApi: api.config }));
vi.mock("@/stores/customizer", () => ({ useCustomizerStore: () => ({ uiTheme: "BlueBusinessLightTheme" }) }));
vi.mock("@/components/shared/LazyMonacoEditor", () => ({
  LazyMonacoEditor: { name: "TestCodeEditor", render: () => null },
}));

import McpServersSection from "../src/components/extension/McpServersSection.vue";
import SkillsSection from "../src/components/extension/SkillsSection.vue";

const ok = (data, message = null) => ({ data: { status: "ok", data, message } });
const failure = (message = null) => ({ data: { status: "error", data: null, message } });
const skill = (name, overrides = {}) => ({
  name,
  active: true,
  description: `${name} description`,
  path: `/skills/${name}`,
  source_type: "local_only",
  ...overrides,
});
const server = (name, overrides = {}) => ({ name, active: true, tools: [], ...overrides });
const mount = async (component) => {
  const result = await mountDashboard(component, {
    global: {
      renderStubDefaultSlot: false,
      stubs: {
        VContainer: true,
        VForm: true,
        VTimeline: true,
        VTimelineItem: true,
        VSnackbar: true,
        VDataTable: true,
      },
    },
  });
  await flushPromises();
  return result;
};

beforeEach(() => {
  for (const group of Object.values(api)) {
    for (const method of Object.values(group)) method.mockReset();
  }
  api.mcp.list.mockResolvedValue(ok([]));
  api.mcp.create.mockResolvedValue(ok({}));
  api.mcp.update.mockResolvedValue(ok({}));
  api.mcp.delete.mockResolvedValue(ok({}));
  api.mcp.setEnabled.mockResolvedValue(ok({}));
  api.mcp.syncModelScope.mockResolvedValue(ok({}));
  api.skills.list.mockResolvedValue(ok({ skills: [], runtime: "local" }));
  api.skills.delete.mockResolvedValue(ok({}));
  api.skills.setEnabled.mockResolvedValue(ok({}));
  api.skills.neoCandidates.mockResolvedValue(ok([]));
  api.skills.neoReleases.mockResolvedValue(ok([]));
  api.config.get.mockResolvedValue(ok({ config: { provider_settings: { computer_use_runtime: "none" } } }));
});

describe("typed MCP management contracts", () => {
  test("editing preserves arbitrary configuration and saves against the original server name", async () => {
    api.mcp.list.mockResolvedValue(
      ok([
        server("original", {
          active: false,
          connected: false,
          tools: ["read_file"],
          errlogs: "not configuration",
          transport: "streamable_http",
          url: "https://mcp.example.invalid/api",
          vendor_options: { retry: 2, feature_flags: ["preview"] },
        }),
      ]),
    );
    const { vm } = await mount(McpServersSection);
    vm.editServer(vm.mcpServers[0]);
    expect(JSON.parse(vm.serverConfigJson)).toEqual({
      transport: "streamable_http",
      url: "https://mcp.example.invalid/api",
      vendor_options: { retry: 2, feature_flags: ["preview"] },
    });
    vm.currentServer.name = "renamed";
    vm.saveServer();
    await flushPromises();
    expect(api.mcp.update).toHaveBeenCalledExactlyOnceWith("original", {
      name: "renamed",
      active: false,
      transport: "streamable_http",
      url: "https://mcp.example.invalid/api",
      vendor_options: { retry: 2, feature_flags: ["preview"] },
    });
    expect(vm.isEditMode).toBe(false);
    expect(vm.loading).toBe(false);
  });

  test("invalid list metadata reports a load error without replacing the previous valid list", async () => {
    api.mcp.list.mockResolvedValue(ok([server("preserved")]));
    const { vm } = await mount(McpServersSection);
    api.mcp.list.mockResolvedValueOnce(ok([{ name: "invalid", active: true, tools: [null] }]));
    await vm.getServers();
    expect(vm.mcpServers.map((item) => item.name)).toEqual(["preserved"]);
    expect(vm.save_message_success).toBe("error");
    expect(vm.save_message).toContain("Invalid MCP server list response");
    expect(vm.loadingGettingServers).toBe(false);
  });

  test("bulk failures remain selected and are not replayed automatically", async () => {
    api.mcp.list.mockResolvedValue(ok([server("alpha"), server("beta")]));
    const { vm } = await mount(McpServersSection);
    vm.startBatchSelection();
    vm.toggleSelectAll();
    vm.confirmBatchDelete();
    api.mcp.delete.mockResolvedValueOnce(ok({})).mockRejectedValueOnce(new Error("connection lost"));
    api.mcp.list.mockResolvedValueOnce(ok([server("beta")]));
    await vm.deleteSelectedMcpServers();
    expect(api.mcp.delete.mock.calls).toEqual([["alpha"], ["beta"]]);
    expect(vm.selectedMcpServerNames).toEqual(["beta"]);
    expect(vm.batchSelectionEnabled).toBe(true);
    expect(vm.batchDeleteDialog).toBe(false);
    expect(vm.batchDeleting).toBe(false);
  });

  test("clearing the provider prevents a sync, and unmounting clears the polling timer", async () => {
    const clearInterval = vi.spyOn(globalThis, "clearInterval");
    const { vm, wrapper } = await mount(McpServersSection);
    const interval = vm.refreshInterval;
    vm.selectedMcpServerProvider = null;
    await vm.syncMcpServers();
    expect(api.mcp.syncModelScope).not.toHaveBeenCalled();
    expect(vm.save_message_success).toBe("error");
    wrapper.unmount();
    expect(clearInterval).toHaveBeenCalledTimes(1);
    expect(toRaw(clearInterval.mock.calls[0][0])).toBe(toRaw(interval));
  });
});

describe("typed skill management contracts", () => {
  test("batch deletion uses names, excludes readonly sources, and retains failures after a failed refresh", async () => {
    api.skills.list.mockResolvedValue(
      ok({
        skills: [
          skill("alpha"),
          skill("beta"),
          skill("plugin", { source_type: "plugin" }),
          skill("preset", { source_type: "sandbox_only", preset: true }),
        ],
      }),
    );
    const { vm } = await mount(SkillsSection);
    vm.startBatchSelection();
    vm.toggleSelectAll();
    vm.confirmBatchDelete();
    expect(vm.batchDeleteTargets).toEqual(["alpha", "beta"]);
    api.skills.delete.mockResolvedValueOnce(ok({})).mockRejectedValueOnce(new Error("connection lost"));
    api.skills.list.mockRejectedValueOnce(new Error("refresh failed"));
    await vm.deleteSelectedSkills();
    expect(api.skills.delete.mock.calls).toEqual([["alpha"], ["beta"]]);
    expect(vm.selectedSkillNames).toEqual(["beta"]);
    expect(vm.batchSelectionEnabled).toBe(true);
    expect(vm.batchDeleteTargets).toEqual([]);
    expect(vm.batchDeleting).toBe(false);
    expect(vm.snackbar.color).toBe("error");
  });

  test("native file selection narrows the event target, skips duplicate/non-ZIP files, and uploads only ready files", async () => {
    const { vm } = await mount(SkillsSection);
    const zip = new File(["archive"], "Alpha.zip", { type: "application/zip" });
    const duplicate = new File(["duplicate"], "alpha.ZIP", { type: "application/zip" });
    const text = new File(["text"], "notes.txt", { type: "text/plain" });
    const input = document.createElement("input");
    input.type = "file";
    Object.defineProperty(input, "files", { value: [zip, duplicate, text] });
    input.addEventListener("change", vm.handleUploadSelection);
    input.dispatchEvent(new Event("change"));
    vm.handleUploadSelection(new Event("change"));
    expect(vm.uploadItems.map((item) => item.status)).toEqual(["waiting", "skipped", "skipped"]);
    api.skills.uploadBatch.mockResolvedValueOnce(ok({ succeeded: [{ filename: "Alpha.zip", name: "alpha" }] }));
    await vm.uploadSkillBatch();
    expect(api.skills.uploadBatch).toHaveBeenCalledExactlyOnceWith([zip]);
    expect(vm.uploadItems.map((item) => item.status)).toEqual(["success", "skipped", "skipped"]);
    expect(vm.uploading).toBe(false);
  });

  test("file editor opens SKILL.md, keeps readonly metadata, and does not discard dirty changes without confirmation", async () => {
    const { vm } = await mount(SkillsSection);
    const entry = { name: "SKILL.md", path: "SKILL.md", type: "file", size: 10, editable: true };
    api.skills.listFiles.mockResolvedValueOnce(ok({ name: "alpha", path: "", entries: [entry] }));
    api.skills.getFile.mockResolvedValueOnce(ok({ path: "SKILL.md", content: "# Alpha", editable: false }));
    await vm.openSkillEditor(skill("alpha"));
    expect(api.skills.getFile).toHaveBeenCalledExactlyOnceWith("alpha", "SKILL.md");
    expect(vm.editorDialog.entries).toEqual([entry]);
    expect(vm.editorDialog.content).toBe("# Alpha");
    expect(vm.editorDialog.fileEditable).toBe(false);
    vm.editorDialog.fileDirty = true;
    vi.spyOn(window, "confirm").mockReturnValue(false);
    await vm.openSkillEntry({ name: "docs", path: "docs", type: "directory", size: 0, editable: false });
    expect(api.skills.listFiles).toHaveBeenCalledTimes(1);
    expect(vm.editorDialog.currentDir).toBe("");
  });

  test("missing download bytes fail before any object URL is created", async () => {
    const { vm } = await mount(SkillsSection);
    const createObjectURL = vi.fn();
    vi.stubGlobal("URL", Object.assign(class extends URL {}, { createObjectURL }));
    api.skills.download.mockResolvedValueOnce({ data: undefined });
    await vm.downloadSkill(skill("alpha"));
    expect(createObjectURL).not.toHaveBeenCalled();
    expect(vm.snackbar.color).toBe("error");
    expect(vm.itemLoading.alpha).toBe(false);
  });

  test("nullable error messages and payload references keep their existing fallbacks", async () => {
    api.config.get.mockResolvedValueOnce(ok({ config: null }));
    const { vm } = await mount(SkillsSection);
    const alpha = skill("alpha");
    api.skills.setEnabled.mockResolvedValueOnce(failure(null));
    await vm.toggleSkill(alpha);
    await vm.viewPayload(null);
    expect(alpha.active).toBe(true);
    expect(vm.snackbar.color).toBe("error");
    expect(vm.snackbar.message).not.toBe("");
    expect(vm.neoEnabled).toBe(false);
    expect(api.skills.neoPayload).not.toHaveBeenCalled();
    expect(vm.skillSourceChip(null)).toBeNull();
  });
});
