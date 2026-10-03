import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';
import ts from 'typescript';
import { computed, nextTick, ref } from 'vue';

const repo = name => `https://github.com/AstrBotDevs/${name}`;
const ok = data => ({ data: { status: 'ok', data } });

function setup(api = {}, overrides = {}) {
  const source = readFileSync(new URL('../src/components/OnboardingSetup.vue', import.meta.url), 'utf8')
    .split('<script setup lang="ts">')[1].split('</script>')[0];
  const ast = ts.createSourceFile('guide.ts', source, ts.ScriptTarget.Latest, true);
  const emitted = [];
  const watchers = [];
  let leave;
  const context = vm.createContext({
    URL, computed, nextTick, ref, watch: (source, callback) => watchers.push({ source, callback }),
    useModuleI18n: () => ({ tm: key => key }),
    useRouter: () => ({ resolve: path => ({ href: `/astrbot/#${path}` }), push: path => emitted.push(path) }),
    onBeforeRouteLeave: callback => { leave = callback; },
    pluginApi: {
      market: async () => ok({
        first: { repo: repo('first'), name: 'First' },
        second: { repo: repo('second'), name: 'Second' },
      }),
      list: async () => ok([]),
      validateRepo: async () => ok({}),
      installGithub: async () => ok({}),
      ...api,
    },
    providerApi: { schema: async () => ok({ providers: [{ id: 'model', provider_type: 'chat_completion' }] }) },
    configProfileApi: {
      get: async () => ok({ config: { agent_runner: { runner_type: 'local', config: { model: { provider_id: 'existing' } } } } }),
      update: async () => { throw new Error('Must not overwrite the default'); },
    },
    systemConfigApi: { runtime: async () => ok({ config: { platform: [] }, metadata: {} }) },
    ...overrides,
  });
  const body = ast.statements.filter(node => !ts.isImportDeclaration(node)).map(node => node.getText(ast)).join('\n');
  vm.runInContext(ts.transpile(body, { target: ts.ScriptTarget.ES2020 }), context);
  const state = vm.runInContext('({ officialRepo, githubRepo, loadPlugins, togglePlugin, installSelected, close, skipStep, finish, computerForm, completed, plugins, pluginGroups, selected, loading, loadError, busy, step, steps, installedCount, nextStep, loadPlatforms, modelReady, platformReady, platformLoading, configError, modelForm, selectedModel })', context);
  return { ...state, emitted, watchers, leave: () => leave() };
}

test('notice comes first, computer access last, and the market is not loaded during trial', async () => {
  let requests = 0;
  const state = setup({ market: async () => { requests++; return ok({}); } });
  assert.deepEqual(Array.from(state.steps.value), ['guide.notice', 'guide.modelTitle', 'guide.chat', 'guide.platform', 'guide.plugins', 'onboard.step3Title']);
  assert.equal(state.step.value, 1);
  await state.nextStep();
  assert.equal(state.step.value, 2);
  const changeStep = state.watchers.find(watcher => watcher.source === state.step).callback;
  changeStep(3);
  assert.equal(requests, 0);
  changeStep(5);
  await new Promise(setImmediate);
  assert.equal(requests, 1);
});

test('only canonical GitHub repositories in the official organization are accepted', () => {
  const { officialRepo } = setup();
  assert.equal(officialRepo('https://github.com/astrbotdevs/First.git/'), repo('first'));
  for (const url of [
    'http://github.com/AstrBotDevs/first', 'https://github.com.evil.test/AstrBotDevs/first',
    'https://github.com/Other/first', 'https://github.com/AstrBotDevs-evil/first',
    'https://github.com/AstrBotDevs/first/tree/main', 'https://github.com/AstrBotDevs/first?ref=evil',
    'https://user@github.com/AstrBotDevs/first', 'javascript:alert(1)', null,
  ]) assert.equal(officialRepo(url), '', String(url));
});

