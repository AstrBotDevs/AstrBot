'use strict';

const fs = require('fs');
const path = require('path');

const LOG_ROTATION_DEFAULT_MAX_MB = 20;
const LOG_ROTATION_DEFAULT_BACKUP_COUNT = 3;

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

function parseLogMaxBytes(
  maxMbRaw,
  defaultMaxMb = LOG_ROTATION_DEFAULT_MAX_MB,
) {
  const parsed = Number.parseInt(`${maxMbRaw ?? defaultMaxMb}`, 10);
  const maxMb = Number.isFinite(parsed) && parsed > 0 ? parsed : defaultMaxMb;
  return maxMb * 1024 * 1024;
}

function parseLogBackupCount(
  backupCountRaw,
  defaultBackupCount = LOG_ROTATION_DEFAULT_BACKUP_COUNT,
) {
  const parsed = Number.parseInt(
    `${backupCountRaw ?? defaultBackupCount}`,
    10,
  );
  if (Number.isFinite(parsed) && parsed >= 0) {
    return parsed;
  }
  return defaultBackupCount;
}

function rotateLogFileIfNeeded(logPath, maxBytes, backupCount, incomingBytes = 0) {
  if (!logPath || !maxBytes || maxBytes <= 0) {
    return;
  }
  if (!fs.existsSync(logPath)) {
    return;
  }

  let currentSize = 0;
  try {
    currentSize = fs.statSync(logPath).size;
  } catch (error) {
    logRotationFsError('stat', logPath, error);
    return;
  }
  if (currentSize + Math.max(0, incomingBytes) <= maxBytes) {
    return;
  }

  if (!backupCount || backupCount <= 0) {
    try {
      fs.truncateSync(logPath, 0);
    } catch (error) {
      logRotationFsError('truncate', logPath, error);
    }
    return;
  }

  const oldestPath = `${logPath}.${backupCount}`;
  try {
    if (fs.existsSync(oldestPath)) {
      fs.unlinkSync(oldestPath);
    }
  } catch (error) {
    logRotationFsError('unlink', oldestPath, error);
  }

  for (let index = backupCount - 1; index >= 1; index -= 1) {
    const sourcePath = `${logPath}.${index}`;
    const targetPath = `${logPath}.${index + 1}`;
    try {
      if (fs.existsSync(sourcePath)) {
        fs.renameSync(sourcePath, targetPath);
      }
    } catch (error) {
      logRotationFsError('rename', `${sourcePath} -> ${targetPath}`, error);
    }
  }

  try {
    fs.renameSync(logPath, `${logPath}.1`);
  } catch (error) {
    logRotationFsError('rename', `${logPath} -> ${logPath}.1`, error);
  }
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
  delay,
  ensureDir,
  isLogRotationDebugEnabled,
  logRotationFsError,
  normalizeUrl,
  parseLogBackupCount,
  parseLogMaxBytes,
  rotateLogFileIfNeeded,
  waitForProcessExit,
};
