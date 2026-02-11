'use strict';

const { appendRotatingLog, clearCachedLogSize } = require('./common');

const DEFAULT_FLUSH_INTERVAL_MS = 120;
const DEFAULT_MAX_BUFFER_BYTES = 128 * 1024;
const MIN_FLUSH_INTERVAL_MS = 10;
const MIN_MAX_BUFFER_BYTES = 4 * 1024;
const MAX_MAX_BUFFER_BYTES = 16 * 1024 * 1024;

function normalizeInt(raw, defaultValue) {
  const parsed = Number.parseInt(`${raw ?? ''}`, 10);
  return Number.isFinite(parsed) ? parsed : defaultValue;
}

function clampInt(raw, defaultValue, min, max) {
  const value = normalizeInt(raw, defaultValue);
  if (value < min) {
    return min;
  }
  if (value > max) {
    return max;
  }
  return value;
}

class BufferedRotatingLogger {
  constructor({
    logPath = null,
    maxBytes,
    backupCount,
    flushIntervalMs,
    maxBufferBytes,
  }) {
    this.logPath = logPath;
    this.maxBytes = maxBytes;
    this.backupCount = backupCount;
    this.flushIntervalMs = clampInt(
      flushIntervalMs,
      DEFAULT_FLUSH_INTERVAL_MS,
      MIN_FLUSH_INTERVAL_MS,
      60 * 1000,
    );
    this.maxBufferBytes = clampInt(
      maxBufferBytes,
      DEFAULT_MAX_BUFFER_BYTES,
      MIN_MAX_BUFFER_BYTES,
      MAX_MAX_BUFFER_BYTES,
    );
    this.buffer = [];
    this.bufferBytes = 0;
    this.flushTimer = null;
  }

  setLogPath(logPath) {
    const previousLogPath = this.logPath;
    this.flush();
    this.logPath = logPath || null;
    if (previousLogPath && previousLogPath !== this.logPath) {
      clearCachedLogSize(previousLogPath);
    }
  }

  log(payload) {
    if (!this.logPath || payload === undefined || payload === null) {
      return;
    }
    const chunk = Buffer.isBuffer(payload)
      ? payload
      : Buffer.from(String(payload), 'utf8');
    if (!chunk.length) {
      return;
    }

    this.buffer.push(chunk);
    this.bufferBytes += chunk.length;

    if (this.bufferBytes >= this.maxBufferBytes) {
      this.flush();
      return;
    }
    this.scheduleFlush();
  }

  flush() {
    this.clearFlushTimer();
    if (!this.buffer.length || !this.logPath) {
      this.buffer = [];
      this.bufferBytes = 0;
      return;
    }

    const chunks = this.buffer;
    this.buffer = [];
    this.bufferBytes = 0;
    const payload = chunks.length === 1 ? chunks[0] : Buffer.concat(chunks);
    appendRotatingLog(this.logPath, payload, {
      maxBytes: this.maxBytes,
      backupCount: this.backupCount,
    });
  }

  scheduleFlush() {
    if (this.flushTimer !== null) {
      return;
    }
    this.flushTimer = setTimeout(() => {
      this.flushTimer = null;
      this.flush();
    }, this.flushIntervalMs);
    this.flushTimer.unref?.();
  }

  clearFlushTimer() {
    if (this.flushTimer === null) {
      return;
    }
    clearTimeout(this.flushTimer);
    this.flushTimer = null;
  }
}

module.exports = {
  BufferedRotatingLogger,
};