test('community repositories still require canonical HTTPS GitHub URLs', () => {
  const { githubRepo } = setup();
  assert.equal(githubRepo('https://github.com/Community/Useful.git/'), 'https://github.com/community/useful');
  for (const url of [
    'http://github.com/community/plugin', 'https://github.com.evil.test/community/plugin',
    'https://github.com/community/plugin/tree/main', 'https://github.com/community/plugin?ref=evil',
    'https://github.com/community/plugin#main', 'https://user:secret@github.com/community/plugin',
    'https://github.com/community/plugin%2Fevil', 'https://github.com/-invalid/plugin',
    'https://github.com/community/..', 'file:///community/plugin', null,
  ]) assert.equal(githubRepo(url), '', String(url));
});

test('market entries are deduplicated by repo; name collisions do not count as installed', async () => {
  const state = setup({
    market: async () => ok({
      $meta: { name: 'Market' },
      first: { name: 'same-name', repo: repo('First') },
      duplicate: { repo: `${repo('first')}.git` },
      second: { repo: repo('second') },
      impostor: { author: 'AstrBotDevs', repo: 'https://github.com/Other/first' },
    }),
    list: async () => ok([
      { name: 'same-name', repo: 'https://github.com/Other/first' },
      { install_source: { repo: `${repo('second')}.git` } },
    ]),
  });
  await state.loadPlugins();
  assert.equal(state.plugins.value.length, 3);
  assert.equal(state.plugins.value[0].installed, false);
  assert.equal(state.plugins.value[1].installed, true);
  assert.equal(state.plugins.value[2].official, false);
  assert.equal(state.selected.value.length, 0);
});

test('only manually selected visible community recommendations can be installed', async () => {
  const requests = [];
  const market = Object.fromEntries(Array.from({ length: 9 }, (_, index) => [String(index), {
    repo: `https://github.com/community/plugin-${index}`, stars: index * 10, author: 'AstrBotDevs',
  }]));
  market.official = { repo: repo('official'), stars: 2 };
  market.invalid = { repo: 'https://evil.test/AstrBotDevs/plugin', stars: 10000 };
  market.unknown = { repo: 'https://github.com/community/unknown', stars: 'unknown' };
  market.duplicate = { repo: 'https://github.com/Community/PLUGIN-8.git', stars: 999 };
  const state = setup({ market: async () => ok(market), installGithub: async body => { requests.push(body); return ok({}); } });
  await state.loadPlugins();
  assert.equal(state.pluginGroups.value[0].items.length, 1);
  assert.equal(state.pluginGroups.value[0].items[0].repo, repo('official'));
  const popular = state.pluginGroups.value[1].items;
  assert.deepEqual(Array.from(popular, item => item.stars), [80, 70, 60, 50, 40, 30]);
  assert.ok(popular.every(item => !item.official));
  assert.equal(state.selected.value.length, 0);
  await state.installSelected();
  assert.equal(requests.length, 0);
  state.selected.value = [popular[0].repo, 'https://github.com/community/plugin-1', 'https://github.com/unlisted/plugin'];
  await state.installSelected();
  assert.equal(requests.length, 1);
  assert.equal(requests[0].url, popular[0].repo);
  assert.equal(requests[0].ignore_version_check, false);
  assert.equal(popular[0].installed, true);
  assert.equal(state.installedCount.value, 1);
  await state.installSelected();
  assert.equal(requests.length, 1);
});

test('community installation validates first and preserves rejected or incompatible selections for retry', async () => {
  const url = 'https://github.com/community/plugin';
  let valid = false;
  let compatible = false;
  let installs = 0;
  let validations = 0;
  const state = setup({
    market: async () => ok({ plugin: { repo: url, stars: 10 } }),
    validateRepo: async body => {
      assert.equal(body.url, url);
      validations++;
      return valid ? ok({}) : { data: { status: 'error', message: 'Invalid repository' } };
    },
    installGithub: async body => {
      assert.equal(body.url, url);
      assert.equal(body.ignore_version_check, false);
      assert.equal(body.download_url, undefined);
      installs++;
      return compatible ? ok({}) : { data: { status: 'warning', message: 'Unsupported version' } };
    },
  });
  await state.loadPlugins();
  state.selected.value = [url];
  await state.installSelected();
  assert.equal(installs, 0);
  assert.equal(state.plugins.value[0].error, 'Invalid repository');
  valid = true;
  await state.installSelected();
  assert.equal(state.plugins.value[0].error, 'Unsupported version');
  assert.equal(state.plugins.value[0].installed, false);
  assert.deepEqual(Array.from(state.selected.value), [url]);
  compatible = true;
  await state.installSelected();
  assert.equal(validations, 3);
  assert.equal(installs, 2);
  assert.equal(state.plugins.value[0].installed, true);
  assert.equal(state.selected.value.length, 0);
});

