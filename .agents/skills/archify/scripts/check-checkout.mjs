#!/usr/bin/env node

import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const skillRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  '..',
);
const repoRoot = path.resolve(skillRoot, '../../..');
const cli = path.join(skillRoot, 'bin/archify.mjs');
const examplesDir = path.join(skillRoot, 'examples');
const typePattern =
  /\.(architecture|workflow|sequence|dataflow|lifecycle)\.json$/;

function run(args) {
  const result = spawnSync(process.execPath, [cli, ...args], {
    cwd: repoRoot,
    encoding: 'utf8',
  });
  if (result.status !== 0) {
    process.stderr.write(result.stderr || result.stdout || '');
    process.exit(result.status || 1);
  }
  return result.stdout;
}

run(['doctor']);

const files = fs
  .readdirSync(examplesDir)
  .filter((name) => typePattern.test(name))
  .sort();
if (files.length === 0) {
  process.stderr.write('no Archify example JSON found\n');
  process.exit(1);
}

for (const name of files) {
  const type = name.match(typePattern)[1];
  const input = path.join(examplesDir, name);
  const receipt = JSON.parse(
    run(['validate', type, input, '--quality', 'showcase', '--json']),
  );
  const checks = Array.isArray(receipt.checks) ? receipt.checks : [];
  const failed = checks.filter((check) => !check.ok);
  if (!receipt.ok || checks.length !== 9 || failed.length > 0) {
    process.stderr.write(`showcase failed: ${name}\n`);
    process.exit(1);
  }
  process.stdout.write(`ok ${name} (${checks.length} checks)\n`);
}
