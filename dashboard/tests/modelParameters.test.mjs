import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";
import * as vue from "vue";
import { compileScript, parse } from "vue/compiler-sfc";
import * as configValue from "../src/utils/configValue.mjs";

const { descriptor } = parse(
  readFileSync(
    new URL("../src/components/config/ModelParameters.vue", import.meta.url),
    "utf8",
  ),
);
const script = ts.transpile(
  compileScript(descriptor, { id: "model-parameters-test" }).content,
  { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS },
);

/**
 * Run the real component setup and save handler against an in-memory API.
 *
 * Args:
 *     t: Test context responsible for stopping component watchers.
 *     provider: Model configuration overrides.
 *     source: Shared provider-source configuration.
 *     options: Selected model and profile-scoped editor state for lifecycle tests.
 *
 * Returns:
 *     Component state, lifecycle scope, API fixtures, requests, and update payloads.
 */
async function setup(t, provider, source = {}, options = {}) {
  const data = {
    provider: {
      id: "test-model",
      enable: true,
      provider_type: "chat_completion",
      provider_source_id: "test-source",
      modalities: ["text", "tool_use"],
      ...provider,
    },
    source: { id: "test-source", ...source },
  };
  const updates = [];
  const requests = [];
  const providerApi = {
    async schema() {
      requests.push("schema");
      return {
        data: {
          status: "ok",
          data: {
            providers: [structuredClone(data.provider)],
            provider_sources: [structuredClone(data.source)],
            config_schema: {
              provider: {
                items: {
                  custom_extra_body: {
                    template_schema: {
                      temperature: {
                        type: "float",
                        default: 0.6,
                        slider: { min: 0, max: 2 },
                      },
                      max_tokens: { type: "int", default: 8192 },
                      reasoning_effort: { type: "string", default: "high" },
                    },
                  },
                },
              },
            },
          },
        },
      };
    },
    async get(id, merged = false) {
      assert.equal(id, data.provider.id);
      return {
        data: {
          status: "ok",
          data: {
            provider: structuredClone(
              merged ? { ...data.source, ...data.provider } : data.provider,
            ),
          },
        },
      };
    },
    async update(id, config) {
      assert.equal(id, data.provider.id);
      data.provider = JSON.parse(JSON.stringify(config));
      updates.push(data.provider);
      return { data: { status: "ok" } };
    },
  };
  const imports = {
    vue: {
      ...vue,
      inject: (key, fallback) => {
        assert.equal(key, "modelParameterEditorState");
        return options.editorState || fallback;
      },
    },
    "@/api/v1": { providerApi },
    "@/utils/configValue.mjs": configValue,
    "@/components/shared/ConfigItemRenderer.vue": {},
    "@/i18n/composables": { useModuleI18n: () => ({ tm: (key) => key }) },
  };
  const context = vm.createContext({
    exports: {},
    require: (name) => {
      assert.ok(name in imports, `Unexpected import: ${name}`);
      return imports[name];
    },
  });
  vm.runInContext(script, context);
  const scope = vue.effectScope();
  t.after(() => scope.stop());
  const props = vue.reactive({
    providerId: options.providerId ?? data.provider.id,
  });
  const state = scope.run(() =>
    context.exports.default.setup(props, { expose() {} }),
  );
  await new Promise(setImmediate);
  assert.equal(state.error.value, "");
  if (props.providerId) assert.ok(state.draft.value);
  state.valid.value = true;
  return { state, data, updates, requests, props, scope, providerApi };
}

test("automatic model selection never edits the first configured provider", async (t) => {
  const { state, updates, requests } = await setup(
    t,
    { type: "openai_chat_completion" },
    {},
    { providerId: "" },
  );
  assert.equal(state.draft.value, null);
  assert.equal(state.loading.value, false);
  assert.deepEqual(requests, []);
  await state.saveParameters();
  assert.deepEqual(updates, []);
});

