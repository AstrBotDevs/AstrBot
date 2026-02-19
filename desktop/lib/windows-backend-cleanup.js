'use strict';

const path = require('path');

const WINDOWS_PROCESS_QUERY_TIMEOUT_MS = 2000;

function createWindowsBackendCleanupState() {
  return {
    commandLineCache: new Map(),
    commandLineQueryUnavailable: false,
    commandLineFallbackLogged: false,
  };
}

function normalizeWindowsPathForMatch(value) {
  return String(value || '')
    .replace(/\//g, '\\')
    .toLowerCase();
}

function normalizeNumericPid(pid) {
  const numericPid = Number.parseInt(`${pid}`, 10);
  return Number.isInteger(numericPid) ? numericPid : null;
}

function normalizePidList(pids) {
  const numericPids = [];
  const seen = new Set();
  for (const pid of Array.isArray(pids) ? pids : []) {
    const numericPid = normalizeNumericPid(pid);
    if (numericPid === null || seen.has(numericPid)) {
      continue;
    }
    seen.add(numericPid);
    numericPids.push(numericPid);
  }
  return numericPids;
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

function parseWindowsCommandLineQueryOutput({ stdout, shellName, log }) {
  const trimmed = String(stdout || '').trim();
  if (!trimmed) {
    return new Map();
  }

  let parsed = null;
  try {
    parsed = JSON.parse(trimmed);
  } catch (error) {
    log(
      `Failed to parse process command line query output from ${shellName}: ${
        error instanceof Error ? error.message : String(error)
      }`,
    );
    return null;
  }

  const items = Array.isArray(parsed) ? parsed : [parsed];
  const commandLineMap = new Map();
  for (const item of items) {
    if (!item || typeof item !== 'object') {
      continue;
    }
    const numericPid = normalizeNumericPid(item.ProcessId);
    if (numericPid === null) {
      continue;
    }
    const rawCommandLine =
      typeof item.CommandLine === 'string' ? item.CommandLine.trim() : '';
    commandLineMap.set(numericPid, rawCommandLine || null);
  }
  return commandLineMap;
}

function queryWindowsProcessCommandLinesByShell({
  shellName,
  numericPids,
  spawnSync,
  log,
  timeoutMs,
}) {
  const filter = numericPids.map((numericPid) => `ProcessId = ${numericPid}`).join(' OR ');
  const query =
    `$p = Get-CimInstance Win32_Process -Filter "${filter}"; ` +
    'if ($null -ne $p) { $p | Select-Object ProcessId, CommandLine | ConvertTo-Json -Compress }';
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
        `Failed to query process command line by ${shellName}: ${error.message}`,
      );
    }
    return { hasShell: false, commandLineMap: null };
  }

  if (result.error && result.error.code === 'ENOENT') {
    return { hasShell: false, commandLineMap: null };
  }
  if (result.error && result.error.code === 'ETIMEDOUT') {
    log(`Timed out (${timeoutMs}ms) querying process command lines by ${shellName}.`);
    return { hasShell: true, commandLineMap: null };
  }
  if (result.error) {
    if (result.error.message) {
      log(
        `Failed to query process command line by ${shellName}: ${result.error.message}`,
      );
    }
    return { hasShell: true, commandLineMap: null };
  }
  if (result.status !== 0) {
    return { hasShell: true, commandLineMap: null };
  }

  const commandLineMap = parseWindowsCommandLineQueryOutput({
    stdout: result.stdout,
    shellName,
    log,
  });
  return { hasShell: true, commandLineMap };
}

function prefetchWindowsProcessCommandLines({
  pids,
  spawnSync,
  log,
  timeoutMs = WINDOWS_PROCESS_QUERY_TIMEOUT_MS,
  cleanupState,
}) {
  const state = cleanupState || createWindowsBackendCleanupState();
  const numericPids = normalizePidList(pids).filter(
    (numericPid) => !state.commandLineCache.has(numericPid),
  );

  if (numericPids.length === 0 || state.commandLineQueryUnavailable) {
    return state;
  }

  const queryAttempts = ['powershell', 'pwsh'];
  let hasAvailableShell = false;
  for (const shellName of queryAttempts) {
    const { hasShell, commandLineMap } = queryWindowsProcessCommandLinesByShell({
      shellName,
      numericPids,
      spawnSync,
      log,
      timeoutMs,
    });
    if (!hasShell) {
      continue;
    }
    hasAvailableShell = true;
    if (commandLineMap === null) {
      continue;
    }

    for (const numericPid of numericPids) {
      state.commandLineCache.set(
        numericPid,
        commandLineMap.has(numericPid) ? commandLineMap.get(numericPid) : null,
      );
    }
    state.commandLineQueryUnavailable = false;
    return state;
  }

  if (!hasAvailableShell) {
    state.commandLineQueryUnavailable = true;
    return state;
  }

  for (const numericPid of numericPids) {
    state.commandLineCache.set(numericPid, null);
  }
  state.commandLineQueryUnavailable = false;
  return state;
}

function getWindowsProcessCommandLine({
  pid,
  spawnSync,
  log,
  timeoutMs = WINDOWS_PROCESS_QUERY_TIMEOUT_MS,
  cleanupState,
}) {
  const state = cleanupState || createWindowsBackendCleanupState();
  const numericPid = normalizeNumericPid(pid);
  if (numericPid === null) {
    return { commandLine: null, commandLineQueryUnavailable: false, cleanupState: state };
  }

  if (state.commandLineQueryUnavailable) {
    return { commandLine: null, commandLineQueryUnavailable: true, cleanupState: state };
  }

  if (!state.commandLineCache.has(numericPid)) {
    prefetchWindowsProcessCommandLines({
      pids: [numericPid],
      spawnSync,
      log,
      timeoutMs,
      cleanupState: state,
    });
  }

  if (state.commandLineQueryUnavailable) {
    return { commandLine: null, commandLineQueryUnavailable: true, cleanupState: state };
  }

  return {
    commandLine: state.commandLineCache.has(numericPid)
      ? state.commandLineCache.get(numericPid)
      : null,
    commandLineQueryUnavailable: false,
    cleanupState: state,
  };
}

function matchesBackendMarkers({
  pid,
  backendConfig,
  spawnSync,
  log,
  cleanupState,
}) {
  const state = cleanupState || createWindowsBackendCleanupState();
  const markers = buildBackendCommandLineMarkers(backendConfig);
  if (!markers.length) {
    log(`Skip unmanaged cleanup for pid=${pid}: backend launch marker is unavailable.`);
    return false;
  }

  const { commandLine, commandLineQueryUnavailable } = getWindowsProcessCommandLine({
    pid,
    spawnSync,
    log,
    timeoutMs: WINDOWS_PROCESS_QUERY_TIMEOUT_MS,
    cleanupState: state,
  });
  if (!commandLine) {
    if (commandLineQueryUnavailable) {
      if (!state.commandLineFallbackLogged) {
        state.commandLineFallbackLogged = true;
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
  fallbackCmdRaw,
  spawnSync,
  log,
  cleanupState,
}) {
  const state = cleanupState || createWindowsBackendCleanupState();
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
    spawnSync,
    log,
    cleanupState: state,
  });
}

module.exports = {
  createWindowsBackendCleanupState,
  prefetchWindowsProcessCommandLines,
  shouldKillUnmanagedBackendProcess,
};
