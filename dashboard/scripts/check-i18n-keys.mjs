#!/usr/bin/env node
/**
 * i18n key checker for the AstrBot dashboard.
 *
 * Verifies that every statically-resolvable translation key used in dashboard/src
 * actually exists in all four locale bundles.
 *
 * Why this exists: the i18n helper returns the string "[MISSING: <key>]" when a
 * key is absent, which is truthy, so `t(key) || 'fallback'` never falls back and
 * the placeholder leaks into the UI. A key that is absent from *all* locales is
 * invisible to locale-vs-locale comparison (src/i18n/validator.ts), because all
 * bundles agree on the missing key. This script compares source usage against
 * the bundles, which is the only way to catch that class of defect.
 *
 * Usage:
 *   node scripts/check-i18n-keys.mjs            # exit 1 on any problem
 *   node scripts/check-i18n-keys.mjs --verbose  # also list dynamic keys
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DASHBOARD = path.resolve(__dirname, '..');
const SRC = path.join(DASHBOARD, 'src');
const LOCALES = path.join(SRC, 'i18n', 'locales');

const LANGS = ['zh-CN', 'en-US', 'ru-RU', 'ja-JP'];
const BASE = 'zh-CN';
const VERBOSE = process.argv.includes('--verbose');

/**
 * Assemble a locale tree the same way the runtime does, by structurally parsing
 * <lang>/index.ts. The bundle filename is NOT the runtime namespace
 * (features/tool-use.json -> features.tooluse), so the mapping must come from
 * index.ts rather than from the file path.
 */
function buildTree(lang) {
  const dir = path.join(LOCALES, lang);
  const idx = fs.readFileSync(path.join(dir, 'index.ts'), 'utf8');

  const varToFile = new Map();
  for (const m of idx.matchAll(/^import\s+(\w+)\s+from\s+'(\.\/[^']+)';/gm)) {
    varToFile.set(m[1], m[2]);
  }
  if (varToFile.size === 0) throw new Error(`no imports parsed from ${lang}/index.ts`);

  const body = idx.slice(idx.indexOf('{', idx.indexOf('export default')));
  let i = 0;

  const parseObj = () => {
    const out = {};
    i++; // consume '{'
    for (;;) {
      while (i < body.length && /[\s,]/.test(body[i])) i++;
      if (i >= body.length) throw new Error(`unterminated object in ${lang}/index.ts`);
      if (body[i] === '}') { i++; break; }

      let key;
      if (body[i] === "'") {
        const end = body.indexOf("'", i + 1);
        key = body.slice(i + 1, end);
        i = end + 1;
      } else {
        const m = /^[A-Za-z0-9_$]+/.exec(body.slice(i));
        if (!m) throw new Error(`bad key at offset ${i} in ${lang}/index.ts`);
        key = m[0];
        i += m[0].length;
      }
      while (i < body.length && /\s/.test(body[i])) i++;
      i++; // consume ':'
      while (i < body.length && /\s/.test(body[i])) i++;

      if (body[i] === '{') {
        out[key] = parseObj();
      } else {
        const m = /^[A-Za-z0-9_$]+/.exec(body.slice(i));
        if (!m) throw new Error(`bad value at offset ${i} in ${lang}/index.ts`);
        i += m[0].length;
        const rel = varToFile.get(m[0]);
        if (!rel) throw new Error(`unresolved reference ${m[0]} in ${lang}/index.ts`);
        // ~29/37 ru-RU bundles carry a UTF-8 BOM, which JSON.parse rejects.
        const raw = fs.readFileSync(path.join(dir, rel), 'utf8').replace(/^\uFEFF/, '');
        out[key] = JSON.parse(raw);
      }
    }
    return out;
  };

  return parseObj();
}

/** Flat list of leaf key paths, e.g. "core.common.cancel". */
function leafKeys(obj, prefix = '') {
  const out = [];
  for (const [k, v] of Object.entries(obj)) {
    const full = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === 'object' && !Array.isArray(v)) out.push(...leafKeys(v, full));
    else out.push(full);
  }
  return out;
}