test('trial opens embedded ChatUI automatically and keeps it mounted when revisiting steps', () => {
  const source = readFileSync(new URL('../src/components/OnboardingSetup.vue', import.meta.url), 'utf8');
  assert.match(source, /class="guide-chat"><StandaloneChat/);
  assert.doesNotMatch(source, /:href="chatHref"/);
  assert.doesNotMatch(source, /chatOpened|guide\.openChat/);
  assert.match(source, /v-if="modelReady" class="guide-chat"><StandaloneChat/);
  assert.match(source, /guide-scroll \{[^}]*overflow-y: auto/);
  assert.match(source, /guide-actions \{[^}]*flex-shrink: 0/);
  assert.doesNotMatch(source.match(/\.guide-chat \{[^}]*\}/)[0], /border|radius/);
  assert.match(source, /\.guide-chat :deep\(\.input-container\) \{ width: 100% !important; max-width: 100% !important; margin-inline: 0 !important;/);
});

test('all primary footer actions use Next while retaining their handlers', () => {
  const source = readFileSync(new URL('../src/components/OnboardingSetup.vue', import.meta.url), 'utf8');
  const footer = source.split('<footer class="guide-actions">')[1].split('</footer>')[0];
  for (const handler of ['installSelected', 'nextStep', 'finish']) {
    assert.match(footer, new RegExp(`@click="${handler}">\\s*\\{\\{ tm\\('guide.next'\\) \\}\\}`));
  }
  assert.match(footer, /tm\('guide.back'\)/);
  assert.match(footer, /tm\('guide.skipAll'\)/);
  assert.match(footer, /tm\('onboard.skip'\)/);
});

test('adapter skip explains ChatUI availability without blocking or saving', () => {
  const source = readFileSync(new URL('../src/components/OnboardingSetup.vue', import.meta.url), 'utf8');
  const footer = source.split('<footer class="guide-actions">')[1].split('</footer>')[0];
  assert.match(footer, /v-if="step === 4" id="guide-adapter-skip-hint"/);
  assert.match(footer, /tm\('guide.adapterSkipHint'\)/);
  assert.match(footer, /:aria-describedby="step === 4 \? 'guide-adapter-skip-hint' : undefined" @click="skipStep"/);
  const state = setup();
  state.step.value = 4;
  state.skipStep();
  assert.equal(state.step.value, 5);
  assert.equal(state.emitted.length, 0);
  for (const locale of ['zh-CN', 'en-US', 'ja-JP', 'ru-RU']) {
    const messages = JSON.parse(readFileSync(new URL(`../src/i18n/locales/${locale}/features/welcome.json`, import.meta.url), 'utf8'));
    assert.match(messages.guide.adapterSkipHint, /ChatUI/);
  }
});

test('the first-step footer can skip the entire guide without configuration writes', () => {
  const source = readFileSync(new URL('../src/components/OnboardingSetup.vue', import.meta.url), 'utf8');
  assert.match(source, /<v-btn v-else[^>]*@click="close">\{\{ tm\('guide.skipAll'\) \}\}/);
  const state = setup({}, {
    configProfileApi: { update: () => { throw new Error('Skip must not change configuration'); } },
  });
  assert.equal(state.step.value, 1);
  state.close();
  assert.deepEqual(state.emitted, ['/dashboard/default']);
  assert.equal(state.modelReady.value, false);
});

