'use strict';

const { delay } = require('./common');

async function loadDashboard(mainWindow, backendUrl, maxWaitMs = 20000) {
  if (!mainWindow) {
    return false;
  }
  const loadUrl = new URL(backendUrl);
  loadUrl.searchParams.set('_electron_ts', `${Date.now()}`);
  const start = Date.now();
  let lastError = null;
  while (maxWaitMs <= 0 || Date.now() - start < maxWaitMs) {
    try {
      await mainWindow.loadURL(loadUrl.toString());
      return true;
    } catch (error) {
      lastError = error;
      await delay(600);
    }
  }
  if (lastError) {
    throw lastError;
  }
  throw new Error(`Timed out loading ${backendUrl}`);
}

module.exports = {
  loadDashboard,
};
