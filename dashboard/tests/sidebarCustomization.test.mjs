import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

// Load the utility without requiring Vite's alias or the Vue icon components.
const source = readFileSync(new URL('../src/utils/sidebarCustomization.js', import.meta.url), 'utf8')
  .replace(/import \{[^}]+\} from [^;]+;/,
    "const MORE_GROUP_KEY = 'core.navigation.groups.more'; const EXTENSION_GROUP_KEY = 'extension';");
const { resolveSidebarItems, applySidebarCustomization, setSidebarCustomization, clearSidebarCustomization } =
  await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
const defaults = [
  { header: 'system' },
  { title: 'welcome', to: '/welcome' },
  { title: 'config', to: '/config' },
  { header: 'extension', collapsible: true, groupToggle: true },
  { title: 'persona', to: '/persona' },
];
const stored = new Map();
globalThis.localStorage = {
  getItem: key => stored.get(key) ?? null,
  setItem: (key, value) => stored.set(key, value),
  removeItem: key => stored.delete(key),
};

test('section headers are excluded from the editor and default layout is preserved', () => {
  const resolved = resolveSidebarItems(defaults, null);
  assert.deepEqual(resolved.mainItems.map(item => item.title), ['welcome', 'config']);
  assert.deepEqual(resolved.moreItems, [defaults[4]]);
  clearSidebarCustomization();
  assert.deepEqual(applySidebarCustomization(defaults), defaults);
});

test('explicit section moves survive reload, and reset restores original membership', () => {
  setSidebarCustomization({ version: 2, mainItems: ['persona', 'welcome'], moreItems: ['config'] });
  const menu = applySidebarCustomization(defaults);
  assert.deepEqual(menu.map(item => item.header || item.title),
    ['system', 'persona', 'welcome', 'extension', 'config']);
  assert.equal(menu[3].groupToggle, true);
  assert.deepEqual(applySidebarCustomization(defaults), menu);
  clearSidebarCustomization();
  assert.deepEqual(applySidebarCustomization(defaults), defaults);
});

test('legacy stale keys and duplicates are removed while new items are saved', () => {
  const config = { mainItems: ['config', null, 'config', 'removed'], moreItems: ['config', 'persona'] };
  const resolved = resolveSidebarItems(defaults, config);
  assert.deepEqual(resolved.normalizedMainKeys, ['config', 'welcome']);
  assert.deepEqual(resolved.normalizedMoreKeys, ['persona']);
  setSidebarCustomization(config);
  applySidebarCustomization(defaults);
  assert.deepEqual(JSON.parse(stored.get('astrbot_sidebar_customization')),
    { version: 2, mainItems: ['config', 'welcome'], moreItems: ['persona'] });
});

test('legacy mixed main lists retain extension membership and merge More into Extensions', () => {
  setSidebarCustomization({ mainItems: ['persona', 'config'], moreItems: ['welcome'] });
  assert.deepEqual(applySidebarCustomization(defaults).map(item => item.header || item.title),
    ['system', 'config', 'extension', 'persona', 'welcome']);
  assert.deepEqual(JSON.parse(stored.get('astrbot_sidebar_customization')),
    { version: 2, mainItems: ['config'], moreItems: ['persona', 'welcome'] });
});

test('reordering system items never moves extension defaults into System', () => {
  setSidebarCustomization({ version: 2, mainItems: ['config', 'welcome'], moreItems: ['persona'] });
  assert.deepEqual(applySidebarCustomization(defaults).map(item => item.header || item.title),
    ['system', 'config', 'welcome', 'extension', 'persona']);
});

test('new extension entries join Extensions while explicit moves stay in System', () => {
  const updated = [...defaults, { title: 'knowledge', to: '/knowledge' }];
  setSidebarCustomization({ version: 2, mainItems: ['welcome', 'persona'], moreItems: ['config'] });
  assert.deepEqual(applySidebarCustomization(updated).map(item => item.header || item.title),
    ['system', 'welcome', 'persona', 'extension', 'config', 'knowledge']);
});

test('legacy More groups remain editable and defaults are never mutated', () => {
  const legacy = [defaults[1], { title: 'core.navigation.groups.more', children: [defaults[2]] }];
  const before = structuredClone(legacy);
  const resolved = resolveSidebarItems(legacy, { version: 2, mainItems: ['config'], moreItems: ['welcome'] },
    { cloneItems: true, assembleMoreGroup: true });
  assert.deepEqual(resolved.merged.map(item => item.title), ['config', 'core.navigation.groups.more']);
  assert.deepEqual(resolved.merged[1].children, [defaults[1]]);
  assert.deepEqual(legacy, before);
});
