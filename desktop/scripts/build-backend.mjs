import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  copyTree,
  resolveAndValidateRuntimeSource,
  resolveRuntimePython,
} from './runtime-layout-utils.mjs';
import {
  resolveExpectedRuntimeVersion,
  validateRuntimePython,
} from './runtime-version-utils.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const rootDir = path.resolve(__dirname, '..', '..');
const outputDir = path.join(rootDir, 'desktop', 'resources', 'backend');
const appDir = path.join(outputDir, 'app');
const runtimeDir = path.join(outputDir, 'python');
const manifestPath = path.join(outputDir, 'runtime-manifest.json');
const launcherPath = path.join(outputDir, 'launch_backend.py');

const runtimeSource =
  process.env.ASTRBOT_DESKTOP_BACKEND_RUNTIME ||
  process.env.ASTRBOT_DESKTOP_CPYTHON_HOME;
const requirePipProbe = process.env.ASTRBOT_DESKTOP_REQUIRE_PIP === '1';

const sourceEntries = [
  ['astrbot', 'astrbot'],
  ['main.py', 'main.py'],
  ['runtime_bootstrap.py', 'runtime_bootstrap.py'],
  ['requirements.txt', 'requirements.txt'],
];

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
  const runtimeSourceReal = resolveAndValidateRuntimeSource({
    rootDir,
    outputDir,
    runtimeSource,
  });
  const expectedRuntimeConstraint = resolveExpectedRuntimeVersion({ rootDir });

  const sourceRuntimePython = resolveRuntimePython({
    runtimeRoot: runtimeSourceReal,
    outputDir,
  });
  if (!sourceRuntimePython) {
    throw new Error(
      `Cannot find Python executable in runtime source: ${runtimeSourceReal}. ` +
        'Expected python under bin/ or Scripts/.',
    );
  }
  validateRuntimePython({
    pythonExecutable: sourceRuntimePython.absolute,
    expectedRuntimeConstraint,
    requirePipProbe,
  });

  fs.rmSync(outputDir, { recursive: true, force: true });
  fs.mkdirSync(outputDir, { recursive: true });
  fs.mkdirSync(appDir, { recursive: true });

  for (const [srcRelative, destRelative] of sourceEntries) {
    const sourcePath = path.join(rootDir, srcRelative);
    const targetPath = path.join(appDir, destRelative);
    if (!fs.existsSync(sourcePath)) {
      throw new Error(`Backend source path does not exist: ${sourcePath}`);
    }
    copyTree(sourcePath, targetPath);
  }

  copyTree(runtimeSourceReal, runtimeDir, { dereference: true });

  const runtimePython = resolveRuntimePython({
    runtimeRoot: runtimeDir,
    outputDir,
  });
  if (!runtimePython) {
    throw new Error(
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
