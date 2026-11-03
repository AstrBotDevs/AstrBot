import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';
import ts from 'typescript';
import { parse } from 'vue/compiler-sfc';

const source = fs.readFileSync(new URL('../src/components/shared/ObjectEditor.vue', import.meta.url), 'utf8');
const { descriptor } = parse(source);
const ast = ts.createSourceFile('ObjectEditor.js', descriptor.scriptSetup.content, ts.ScriptTarget.Latest, true);
const functions = ast.statements.filter(statement => ts.isFunctionDeclaration(statement)).map(statement => statement.getText(ast)).join('\n');

function editor(modelValue = {}) {
  const scope = {
    props: { modelValue },
    templateSchema: { value: {
      reasoning_effort: { type: 'string', default: 'high' },
      temperature: { type: 'number', default: 0 },
      flag: { type: 'boolean', default: false },
      empty: { type: 'string', default: '' },
    } },
    localKeyValuePairs: { value: [] }, originalKeyValuePairs: { value: [] },
    nextPairId: { value: 0 }, newKey: { value: '' }, newValueType: { value: 'string' },
    dialog: { value: false }, emit: (_event, value) => { scope.saved = JSON.parse(JSON.stringify(value)); },
  };
  vm.createContext(scope);
  vm.runInContext(functions, scope);
  scope.openDialog();
  return scope;
}

// Exercise the actual activation expression used by the checkbox in the SFC.
const activationExpression = descriptor.template.content.match(/@update:model-value="(\$event \? updateTemplateValue[^\"]+)"/)[1];
function toggle(scope, templateKey, enabled) {
  scope.templateKey = templateKey;
  scope.$event = enabled;
  vm.runInContext(activationExpression, scope);
}

test('preview defaults do not activate parameters on confirmation', () => {
  const scope = editor();
  assert.equal(scope.getTemplateValue('reasoning_effort'), 'high');
  assert.equal(scope.isTemplateKeyAdded('reasoning_effort'), false);
  scope.confirmDialog();
  assert.deepEqual(scope.saved, {});
});

test('explicit activation saves high without editing text or enabling other fields', () => {
  const scope = editor({ unrelated: 'keep' });
  toggle(scope, 'reasoning_effort', true);
  scope.confirmDialog();
  assert.deepEqual(scope.saved, { unrelated: 'keep', reasoning_effort: 'high' });
});

test('editing persists and disabling removes only the selected key', () => {
  const scope = editor({ unrelated: 'keep', reasoning_effort: 'medium', temperature: 0.5 });
  scope.updateTemplateValue('reasoning_effort', 'low');
  scope.confirmDialog();
  assert.equal(scope.saved.reasoning_effort, 'low');
  toggle(scope, 'reasoning_effort', false);
  scope.confirmDialog();
  assert.deepEqual(scope.saved, { unrelated: 'keep', temperature: 0.5 });
});

test('cancel does not emit and reopening restores persisted values', () => {
  const scope = editor({ reasoning_effort: 'medium' });
  toggle(scope, 'reasoning_effort', false);
  scope.cancelDialog();
  assert.equal(scope.saved, undefined);
  scope.openDialog();
  assert.equal(scope.isTemplateKeyAdded('reasoning_effort'), true);
  assert.equal(scope.getTemplateValue('reasoning_effort'), 'medium');
});

test('falsy defaults retain their declared types', () => {
  const scope = editor();
  for (const key of ['temperature', 'flag', 'empty']) toggle(scope, key, true);
  scope.confirmDialog();
  assert.deepEqual(scope.saved, { temperature: 0, flag: false, empty: '' });
});

test('reenabling a removed field restores its schema default', () => {
  const scope = editor({ reasoning_effort: 'medium' });
  toggle(scope, 'reasoning_effort', false);
  toggle(scope, 'reasoning_effort', true);
  scope.confirmDialog();
  assert.deepEqual(scope.saved, { reasoning_effort: 'high' });
});

test('all four template input controls are disabled until explicitly activated', () => {
  assert.equal((descriptor.template.content.match(/:disabled="!isTemplateKeyAdded\(templateKey\)"/g) || []).length, 4);
  assert.match(descriptor.template.content, /core\.common\.enabled/);
  assert.match(descriptor.template.content, /core\.common\.disabled/);
});
