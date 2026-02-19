'use strict';

const path = require('path');

const WINDOWS_PROCESS_QUERY_TIMEOUT_MS = 2000;

function normalizeWindowsPathForMatch(value) {
  return String(value || '')
    .replace(/\//g, '\\')
    .toLowerCase();
}

function isGenericWindowsPythonImage(imageName) {
  const normalized = String(imageName || '').toLowerCase();
  return normalized === 'python.exe' || normalized === 'pythonw.exe' || normalized === 'py.exe';
}

function buildBackendCommandLineMarkers(backendConfig) {
  const safeBackendConfig =
    backendConfig && typeof backendConfig === 'object' ? backendConfig : {};
  if (!Array.isArray(safeBackendConfig.args) || safeBackendConfig.args.length === 0) {
    return [];
  }

  const primaryArg = safeBackendConfig.args[0];
  if (typeof primaryArg !== 'string' || !primaryArg) {
    return [];
  }

  const resolvedPrimaryArg = path.isAbsolute(primaryArg)
    ? primaryArg
    : path.resolve(safeBackendConfig.cwd || process.cwd(), primaryArg);
  return [
    normalizeWindowsPathForMatch(resolvedPrimaryArg),
    normalizeWindowsPathForMatch(path.basename(primaryArg)),
  ];
}

function getExpectedImageName(backendConfig, fallbackCmdRaw) {
  const safeBackendConfig =
    backendConfig && typeof backendConfig === 'object' ? backendConfig : {};
  const fallbackCmd = String(fallbackCmdRaw || 'python.exe')
    .trim()
    .split(/\s+/, 1)[0];
  return path
    .basename(safeBackendConfig.cmd || fallbackCmd || 'python.exe')
    .toLowerCase();
}

function matchesExpectedImage(processInfo, expectedImageName) {
  return processInfo.imageName.toLowerCase() === expectedImageName;
}

class WindowsBackendCleaner {
  constructor() {
    this.commandLineCache = new Map();
    this.commandLineQueryUnavailable = false;
    this.commandLineFallbackLogged = false;
  }

  resetState() {
    this.commandLineCache.clear();
    this.commandLineQueryUnavailable = false;
    this.commandLineFallbackLogged = false;
  }

  _tryShellForCommandLine({ shellName, numericPid, spawnSync, log, timeoutMs }) {
    const query = `$p = Get-CimInstance Win32_Process -Filter "ProcessId = ${numericPid}"; if ($null -ne $p) { $p.CommandLine }`;
    const args = ['-NoProfile', '-NonInteractive', '-Command', query];
    const options = {
      stdio: ['ignore', 'pipe', 'ignore'],
      encoding: 'utf8',
      windowsHide: true,
      timeout: timeoutMs,
    };

    let result = null;
    try {
      result = spawnSync(shellName, args, options);
    } catch (error) {
      if (error instanceof Error && error.message) {
        log(
          `Failed to query process command line by ${shellName} for pid=${numericPid}: ${error.message}`,
        );
      }
      return { hasShell: false, commandLine: null };
    }

    if (result.error && result.error.code === 'ENOENT') {
      return { hasShell: false, commandLine: null };
    }
    if (result.error && result.error.code === 'ETIMEDOUT') {
      log(
        `Timed out (${timeoutMs}ms) querying process command line by ${shellName} for pid=${numericPid}.`,
      );
      return { hasShell: true, commandLine: null };
    }
    if (result.error) {
      if (result.error.message) {
        log(
          `Failed to query process command line by ${shellName} for pid=${numericPid}: ${result.error.message}`,
        );
      }
      return { hasShell: true, commandLine: null };
    }

    if (result.status !== 0) {
      return { hasShell: true, commandLine: null };
    }

    const commandLine =
      result.stdout
        .split(/\r?\n/)
        .map((item) => item.trim())
        .find((item) => item.length > 0) || null;
    return { hasShell: true, commandLine };
  }

  getWindowsProcessCommandLine({ pid, spawnSync, log, timeoutMs }) {
    const numericPid = Number.parseInt(`${pid}`, 10);
    if (!Number.isInteger(numericPid)) {
      return { commandLine: null, commandLineQueryUnavailable: false };
    }

    if (this.commandLineQueryUnavailable) {
      return { commandLine: null, commandLineQueryUnavailable: true };
    }

    if (this.commandLineCache.has(numericPid)) {
      return {
        commandLine: this.commandLineCache.get(numericPid),
        commandLineQueryUnavailable: false,
      };
    }

    const queryAttempts = ['powershell', 'pwsh'];
    let hasAvailableShell = false;
    for (const shellName of queryAttempts) {
      const { hasShell, commandLine } = this._tryShellForCommandLine({
        shellName,
        numericPid,
        spawnSync,
        log,
        timeoutMs,
      });
      if (!hasShell) {
        continue;
      }
      hasAvailableShell = true;
      if (commandLine !== null) {
        this.commandLineCache.set(numericPid, commandLine);
        this.commandLineQueryUnavailable = false;
        return { commandLine, commandLineQueryUnavailable: false };
      }
    }

    if (!hasAvailableShell) {
      this.commandLineQueryUnavailable = true;
      return { commandLine: null, commandLineQueryUnavailable: true };
    }

    this.commandLineCache.set(numericPid, null);
    this.commandLineQueryUnavailable = false;
    return { commandLine: null, commandLineQueryUnavailable: false };
  }

  _matchesBackendMarkers({
    pid,
    backendConfig,
    spawnSync,
    log,
  }) {
    const markers = buildBackendCommandLineMarkers(backendConfig);
    if (!markers.length) {
      log(`Skip unmanaged cleanup for pid=${pid}: backend launch marker is unavailable.`);
      return false;
    }

    const { commandLine, commandLineQueryUnavailable } = this.getWindowsProcessCommandLine({
      pid,
      spawnSync,
      log,
      timeoutMs: WINDOWS_PROCESS_QUERY_TIMEOUT_MS,
    });
    if (!commandLine) {
      if (commandLineQueryUnavailable) {
        if (!this.commandLineFallbackLogged) {
          this.commandLineFallbackLogged = true;
          log(
            'Neither powershell nor pwsh is available. ' +
              'Falling back to image-name-only matching for generic Python backend cleanup.',
          );
        }
        return true;
      }
      log(`Skip unmanaged cleanup for pid=${pid}: unable to resolve process command line.`);
      return false;
    }

    const normalizedCommandLine = normalizeWindowsPathForMatch(commandLine);
    const matched = markers.some(
      (marker) => marker && normalizedCommandLine.includes(marker),
    );
    if (!matched) {
      log(
        `Skip unmanaged cleanup for pid=${pid}: command line does not match AstrBot backend launch marker.`,
      );
    }
    return matched;
  }

  shouldKillUnmanagedBackendProcess({
    pid,
    processInfo,
    backendConfig,
    allowImageOnlyMatch,
    spawnSync,
    log,
    fallbackCmdRaw,
  }) {
    const expectedImageName = getExpectedImageName(backendConfig, fallbackCmdRaw);
    if (!matchesExpectedImage(processInfo, expectedImageName)) {
      log(
        `Skip unmanaged cleanup for pid=${pid}: unexpected process image ${processInfo.imageName}.`,
      );
      return false;
    }

    if (allowImageOnlyMatch || !isGenericWindowsPythonImage(expectedImageName)) {
      return true;
    }

    return this._matchesBackendMarkers({
      pid,
      backendConfig,
      spawnSync,
      log,
    });
  }
}

module.exports = {
  WindowsBackendCleaner,
};