test("search and tab remounts retain the unsaved draft and its original baseline", async (t) => {
  const editorState = vue.shallowRef(null);
  const provider = {
    type: "openai_responses",
    custom_extra_body: { max_output_tokens: 8192, top_p: 0.8 },
  };
  const first = await setup(t, provider, {}, { editorState });
  first.state.draft.value.custom_extra_body.max_tokens = "12345";
  first.scope.stop();

  const restored = await setup(
    t,
    { ...provider, custom_extra_body: { max_output_tokens: 8192, top_p: 0.9 } },
    {},
    { editorState },
  );
  assert.equal(
    restored.state.draft.value.custom_extra_body.max_tokens,
    "12345",
  );
  assert.equal(restored.state.dirty.value, true);
  assert.deepEqual(restored.requests, []);
  await restored.state.saveParameters();
  assert.deepEqual(restored.updates[0].custom_extra_body, {
    max_output_tokens: 12345,
    top_p: 0.9,
  });
  assert.equal(restored.state.dirty.value, false);
});

test("returning to a saved editor reloads current provider values", async (t) => {
  const editorState = vue.shallowRef(null);
  const first = await setup(t, {}, {}, { editorState });
  first.state.draft.value.custom_extra_body.temperature = 0.5;
  await first.state.saveParameters();
  first.scope.stop();
  const restored = await setup(
    t,
    { custom_extra_body: { temperature: 0.8 } },
    {},
    { editorState },
  );
  assert.equal(restored.state.draft.value.custom_extra_body.temperature, 0.8);
  assert.deepEqual(restored.requests, ["schema"]);
  assert.equal(restored.state.dirty.value, false);
});

test("clearing the selected model discards its draft and disables saving", async (t) => {
  const { state, props, requests, updates } = await setup(t, {});
  state.draft.value.custom_extra_body.max_tokens = 12345;
  props.providerId = "";
  await new Promise(setImmediate);
  assert.equal(state.draft.value, null);
  assert.equal(state.loading.value, false);
  assert.deepEqual(requests, ["schema"]);
  await state.saveParameters();
  assert.deepEqual(updates, []);
  props.providerId = "test-model";
  await new Promise(setImmediate);
  assert.equal(state.draft.value.custom_extra_body.max_tokens, undefined);
  assert.equal(state.dirty.value, false);
});

test("a pending save completes across editor remounts without duplicate writes", async (t) => {
  const editorState = vue.shallowRef(null);
  const first = await setup(t, {}, {}, { editorState });
  let finishSave;
  const pendingSave = new Promise((resolve) => {
    finishSave = resolve;
  });
  const update = first.providerApi.update;
  first.providerApi.update = async (...args) => {
    await pendingSave;
    return update(...args);
  };
  first.state.draft.value.custom_extra_body.max_tokens = 12345;
  const saving = first.state.saveParameters();
  first.scope.stop();
  const restored = await setup(t, {}, {}, { editorState });
  assert.equal(restored.state.saving.value, true);
  assert.equal(restored.state.draft.value.custom_extra_body.max_tokens, 12345);
  await restored.state.saveParameters();
  assert.deepEqual(restored.updates, []);
  finishSave();
  await saving;
  assert.equal(first.updates.length, 1);
  assert.equal(restored.state.saved.value, true);
  assert.equal(restored.state.dirty.value, false);
  assert.equal(restored.state.saving.value, false);
});

test("model drafts are isolated between configuration pages", async (t) => {
  const first = await setup(t, {}, {}, { editorState: vue.shallowRef(null) });
  first.state.draft.value.custom_extra_body.max_tokens = 12345;
  first.scope.stop();
  const otherProfile = await setup(
    t,
    {},
    {},
    { editorState: vue.shallowRef(null) },
  );
  assert.equal(
    otherProfile.state.draft.value.custom_extra_body.max_tokens,
    undefined,
  );
  assert.equal(otherProfile.state.dirty.value, false);
});

test("Anthropic reads, saves, and clears native adaptive effort", async (t) => {
  const { state, data, updates } = await setup(
    t,
    { custom_extra_body: { temperature: 0, reasoning_effort: "invalid" } },
    {
      type: "anthropic_chat_completion",
      anth_thinking_config: {
        type: "adaptive",
        budget: 2048,
        effort: "high",
      },
    },
  );
  assert.equal(state.draft.value.custom_extra_body.reasoning_effort, "high");
  assert.equal(state.supportsReasoning.value, true);
  state.draft.value.custom_extra_body.reasoning_effort = "low";
  data.provider.custom_extra_body.top_p = 0.9;
  data.source.anth_thinking_config.budget = 4096;
  await state.saveParameters();
  assert.equal(updates.length, 1);
  assert.deepEqual(updates[0].anth_thinking_config, {
    type: "adaptive",
    budget: 4096,
    effort: "low",
  });
  assert.deepEqual(updates[0].custom_extra_body, {
    temperature: 0,
    top_p: 0.9,
  });
  assert.equal(
    updates[0].type,
    undefined,
    "source fields must not leak into the model",
  );
  assert.equal(data.source.anth_thinking_config.effort, "high");

  state.draft.value.custom_extra_body.reasoning_effort = "";
  await state.saveParameters();
  assert.deepEqual(updates[1].anth_thinking_config, {
    type: "adaptive",
    budget: 4096,
  });
  assert.equal("reasoning_effort" in updates[1].custom_extra_body, false);
});

