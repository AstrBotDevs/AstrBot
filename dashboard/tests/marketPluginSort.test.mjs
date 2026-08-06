import test from 'node:test';
import assert from 'node:assert/strict';

import { sortMarketPluginsByDownloads } from '../src/views/extension/marketPluginSort.mjs';

const plugin = (name, downloadCount) => ({
  name,
  download_count: downloadCount,
});

const names = (plugins) => plugins.map((item) => item.name);

test('sorts downloads in descending order by default', () => {
  const plugins = [plugin('a', 5), plugin('b', 20), plugin('c', 0)];

  assert.deepEqual(names(sortMarketPluginsByDownloads(plugins)), ['b', 'a', 'c']);
  assert.deepEqual(names(sortMarketPluginsByDownloads(plugins, 'desc')), ['b', 'a', 'c']);
});

test('sorts downloads in ascending order', () => {
  const plugins = [plugin('a', 20), plugin('b', 5), plugin('c', 0)];

  assert.deepEqual(names(sortMarketPluginsByDownloads(plugins, 'asc')), ['c', 'b', 'a']);
});

test('treats zero downloads as a valid value instead of unknown', () => {
  const plugins = [plugin('unknown', undefined), plugin('zero', 0), plugin('many', 9)];

  assert.deepEqual(names(sortMarketPluginsByDownloads(plugins, 'desc')), ['many', 'zero', 'unknown']);
  assert.deepEqual(names(sortMarketPluginsByDownloads(plugins, 'asc')), ['zero', 'many', 'unknown']);
});

test('places unknown download counts last in both directions', () => {
  const unknownValues = [undefined, null, '', 'not-a-number', NaN, Infinity, -Infinity];

  for (const value of unknownValues) {
    const plugins = [plugin('unknown', value), plugin('known', 1)];

    assert.deepEqual(
      names(sortMarketPluginsByDownloads(plugins, 'desc')),
      ['known', 'unknown'],
      `desc should place ${String(value)} last`,
    );
    assert.deepEqual(
      names(sortMarketPluginsByDownloads(plugins, 'asc')),
      ['known', 'unknown'],
      `asc should place ${String(value)} last`,
    );
  }
});

test('normalizes negative counts to zero', () => {
  const plugins = [plugin('negative', -3), plugin('zero', 0), plugin('many', 2)];

  assert.deepEqual(names(sortMarketPluginsByDownloads(plugins, 'desc')), ['many', 'negative', 'zero']);
  assert.deepEqual(names(sortMarketPluginsByDownloads(plugins, 'asc')), ['negative', 'zero', 'many']);
});

test('accepts numeric strings and truncates decimals', () => {
  const plugins = [plugin('string', '15'), plugin('decimal', 10.9), plugin('plain', 11)];

  assert.deepEqual(names(sortMarketPluginsByDownloads(plugins, 'desc')), ['string', 'plain', 'decimal']);
  assert.deepEqual(names(sortMarketPluginsByDownloads(plugins, 'asc')), ['decimal', 'plain', 'string']);
});

test('keeps the original order for equal download counts', () => {
  const plugins = [plugin('first', 7), plugin('second', 7), plugin('third', 7), plugin('top', 8)];

  assert.deepEqual(names(sortMarketPluginsByDownloads(plugins, 'desc')), ['top', 'first', 'second', 'third']);
  assert.deepEqual(names(sortMarketPluginsByDownloads(plugins, 'asc')), ['first', 'second', 'third', 'top']);
});

test('keeps the original order among multiple unknown values', () => {
  const plugins = [
    plugin('unknown-a', undefined),
    plugin('known', 3),
    plugin('unknown-b', null),
    plugin('unknown-c', 'nope'),
  ];

  assert.deepEqual(names(sortMarketPluginsByDownloads(plugins, 'desc')), [
    'known',
    'unknown-a',
    'unknown-b',
    'unknown-c',
  ]);
  assert.deepEqual(names(sortMarketPluginsByDownloads(plugins, 'asc')), [
    'known',
    'unknown-a',
    'unknown-b',
    'unknown-c',
  ]);
});

test('does not mutate the input array or plugin objects', () => {
  const plugins = [plugin('a', 1), plugin('b', undefined), plugin('c', 5)];
  const snapshot = plugins.map((item) => ({ ...item }));

  const sorted = sortMarketPluginsByDownloads(plugins, 'desc');

  assert.notEqual(sorted, plugins);
  assert.deepEqual(names(plugins), ['a', 'b', 'c']);
  assert.deepEqual(plugins, snapshot);
});
