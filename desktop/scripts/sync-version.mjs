import { readFile, writeFile } from 'node:fs/promises';
import { spawnSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const rootDir = path.resolve(__dirname, '..', '..');
const desktopPackagePath = path.join(rootDir, 'desktop', 'package.json');
const pyprojectPath = path.join(rootDir, 'pyproject.toml');

function getGitTag() {
  const result = spawnSync('git', ['describe', '--tags', '--abbrev=0'], {
    cwd: rootDir,
    encoding: 'utf8',
  });
  if (result.status === 0) {
    const tag = result.stdout.trim();
    return tag.length ? tag : null;
  }
  return null;
}

function normalizeTag(tag) {
  return tag.replace(/^v/i, '');
}

async function getPyprojectVersion() {
  try {
    const data = await readFile(pyprojectPath, 'utf8');
    const match = data.match(/^\s*version\s*=\s*"([^"]+)"/m);
    return match ? match[1] : null;
  } catch {
    return null;
  }
}

const pkgRaw = await readFile(desktopPackagePath, 'utf8');
const pkg = JSON.parse(pkgRaw);
const tag = getGitTag();
const versionFromTag = tag ? normalizeTag(tag) : null;
const versionFromPyproject = await getPyprojectVersion();
const version = versionFromPyproject || versionFromTag || pkg.version;

if (
  versionFromPyproject &&
  versionFromTag &&
  versionFromPyproject !== versionFromTag
) {
  console.log(
    `Using pyproject version ${versionFromPyproject} (ignoring git tag ${versionFromTag}).`,
  );
}

if (!version) {
  console.warn('No version found to sync.');
  process.exit(0);
}

if (pkg.version === version) {
  console.log(`Desktop version already ${version}`);
  process.exit(0);
}

pkg.version = version;
await writeFile(desktopPackagePath, `${JSON.stringify(pkg, null, 2)}\n`, 'utf8');
console.log(`Updated desktop version to ${version}`);
