'use strict';

const fs = require('fs');
const path = require('path');

function resolvePackagedBackendState(resourcesPath, logFn) {
  const backendDir = path.join(resourcesPath, 'backend');
  if (!fs.existsSync(backendDir)) {
    return {
      ok: false,
      config: null,
      failureReason:
        `Packaged backend directory is missing: ${backendDir}. ` +
        'Please rebuild desktop backend runtime.',
    };
  }

  const manifestPath = path.join(backendDir, 'runtime-manifest.json');
  let manifest = null;
  if (fs.existsSync(manifestPath)) {
    try {
      const parsed = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
      if (parsed && typeof parsed === 'object') {
        manifest = parsed;
      }
    } catch (error) {
      if (typeof logFn === 'function') {
        logFn(
          `Failed to parse packaged backend manifest: ${
            error instanceof Error ? error.message : String(error)
          }`,
        );
      }
    }
  }

  const configFromManifest = manifest && typeof manifest === 'object' ? manifest : {};
  const resolvePath = (key, defaultRelative) => {
    const relativePath =
      typeof configFromManifest[key] === 'string' && configFromManifest[key]
        ? configFromManifest[key]
        : defaultRelative;
    const candidate = path.join(backendDir, relativePath);
    return fs.existsSync(candidate) ? candidate : null;
  };

  const defaultPythonRelative =
    process.platform === 'win32'
      ? path.join('python', 'Scripts', 'python.exe')
      : path.join('python', 'bin', 'python3');

  const config = {
    backendDir,
    manifest,
    appDir: resolvePath('app', 'app'),
    launchScriptPath: resolvePath('entrypoint', 'launch_backend.py'),
    runtimePythonPath: resolvePath('python', defaultPythonRelative),
  };

  const missingParts = [];
  if (!config.runtimePythonPath) {
    missingParts.push('runtime python executable');
  }
  if (!config.launchScriptPath) {
    missingParts.push('launch backend script');
  }
  if (missingParts.length > 0) {
    return {
      ok: false,
      config,
      failureReason:
        `Packaged backend runtime is incomplete (${missingParts.join(', ')}). ` +
        `backendDir=${config.backendDir}. ` +
        'Please run `pnpm --dir desktop run build:backend` before packaging.',
    };
  }

  return { ok: true, config, failureReason: null };
}

module.exports = {
  resolvePackagedBackendState,
};
