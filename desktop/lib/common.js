'use strict';

const fs = require('fs');

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

function parseEnvInt(raw, defaultValue) {
  const parsed = Number.parseInt(`${raw ?? ''}`, 10);
  return Number.isFinite(parsed) ? parsed : defaultValue;
}

function isLogRotationDebugEnabled() {
  return (
    process.env.ASTRBOT_LOG_ROTATION_DEBUG === '1' ||
    process.env.NODE_ENV === 'development'
  );
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

function isIgnorableFsError(error) {
  return Boolean(error && typeof error === 'object' && error.code === 'ENOENT');
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
  delay,
  ensureDir,
  isIgnorableFsError,
  isLogRotationDebugEnabled,
  normalizeUrl,
  parseEnvInt,
  parseLogBackupCount,
  parseLogMaxBytes,
  waitForProcessExit,
};
