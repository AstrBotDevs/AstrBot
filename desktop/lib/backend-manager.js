'use strict';

const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawn, spawnSync } = require('child_process');
const { BufferedRotatingLogger } = require('./buffered-rotating-logger');
const { resolvePackagedBackendState } = require('./packaged-backend-config');
const { shouldKillUnmanagedBackendProcess } = require('./windows-backend-cleanup');
const {
  delay,
  ensureDir,
  formatLogTimestamp,
  normalizeUrl,
  parseLogBackupCount,
  parseLogMaxBytes,
  waitForProcessExit,
} = require('./common');

const PACKAGED_BACKEND_TIMEOUT_FALLBACK_MS = 5 * 60 * 1000;
const GRACEFUL_RESTART_WAIT_FALLBACK_MS = 20 * 1000;
const BACKEND_LOG_FLUSH_INTERVAL_MS = 120;
const BACKEND_LOG_MAX_BUFFER_BYTES = 128 * 1024;

function parseBackendTimeoutMs(app) {
  const defaultTimeoutMs = app.isPackaged ? 0 : 20000;
  const parsed = Number.parseInt(
    process.env.ASTRBOT_BACKEND_TIMEOUT_MS || `${defaultTimeoutMs}`,
    10,
  );
  if (Number.isFinite(parsed) && parsed >= 0) {
    return parsed;
  }
  return defaultTimeoutMs;
}

class BackendManager {
  constructor({ app, baseDir, log, shouldSkipStart }) {
    this.app = app;
    this.baseDir = baseDir;
    this.log = typeof log === 'function' ? log : () => {};
    this.shouldSkipStart =
      typeof shouldSkipStart === 'function' ? shouldSkipStart : () => false;

    this.backendUrl = normalizeUrl(
      process.env.ASTRBOT_BACKEND_URL || 'http://127.0.0.1:6185/',
    );
    this.backendAutoStart = process.env.ASTRBOT_BACKEND_AUTO_START !== '0';
    this.backendTimeoutMs = parseBackendTimeoutMs(app);
    this.backendLogMaxBytes = parseLogMaxBytes(
      process.env.ASTRBOT_BACKEND_LOG_MAX_MB,
    );
    this.backendLogBackupCount = parseLogBackupCount(
      process.env.ASTRBOT_BACKEND_LOG_BACKUP_COUNT,
    );

    this.backendProcess = null;
    this.backendConfig = null;
    this.packagedBackendState = null;
    this.backendLogger = new BufferedRotatingLogger({
      logPath: null,
      maxBytes: this.backendLogMaxBytes,
      backupCount: this.backendLogBackupCount,
      flushIntervalMs: BACKEND_LOG_FLUSH_INTERVAL_MS,
      maxBufferBytes: BACKEND_LOG_MAX_BUFFER_BYTES,
    });
    this.backendLastExitReason = null;
    this.backendStartupFailureReason = null;
    this.backendSpawning = false;
    this.backendRestarting = false;
  }

  getBackendUrl() {
    return this.backendUrl;
  }

  getRootDir() {
    return (
      process.env.ASTRBOT_ROOT ||
      this.backendConfig?.rootDir ||
      this.resolveBackendRoot()
    );
  }

  getBackendLogPath() {
    const rootDir = this.getRootDir();
    if (!rootDir) {
      return null;
    }
    return path.join(rootDir, 'logs', 'backend.log');
  }

  getStartupFailureReason() {
    return this.backendStartupFailureReason;
  }

  resolveBackendRoot() {
    if (!this.app.isPackaged) {
      return null;
    }
    return path.join(os.homedir(), '.astrbot');
  }

  resolveBackendCwd() {
    if (!this.app.isPackaged) {
      return path.resolve(this.baseDir, '..');
    }
    return this.resolveBackendRoot();
  }

