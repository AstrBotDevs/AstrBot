import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { randomBytes } from 'node:crypto';
import { once } from 'node:events';
import { access, chmod, mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { createServer } from 'node:net';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import { chromium } from 'playwright';

const repo = fileURLToPath(new URL('../../../', import.meta.url));
const python = process.env.ASTRBOT_E2E_PYTHON || join(repo, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');

async function freePort() {
  const server = createServer();
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  const port = server.address().port;
  await new Promise(resolve => server.close(resolve));
  return port;
}

async function eventually(check, message, timeout = 15000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    if (await check()) return;
    await delay(200);
  }
  throw new Error(message);
}

test('onboarding against an isolated real AstrBot process', { timeout: 300000 }, async t => {
  await access(join(repo, 'dashboard/dist/index.html'));
  await access(python);
  const root = await mkdtemp(join(tmpdir(), 'astrbot-onboarding-e2e-'));
  await chmod(root, 0o700);
  const port = await freePort();
  const adapterPort = await freePort();
  const editedPort = await freePort();
  const base = `http://127.0.0.1:${port}`;
  const username = 'onboarding-e2e';
  const password = `E2e-${randomBytes(18).toString('hex')}`;
  const adapterToken = randomBytes(24).toString('hex');
  let token;
  let backend;
  let browser;
  let page;
  let model;
  let chatSessionId;
  const errors = [];
  const writes = [];
  const env = { ...process.env, ASTRBOT_ROOT: root, DASHBOARD_HOST: '127.0.0.1', DASHBOARD_PORT: String(port),
    ASTRBOT_DASHBOARD_SKIP_DEFAULT_PASSWORD_AUTH: 'true', PYTHONDONTWRITEBYTECODE: '1' };
  delete env.ASTRBOT_RESET_DASHBOARD_PASSWORD;
  delete env.ASTRBOT_E2E_MODEL_FILE;

  async function api(path, options = {}) {
    const response = await fetch(`${base}/api/v1${path}`, { ...options, signal: AbortSignal.timeout(10000),
      headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}), ...options.headers } });
    assert.equal(response.ok, true, `${path}: HTTP ${response.status}`);
    const body = await response.json();
    assert.equal(body.status, 'ok', `${path}: API rejected request`);
    return body.data;
  }

  async function stopBackend() {
    if (!backend || backend.exitCode !== null || backend.signalCode !== null) return;
    const exited = once(backend, 'exit');
    backend.kill('SIGTERM');
    const killTimer = setTimeout(() => backend.kill('SIGKILL'), 10000);
    try { await exited; } finally { clearTimeout(killTimer); }
  }

  async function startBackend() {
    let spawnError;
    backend = spawn(python, [join(repo, 'main.py'), '--webui-dir', join(repo, 'dashboard/dist')],
      { cwd: root, env, stdio: 'ignore' });
    backend.on('error', error => { spawnError = error; });
    await eventually(async () => {
      if (spawnError) throw spawnError;
      assert.equal(backend.exitCode, null, 'AstrBot exited during startup');
      try { await api('/auth/setup-status'); return true; } catch { return false; }
    }, 'AstrBot startup timed out', 60000);
  }

  async function enterAdapter() {
    await page.goto(`${base}/#/auth/onboarding`);
    await page.reload();
    await page.getByRole('button', { name: 'Next', exact: true }).click();
    await page.getByRole('button', { name: 'Skip', exact: true }).click();
    await page.getByRole('heading', { name: 'Connect a messaging platform', exact: true }).waitFor();
    await page.locator('.guide-content .v-progress-linear[aria-hidden="false"]').waitFor({ state: 'hidden' });
  }

  const field = title => page.locator('.config-row').filter({ has: page.getByText(title, { exact: true }) }).locator('input');
  try {
    if (process.env.ASTRBOT_E2E_MODEL_FILE) {
      model = JSON.parse(await readFile(process.env.ASTRBOT_E2E_MODEL_FILE, 'utf8'));
      assert.ok(model.api_base && model.api_key && model.model, 'Model file requires api_base, api_key and model');
    }
    await startBackend();
    assert.equal((await api('/auth/setup-status')).setup_required, true);
    const denied = await fetch(`${base}/api/v1/system-config/runtime`);
    assert.ok([401, 403].includes(denied.status), 'Anonymous configuration access must be rejected');
    await stopBackend();
    await startBackend();
    browser = await chromium.launch({ headless: true, ...(process.env.ASTRBOT_E2E_BROWSER ? { executablePath: process.env.ASTRBOT_E2E_BROWSER } : {}) });
    const context = await browser.newContext({ viewport: { width: 1280, height: 900 }, locale: 'en-US' });
    await context.addInitScript(() => {
      if (location.protocol === 'http:') localStorage.setItem('astrbot-locale', 'en-US');
    });
    page = await context.newPage();
    page.setDefaultTimeout(15000);
    page.on('pageerror', error => errors.push(error.message));
    page.on('request', request => {
      const url = new URL(request.url());
      if (url.origin === base && !['GET', 'HEAD', 'OPTIONS'].includes(request.method())) writes.push(url.pathname);
    });
    await page.goto(`${base}/#/auth/onboarding`);
    await page.getByLabel('New username', { exact: true }).waitFor();
    assert.ok(page.url().endsWith('#/auth/setup'), 'Anonymous onboarding must go through account setup');
    const rejectedSetup = await fetch(`${base}/api/v1/auth/setup`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password, confirm_password: 'mismatch' }) });
    assert.notEqual((await rejectedSetup.json()).status, 'ok');
    await page.getByLabel('New username', { exact: true }).fill(username);
    await page.getByLabel('New password', { exact: true }).fill(password);
    await page.getByLabel('Confirm new password', { exact: true }).fill(password);
    const setupResponse = page.waitForResponse(response => new URL(response.url()).pathname === '/api/v1/auth/setup' && response.request().method() === 'POST');
    await page.getByRole('button', { name: 'Complete Setup', exact: true }).click();
    const account = (await (await setupResponse).json()).data;
    token = account.token;
    assert.ok(token, 'Setup must issue a usable token');
    assert.equal(account.onboarding_required, true);
    await page.getByRole('button', { name: 'Skip entire setup', exact: true }).waitFor();
    assert.ok(page.url().endsWith('#/auth/onboarding'));
    assert.equal((await api('/auth/setup-status')).setup_required, false);
    const emptyConfig = JSON.parse((await readFile(join(root, 'data/cmd_config.json'), 'utf8')).replace(/^\uFEFF/, ''));
    const repeatedSetup = await fetch(`${base}/api/v1/auth/setup`, { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ username, password, confirm_password: password }) });
    assert.notEqual((await repeatedSetup.json()).status, 'ok', 'A second tab cannot repeat account setup');
    t.diagnostic('PASS: fresh installation survives pre-setup restart and validation failure; browser setup enters onboarding once');

    await page.getByRole('button', { name: 'Skip entire setup', exact: true }).click();
    await page.waitForURL(url => url.hash === '#/data/statistics');
    await page.reload();
    await page.waitForURL(url => url.hash === '#/data/statistics');
    await context.clearCookies();
    await page.evaluate(() => localStorage.clear());
    await page.goto(`${base}/#/auth/login`);
    await page.locator('input[name="username"]').fill(username);
    await page.locator('input[name="password"]').fill(password);
    await page.locator('button[type="submit"]').click();
    await page.waitForURL(url => url.hash === '#/data/statistics');
    t.diagnostic('PASS: real setup, authorization and browser login');

    await page.goto(`${base}/#/welcome`);
    await page.reload();
    await page.waitForURL(url => url.hash === '#/data/statistics');
    await page.goto(`${base}/#/settings#settings-maintenance`);
    await page.getByRole('link', { name: 'Reopen setup', exact: true }).click();
    await page.getByRole('button', { name: 'Skip entire setup', exact: true }).waitFor();

    await page.goto(`${base}/#/auth/onboarding`);
    const beforeSkip = writes.length;
    await page.getByRole('button', { name: 'Skip entire setup', exact: true }).click();
    await page.waitForURL(url => !url.hash.startsWith('#/auth/'));
    assert.equal(writes.slice(beforeSkip).some(path => /bots|providers|config-profiles/.test(path)), false);
    assert.equal((await api('/bots')).bots.length, 0);
    t.diagnostic('PASS: skip entire guide without creating configuration');

    await enterAdapter();
    await page.locator('.platform-embedded .v-select').first().click();
    await page.getByText('OneBot v11', { exact: true }).click();
    await field('Bot Name').fill('');
    assert.equal(await page.getByRole('button', { name: 'Next', exact: true }).isEnabled(), false);
    await field('Bot Name').fill('e2e-onebot');
    await field('Reverse WebSocket Host').fill('127.0.0.1');
    await field('Reverse WebSocket Port').fill(String(adapterPort));
    await field('Reverse WebSocket Token').fill(adapterToken);
    await page.getByRole('button', { name: 'Next', exact: true }).click();
    await page.locator('.guide-welcome').waitFor();
    let bots = (await api('/bots')).bots;
    assert.equal(bots.length, 1);
    assert.equal(bots[0].id, 'e2e-onebot');
    assert.equal(bots[0].ws_reverse_port, adapterPort);
    assert.equal(bots[0].enable, true);
    await eventually(async () => {
      try { await fetch(`http://127.0.0.1:${adapterPort}/`, { signal: AbortSignal.timeout(1000) }); return true; } catch { return false; }
    }, 'Real OneBot listener did not start');
    await page.getByRole('button', { name: 'Get started', exact: true }).click();
    await page.waitForURL(url => !url.hash.startsWith('#/auth/'));
    t.diagnostic('PASS: validation, real adapter creation/listener and welcome exit');

    await enterAdapter();
    assert.equal(await field('Reverse WebSocket Port').inputValue(), String(adapterPort));
    assert.equal(await field('Reverse WebSocket Token').inputValue() === adapterToken, true);
    const beforeUnchanged = writes.length;
    await page.getByRole('button', { name: 'Next', exact: true }).click();
    await page.locator('.guide-welcome').waitFor();
    assert.equal(writes.slice(beforeUnchanged).some(path => /bots|config-routes/.test(path)), false);
    await enterAdapter();
    await field('Reverse WebSocket Port').fill(String(editedPort));
    await page.getByRole('button', { name: 'Skip', exact: true }).click();
    await page.locator('.guide-welcome').waitFor();
    assert.equal((await api('/bots')).bots[0].ws_reverse_port, adapterPort);
    await enterAdapter();
    await field('Reverse WebSocket Port').fill(String(editedPort));
    await page.getByRole('button', { name: 'Next', exact: true }).click();
    await page.locator('.guide-welcome').waitFor();
    bots = (await api('/bots')).bots;
    assert.equal(bots.length, 1);
    assert.equal(bots[0].ws_reverse_port, editedPort);
    const disk = JSON.parse((await readFile(join(root, 'data/cmd_config.json'), 'utf8')).replace(/^\uFEFF/, ''));
    assert.equal(disk.platform[0].ws_reverse_port, editedPort);
    t.diagnostic('PASS: adapter prefill, unchanged save, discarded draft and persisted edit');

    await enterAdapter();
    await page.locator('.platform-embedded .v-data-table button').first().click();
    await page.locator('.config-profile-drawer-content').waitFor();
    const configInput = page.locator('.config-profile-drawer-content .config-row input:not([readonly]):not([disabled])').filter({ visible: true }).first();
    await configInput.waitFor();
    const originalValue = await configInput.inputValue();
    const editedValue = await configInput.getAttribute('type') === 'number' ? '2' : 'onboarding-edit-check';
    await configInput.fill(editedValue);
    assert.equal(await configInput.inputValue(), editedValue);
    await configInput.fill(originalValue);
    await page.locator('.config-profile-drawer-header button').click();
    const originalRoutes = (await api('/config-routes')).routing;
    await page.getByRole('button', { name: 'Edit', exact: true }).click();
    await page.locator('.route-source-input-row input').last().fill('onboarding-e2e');
    await page.getByRole('button', { name: 'Skip', exact: true }).click();
    await page.locator('.guide-welcome').waitFor();
    assert.deepEqual((await api('/config-routes')).routing, originalRoutes);
    await enterAdapter();
    await page.getByRole('button', { name: 'Edit', exact: true }).click();
    await page.locator('.route-source-input-row input').last().fill('onboarding-e2e');
    const beforeRoutes = writes.length;
    if (process.env.ASTRBOT_E2E_SCREENSHOT_DIR) {
      await mkdir(process.env.ASTRBOT_E2E_SCREENSHOT_DIR, { recursive: true, mode: 0o700 });
      for (const width of [1280, 360]) {
        await page.setViewportSize({ width, height: 900 });
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
        await page.locator('.route-source-input-row').scrollIntoViewIfNeeded();
        await page.screenshot({ path: join(process.env.ASTRBOT_E2E_SCREENSHOT_DIR, `adapter-routes-${width}.png`) });
      }
      await page.setViewportSize({ width: 1280, height: 900 });
    }
    await page.getByRole('button', { name: 'Next', exact: true }).click();
    await page.locator('.guide-welcome').waitFor();
    assert.equal((await api('/config-routes')).routing['e2e-onebot:*:onboarding-e2e'], 'default');
    assert.equal(writes.slice(beforeRoutes).some(path => path.includes('/bots')), false);
    t.diagnostic('PASS: reopened config drawer is editable; route drafts discard or persist without rewriting the adapter');

    await t.test('real model configuration and streamed ChatUI reply', { skip: model ? false : 'Set ASTRBOT_E2E_MODEL_FILE to exercise a real model' }, async () => {
      await page.goto(`${base}/#/auth/onboarding`);
      await page.reload();
      await page.getByRole('button', { name: 'Next', exact: true }).click();
      await page.locator('.model-choices button').filter({ hasText: /OpenAI/ }).first().click();
      try {
        await page.getByLabel('API Key', { exact: true }).fill(model.api_key);
      } catch {
        throw new Error('Could not fill the API key field; locator details omitted to protect credentials');
      }
      await page.getByLabel('API Base URL', { exact: true }).fill(model.api_base);
      await page.getByLabel('Model name', { exact: true }).fill(model.model);
      const sessionCreated = page.waitForResponse(response => new URL(response.url()).pathname === '/api/v1/chat/sessions/new');
      await page.getByRole('button', { name: 'Next', exact: true }).click();
      chatSessionId = (await (await sessionCreated).json()).data.session_id;
      assert.equal(await page.locator('.standalone-chat .input-left-actions, .standalone-chat .record-btn, .standalone-chat input[type="file"]').count(), 0);
      assert.equal(await page.locator('.standalone-chat .input-right-actions button').count(), 1, 'Trial composer only exposes Send/Stop');
      await page.locator('.standalone-chat textarea').fill('Reply with only ASTRBOT_E2E_OK. Do not use tools.');
      await page.locator('.standalone-chat textarea').press('Enter');
      await eventually(async () => {
        const session = await api(`/chat/sessions/${chatSessionId}`);
        return !session.is_running && session.history.some(item => item.sender_id === 'bot' && JSON.stringify(item.content).includes('ASTRBOT_E2E_OK'));
      }, 'Real model reply was not persisted', 90000);
      assert.match(await page.locator('.from-bot').innerText(), /ASTRBOT_E2E_OK/);
      assert.ok(page.url().endsWith('#/auth/onboarding'), 'ChatUI must remain embedded');
      for (const width of [1280, 360]) {
        await page.setViewportSize({ width, height: 900 });
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
        if (process.env.ASTRBOT_E2E_SCREENSHOT_DIR) {
          await mkdir(process.env.ASTRBOT_E2E_SCREENSHOT_DIR, { recursive: true, mode: 0o700 });
          await page.screenshot({ path: join(process.env.ASTRBOT_E2E_SCREENSHOT_DIR, `trial-${width}.png`) });
        }
      }
      await page.setViewportSize({ width: 1280, height: 900 });
      const schema = await api('/providers/schema');
      assert.equal(schema.providers.length, 1);
      const config = (await api('/config-profiles/default')).config;
      assert.equal(config.agent_runner.config.model.provider_id, schema.providers[0].id);
      await page.getByRole('button', { name: 'Back', exact: true }).click();
      await page.getByRole('button', { name: 'Next', exact: true }).click();
      assert.equal((await api('/chat/sessions')).length, 1, 'Back/Next must preserve the embedded session');
      assert.equal((await api('/providers/schema')).providers.length, 1);
      await page.getByRole('button', { name: 'Next', exact: true }).click();
      await page.getByRole('button', { name: 'Skip', exact: true }).click();
      await page.getByRole('button', { name: 'Get started', exact: true }).click();
      await page.waitForURL(url => !url.hash.startsWith('#/auth/'));
      await page.goto(`${base}/#/chat`);
      await page.reload();
      await page.locator('.input-left-actions').waitFor();
      await page.locator('.record-btn').waitFor();
      assert.ok(await page.locator('.input-right-actions button').count() > 1, 'Regular ChatUI retains its controls');
    });

    await page.goto('about:blank');
    await stopBackend();
    await startBackend();
    assert.equal((await api('/auth/setup-status')).setup_required, false);
    bots = (await api('/bots')).bots;
    assert.equal(bots.length, 1);
    assert.equal(bots[0].ws_reverse_port, editedPort);
    assert.equal((await api('/config-routes')).routing['e2e-onebot:*:onboarding-e2e'], 'default');
    await enterAdapter();
    assert.equal(await field('Reverse WebSocket Port').inputValue(), String(editedPort));
    if (chatSessionId) {
      assert.ok((await api(`/chat/sessions/${chatSessionId}`)).history.some(item => item.sender_id === 'bot' && JSON.stringify(item.content).includes('ASTRBOT_E2E_OK')));
      await page.goto(`${base}/#/auth/onboarding`);
      await page.reload();
      await page.getByRole('button', { name: 'Next', exact: true }).click();
      await eventually(async () => await page.getByRole('button', { name: 'Next', exact: true }).isEnabled(), 'Existing model was not ready');
      assert.equal(await page.getByLabel('Model name', { exact: true }).inputValue(), model.model);
      assert.equal(await page.getByLabel('API Base URL', { exact: true }).inputValue(), model.api_base);
    }
    assert.deepEqual(errors, []);
    t.diagnostic('PASS: configuration survives process restart; browser has no uncaught errors');

    for (const variant of ['legacy-empty', 'legacy-adapter-only', 'password-reset']) {
      await page.goto('about:blank');
      await stopBackend();
      const existing = structuredClone(emptyConfig);
      if (variant !== 'password-reset') delete existing.dashboard.onboarding_pending;
      if (variant === 'legacy-adapter-only') existing.platform = [{ ...bots[0], enable: false }];
      await writeFile(join(root, 'data/cmd_config.json'), JSON.stringify(existing), { mode: 0o600 });
      env.ASTRBOT_RESET_DASHBOARD_PASSWORD = 'true';
      await startBackend();
      delete env.ASTRBOT_RESET_DASHBOARD_PASSWORD;
      await context.clearCookies();
      await page.goto(base);
      await page.evaluate(() => localStorage.clear());
      await page.goto(`${base}/#/auth/setup`);
      await page.reload();
      await page.getByLabel('New username', { exact: true }).fill(username);
      await page.getByLabel('New password', { exact: true }).fill(password);
      await page.getByLabel('Confirm new password', { exact: true }).fill(password);
      const saved = page.waitForResponse(response => new URL(response.url()).pathname === '/api/v1/auth/setup' && response.request().method() === 'POST');
      await page.getByRole('button', { name: 'Complete Setup', exact: true }).click();
      const result = (await (await saved).json()).data;
      assert.equal(result.onboarding_required, false, variant);
      token = result.token;
      await page.waitForURL(url => url.hash === '#/data/statistics');
      assert.equal(await page.locator('.onboarding-setup').count(), 0);
      t.diagnostic(`PASS: ${variant} changes password without automatic onboarding`);
    }
  } catch (error) {
    if (page && process.env.ASTRBOT_E2E_SCREENSHOT) {
      await page.screenshot({ path: process.env.ASTRBOT_E2E_SCREENSHOT });
    }
    throw error;
  } finally {
    try { await browser?.close(); } finally {
      await stopBackend();
      await rm(root, { recursive: true, force: true });
    }
  }
});
