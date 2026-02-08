'use strict';

const fs = require('fs');
const os = require('os');
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
const { spawn, spawnSync } = require('child_process');

const isMac = process.platform === 'darwin';
const backendUrl = normalizeUrl(
  process.env.ASTRBOT_BACKEND_URL || 'http://127.0.0.1:6185/',
);
const backendAutoStart = process.env.ASTRBOT_BACKEND_AUTO_START !== '0';
const defaultBackendTimeoutMs = app.isPackaged ? 0 : 20000;
const backendTimeoutMsParsed = Number.parseInt(
  process.env.ASTRBOT_BACKEND_TIMEOUT_MS || `${defaultBackendTimeoutMs}`,
  10,
);
const backendTimeoutMs =
  Number.isFinite(backendTimeoutMsParsed) && backendTimeoutMsParsed >= 0
    ? backendTimeoutMsParsed
    : defaultBackendTimeoutMs;
const dashboardTimeoutMs = Number.parseInt(
  process.env.ASTRBOT_DASHBOARD_TIMEOUT_MS || '20000',
  10,
);
const LOCALE_STORAGE_KEY = 'astrbot-locale';
const SUPPORTED_STARTUP_LOCALES = new Set(['zh-CN', 'en-US']);

let mainWindow = null;
let tray = null;
let isQuitting = false;
let quitInProgress = false;
let backendProcess = null;
let backendConfig = null;
let backendLogFd = null;
let backendLastExitReason = null;
let backendStartupFailureReason = null;
let backendSpawning = false;
let backendRestarting = false;

app.commandLine.appendSwitch('disable-http-cache');

