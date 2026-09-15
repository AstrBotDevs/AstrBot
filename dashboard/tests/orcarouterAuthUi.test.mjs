import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

import { redactSecret } from '../src/utils/secretMask.js';

const HERE = dirname(fileURLToPath(import.meta.url));
const LOCALES = ['en-US', 'zh-CN', 'ja-JP', 'ru-RU'];
const FAKE_KEY = 'sk-orca-test-not-a-real-credential';

// ── Secret masking ─────────────────────────────────────────────────────────

test('redactSecret never returns the full credential', () => {
  const masked = redactSecret(FAKE_KEY);

  assert.notEqual(masked, FAKE_KEY);
  assert.ok(!masked.includes(FAKE_KEY));
  assert.equal(masked, 'sk-orca-…tial');
});

test('redactSecret keeps a recognisable prefix and suffix only', () => {
  const masked = redactSecret(FAKE_KEY);

  assert.ok(masked.startsWith('sk-orca-'));
  assert.ok(masked.includes('…'));
  // Far shorter than the original, so the middle cannot be recovered.
  assert.ok(masked.length < FAKE_KEY.length / 2);
});

test('redactSecret handles short and empty values without leaking them', () => {
  assert.equal(redactSecret('short'), '****');
  assert.equal(redactSecret(''), '');
  assert.equal(redactSecret(undefined), '');
  assert.equal(redactSecret(null), '');
});

test('redactSecret does not echo a non-string value', () => {
  assert.equal(redactSecret(12345678901234), '');
});

// ── Locale parity for the OrcaRouter catalog ───────────────────────────────

function loadLocale(locale) {
  const path = join(HERE, '..', 'src', 'i18n', 'locales', locale, 'features', 'provider.json');
  // ru-RU ships a UTF-8 BOM, so strip it before parsing.
  return JSON.parse(readFileSync(path, 'utf8').replace(/^﻿/, ''));
}

test('every shipped locale carries the OrcaRouter keys', () => {
  const reference = Object.keys(
    loadLocale('en-US').providerSources.orcarouter
  ).sort();

  assert.ok(reference.length > 0);

  for (const locale of LOCALES) {
    const keys = Object.keys(loadLocale(locale).providerSources.orcarouter).sort();
    assert.deepEqual(keys, reference, `${locale} key set diverged from en-US`);
  }
});

test('no OrcaRouter translation is empty in any locale', () => {
  for (const locale of LOCALES) {
    const entry = loadLocale(locale).providerSources.orcarouter;
    for (const [key, value] of Object.entries(entry)) {
      assert.ok(
        typeof value === 'string' && value.trim().length > 0,
        `${locale}.${key} is empty`
      );
    }
  }
});

test('the two authentication methods are labelled distinctly in every locale', () => {
  for (const locale of LOCALES) {
    const entry = loadLocale(locale).providerSources.orcarouter;
    assert.notEqual(
      entry.apiKeyLabel,
      entry.connectLabel,
      `${locale} does not distinguish the API-key and Auth entries`
    );
  }
});

test('the connect success message reports the granted scope', () => {
  for (const locale of LOCALES) {
    const entry = loadLocale(locale).providerSources.orcarouter;
    assert.ok(
      entry.connectSuccess.includes('{scope}'),
      `${locale} connectSuccess does not report the granted scope`
    );
  }
});
