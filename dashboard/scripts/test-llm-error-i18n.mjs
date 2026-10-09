import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import vm from 'node:vm';
import ts from 'typescript';

const require = createRequire(import.meta.url);
const source = readFileSync(new URL('../src/composables/useMessages.ts', import.meta.url), 'utf8');
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
});
let catalog;
const module = { exports: {} };
vm.runInNewContext(outputText, {
  exports: module.exports,
  require(name) {
    if (name === 'vue') return require('vue');
    if (name === '@/i18n/composables') {
      return {
        useI18n: () => ({
          t(key, params = {}) {
            const code = key.replace('features.chat.llmErrors.', '');
            assert.ok(catalog[code], `Missing translation: ${key}`);
            return catalog[code].replace(/\{(\w+)\}/g, (_, name) => {
              assert.ok(name in params, `Missing interpolation: ${name}`);
              return params[name];
            });
          },
        }),
      };
    }
    if (name.startsWith('@/api/')) return {};
    throw new Error(`Unexpected import: ${name}`);
  },
});
const { messagePartText, normalizeMessageParts, appendPlain } = module.exports;
const params = {
  noProvider: {},
  providerNotFound: { provider: 'test-provider' },
  invalidProviderType: { provider_type: 'EmbeddingProvider' },
  requestFailed: { detail: 'API returned 429' },
  blockedProvider: { api_base: 'https://blocked.example' },
  agentRequestFailed: { detail: 'API returned 500' },
};
const saved = { type: 'plain', text: 'Fallback', error_code: 'noProvider', error_params: {} };
for (const locale of ['zh-CN', 'en-US', 'ja-JP', 'ru-RU']) {
  const data = readFileSync(new URL(`../src/i18n/locales/${locale}/features/chat.json`, import.meta.url), 'utf8');
  catalog = JSON.parse(data.replace(/^\uFEFF/, '')).llmErrors;
  assert.deepEqual(Object.keys(catalog).sort(), Object.keys(params).sort());
  for (const [code, values] of Object.entries(params)) {
    const translated = messagePartText({ ...saved, error_code: code, error_params: values });
    assert.notEqual(translated, saved.text);
    assert.ok(!/\{\w+\}/.test(translated));
    for (const value of Object.values(values)) assert.ok(translated.includes(value));
  }
  const restored = normalizeMessageParts(JSON.parse(JSON.stringify([saved])))[0];
  assert.equal(messagePartText(restored), catalog.noProvider);
  assert.equal(messagePartText({ type: 'plain', text: 'Custom reply' }), 'Custom reply');
  assert.equal(messagePartText({ ...saved, error_code: 'futureCode' }), 'Fallback');
}
const record = { content: { type: 'bot', message: [{ ...saved }] } };
appendPlain(record, 'Later output');
assert.equal(record.content.message[0].text, 'Fallback');
assert.equal(record.content.message[1].text, 'Later output');
console.log('LLM error localization passed: four locales, interpolation, history reload, locale switching, fallback, and adjacent output.');
