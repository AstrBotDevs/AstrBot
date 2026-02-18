'use strict';

const path = require('path');
const { RotatingLogWriter } = require('./rotating-log-writer');
const {
  formatLogTimestamp,
  parseLogBackupCount,
  parseLogMaxBytes,
} = require('./common');

function createElectronLogger({ app, getRootDir }) {
  const electronLogMaxBytes = parseLogMaxBytes(
    process.env.ASTRBOT_ELECTRON_LOG_MAX_MB,
  );
  const electronLogBackupCount = parseLogBackupCount(
    process.env.ASTRBOT_ELECTRON_LOG_BACKUP_COUNT,
  );
  const writer = new RotatingLogWriter({
    logPath: null,
    maxBytes: electronLogMaxBytes,
    backupCount: electronLogBackupCount,
    label: 'electron-log',
  });

  function getElectronLogPath() {
    const rootDir =
      process.env.ASTRBOT_ROOT ||
      (typeof getRootDir === 'function' ? getRootDir() : null) ||
      app.getPath('userData');
    return path.join(rootDir, 'logs', 'electron.log');
  }

  function logElectron(message) {
    const logPath = getElectronLogPath();
    const line = `[${formatLogTimestamp()}] ${message}\n`;
    void writer.setLogPath(logPath);
    void writer.append(line);
  }

  async function flushElectron() {
    await writer.flush();
  }

  return {
    logElectron,
    flushElectron,
  };
}

module.exports = {
  createElectronLogger,
};
