import test from 'node:test';
import assert from 'node:assert/strict';

import {
  filterCompatibleProviders,
  nonTextModalities,
  supportsRequiredModalities,
} from '../src/utils/modelCapabilities.mjs';

// Fixtures mirror the shape the dashboard API returns: `providerConfigs` from
// /api/v1/providers plus `model_metadata` from catalog discovery. Model IDs
// keep the vendor namespace the catalog publishes.
const IMAGE_CHAT = {
  id: 'orcarouter/vision-chat',
  model: 'deepseek/deepseek-v4-flash-vision-exp',
  modalities: ['text', 'image'],
};
const TEXT_CHAT = {
  id: 'orcarouter/text-chat',
  model: 'orcarouter/free',
  modalities: ['text'],
};
const UNDECLARED_CHAT = {
  id: 'orcarouter/undeclared',
  model: 'orcarouter/mystery',
  modalities: [],
};
const EMBEDDING = {
  id: 'orcarouter/embed',
  model: 'orcarouter/embed-1',
  modalities: ['text'],
};

const METADATA = {
  'deepseek/deepseek-v4-flash-vision-exp': {
    modalities: { input: ['image', 'text'], output: ['text'] },
  },
  'orcarouter/free': { modalities: { input: [], output: [] } },
  'orcarouter/mystery': { modalities: { input: [], output: [] } },
};

const ALL = [IMAGE_CHAT, TEXT_CHAT, UNDECLARED_CHAT, EMBEDDING];

test('nonTextModalities drops text and falsy entries', () => {
  assert.deepEqual(nonTextModalities(['text', 'image', '', null, 'audio']), [
    'image',
    'audio',
  ]);
  assert.deepEqual(nonTextModalities(undefined), []);
});

test('a text-only entry point keeps every configured model', () => {
  assert.deepEqual(
    filterCompatibleProviders(ALL, METADATA, []).map((item) => item.id),
    ALL.map((item) => item.id)
  );
});

test('an image attachment keeps only models declaring image input', () => {
  const kept = filterCompatibleProviders(ALL, METADATA, ['image']).map(
    (item) => item.id
  );

  assert.deepEqual(kept, ['orcarouter/vision-chat']);
  assert.ok(!kept.includes('orcarouter/text-chat'));
  assert.ok(!kept.includes('orcarouter/undeclared'));
});

test('a model that declares nothing fails closed for a non-text modality', () => {
  assert.equal(
    supportsRequiredModalities(UNDECLARED_CHAT, METADATA['orcarouter/mystery'], [
      'image',
    ]),
    false
  );
});

test('an undeclared model still qualifies while only text is sent', () => {
  assert.equal(
    supportsRequiredModalities(UNDECLARED_CHAT, METADATA['orcarouter/mystery'], []),
    true
  );
});

test('catalog metadata wins over a stale configured modality list', () => {
  // The provider entry claims image support, but the live catalog declares this
  // model as text-only, so the catalog is authoritative.
  const stale = {
    id: 'orcarouter/stale',
    model: 'deepseek/deepseek-v4-pro',
    modalities: ['text', 'image'],
  };
  const metadata = {
    'deepseek/deepseek-v4-pro': {
      modalities: { input: ['text'], output: ['text'] },
    },
  };

  assert.equal(supportsRequiredModalities(stale, metadata['deepseek/deepseek-v4-pro'], ['image']), false);
  assert.deepEqual(
    filterCompatibleProviders([stale], metadata, ['image']),
    []
  );
});

test('a configured modality list is used when the catalog says nothing', () => {
  assert.equal(
    supportsRequiredModalities(IMAGE_CHAT, { modalities: { input: [] } }, ['image']),
    true
  );
});

test('audio and video requirements are honoured independently', () => {
  const audioChat = {
    id: 'orcarouter/audio-chat',
    model: 'google/gemini-3.5-flash',
    modalities: ['text', 'audio'],
  };
  const metadata = {
    'google/gemini-3.5-flash': {
      modalities: { input: ['audio', 'image', 'text', 'video'], output: ['text'] },
    },
  };

  assert.deepEqual(
    filterCompatibleProviders([audioChat, TEXT_CHAT], metadata, ['audio']).map(
      (item) => item.id
    ),
    ['orcarouter/audio-chat']
  );
  assert.deepEqual(
    filterCompatibleProviders([audioChat, TEXT_CHAT], metadata, ['video']).map(
      (item) => item.id
    ),
    ['orcarouter/audio-chat']
  );
  assert.deepEqual(
    filterCompatibleProviders([audioChat, TEXT_CHAT], metadata, ['image', 'video']).map(
      (item) => item.id
    ),
    ['orcarouter/audio-chat']
  );
});

test('a non-array provider list yields an empty selection', () => {
  assert.deepEqual(filterCompatibleProviders(null, METADATA, ['image']), []);
  assert.deepEqual(filterCompatibleProviders(undefined, null, ['image']), []);
});
