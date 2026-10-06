import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import test from 'node:test';

const root = new URL('../src/i18n/locales/', import.meta.url);
const locales = readdirSync(root, { withFileTypes: true }).filter(entry => entry.isDirectory()).map(entry => entry.name);
const read = (locale, module) => JSON.parse(readFileSync(new URL(`${locale}/${module}.json`, root), 'utf8').replace(/^\uFEFF/, ''));

for (const locale of locales) {
  test(`${locale}: onboarding translations, placeholders and usage notice are complete`, () => {
    const welcome = read(locale, 'features/welcome');
    const sections = [
      [read('en-US', 'features/welcome').guide, welcome.guide],
      [read('en-US', 'features/welcome').onboard, welcome.onboard],
      [read('en-US', 'features/settings').system.onboarding, read(locale, 'features/settings').system.onboarding],
    ];
    for (const [expected, actual] of sections) {
      assert.deepEqual(Object.keys(actual).sort(), Object.keys(expected).sort());
      for (const [key, value] of Object.entries(expected)) {
        assert.equal(typeof actual[key], 'string', key);
        assert.ok(actual[key].trim(), key);
        assert.deepEqual((actual[key].match(/\{\w+\}/g) || []).sort(), (value.match(/\{\w+\}/g) || []).sort(), key);
      }
    }
    for (const file of ['OnboardingModel.vue', 'OnboardingSetup.vue', 'OnboardingWelcome.vue']) {
      const source = readFileSync(new URL(`../src/components/${file}`, import.meta.url), 'utf8');
      for (const [, section, key] of source.matchAll(/\b(?:t|tm)\(['"](guide|onboard)\.([^'"]+)['"]/g)) {
        assert.ok(welcome[section][key], `${file}: ${section}.${key}`);
      }
    }
    const fields = read(locale, 'features/provider').providerSources.fields;
    assert.ok(fields.apiKey.trim());
    assert.notEqual(fields.apiKey, fields.baseUrl, 'The API key is not a URL');
    const notice = locale === 'zh-CN' ? 'FIRST_NOTICE.md' : `FIRST_NOTICE.${locale}.md`;
    assert.ok(readFileSync(new URL(`../../${notice}`, import.meta.url), 'utf8').trim());
  });
}

test('onboarding API field labels retain their technical names', () => {
  const source = readFileSync(new URL('../src/components/OnboardingModel.vue', import.meta.url), 'utf8');
  assert.match(source, /\slabel="API Key"/);
  assert.match(source, /\slabel="API Base URL"/);
});
