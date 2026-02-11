'use strict';

const fs = require('fs');
const path = require('path');

const LOG_ROTATION_DEFAULT_MAX_MB = 20;
const LOG_ROTATION_DEFAULT_BACKUP_COUNT = 3;
const LOG_SIZE_CACHE_MAX_ENTRIES = 256;
const logSizeCache = new Map();

function normalizeUrl(value) {
  try {
    const url = new URL(value);
    if (!url.pathname.endsWith('/')) {
      url.pathname += '/';
    }
    return url.toString();
  } catch {
    return 'http://127.0.0.1:6185/';
  }
}

function ensureDir(value) {
  if (!value) {
    return;
  }
  if (fs.existsSync(value)) {
    return;
  }
  fs.mkdirSync(value, { recursive: true });
}

function isLogRotationDebugEnabled() {
  return (
    process.env.ASTRBOT_LOG_ROTATION_DEBUG === '1' ||
    process.env.NODE_ENV === 'development'
  );
}

function logRotationFsError(action, targetPath, error) {
  if (!isLogRotationDebugEnabled()) {
    return;
  }
  const details = error instanceof Error ? error.message : String(error);
  console.warn(
    `[astrbot][log-rotation] ${action} failed for ${targetPath}: ${details}`,
  );
}

function isIgnorableFsError(error) {
  return Boolean(error && typeof error === 'object' && error.code === 'ENOENT');
}

function readLogSize(logPath) {
  try {
    return fs.statSync(logPath).size;
  } catch (error) {
    if (isIgnorableFsError(error)) {
      return 0;
    }
    logRotationFsError('stat', logPath, error);
    return 0;
  }
}

function getCachedLogSize(logPath) {
  if (logSizeCache.has(logPath)) {
    return logSizeCache.get(logPath);
  }
  const size = readLogSize(logPath);
  setCachedLogSize(logPath, size);
  return size;
}

function setCachedLogSize(logPath, size) {
  if (!logPath) {
    return;
  }
  if (!Number.isFinite(size) || size < 0) {
    logSizeCache.delete(logPath);
    return;
  }
  if (logSizeCache.has(logPath)) {
    // Refresh insertion order to keep recently used entries.
    logSizeCache.delete(logPath);
  }
  logSizeCache.set(logPath, size);
  while (logSizeCache.size > LOG_SIZE_CACHE_MAX_ENTRIES) {
    const oldestKey = logSizeCache.keys().next().value;
    if (oldestKey === undefined) {
      break;
    }
    logSizeCache.delete(oldestKey);
  }
}

function clearCachedLogSize(logPath) {
  if (!logPath) {
    return;
  }
  logSizeCache.delete(logPath);
}

function parseEnvInt(raw, defaultValue) {
  const parsed = Number.parseInt(`${raw ?? ''}`, 10);
  return Number.isFinite(parsed) ? parsed : defaultValue;
}

function parseLogMaxBytes(envValue) {
  const mb = parseEnvInt(envValue, LOG_ROTATION_DEFAULT_MAX_MB);
  const maxMb = mb > 0 ? mb : LOG_ROTATION_DEFAULT_MAX_MB;
  return maxMb * 1024 * 1024;
}

function parseLogBackupCount(envValue) {
  const count = parseEnvInt(envValue, LOG_ROTATION_DEFAULT_BACKUP_COUNT);
  return count >= 0 ? count : LOG_ROTATION_DEFAULT_BACKUP_COUNT;
}

function rotateWithoutBackups(logPath) {
  try {
    fs.truncateSync(logPath, 0);
  } catch (error) {
    if (isIgnorableFsError(error)) {
      setCachedLogSize(logPath, 0);
      return;
    }
    logRotationFsError('truncate', logPath, error);
  }
}

function rotateWithBackups(logPath, backupCount) {
  const oldestPath = `${logPath}.${backupCount}`;
  try {
    fs.unlinkSync(oldestPath);
  } catch (error) {
    if (!isIgnorableFsError(error)) {
      logRotationFsError('unlink', oldestPath, error);
    }
  }

  for (let index = backupCount - 1; index >= 1; index -= 1) {
    const sourcePath = `${logPath}.${index}`;
    const targetPath = `${logPath}.${index + 1}`;
    try {
      fs.renameSync(sourcePath, targetPath);
    } catch (error) {
      if (isIgnorableFsError(error)) {
        continue;
      }
      logRotationFsError('rename', `${sourcePath} -> ${targetPath}`, error);
    }
  }

  try {
    fs.renameSync(logPath, `${logPath}.1`);
  } catch (error) {
    if (isIgnorableFsError(error)) {
      return;
    }
    logRotationFsError('rename', `${logPath} -> ${logPath}.1`, error);
  }
}

function syncCachedLogSizeFromDisk(logPath) {
  setCachedLogSize(logPath, readLogSize(logPath));
}

function rotateLogFileIfNeeded(logPath, maxBytes, backupCount, incomingBytes = 0) {
  if (!logPath || !maxBytes || maxBytes <= 0) {
    return false;
  }

  const baseSize = getCachedLogSize(logPath);
  if (baseSize + Math.max(0, incomingBytes) <= maxBytes) {
    return false;
  }

  if (!backupCount || backupCount <= 0) {
    rotateWithoutBackups(logPath);
  } else {
    rotateWithBackups(logPath, backupCount);
  }
  syncCachedLogSizeFromDisk(logPath);
  return true;
}

function appendRotatingLog(logPath, payload, options = {}) {
  if (!logPath || payload === undefined || payload === null) {
    return;
  }
  ensureDir(path.dirname(logPath));
  const content =
    typeof payload === 'string' || Buffer.isBuffer(payload)
      ? payload
      : String(payload);
  const incomingBytes = Buffer.isBuffer(content)
    ? content.length
    : Buffer.byteLength(content, 'utf8');
  const maxBytes = Number.isFinite(options.maxBytes) ? options.maxBytes : 0;
  const backupCount = Number.isFinite(options.backupCount)
    ? options.backupCount
    : 0;
  rotateLogFileIfNeeded(logPath, maxBytes, backupCount, incomingBytes);
  try {
    fs.appendFileSync(logPath, content, Buffer.isBuffer(content) ? undefined : 'utf8');
    setCachedLogSize(logPath, getCachedLogSize(logPath) + incomingBytes);
  } catch (error) {
    logRotationFsError('append', logPath, error);
  }
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function waitForProcessExit(child, timeoutMs = 5000) {
  if (!child) {
    return Promise.resolve('missing');
  }
  if (child.exitCode !== null || child.signalCode !== null) {
    return Promise.resolve('exited');
  }
  return new Promise((resolve) => {
    let settled = false;
    const finish = (reason) => {
      if (settled) {
        return;
      }
      settled = true;
      clearTimeout(timeout);
      resolve(reason);
    };
    const timeout = setTimeout(() => finish('timeout'), timeoutMs);
    child.once('exit', () => finish('exit'));
    child.once('error', () => finish('error'));
  });
}

module.exports = {
  LOG_ROTATION_DEFAULT_BACKUP_COUNT,
  LOG_ROTATION_DEFAULT_MAX_MB,
  appendRotatingLog,
  clearCachedLogSize,
  delay,
  ensureDir,
  isIgnorableFsError,
  isLogRotationDebugEnabled,
  logRotationFsError,
  normalizeUrl,
  parseLogBackupCount,
  parseLogMaxBytes,
  rotateLogFileIfNeeded,
  waitForProcessExit,
};
