'use strict';

const path = require('path');

const WINDOWS_PROCESS_QUERY_TIMEOUT_MS = 2000;
const COMMAND_LINE_QUERY_UNAVAILABLE_KEY = '__command_line_query_unavailable__';
const COMMAND_LINE_FALLBACK_LOGGED_KEY = '__command_line_fallback_logged__';

function isQueryUnavailable(cache) {
  return !!(cache && cache.get(COMMAND_LINE_QUERY_UNAVAILABLE_KEY));
}

function setQueryUnavailable(cache, value) {
  if (cache) {
    cache.set(COMMAND_LINE_QUERY_UNAVAILABLE_KEY, !!value);
  }
}

function wasFallbackLogged(cache) {
  return !!(cache && cache.get(COMMAND_LINE_FALLBACK_LOGGED_KEY));
}

function markFallbackLogged(cache) {
  if (cache) {
    cache.set(COMMAND_LINE_FALLBACK_LOGGED_KEY, true);
  }
}

function normalizeWindowsPathForMatch(value) {
  return String(value || '')
    .replace(/\//g, '\\')
    .toLowerCase();
}

function isGenericWindowsPythonImage(imageName) {
  const normalized = String(imageName || '').toLowerCase();
  return normalized === 'python.exe' || normalized === 'pythonw.exe' || normalized === 'py.exe';
}

function getWindowsProcessCommandLine({ pid, commandLineCache, spawnSync, log, timeoutMs }) {
  const numericPid = Number.parseInt(`${pid}`, 10);
  if (!Number.isInteger(numericPid)) {
    return { commandLine: null, commandLineQueryUnavailable: false };
  }

  if (isQueryUnavailable(commandLineCache)) {
    return { commandLine: null, commandLineQueryUnavailable: true };
  }

  if (commandLineCache && commandLineCache.has(numericPid)) {
    return {
      commandLine: commandLineCache.get(numericPid),
      commandLineQueryUnavailable: false,
    };
  }

  const query = `$p = Get-CimInstance Win32_Process -Filter "ProcessId = ${numericPid}"; if ($null -ne $p) { $p.CommandLine }`;
  const args = ['-NoProfile', '-NonInteractive', '-Command', query];
  const options = {
    stdio: ['ignore', 'pipe', 'ignore'],
    encoding: 'utf8',
    windowsHide: true,
    timeout: timeoutMs,
  };

  const queryAttempts = ['powershell', 'pwsh'];
  let hasAvailableShell = false;
  for (const shellName of queryAttempts) {
    let result = null;
    try {
      result = spawnSync(shellName, args, options);
    } catch (error) {
      if (error instanceof Error && error.message) {
        log(
          `Failed to query process command line by ${shellName} for pid=${numericPid}: ${error.message}`,
        );
      }
      continue;
    }

    if (result.error && result.error.code === 'ENOENT') {
      continue;
    }
    hasAvailableShell = true;
    if (result.error && result.error.code === 'ETIMEDOUT') {
      log(
        `Timed out (${timeoutMs}ms) querying process command line by ${shellName} for pid=${numericPid}.`,
      );
      continue;
    }
    if (result.error) {
      if (result.error.message) {
        log(
          `Failed to query process command line by ${shellName} for pid=${numericPid}: ${result.error.message}`,
        );
      }
      continue;
    }

    if (result.status === 0) {
      const commandLine =
        result.stdout
          .split(/\r?\n/)
          .map((item) => item.trim())
          .find((item) => item.length > 0) || null;
      if (commandLineCache) {
        commandLineCache.set(numericPid, commandLine);
        setQueryUnavailable(commandLineCache, false);
      }
      return { commandLine, commandLineQueryUnavailable: false };
    }
  }

  if (!hasAvailableShell) {
    setQueryUnavailable(commandLineCache, true);
    return { commandLine: null, commandLineQueryUnavailable: true };
  }

  if (commandLineCache) {
    commandLineCache.set(numericPid, null);
    setQueryUnavailable(commandLineCache, false);
  }
  return { commandLine: null, commandLineQueryUnavailable: false };
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

function matchesBackendMarkers({
  pid,
  backendConfig,
  commandLineCache,
  spawnSync,
  log,
}) {
  const markers = buildBackendCommandLineMarkers(backendConfig);
  if (!markers.length) {
    log(`Skip unmanaged cleanup for pid=${pid}: backend launch marker is unavailable.`);
    return false;
  }

  const { commandLine, commandLineQueryUnavailable } = getWindowsProcessCommandLine({
    pid,
    commandLineCache,
    spawnSync,
    log,
    timeoutMs: WINDOWS_PROCESS_QUERY_TIMEOUT_MS,
  });
  if (!commandLine) {
    if (commandLineQueryUnavailable) {
      if (!wasFallbackLogged(commandLineCache)) {
        markFallbackLogged(commandLineCache);
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
  const matched = markers.some((marker) => marker && normalizedCommandLine.includes(marker));
  if (!matched) {
    log(
      `Skip unmanaged cleanup for pid=${pid}: command line does not match AstrBot backend launch marker.`,
    );
  }
  return matched;
}

function shouldKillUnmanagedBackendProcess({
  pid,
  processInfo,
  backendConfig,
  allowImageOnlyMatch,
  commandLineCache,
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

  return matchesBackendMarkers({
    pid,
    backendConfig,
    commandLineCache,
    spawnSync,
    log,
  });
}

module.exports = {
  shouldKillUnmanagedBackendProcess,
};
