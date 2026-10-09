import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';
import ts from 'typescript';

const input = readFileSync(new URL('../src/components/chat/ChatInput.vue', import.meta.url), 'utf8');
const standalone = readFileSync(new URL('../src/components/chat/StandaloneChat.vue', import.meta.url), 'utf8');

test('only onboarding opts into a composer without upload, model, settings or voice controls', () => {
  const guide = readFileSync(new URL('../src/components/OnboardingSetup.vue', import.meta.url), 'utf8');
  const regular = readFileSync(new URL('../src/components/chat/Chat.vue', import.meta.url), 'utf8');
  assert.match(guide, /<StandaloneChat minimal\s*\/>/);
  assert.doesNotMatch(regular, /\bminimal\b/);
  for (const source of [input, standalone]) assert.match(source, /minimal: false/);
  assert.match(standalone, /:minimal="minimal"/);
  assert.match(standalone, /:show-settings="!minimal"/);
  assert.match(standalone, /<ChatSettingsDialog\s+v-if="!minimal"/);
  assert.match(standalone, /v-if="!minimal && isDragging"/);
  assert.match(standalone, /async function handleFilesSelected[^\{]+\{\s*if \(props.minimal\) return;/);
  assert.match(input, /<div v-if="!minimal" class="input-left-actions"/);
  assert.match(input, /<input\s+v-if="!minimal"\s+type="file"/);
  assert.match(input, /<ProviderModelMenu\s+v-if="!minimal && props.showProviderSelector && providerSelectorAvailable"/);
  assert.match(input, /<v-btn\s+v-if="!minimal"\s+@click="handleRecordClick"/);
});

test('minimal composer retains text sending but cannot upload, record or override the model', () => {
  const source = input.split('<script setup lang="ts">')[1].split('</script>')[0];
  const ast = ts.createSourceFile('input.ts', source, ts.ScriptTarget.Latest, true);
  const functions = ast.statements.filter(node => ts.isFunctionDeclaration(node) &&
    ['handlePaste', 'handleKeyDown', 'getCurrentSelection'].includes(node.name.text));
  const events = [];
  const timers = [];
  let prevented = false;
  const props = { minimal: true, showProviderSelector: true, sendShortcut: 'enter', isRecording: false };
  const selection = { providerId: 'other-model' };
  const context = vm.createContext({
    props, File, longPasteThreshold: 10000, emit: (...args) => events.push(args),
    providerSelectorAvailable: { value: true }, providerModelMenuRef: { value: { getCurrentSelection: () => selection } },
    showCommandSuggestion: { value: false }, filteredCommands: { value: [] },
    ctrlKeyDown: { value: false }, ctrlKeyTimer: { value: null }, ctrlKeyLongPressThreshold: 300,
    window: { setTimeout: callback => timers.push(callback) }, isComposingEnter: () => false,
    isComposing: { value: false }, lastCompositionEndAt: { value: null },
    localPrompt: { value: 'Hello' }, canSend: { value: true },
  });
  vm.runInContext(ts.transpile(functions.map(node => node.getText(ast)).join('\n')), context);
  const paste = { clipboardData: { getData: () => 'x'.repeat(10001) }, preventDefault: () => { prevented = true; } };
  context.handlePaste(paste);
  assert.equal(prevented, false, 'Text paste must retain native behavior');
  assert.deepEqual(events, []);
  assert.equal(context.getCurrentSelection(), null);
  context.handleKeyDown({ key: 'b', keyCode: 66, ctrlKey: true, preventDefault: paste.preventDefault });
  assert.equal(timers.length, 0);
  context.handleKeyDown({ key: 'Enter', preventDefault: paste.preventDefault });
  assert.deepEqual(events, [['send']]);

  props.minimal = false;
  events.length = 0;
  assert.equal(context.getCurrentSelection(), selection);
  context.handlePaste(paste);
  assert.equal(events[0][0], 'fileSelect');
  assert.equal(events[0][1][0].size, 10001);
  context.handlePaste({ clipboardData: { getData: () => 'short text' } });
  assert.equal(events[1][0], 'pasteImage');
  context.handleKeyDown({ key: 'b', keyCode: 66, ctrlKey: true, preventDefault: paste.preventDefault });
  assert.equal(timers.length, 1);
  timers[0]();
  assert.equal(events.at(-1)[0], 'startRecording');
});