  resolveWebuiDir() {
    if (process.env.ASTRBOT_WEBUI_DIR) {
      return process.env.ASTRBOT_WEBUI_DIR;
    }
    if (!this.app.isPackaged) {
      return null;
    }
    const candidate = path.join(process.resourcesPath, 'webui');
    const indexPath = path.join(candidate, 'index.html');
    return fs.existsSync(indexPath) ? candidate : null;
  }

  getPackagedBackendState() {
    if (!this.app.isPackaged) {
      return null;
    }
    if (!this.packagedBackendState) {
      this.packagedBackendState = resolvePackagedBackendState(
        process.resourcesPath,
        (message) => this.log(message),
      );
    }
    return this.packagedBackendState;
  }

  buildDefaultBackendLaunch(webuiDir) {
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

  buildLaunchForPackagedBackend(packagedBackendState, webuiDir) {
    if (!packagedBackendState?.ok || !packagedBackendState.config) {
      return {
        launch: null,
        failureReason:
          packagedBackendState?.failureReason || 'Backend command is not configured.',
      };
    }

    const { runtimePythonPath, launchScriptPath } = packagedBackendState.config;
    const args = [launchScriptPath];
    if (webuiDir) {
      args.push('--webui-dir', webuiDir);
    }
    return {
      launch: { cmd: runtimePythonPath, args, shell: false },
      failureReason: null,
    };
  }

  buildBackendConfig() {
    const webuiDir = this.resolveWebuiDir();
    let launch = null;
    let failureReason = null;
    const customCmd = process.env.ASTRBOT_BACKEND_CMD;
    if (customCmd) {
      launch = { cmd: customCmd, args: [], shell: true };
    } else if (this.app.isPackaged) {
      ({ launch, failureReason } = this.buildLaunchForPackagedBackend(
        this.getPackagedBackendState(),
        webuiDir,
      ));
    } else {
      launch = this.buildDefaultBackendLaunch(webuiDir);
    }

    const cwd = process.env.ASTRBOT_BACKEND_CWD || this.resolveBackendCwd();
    const rootDir = process.env.ASTRBOT_ROOT || this.resolveBackendRoot();

    return {
      launch,
      cwd,
      rootDir,
      webuiDir,
      failureReason,
    };
  }

  resolveBackendConfig() {
    const { launch, cwd, rootDir, webuiDir, failureReason } =
      this.buildBackendConfig();
    ensureDir(cwd);
    if (rootDir) {
      ensureDir(rootDir);
    }
    if (failureReason) {
      this.log(failureReason);
    }
    this.backendConfig = {
      cmd: launch ? launch.cmd : null,
      args: launch ? launch.args : [],
      shell: launch ? launch.shell : true,
      cwd,
      webuiDir,
      rootDir,
      failureReason,
    };
    return this.backendConfig;
  }

  getBackendConfig() {
    if (!this.backendConfig) {
      return this.resolveBackendConfig();
    }
    return this.backendConfig;
  }

  getBackendPort() {
    try {
      const parsed = new URL(this.backendUrl);
      if (parsed.port) {
        const port = Number.parseInt(parsed.port, 10);
        return Number.isFinite(port) ? port : null;
      }
      return parsed.protocol === 'https:' ? 443 : 80;
    } catch {
      return null;
    }
  }

  canManageBackend() {
    return Boolean(this.getBackendConfig().cmd);
  }

  getBackendCommandUnavailableReason() {
    return this.getBackendConfig().failureReason || 'Backend command is not configured.';
  }

  async flushLogs() {
    await this.backendLogger.flush();
  }

  async pingBackend(timeoutMs = 800) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMs);
    try {
      await fetch(this.backendUrl, {
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

  getEffectiveWaitMs(maxWaitMs = 0) {
    if (maxWaitMs > 0) {
      return maxWaitMs;
    }
    if (this.app.isPackaged) {
      return PACKAGED_BACKEND_TIMEOUT_FALLBACK_MS;
    }
    return 0;
  }

  async requestBackendJson(pathname, options = {}) {
    const timeoutMs = options.timeoutMs || 2000;
    const method = options.method || 'GET';
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMs);
    const requestUrl = new URL(pathname, this.backendUrl);
    requestUrl.searchParams.set('_ts', `${Date.now()}`);

    const authToken =
      typeof options.authToken === 'string' && options.authToken
        ? options.authToken
        : null;

    try {
      const response = await fetch(requestUrl.toString(), {
        method,
        signal: controller.signal,
        redirect: 'manual',
        headers: {
          Accept: 'application/json',
          ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
          ...(options.headers || {}),
        },
      });
      if (!response.ok) {
        return { ok: false, data: null };
      }
      const data = await response.json();
      return { ok: true, data };
    } catch {
      return { ok: false, data: null };
    } finally {
      clearTimeout(timeout);
    }
  }

  async getBackendStartTime() {
    const result = await this.requestBackendJson('/api/stat/start-time', {
      timeoutMs: 1800,
      method: 'GET',
    });
    if (!result.ok || !result.data) {
      return null;
    }
    const rawStartTime = result.data?.data?.start_time;
    const numericStartTime = Number(rawStartTime);
    return Number.isFinite(numericStartTime) ? numericStartTime : null;
  }

  async requestGracefulRestart(authToken = null) {
    const result = await this.requestBackendJson('/api/stat/restart-core', {
      timeoutMs: 2500,
      method: 'POST',
      authToken,
      headers: {
        'Content-Type': 'application/json',
      },
    });
    return result.ok;
  }

  async waitForGracefulRestart(previousStartTime, maxWaitMs = 0) {
    const effectiveMaxWaitMs = this.getEffectiveWaitMs(maxWaitMs);
    const gracefulWaitMs =
      effectiveMaxWaitMs > 0
        ? effectiveMaxWaitMs
        : GRACEFUL_RESTART_WAIT_FALLBACK_MS;
    const start = Date.now();
    let sawBackendDown = false;

    while (true) {
      const reachable = await this.pingBackend(700);
      if (!reachable) {
        sawBackendDown = true;
      } else {
        const currentStartTime = await this.getBackendStartTime();
        if (
          previousStartTime !== null &&
          currentStartTime !== null &&
          currentStartTime !== previousStartTime
        ) {
          return { ok: true, reason: null };
        }
        if (sawBackendDown && previousStartTime === null) {
          return { ok: true, reason: null };
        }
      }

      if (Date.now() - start >= gracefulWaitMs) {
        return {
          ok: false,
          reason: `Timed out after ${gracefulWaitMs}ms waiting for graceful restart.`,
        };
      }

      await delay(350);
    }
  }

  async waitForBackend(maxWaitMs = 0, failOnProcessExit = false) {
    const effectiveMaxWaitMs = this.getEffectiveWaitMs(maxWaitMs);
    const start = Date.now();
    while (true) {
      if (await this.pingBackend()) {
        return { ok: true, reason: null };
      }
      if (failOnProcessExit && !this.backendProcess) {
        return {
          ok: false,
          reason:
            this.backendLastExitReason ||
            'Backend process exited before becoming reachable.',
        };
      }
      if (effectiveMaxWaitMs > 0 && Date.now() - start >= effectiveMaxWaitMs) {
        return {
          ok: false,
          reason: `Timed out after ${effectiveMaxWaitMs}ms waiting for backend startup.`,
        };
      }
      await delay(600);
    }
  }

  async startBackend() {
    if (this.shouldSkipStart()) {
      this.log('Skip backend start because app is quitting.');
      return;
    }
    if (this.backendProcess) {
      return;
    }
    const backendConfig = this.getBackendConfig();
    if (!backendConfig.cmd) {
      return;
    }

    this.backendLastExitReason = null;
    const env = {
      ...process.env,
      PYTHONUNBUFFERED: '1',
    };
    if (this.app.isPackaged) {
      env.ASTRBOT_ELECTRON_CLIENT = '1';
      const hasExplicitDashboardHost = Boolean(
        process.env.DASHBOARD_HOST || process.env.ASTRBOT_DASHBOARD_HOST,
      );
      const hasExplicitDashboardPort = Boolean(
        process.env.DASHBOARD_PORT || process.env.ASTRBOT_DASHBOARD_PORT,
      );
      if (!hasExplicitDashboardHost) {
        env.DASHBOARD_HOST = '127.0.0.1';
      }
      if (!hasExplicitDashboardPort) {
        env.DASHBOARD_PORT = '6185';
      }
    }
    if (backendConfig.webuiDir) {
      env.ASTRBOT_WEBUI_DIR = backendConfig.webuiDir;
    }
    let backendLogPath = null;
    if (backendConfig.rootDir) {
      env.ASTRBOT_ROOT = backendConfig.rootDir;
      const logsDir = path.join(backendConfig.rootDir, 'logs');
      ensureDir(logsDir);
      backendLogPath = path.join(logsDir, 'backend.log');
    }
    await this.backendLogger.setLogPath(backendLogPath);
    const usePipedLogging = Boolean(backendLogPath);

    this.backendProcess = spawn(backendConfig.cmd, backendConfig.args || [], {
      cwd: backendConfig.cwd,
      env,
      shell: backendConfig.shell,
      stdio: usePipedLogging ? ['ignore', 'pipe', 'pipe'] : 'ignore',
      windowsHide: true,
    });

    if (usePipedLogging) {
      if (this.backendProcess.stdout) {
        this.backendProcess.stdout.on('data', (chunk) => {
          this.backendLogger.log(chunk);
        });
      }
      if (this.backendProcess.stderr) {
        this.backendProcess.stderr.on('data', (chunk) => {
          this.backendLogger.log(chunk);
        });
      }
    }

    if (usePipedLogging) {
      const launchLine = [backendConfig.cmd, ...(backendConfig.args || [])]
        .map((item) => JSON.stringify(item))
        .join(' ');
      this.backendLogger.log(
        `[${formatLogTimestamp()}] [Electron] Start backend ${launchLine}\n`,
      );
    }

    this.backendProcess.on('error', (error) => {
      this.backendLastExitReason =
        error instanceof Error ? error.message : String(error);
      this.backendLogger.log(
        `[${formatLogTimestamp()}] [Electron] Backend spawn error: ${
          error instanceof Error ? error.message : String(error)
        }\n`,
      );
      void this.backendLogger.flush();
      this.backendProcess = null;
    });

    this.backendProcess.on('exit', (code, signal) => {
      this.backendLastExitReason = `Backend process exited (code=${code ?? 'null'}, signal=${signal ?? 'null'}).`;
      void this.backendLogger.flush();
      this.backendProcess = null;
    });
  }

  async startBackendAndWait(maxWaitMs = this.backendTimeoutMs) {
    if (!this.canManageBackend()) {
      return {
        ok: false,
        reason: this.getBackendCommandUnavailableReason(),
      };
    }
    this.backendSpawning = true;
    try {
      await this.startBackend();
      return await this.waitForBackend(maxWaitMs, true);
    } finally {
      this.backendSpawning = false;
    }
  }

  async stopManagedBackend() {
    if (!this.backendProcess) {
      return;
    }
    const processToStop = this.backendProcess;
    const pid = processToStop.pid;
    this.backendProcess = null;
    this.log(`Stop backend requested pid=${pid ?? 'unknown'}`);

    if (process.platform === 'win32' && pid) {
      try {
        // Synchronous taskkill is acceptable here because stop/restart is
        // already a control-path operation and not latency-sensitive.
        const result = spawnSync('taskkill', ['/pid', `${pid}`, '/t', '/f'], {
          stdio: 'ignore',
          windowsHide: true,
        });
        if (result.status !== 0) {
          this.log(
            `taskkill failed pid=${pid} status=${result.status} signal=${result.signal ?? 'null'}`,
          );
        } else {
          this.log(`taskkill completed pid=${pid}`);
        }
      } catch (error) {
        this.log(
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
          this.log(
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
    await this.backendLogger.flush();
  }

  findListeningPidsOnWindows(port) {
    // Synchronous netstat parsing is acceptable here because this helper is
    // used only during shutdown/restart cleanup paths.
    const result = spawnSync('netstat', ['-ano', '-p', 'tcp'], {
      stdio: ['ignore', 'pipe', 'ignore'],
      encoding: 'utf8',
      windowsHide: true,
    });

    if (result.status !== 0 || !result.stdout) {
      return [];
    }

    const pids = new Set();
    const lines = result.stdout.split(/\r?\n/);

    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed || !trimmed.toUpperCase().startsWith('TCP')) {
        continue;
      }

      const parts = trimmed.split(/\s+/);
      if (parts.length < 5) {
        continue;
      }

      const localAddress = parts[1] || '';
      const state = (parts[3] || '').toUpperCase();
      const pid = parts[parts.length - 1];
      if (!/^\d+$/.test(pid)) {
        continue;
      }

      if (state !== 'LISTENING') {
        continue;
      }

      const cleanedLocalAddress = localAddress.replace(/\]$/, '');
      const segments = cleanedLocalAddress.split(':');
      const portStr = segments[segments.length - 1];
      const portNum = Number(portStr);
      if (Number.isInteger(portNum) && portNum === Number(port)) {
        pids.add(pid);
      }
    }

    return Array.from(pids);
  }

  getWindowsProcessInfo(pid) {
    const result = spawnSync(
      'tasklist',
      ['/FI', `PID eq ${pid}`, '/FO', 'CSV', '/NH'],
      {
        stdio: ['ignore', 'pipe', 'ignore'],
        encoding: 'utf8',
        windowsHide: true,
      },
    );
    if (result.status !== 0 || !result.stdout) {
      return null;
    }

    const firstLine = result.stdout
      .split(/\r?\n/)
      .map((line) => line.trim())
      .find((line) => line.length > 0);
    if (!firstLine || firstLine.startsWith('INFO:')) {
      return null;
    }

    const fields = firstLine
      .replace(/^"/, '')
      .replace(/"$/, '')
      .split('","');
    const imageName = fields[0] || '';
    const parsedPid = Number.parseInt(fields[1] || '', 10);
    if (!imageName || !Number.isInteger(parsedPid) || parsedPid !== Number(pid)) {
      return null;
    }
    return { imageName, pid: parsedPid };
  }

  async stopUnmanagedBackendByPort() {
    if (!this.app.isPackaged || process.platform !== 'win32') {
      return false;
    }

    const port = this.getBackendPort();
    if (!port) {
      return false;
    }

    const pids = this.findListeningPidsOnWindows(port);
    if (!pids.length) {
      return false;
    }

    this.log(
      `Attempting unmanaged backend cleanup by port=${port} pids=${pids.join(',')}`,
    );
    let backendConfig = null;
    try {
      backendConfig = this.getBackendConfig();
    } catch (error) {
      this.log(
        `Failed to resolve backend config during unmanaged cleanup: ${
          error instanceof Error ? error.message : String(error)
        }`,
      );
    }
    const hasBackendConfig = backendConfig && typeof backendConfig === 'object';
    if (!hasBackendConfig) {
      this.log(
        'Backend config is unavailable during unmanaged cleanup; falling back to image-name-only matching.',
      );
    }
    const contextBase = {
      backendConfig,
      allowImageOnlyMatch: !hasBackendConfig,
      commandLineCache: new Map(),
      fallbackCmdRaw: process.env.ASTRBOT_BACKEND_CMD || 'python.exe',
      spawnSync,
      log: (message) => this.log(message),
    };

    for (const pid of pids) {
      const processInfo = this.getWindowsProcessInfo(pid);
      if (!processInfo) {
        this.log(`Skip unmanaged cleanup for pid=${pid}: unable to resolve process info.`);
        continue;
      }
      const shouldKill = shouldKillUnmanagedBackendProcess({
        pid,
        processInfo,
        ...contextBase,
      });
      if (!shouldKill) {
        continue;
      }

      try {
        // Synchronous taskkill is acceptable here because unmanaged cleanup
        // is performed only during shutdown/restart control flows.
        spawnSync('taskkill', ['/pid', `${pid}`, '/t', '/f'], {
          stdio: 'ignore',
          windowsHide: true,
        });
      } catch {}
    }

    await delay(500);
    return !(await this.pingBackend(1200));
  }

  async stopAnyBackend() {
    if (this.backendProcess) {
      await this.stopManagedBackend();
      const running = await this.pingBackend();
      if (!running) {
        return { ok: true, reason: null };
      }
    } else {
      const running = await this.pingBackend();
      if (!running) {
        return { ok: true, reason: null };
      }
    }

    const cleaned = await this.stopUnmanagedBackendByPort();
    if (cleaned) {
      return { ok: true, reason: null };
    }

    return {
      ok: false,
      reason: 'Backend is running but not managed by Electron.',
    };
  }

  async ensureBackend() {
    this.backendStartupFailureReason = null;

    const running = await this.pingBackend();
    if (running) {
      return true;
    }
    if (!this.backendAutoStart) {
      this.backendStartupFailureReason = 'Backend auto-start is disabled.';
      return false;
    }
    if (!this.canManageBackend()) {
      this.backendStartupFailureReason = this.getBackendCommandUnavailableReason();
      return false;
    }
    const waitResult = await this.startBackendAndWait(this.backendTimeoutMs);
    if (!waitResult.ok) {
      this.backendStartupFailureReason = waitResult.reason;
      return false;
    }
    return true;
  }

  async getState() {
    return {
      running: await this.pingBackend(),
      spawning: this.backendSpawning,
      restarting: this.backendRestarting,
      canManage: this.canManageBackend(),
    };
  }

  async restartBackend(authToken = null) {
    if (!this.canManageBackend()) {
      return {
        ok: false,
        reason: this.getBackendCommandUnavailableReason(),
      };
    }
    if (this.backendSpawning || this.backendRestarting) {
      return {
        ok: false,
        reason: 'Backend action already in progress.',
      };
    }

    this.backendRestarting = true;
    try {
      const backendRunning = await this.pingBackend(900);
      if (backendRunning) {
        const previousStartTime = await this.getBackendStartTime();
        const gracefulRequested = await this.requestGracefulRestart(authToken);
        if (gracefulRequested) {
          const gracefulResult = await this.waitForGracefulRestart(
            previousStartTime,
            this.backendTimeoutMs,
          );
          if (gracefulResult.ok) {
            return {
              ok: true,
              reason: null,
            };
          }
          this.log(
            `Graceful restart did not complete: ${gracefulResult.reason || 'unknown reason'}`,
          );
        } else {
          this.log(
            'Graceful restart request failed; falling back to managed restart.',
          );
        }
      }

      await this.stopManagedBackend();
      const startResult = await this.startBackendAndWait(this.backendTimeoutMs);
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
      this.backendRestarting = false;
    }
  }

  async stopBackendForIpc() {
    if (!this.canManageBackend()) {
      return {
        ok: false,
        reason: this.getBackendCommandUnavailableReason(),
      };
    }
    if (this.backendSpawning || this.backendRestarting) {
      return {
        ok: false,
        reason: 'Backend action already in progress.',
      };
    }

    try {
      return await this.stopAnyBackend();
    } catch (error) {
      return {
        ok: false,
        reason: error instanceof Error ? error.message : String(error),
      };
    }
  }
}

module.exports = {
  BackendManager,
};
