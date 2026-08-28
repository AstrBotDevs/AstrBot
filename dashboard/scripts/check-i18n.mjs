import { readdirSync, readFileSync } from 'node:fs';
import { join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const LOCALES = ['zh-CN', 'en-US'];
const SOURCE_EXTENSIONS = new Set(['.ts', '.vue']);
const TRANSLATOR_SOURCES = new Set(['t', 'tm', 'getRaw']);
const DASHBOARD_ROOT = resolve(fileURLToPath(new URL('..', import.meta.url)));
const LOCALE_FILE_KEY_OVERRIDES = {
  'features/tool-use': 'features.tooluse',
};

export function walkFiles(directory, predicate) {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const entryPath = join(directory, entry.name);
    if (entry.isDirectory()) return walkFiles(entryPath, predicate);
    return predicate(entryPath) ? [entryPath] : [];
  });
}

export function stripComments(source) {
  let output = '';
  let index = 0;

  while (index < source.length) {
    if (source.startsWith('<!--', index)) {
      const end = source.indexOf('-->', index + 4);
      index = end === -1 ? source.length : end + 3;
      continue;
    }
    if (source.startsWith('/*', index)) {
      const end = source.indexOf('*/', index + 2);
      index = end === -1 ? source.length : end + 2;
      continue;
    }
    if (source.startsWith('//', index)) {
      const end = source.indexOf('\n', index);
      index = end === -1 ? source.length : end;
      continue;
    }

    const quote = source[index];
    if (quote === '"' || quote === "'" || quote === '`') {
      output += quote;
      index += 1;
      while (index < source.length) {
        const character = source[index];
        output += character;
        index += 1;
        if (character === '\\') {
          if (index < source.length) {
            output += source[index];
            index += 1;
          }
          continue;
        }
        if (character === quote) break;
      }
      continue;
    }

    output += source[index];
    index += 1;
  }

  return output;
}

export function localeModuleKey(relativePath) {
  const withoutExtension = relativePath
    .replace(/\.json$/, '')
    .replaceAll('\\', '/');
  return (
    LOCALE_FILE_KEY_OVERRIDES[withoutExtension] ??
    withoutExtension.replaceAll('/', '.')
  );
}

function recordValue(prefix, value, leaves, nodes) {
  if (prefix) nodes.add(prefix);
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    for (const [key, child] of Object.entries(value)) {
      recordValue(prefix ? `${prefix}.${key}` : key, child, leaves, nodes);
    }
    return;
  }
  if (prefix) leaves.set(prefix, value);
}

export function catalogFromLocaleDir(localeDir) {
  const leaves = new Map();
  const nodes = new Set();
  const files = [];

  for (const filePath of walkFiles(localeDir, (path) =>
    path.endsWith('.json'),
  )) {
    const relativePath = relative(localeDir, filePath).replaceAll('\\', '/');
    files.push(relativePath);
    const moduleKey = localeModuleKey(relativePath);
    const data = JSON.parse(readFileSync(filePath, 'utf8'));
    recordValue(moduleKey, data, leaves, nodes);
  }

  return { leaves, nodes, files };
}

function extractFirstArg(source, start) {
  let index = start;
  let paren = 0;
  let brace = 0;
  let bracket = 0;
  let quote = null;
  let escaped = false;

  while (index < source.length) {
    const character = source[index];
    if (quote) {
      if (escaped) {
        escaped = false;
      } else if (character === '\\') {
        escaped = true;
      } else if (character === quote) {
        quote = null;
      }
      index += 1;
      continue;
    }
    if (character === '"' || character === "'" || character === '`') {
      quote = character;
      index += 1;
      continue;
    }
    if (character === '(') paren += 1;
    else if (character === ')') {
      if (paren === 0 && brace === 0 && bracket === 0) {
        return { arg: source.slice(start, index).trim(), end: index };
      }
      paren -= 1;
    } else if (character === '{') brace += 1;
    else if (character === '}') brace -= 1;
    else if (character === '[') bracket += 1;
    else if (character === ']') bracket -= 1;
    else if (character === ',' && paren === 0 && brace === 0 && bracket === 0) {
      return { arg: source.slice(start, index).trim(), end: index };
    }
    index += 1;
  }

  return { arg: source.slice(start).trim(), end: source.length };
}

