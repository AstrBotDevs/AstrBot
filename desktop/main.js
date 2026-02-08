'use strict';

const fs = require('fs');
const path = require('path');
const {
  app,
  BrowserWindow,
  Menu,
  Tray,
  nativeImage,
  shell,
  dialog,
  ipcMain,
} = require('electron');

const { BackendManager } = require('./lib/backend-manager');
const { loadDashboard } = require('./lib/dashboard-loader');
const { createElectronLogger } = require('./lib/electron-logger');
const { createLocaleService } = require('./lib/locale-service');
const { loadStartupScreen } = require('./lib/startup-screen');

const isMac = process.platform === 'darwin';
const dashboardTimeoutMsParsed = Number.parseInt(
  process.env.ASTRBOT_DASHBOARD_TIMEOUT_MS || '20000',
  10,
);
const dashboardTimeoutMs = Number.isFinite(dashboardTimeoutMsParsed)
  ? dashboardTimeoutMsParsed
  : 20000;

let mainWindow = null;
let tray = null;
let isQuitting = false;
let quitInProgress = false;
let backendManager = null;

app.commandLine.appendSwitch('disable-http-cache');

const { logElectron } = createElectronLogger({
  app,
  getRootDir: () => (backendManager ? backendManager.getRootDir() : null),
});

backendManager = new BackendManager({
  app,
  baseDir: __dirname,
  log: logElectron,
  shouldSkipStart: () => isQuitting || quitInProgress,
});

const localeService = createLocaleService({
  app,
  getRootDir: () => backendManager.getRootDir(),
});

function getAssetPath(filename) {
  if (app.isPackaged) {
    const packaged = path.join(process.resourcesPath, 'assets', filename);
    if (fs.existsSync(packaged)) {
      return packaged;
    }
  }
  return path.join(__dirname, 'assets', filename);
}

function loadImageSafe(imagePath) {
  try {
    const image = nativeImage.createFromPath(imagePath);
    if (!image.isEmpty()) {
      return image;
    }
  } catch {}
  return nativeImage.createEmpty();
}

function showWindow() {
  if (!mainWindow) {
    return;
  }
  mainWindow.show();
  mainWindow.focus();
  updateTrayMenu();
}

function toggleWindow() {
  if (!mainWindow) {
    return;
  }
  if (mainWindow.isVisible()) {
    mainWindow.hide();
  } else {
    mainWindow.show();
    mainWindow.focus();
  }
  updateTrayMenu();
}

function updateTrayMenu() {
  if (!tray || !mainWindow) {
    return;
  }
  const shellTexts = localeService.getShellTexts(
    localeService.resolveStartupLocale(),
  );
  const isVisible = mainWindow.isVisible();
  const contextMenu = Menu.buildFromTemplate([
    {
      label: isVisible ? shellTexts.trayHide : shellTexts.trayShow,
      click: () => toggleWindow(),
    },
    {
      label: shellTexts.trayReload,
      click: () => {
        if (mainWindow) {
          mainWindow.reload();
        }
      },
    },
    { type: 'separator' },
    {
      label: shellTexts.trayQuit,
      click: () => app.quit(),
    },
  ]);
  tray.setContextMenu(contextMenu);
}

function createTray() {
  const traySize = isMac ? 18 : 16;
  const trayPath = getAssetPath('tray.png');
  let trayImage = loadImageSafe(trayPath);
  if (trayImage.isEmpty()) {
    trayImage = loadImageSafe(getAssetPath('icon.png'));
  }
  if (!trayImage.isEmpty()) {
    trayImage = trayImage.resize({ width: traySize, height: traySize });
    if (isMac) {
      trayImage.setTemplateImage(true);
    }
    tray = new Tray(trayImage);
  } else {
    tray = new Tray(nativeImage.createEmpty());
  }
  tray.setToolTip('AstrBot');
  tray.on('click', () => toggleWindow());
  updateTrayMenu();
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 980,
    minHeight: 680,
    show: false,
    backgroundColor: '#f9fafc',
    autoHideMenuBar: !isMac,
    icon: getAssetPath('icon.png'),
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      preload: path.join(__dirname, 'preload.js'),
    },
  });

  mainWindow.on('close', (event) => {
    if (isQuitting) {
      return;
    }
    event.preventDefault();
    mainWindow.hide();
  });

  mainWindow.on('minimize', (event) => {
    event.preventDefault();
    mainWindow.hide();
  });

  mainWindow.on('show', () => updateTrayMenu());
  mainWindow.on('hide', () => updateTrayMenu());

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });

  mainWindow.webContents.on(
    'did-fail-load',
    (_event, errorCode, errorDescription, validatedURL, isMainFrame) => {
      if (!isMainFrame) {
        return;
      }
      logElectron(
        `did-fail-load main-frame code=${errorCode} desc=${errorDescription} url=${validatedURL}`,
      );
    },
  );

  mainWindow.webContents.on('did-finish-load', () => {
    const currentUrl = mainWindow.webContents.getURL();
    logElectron(`did-finish-load url=${currentUrl}`);
    if (currentUrl.startsWith(backendManager.getBackendUrl())) {
      void localeService.persistLocaleFromDashboard(
        mainWindow,
        backendManager.getBackendUrl(),
      );
    }
  });

  mainWindow.webContents.on('render-process-gone', (_event, details) => {
    logElectron(
      `render-process-gone reason=${details.reason} exitCode=${details.exitCode}`,
    );
  });

  mainWindow.webContents.on(
    'console-message',
    (_event, level, message, line, sourceId) => {
      if (level >= 2) {
        logElectron(
          `renderer-console level=${level} source=${sourceId}:${line} message=${message}`,
        );
      }
    },
  );

  return mainWindow;
}

