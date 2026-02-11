'use strict';

const { RotatingLogWriter } = require('./rotating-log-writer');

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
    label = 'buffered-log',
  }) {
    this.logPath = logPath || null;
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
    this.writer = new RotatingLogWriter({
      logPath: this.logPath,
      maxBytes,
      backupCount,
      label,
    });
  }

  setLogPath(logPath) {
    const nextLogPath = logPath || null;
    if (nextLogPath === this.logPath) {
      return this.writer.flush();
    }
    const previousFlush = this.flush();
    this.logPath = nextLogPath;
    return previousFlush.finally(() => this.writer.setLogPath(nextLogPath));
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
      void this.flush();
      return;
    }
    this.scheduleFlush();
  }

  flush() {
    this.clearFlushTimer();
    if (!this.buffer.length || !this.logPath) {
      this.buffer = [];
      this.bufferBytes = 0;
      return this.writer.flush();
    }

    const chunks = this.buffer;
    this.buffer = [];
    this.bufferBytes = 0;
    const payload = chunks.length === 1 ? chunks[0] : Buffer.concat(chunks);
    this.writer.append(payload);
    return this.writer.flush();
  }

  scheduleFlush() {
    if (this.flushTimer !== null) {
      return;
    }
    this.flushTimer = setTimeout(() => {
      this.flushTimer = null;
      void this.flush();
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

