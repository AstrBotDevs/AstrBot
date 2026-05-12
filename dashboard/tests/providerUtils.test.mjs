import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));

async function loadProviderUtils() {
  const source = await readFile(join(__dirname, '../src/utils/providerUtils.js'), 'utf8');
  return import(`data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`);
}

test('OpenAI Responses template uses OpenAI provider description', async () => {
  const { getProviderDescription } = await loadProviderUtils();
  const tm = (key, params) => `${key}:${params?.type ?? ''}`;
  const description = getProviderDescription(
    { provider: 'openai', type: 'openai_responses_completion' },
    'OpenAI Responses',
    tm,
  );

  assert.equal(description, 'providers.description.openai:openai_responses_completion');
});
