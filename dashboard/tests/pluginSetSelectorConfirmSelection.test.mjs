import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';
import ts from 'typescript';
import { parse } from 'vue/compiler-sfc';

const source = fs.readFileSync(
  new URL('../src/components/shared/PluginSetSelector.vue', import.meta.url),
  'utf8',
);
const { descriptor } = parse(source);
const ast = ts.createSourceFile(
  'PluginSetSelector.js', descriptor.scriptSetup.content, ts.ScriptTarget.Latest, true,
);
const confirmSelection = ast.statements
  .filter(statement => ts.isFunctionDeclaration(statement)
    && statement.name?.text === 'confirmSelection')
  .map(statement => statement.getText(ast)).join('\n');

// The dialog hides reserved plugins, so the selectable list is this subset.
const VISIBLE_PLUGINS = ['astrbot_plugin_alpha', 'astrbot_plugin_beta'];

/**
 * Runs the component's confirmSelection with the given dialog state.
 *
 * @param {{mode: string, selected?: string[], plugins?: string[]}} state Dialog state.
 * @returns {string[]} The value emitted through update:modelValue.
 */
function confirm({ mode, selected = [], plugins = VISIBLE_PLUGINS }) {
  let emitted;
  const scope = {
    selectionMode: { value: mode },
    selectedPlugins: { value: selected },
    pluginList: { value: plugins.map(name => ({ name })) },
    dialog: { value: true },
    emit: (event, value) => {
      assert.equal(event, 'update:modelValue');
      emitted = value;
    },
  };
  vm.createContext(scope);
  vm.runInContext(confirmSelection, scope);
  scope.confirmSelection();
  assert.equal(scope.dialog.value, false, 'dialog should close after confirming');
  // Copy into this realm so deep comparisons do not trip over prototypes.
  return Array.from(emitted ?? []);
}

test('keeps the wildcard when custom selection covers every listed plugin', () => {
  assert.deepEqual(confirm({ mode: 'custom', selected: [...VISIBLE_PLUGINS] }), ['*']);
});

test('keeps a subset of plugins as an explicit list', () => {
  assert.deepEqual(
    confirm({ mode: 'custom', selected: [VISIBLE_PLUGINS[0]] }),
    [VISIBLE_PLUGINS[0]],
  );
});

test('preserves an empty custom selection instead of enabling everything', () => {
  assert.deepEqual(confirm({ mode: 'custom', selected: [], plugins: [] }), []);
});

test('emits the wildcard for the all mode and an empty list for the none mode', () => {
  assert.deepEqual(confirm({ mode: 'all' }), ['*']);
  assert.deepEqual(confirm({ mode: 'none' }), []);
});
