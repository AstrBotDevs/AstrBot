import { flushPromises, mount } from "@vue/test-utils";
import { createPinia } from "pinia";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { createVuetify } from "vuetify";
import * as components from "vuetify/components";
import { VSelect } from "vuetify/components";
import { initI18n } from "../src/i18n/composables.ts";
import { mountDashboard } from "./helpers/components.mjs";

const fixtures = vi.hoisted(() => ({
  request: { get: vi.fn(), post: vi.fn() },
  toast: { warning: vi.fn(), info: vi.fn(), success: vi.fn(), error: vi.fn() },
}));

vi.mock("@/utils/request", () => ({
  default: fixtures.request,
  isAxiosError: (error) => error?.isAxiosError === true,
}));
vi.mock("@/components/shared/ConsoleDisplayer.vue", () => ({
  default: { name: "ConsoleDisplayer", render: () => null },
}));

import KnowledgeBase from "../src/views/alkaid/KnowledgeBase.vue";
import LongTermMemory from "../src/views/alkaid/LongTermMemory.vue";

const ok = (data) => ({ data: { status: "ok", data } });
const providers = [
  { id: "embedding-A", provider_type: "embedding", embedding_model: "Embedding Alpha", embedding_dimensions: 1024 },
  { id: "rerank-A", provider_type: "rerank", rerank_model: "Rerank Alpha" },
  { id: "llm-A", provider_type: "chat_completion", llm_model: "LLM Alpha" },
];
const graph = () => ({
  nodes: [
    ["node-A", { _label: "PhaseNode", name: "First node", user_id: "owner" }],
    ["node-B", { _label: "FactNode", name: "Second node", user_id: "owner" }],
  ],
  edges: [["node-A", "node-B", { relation_type: "_related_", fact_id: "fact-A" }]],
});

const mountSimple = async (component, options = {}) => {
  const result = await mountDashboard(component, {
    ...options,
    global: {
      ...options.global,
      mocks: { $toast: fixtures.toast, ...options.global?.mocks },
      stubs: { VForm: true, VSnackbar: true, VBanner: true, ...options.global?.stubs },
    },
  });
  await flushPromises();
  return result;
};

beforeEach(() => {
  for (const method of Object.values(fixtures.request)) method.mockReset();
  for (const method of Object.values(fixtures.toast)) method.mockReset();
  fixtures.request.get.mockImplementation(async (url) => {
    if (url.startsWith("/api/plugin/get")) return ok([{ activated: true, version: "1.0.0" }]);
    if (url === "/api/plugin/market_list") return ok({ astrbot_plugin_knowledge_base: { version: "1.0.0" } });
    if (url === "/api/plug/alkaid/kb/collections") return ok([{ collection_name: "notes", emoji: "📚", count: 2 }]);
    if (url === "/api/config/provider/list") return ok(providers);
    if (url === "/api/plug/alkaid/kb/collection/search") {
      return ok([{ content: "A matching paragraph", score: 0.75 }]);
    }
    if (url === "/api/plug/alkaid/ltm/graph") return ok(graph());
    if (url === "/api/plug/alkaid/ltm/user_ids") return ok(["owner"]);
    throw new Error(`Unexpected fixture GET ${url}`);
  });
  fixtures.request.post.mockResolvedValue(ok({}));
});

