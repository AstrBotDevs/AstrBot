'use strict';

const fs = require('fs');
const path = require('path');
const { ensureDir } = require('./common');

function createElectronLogger({ app, getRootDir }) {
  function getElectronLogPath() {
    const rootDir =
      process.env.ASTRBOT_ROOT ||
      (typeof getRootDir === 'function' ? getRootDir() : null) ||
      app.getPath('userData');
    return path.join(rootDir, 'logs', 'electron.log');
  }

  function logElectron(message) {
    const logPath = getElectronLogPath();
    ensureDir(path.dirname(logPath));
    const line = `[${new Date().toISOString()}] ${message}\n`;
    try {
      fs.appendFileSync(logPath, line, 'utf8');
    } catch {}
  }

  return {
    getElectronLogPath,
    logElectron,
  };
}

module.exports = {
  createElectronLogger,
};