function getElectronLogPath() {
  const rootDir =
    process.env.ASTRBOT_ROOT || backendConfig?.rootDir || app.getPath('userData');
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

function ensureDir(value) {
  if (!value) {
    return;
  }
  if (fs.existsSync(value)) {
    return;
  }
  fs.mkdirSync(value, { recursive: true });
}

function closeBackendLogFd() {
  if (backendLogFd === null) {
    return;
  }
  try {
    fs.closeSync(backendLogFd);
  } catch {}
  backendLogFd = null;
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
  return path.join(os.homedir(), '.astrbot');
}

function resolveBackendCwd() {
  if (!app.isPackaged) {
    return path.resolve(__dirname, '..');
  }
  return resolveBackendRoot();
}

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

function getDesktopStatePath() {
  const rootDir =
    process.env.ASTRBOT_ROOT ||
    backendConfig?.rootDir ||
    resolveBackendRoot() ||
    app.getPath('userData');
  return path.join(rootDir, 'data', 'desktop_state.json');
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

function buildDefaultBackendLaunch(webuiDir) {
  if (app.isPackaged) {
    const packagedBackend = getPackagedBackendPath();
    if (!packagedBackend) {
      return null;
    }
    const args = [];
    if (webuiDir) {
      args.push('--webui-dir', webuiDir);
    }
    return {
      cmd: packagedBackend,
      args,
      shell: false,
    };
  }
  const args = ['run', 'main.py'];
  if (webuiDir) {
    args.push('--webui-dir', webuiDir);
  }
  return {
    cmd: 'uv',
    args,
    shell: process.platform === 'win32',
  };
}

function resolveBackendConfig() {
  const webuiDir = resolveWebuiDir();
  const customCmd = process.env.ASTRBOT_BACKEND_CMD;
  const launch = customCmd
    ? {
        cmd: customCmd,
        args: [],
        shell: true,
      }
    : buildDefaultBackendLaunch(webuiDir);
  const cwd = process.env.ASTRBOT_BACKEND_CWD || resolveBackendCwd();
  const rootDir = process.env.ASTRBOT_ROOT || resolveBackendRoot();
  ensureDir(cwd);
  if (rootDir) {
    ensureDir(rootDir);
  }
  return {
    cmd: launch ? launch.cmd : null,
    args: launch ? launch.args : [],
    shell: launch ? launch.shell : true,
    cwd,
    webuiDir,
    rootDir,
  };
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function waitForProcessExit(child, timeoutMs = 5000) {
  if (!child) {
    return Promise.resolve('missing');
  }
  if (child.exitCode !== null || child.signalCode !== null) {
    return Promise.resolve('exited');
  }
  return new Promise((resolve) => {
    let settled = false;
    const finish = (reason) => {
      if (settled) {
        return;
      }
      settled = true;
      clearTimeout(timeout);
      resolve(reason);
    };
    const timeout = setTimeout(() => finish('timeout'), timeoutMs);
    child.once('exit', () => finish('exit'));
    child.once('error', () => finish('error'));
  });
}

async function pingBackend(timeoutMs = 800) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    await fetch(backendUrl, {
      signal: controller.signal,
      redirect: 'manual',
    });
    return true;
  } catch {
    return false;
  } finally {
    clearTimeout(timeout);
  }
}

async function waitForBackend(maxWaitMs = 0, failOnProcessExit = false) {
  const start = Date.now();
  while (true) {
    if (await pingBackend()) {
      return { ok: true, reason: null };
    }
    if (failOnProcessExit && !backendProcess) {
      return {
        ok: false,
        reason:
          backendLastExitReason ||
          'Backend process exited before becoming reachable.',
      };
    }
    if (maxWaitMs > 0 && Date.now() - start >= maxWaitMs) {
      return {
        ok: false,
        reason: `Timed out after ${maxWaitMs}ms waiting for backend startup.`,
      };
    }
    await delay(600);
  }
}

function canManageBackend() {
  if (!backendConfig) {
    backendConfig = resolveBackendConfig();
  }
  return Boolean(backendConfig?.cmd);
}

async function startBackendAndWait(maxWaitMs = backendTimeoutMs) {
  if (!canManageBackend()) {
    return {
      ok: false,
      reason: 'Backend command is not configured.',
    };
  }
  backendSpawning = true;
  try {
    startBackend();
    return await waitForBackend(maxWaitMs, true);
  } finally {
    backendSpawning = false;
  }
}

function startBackend() {
  if (isQuitting || quitInProgress) {
    logElectron('Skip backend start because app is quitting.');
    return;
  }
  if (backendProcess) {
    return;
  }
  if (!backendConfig) {
    backendConfig = resolveBackendConfig();
  }
  if (!backendConfig.cmd) {
    return;
  }
  backendLastExitReason = null;
  const env = {
    ...process.env,
    PYTHONUNBUFFERED: '1',
  };
  if (backendConfig.rootDir) {
    env.ASTRBOT_ROOT = backendConfig.rootDir;
    const logsDir = path.join(backendConfig.rootDir, 'logs');
    ensureDir(logsDir);
    const logPath = path.join(logsDir, 'backend.log');
    try {
      backendLogFd = fs.openSync(logPath, 'a');
    } catch {
      backendLogFd = null;
    }
  }
  backendProcess = spawn(backendConfig.cmd, backendConfig.args || [], {
    cwd: backendConfig.cwd,
    env,
    shell: backendConfig.shell,
    stdio:
      backendLogFd === null
        ? 'ignore'
        : ['ignore', backendLogFd, backendLogFd],
    windowsHide: true,
  });

  if (backendLogFd !== null) {
    const launchLine = [backendConfig.cmd, ...(backendConfig.args || [])]
      .map((item) => JSON.stringify(item))
      .join(' ');
    try {
      fs.writeSync(
        backendLogFd,
        `[${new Date().toISOString()}] [Electron] Start backend ${launchLine}\n`,
      );
    } catch {}
  }

  backendProcess.on('error', (error) => {
    backendLastExitReason =
      error instanceof Error ? error.message : String(error);
    if (backendLogFd !== null) {
      try {
        fs.writeSync(
          backendLogFd,
          `[${new Date().toISOString()}] [Electron] Backend spawn error: ${
            error instanceof Error ? error.message : String(error)
          }\n`,
        );
      } catch {}
    }
    closeBackendLogFd();
    backendProcess = null;
  });

  backendProcess.on('exit', (code, signal) => {
    backendLastExitReason = `Backend process exited (code=${code ?? 'null'}, signal=${signal ?? 'null'}).`;
    closeBackendLogFd();
    backendProcess = null;
  });
}

async function stopBackend() {
  if (!backendProcess) {
    return;
  }
  const processToStop = backendProcess;
  const pid = processToStop.pid;
  backendProcess = null;
  logElectron(`Stop backend requested pid=${pid ?? 'unknown'}`);

  if (process.platform === 'win32' && pid) {
    try {
      const result = spawnSync('taskkill', ['/pid', `${pid}`, '/t', '/f'], {
        stdio: 'ignore',
        windowsHide: true,
      });
      if (result.status !== 0) {
        logElectron(
          `taskkill failed pid=${pid} status=${result.status} signal=${result.signal ?? 'null'}`,
        );
      } else {
        logElectron(`taskkill completed pid=${pid}`);
      }
    } catch (error) {
      logElectron(
        `taskkill threw for pid=${pid}: ${
          error instanceof Error ? error.message : String(error)
        }`,
      );
    }
    await waitForProcessExit(processToStop, 5000);
  } else {
    if (!processToStop.killed) {
      try {
        processToStop.kill('SIGTERM');
      } catch (error) {
        logElectron(
          `SIGTERM failed for pid=${pid ?? 'unknown'}: ${
            error instanceof Error ? error.message : String(error)
          }`,
        );
      }
    }
    const exitResult = await waitForProcessExit(processToStop, 5000);
    if (exitResult === 'timeout' && !processToStop.killed) {
      try {
        processToStop.kill('SIGKILL');
      } catch {}
      await waitForProcessExit(processToStop, 1500);
    }
  }
  closeBackendLogFd();
}

async function loadDashboard(maxWaitMs = 20000) {
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

async function persistLocaleFromDashboard(timeoutMs = 1200) {
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

async function loadStartupScreen() {
  if (!mainWindow) {
    return false;
  }
  const startupLocale = resolveStartupLocale();
  const startupTexts = getStartupTexts(startupLocale);
  let iconUrl = '';
  try {
    const iconBuffer = fs.readFileSync(getAssetPath('icon-no-shadow.svg'));
    iconUrl = `data:image/svg+xml;base64,${iconBuffer.toString('base64')}`;
  } catch {}
  const html = `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>AstrBot</title>
  <style>
    :root {
      color-scheme: light dark;
      --primary: #3c96ca;
      --bg: #f9fafc;
      --surface: #ffffff;
      --text: #1b1c1d;
      --muted: #556170;
      --border: #eeeeee;
    }
    body {
      margin: 0;
      min-height: 100vh;
      font-family: "Poppins", "Segoe UI", -apple-system, BlinkMacSystemFont, sans-serif;
      display: grid;
      place-items: center;
      background: var(--bg);
      color: var(--text);
      transition: background-color 0.2s ease, color 0.2s ease;
    }
    .card {
      text-align: center;
      padding: 28px 30px 24px;
      border-radius: 14px;
      background: var(--surface);
      border: 1px solid var(--border);
      width: min(360px, calc(100vw - 48px));
    }
    .logo {
      width: 64px;
      height: 64px;
      display: block;
      margin: 0 auto 12px;
    }
    .spinner {
      width: 32px;
      height: 32px;
      margin: 0 auto 14px;
      border: 3px solid rgba(60, 150, 202, 0.22);
      border-top-color: var(--primary);
      border-radius: 50%;
      animation: spin 0.9s linear infinite;
    }
    h1 {
      margin: 0 0 10px;
      font-size: 19px;
      font-weight: 700;
      letter-spacing: 0.01em;
    }
    p {
      margin: 0;
      line-height: 1.55;
      color: var(--muted);
      font-size: 14px;
    }
    @media (prefers-color-scheme: dark) {
      :root {
        --primary: #1677ff;
        --bg: #1d1d1d;
        --surface: #1f1f1f;
        --text: #ffffff;
        --muted: #c8c8cc;
        --border: #333333;
      }
      .card {
        box-shadow: 0 18px 42px rgba(0, 0, 0, 0.45);
      }
    }
    @keyframes spin {
      to {
        transform: rotate(360deg);
      }
    }
  </style>
</head>
<body>
  <div class="card">
    ${
      iconUrl
        ? `<img class="logo" src="${iconUrl}" alt="AstrBot logo" />`
        : '<div class="logo" aria-hidden="true"></div>'
    }
    <div class="spinner" aria-hidden="true"></div>
    <h1>${startupTexts.title}</h1>
    <p>${startupTexts.message}</p>
  </div>
</body>
</html>`;
  const startupUrl = `data:text/html;charset=utf-8,${encodeURIComponent(html)}`;
  await mainWindow.loadURL(startupUrl);
  return true;
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
    if (currentUrl.startsWith(backendUrl)) {
      void persistLocaleFromDashboard();
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
  backendStartupFailureReason = null;
  if (!backendConfig) {
    backendConfig = resolveBackendConfig();
  }
  const running = await pingBackend();
  if (running) {
    return true;
  }
  if (!backendAutoStart || !backendConfig.cmd) {
    backendStartupFailureReason =
      'Backend auto-start is disabled or backend command is not configured.';
    return false;
  }
  const waitResult = await startBackendAndWait(backendTimeoutMs);
  if (!waitResult.ok) {
    backendStartupFailureReason = waitResult.reason;
    return false;
  }
  return true;
}

ipcMain.handle('astrbot-desktop:is-electron-runtime', async () => true);

ipcMain.handle('astrbot-desktop:get-backend-state', async () => {
  const running = await pingBackend();
  return {
    running,
    spawning: backendSpawning,
    restarting: backendRestarting,
    canManage: canManageBackend(),
  };
});

ipcMain.handle('astrbot-desktop:restart-backend', async () => {
  if (!canManageBackend()) {
    return {
      ok: false,
      reason: 'Backend command is not configured.',
    };
  }
  if (backendSpawning || backendRestarting) {
    return {
      ok: false,
      reason: 'Backend action already in progress.',
    };
  }

  backendRestarting = true;
  try {
    await stopBackend();
    const startResult = await startBackendAndWait(backendTimeoutMs);
    if (!startResult.ok) {
      return {
        ok: false,
        reason: startResult.reason || 'Failed to restart backend.',
      };
    }
    return {
      ok: true,
      reason: null,
    };
  } catch (error) {
    return {
      ok: false,
      reason: error instanceof Error ? error.message : String(error),
    };
  } finally {
    backendRestarting = false;
  }
});

ipcMain.handle('astrbot-desktop:stop-backend', async () => {
  if (!canManageBackend()) {
    return {
      ok: false,
      reason: 'Backend command is not configured.',
    };
  }
  if (backendSpawning || backendRestarting) {
    return {
      ok: false,
      reason: 'Backend action already in progress.',
    };
  }

  try {
    if (!backendProcess) {
      const running = await pingBackend();
      if (running) {
        return {
          ok: false,
          reason: 'Backend is running but not managed by Electron.',
        };
      }
      return {
        ok: true,
        reason: null,
      };
    }
    await stopBackend();
    const running = await pingBackend();
    if (running) {
      return {
        ok: false,
        reason: 'Backend is still reachable after stop request.',
      };
    }
    return {
      ok: true,
      reason: null,
    };
  } catch (error) {
    return {
      ok: false,
      reason: error instanceof Error ? error.message : String(error),
    };
  }
});

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
  persistLocaleFromDashboard()
    .catch(() => {})
    .then(() =>
      stopBackend().catch((error) => {
        logElectron(
          `stopBackend failed: ${
            error instanceof Error ? error.message : String(error)
          }`,
        );
      }),
    )
    .finally(() => {
      logElectron(
        'Backend stop finished, exiting app.',
      );
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
  createWindow();
  createTray();
  try {
    await loadStartupScreen();
  } catch (error) {
    logElectron(
      `failed to load startup screen: ${
        error instanceof Error ? error.message : String(error)
      }`,
    );
  }
  showWindow();

  const ready = await ensureBackend();
  if (isQuitting) {
    return;
  }

  if (!ready) {
    const backendLogPath = backendConfig?.rootDir
      ? path.join(backendConfig.rootDir, 'logs', 'backend.log')
      : null;
    const detailLines = [];
    if (backendStartupFailureReason) {
      detailLines.push(`Reason: ${backendStartupFailureReason}`);
    }
    detailLines.push(
      'Please start the backend at http://127.0.0.1:6185 and relaunch AstrBot.',
    );
    if (backendLogPath) {
      detailLines.push(`Backend log: ${backendLogPath}`);
    }
    await dialog.showMessageBox({
      type: 'error',
      title: 'AstrBot startup failed',
      message: 'AstrBot backend is not reachable.',
      detail: detailLines.join('\n'),
    });
    isQuitting = true;
    app.quit();
    return;
  }

  try {
    await loadDashboard(dashboardTimeoutMs);
    showWindow();
  } catch (error) {
    await dialog.showMessageBox({
      type: 'error',
      title: 'Failed to load AstrBot',
      message: 'Unable to load the AstrBot dashboard.',
      detail: error instanceof Error ? error.message : String(error),
    });
    isQuitting = true;
    app.quit();
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
