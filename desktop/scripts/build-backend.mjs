import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const rootDir = path.resolve(__dirname, '..', '..');
const outputDir = path.join(rootDir, 'desktop', 'resources', 'backend');
const appDir = path.join(outputDir, 'app');
const runtimeDir = path.join(outputDir, 'python');
const manifestPath = path.join(outputDir, 'runtime-manifest.json');
const launcherPath = path.join(outputDir, 'launch_backend.py');

const runtimeSource =
  process.env.ASTRBOT_DESKTOP_CPYTHON_HOME ||
  process.env.ASTRBOT_DESKTOP_BACKEND_RUNTIME;

if (!runtimeSource) {
  console.error(
    'Missing CPython runtime source. Set ASTRBOT_DESKTOP_CPYTHON_HOME ' +
      '(recommended) or ASTRBOT_DESKTOP_BACKEND_RUNTIME.',
  );
  process.exit(1);
}

const runtimeSourceReal = path.resolve(rootDir, runtimeSource);
if (!fs.existsSync(runtimeSourceReal)) {
  console.error(`CPython runtime source does not exist: ${runtimeSourceReal}`);
  process.exit(1);
}

const normalizePathForCompare = (targetPath) => {
  const resolved = path.resolve(targetPath).replace(/[\\/]+$/, '');
  return process.platform === 'win32' ? resolved.toLowerCase() : resolved;
};

const isSameOrSubPath = (targetPath, parentPath) => {
  const target = normalizePathForCompare(targetPath);
  const parent = normalizePathForCompare(parentPath);
  return target === parent || target.startsWith(`${parent}${path.sep}`);
};

if (
  isSameOrSubPath(runtimeSourceReal, outputDir) ||
  isSameOrSubPath(outputDir, runtimeSourceReal)
) {
  console.error(
    `CPython runtime source overlaps with backend output directory. ` +
      `runtime=${runtimeSourceReal}, output=${outputDir}. ` +
      'Please set ASTRBOT_DESKTOP_CPYTHON_HOME to a separate runtime directory.',
  );
  process.exit(1);
}

const parseExpectedRuntimeVersion = (rawVersion, sourceName) => {
  const match = /^(\d+)\.(\d+)$/.exec(String(rawVersion).trim());
  if (!match) {
    console.error(
      `Invalid expected Python version from ${sourceName}: ${rawVersion}. ` +
        'Expected format <major>.<minor>.',
    );
    process.exit(1);
  }
  return {
    major: Number.parseInt(match[1], 10),
    minor: Number.parseInt(match[2], 10),
  };
};

const readProjectRequiresPythonLowerBound = () => {
  const pyprojectPath = path.join(rootDir, 'pyproject.toml');
  if (!fs.existsSync(pyprojectPath)) {
    return null;
  }
  const content = fs.readFileSync(pyprojectPath, 'utf8');
  const requiresPythonMatch = /^\s*requires-python\s*=\s*"([^"]+)"/m.exec(content);
  if (!requiresPythonMatch) {
    return null;
  }
  const lowerBoundMatch = />=\s*(\d+)\.(\d+)/.exec(requiresPythonMatch[1]);
  if (!lowerBoundMatch) {
    return null;
  }
  return `${lowerBoundMatch[1]}.${lowerBoundMatch[2]}`;
};

const resolveExpectedRuntimeVersion = () => {
  if (process.env.ASTRBOT_DESKTOP_EXPECTED_PYTHON) {
    return parseExpectedRuntimeVersion(
      process.env.ASTRBOT_DESKTOP_EXPECTED_PYTHON,
      'ASTRBOT_DESKTOP_EXPECTED_PYTHON',
    );
  }

  const projectLowerBound = readProjectRequiresPythonLowerBound();
  if (projectLowerBound) {
    return parseExpectedRuntimeVersion(projectLowerBound, 'pyproject.toml requires-python');
  }

  console.error(
    'Unable to determine expected runtime Python version. ' +
      'Set ASTRBOT_DESKTOP_EXPECTED_PYTHON or declare project.requires-python in pyproject.toml.',
  );
  process.exit(1);
};

const expectedRuntimeVersion = resolveExpectedRuntimeVersion();

const sourceEntries = [
  ['astrbot', 'astrbot'],
  ['main.py', 'main.py'],
  ['runtime_bootstrap.py', 'runtime_bootstrap.py'],
  ['requirements.txt', 'requirements.txt'],
];

const shouldCopy = (srcPath) => {
  const base = path.basename(srcPath);
  if (base === '__pycache__' || base === '.pytest_cache' || base === '.ruff_cache') {
    return false;
  }
  if (base === '.git' || base === '.mypy_cache' || base === '.DS_Store') {
    return false;
  }
  if (base.endsWith('.pyc') || base.endsWith('.pyo')) {
    return false;
  }
  return true;
};