/** Build a Set of every resolvable key path, including intermediate object nodes. */
function keySet(obj, prefix = '') {
  const out = new Set();
  for (const [k, v] of Object.entries(obj)) {
    const full = prefix ? `${prefix}.${k}` : k;
    out.add(full);
    if (v && typeof v === 'object' && !Array.isArray(v)) {
      for (const nested of keySet(v, full)) out.add(nested);
    }
  }
  return out;
}

function walk(dir, out = []) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) walk(p, out);
    else if (/\.(vue|ts|js|jsx|tsx)$/.test(e.name) && !/\.d\.ts$/.test(e.name)) out.push(p);
  }
  return out;
}

/**
 * Blank out comments while preserving byte offsets and newlines, so reported
 * line numbers stay accurate. Commented-out t('...') calls are common here.
 */
function stripComments(src) {
  let out = '';
  let i = 0;
  let mode = null; // null | 'line' | 'block' | 'html'
  while (i < src.length) {
    const c = src[i];
    const n = src[i + 1];
    if (mode === null) {
      if (c === '/' && n === '/') { mode = 'line'; out += '  '; i += 2; continue; }
      if (c === '/' && n === '*') { mode = 'block'; out += '  '; i += 2; continue; }
      if (c === '<' && src.startsWith('<!--', i)) { mode = 'html'; out += '    '; i += 4; continue; }
      out += c; i++; continue;
    }
    if (mode === 'line') {
      if (c === '\n') { mode = null; out += c; } else out += ' ';
      i++; continue;
    }
    if (mode === 'block') {
      if (c === '*' && n === '/') { mode = null; out += '  '; i += 2; continue; }
      out += c === '\n' ? '\n' : ' ';
      i++; continue;
    }
    if (mode === 'html') {
      if (src.startsWith('-->', i)) { mode = null; out += '   '; i += 3; continue; }
      out += c === '\n' ? '\n' : ' ';
      i++; continue;
    }
  }
  return out;
}

