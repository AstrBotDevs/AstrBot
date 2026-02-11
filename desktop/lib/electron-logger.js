'use strict';

const path = require('path');
const {
  appendRotatingLog,
  parseLogBackupCount,
  parseLogMaxBytes,
} = require('./common');

function createElectronLogger({ app, getRootDir }) {
  const electronLogMaxBytes = parseLogMaxBytes(
    process.env.ASTRBOT_ELECTRON_LOG_MAX_MB,
    20,
  );
  const electronLogBackupCount = parseLogBackupCount(
    process.env.ASTRBOT_ELECTRON_LOG_BACKUP_COUNT,
    3,
  );

  function getElectronLogPath() {
    const rootDir =
      process.env.ASTRBOT_ROOT ||
      (typeof getRootDir === 'function' ? getRootDir() : null) ||
      app.getPath('userData');
    return path.join(rootDir, 'logs', 'electron.log');
  }

  function logElectron(message) {
    const logPath = getElectronLogPath();
    const line = `[${new Date().toISOString()}] ${message}\n`;
    appendRotatingLog(logPath, line, {
      maxBytes: electronLogMaxBytes,
      backupCount: electronLogBackupCount,
    });
  }

  return {
    getElectronLogPath,
    logElectron,
  };
}

module.exports = {
  createElectronLogger,
};
