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
} = require('electron');
const { spawn } = require('child_process');

const isMac = process.platform === 'darwin';
const backendUrl = normalizeUrl(
  process.env.ASTRBOT_BACKEND_URL || 'http://127.0.0.1:6185/',
);
const backendAutoStart = process.env.ASTRBOT_BACKEND_AUTO_START !== '0';
const backendTimeoutMs = Number.parseInt(
  process.env.ASTRBOT_BACKEND_TIMEOUT_MS || '20000',
  10,
);

let mainWindow = null;
let tray = null;
let isQuitting = false;
let backendProcess = null;
let backendConfig = null;

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

function normalizeUrl(value) {
  try {
    const url = new URL(value);
    if (!url.pathname.endsWith('/')) {
      url.pathname += '/';
    }
    return url.toString();
  } catch {
    return 'http://127.0.0.1:6185/';
  }
}

function shellQuote(value) {
  if (!value) {
    return '';
  }
  if (process.platform === 'win32') {
    return `"${value.replace(/"/g, '\\"')}"`;
  }
  return `'${value.replace(/'/g, "'\\''")}'`;
}

function ensureDir(value) {
  if (!value) {
    return;
  }
  if (fs.existsSync(value)) {
    return;
  }
  fs.mkdirSync(value, { recursive: true });
}

function getPackagedBackendPath() {
  if (!app.isPackaged) {
    return null;
  }
  const filename =
    process.platform === 'win32' ? 'astrbot-backend.exe' : 'astrbot-backend';
  const candidate = path.join(process.resourcesPath, 'backend', filename);
  return fs.existsSync(candidate) ? candidate : null;
}

function resolveWebuiDir() {
  if (process.env.ASTRBOT_WEBUI_DIR) {
    return process.env.ASTRBOT_WEBUI_DIR;
  }
  if (!app.isPackaged) {
    return null;
  }
  const candidate = path.join(process.resourcesPath, 'webui');
  const indexPath = path.join(candidate, 'index.html');
  return fs.existsSync(indexPath) ? candidate : null;
}

function resolveBackendRoot() {
  if (!app.isPackaged) {
    return null;
  }
  return app.getPath('userData');
}

function resolveBackendCwd() {
  if (!app.isPackaged) {
    return path.resolve(__dirname, '..');
  }
  return app.getPath('userData');
}

function buildDefaultBackendCmd(webuiDir) {
  if (app.isPackaged) {
    const packagedBackend = getPackagedBackendPath();
    if (!packagedBackend) {
      return null;
    }
    let cmd = shellQuote(packagedBackend);
    if (webuiDir) {
      cmd += ` --webui-dir ${shellQuote(webuiDir)}`;
    }
    return cmd;
  }
  let cmd = 'uv run main.py';
  if (webuiDir) {
    cmd += ` --webui-dir ${shellQuote(webuiDir)}`;
  }
  return cmd;
}

function resolveBackendConfig() {
  const webuiDir = resolveWebuiDir();
  const cmd =
    process.env.ASTRBOT_BACKEND_CMD || buildDefaultBackendCmd(webuiDir);
  const cwd = process.env.ASTRBOT_BACKEND_CWD || resolveBackendCwd();
  const rootDir = process.env.ASTRBOT_ROOT || resolveBackendRoot();
  ensureDir(cwd);
  if (rootDir) {
    ensureDir(rootDir);
  }
  return {
    cmd,
    cwd,
    webuiDir,
    rootDir,
  };
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function pingBackend(timeoutMs = 800) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(backendUrl, { signal: controller.signal });
    return response.ok;
  } catch {
    return false;
  } finally {
    clearTimeout(timeout);
  }
}

async function waitForBackend(maxWaitMs = 20000) {
  const start = Date.now();
  while (Date.now() - start < maxWaitMs) {
    if (await pingBackend()) {
      return true;
    }
    await delay(600);
  }
  return false;
}

function startBackend() {
  if (backendProcess) {
    return;
  }
  if (!backendConfig) {
    backendConfig = resolveBackendConfig();
  }
  if (!backendConfig.cmd) {
    return;
  }
  const env = {
    ...process.env,
    PYTHONUNBUFFERED: '1',
  };
  if (backendConfig.rootDir) {
    env.ASTRBOT_ROOT = backendConfig.rootDir;
  }
  backendProcess = spawn(backendConfig.cmd, {
    cwd: backendConfig.cwd,
    env,
    shell: true,
    stdio: 'ignore',
    windowsHide: true,
  });

  backendProcess.on('exit', () => {
    backendProcess = null;
  });
}

function stopBackend() {
  if (!backendProcess || backendProcess.killed) {
    return;
  }
  if (process.platform === 'win32' && backendProcess.pid) {
    spawn('taskkill', ['/pid', `${backendProcess.pid}`, '/t', '/f'], {
      stdio: 'ignore',
      windowsHide: true,
    });
  } else {
    backendProcess.kill('SIGTERM');
  }
  backendProcess = null;
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 980,
    minHeight: 680,
    show: false,
    autoHideMenuBar: !isMac,
    icon: getAssetPath('icon.png'),
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      preload: path.join(__dirname, 'preload.js'),
    },
  });

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
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

  return mainWindow;
}

function updateTrayMenu() {
  if (!tray || !mainWindow) {
    return;
  }
  const isVisible = mainWindow.isVisible();
  const contextMenu = Menu.buildFromTemplate([
    {
      label: isVisible ? 'Hide AstrBot' : 'Show AstrBot',
      click: () => toggleWindow(),
    },
    {
      label: 'Reload',
      click: () => {
        if (mainWindow) {
          mainWindow.reload();
        }
      },
    },
    { type: 'separator' },
    {
      label: 'Quit',
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

async function ensureBackend() {
  if (!backendConfig) {
    backendConfig = resolveBackendConfig();
  }
  const running = await pingBackend();
  if (running) {
    return true;
  }
  if (!backendAutoStart || !backendConfig.cmd) {
    return false;
  }
  startBackend();
  return waitForBackend(backendTimeoutMs);
}

app.setAppUserModelId('com.astrbot.desktop');

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    showWindow();
  });
}

app.on('before-quit', () => {
  isQuitting = true;
  stopBackend();
});

app.whenReady().then(async () => {
  if (isMac && app.dock) {
    const dockIcon = getAssetPath('icon.png');
    if (fs.existsSync(dockIcon)) {
      app.dock.setIcon(dockIcon);
    }
  }
  const ready = await ensureBackend();

  if (!ready) {
    await dialog.showMessageBox({
      type: 'error',
      title: 'AstrBot startup failed',
      message: 'AstrBot backend is not reachable.',
      detail:
        'Please start the backend at http://127.0.0.1:6185 and relaunch AstrBot.',
    });
    isQuitting = true;
    app.quit();
    return;
  }

  createWindow();
  createTray();

  try {
    await mainWindow.loadURL(backendUrl);
  } catch (error) {
    dialog.showMessageBox({
      type: 'error',
      title: 'Failed to load AstrBot',
      message: 'Unable to load the AstrBot dashboard.',
      detail: error instanceof Error ? error.message : String(error),
    });
  }
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
