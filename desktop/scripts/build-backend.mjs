import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
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
const launcherTemplatePath = path.join(
  rootDir,
  'desktop',
  'scripts',
  'templates',
  'launch_backend.py',
);

const runtimeSource =
  process.env.ASTRBOT_DESKTOP_BACKEND_RUNTIME ||
  process.env.ASTRBOT_DESKTOP_CPYTHON_HOME;
const requirePipProbe = process.env.ASTRBOT_DESKTOP_REQUIRE_PIP === '1';

const sourceEntries = [
  'astrbot',
  'main.py',
  'runtime_bootstrap.py',
  'requirements.txt',
];

const prepareOutputDirs = () => {
  fs.rmSync(outputDir, { recursive: true, force: true });
  fs.mkdirSync(outputDir, { recursive: true });
  fs.mkdirSync(appDir, { recursive: true });
};

const copyAppSources = () => {
  for (const relativePath of sourceEntries) {
    const sourcePath = path.join(rootDir, relativePath);
    const targetPath = path.join(appDir, relativePath);
    if (!fs.existsSync(sourcePath)) {
      throw new Error(`Backend source path does not exist: ${sourcePath}`);
    }
    copyTree(sourcePath, targetPath);
  }
};

const prepareRuntimeExecutable = (runtimeSourceReal) => {
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
  return runtimePython;
};

const writeLauncherScript = () => {
  if (!fs.existsSync(launcherTemplatePath)) {
    throw new Error(`Launcher template does not exist: ${launcherTemplatePath}`);
  }
  const content = fs.readFileSync(launcherTemplatePath, 'utf8');
  fs.writeFileSync(launcherPath, content, 'utf8');
};

const writeRuntimeManifest = (runtimePython) => {
  const manifest = {
    mode: 'cpython-runtime',
    python: runtimePython.relative,
    entrypoint: path.basename(launcherPath),
    app: path.relative(outputDir, appDir),
  };
  fs.writeFileSync(manifestPath, JSON.stringify(manifest, null, 2), 'utf8');
};

const installRuntimeDependencies = (runtimePython) => {
  const requirementsPath = path.join(appDir, 'requirements.txt');
  if (!fs.existsSync(requirementsPath)) {
    throw new Error(`Backend requirements file does not exist: ${requirementsPath}`);
  }

  const runPipInstall = (extraArgs = []) => {
    const installArgs = [
      '-m',
      'pip',
      '--disable-pip-version-check',
      'install',
      '--no-cache-dir',
      '-r',
      requirementsPath,
      ...extraArgs,
    ];
    const installResult = spawnSync(runtimePython.absolute, installArgs, {
      cwd: outputDir,
      stdio: ['ignore', 'pipe', 'pipe'],
      encoding: 'utf8',
      windowsHide: true,
    });
    if (installResult.stdout) {
      process.stdout.write(installResult.stdout);
    }
    if (installResult.stderr) {
      process.stderr.write(installResult.stderr);
    }
    return installResult;
  };

  let installResult = runPipInstall();
  if (installResult.error) {
    throw new Error(
      `Failed to install backend runtime dependencies: ${installResult.error.message}`,
    );
  }
  if (installResult.status === 0) {
    return;
  }

  const outputText = `${installResult.stderr || ''}\n${installResult.stdout || ''}`;
  const shouldRetryWithBreakSystemPackages =
    outputText.includes('externally-managed-environment') ||
    outputText.includes('This environment is externally managed');

  if (shouldRetryWithBreakSystemPackages) {
    console.warn(
      'Detected externally managed Python runtime; retrying pip install with --break-system-packages.',
    );
    installResult = runPipInstall(['--break-system-packages']);
    if (installResult.error) {
      throw new Error(
        `Failed to install backend runtime dependencies: ${installResult.error.message}`,
      );
    }
    if (installResult.status === 0) {
      return;
    }
  }

  throw new Error(
    `Backend runtime dependency installation failed with exit code ${installResult.status}.`,
  );
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

  prepareOutputDirs();
  copyAppSources();
  const runtimePython = prepareRuntimeExecutable(runtimeSourceReal);
  installRuntimeDependencies(runtimePython);
  writeLauncherScript();
  writeRuntimeManifest(runtimePython);

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
