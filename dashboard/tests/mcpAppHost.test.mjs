import assert from 'node:assert/strict';
import test from 'node:test';
import { appDocument, createAppHost } from '../src/utils/mcpAppHost.mjs';

function fixture() {
  const source = {};
  const sent = [], proposed = [], sizes = [];
  const host = createAppHost({ source: () => source, send: d => sent.push(d), arguments: { choices: [1, 2] }, result: { content: [], structuredContent: { ids: [1, 2] } }, propose: t => proposed.push(t), resize: h => sizes.push(h) });
  const request = (method, params = {}, id) => host.receive({ source, origin: 'null', data: { jsonrpc: '2.0', method, params, ...(id !== undefined ? { id } : {}) } });
  const init = () => { request('ui/initialize', { protocolVersion: '2026-01-26', appInfo: { name: 'Picker', version: '1' } }, 1); request('ui/notifications/initialized'); };
  return { host, source, sent, proposed, sizes, request, init };
}

test('initializes once and sends input before structured result', () => {
  const f = fixture(); f.init();
  assert.equal(f.sent[0].result.protocolVersion, '2026-01-26');
  assert.deepEqual(f.sent.slice(1).map(x => x.method), ['ui/notifications/tool-input', 'ui/notifications/tool-result']);
  assert.deepEqual(f.sent[2].params.structuredContent.ids, [1, 2]);
  f.request('ui/notifications/initialized'); assert.equal(f.sent.length, 3);
});
test('accepts text only after explicit host review, supports decline and reuse', () => {
  const f = fixture(); f.init();
  f.request('ui/message', { role: 'user', content: [{ type: 'text', text: 'Choose 2' }] }, 2);
  assert.deepEqual(f.proposed, ['Choose 2']); assert.equal(f.sent.length, 3);
  f.host.settle(false); assert.ok(f.sent.at(-1).error);
  f.request('ui/message', { role: 'user', content: [{ type: 'text', text: 'Choose 1' }] }, 3);
  f.host.settle(true); assert.deepEqual(f.sent.at(-1), { jsonrpc: '2.0', id: 3, result: {} });
});
test('ignores sibling windows and rejects unsupported operations', () => {
  const f = fixture(); f.init();
  f.host.receive({ source: {}, origin: 'null', data: { jsonrpc: '2.0', id: 2, method: 'ui/message' } });
  f.host.receive({ source: f.source, origin: 'https://other.invalid', data: { jsonrpc: '2.0', id: 2, method: 'ui/message' } });
  assert.equal(f.sent.length, 3);
  for (const method of ['tools/call', 'resources/read', 'ui/open-link', 'ui/update-model-context']) {
    f.request(method, {}, 5); assert.equal(f.sent.at(-1).error.code, -32601);
  }
});
test('rejects messages before init, non-text, oversized text and overlapping requests', () => {
  const f = fixture(); f.request('ui/message', {}, 2); assert.ok(f.sent.at(-1).error); f.init();
  for (const params of [{role: 'assistant', content: []}, {role: 'user', content: [{type: 'image'}]}, {role: 'user', content: [{type: 'text', text: 'x'.repeat(10001)}]}]) {
    f.request('ui/message', params, 2); assert.ok(f.sent.at(-1).error);
  }
  const params = {role: 'user', content: [{type: 'text', text: 'hello'}]};
  f.request('ui/message', params, 3); f.request('ui/message', params, 4);
  assert.equal(f.proposed.length, 1); assert.ok(f.sent.at(-1).error);
});
test('bounds resize and puts restrictive CSP before any supplied markup', () => {
  const f = fixture(); f.init(); f.request('ui/notifications/size-changed', {height: 1e9});
  assert.deepEqual(f.sizes, [800]);
  const html = appDocument('<script>test()</script>');
  assert.ok(html.startsWith('<meta http-equiv="Content-Security-Policy"'));
  assert.ok(html.includes("connect-src 'none'"));
});