function registerIpcHandlers() {
  ipcMain.handle('astrbot-desktop:is-electron-runtime', async () => true);

  ipcMain.handle('astrbot-desktop:get-backend-state', async () => {
    return backendManager.getState();
  });

  ipcMain.handle('astrbot-desktop:restart-backend', async () => {
    return backendManager.restartBackend();
  });

  ipcMain.handle('astrbot-desktop:stop-backend', async () => {
    return backendManager.stopBackendForIpc();
  });
}

async function startDesktopFlow() {
  createWindow();
  createTray();

  try {
    const startupTexts = localeService.getStartupTexts(
      localeService.resolveStartupLocale(),
    );
    await loadStartupScreen(mainWindow, {
      getAssetPath,
      startupTexts,
    });
  } catch (error) {
    logElectron(
      `failed to load startup screen: ${
        error instanceof Error ? error.message : String(error)
      }`,
    );
  }

  showWindow();

  const ready = await backendManager.ensureBackend();
  if (isQuitting) {
    return;
  }

  if (!ready) {
    const shellTexts = localeService.getShellTexts(
      localeService.resolveStartupLocale(),
    );
    const backendLogPath = backendManager.getBackendLogPath();
    const detailLines = [];
    const startupFailureReason = backendManager.getStartupFailureReason();
    if (startupFailureReason) {
      detailLines.push(
        `${shellTexts.startupFailReasonPrefix}: ${startupFailureReason}`,
      );
    }
    detailLines.push(shellTexts.startupFailAction);
    if (backendLogPath) {
      detailLines.push(`${shellTexts.startupFailLogPrefix}: ${backendLogPath}`);
    }

    await dialog.showMessageBox({
      type: 'error',
      title: shellTexts.startupFailTitle,
      message: shellTexts.startupFailMessage,
      detail: detailLines.join('\n'),
    });
    isQuitting = true;
    app.quit();
    return;
  }

  try {
    await loadDashboard(
      mainWindow,
      backendManager.getBackendUrl(),
      dashboardTimeoutMs,
    );
    showWindow();
  } catch (error) {
    const shellTexts = localeService.getShellTexts(
      localeService.resolveStartupLocale(),
    );
    await dialog.showMessageBox({
      type: 'error',
      title: shellTexts.dashboardFailTitle,
      message: shellTexts.dashboardFailMessage,
      detail: error instanceof Error ? error.message : String(error),
    });
    isQuitting = true;
    app.quit();
  }
}

registerIpcHandlers();

app.setAppUserModelId('com.astrbot.desktop');

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    showWindow();
  });
}

app.on('before-quit', (event) => {
  if (quitInProgress) {
    event.preventDefault();
    return;
  }
  event.preventDefault();
  quitInProgress = true;
  isQuitting = true;
  logElectron('before-quit received, stopping backend.');

  localeService
    .persistLocaleFromDashboard(mainWindow, backendManager.getBackendUrl())
    .catch(() => {})
    .then(() =>
      backendManager.stopManagedBackend().catch((error) => {
        logElectron(
          `stopBackend failed: ${
            error instanceof Error ? error.message : String(error)
          }`,
        );
      }),
    )
    .finally(() => {
      logElectron('Backend stop finished, exiting app.');
      app.exit(0);
    });
});

app.whenReady().then(async () => {
  if (isMac && app.dock) {
    const dockIcon = getAssetPath('icon.png');
    if (fs.existsSync(dockIcon)) {
      app.dock.setIcon(dockIcon);
    }
  }
  await startDesktopFlow();
});

app.on('activate', () => {
  if (mainWindow) {
    showWindow();
  }
});

app.on('window-all-closed', () => {
  if (!isMac) {
    app.quit();
  }
});
