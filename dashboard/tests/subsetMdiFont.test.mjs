import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdirSync, writeFileSync, rmSync } from 'fs';
import { join } from 'path';
import { tmpdir } from 'os';

import {
  collectFiles,
  scanUsedIcons,
  parseIconCodepoints,
  resolveUsedIcons,
  extractUtilityCss,
  ICON_CLASS_PATTERN,
  REQUIRED_ICONS,
} from '../scripts/subset-mdi-font.mjs';

// ── Helper: create a temporary directory tree for file-system tests ─────────

function makeTmpDir() {
  const base = join(tmpdir(), `mdi-test-${Date.now()}-${Math.random().toString(36).slice(2)}`);
  mkdirSync(base, { recursive: true });
  return base;
}

// ── collectFiles ────────────────────────────────────────────────────────────

test('collectFiles yields files matching given extensions', () => {
  const tmp = makeTmpDir();
  writeFileSync(join(tmp, 'a.vue'), '');
  writeFileSync(join(tmp, 'b.ts'), '');
  writeFileSync(join(tmp, 'c.txt'), '');

  const files = [...collectFiles(tmp, ['.vue', '.ts'])];
  assert.equal(files.length, 2);
  assert.ok(files.some(f => f.endsWith('a.vue')));
  assert.ok(files.some(f => f.endsWith('b.ts')));

  rmSync(tmp, { recursive: true });
});

test('collectFiles recurses into subdirectories', () => {
  const tmp = makeTmpDir();
  const sub = join(tmp, 'sub');
  mkdirSync(sub);
  writeFileSync(join(sub, 'deep.vue'), '');

  const files = [...collectFiles(tmp, ['.vue'])];
  assert.equal(files.length, 1);
  assert.ok(files[0].endsWith('deep.vue'));

  rmSync(tmp, { recursive: true });
});

test('collectFiles skips node_modules directories', () => {
  const tmp = makeTmpDir();
  const nm = join(tmp, 'node_modules');
  mkdirSync(nm);
  writeFileSync(join(nm, 'pkg.vue'), '');
  writeFileSync(join(tmp, 'app.vue'), '');

  const files = [...collectFiles(tmp, ['.vue'])];
  assert.equal(files.length, 1);
  assert.ok(files[0].endsWith('app.vue'));

  rmSync(tmp, { recursive: true });
});

test('collectFiles yields nothing for empty directory', () => {
  const tmp = makeTmpDir();
  const files = [...collectFiles(tmp, ['.vue'])];
  assert.equal(files.length, 0);

  rmSync(tmp, { recursive: true });
});

// ── scanUsedIcons ───────────────────────────────────────────────────────────

test('scanUsedIcons extracts mdi-* icon names from files', () => {
  const tmp = makeTmpDir();
  writeFileSync(join(tmp, 'A.vue'), '<v-icon>mdi-home</v-icon><v-icon>mdi-close</v-icon>');
  writeFileSync(join(tmp, 'B.vue'), 'icon="mdi-home"');

  const icons = scanUsedIcons(collectFiles(tmp, ['.vue']));
  assert.ok(icons instanceof Set);
  assert.ok(icons.has('mdi-home'));
  assert.ok(icons.has('mdi-close'));
  for (const requiredIcon of REQUIRED_ICONS) {
    assert.ok(icons.has(requiredIcon));
  }
  const expectedIcons = new Set([...REQUIRED_ICONS, 'mdi-home', 'mdi-close']);
  assert.deepEqual(icons, expectedIcons);

  rmSync(tmp, { recursive: true });
});

test('scanUsedIcons excludes utility classes', () => {
  const tmp = makeTmpDir();
  writeFileSync(join(tmp, 'A.vue'), 'mdi-spin mdi-rotate-90 mdi-flip-h mdi-home');

  const icons = scanUsedIcons(collectFiles(tmp, ['.vue']));
  assert.ok(icons.has('mdi-home'));
  assert.ok(!icons.has('mdi-spin'));
  assert.ok(!icons.has('mdi-rotate-90'));
  assert.ok(!icons.has('mdi-flip-h'));

  rmSync(tmp, { recursive: true });
});

test('scanUsedIcons includes all required icons even when no mdi-* icons are found in source', () => {
  const tmp = makeTmpDir();
  writeFileSync(join(tmp, 'A.vue'), '<div>Hello</div>');

  const icons = scanUsedIcons(collectFiles(tmp, ['.vue']));
  for (const requiredIcon of REQUIRED_ICONS) {
    assert.ok(icons.has(requiredIcon));
  }
  assert.equal(icons.size, REQUIRED_ICONS.size);

  rmSync(tmp, { recursive: true });
});

test('scanUsedIcons deduplicates required icons when source already references them', () => {
  const tmp = makeTmpDir();
  const requiredIcon = [...REQUIRED_ICONS][0];
  writeFileSync(join(tmp, 'A.vue'), `<v-icon>${requiredIcon}</v-icon><v-icon>mdi-home</v-icon>`);

  const icons = [...scanUsedIcons(collectFiles(tmp, ['.vue']))];
  assert.equal(icons.filter(icon => icon === requiredIcon).length, 1);
  for (const builtInRequiredIcon of REQUIRED_ICONS) {
    assert.ok(icons.includes(builtInRequiredIcon));
  }
  assert.ok(icons.includes('mdi-home'));

  rmSync(tmp, { recursive: true });
});

