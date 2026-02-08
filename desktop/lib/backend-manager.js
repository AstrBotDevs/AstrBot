'use strict';

const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawn, spawnSync } = require('child_process');
const { delay, ensureDir, normalizeUrl, waitForProcessExit } = require('./common');

const PACKAGED_BACKEND_TIMEOUT_FALLBACK_MS = 5 * 60 * 1000;

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

    this.backendProcess = null;
    this.backendConfig = null;
    this.backendLogFd = null;
    this.backendLastExitReason = null;
    this.backendStartupFailureReason = null;
    this.backendSpawning = false;
    this.backendRestarting = false;
  }

  getBackendUrl() {
    return this.backendUrl;
  }

  getBackendTimeoutMs() {
    return this.backendTimeoutMs;
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

  isSpawning() {
    return this.backendSpawning;
  }

  isRestarting() {
    return this.backendRestarting;
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

  getPackagedBackendPath() {
    if (!this.app.isPackaged) {
      return null;
    }
    const filename =
      process.platform === 'win32' ? 'astrbot-backend.exe' : 'astrbot-backend';
    const candidate = path.join(process.resourcesPath, 'backend', filename);
    return fs.existsSync(candidate) ? candidate : null;
  }

  buildDefaultBackendLaunch(webuiDir) {
    if (this.app.isPackaged) {
      const packagedBackend = this.getPackagedBackendPath();
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

  resolveBackendConfig() {
    const webuiDir = this.resolveWebuiDir();
    const customCmd = process.env.ASTRBOT_BACKEND_CMD;
    const launch = customCmd
      ? {
          cmd: customCmd,
          args: [],
          shell: true,
        }
      : this.buildDefaultBackendLaunch(webuiDir);
    const cwd = process.env.ASTRBOT_BACKEND_CWD || this.resolveBackendCwd();
    const rootDir = process.env.ASTRBOT_ROOT || this.resolveBackendRoot();
    ensureDir(cwd);
    if (rootDir) {
      ensureDir(rootDir);
    }
    this.backendConfig = {
      cmd: launch ? launch.cmd : null,
      args: launch ? launch.args : [],
      shell: launch ? launch.shell : true,
      cwd,
      webuiDir,
      rootDir,
    };
    return this.backendConfig;
  }

  getBackendConfig() {
    if (!this.backendConfig) {
      return this.resolveBackendConfig();
    }
    return this.backendConfig;
  }

  canManageBackend() {
    return Boolean(this.getBackendConfig().cmd);
  }

  closeBackendLogFd() {
    if (this.backendLogFd === null) {
      return;
    }
    try {
      fs.closeSync(this.backendLogFd);
    } catch {}
    this.backendLogFd = null;
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

  async waitForBackend(maxWaitMs = 0, failOnProcessExit = false) {
    const effectiveMaxWaitMs =
      maxWaitMs > 0
        ? maxWaitMs
        : this.app.isPackaged
          ? PACKAGED_BACKEND_TIMEOUT_FALLBACK_MS
          : 0;
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

  startBackend() {
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
    if (backendConfig.rootDir) {
      env.ASTRBOT_ROOT = backendConfig.rootDir;
      const logsDir = path.join(backendConfig.rootDir, 'logs');
      ensureDir(logsDir);
      const logPath = path.join(logsDir, 'backend.log');
      try {
        this.backendLogFd = fs.openSync(logPath, 'a');
      } catch {
        this.backendLogFd = null;
      }
    }

    this.backendProcess = spawn(backendConfig.cmd, backendConfig.args || [], {
      cwd: backendConfig.cwd,
      env,
      shell: backendConfig.shell,
      stdio:
        this.backendLogFd === null
          ? 'ignore'
          : ['ignore', this.backendLogFd, this.backendLogFd],
      windowsHide: true,
    });

    if (this.backendLogFd !== null) {
      const launchLine = [backendConfig.cmd, ...(backendConfig.args || [])]
        .map((item) => JSON.stringify(item))
        .join(' ');
      try {
        fs.writeSync(
          this.backendLogFd,
          `[${new Date().toISOString()}] [Electron] Start backend ${launchLine}\n`,
        );
      } catch {}
    }

    this.backendProcess.on('error', (error) => {
      this.backendLastExitReason =
        error instanceof Error ? error.message : String(error);
      if (this.backendLogFd !== null) {
        try {
          fs.writeSync(
            this.backendLogFd,
            `[${new Date().toISOString()}] [Electron] Backend spawn error: ${
              error instanceof Error ? error.message : String(error)
            }\n`,
          );
        } catch {}
      }
      this.closeBackendLogFd();
      this.backendProcess = null;
    });

    this.backendProcess.on('exit', (code, signal) => {
      this.backendLastExitReason = `Backend process exited (code=${code ?? 'null'}, signal=${signal ?? 'null'}).`;
      this.closeBackendLogFd();
      this.backendProcess = null;
    });
  }

  async startBackendAndWait(maxWaitMs = this.backendTimeoutMs) {
    if (!this.canManageBackend()) {
      return {
        ok: false,
        reason: 'Backend command is not configured.',
      };
    }
    this.backendSpawning = true;
    try {
      this.startBackend();
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
    this.closeBackendLogFd();
  }

  async ensureBackend() {
    this.backendStartupFailureReason = null;

    const running = await this.pingBackend();
    if (running) {
      return true;
    }
    if (!this.backendAutoStart || !this.canManageBackend()) {
      this.backendStartupFailureReason =
        'Backend auto-start is disabled or backend command is not configured.';
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

  async restartBackend() {
    if (!this.canManageBackend()) {
      return {
        ok: false,
        reason: 'Backend command is not configured.',
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
        reason: 'Backend command is not configured.',
      };
    }
    if (this.backendSpawning || this.backendRestarting) {
      return {
        ok: false,
        reason: 'Backend action already in progress.',
      };
    }

    try {
      if (!this.backendProcess) {
        const running = await this.pingBackend();
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
      await this.stopManagedBackend();
      const running = await this.pingBackend();
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
  }
}

module.exports = {
  BackendManager,
};