test('onboarding reuses market cards and the settings switch, with the title beside the brand', () => {
  const read = path => readFileSync(new URL(`../src/${path}`, import.meta.url), 'utf8');
  const guide = read('components/OnboardingSetup.vue');
  assert.match(guide, /<MarketPluginCard/);
  assert.match(guide, /#install-action/);
  assert.doesNotMatch(guide, /<v-list-item/);
  assert.match(read('components/extension/MarketPluginCard.vue'), /<slot name="install-action">[\s\S]*handleInstall\(plugin\)/);
  assert.match(read('components/OnboardingComputer.vue'), /<v-switch[\s\S]*inset density="compact" hide-details/);
  const header = read('views/authentication/auth/SetupPage.vue').split('class="setup-brand"')[1].split('</div>')[0];
  assert.match(header, /setup-wordmark/);
  assert.match(header, /<h1.*guide.title/);
  assert.match(guide, /\.guide-content \{ width: 100%; padding: 32px 0 24px/);
});

test('market-card selection is manual and locked while installing or already installed', async () => {
  const state = setup();
  await state.loadPlugins();
  const plugin = state.plugins.value[0];
  state.togglePlugin(plugin);
  assert.deepEqual(Array.from(state.selected.value), [plugin.repo]);
  state.togglePlugin(plugin);
  assert.equal(state.selected.value.length, 0);
  state.busy.value = true;
  state.togglePlugin(plugin);
  assert.equal(state.selected.value.length, 0);
  state.busy.value = false;
  plugin.installed = true;
  state.togglePlugin(plugin);
  assert.equal(state.selected.value.length, 0);
});

test('market errors remain retryable and never install anything', async () => {
  let fail = true;
  const state = setup({ market: async () => fail ? { data: { status: 'error' } } : ok({}) });
  await state.loadPlugins();
  assert.equal(state.loadError.value, 'guide.loadFailed');
  assert.equal(state.loading.value, false);
  fail = false;
  await state.loadPlugins();
  assert.equal(state.loadError.value, '');
});

test('partial failures stay selected; retry skips successes and never overrides version checks', async () => {
  const requests = [];
  let fail = true;
  const state = setup({ installGithub: async body => {
    requests.push(body);
    return body.url === repo('first') && fail
      ? { data: { status: 'warning', message: 'Unsupported version' } } : ok({});
  } });
  await state.loadPlugins();
  state.step.value = 5;
  state.selected.value = [repo('first'), repo('second')];
  await state.installSelected();
  assert.equal(state.step.value, 5);
  assert.equal(state.emitted.length, 0);
  assert.equal(state.plugins.value[0].error, 'Unsupported version');
  assert.equal(state.plugins.value[1].installed, true);
  fail = false;
  await state.installSelected();
  assert.equal(state.step.value, 5);
  assert.equal(state.emitted.length, 0);
  assert.equal(state.installedCount.value, 2);
  assert.deepEqual(requests.map(r => r.url), [repo('first'), repo('second'), repo('first')]);
  assert.ok(requests.every(r => r.ignore_version_check === false && !r.download_url));
});

test('an in-flight install blocks duplicate requests, dismissal and route changes', async () => {
  let resolve;
  let requests = 0;
  const state = setup({ installGithub: () => {
    requests++;
    return new Promise(done => { resolve = done; });
  } });
  await state.loadPlugins();
  state.selected.value = [repo('first')];
  const pending = state.installSelected();
  await new Promise(setImmediate);
  await state.installSelected();
  state.close();
  assert.equal(requests, 1);
  assert.equal(state.leave(), false);
  assert.equal(state.emitted.length, 0);
  resolve(ok({}));
  await pending;
  assert.equal(state.leave(), true);
  state.close();
  assert.deepEqual(state.emitted, ['/dashboard/default']);
});

test('model form failure stays in place; success selects the saved model instead of the first provider', async () => {
  let saved;
  const state = setup({}, {
    providerApi: { schema: async () => ok({ providers: [
      { id: 'first', provider_type: 'chat_completion' }, { id: 'chosen', provider_type: 'chat_completion' },
    ] }) },
    configProfileApi: {
      get: async () => ok({ config: { agent_runner: { runner_type: 'local', config: { model: { provider_id: '' } } } } }),
      update: async (_, config) => { saved = config.agent_runner.config.model.provider_id; return ok({}); },
    },
  });
  state.modelForm.value = { save: async () => undefined };
  state.step.value = 2;
  await state.nextStep();
  assert.equal(state.step.value, 2);
  assert.equal(saved, undefined);
  state.modelForm.value = { save: async () => 'chosen' };
  await state.nextStep();
  assert.equal(state.step.value, 3);
  assert.equal(saved, 'chosen');
  assert.equal(state.selectedModel.value, 'chosen');
});

function modelSetup(overrides = {}, api = {}) {
  const source = readFileSync(new URL('../src/components/OnboardingModel.vue', import.meta.url), 'utf8')
    .split('<script setup lang="ts">')[1].split('</script>')[0];
  const ast = ts.createSourceFile('model.ts', source, ts.ScriptTarget.Latest, true);
  const calls = [];
  const state = {
    selectedProviderSource: ref({ id: 'source' }), editableProviderSource: ref({}),
    availableModels: ref([]), displayedProviderSources: ref([]), availableSourceTypes: ref([]),
    loadingModels: ref(false), isSourceModified: ref(true), sourceProviders: ref([]),
    saveProviderSource: async () => { calls.push('source'); return true; },
    buildModelProviderConfig: name => ({ id: `source/${name}`, provider_source_id: 'source', model: name, enable: true }),
    loadConfig: async () => { calls.push('reload'); },
    ...overrides,
  };
  const context = vm.createContext({
    computed, ref, watch() {}, defineProps() {}, defineEmits: () => () => {}, defineExpose() {},
    useModuleI18n: () => ({ tm: key => key }), useProviderSources: () => state,
    providerApi: {
      createInSource: async (id, config) => { calls.push(['create', id, config]); return ok({}); },
      update: async (id, config) => { calls.push(['update', id, config]); return ok({}); },
      ...api,
    },
  });
  const body = ast.statements.filter(node => !ts.isImportDeclaration(node)).map(node => node.getText(ast)).join('\n');
  vm.runInContext(ts.transpile(body, { target: ts.ScriptTarget.ES2020 }), context);
  return { ...vm.runInContext('({ save, model, error, ready })', context), calls };
}

test('focused model form saves credentials and model together, trimming the model ID', async () => {
  const state = modelSetup();
  assert.equal(state.ready.value, false);
  await state.save();
  assert.deepEqual(state.calls, []);
  state.model.value = ' demo-model ';
  assert.equal(await state.save(), 'source/demo-model');
  assert.equal(state.calls[0], 'source');
  assert.equal(state.calls[1][0], 'create');
  assert.equal(state.calls[1][2].model, 'demo-model');
});

test('focused form preserves failures and never creates a model after credential failure', async () => {
  const failedSource = modelSetup({ saveProviderSource: async () => false });
  failedSource.model.value = 'model';
  assert.equal(await failedSource.save(), undefined);
  assert.deepEqual(failedSource.calls, []);
  const failedModel = modelSetup({}, { createInSource: async () => ({ data: { status: 'error', message: 'Rejected' } }) });
  failedModel.model.value = 'model';
  assert.equal(await failedModel.save(), undefined);
  assert.equal(failedModel.error.value, 'Rejected');
  assert.equal(failedModel.model.value, 'model');
});

test('focused form reuses configured models and only enables the selected disabled model', async () => {
  for (const enabled of [true, false]) {
    const state = modelSetup({ isSourceModified: ref(false), sourceProviders: ref([{ id: 'existing', model: 'model', enable: enabled }]) });
    state.model.value = 'model';
    assert.equal(await state.save(), 'existing');
    if (enabled) assert.deepEqual(state.calls, []);
    else {
      assert.equal(state.calls[0][0], 'update');
      assert.equal(state.calls[0][2].enable, true);
    }
  }
});

test('continuing requires a saved enabled chat model and preserves an existing default', async () => {
  const state = setup();
  state.step.value = 2;
  await state.nextStep();
  assert.equal(state.configError.value, '');
  assert.equal(state.modelReady.value, true);
  assert.equal(state.step.value, 3);
  for (const providers of [[], [{ id: 'disabled', provider_type: 'chat_completion', enable: false }],
    [{ id: 'embedding', provider_type: 'embedding', type: 'chat_completion' }]]) {
    const invalid = setup({}, { providerApi: { schema: async () => ok({ providers }) } });
    invalid.step.value = 2;
    await invalid.nextStep();
    assert.equal(invalid.step.value, 2);
    assert.equal(invalid.modelReady.value, false);
    assert.equal(invalid.configError.value, 'guide.modelPending');
  }
});

test('an empty default is assigned before trial; save failures stay on the model step', async () => {
  let fail = true;
  const state = setup({}, {
    providerApi: { schema: async () => ok({ providers: [{ id: 'new', provider_source_id: 'source' }], provider_sources: [{ id: 'source', provider_type: 'chat_completion' }] }) },
    configProfileApi: {
      get: async () => ok({ config: { agent_runner: { runner_type: 'local', config: { model: { provider_id: '' } } } } }),
      update: async (_, config) => {
        assert.equal(config.agent_runner.config.model.provider_id, 'new');
        return fail ? { data: { status: 'error', message: 'Save failed' } } : ok({});
      },
    },
  });
  state.step.value = 2;
  await state.nextStep();
  assert.equal(state.step.value, 2);
  assert.equal(state.configError.value, 'Save failed');
  fail = false;
  await state.nextStep();
  assert.equal(state.step.value, 3);
  assert.equal(state.busy.value, false);
});

test('platform metadata failures can be retried without marking configuration complete', async () => {
  let fail = true;
  const state = setup({}, { systemConfigApi: { runtime: async () => fail
    ? { data: { status: 'error', message: 'Unavailable' } } : ok({ config: { platform: [{ id: 'bot' }] } }) } });
  await state.loadPlatforms();
  assert.equal(state.platformReady.value, false);
  assert.equal(state.configError.value, 'Unavailable');
  fail = false;
  await state.loadPlatforms();
  assert.equal(state.platformReady.value, true);
  assert.equal(state.configError.value, '');
});

test('only successful account setup continues onboarding; login and configured instances keep their destinations', async () => {
  const source = readFileSync(new URL('../src/stores/auth.ts', import.meta.url), 'utf8');
  const ast = ts.createSourceFile('auth.ts', source, ts.ScriptTarget.Latest, true);
  const body = ast.statements.filter(node => !ts.isImportDeclaration(node)).map(node => node.getText(ast)).join('\n');
  const destinations = [];
  const session = { username: 'astrbot', token: 'test-token' };
  let actions;
  let fail = false;
  const context = vm.createContext({
    exports: {}, console,
    defineStore: (_, options) => { actions = options.actions; },
    router: { push: path => destinations.push(path), replace: path => destinations.push(path) },
    localStorage: { setItem() {}, removeItem() {} },
    authApi: { setup: async () => fail ? { data: { status: 'error', message: 'Setup rejected' } } : ok(session) },
  });
  vm.runInContext(ts.transpile(body, { module: ts.ModuleKind.CommonJS }), context);
  const auth = { ...actions, checkOnboardingCompleted: async () => false };
  await auth.setup('astrbot', 'test-password', 'test-password');
  assert.equal(destinations.pop(), '/auth/onboarding');
  await auth.finishAuthenticatedSession(session);
  assert.equal(destinations.pop(), '/dashboard/default');
  await auth.finishAuthenticatedSession({ ...session, change_pwd_hint: true }, true);
  assert.equal(destinations.pop(), '/auth/setup');
  auth.checkOnboardingCompleted = async () => true;
  await auth.setup('astrbot', 'test-password', 'test-password');
  assert.equal(destinations.pop(), '/dashboard/default');
  fail = true;
  await assert.rejects(auth.setup('astrbot', 'test-password', 'test-password'));
  assert.deepEqual(destinations, []);
});

test('setup page gates configuration on authentication and completed password setup', async () => {
  const source = readFileSync(new URL('../src/views/authentication/auth/SetupPage.vue', import.meta.url), 'utf8')
    .split('<script setup lang="ts">')[1].split('</script>')[0];
  const ast = ts.createSourceFile('setup.ts', source, ts.ScriptTarget.Latest, true);
  const watcher = ast.statements.find(node => ts.isExpressionStatement(node) && node.getText(ast).startsWith('watch(isOnboarding,'));
  for (const [onboarding, token, required, skip, destination, expectedReady] of [
    [true, false, false, false, '/auth/login', false],
    [true, true, true, false, '/auth/setup', false],
    [true, true, false, false, undefined, true],
    [false, false, true, false, '/auth/login', false],
    [false, false, true, true, undefined, true],
    [false, true, true, false, undefined, true],
  ]) {
    let initialize;
    let redirected;
    const ready = ref(false);
    vm.runInNewContext(ts.transpile(watcher.getText(ast)), {
      ready, isOnboarding: onboarding, watch: (_, callback) => { initialize = callback; },
      authStore: { has_token: () => token },
      authApi: { setupStatus: async () => ok({ setup_required: required, skip_default_password_auth: skip }) },
      router: { replace: path => { redirected = path; } },
    });
    await initialize(onboarding, undefined, () => {});
    assert.equal(ready.value, expectedReady);
    assert.equal(redirected, destination);
  }
});

function computerSetup(api = {}) {
  const source = readFileSync(new URL('../src/components/OnboardingComputer.vue', import.meta.url), 'utf8')
    .split('<script setup lang="ts">')[1].split('</script>')[0];
  const ast = ts.createSourceFile('computer.ts', source, ts.ScriptTarget.Latest, true);
  const context = vm.createContext({
    computed, ref, onMounted() {}, defineProps() {}, defineExpose() {},
    useModuleI18n: () => ({ tm: key => key }),
    configProfileApi: {
      get: async () => ok({ config: { provider_settings: { computer_use_runtime: 'none' } } }),
      update: async () => { throw new Error('Unexpected permission change'); },
      ...api,
    },
  });
  const body = ast.statements.filter(node => !ts.isImportDeclaration(node)).map(node => node.getText(ast)).join('\n');
  vm.runInContext(ts.transpile(body, { target: ts.ScriptTarget.ES2020 }), context);
  return vm.runInContext('({ load, save, allowed, originalRuntime, error, ready, loading })', context);
}

test('computer access stays off on a fresh instance and preserves existing local and sandbox configurations', async () => {
  for (const runtime of [undefined, 'none', 'local', 'sandbox']) {
    let writes = 0;
    const state = computerSetup({
      get: async () => ok({ config: { provider_settings: { computer_use_runtime: runtime } } }),
      update: async () => { writes++; return ok({}); },
    });
    assert.equal(state.allowed.value, false);
    assert.equal(state.ready.value, false);
    await state.load();
    assert.equal(state.allowed.value, ['local', 'sandbox'].includes(runtime));
    assert.equal(await state.save(), true);
    assert.equal(writes, 0);
  }
});

test('an explicit computer permission change preserves fresh unrelated settings and retries failed writes', async () => {
  let fail = true;
  let saved;
  let reads = 0;
  const state = computerSetup({
    get: async () => ok({ config: { revision: ++reads, provider_settings: { computer_use_runtime: 'none', other: 'keep' } } }),
    update: async (_, config) => {
      saved = config;
      return fail ? { data: { status: 'error', message: 'Rejected' } } : ok({});
    },
  });
  await state.load();
  state.allowed.value = true;
  assert.equal(saved, undefined);
  assert.equal(await state.save(), false);
  assert.equal(state.error.value, 'Rejected');
  assert.equal(state.allowed.value, true);
  assert.equal(state.ready.value, true);
  fail = false;
  assert.equal(await state.save(), true);
  assert.equal(saved.revision, 3);
  assert.deepEqual(saved.provider_settings, { computer_use_runtime: 'local', other: 'keep' });
  state.allowed.value = false;
  assert.equal(await state.save(), true);
  assert.equal(saved.provider_settings.computer_use_runtime, 'none');
});

test('failed or malformed permission reads cannot write and remain retryable', async () => {
  let fail = true;
  const state = computerSetup({ get: async () => fail ? ok({ config: {} }) : ok({ config: { provider_settings: {} } }) });
  await state.load();
  assert.equal(state.ready.value, false);
  assert.equal(await state.save(), false);
  assert.equal(state.loading.value, false);
  fail = false;
  await state.load();
  assert.equal(state.ready.value, true);
  assert.equal(state.error.value, '');
});

test('skipping never saves permissions; finish stays in place on failure and blocks concurrent navigation', async () => {
  const skipped = setup();
  skipped.step.value = 6;
  skipped.computerForm.value = { ready: true, save: () => { throw new Error('Must not save on skip'); } };
  skipped.skipStep();
  assert.deepEqual(skipped.emitted, ['/dashboard/default']);
  assert.equal(skipped.completed.value, false);
  const state = setup();
  state.step.value = 2;
  state.skipStep();
  assert.equal(state.step.value, 4);
  state.step.value = 6;
  let resolve;
  state.computerForm.value = { ready: true, save: () => new Promise(done => { resolve = done; }) };
  const pending = state.finish();
  assert.equal(state.leave(), false);
  state.skipStep();
  assert.equal(state.emitted.length, 0);
  resolve(false);
  await pending;
  assert.equal(state.busy.value, false);
  assert.equal(state.step.value, 6);
  assert.equal(state.emitted.length, 0);
  assert.equal(state.completed.value, false);
  let saves = 0;
  state.computerForm.value = { ready: true, save: async () => { saves++; return true; } };
  await state.finish();
  assert.equal(state.completed.value, true);
  assert.equal(state.emitted.length, 0);
  assert.equal(state.leave(), true);
  await state.finish();
  assert.equal(saves, 1);
  state.close();
  assert.deepEqual(state.emitted, ['/dashboard/default']);
});

test('welcome celebrates from both sides once, respects reduced motion and cleans up its canvas', () => {
  const source = readFileSync(new URL('../src/components/OnboardingWelcome.vue', import.meta.url), 'utf8');
  const script = source.split('<script setup lang="ts">')[1].split('</script>')[0];
  const ast = ts.createSourceFile('welcome.ts', script, ts.ScriptTarget.Latest, true);
  let mount, unmount, options, target, focused = false, resets = 0;
  const bursts = [];
  const celebrate = options => bursts.push(options);
  celebrate.reset = () => { resets++; };
  const context = vm.createContext({
    ref, onMounted: callback => { mount = callback; }, onBeforeUnmount: callback => { unmount = callback; },
    useModuleI18n: () => ({ tm: key => key }),
    confetti: { create: (canvas, config) => { target = canvas; options = config; return celebrate; } },
  });
  const body = ast.statements.filter(node => !ts.isImportDeclaration(node)).map(node => node.getText(ast)).join('\n');
  vm.runInContext(ts.transpile(body, { target: ts.ScriptTarget.ES2020 }), context);
  const state = vm.runInContext('({ canvas, heading })', context);
  state.canvas.value = {};
  state.heading.value = { focus: () => { focused = true; } };
  mount();
  assert.equal(target, state.canvas.value);
  assert.equal(focused, true);
  assert.equal(options.resize, true);
  assert.equal(options.disableForReducedMotion, true);
  assert.deepEqual(bursts.map(burst => [burst.origin.x, burst.origin.y, burst.angle]), [[0, 0.68, 60], [1, 0.68, 120]]);
  assert.ok(bursts.every(burst => burst.particleCount > 0 && burst.ticks <= 200));
  unmount();
  assert.equal(resets, 1);
  assert.match(source, /aria-hidden="true"/);
  assert.match(source, /pointer-events: none/);
  const guide = readFileSync(new URL('../src/components/OnboardingSetup.vue', import.meta.url), 'utf8');
  assert.match(guide, /<OnboardingWelcome v-if="completed"/);
  assert.match(guide, /v-if="completed"[^>]*@click="close">\{\{ tm\('guide.start'\) \}\}/);
});

test('settings owns reentry, the legacy welcome URL redirects, and first notice is embedded only in onboarding', () => {
  const read = path => readFileSync(new URL(`../src/${path}`, import.meta.url), 'utf8');
  assert.match(read('views/Settings.vue'), /to="\/auth\/onboarding"/);
  assert.match(read('router/MainRoutes.ts'), /path: '\/welcome',\s*redirect: '\/dashboard\/default'/);
  assert.doesNotMatch(read('router/MainRoutes.ts'), /WelcomePage/);
  assert.doesNotMatch(read('layouts/full/vertical-sidebar/sidebarItem.ts'), /\/welcome/);
  assert.doesNotMatch(read('layouts/full/FullLayout.vue'), /ReadmeDialog|firstNotice|first-notice/);
  assert.match(read('components/OnboardingSetup.vue'), /<ReadmeDialog embedded :show="step === 1" mode="first-notice"/);
  assert.match(read('components/shared/ReadmeDialog.vue'), /embedded \? 'section' : VDialog/);
});