describe("Alkaid knowledge-base contracts", () => {
  test("real Vuetify provider selections store IDs and submit those IDs", async () => {
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
    const wrapper = mount(KnowledgeBase, {
      attachTo: document.body,
      global: { plugins: [createPinia(), createVuetify({ components })] },
    });
    await flushPromises();
    await wrapper.setData({ showCreateDialog: true });
    await flushPromises();

    for (const [labelKey, title, field, id] of [
      ["createDialog.embeddingModelLabel", "Embedding Alpha", "embedding_provider_id", "embedding-A"],
      ["createDialog.rerankModelLabel", "Rerank Alpha", "rerank_provider_id", "rerank-A"],
    ]) {
      const select = wrapper.findAllComponents(VSelect).find((item) => item.props("label") === wrapper.vm.tm(labelKey));
      expect(select).toBeDefined();
      select.vm.menu = true;
      await flushPromises();
      let option;
      await vi.waitFor(() => {
        option = [...document.querySelectorAll(".v-overlay .v-list-item")].find((item) =>
          item.textContent.includes(title),
        );
        expect(option).toBeDefined();
      });
      option.dispatchEvent(new MouseEvent("click", { bubbles: true }));
      await flushPromises();
      expect(wrapper.vm.newKB[field]).toBe(id);
      expect(select.find(".v-select__selection-text").text()).toBe(title);
    }
    wrapper.vm.newKB.name = "new-notes";
    wrapper.vm.submitCreateForm();
    await flushPromises();
    expect(fixtures.request.post).toHaveBeenCalledExactlyOnceWith("/api/plug/alkaid/kb/create_collection", {
      collection_name: "new-notes",
      emoji: "🙂",
      description: "",
      embedding_provider_id: "embedding-A",
      rerank_provider_id: "rerank-A",
    });
  });

  test("collection and search results render without optional source metadata", async () => {
    const renderErrors = [];
    const { vm, wrapper } = await mountSimple(KnowledgeBase, {
      global: { config: { errorHandler: (error) => renderErrors.push(error) } },
    });
    expect(vm.kbCollections).toEqual([{ collection_name: "notes", emoji: "📚", count: 2 }]);
    expect(vm.embeddingProviderConfigs).toEqual([providers[0]]);
    expect(vm.rerankProviderConfigs).toEqual([providers[1]]);
    expect(vm.llmProviderConfigs).toEqual([providers[2]]);
    vm.openKnowledgeBase(vm.kbCollections[0]);
    vm.activeTab = "search";
    vm.searchQuery = " paragraph ";
    vm.searchKnowledgeBase();
    await flushPromises();
    expect(vm.searching).toBe(false);
    expect(vm.searchResults).toHaveLength(1);
    expect(renderErrors).toEqual([]);
    expect(wrapper.text()).toContain("A matching paragraph");
    expect(fixtures.request.get).toHaveBeenCalledWith("/api/plug/alkaid/kb/collection/search", {
      params: { collection_name: "notes", query: "paragraph", top_k: 5 },
    });
  });

  test.each([
    undefined,
    null,
    "unexpected text",
  ])("completed task without an object result stops safely: %s", async (result) => {
    const { vm } = await mountSimple(KnowledgeBase);
    vm.importing = true;
    await vm.handleImportResult({ status: "completed", result });
    expect(vm.importing).toBe(false);
    expect(vm.snackbar.color).toBe("error");
    expect(fixtures.request.post).not.toHaveBeenCalled();
  });

  test("noise objects upload only their nonempty text and preserve chunk order", async () => {
    const { vm } = await mountSimple(KnowledgeBase);
    const upload = vi.spyOn(vm, "uploadChunkAsFile").mockResolvedValue({ status: "ok" });
    vm.importing = true;
    await vm.handleImportResult({
      status: "completed",
      result: {
        overall_summary: "Overall summary",
        topics: [{ topic_id: "alpha", topic_summary: "Topic summary" }],
        noise_points: [{ text: "" }, { text: "Object text" }, "Plain text", "   "],
      },
    });
    expect(upload.mock.calls).toEqual([
      ["Overall summary", "overall_summary.txt"],
      ["Topic summary", "topic_alpha_summary.txt"],
      ["Object text", "noise_2.txt"],
      ["Plain text", "noise_3.txt"],
    ]);
    expect(vm.importing).toBe(false);
    expect(vm.snackbar.color).toBe("success");
  });

  test("URL import keeps false and zero options, and cancellation prevents later polling", async () => {
    vi.useFakeTimers();
    const { vm, wrapper } = await mountSimple(KnowledgeBase);
    fixtures.request.post.mockResolvedValueOnce({ data: { task_id: "task-A" } });
    vm.importUrl = "https://example.invalid/document";
    vm.importOptions.use_llm_repair = false;
    vm.importOptions.chunk_overlap = 0;
    vm.importOptions.repair_llm_provider_id = null;
    await vm.startImportFromUrl();
    expect(fixtures.request.post).toHaveBeenCalledExactlyOnceWith("/api/plug/url_2_kb/add", {
      url: "https://example.invalid/document",
      use_llm_repair: false,
      use_clustering_summary: false,
      summarize_llm_provider_id: "llm-A",
      embedding_provider_id: "embedding-A",
      chunk_size: 300,
      chunk_overlap: 0,
    });
    wrapper.unmount();
    await vi.advanceTimersByTimeAsync(9000);
    expect(fixtures.request.post).toHaveBeenCalledTimes(1);
  });

  test("an explicit zero chunk overlap reaches the upload endpoint", async () => {
    const { vm } = await mountSimple(KnowledgeBase);
    vm.currentKB = { collection_name: "notes" };
    vm.importOptions.chunk_overlap = 0;
    await vm.uploadChunkAsFile("text", "chunk.txt");
    const formData = fixtures.request.post.mock.calls[0][1];
    expect(formData.get("chunk_overlap")).toBe("0");
    expect(formData.get("collection_name")).toBe("notes");
    expect(formData.get("file").name).toBe("chunk.txt");
  });
});

describe("Alkaid long-term memory graph contracts", () => {
  test("raw API tuples survive D3 link resolution and real SVG rendering", async () => {
    const { vm, wrapper } = await mountSimple(LongTermMemory, { attachTo: document.body });
    vm.simulation.stop();
    expect(vm.node_data).toEqual(graph().nodes);
    expect(vm.edge_data).toEqual(graph().edges);
    expect(vm.graphStats).toEqual({ nodeCount: 2, edgeCount: 1 });
    expect(wrapper.findAll("#graph-container circle")).toHaveLength(2);
    expect(wrapper.find("#graph-container svg").attributes("viewBox").split(/[ ,]+/).map(Number)).toEqual([
      0, 0, 800, 600,
    ]);
    expect(vm.links[0].source.id).toBe("node-A");
    expect(vm.links[0].target.id).toBe("node-B");
    expect(vm.generateLinkPath(vm.links[0])).not.toContain("NaN");
    await wrapper.find("#graph-container circle").trigger("click");
    expect(vm.selectedNode).toEqual(graph().nodes[0][1]);

    const drag = vm.dragBehavior();
    const node = vm.nodes[0];
    drag.on("start")({ active: true }, node);
    expect(node.fx).toBe(node.x);
    drag.on("drag")({ x: 12, y: 34 }, node);
    expect([node.fx, node.fy]).toEqual([12, 34]);
    drag.on("end")({ active: true }, node);
    expect([node.fx, node.fy]).toEqual([null, null]);

    const stop = vi.spyOn(vm.simulation, "stop");
    wrapper.unmount();
    expect(stop).toHaveBeenCalledOnce();
    expect(document.querySelector("#graph-container svg")).toBeNull();
  });
});