for (const type of [
  "kimi_code_chat_completion",
  "minimax_token_plan",
  "xiaomi_token_plan",
]) {
  test(`${type} uses native adaptive effort`, async (t) => {
    const { state, updates } = await setup(
      t,
      {},
      {
        type,
        anth_thinking_config: { type: "adaptive", effort: "high" },
      },
    );
    assert.equal(state.supportsReasoning.value, true);
    assert.equal(state.draft.value.custom_extra_body.reasoning_effort, "high");
    state.draft.value.custom_extra_body.reasoning_effort = "low";
    await state.saveParameters();
    assert.equal(updates[0].anth_thinking_config.effort, "low");
    assert.equal("reasoning_effort" in updates[0].custom_extra_body, false);
  });
}

test("Anthropic native request overrides stay effective without losing other output options", async (t) => {
  const { state, updates } = await setup(t, {
    type: "anthropic_chat_completion",
    anth_thinking_config: { type: "adaptive", effort: "low" },
    custom_extra_body: {
      output_config: { effort: "high", format: { type: "json_schema" } },
    },
  });
  assert.equal(state.draft.value.custom_extra_body.reasoning_effort, "high");
  state.draft.value.custom_extra_body.reasoning_effort = "medium";
  await state.saveParameters();
  assert.equal(updates[0].anth_thinking_config.effort, "medium");
  assert.deepEqual(updates[0].custom_extra_body.output_config, {
    effort: "medium",
    format: { type: "json_schema" },
  });
  state.draft.value.custom_extra_body.reasoning_effort = null;
  await state.saveParameters();
  assert.deepEqual(updates[1].anth_thinking_config, { type: "adaptive" });
  assert.deepEqual(updates[1].custom_extra_body.output_config, {
    format: { type: "json_schema" },
  });
});

test("manual Anthropic thinking keeps its mode and budget when saving other parameters", async (t) => {
  const { state, updates } = await setup(t, {
    type: "anthropic_chat_completion",
    anth_thinking_config: { type: "", budget: 2048, effort: "high" },
  });
  assert.equal(state.supportsReasoning.value, false);
  state.draft.value.custom_extra_body.temperature = 0.5;
  await state.saveParameters();
  assert.deepEqual(updates[0].anth_thinking_config, {
    type: "",
    budget: 2048,
    effort: "high",
  });
  assert.deepEqual(updates[0].custom_extra_body, { temperature: 0.5 });
});

test("Responses edits and clearing honor native fields while preserving unrelated options", async (t) => {
  const { state, data, updates } = await setup(t, {
    type: "openai_responses",
    custom_extra_body: {
      max_output_tokens: 4096,
      max_tokens: 1024,
      reasoning: { effort: "high", summary: "auto" },
      reasoning_effort: "low",
      top_p: 0.8,
    },
  });
  assert.equal(state.draft.value.custom_extra_body.max_tokens, 4096);
  assert.equal(state.draft.value.custom_extra_body.reasoning_effort, "high");
  assert.equal(state.tokenRules[0]("1e5"), true);
  state.draft.value.custom_extra_body.max_tokens = "1e5";
  state.draft.value.custom_extra_body.reasoning_effort = "xhigh";
  data.provider.custom_extra_body.top_p = 0.9;
  await state.saveParameters();
  assert.deepEqual(updates[0].custom_extra_body, {
    max_output_tokens: 100000,
    reasoning: { effort: "xhigh", summary: "auto" },
    top_p: 0.9,
  });
  state.draft.value.custom_extra_body.max_tokens = null;
  state.draft.value.custom_extra_body.reasoning_effort = "";
  await state.saveParameters();
  assert.deepEqual(updates[1].custom_extra_body, {
    reasoning: { summary: "auto" },
    top_p: 0.9,
  });
});

