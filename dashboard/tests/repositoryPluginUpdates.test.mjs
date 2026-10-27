import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";

const source = readFileSync(
  new URL("../src/views/extension/useExtensionPage.js", import.meta.url),
  "utf8",
);
const ast = ts.createSourceFile(
  "extension.js",
  source,
  ts.ScriptTarget.Latest,
  true,
);
const declarations = new Map();
function visit(node) {
  if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name))
    declarations.set(node.name.text, node.getText(ast));
  ts.forEachChild(node, visit);
}
visit(ast);

async function check(extension, marketPlugins = []) {
  const requests = [];
  const context = vm.createContext({
    extension_data: { data: [extension] },
    sourcePlugins: new Map(),
    selectedSource: { value: "" },
    pluginMarketData: { value: marketPlugins },
    commonStore: {
      getPluginCollections: async (...args) => {
        requests.push(args);
        return marketPlugins;
      },
    },
    normalizeRegistryUrl: (value) => value || "",
    normalizeInstallUrl: (value) => value || "",
    normalizeStr: (value) => String(value || "").toLowerCase(),
    getMarketPluginId: (plugin) => plugin.market_plugin_id,
    tm: () => "Unknown",
    console,
  });
  for (const name of [
    "normalizeVersionParts",
    "compareVersions",
    "buildMarketPluginLookup",
    "checkUpdate",
  ]) {
    vm.runInContext(`const ${declarations.get(name)};`, context);
  }
  await vm.runInContext("checkUpdate()", context);
  return requests;
}

for (const [local, remote, expected] of [
  ["v1.0.0", "v1.1.0", true],
  ["1.1.0", "1.1.0", false],
  ["2.0.0", "1.1.0", false],
  ["1.1.0-beta", "1.1.0", true],
  ["1.0.0", "", false],
  ["1.0.0", "Unknown", false],
  ["unknown", "2.0.0", false],
]) {
  test(`repository observation ${local} -> ${
    remote || "missing"
  }: update=${expected}`, async () => {
    const extension = {
      version: local,
      updates_enabled: true,
      install_source: {
        install_method: "repository",
        repository_version: remote,
      },
    };
    assert.deepEqual(await check(extension), []);
    assert.equal(extension.has_update, expected);
    assert.equal(extension.online_version, remote);
  });
}

test("disabled repository plugins never advertise an update", async () => {
  const extension = {
    version: "1.0",
    updates_enabled: false,
    install_source: { install_method: "repository", repository_version: "2.0" },
  };
  await check(extension);
  assert.equal(extension.has_update, false);
});

test("market plugins continue to use market versions rather than repository observations", async () => {
  const extension = {
    version: "1.0",
    updates_enabled: true,
    install_source: {
      install_method: "market",
      market_plugin_id: "owner/plugin",
      repository_version: "9.0",
    },
  };
  await check(extension, [
    { market_plugin_id: "owner/plugin", version: "1.0" },
  ]);
  assert.equal(extension.online_version, "1.0");
  assert.equal(extension.has_update, false);
});

test("source confirmation sends the validated metadata version and refreshes update state", async () => {
  const calls = [];
  const context = vm.createContext({
    sourceBindingDialog: {
      extension: { name: "demo" },
      selectedKey: "repo",
      candidates: [
        {
          key: "repo",
          install_method: "repository",
          version: "Translated display text",
          metadata: { version: "v2.1.0" },
        },
      ],
      saving: false,
    },
    pluginApi: {
      bindSource: async (name, payload) => {
        calls.push([name, payload]);
        return { data: { status: "ok" } };
      },
    },
    toast() {},
    tm: (key) => key,
    closePluginSourceBindingDialog() {},
    getExtensions: async () => {
      calls.push("list");
    },
    checkAlreadyInstalled() {},
    checkUpdate: async () => {
      calls.push("updates");
    },
    continuePendingUpdateAfterBinding: async () => {},
  });
  vm.runInContext(
    `const ${declarations.get("confirmPluginSourceBinding")};`,
    context,
  );
  await vm.runInContext("confirmPluginSourceBinding()", context);
  assert.deepEqual(JSON.parse(JSON.stringify(calls)), [
    ["demo", { install_method: "repository", repository_version: "v2.1.0" }],
    "list",
    "updates",
  ]);
});
