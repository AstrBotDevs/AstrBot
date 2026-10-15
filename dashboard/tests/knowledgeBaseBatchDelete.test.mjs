import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';
import ts from 'typescript';
import { computed, nextTick, reactive, ref, watch } from 'vue';

function setup(deleteDocuments = async () => ({ data: { status: 'ok' } })) {
  const source = readFileSync(new URL('../src/views/knowledge-base/components/DocumentsTab.vue', import.meta.url), 'utf8');
  const script = source.split('<script setup lang="ts">')[1].split('</script>')[0];
  const ast = ts.createSourceFile('documents.ts', script, ts.ScriptTarget.Latest, true);
  const code = ast.statements.filter(node => !ts.isImportDeclaration(node)).map(node => node.getText(ast)).join('\n');
  const props = reactive({ kbId: 'kb1', kb: {} });
  const calls = [];
  const refreshes = [];
  const notifications = [];
  let listed = [{ doc_id: 'a', doc_name: 'A' }, { doc_id: 'b', doc_name: 'B' }];
  const context = vm.createContext({
    ref, computed, watch, console: { error() {} },
    defineProps: () => props,
    defineEmits: () => (...args) => refreshes.push(args),
    useRouter: () => ({ push() {} }),
    useToast: () => ({ warning: text => notifications.push({ text, color: 'warning' }), success: text => notifications.push({ text, color: 'success' }), error: text => notifications.push({ text, color: 'error' }) }),
    useI18n: () => ({ locale: ref('en-US') }),
    useModuleI18n: () => ({ tm: (key, args) => `${key}:${JSON.stringify(args || {})}` }),
    onMounted() {}, onUnmounted() {},
    window: { setTimeout: () => 1, clearTimeout() {} },
    knowledgeApi: {
      documents: async () => ({ data: { status: 'ok', data: { items: listed, total: listed.length } } }),
      deleteDocument: async (...args) => { calls.push(args); return deleteDocuments(...args); },
      deleteDocuments: async (...args) => { calls.push(args); return deleteDocuments(...args); },
    },
  });
  vm.runInContext(ts.transpile(code, { target: ts.ScriptTarget.ES2020 }), context);
  const state = vm.runInContext('({ documents, selectedDocumentIds, selectableDocuments, loading, batchDeleting, batchDeleteTargets, showBatchDeleteDialog, snackbar, page, total, confirmBatchDelete, deleteSelectedDocuments, loadDocuments, onPageChange, onItemsPerPageChange, searchQuery, deleteTarget, showDeleteDialog, deleteDocument })', context);
  return { state, calls, props, refreshes, notifications, list: items => { listed = items; } };
}

test('confirmation snapshots only selected persisted documents without deleting', () => {
  const { state, calls } = setup();
  state.documents.value = [{ doc_id: 'a', doc_name: 'A' }, { doc_id: 'upload', uploading: true }, { doc_id: 'b', doc_name: 'B' }];
  state.selectedDocumentIds.value = ['a', 'upload', 'hidden'];
  state.confirmBatchDelete();
  assert.deepEqual(Array.from(state.batchDeleteTargets.value, doc => doc.doc_id), ['a']);
  assert.equal(state.showBatchDeleteDialog.value, true);
  assert.equal(state.selectableDocuments.value[1].selectable, false);
  assert.equal(calls.length, 0);
});

for (const networkFailure of [false, true]) {
  test(`failed batch sends one global error and refreshes the actual list (network=${networkFailure})`, async () => {
    const { state, calls, list, refreshes, notifications } = setup(async () => {
      if (networkFailure) throw new Error('Connection lost');
      return { data: { status: 'error', message: 'Deletion did not complete' } };
    });
    state.documents.value = ['a', 'b', 'c'].map(doc_id => ({ doc_id, doc_name: doc_id }));
    state.selectedDocumentIds.value = ['a', 'b', 'c'];
    state.confirmBatchDelete();
    list([]);
    await state.deleteSelectedDocuments();
    assert.deepEqual(JSON.parse(JSON.stringify(calls)), [['kb1', ['a', 'b', 'c']]]);
    assert.equal(state.snackbar.value.show, false);
    assert.equal(notifications.length, 1);
    assert.equal(notifications.at(-1).color, 'error');
    assert.equal(state.batchDeleting.value, false);
    assert.equal(state.documents.value.length, 0);
    assert.equal(refreshes.length, 1);
  });
}

test('one batch request is sent and duplicate submission is ignored', async () => {
  let finish;
  const { state, calls, notifications } = setup(() => new Promise(resolve => { finish = resolve; }));
  state.documents.value = ['a', 'b'].map(doc_id => ({ doc_id, doc_name: doc_id }));
  state.selectedDocumentIds.value = ['a', 'b'];
  state.confirmBatchDelete();
  const work = state.deleteSelectedDocuments();
  await state.deleteSelectedDocuments();
  assert.deepEqual(JSON.parse(JSON.stringify(calls)), [['kb1', ['a', 'b']]]);
  assert.equal(state.selectableDocuments.value[0].selectable, false);
  finish({ data: { status: 'ok' } });
  await work;
  assert.equal(calls.length, 1);
  assert.equal(state.snackbar.value.show, false);
  assert.equal(notifications.at(-1).color, 'success');
  assert.ok(notifications.at(-1).text.includes('documents.batchDeleteSuccess'));
  assert.equal(state.batchDeleting.value, false);
});

