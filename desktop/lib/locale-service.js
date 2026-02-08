'use strict';

const fs = require('fs');
const path = require('path');
const { delay, ensureDir } = require('./common');

const LOCALE_STORAGE_KEY = 'astrbot-locale';
const SUPPORTED_STARTUP_LOCALES = new Set(['zh-CN', 'en-US']);

function normalizeLocale(value) {
  if (!value) {
    return null;
  }
  const raw = String(value).trim();
  if (!raw) {
    return null;
  }
  if (SUPPORTED_STARTUP_LOCALES.has(raw)) {
    return raw;
  }
  const lower = raw.toLowerCase();
  if (lower.startsWith('zh')) {
    return 'zh-CN';
  }
  if (lower.startsWith('en')) {
    return 'en-US';
  }
  return null;
}

function getStartupTexts(locale) {
  if (locale === 'zh-CN') {
    return {
      title: 'AstrBot 正在启动',
      message: '界面很快就会加载完成。',
    };
  }
  return {
    title: 'AstrBot is starting',
    message: 'The dashboard will be ready in a moment.',
  };
}

function getShellTexts(locale) {
  if (locale === 'zh-CN') {
    return {
      trayHide: '隐藏 AstrBot',
      trayShow: '显示 AstrBot',
      trayReload: '重新加载',
      trayQuit: '退出',
      startupFailTitle: 'AstrBot 启动失败',
      startupFailMessage: 'AstrBot 后端不可达。',
      startupFailReasonPrefix: '原因',
      startupFailAction:
        '请先启动 http://127.0.0.1:6185 的后端服务，然后重新打开 AstrBot。',
      startupFailLogPrefix: '后端日志',
      dashboardFailTitle: 'AstrBot 加载失败',
      dashboardFailMessage: '无法加载 AstrBot 控制台页面。',
    };
  }
  return {
    trayHide: 'Hide AstrBot',
    trayShow: 'Show AstrBot',
    trayReload: 'Reload',
    trayQuit: 'Quit',
    startupFailTitle: 'AstrBot startup failed',
    startupFailMessage: 'AstrBot backend is not reachable.',
    startupFailReasonPrefix: 'Reason',
    startupFailAction:
      'Please start the backend at http://127.0.0.1:6185 and relaunch AstrBot.',
    startupFailLogPrefix: 'Backend log',
    dashboardFailTitle: 'Failed to load AstrBot',
    dashboardFailMessage: 'Unable to load the AstrBot dashboard.',
  };
}

function createLocaleService({ app, getRootDir }) {
  function resolveStateRoot() {
    const callbackRoot = (() => {
      try {
        return getRootDir ? getRootDir() : null;
      } catch {
        return null;
      }
    })();
    return process.env.ASTRBOT_ROOT || callbackRoot || app.getPath('userData');
  }

  function getDesktopStatePath() {
    return path.join(resolveStateRoot(), 'data', 'desktop_state.json');
  }

  function readCachedLocale() {
    const statePath = getDesktopStatePath();
    try {
      const raw = fs.readFileSync(statePath, 'utf8');
      const parsed = JSON.parse(raw);
      return normalizeLocale(parsed?.locale);
    } catch {
      return null;
    }
  }

  function writeCachedLocale(locale) {
    const normalized = normalizeLocale(locale);
    if (!normalized) {
      return;
    }
    const statePath = getDesktopStatePath();
    ensureDir(path.dirname(statePath));
    try {
      fs.writeFileSync(
        statePath,
        `${JSON.stringify({ locale: normalized }, null, 2)}\n`,
        'utf8',
      );
    } catch {}
  }

  function resolveStartupLocale() {
    const cached = readCachedLocale();
    if (cached) {
      return cached;
    }
    return normalizeLocale(app.getLocale()) || 'zh-CN';
  }

  async function persistLocaleFromDashboard(
    mainWindow,
    backendUrl,
    timeoutMs = 1200,
  ) {
    if (!mainWindow || mainWindow.isDestroyed()) {
      return;
    }
    const currentUrl = mainWindow.webContents.getURL();
    if (!currentUrl || !currentUrl.startsWith(backendUrl)) {
      return;
    }
    try {
      const localeRaw = await Promise.race([
        mainWindow.webContents.executeJavaScript(
          `(() => {
            try {
              return window.localStorage.getItem('${LOCALE_STORAGE_KEY}') || '';
            } catch {
              return '';
            }
          })();`,
          true,
        ),
        delay(timeoutMs).then(() => null),
      ]);
      const locale = normalizeLocale(localeRaw);
      if (locale) {
        writeCachedLocale(locale);
      }
    } catch {}
  }

  return {
    getShellTexts,
    getStartupTexts,
    persistLocaleFromDashboard,
    resolveStartupLocale,
  };
}

module.exports = {
  createLocaleService,
  normalizeLocale,
};
