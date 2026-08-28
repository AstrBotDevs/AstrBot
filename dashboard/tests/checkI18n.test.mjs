import { after, test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'fs';
import { join } from 'path';
import { tmpdir } from 'os';

import {
  checkI18n,
  inspectI18n,
  keysFromCallArgument,
  localeModuleKey,
  stripComments,
} from '../scripts/check-i18n.mjs';

function makeTmpDir() {
  const directory = mkdtempSync(join(tmpdir(), 'astrbot-i18n-test-'));
  temporaryDirectories.add(directory);
  return directory;
}

const temporaryDirectories = new Set();

after(() => {
  for (const directory of temporaryDirectories) {
    rmSync(directory, { recursive: true, force: true });
  }
});

function writeLocaleTree(root, locale, modulePath, data) {
  const directory = join(root, locale, ...modulePath.split('/').slice(0, -1));
  mkdirSync(directory, { recursive: true });
  writeFileSync(
    join(root, locale, `${modulePath}.json`),
    `${JSON.stringify(data, null, 2)}\n`,
  );
}

function writeFixture({
  zh = { title: '标题', subtitle: '副标题' },
  en = { title: 'Title', subtitle: 'Subtitle' },
  source = `
    const { tm: t } = useModuleI18n('features/stats');
    const label = t('title');
  `,
} = {}) {
  const root = makeTmpDir();
  const srcRoot = join(root, 'src');
  const localesRoot = join(srcRoot, 'i18n', 'locales');
  mkdirSync(join(srcRoot, 'views'), { recursive: true });
  writeLocaleTree(localesRoot, 'zh-CN', 'features/stats', zh);
  writeLocaleTree(localesRoot, 'en-US', 'features/stats', en);
  writeFileSync(join(srcRoot, 'views', 'StatsPage.vue'), source);
  return { srcRoot, localesRoot };
}

test('stripComments ignores translator calls in line comments', () => {
  const source = [
    "const { tm } = useModuleI18n('core.shared');",
    "return null; // PersonaForm uses tm('form.rootFolder')",
    "const label = tm('personaSelector.rootFolder');",
  ].join('\n');

  const stripped = stripComments(source);
  assert.equal(stripped.includes("tm('form.rootFolder')"), false);
  assert.equal(stripped.includes("tm('personaSelector.rootFolder')"), true);
});

test('localeModuleKey remaps tool-use.json onto the runtime tooluse path', () => {
  assert.equal(localeModuleKey('features/tool-use.json'), 'features.tooluse');
  assert.equal(
    localeModuleKey('features/knowledge-base/index.json'),
    'features.knowledge-base.index',
  );
});

test('keysFromCallArgument extracts ternary string literals', () => {
  const extracted = keysFromCallArgument(
    "isEditing.value ? 'form.editTitle' : 'form.title'",
  );
  assert.deepEqual(extracted.keys, ['form.editTitle', 'form.title']);
  assert.equal(extracted.dynamic, false);
});

test('keysFromCallArgument ignores comparison literals in ternary conditions', () => {
  const extracted = keysFromCallArgument(
    "runtime.value === 'local' ? 'onboard.allow' : 'onboard.deny'",
  );
  assert.deepEqual(extracted.keys, ['onboard.allow', 'onboard.deny']);
});

test('inspectI18n reports a source key missing from zh-CN', () => {
  const fixture = writeFixture({
    zh: { title: '标题' },
    en: { title: 'Title', subtitle: 'Subtitle' },
    source: `
      const { tm: t } = useModuleI18n('features/stats');
      const title = t('title');
      const subtitle = t('subtitle');
    `,
  });

  const report = inspectI18n({
    srcRoot: fixture.srcRoot,
    localesRoot: fixture.localesRoot,
    checkTranslationsImports: false,
  });

  assert.equal(report.ok, false);
  assert.ok(
    report.errors.some((error) =>
      error.includes('zh-CN missing catalog key: features.stats.subtitle'),
    ),
  );
  assert.ok(
    report.errors.some((error) =>
      error.includes('zh-CN missing key: features.stats.subtitle'),
    ),
  );
});

test('inspectI18n accepts matching catalogs and module-prefixed keys', () => {
  const fixture = writeFixture();
  const report = inspectI18n({
    srcRoot: fixture.srcRoot,
    localesRoot: fixture.localesRoot,
    checkTranslationsImports: false,
  });
  assert.equal(report.ok, true, report.errors.join('\n'));
});

test('inspectI18n resolves same-file labelKey literals', () => {
  const fixture = writeFixture({
    source: `
      const { tm: t } = useModuleI18n('features/stats');
      const rangeOptions = [
        { labelKey: 'title', value: 1 },
      ];
      const label = t(option.labelKey);
    `,
  });
  const report = inspectI18n({
    srcRoot: fixture.srcRoot,
    localesRoot: fixture.localesRoot,
    checkTranslationsImports: false,
  });
  assert.equal(report.ok, true, report.errors.join('\n'));
});

test('checkI18n passes against the Dashboard source tree', () => {
  const report = checkI18n();
  assert.equal(report.ok, true);
  assert.ok(report.usedCount > 0);
  assert.ok(report.catalogCount > 0);
});
