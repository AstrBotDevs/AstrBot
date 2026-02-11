'use strict';

const { RotatingLogWriter } = require('./rotating-log-writer');
const { parseEnvInt } = require('./common');

const DEFAULT_FLUSH_INTERVAL_MS = 120;
const DEFAULT_MAX_BUFFER_BYTES = 128 * 1024;
const MIN_FLUSH_INTERVAL_MS = 10;
const MIN_MAX_BUFFER_BYTES = 4 * 1024;
const MAX_MAX_BUFFER_BYTES = 16 * 1024 * 1024;

function clampIntOption(raw, { defaultValue, min, max }) {
  const value = parseEnvInt(raw, defaultValue);
  return Math.min(Math.max(value, min), max);
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
    this.flushIntervalMs = clampIntOption(flushIntervalMs, {
      defaultValue: DEFAULT_FLUSH_INTERVAL_MS,
      min: MIN_FLUSH_INTERVAL_MS,
      max: 60 * 1000,
    });
    this.maxBufferBytes = clampIntOption(maxBufferBytes, {
      defaultValue: DEFAULT_MAX_BUFFER_BYTES,
      min: MIN_MAX_BUFFER_BYTES,
      max: MAX_MAX_BUFFER_BYTES,
    });
    this.buffer = [];
    this.bufferBytes = 0;
    this.flushTimer = null;
    this.pathSwitch = Promise.resolve();
    this.writer = new RotatingLogWriter({
      logPath: this.logPath,
      maxBytes,
      backupCount,
      label,
    });
  }

  setLogPath(logPath) {
    const nextLogPath = logPath || null;
    this.pathSwitch = this.pathSwitch.then(async () => {
      if (nextLogPath === this.logPath) {
        await this.flush();
        return;
      }

      const previousLogPath = this.logPath;
      if (previousLogPath) {
        await this.flush();
      }

      this.logPath = null;
      await this.writer.setLogPath(nextLogPath);
      this.logPath = nextLogPath;
      await this.flush();
    });
    return this.pathSwitch;
  }

  log(payload) {
    if (payload === undefined || payload === null) {
      return;
    }
    const chunk = Buffer.isBuffer(payload)
      ? payload
      : Buffer.from(String(payload), 'utf8');
    if (!chunk.length) {
      return;
    }

    if (!this.logPath) {
      const boundedChunk = this.clipChunkToBufferLimit(chunk);
      this.dropOldestUntilWithinLimit(boundedChunk.length);
      this.buffer.push(boundedChunk);
      this.bufferBytes += boundedChunk.length;
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
    if (!this.buffer.length) {
      return this.writer.flush();
    }
    if (!this.logPath) {
      // Path is switching or temporarily unavailable; keep buffered data.
      this.dropOldestUntilWithinLimit(0);
      return this.writer.flush();
    }

    const chunks = this.buffer;
    this.buffer = [];
    this.bufferBytes = 0;
    const payload = chunks.length === 1 ? chunks[0] : Buffer.concat(chunks);
    this.writer.append(payload);
    return this.writer.flush();
  }

  dropOldestUntilWithinLimit(incomingBytes = 0) {
    while (
      this.buffer.length &&
      this.bufferBytes + Math.max(0, incomingBytes) > this.maxBufferBytes
    ) {
      const removed = this.buffer.shift();
      if (removed) {
        this.bufferBytes -= removed.length;
      }
    }
    if (this.bufferBytes < 0) {
      this.bufferBytes = 0;
    }
  }

  clipChunkToBufferLimit(chunk) {
    if (chunk.length <= this.maxBufferBytes) {
      return chunk;
    }
    return chunk.subarray(chunk.length - this.maxBufferBytes);
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
