import fs from 'node:fs';
import path from 'node:path';

const shouldCopy = (sourcePath) => {
  const base = path.basename(sourcePath);
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

export const copyTree = (fromPath, toPath, { dereference = false } = {}) => {
  fs.cpSync(fromPath, toPath, {
    recursive: true,
    force: true,
    filter: shouldCopy,
    dereference,
  });
};

export const resolveAndValidateRuntimeSource = ({ rootDir, outputDir, runtimeSource }) => {
  if (!runtimeSource) {
    throw new Error(
      'Missing CPython runtime source. Set ASTRBOT_DESKTOP_CPYTHON_HOME ' +
        '(recommended) or ASTRBOT_DESKTOP_BACKEND_RUNTIME.',
    );
  }

  const runtimeSourceReal = path.resolve(rootDir, runtimeSource);
  if (!fs.existsSync(runtimeSourceReal)) {
    throw new Error(`CPython runtime source does not exist: ${runtimeSourceReal}`);
  }

  const normalizeForCompare = (targetPath) => {
    const resolved = path.resolve(targetPath).replace(/[\\/]+$/, '');
    return process.platform === 'win32' ? resolved.toLowerCase() : resolved;
  };

  const runtimeNorm = normalizeForCompare(runtimeSourceReal);
  const outputNorm = normalizeForCompare(outputDir);
  const runtimeIsOutputOrSub =
    runtimeNorm === outputNorm || runtimeNorm.startsWith(`${outputNorm}${path.sep}`);
  const outputIsRuntimeOrSub =
    outputNorm === runtimeNorm || outputNorm.startsWith(`${runtimeNorm}${path.sep}`);

  if (runtimeIsOutputOrSub || outputIsRuntimeOrSub) {
    throw new Error(
      `CPython runtime source overlaps with backend output directory. ` +
        `runtime=${runtimeSourceReal}, output=${outputDir}. ` +
        'Please set ASTRBOT_DESKTOP_CPYTHON_HOME to a separate runtime directory.',
    );
  }

  return runtimeSourceReal;
};

export const resolveRuntimePython = ({ runtimeRoot, outputDir }) => {
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
