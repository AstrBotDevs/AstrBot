import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { setImmediate } from "node:timers/promises";
import { fileURLToPath } from "node:url";
import { compileFunction } from "node:vm";
import test from "node:test";
import { compileScript, parse } from "vue/compiler-sfc";
import ts from "typescript";
import * as vue from "vue";

// Execute the real component scripts without mounting their visual dependencies.
function loadScript(path, dependencies = {}, storage = undefined) {
  const url = new URL(`../src/${path}`, import.meta.url);
  const filename = fileURLToPath(url);
  let source = readFileSync(url, "utf8");
  if (path.endsWith(".vue")) {
    const { descriptor, errors } = parse(source, { filename });
    assert.deepEqual(errors, []);
    source = compileScript(descriptor, { id: filename }).content;
  }
  const { outputText } = ts.transpileModule(source, {
    fileName: filename,
    compilerOptions: {
      target: ts.ScriptTarget.ES2022,
      module: ts.ModuleKind.CommonJS,
      esModuleInterop: true,
    },
  });
  const module = { exports: {} };
  const require = (id) => {
    if (id === "vue") return vue;
    if (Object.hasOwn(dependencies, id)) return dependencies[id];
    if (/\.(vue|png|svg)$/.test(id)) return {};
    throw new Error(`Unexpected test dependency: ${id}`);
  };
  compileFunction(outputText, ["require", "module", "exports", "localStorage"], { filename })(
    require,
    module,
    module.exports,
    storage,
  );
  return module.exports;
}

const inputValue = loadScript("utils/inputValue.ts");
const errorUtils = loadScript("utils/errorUtils.js");
const translate = (key, params) => `${key}${params ? ` ${JSON.stringify(params)}` : ""}`;

function createMcpModel(request) {
  const { default: component } = loadScript("components/extension/McpServersSection.vue", {
    "@guolao/vue-monaco-editor": { VueMonacoEditor: {} },
    "@/i18n/composables": {
      useI18n: () => ({ t: translate }),
      useModuleI18n: () => ({ tm: translate }),
    },
    "@/utils/confirmDialog": {
      useConfirmDialog: () => ({}),
      askForConfirmation: async () => true,
    },
    "@/utils/errorUtils.js": errorUtils,
    "@/utils/request": request,
  });
  const model = vue.reactive({ ...component.data(), ...component.setup() });
  for (const [name, method] of Object.entries(component.methods)) {
    model[name] = method.bind(model);
  }
  return model;
}

function setupComponent(t, component, props) {
  const scope = vue.effectScope();
  t.after(() => scope.stop());
  return scope.run(() => component.setup(props, { expose: () => undefined, emit: () => undefined }));
}

test("installed plugin typing preserves sorted identities and installed-first pin lookup", (t) => {
  const alpha = { name: "alpha", logo: null, pages: ["settings"], support_platforms: null };
  const beta = { name: "beta", reserved: true, activated: false };
  const market = { name: "market", install_source: { repo: "https://example.com/market" } };
  const state = {
    extension_data: vue.reactive({ data: [alpha, beta] }),
    filteredPlugins: vue.ref([beta, alpha, { name: 42 }, { name: "bad", pages: [null] }]),
    sortedPlugins: vue.ref([{ name: "alpha", desc: "market copy" }, market]),
    pluginMarketData: vue.ref([market]),
  };
  const routes = [];
  const storage = {
    getItem: () => JSON.stringify(["alpha", 42, "market", "missing", "beta"]),
    setItem: () => undefined,
  };
  const { default: component } = loadScript(
    "views/extension/InstalledPluginsTab.vue",
    {
      "vue-router": { useRouter: () => ({ push: (route) => routes.push(route) }) },
      "@/utils/inputValue": inputValue,
    },
    storage,
  );
  const model = setupComponent(t, component, { state });

  assert.deepEqual(
    model.filteredPlugins.value.map((plugin) => plugin.name),
    ["beta", "alpha"],
  );
  assert.equal(model.filteredPlugins.value[0], state.filteredPlugins.value[0]);
  assert.deepEqual(
    model.pinnedPlugins.value.map((plugin) => plugin.name),
    ["alpha", "market", "beta"],
  );
  assert.equal(model.pinnedPlugins.value[0], state.extension_data.data[0]);
  model.openPluginWebui(alpha);
  model.openPluginWebui({ name: "invalid", pages: [{ name: "settings" }] });
  assert.deepEqual(routes, [{ name: "PluginPage", params: { pluginName: "alpha", pageName: "settings" } }]);
});