// ── parseIconCodepoints ─────────────────────────────────────────────────────

test('parseIconCodepoints parses icon definitions from CSS', () => {
  const css = `
.mdi-home::before { content: "\\F02DC"; }
.mdi-close::before { content: "\\F0156"; }
`;
  const map = parseIconCodepoints(css);
  assert.equal(map.size, 2);
  assert.equal(map.get('mdi-home'), 'F02DC');
  assert.equal(map.get('mdi-close'), 'F0156');
});

test('parseIconCodepoints handles CSS with semicolons inside braces', () => {
  const css = `.mdi-check::before { content: "\\F012C"; }`;
  const map = parseIconCodepoints(css);
  assert.equal(map.get('mdi-check'), 'F012C');
});

test('parseIconCodepoints returns empty map for non-matching CSS', () => {
  const css = `.some-other-class { color: red; }`;
  const map = parseIconCodepoints(css);
  assert.equal(map.size, 0);
});

// ── resolveUsedIcons ────────────────────────────────────────────────────────

test('resolveUsedIcons separates resolved and missing icons', () => {
  const usedIcons = new Set(['mdi-home', 'mdi-close', 'mdi-nonexistent']);
  const iconMap = new Map([
    ['mdi-home', 'F02DC'],
    ['mdi-close', 'F0156'],
  ]);

  const { resolvedIcons, missingIcons, subsetChars } = resolveUsedIcons(usedIcons, iconMap);

  assert.ok(resolvedIcons.includes('mdi-home'));
  assert.ok(resolvedIcons.includes('mdi-close'));
  assert.equal(resolvedIcons.length, 2);

  assert.deepEqual(missingIcons, ['mdi-nonexistent']);

  // Verify subsetChars contains correct Unicode characters
  assert.equal(subsetChars.length, 2);
  assert.equal(subsetChars[0], String.fromCodePoint(0xF02DC));
  assert.equal(subsetChars[1], String.fromCodePoint(0xF0156));
});

test('resolveUsedIcons returns all missing when iconMap is empty', () => {
  const usedIcons = new Set(['mdi-home']);
  const iconMap = new Map();

  const { resolvedIcons, missingIcons, subsetChars } = resolveUsedIcons(usedIcons, iconMap);
  assert.equal(resolvedIcons.length, 0);
  assert.deepEqual(missingIcons, ['mdi-home']);
  assert.equal(subsetChars.length, 0);
});

// ── extractUtilityCss ───────────────────────────────────────────────────────

test('extractUtilityCss removes icon definitions and keeps utility rules', () => {
  const css = `
@font-face {
  font-family: "Material Design Icons";
  src: url("../fonts/materialdesignicons-webfont.woff2") format("woff2");
}

.mdi:before,
.mdi-set {
  display: inline-block;
  font: normal normal normal 24px/1 "Material Design Icons";
}

.mdi-home::before { content: "\\F02DC"; }
.mdi-close::before { content: "\\F0156"; }

.mdi-spin:before {
  animation: mdi-spin 2s infinite linear;
}

.mdi-18px.mdi-set, .mdi-18px.mdi:before {
  font-size: 18px;
}
/*# sourceMappingURL=materialdesignicons.css.map */
`;

  const result = extractUtilityCss(css, ICON_CLASS_PATTERN);

  // Should NOT contain icon definitions
  assert.ok(!result.includes('mdi-home'));
  assert.ok(!result.includes('mdi-close'));

  // Should NOT contain @font-face
  assert.ok(!result.includes('@font-face'));

  // Should NOT contain base .mdi rules
  assert.ok(!result.includes('display: inline-block'));

  // Should NOT contain source map
  assert.ok(!result.includes('sourceMappingURL'));

  // SHOULD contain utility classes
  assert.ok(result.includes('mdi-spin'));
  assert.ok(result.includes('mdi-18px'));
});

test('extractUtilityCss returns empty string when only icon defs exist', () => {
  const css = `
@font-face { font-family: "MDI"; src: url("font.woff2"); }
.mdi:before, .mdi-set { display: inline-block; }
.mdi-home::before { content: "\\F02DC"; }
`;

  const result = extractUtilityCss(css, ICON_CLASS_PATTERN);
  assert.equal(result, '');
});

test('extractUtilityCss handles empty CSS input', () => {
  const result = extractUtilityCss('', ICON_CLASS_PATTERN);
  assert.equal(result, '');
});

// ── ICON_CLASS_PATTERN ──────────────────────────────────────────────────────

test('ICON_CLASS_PATTERN matches standard MDI icon definitions', () => {
  const css = `.mdi-home::before { content: "\\F02DC"; }`;
  const matches = [...css.matchAll(ICON_CLASS_PATTERN)];
  assert.equal(matches.length, 1);
  assert.equal(matches[0][1], 'mdi-home');
  assert.equal(matches[0][2], 'F02DC');
});

test('ICON_CLASS_PATTERN does not match non-icon classes', () => {
  const css = `.some-class::before { content: "hello"; }`;
  const matches = [...css.matchAll(ICON_CLASS_PATTERN)];
  assert.equal(matches.length, 0);
});