const copyTree = (fromPath, toPath, { dereference = false } = {}) => {
  fs.cpSync(fromPath, toPath, {
    recursive: true,
    force: true,
    filter: shouldCopy,
    dereference,
  });
};

const resolveRuntimePython = (runtimeRoot) => {
  const candidates =
    process.platform === 'win32'
      ? ['python.exe', path.join('Scripts', 'python.exe')]
      : [path.join('bin', 'python3'), path.join('bin', 'python')];

  for (const relativeCandidate of candidates) {
    const candidate = path.join(runtimeRoot, relativeCandidate);
    if (fs.existsSync(candidate)) {
      return {
        absolute: candidate,
        relative: path.relative(outputDir, candidate),
      };
    }
  }

  return null;
};

const validateRuntimePython = (pythonExecutable) => {
  const probe = spawnSync(
    pythonExecutable,
    ['-c', 'import sys, pip; print(f"{sys.version_info.major}.{sys.version_info.minor}")'],
    {
      stdio: ['ignore', 'pipe', 'pipe'],
      encoding: 'utf8',
      windowsHide: true,
      timeout: 5000,
    },
  );

  if (probe.error) {
    const reason =
      probe.error.code === 'ETIMEDOUT'
        ? 'runtime Python probe timed out'
        : probe.error.message || String(probe.error);
    console.error(`Runtime Python probe failed: ${reason}`);
    process.exit(1);
  }

  if (probe.status !== 0) {
    const stderrText = (probe.stderr || '').trim();
    console.error(
      `Runtime Python probe failed with exit code ${probe.status}. ` +
        (stderrText ? `stderr: ${stderrText}` : ''),
    );
    process.exit(1);
  }

  const versionMatch = /(\d+)\.(\d+)/.exec((probe.stdout || '').trim());
  if (!versionMatch) {
    console.error(
      `Runtime Python probe did not report a valid version. Output: ${(probe.stdout || '').trim()}`,
    );
    process.exit(1);
  }

  const actualVersion = {
    major: Number.parseInt(versionMatch[1], 10),
    minor: Number.parseInt(versionMatch[2], 10),
  };
  if (
    actualVersion.major !== expectedRuntimeVersion.major ||
    actualVersion.minor !== expectedRuntimeVersion.minor
  ) {
    console.error(
      `Runtime Python version mismatch: expected ${expectedRuntimeVersion.major}.${expectedRuntimeVersion.minor}, ` +
        `got ${actualVersion.major}.${actualVersion.minor}.`,
    );
    process.exit(1);
  }
};

const writeLauncherScript = () => {
  const content = `from __future__ import annotations

import runpy
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
APP_DIR = BACKEND_DIR / "app"

sys.path.insert(0, str(APP_DIR))

main_file = APP_DIR / "main.py"
if not main_file.is_file():
    raise FileNotFoundError(f"Backend entrypoint not found: {main_file}")

sys.argv[0] = str(main_file)
runpy.run_path(str(main_file), run_name="__main__")
`;
  fs.writeFileSync(launcherPath, content, 'utf8');
};

const sourceRuntimePython = resolveRuntimePython(runtimeSourceReal);
if (!sourceRuntimePython) {
  console.error(
    `Cannot find Python executable in runtime source: ${runtimeSourceReal}. ` +
      'Expected python under bin/ or Scripts/.',
  );
  process.exit(1);
}
validateRuntimePython(sourceRuntimePython.absolute);

fs.rmSync(outputDir, { recursive: true, force: true });
fs.mkdirSync(outputDir, { recursive: true });
fs.mkdirSync(appDir, { recursive: true });

for (const [srcRelative, destRelative] of sourceEntries) {
  const sourcePath = path.join(rootDir, srcRelative);
  const targetPath = path.join(appDir, destRelative);
  if (!fs.existsSync(sourcePath)) {
    console.error(`Backend source path does not exist: ${sourcePath}`);
    process.exit(1);
  }
  copyTree(sourcePath, targetPath);
}

copyTree(runtimeSourceReal, runtimeDir, { dereference: true });

const runtimePython = resolveRuntimePython(runtimeDir);
if (!runtimePython) {
  console.error(
    `Cannot find Python executable in runtime: ${runtimeDir}. ` +
      'Expected python under bin/ or Scripts/.',
  );
  process.exit(1);
}

writeLauncherScript();

const manifest = {
  mode: 'cpython-runtime',
  python: runtimePython.relative,
  entrypoint: path.basename(launcherPath),
  app: path.relative(outputDir, appDir),
};
fs.writeFileSync(manifestPath, JSON.stringify(manifest, null, 2), 'utf8');

console.log(`Prepared CPython backend runtime in ${outputDir}`);
console.log(`Runtime source: ${runtimeSourceReal}`);
console.log(`Python executable: ${runtimePython.relative}`);
