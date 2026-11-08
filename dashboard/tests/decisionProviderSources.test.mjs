import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';
import ts from 'typescript';
import { computed, ref } from 'vue';
import { parse } from 'vue/compiler-sfc';

function setup(type = 'openai_decision') {
  const source = readFileSync(new URL('../src/composables/useProviderSources.ts', import.meta.url), 'utf8');
  const exports = {};
  const calls = [];
  const api = {
    sourceModels: async () => ({ data: { status: 'ok', data: {
      models: ['gateway/unknown-a', 'unknown-b'],
      model_metadata: { 'gateway/unknown-a': { tool_call: true, limit: { context: 128000 } } },
    } } }),
    createInSource: async (sourceId, config) => { calls.push({ sourceId, config }); return { data: { status: 'ok' } }; },
  };
  const modules = {
    vue: { ref, computed, watch() {}, onMounted() {}, nextTick: callback => callback?.() },
    '@/api/v1': { providerApi: api },
    '@/utils/providerUtils': { getProviderIcon() {}, isMonochromeProviderIcon() {} },
    '@/utils/confirmDialog': { useConfirmDialog() {} },
    '@/utils/inputValue': { normalizeTextInput: value => value || '' },
    '@/utils/sponsorCatalog': { sponsorCatalog: ref(null), loadSponsorCatalog() {} },
    '@/i18n/composables': { useI18n: () => ({ locale: ref('en-US') }) },
  };
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
  vm.runInNewContext(code, { exports, require: name => modules[name], console });
  const state = exports.useProviderSources({ tm: key => key, showMessage() {}, defaultTab: 'decision' });
  state.selectProviderSource({ id: 'decisions', type, provider_type: 'decision' });
  return { state, calls };
}

test('Decision sources create independent unknown-model instances without chat settings', async () => {
  const { state } = setup();
  await state.fetchAvailableModels();
  assert.deepEqual(Array.from(state.availableModels.value, item => item.name), ['gateway/unknown-a', 'unknown-b']);
  assert.equal(state.availableModels.value[0].metadata, null);
  assert.equal(state.filteredMergedModelEntries.value[0].hasModelMetadata, false);
  for (const model of ['gateway/unknown-a', 'unknown-b', 'manual-private-model']) {
    const config = JSON.parse(JSON.stringify(state.buildModelProviderConfig(model)));
    assert.deepEqual(config, { id: `decisions/${model}`, enable: true, provider_source_id: 'decisions', model });
  }
});

test('Responses sources retain existing chat model parameters', () => {
  const { state } = setup('openai_responses');
  const config = state.buildModelProviderConfig('unknown-chat-model');
  assert.deepEqual(Array.from(config.modalities), ['text', 'image', 'audio', 'tool_use']);
  assert.equal(config.max_context_tokens, 0);
});

test('Decision workbench routes OpenAI sources and keeps System One in its legacy form', () => {
  const source = readFileSync(new URL('../src/views/ProviderPage.vue', import.meta.url), 'utf8');
  const { descriptor } = parse(source);
  const ast = ts.createSourceFile('ProviderPage.js', descriptor.scriptSetup.content, ts.ScriptTarget.Latest, true);
  const functions = ast.statements.filter(statement => ts.isFunctionDeclaration(statement)
    && ['selectSidebarProvider', 'addSidebarProvider'].includes(statement.name?.text))
    .map(statement => statement.getText(ast)).join('\n');
  const calls = [];
  const selectedLegacyProvider = ref({ type: 'system_one_decision' });
  const scope = {
    selectedProviderType: ref('decision'), selectedLegacyProvider,
    configSchema: ref({ provider: { config_template: {
      'OpenAI Decisions': { type: 'openai_decision' }, 'TypeSafe System One': { type: 'system_one_decision' },
    } } }),
    addProviderSource: value => calls.push(['source-add', value]),
    addLegacyProvider: value => calls.push(['legacy-add', value]),
    selectProviderSource: value => calls.push(['source-select', value.type]),
    selectLegacyProvider: value => calls.push(['legacy-select', value.type]),
  };
  vm.createContext(scope);
  vm.runInContext(functions, scope);
  scope.addSidebarProvider('OpenAI Decisions');
  assert.equal(selectedLegacyProvider.value, null);
  scope.addSidebarProvider('TypeSafe System One');
  scope.selectSidebarProvider({ type: 'openai_decision' });
  scope.selectSidebarProvider({ type: 'system_one_decision' });
  assert.deepEqual(calls, [
    ['source-add', 'OpenAI Decisions'], ['legacy-add', 'TypeSafe System One'],
    ['source-select', 'openai_decision'], ['legacy-select', 'system_one_decision'],
  ]);
});
