'use strict';

const fs = require('fs');

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
  delay,
  ensureDir,
  normalizeUrl,
  waitForProcessExit,
};
