import { execFileSync } from 'node:child_process';
import { readdirSync } from 'node:fs';
import { relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const dashboardRoot = resolve(fileURLToPath(new URL('..', import.meta.url)));
const testsRoot = resolve(dashboardRoot, 'tests');
const vitestCli = resolve(dashboardRoot, 'node_modules/vitest/vitest.mjs');
const testFilePattern = /\.(?:test|spec|vitest)\.(?:[cm]?[jt]sx?)$/;
const supportFiles = new Set(['setup.vitest.ts']);
const nativeNodeTestFiles = new Set([
  'subsetMdiFont.test.mjs',
  'checkI18n.test.mjs',
]);

function findTestLikeFiles(directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = resolve(directory, entry.name);

    if (entry.isDirectory()) {
      return findTestLikeFiles(path);
    }

    return entry.isFile() && testFilePattern.test(entry.name) ? [path] : [];
  });
}

const testFiles = findTestLikeFiles(testsRoot);
const vitestFiles = [];
const nodeFiles = [];
const unsupportedFiles = [];

for (const file of testFiles) {
  const testRelativePath = relative(testsRoot, file).replaceAll('\\', '/');

  if (supportFiles.has(testRelativePath)) {
    continue;
  }
  if (
    testRelativePath.startsWith('e2e/') &&
    testRelativePath.endsWith('.spec.ts')
  ) {
    continue;
  }
  if (
    testRelativePath.endsWith('.vitest.ts') ||
    (testRelativePath.endsWith('.test.mjs') &&
      !nativeNodeTestFiles.has(testRelativePath))
  ) {
    vitestFiles.push(file);
    continue;
  }
  if (testRelativePath.endsWith('.test.mjs')) {
    nodeFiles.push(file);
    continue;
  }
  unsupportedFiles.push(file);
}

if (unsupportedFiles.length > 0) {
  throw new Error(
    `Test-like files have no configured runner:\n${unsupportedFiles
      .map((file) => `  - ${relative(dashboardRoot, file)}`)
      .join('\n')}`,
  );
}

const collectedFiles = new Set(
  JSON.parse(
    execFileSync(
      process.execPath,
      [
        vitestCli,
        'list',
        '--config',
        'vitest.config.ts',
        '--filesOnly',
        '--json',
      ],
      { cwd: dashboardRoot, encoding: 'utf8' },
    ),
  ).map(({ file }) => resolve(file)),
);
const missingVitestFiles = vitestFiles.filter(
  (file) => !collectedFiles.has(file),
);

if (missingVitestFiles.length > 0) {
  throw new Error(
    `Vitest is not collecting test files:\n${missingVitestFiles
      .map((file) => `  - ${relative(dashboardRoot, file)}`)
      .join('\n')}`,
  );
}

if (nodeFiles.length === 0) {
  throw new Error('No native Node test files were found.');
}

console.log(
  `Collected ${vitestFiles.length} Vitest files and ${nodeFiles.length} native Node test files.`,
);
