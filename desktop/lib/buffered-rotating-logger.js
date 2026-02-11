'use strict';

const { appendRotatingLog } = require('./common');

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
    this.flushIntervalMs = flushIntervalMs;
    this.maxBufferBytes = maxBufferBytes;
    this.buffer = [];
    this.bufferBytes = 0;
    this.flushTimer = null;
  }

  setLogPath(logPath) {
    this.flush();
    this.logPath = logPath || null;
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

