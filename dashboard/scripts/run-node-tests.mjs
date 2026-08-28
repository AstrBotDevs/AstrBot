import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const dashboardRoot = resolve(fileURLToPath(new URL('..', import.meta.url)));
const testFiles = [
  resolve(dashboardRoot, 'tests/subsetMdiFont.test.mjs'),
  resolve(dashboardRoot, 'tests/checkI18n.test.mjs'),
];

for (const testFile of testFiles) {
  if (!existsSync(testFile)) {
    throw new Error(`Native Node test file is missing: ${testFile}`);
  }
}

const result = spawnSync(
  process.execPath,
  ['--no-warnings', '--test', ...testFiles],
  { cwd: dashboardRoot, stdio: 'inherit' },
);

if (result.error) {
  throw result.error;
}

process.exitCode = result.status ?? 1;
