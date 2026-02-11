'use strict';

const fs = require('fs/promises');
const path = require('path');
const { isIgnorableFsError, isLogRotationDebugEnabled } = require('./common');

class RotatingLogWriter {
  constructor({ logPath = null, maxBytes = 0, backupCount = 0, label = 'log' }) {
    this.logPath = logPath || null;
    this.maxBytes = Number.isFinite(maxBytes) && maxBytes > 0 ? maxBytes : 0;
    this.backupCount = Number.isFinite(backupCount) && backupCount >= 0 ? backupCount : 0;
    this.label = label;
    this.cachedSize = null;
    this.dirReadyForPath = null;
    this.queue = Promise.resolve();
  }

  setLogPath(logPath) {
    const nextPath = logPath || null;
    if (nextPath === this.logPath) {
      return this.queue;
    }
    return this.enqueue(async () => {
      this.logPath = nextPath;
      this.cachedSize = null;
      this.dirReadyForPath = null;
    });
  }

  append(payload) {
    if (payload === undefined || payload === null) {
      return this.queue;
    }
    const content = Buffer.isBuffer(payload)
      ? payload
      : Buffer.from(String(payload), 'utf8');
    if (!content.length) {
      return this.queue;
    }
    return this.enqueue(async () => {
      if (!this.logPath) {
        return;
      }
      await this.ensureDirReady();
      await this.ensureSizeLoaded();
      await this.rotateIfNeeded(content.length);
      await fs.appendFile(this.logPath, content);
      if (!Number.isFinite(this.cachedSize)) {
        this.cachedSize = await this.readSize();
      } else {
        this.cachedSize += content.length;
      }
    });
  }

  flush() {
    return this.queue;
  }

  enqueue(task) {
    const run = async () => {
      try {
        await task();
      } catch (error) {
        this.reportError('write', this.logPath || 'unknown', error);
      }
    };
    this.queue = this.queue.then(run, run);
    return this.queue;
  }

  async ensureSizeLoaded() {
    if (Number.isFinite(this.cachedSize)) {
      return;
    }
    this.cachedSize = await this.readSize();
  }

  async ensureDirReady() {
    if (!this.logPath) {
      return;
    }
    if (this.dirReadyForPath === this.logPath) {
      return;
    }
    const dirPath = path.dirname(this.logPath);
    try {
      await fs.mkdir(dirPath, { recursive: true });
      this.dirReadyForPath = this.logPath;
    } catch (error) {
      this.reportError('mkdir', dirPath, error);
    }
  }

  async readSize() {
    if (!this.logPath) {
      return 0;
    }
    try {
      const stat = await fs.stat(this.logPath);
      return stat.size;
    } catch (error) {
      if (isIgnorableFsError(error)) {
        return 0;
      }
      this.reportError('stat', this.logPath, error);
      return 0;
    }
  }

  async rotateIfNeeded(incomingBytes) {
    if (!this.logPath || this.maxBytes <= 0) {
      return;
    }

    const currentSize = Number.isFinite(this.cachedSize) ? this.cachedSize : 0;
    if (currentSize + Math.max(0, incomingBytes) <= this.maxBytes) {
      return;
    }

    if (this.backupCount <= 0) {
      try {
        await fs.truncate(this.logPath, 0);
      } catch (error) {
        if (!isIgnorableFsError(error)) {
          this.reportError('truncate', this.logPath, error);
        }
      }
      this.cachedSize = await this.readSize();
      return;
    }

    const oldestPath = `${this.logPath}.${this.backupCount}`;
    try {
      await fs.unlink(oldestPath);
    } catch (error) {
      if (!isIgnorableFsError(error)) {
        this.reportError('unlink', oldestPath, error);
      }
    }

    for (let index = this.backupCount - 1; index >= 1; index -= 1) {
      const sourcePath = `${this.logPath}.${index}`;
      const targetPath = `${this.logPath}.${index + 1}`;
      try {
        await fs.rename(sourcePath, targetPath);
      } catch (error) {
        if (!isIgnorableFsError(error)) {
          this.reportError('rename', `${sourcePath} -> ${targetPath}`, error);
        }
      }
    }

    try {
      await fs.rename(this.logPath, `${this.logPath}.1`);
    } catch (error) {
      if (!isIgnorableFsError(error)) {
        this.reportError('rename', `${this.logPath} -> ${this.logPath}.1`, error);
      }
    }

    this.cachedSize = await this.readSize();
  }

  reportError(action, targetPath, error) {
    if (!isLogRotationDebugEnabled()) {
      return;
    }
    const details = error instanceof Error ? error.message : String(error);
    console.error(
      `[astrbot][${this.label}] ${action} failed for ${targetPath}: ${details}`,
    );
  }
}

module.exports = {
  RotatingLogWriter,
};