test("Responses legacy aliases migrate to native fields and clear without empty objects", async (t) => {
  const { state, updates } = await setup(
    t,
    { type: "openai_responses" },
    {
      custom_extra_body: {
        max_tokens: 4096,
        reasoning_effort: "high",
        top_p: 0.8,
      },
    },
  );
  assert.equal(state.draft.value.custom_extra_body.max_tokens, 4096);
  assert.equal(state.draft.value.custom_extra_body.reasoning_effort, "high");
  state.draft.value.custom_extra_body.max_tokens = 8192;
  state.draft.value.custom_extra_body.reasoning_effort = "low";
  await state.saveParameters();
  assert.deepEqual(updates[0].custom_extra_body, {
    max_output_tokens: 8192,
    reasoning: { effort: "low" },
    top_p: 0.8,
  });
  state.draft.value.custom_extra_body.max_tokens = "";
  state.draft.value.custom_extra_body.reasoning_effort = null;
  await state.saveParameters();
  assert.deepEqual(updates[1].custom_extra_body, { top_p: 0.8 });
});

for (const type of [
  "openai_chat_completion",
  "openai_responses",
  "anthropic_chat_completion",
]) {
  test(`${type} saves only edited fields and preserves newer model settings`, async (t) => {
    const { state, data, updates } = await setup(t, {
      type,
      anth_thinking_config: { type: "adaptive", effort: "low" },
      custom_extra_body: { temperature: 0.5, max_tokens: 1024 },
    });
    data.provider.custom_extra_body.temperature = 0.8;
    data.provider.custom_extra_body.reasoning = {
      effort: "high",
      summary: "auto",
    };
    data.provider.anth_thinking_config.effort = "high";
    data.provider.modalities.push("image");
    state.draft.value.custom_extra_body.max_tokens = 2048;
    await state.saveParameters();
    assert.equal(updates[0].custom_extra_body.temperature, 0.8);
    assert.deepEqual(updates[0].custom_extra_body.reasoning, {
      effort: "high",
      summary: "auto",
    });
    assert.equal(updates[0].anth_thinking_config.effort, "high");
    assert.deepEqual(updates[0].modalities, ["text", "tool_use", "image"]);
    assert.equal(
      updates[0].custom_extra_body[
        type === "openai_responses" ? "max_output_tokens" : "max_tokens"
      ],
      2048,
    );

    state.draft.value.custom_extra_body.max_tokens = "";
    await state.saveParameters();
    assert.equal(updates[1].custom_extra_body.temperature, 0.8);
    assert.equal("max_tokens" in updates[1].custom_extra_body, false);
    assert.equal("max_output_tokens" in updates[1].custom_extra_body, false);
  });
}

test("Chat Completions preserves inherited parameters for capability edits and uses model type when editing parameters", async (t) => {
  const { state, updates } = await setup(
    t,
    {
      type: "openai_chat_completion",
    },
    {
      type: "anthropic_chat_completion",
      custom_extra_body: { temperature: 0, top_p: 0.8 },
    },
  );
  state.draft.value.modalities.push("image");
  await state.saveParameters();
  assert.equal(updates[0].custom_extra_body, undefined);
  assert.deepEqual(updates[0].modalities, ["text", "tool_use", "image"]);
  state.draft.value.custom_extra_body.max_tokens = "1e5";
  state.draft.value.custom_extra_body.reasoning_effort = "low";
  await state.saveParameters();
  assert.deepEqual(updates[1].custom_extra_body, {
    temperature: 0,
    top_p: 0.8,
    max_tokens: 100000,
    reasoning_effort: "low",
  });
});

test("Gemini capability edits preserve unsupported request parameters", async (t) => {
  const { state, updates } = await setup(t, {
    type: "googlegenai_chat_completion",
    custom_extra_body: { temperature: 0.5, reasoning_effort: "low" },
  });
  assert.equal(state.supportsExtraBody.value, false);
  assert.equal(state.supportsReasoning.value, false);
  state.draft.value.modalities.push("image");
  await state.saveParameters();
  assert.deepEqual(updates[0].custom_extra_body, {
    temperature: 0.5,
    reasoning_effort: "low",
  });
  assert.deepEqual(updates[0].modalities, ["text", "tool_use", "image"]);
});