/** Collect literal translator calls plus the dynamic ones we deliberately skip. */
function collectUsages(file, raw) {
  const src = stripComments(raw);
  const rel = path.relative(DASHBOARD, file).replace(/\\/g, '/');

  // Plugin-provided strings come from plugin metadata, not these bundles.
  if (/usePluginI18n/.test(src)) return { usages: [], dynamic: 0, skipped: true };

  // Binding forms seen in this codebase:
  //   const { tm: t }        = useModuleI18n('features/stats')   -> t is module-relative
  //   const { tm }           = useModuleI18n('...')              -> tm is module-relative
  //   const { locale, t: globalT } = useI18n()                   -> globalT is full-path
  //   const { t }            = useI18n()                         -> t is full-path
  // Note "useModuleI18n(" contains "useI18n(" as a substring, hence the lookbehind.
  const moduleAliases = new Map(); // local name -> module namespace
  const fullAliases = new Set();   // local names that take a full key path

  for (const m of src.matchAll(/const\s*\{([^}]*)\}\s*=\s*useModuleI18n\(\s*['"]([^'"]+)['"]\s*\)/g)) {
    const ns = m[2].replace(/\//g, '.');
    for (const part of m[1].split(',')) {
      const [orig, alias] = part.split(':').map((s) => s.trim());
      const local = alias || orig;
      if (orig === 't' || orig === 'tm') moduleAliases.set(local, ns);
    }
  }
  for (const m of src.matchAll(/const\s*\{([^}]*)\}\s*=\s*(?<![\w$])useI18n\s*\(/g)) {
    for (const part of m[1].split(',')) {
      const [orig, alias] = part.split(':').map((s) => s.trim());
      const local = alias || orig;
      // useI18n() only exposes the full-path t; tm() is not offered there.
      if (orig === 't') fullAliases.add(local);
    }
  }
  if (/\bthis\.t\s*\(/.test(src)) fullAliases.add('t');

  const usages = [];
  const lineOf = (offset) => src.slice(0, offset).split('\n').length;
  const callRe = /\b(t|tm)\s*\(\s*(['"`])/g;

  let dynamic = 0;
  for (const m of src.matchAll(callRe)) {
    const [, fn, quote] = m;
    const moduleNs = moduleAliases.get(fn);
    const isModule = moduleNs !== undefined;
    const isFull = fullAliases.has(fn);
    if (!isModule && !isFull) continue;

    const start = m.index + m[0].length;
    const end = src.indexOf(quote, start);
    if (end === -1) continue;
    const literal = src.slice(start, end);

    // Template literal with interpolation, or a concatenated key: not statically resolvable.
    if (quote === '`' && literal.includes('${')) { dynamic++; continue; }
    if (!literal || /[\\\n]/.test(literal)) continue;

    // A name bound from useModuleI18n() always resolves relative to that module.
    usages.push({ key: literal, module: isModule ? moduleNs : null, line: lineOf(m.index), fn });
  }
  return { usages, dynamic, skipped: false };
}

// ---------------------------------------------------------------- run

const trees = {};
const sets = {};
const leaves = {};
for (const lang of LANGS) {
  trees[lang] = buildTree(lang);
  sets[lang] = keySet(trees[lang]);
  leaves[lang] = leafKeys(trees[lang]);
}

const baselineKeys = new Set(leaves[BASE]);

// (A) code -> bundle: a key used in source but absent from some/all locales.
const codeProblems = new Map(); // key -> { langs:Set, sites:[] }
let dynamicCount = 0;
let scanned = 0;
let skippedFiles = 0;

for (const file of walk(SRC)) {
  const raw = fs.readFileSync(file, 'utf8');
  const { usages, dynamic, skipped } = collectUsages(file, raw);
  if (skipped) { skippedFiles++; continue; }
  if (usages.length) scanned++;

  for (const u of usages) {
    const full = u.module ? `${u.module}.${u.key}` : u.key;
    for (const lang of LANGS) {
      if (sets[lang].has(full)) continue;
      if (!codeProblems.has(full)) codeProblems.set(full, { langs: new Set(), sites: [] });
      const rec = codeProblems.get(full);
      rec.langs.add(lang);
      rec.sites.push(`${path.relative(DASHBOARD, file).replace(/\\/g, '/')}:${u.line}  ${u.fn}('${u.key}')`);
    }
  }
  dynamicCount += dynamic;
}

// (B) bundle -> bundle: keys present in some locales but missing from others.
const drift = [];
for (const lang of LANGS) {
  if (lang === BASE) continue;
  const missing = [...baselineKeys].filter((k) => !sets[lang].has(k));
  if (missing.length) drift.push({ lang, missing });
}

// ---------------------------------------------------------------- report

console.log('i18n key check');
console.log(`  locales:  ${LANGS.join(', ')}  (baseline: ${BASE})`);
console.log(`  leaf keys: ${LANGS.map((l) => `${l}=${leaves[l].length}`).join('  ')}`);
console.log(`  scanned:  ${scanned} files with translator calls, ${dynamicCount} dynamic keys skipped, ${skippedFiles} plugin-i18n file(s) skipped`);

let failed = false;

console.log('\n[A] keys used in source but missing from a bundle');
if (codeProblems.size === 0) {
  console.log('  OK - every statically-resolvable key resolves in all four locales');
} else {
  failed = true;
  for (const [key, rec] of [...codeProblems].sort()) {
    const absent = LANGS.filter((l) => rec.langs.has(l));
    const severity = absent.length === LANGS.length ? 'ALL LOCALES' : absent.join(',');
    console.log(`  MISSING in ${severity}: ${key}`);
    for (const s of [...new Set(rec.sites)]) console.log(`      ${s}`);
  }
  console.log(`  ${codeProblems.size} key(s) affected`);
}

console.log('\n[B] locale drift (present in baseline, absent elsewhere)');
if (drift.length === 0) {
  console.log('  OK - all locales cover the baseline key set');
} else {
  for (const { lang, missing } of drift) {
    console.log(`  ${lang}: ${missing.length} keys missing`);
    for (const k of missing.slice(0, VERBOSE ? missing.length : 10)) console.log(`      ${k}`);
    if (!VERBOSE && missing.length > 10) console.log(`      ... and ${missing.length - 10} more (use --verbose)`);
  }
}

if (failed) {
  console.log('\nFAILED: add the missing keys to every locale bundle.');
  process.exit(1);
}
console.log('\nPASS');