test("MCP list guards retain arbitrary config and surface invalid payloads with loaders cleared", async () => {
  const server = {
    name: "oauth-server",
    active: true,
    connected: true,
    tools: ["search"],
    transport: "streamable_http",
    url: "https://example.com/mcp",
    oauth: { client_id: "sample-client" },
  };
  let payload = [server];
  const model = createMcpModel({ get: async () => ({ data: { status: "ok", data: payload } }) });
  model.getServers();
  assert.equal(model.loadingGettingServers, true);
  await setImmediate();
  assert.equal(model.loadingGettingServers, false);
  assert.deepEqual(model.mcpServers, [server]);
  assert.equal(model.mcpServerUpdateLoaders[server.name], false);

  payload = [{ ...server, tools: [null] }];
  model.getServers();
  await setImmediate();
  assert.deepEqual(model.mcpServers, [server]);
  assert.equal(model.loadingGettingServers, false);
  assert.equal(model.save_message_success, "error");
  assert.match(model.save_message, /Invalid MCP server list response/);
});

test("MCP editing preserves transport and OAuth config while JSON validation rejects non-objects", () => {
  const model = createMcpModel({});
  const config = { transport: "sse", url: "https://example.com/sse", oauth: { client_id: "sample-client" } };
  model.editServer({ ...config, name: "server", active: true, tools: [], connected: false, errlogs: [] });
  assert.deepEqual(JSON.parse(model.serverConfigJson), config);
  assert.equal(model.validateJson(), true);
  for (const json of ["null", "[]", "true", "1", '"server"', "{"]) {
    model.serverConfigJson = json;
    assert.equal(model.validateJson(), false);
    assert.match(model.jsonError, /jsonFormat/);
  }
  model.serverConfigJson = JSON.stringify({ mcpServers: { nested: { command: "python", args: ["-m", "server"] } } });
  assert.equal(model.validateJson(), true);
  assert.equal(model.jsonError, null);
});

test("MCP status failures restore activation and per-server loading for unknown errors", async () => {
  const model = createMcpModel({
    post: async () => {
      throw { response: { data: { message: "network unavailable" } } };
    },
  });
  const server = { name: "server", active: true, tools: [] };
  model.updateServerStatus(server);
  assert.equal(server.active, false);
  assert.equal(model.mcpServerUpdateLoaders.server, true);
  await setImmediate();
  assert.equal(server.active, true);
  assert.equal(model.mcpServerUpdateLoaders.server, false);
  assert.match(model.save_message, /network unavailable/);
});

test("MCP provider synchronization keeps token payload and success feedback", async () => {
  const calls = [];
  const model = createMcpModel({
    post: async (url, body) => {
      calls.push([url, body]);
      return { data: { status: "ok", message: "synced" } };
    },
    get: async () => ({ data: { status: "ok", data: [] } }),
  });
  model.mcpProviderToken = "  sample-token  ";
  model.showSyncMcpServerDialog = true;
  await model.syncMcpServers();
  assert.deepEqual(calls, [["/api/tools/mcp/sync-provider", { name: "modelscope", access_token: "sample-token" }]]);
  assert.equal(model.mcpProviderToken, "");
  assert.equal(model.showSyncMcpServerDialog, false);
  assert.equal(model.loading, false);
  assert.equal(model.save_message, "synced");
});

test("tool actions roll back unknown failures and update permission summaries", async () => {
  const messages = [];
  const { useToolActions } = loadScript("components/extension/componentPanel/composables/useToolActions.ts", {
    "@/api/v1": {
      toolApi: {
        setEnabled: async () => {
          throw "offline";
        },
        setPermission: async () => ({ data: { status: "ok" } }),
      },
    },
    "@/utils/inputValue": inputValue,
    "@/utils/errorUtils.js": errorUtils,
  });
  const tools = vue.ref([{ tool_key: "search", name: "search", description: "Search", active: true }]);
  const model = useToolActions(tools, (...message) => messages.push(message));
  await model.toggleTool(tools.value[0], "readonly", "updated", "failed");
  assert.equal(tools.value[0].active, true);
  assert.deepEqual(messages[0], ["offline", "error"]);
  assert.deepEqual(model.toolSummary.value, { total: 1, active: 1, inactive: 0 });
  await model.updateToolPermission(tools.value[0], "admin", "updated", "builtin", "failed");
  assert.equal(tools.value[0].permission, "admin");
  assert.equal(tools.value[0].permission_configured, true);
});
