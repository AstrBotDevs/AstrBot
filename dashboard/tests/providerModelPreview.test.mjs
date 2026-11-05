import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";
import * as vue from "vue";

test("model previews stay consistent across selection and saving", async (t) => {
  const source = { id: "deepseek", provider: "deepseek" };
  let stored = {
    id: "deepseek/deepseek-flash",
    provider_source_id: source.id,
    model: "deepseek-flash",
    modalities: ["text", "image"],
    max_context_tokens: 2048,
    enable: true,
  };
  const otherSource = { id: "other", provider: "other" };
  const otherProvider = {
    ...structuredClone(stored),
    id: "other/model",
    provider_source_id: otherSource.id,
    model: "other-model",
  };
  const metadata = {
    modalities: { input: ["text", "image"] },
    tool_call: true,
    reasoning: true,
    limit: { context: 1000000, output: 64000 },
  };
  const imports = {
    vue: { ...vue, onMounted: () => {} },
    "@/api/v1": {
      providerApi: {
        schema: async () => ({
          data: {
            status: "ok",
            data: {
              providers: [structuredClone(stored), structuredClone(otherProvider)],
              provider_sources: [source, otherSource],
              model_metadata: {
                "deepseek-flash": structuredClone(metadata),
                "other-model": structuredClone(metadata),
              },
            },
          },
        }),
        update: async (id, config) => {
          if (id === otherProvider.id) {
            Object.assign(otherProvider, JSON.parse(JSON.stringify(config)));
          } else {
            assert.equal(id, stored.id);
            stored = JSON.parse(JSON.stringify(config));
          }
          return { data: { status: "ok" } };
        },
      },
    },
    "@/utils/providerUtils": {},
    "@/utils/confirmDialog": { useConfirmDialog: () => ({}) },
    "@/utils/inputValue": {},
    "@/utils/sponsorCatalog": {},
    "@/i18n/composables": { useI18n: () => ({ locale: vue.ref("en-US") }) },
  };
  const exports = {};
  for (const name of ["useProviderSources", "useProviderModelConfigDialog"]) {
    const code = readFileSync(
      new URL(`../src/composables/${name}.ts`, import.meta.url),
      "utf8",
    );
    vm.runInNewContext(
      ts.transpileModule(code, {
        compilerOptions: {
          module: ts.ModuleKind.CommonJS,
          target: ts.ScriptTarget.ES2020,
        },
      }).outputText,
      { exports, require: (name) => imports[name], console },
    );
  }
  const options = { tm: (key) => key, showMessage: () => {} };
  const state = exports.useProviderSources(options);
  const dialog = exports.useProviderModelConfigDialog({ ...state, ...options });
  const panel = readFileSync(
    new URL("../src/components/provider/ProviderModelsPanel.vue", import.meta.url),
    "utf8",
  );
  const badges = vm.runInNewContext(
    panel.slice(
      panel.indexOf("const capabilityBadges ="),
      panel.indexOf("const isProviderTesting ="),
    ) + "\ncapabilityBadges",
    { props: { ...state, ...options } },
  );

  await state.loadConfig();
  state.selectProviderSource(state.providerSources.value[0]);
  const before = state.mergedModelEntries.value[0];
  assert.equal(before.hasModelMetadata, true);
  assert.equal(state.formatContextLimit(before.metadata), "2K");
  const original = structuredClone(stored);
  dialog.openProviderEdit(before.provider);
  await dialog.saveEditedProvider();
  const after = state.mergedModelEntries.value[0];
  assert.deepEqual(stored, original);
  assert.equal(state.formatContextLimit(after.metadata), "2K");
  assert.deepEqual(badges(after), badges(before));
  assert.equal(state.modelMetadata.value[stored.model].limit.context, 1000000);
  assert.equal(after.metadata.limit.output, 64000);

  state.selectProviderSource(state.providerSources.value[0]);
  assert.deepEqual(badges(state.mergedModelEntries.value[0]), badges(before));
  assert.equal(state.mergedModelEntries.value[0].metadata.limit.context, 2048);

  // Automatic limits retain catalog metadata, while custom models use config.
  state.providers.value[0].max_context_tokens = 0;
  assert.equal(state.mergedModelEntries.value[0].metadata.limit.context, 1000000);
  state.providers.value[0].model = "custom-model";
  state.providers.value[0].max_context_tokens = 4096;
  const custom = state.mergedModelEntries.value[0];
  assert.equal(custom.hasModelMetadata, false);
  assert.equal(custom.metadata.limit.context, 4096);
  assert.equal(state.supportsImageInput(custom.metadata), true);

  // An explicit override must not mutate fetched candidate metadata either.
  state.providers.value[0].model = stored.model;
  state.availableModels.value = [{ name: stored.model, metadata }];
  assert.equal(state.mergedModelEntries.value[0].metadata.limit.context, 4096);
  assert.equal(state.availableModels.value[0].metadata.limit.context, 1000000);

  for (const outcome of ["success", "error response", "network error"]) {
    await t.test(`cross-source previews survive a model fetch: ${outcome}`, async () => {
      imports["@/api/v1"].providerApi.sourceModels = async (id) => {
        assert.equal(id, source.id);
        if (outcome === "network error") throw new Error("Offline");
        if (outcome === "error response") {
          return { data: { status: "error", message: "Unavailable" } };
        }
        return {
          data: {
            status: "ok",
            data: {
              models: [stored.model],
              model_metadata: { [stored.model]: structuredClone(metadata) },
            },
          },
        };
      };
      await state.loadConfig();
      state.selectProviderSource(otherSource);
      const initial = state.mergedModelEntries.value[0];
      state.selectProviderSource(source);
      await state.fetchAvailableModels();
      state.selectProviderSource(otherSource);
      const switched = state.mergedModelEntries.value[0];
      assert.deepEqual(badges(switched), badges(initial));
      assert.equal(switched.metadata.limit.context, 2048);
      dialog.openProviderEdit(switched.provider);
      await dialog.saveEditedProvider();
      const saved = state.mergedModelEntries.value[0];
      assert.deepEqual(badges(saved), badges(initial));
      assert.equal(saved.metadata.limit.context, 2048);
    });
  }
});