export function keysFromCallArgument(arg) {
  const trimmed = arg.trim();
  const quoted = trimmed.match(/^(['"`])([\s\S]*)\1$/);
  if (quoted) {
    if (quoted[1] === '`' && quoted[2].includes('${')) {
      return { keys: [], dynamic: true };
    }
    return { keys: [quoted[2]], dynamic: false };
  }

  const withoutComparisons = trimmed
    .replace(/[!=]==?\s*(['"])[^'"]*\1/g, '')
    .replace(/(['"])[^'"]*\1\s*[!=]==?/g, '');
  const keys = [];
  const literalPattern = /(['"])([a-zA-Z][\w.-]*)\1/g;
  for (const match of withoutComparisons.matchAll(literalPattern)) {
    keys.push(match[2]);
  }
  return { keys, dynamic: keys.length === 0 };
}

function parseBindings(source) {
  const bindings = new Map();
  const pattern =
    /(?:const|let|var)\s*\{([^}]+)\}\s*=\s*(use(?:Module)?I18n)\(\s*(?:(['"])([^'"]*)\3\s*)?\)/g;

  for (const match of source.matchAll(pattern)) {
    const callee = match[2];
    const moduleName = match[4];
    let kind = 'global';
    let modulePrefix = '';
    if (callee === 'useModuleI18n') {
      if (!moduleName) continue;
      kind = 'module';
      modulePrefix = moduleName.replaceAll('/', '.');
    }

    for (const raw of match[1].split(',')) {
      const part = raw.trim();
      if (!part || part.startsWith('...')) continue;
      const [left, right] = part.split(':').map((item) => item.trim());
      const sourceName = left.replace(/\s*=.*$/, '');
      const localName = (right || left).replace(/\s*=.*$/, '');
      if (!TRANSLATOR_SOURCES.has(sourceName)) continue;
      if (kind === 'global' && sourceName !== 't') continue;
      bindings.set(localName, {
        kind,
        modulePrefix,
        sourceName,
      });
    }
  }

  return bindings;
}

function resolveKey(binding, rawKey) {
  if (binding.kind === 'module') return `${binding.modulePrefix}.${rawKey}`;
  return rawKey;
}

function collectPropertyLiterals(source, propertyName) {
  const pattern = new RegExp(
    `\\b${propertyName}\\s*:\\s*(['"])([^'"\\n]+)\\1`,
    'g',
  );
  return [...source.matchAll(pattern)].map((match) => match[2]);
}

function collectUsedKeysFromSource(source, file) {
  const stripped = stripComments(source);
  const bindings = parseBindings(stripped);
  if (bindings.size === 0) return [];

  const used = [];
  for (const [localName, binding] of bindings) {
    const callPattern = new RegExp(`\\b${localName}\\s*\\(`, 'g');
    for (const match of stripped.matchAll(callPattern)) {
      const { arg } = extractFirstArg(stripped, match.index + match[0].length);
      const extracted = keysFromCallArgument(arg);
      for (const rawKey of extracted.keys) {
        used.push({
          file,
          key: resolveKey(binding, rawKey),
          sourceName: binding.sourceName,
        });
      }
      if (extracted.dynamic) {
        const property = arg.match(/\.([A-Za-z_][\w]*)\s*$/);
        if (property?.[1].endsWith('Key')) {
          for (const rawKey of collectPropertyLiterals(stripped, property[1])) {
            used.push({
              file,
              key: resolveKey(binding, rawKey),
              sourceName: binding.sourceName,
            });
          }
        }
      }
    }
  }

  return used;
}

export function collectUsedKeys(srcRoot) {
  const files = walkFiles(srcRoot, (filePath) => {
    const relativePath = relative(srcRoot, filePath).replaceAll('\\', '/');
    if (relativePath.startsWith('i18n/')) return false;
    if (relativePath.startsWith('api/generated/')) return false;
    const extension = filePath.slice(filePath.lastIndexOf('.'));
    return SOURCE_EXTENSIONS.has(extension);
  });

  return files.flatMap((filePath) => {
    const file = relative(srcRoot, filePath).replaceAll('\\', '/');
    return collectUsedKeysFromSource(readFileSync(filePath, 'utf8'), file);
  });
}

function missingCatalogValue(leaves, nodes, usage) {
  if (usage.sourceName === 'getRaw') {
    if (leaves.has(usage.key) || nodes.has(usage.key)) return null;
    return 'missing';
  }
  if (!leaves.has(usage.key)) {
    if (nodes.has(usage.key)) return 'invalid';
    return 'missing';
  }
  const value = leaves.get(usage.key);
  if (typeof value !== 'string') return 'invalid';
  if (!value.trim()) return 'empty';
  return null;
}

function formatUsage(usage) {
  return `${usage.key} (${usage.file})`;
}

export function inspectI18n(options = {}) {
  const dashboardRoot = options.dashboardRoot ?? DASHBOARD_ROOT;
  const srcRoot = options.srcRoot ?? join(dashboardRoot, 'src');
  const localesRoot = options.localesRoot ?? join(srcRoot, 'i18n', 'locales');
  const translationsPath =
    options.translationsPath ?? join(srcRoot, 'i18n', 'translations.ts');
  const checkTranslationsImports = options.checkTranslationsImports ?? true;

  const catalogs = Object.fromEntries(
    LOCALES.map((locale) => [
      locale,
      catalogFromLocaleDir(join(localesRoot, locale)),
    ]),
  );
  const used = collectUsedKeys(srcRoot);
  const errors = [];

  const fileSets = LOCALES.map((locale) => new Set(catalogs[locale].files));
  for (const file of fileSets[0]) {
    if (!fileSets[1].has(file)) {
      errors.push(`locale file missing from en-US: ${file}`);
    }
  }
  for (const file of fileSets[1]) {
    if (!fileSets[0].has(file)) {
      errors.push(`locale file missing from zh-CN: ${file}`);
    }
  }

  const zhLeaves = catalogs['zh-CN'].leaves;
  const enLeaves = catalogs['en-US'].leaves;
  for (const key of zhLeaves.keys()) {
    if (!enLeaves.has(key)) errors.push(`en-US missing catalog key: ${key}`);
  }
  for (const key of enLeaves.keys()) {
    if (!zhLeaves.has(key)) errors.push(`zh-CN missing catalog key: ${key}`);
  }

  for (const locale of LOCALES) {
    const catalog = catalogs[locale];
    const seen = new Set();
    for (const usage of used) {
      const stamp = `${locale}:${usage.file}:${usage.key}:${usage.sourceName}`;
      if (seen.has(stamp)) continue;
      seen.add(stamp);
      const problem = missingCatalogValue(catalog.leaves, catalog.nodes, usage);
      if (problem === 'missing') {
        errors.push(`${locale} missing key: ${formatUsage(usage)}`);
      } else if (problem === 'invalid') {
        errors.push(`${locale} non-string key: ${formatUsage(usage)}`);
      } else if (problem === 'empty') {
        errors.push(`${locale} empty key: ${formatUsage(usage)}`);
      }
    }
  }

  if (checkTranslationsImports) {
    const translationsSource = readFileSync(translationsPath, 'utf8');
    for (const locale of LOCALES) {
      for (const file of catalogs[locale].files) {
        if (!translationsSource.includes(`./locales/${locale}/${file}`)) {
          errors.push(`translations.ts does not import ${locale}/${file}`);
        }
      }
    }
  }

  return {
    ok: errors.length === 0,
    errors,
    usedCount: new Set(used.map((item) => item.key)).size,
    catalogCount: zhLeaves.size,
    used,
  };
}

export function checkI18n(options = {}) {
  const report = inspectI18n(options);
  if (!report.ok) {
    throw new Error(
      `Dashboard i18n check failed:\n${report.errors.join('\n')}`,
    );
  }
  return report;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  try {
    const report = checkI18n();
    console.log(
      `i18n check passed: ${report.usedCount} static keys, ${report.catalogCount} catalog keys.`,
    );
  } catch (error) {
    console.error(error instanceof Error ? error.message : error);
    process.exitCode = 1;
  }
}
