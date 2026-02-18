import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const readRequiresPythonScriptPath = path.join(__dirname, 'read-requires-python.py');

const parseExpectedRuntimeVersion = (rawVersion, sourceName) => {
  const match = /^(\d+)\.(\d+)$/.exec(String(rawVersion).trim());
  if (!match) {
    throw new Error(
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
    const match = /^(>=|>|==|~=)(\d+)(?:\.(\d+))?$/.exec(clause);
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

const readProjectRequiresPythonLowerBound = (rootDir) => {
  const pyprojectPath = path.join(rootDir, 'pyproject.toml');
  if (!fs.existsSync(pyprojectPath)) {
    return null;
  }
  if (!fs.existsSync(readRequiresPythonScriptPath)) {
    return null;
  }

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
      [...probeCommand.prefixArgs, readRequiresPythonScriptPath, pyprojectPath],
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

const compareMajorMinor = (left, right) => {
  if (left.major < right.major) {
    return -1;
  }
  if (left.major > right.major) {
    return 1;
  }
  if (left.minor < right.minor) {
    return -1;
  }
  if (left.minor > right.minor) {
    return 1;
  }
  return 0;
};

export const resolveExpectedRuntimeVersion = ({ rootDir }) => {
  if (process.env.ASTRBOT_DESKTOP_EXPECTED_PYTHON) {
    return {
      expectedRuntimeVersion: parseExpectedRuntimeVersion(
        process.env.ASTRBOT_DESKTOP_EXPECTED_PYTHON,
        'ASTRBOT_DESKTOP_EXPECTED_PYTHON',
      ),
      isLowerBoundRuntimeVersion: false,
      source: 'ASTRBOT_DESKTOP_EXPECTED_PYTHON',
    };
  }

  const projectLowerBound = readProjectRequiresPythonLowerBound(rootDir);
  if (projectLowerBound) {
    return {
      expectedRuntimeVersion: parseExpectedRuntimeVersion(
        projectLowerBound,
        'pyproject.toml requires-python',
      ),
      isLowerBoundRuntimeVersion: true,
      source: 'pyproject.toml requires-python',
    };
  }

  throw new Error(
    'Unable to determine expected runtime Python version. ' +
      'Set ASTRBOT_DESKTOP_EXPECTED_PYTHON or declare project.requires-python in pyproject.toml.',
  );
};

export const validateRuntimePython = ({
  pythonExecutable,
  expectedRuntimeConstraint,
  requirePipProbe,
}) => {
  const probeScript = requirePipProbe
    ? 'import sys, pip; print(sys.version_info[0], sys.version_info[1])'
    : 'import sys; print(sys.version_info[0], sys.version_info[1])';
  const probe = spawnSync(pythonExecutable, ['-c', probeScript], {
    stdio: ['ignore', 'pipe', 'pipe'],
    encoding: 'utf8',
    windowsHide: true,
    timeout: 5000,
  });

  if (probe.error) {
    const reason =
      probe.error.code === 'ETIMEDOUT'
        ? 'runtime Python probe timed out'
        : probe.error.message || String(probe.error);
    throw new Error(`Runtime Python probe failed: ${reason}`);
  }

  if (probe.status !== 0) {
    const stderrText = (probe.stderr || '').trim();
    if (requirePipProbe) {
      throw new Error(
        `Runtime Python probe failed with exit code ${probe.status}. ` +
          `pip import check is enabled by ASTRBOT_DESKTOP_REQUIRE_PIP=1. ` +
          (stderrText ? `stderr: ${stderrText}` : ''),
      );
    }
    throw new Error(
      `Runtime Python probe failed with exit code ${probe.status}. ` +
        (stderrText ? `stderr: ${stderrText}` : ''),
    );
  }

  const parts = (probe.stdout || '').trim().split(/\s+/);
  if (parts.length < 2) {
    throw new Error(
      `Runtime Python probe did not report a valid version. Output: ${(probe.stdout || '').trim()}`,
    );
  }

  const actualVersion = {
    major: Number.parseInt(parts[0], 10),
    minor: Number.parseInt(parts[1], 10),
  };
  const expectedRuntimeVersion = expectedRuntimeConstraint.expectedRuntimeVersion;
  const compareResult = compareMajorMinor(actualVersion, expectedRuntimeVersion);
  if (expectedRuntimeConstraint.isLowerBoundRuntimeVersion) {
    if (compareResult < 0) {
      throw new Error(
        `Runtime Python version is too low for ${expectedRuntimeConstraint.source}: ` +
          `expected >= ${expectedRuntimeVersion.major}.${expectedRuntimeVersion.minor}, ` +
          `got ${actualVersion.major}.${actualVersion.minor}.`,
      );
    }
    return;
  }

  if (compareResult !== 0) {
    throw new Error(
      `Runtime Python version mismatch for ${expectedRuntimeConstraint.source}: ` +
        `expected ${expectedRuntimeVersion.major}.${expectedRuntimeVersion.minor}, ` +
        `got ${actualVersion.major}.${actualVersion.minor}.`,
    );
  }
};
