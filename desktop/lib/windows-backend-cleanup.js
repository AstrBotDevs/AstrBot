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

function queryWindowsProcessCommandLine({ pid, shellName, spawnSync, timeoutMs }) {
  const query = `$p = Get-CimInstance Win32_Process -Filter "ProcessId = ${pid}"; if ($null -ne $p) { $p.CommandLine }`;
  const args = ['-NoProfile', '-NonInteractive', '-Command', query];
  const options = {
    stdio: ['ignore', 'pipe', 'ignore'],
    encoding: 'utf8',
    windowsHide: true,
    timeout: timeoutMs,
  };
  if (shellName === 'powershell') {
    return spawnSync('powershell', args, options);
  }
  if (shellName === 'pwsh') {
    return spawnSync('pwsh', args, options);
  }
  throw new Error(`Unsupported shell for process command line query: ${shellName}`);
}

function parseWindowsProcessCommandLine(result) {
  if (!result || !result.stdout) {
    return null;
  }
  return (
    result.stdout
      .split(/\r?\n/)
      .map((item) => item.trim())
      .find((item) => item.length > 0) || null
  );
}

function getWindowsProcessCommandLine({ pid, commandLineCache, spawnSync, log, timeoutMs }) {
  const numericPid = Number.parseInt(`${pid}`, 10);
  if (!Number.isInteger(numericPid)) {
    return null;
  }

  if (commandLineCache && commandLineCache.has(numericPid)) {
    return commandLineCache.get(numericPid);
  }

  const queryAttempts = ['powershell', 'pwsh'];
  for (const shellName of queryAttempts) {
    let result = null;
    try {
      result = queryWindowsProcessCommandLine({
        pid: numericPid,
        shellName,
        spawnSync,
        timeoutMs,
      });
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
    if (result.error && result.error.code === 'ETIMEDOUT') {
      log(
        `Timed out (${timeoutMs}ms) querying process command line by ${shellName} for pid=${numericPid}.`,
      );
      continue;
    }

    if (result.status === 0) {
      const commandLine = parseWindowsProcessCommandLine(result);
      if (commandLineCache) {
        commandLineCache.set(numericPid, commandLine);
      }
      return commandLine;
    }
  }

  if (commandLineCache) {
    commandLineCache.set(numericPid, null);
  }
  return null;
}

function getFallbackWindowsBackendImageName(fallbackCmdRaw) {
  const fallbackCmd = String(fallbackCmdRaw || 'python.exe')
    .trim()
    .split(/\s+/, 1)[0];
  return path.basename(fallbackCmd || 'python.exe').toLowerCase();
}

function getExpectedWindowsBackendImageName(backendConfig, fallbackCmdRaw) {
  const safeBackendConfig =
    backendConfig && typeof backendConfig === 'object' ? backendConfig : {};
  return path
    .basename(safeBackendConfig.cmd || getFallbackWindowsBackendImageName(fallbackCmdRaw))
    .toLowerCase();
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
  const expectedImageName = getExpectedWindowsBackendImageName(backendConfig, fallbackCmdRaw);
  const actualImageName = processInfo.imageName.toLowerCase();
  if (actualImageName !== expectedImageName) {
    log(
      `Skip unmanaged cleanup for pid=${pid}: unexpected process image ${processInfo.imageName}.`,
    );
    return false;
  }

  if (allowImageOnlyMatch || !isGenericWindowsPythonImage(expectedImageName)) {
    return true;
  }

  const markers = buildBackendCommandLineMarkers(backendConfig);
  if (!markers.length) {
    log(`Skip unmanaged cleanup for pid=${pid}: backend launch marker is unavailable.`);
    return false;
  }

  const commandLine = getWindowsProcessCommandLine({
    pid,
    commandLineCache,
    spawnSync,
    log,
    timeoutMs: WINDOWS_PROCESS_QUERY_TIMEOUT_MS,
  });
  if (!commandLine) {
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

module.exports = {
  shouldKillUnmanagedBackendProcess,
};