test('pagination and search clear selection and reload prunes stale IDs', async () => {
  const { state } = setup();
  state.selectedDocumentIds.value = ['a', 'hidden'];
  await state.loadDocuments();
  assert.deepEqual(Array.from(state.selectedDocumentIds.value), ['a']);
  state.onPageChange(2);
  assert.equal(state.selectedDocumentIds.value.length, 0);
  state.selectedDocumentIds.value = ['a'];
  state.onItemsPerPageChange(25);
  assert.equal(state.selectedDocumentIds.value.length, 0);
  state.selectedDocumentIds.value = ['a'];
  state.searchQuery.value = 'new';
  await nextTick();
  assert.equal(state.selectedDocumentIds.value.length, 0);
});

test('deleting the last page returns to a valid page', async () => {
  const { state, list } = setup();
  state.documents.value = [{ doc_id: 'last', doc_name: 'Last' }];
  state.selectedDocumentIds.value = ['last'];
  state.total.value = 11;
  state.page.value = 2;
  state.confirmBatchDelete();
  list([]);
  await state.deleteSelectedDocuments();
  assert.equal(state.page.value, 1);
});

test('changing knowledge bases clears confirmation and selection', async () => {
  const { state, props } = setup();
  state.documents.value = [{ doc_id: 'a', doc_name: 'A' }];
  state.selectedDocumentIds.value = ['a'];
  state.confirmBatchDelete();
  props.kbId = 'kb2';
  await nextTick();
  assert.equal(state.selectedDocumentIds.value.length, 0);
  assert.equal(state.batchDeleteTargets.value.length, 0);
  assert.equal(state.showBatchDeleteDialog.value, false);
});


test('search debounce cannot select or confirm stale rows', async () => {
  const { state, calls } = setup();
  state.documents.value = [{ doc_id: 'old', doc_name: 'Old' }];
  state.selectedDocumentIds.value = ['old'];
  state.searchQuery.value = 'different';
  await nextTick();
  assert.equal(state.loading.value, true);
  assert.equal(state.documents.value.length, 0);
  state.confirmBatchDelete();
  assert.equal(state.showBatchDeleteDialog.value, false);
  assert.equal(calls.length, 0);
});

for (const outcome of ['ok', 'error', 'network']) {
  test(`single deletion sends global feedback (${outcome})`, async () => {
    const { state, calls, notifications } = setup(async () => {
      if (outcome === 'network') throw new Error('Connection lost');
      return { data: { status: outcome, message: outcome === 'error' ? 'Deletion failed' : undefined } };
    });
    state.deleteTarget.value = { doc_id: 'a' };
    state.showDeleteDialog.value = true;
    await state.deleteDocument();
    assert.deepEqual(JSON.parse(JSON.stringify(calls)), [['kb1', 'a']]);
    assert.equal(notifications.length, 1);
    assert.equal(notifications[0].color, outcome === 'ok' ? 'success' : 'error');
    assert.equal(state.snackbar.value.show, false);
  });
}


for (const single of [false, true]) {
  test(`completed deletion with stale statistics shows one global warning (single=${single})`, async () => {
    const { state, notifications, list, refreshes } = setup(async () => ({
      data: { status: 'ok', data: { deleted_count: 1, stats_refreshed: false, warning: 'stats_refresh_failed' } },
    }));
    state.documents.value = [{ doc_id: 'a', doc_name: 'A' }];
    state.selectedDocumentIds.value = ['a'];
    list([]);
    if (single) {
      state.deleteTarget.value = { doc_id: 'a' };
      state.showDeleteDialog.value = true;
      await state.deleteDocument();
      assert.equal(state.showDeleteDialog.value, false);
    } else {
      state.confirmBatchDelete();
      await state.deleteSelectedDocuments();
      assert.equal(state.showBatchDeleteDialog.value, false);
      assert.equal(state.selectedDocumentIds.value.length, 0);
    }
    assert.deepEqual(notifications, [{ text: 'documents.deleteStatsWarning:{}', color: 'warning' }]);
    assert.equal(state.documents.value.length, 0);
    assert.equal(refreshes.length, 1);
  });
}

test('content failure keeps remaining documents selected for another submission', async () => {
  const { state, notifications } = setup(async () => ({ data: { status: 'error', message: 'Cleanup incomplete' } }));
  state.documents.value = [{ doc_id: 'a', doc_name: 'A' }, { doc_id: 'b', doc_name: 'B' }];
  state.selectedDocumentIds.value = ['a', 'b'];
  state.confirmBatchDelete();
  await state.deleteSelectedDocuments();
  assert.equal(state.showBatchDeleteDialog.value, true);
  assert.deepEqual(Array.from(state.selectedDocumentIds.value), ['a', 'b']);
  assert.equal(state.batchDeleteTargets.value.length, 2);
  assert.equal(notifications.at(-1).color, 'error');
});

test('success notification uses the actual removed count', async () => {
  const { state, notifications } = setup(async () => ({ data: { status: 'ok', data: { deleted_count: 1, stats_refreshed: true } } }));
  state.documents.value = [{ doc_id: 'a', doc_name: 'A' }, { doc_id: 'b', doc_name: 'B' }];
  state.selectedDocumentIds.value = ['a', 'b'];
  state.confirmBatchDelete();
  await state.deleteSelectedDocuments();
  assert.equal(notifications.at(-1).text, 'documents.batchDeleteSuccess:{"count":1}');
});
