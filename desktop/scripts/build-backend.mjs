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

const fail = (message) => {
  return new Error(message);
};

const normalizePathForCompare = (targetPath) => {
  const resolved = path.resolve(targetPath).replace(/[\\/]+$/, '');
  return process.platform === 'win32' ? resolved.toLowerCase() : resolved;
};

const isSameOrSubPath = (targetPath, parentPath) => {
  const target = normalizePathForCompare(targetPath);
  const parent = normalizePathForCompare(parentPath);
  return target === parent || target.startsWith(`${parent}${path.sep}`);
};

const resolveAndValidateRuntimeSource = () => {
  if (!runtimeSource) {
    throw fail(
      'Missing CPython runtime source. Set ASTRBOT_DESKTOP_CPYTHON_HOME ' +
        '(recommended) or ASTRBOT_DESKTOP_BACKEND_RUNTIME.',
    );
  }

  const runtimeSourceReal = path.resolve(rootDir, runtimeSource);
  if (!fs.existsSync(runtimeSourceReal)) {
    throw fail(`CPython runtime source does not exist: ${runtimeSourceReal}`);
  }

  if (
    isSameOrSubPath(runtimeSourceReal, outputDir) ||
    isSameOrSubPath(outputDir, runtimeSourceReal)
  ) {
    throw fail(
      `CPython runtime source overlaps with backend output directory. ` +
        `runtime=${runtimeSourceReal}, output=${outputDir}. ` +
        'Please set ASTRBOT_DESKTOP_CPYTHON_HOME to a separate runtime directory.',
    );
  }

  return runtimeSourceReal;
};

const parseExpectedRuntimeVersion = (rawVersion, sourceName) => {
  const match = /^(\d+)\.(\d+)$/.exec(String(rawVersion).trim());
  if (!match) {
    throw fail(
      `Invalid expected Python version from ${sourceName}: ${rawVersion}. ` +
        'Expected format <major>.<minor>.',
    );
  }
  return {
    major: Number.parseInt(match[1], 10),
    minor: Number.parseInt(match[2], 10),
  };
};

const extractLowerBoundFromPythonSpecifier = (rawSpecifier) => {
  if (typeof rawSpecifier !== 'string' || !rawSpecifier.trim()) {
    return null;
  }

  const clauses = rawSpecifier.replace(/\s+/g, '').split(',').filter(Boolean);
  let bestLowerBound = null;

  const updateLowerBound = (major, minor) => {
    if (
      !bestLowerBound ||
      major > bestLowerBound.major ||
      (major === bestLowerBound.major && minor > bestLowerBound.minor)
    ) {
      bestLowerBound = { major, minor };
    }
  };

  for (const clause of clauses) {
    const match = /^(>=|>|==|~=)(\d+)(?:\.(\d+))?/.exec(clause);
    if (!match) {
      continue;
    }

    const operator = match[1];
    let major = Number.parseInt(match[2], 10);
    let minor = Number.parseInt(match[3] || '0', 10);
    if (operator === '>') {
      if (match[3]) {
        minor += 1;
      } else {
        major += 1;
        minor = 0;
      }
    }
    updateLowerBound(major, minor);
  }

  if (!bestLowerBound) {
    return null;
  }
  return `${bestLowerBound.major}.${bestLowerBound.minor}`;
};

const parsePyprojectProbeOutput = (stdoutText) => {
  const lines = String(stdoutText || '')
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  for (let i = lines.length - 1; i >= 0; i -= 1) {
    try {
      const parsed = JSON.parse(lines[i]);
      if (parsed && typeof parsed === 'object') {
        return parsed;
      }
    } catch {}
  }
  return null;
};

