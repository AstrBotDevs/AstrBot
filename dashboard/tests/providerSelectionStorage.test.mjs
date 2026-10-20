import test from 'node:test';
import assert from 'node:assert/strict';

import { clearProviderSelectionStorage } from '../src/utils/providerSelectionStorage.mjs';

function makeStorage(entries) {
  const map = new Map(Object.entries(entries));
  return {
    map,
    get length() { return map.size; },
    key: (i) => [...map.keys()][i] ?? null,
    getItem: (k) => (map.has(k) ? map.get(k) : null),
    setItem: (k, v) => map.set(k, String(v)),
    removeItem: (k) => map.delete(k),
  };
}

test('clearProviderSelectionStorage removes global and every session provider key', () => {
  const storage = makeStorage({
    selectedProvider: 'p1',
    selectedProviderModel: 'm1',
    'chat.sessionProvider.a': '{"providerId":"p1","modelName":"m1"}',
    'chat.sessionProvider.b': '{"providerId":"p2","modelName":"m2"}',
    token: 'keep',
    'astrbot.chat.draft.a': 'keep',
  });
  clearProviderSelectionStorage(storage);
  assert.deepEqual([...storage.map.keys()].sort(), ['astrbot.chat.draft.a', 'token']);
});

test('clearProviderSelectionStorage with a session id only clears that session and the globals', () => {
  const storage = makeStorage({
    selectedProvider: 'p1',
    selectedProviderModel: 'm1',
    'chat.sessionProvider.a': 'x',
    'chat.sessionProvider.b': 'y',
  });
  clearProviderSelectionStorage(storage, 'a');
  assert.deepEqual([...storage.map.keys()], ['chat.sessionProvider.b']);
});