const readProjectRequiresPythonLowerBound = () => {
  const pyprojectPath = path.join(rootDir, 'pyproject.toml');
  if (!fs.existsSync(pyprojectPath)) {
    return null;
  }

  const pyprojectProbeScript = `import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
try:
    import tomllib
except Exception:
    try:
        import tomli as tomllib
    except Exception:
        print(json.dumps({"requires_python": None}))
        raise SystemExit(0)

try:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
except Exception:
    print(json.dumps({"requires_python": None}))
    raise SystemExit(0)

project = data.get("project") if isinstance(data, dict) else None
requires_python = project.get("requires-python") if isinstance(project, dict) else None
print(json.dumps({"requires_python": requires_python}))
`;

  const probeCommands =
    process.platform === 'win32'
      ? [
          { cmd: 'python', prefixArgs: [] },
          { cmd: 'py', prefixArgs: ['-3'] },
        ]
      : [
          { cmd: 'python3', prefixArgs: [] },
          { cmd: 'python', prefixArgs: [] },
        ];

  for (const probeCommand of probeCommands) {
    const probe = spawnSync(
      probeCommand.cmd,
      [...probeCommand.prefixArgs, '-c', pyprojectProbeScript, pyprojectPath],
      {
        stdio: ['ignore', 'pipe', 'ignore'],
        encoding: 'utf8',
        windowsHide: true,
        timeout: 5000,
      },
    );
    if (probe.error && probe.error.code === 'ENOENT') {
      continue;
    }
    if (probe.error || probe.status !== 0) {
      continue;
    }

    const parsedOutput = parsePyprojectProbeOutput(probe.stdout);
    const requiresPythonSpecifier = parsedOutput?.requires_python;
    const lowerBound = extractLowerBoundFromPythonSpecifier(requiresPythonSpecifier);
    if (lowerBound) {
      return lowerBound;
    }
  }

  return null;
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

  throw fail(
    'Unable to determine expected runtime Python version. ' +
      'Set ASTRBOT_DESKTOP_EXPECTED_PYTHON or declare project.requires-python in pyproject.toml.',
  );
};

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

const validateRuntimePython = (pythonExecutable, expectedRuntimeVersion) => {
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
    throw fail(`Runtime Python probe failed: ${reason}`);
  }

  if (probe.status !== 0) {
    const stderrText = (probe.stderr || '').trim();
    throw fail(
      `Runtime Python probe failed with exit code ${probe.status}. ` +
        (stderrText ? `stderr: ${stderrText}` : ''),
    );
  }

  const versionMatch = /(\d+)\.(\d+)/.exec((probe.stdout || '').trim());
  if (!versionMatch) {
    throw fail(
      `Runtime Python probe did not report a valid version. Output: ${(probe.stdout || '').trim()}`,
    );
  }

  const actualVersion = {
    major: Number.parseInt(versionMatch[1], 10),
    minor: Number.parseInt(versionMatch[2], 10),
  };
  if (
    actualVersion.major !== expectedRuntimeVersion.major ||
    actualVersion.minor !== expectedRuntimeVersion.minor
  ) {
    throw fail(
      `Runtime Python version mismatch: expected ${expectedRuntimeVersion.major}.${expectedRuntimeVersion.minor}, ` +
        `got ${actualVersion.major}.${actualVersion.minor}.`,
    );
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

const main = () => {
  const runtimeSourceReal = resolveAndValidateRuntimeSource();
  const expectedRuntimeVersion = resolveExpectedRuntimeVersion();

  const sourceRuntimePython = resolveRuntimePython(runtimeSourceReal);
  if (!sourceRuntimePython) {
    throw fail(
      `Cannot find Python executable in runtime source: ${runtimeSourceReal}. ` +
        'Expected python under bin/ or Scripts/.',
    );
  }
  validateRuntimePython(sourceRuntimePython.absolute, expectedRuntimeVersion);

  fs.rmSync(outputDir, { recursive: true, force: true });
  fs.mkdirSync(outputDir, { recursive: true });
  fs.mkdirSync(appDir, { recursive: true });

  for (const [srcRelative, destRelative] of sourceEntries) {
    const sourcePath = path.join(rootDir, srcRelative);
    const targetPath = path.join(appDir, destRelative);
    if (!fs.existsSync(sourcePath)) {
      throw fail(`Backend source path does not exist: ${sourcePath}`);
    }
    copyTree(sourcePath, targetPath);
  }

  copyTree(runtimeSourceReal, runtimeDir, { dereference: true });

  const runtimePython = resolveRuntimePython(runtimeDir);
  if (!runtimePython) {
    throw fail(
      `Cannot find Python executable in runtime: ${runtimeDir}. ` +
        'Expected python under bin/ or Scripts/.',
    );
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
};

try {
  main();
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
}
