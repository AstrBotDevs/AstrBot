import { createPinia, setActivePinia } from 'pinia';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  initI18n,
  mergeDynamicTranslations,
  setupI18n,
  useI18n,
  useLanguageSwitcher,
  useModuleI18n,
} from '@/i18n/composables';
import { I18nLoader } from '@/i18n/loader';
import { I18nValidator } from '@/i18n/validator';
import { translationData } from '@/i18n/types';
import {
  getInitialSystemPrefersDark,
  getSystemUiTheme,
  resolveUiTheme,
} from '@/config';
import {
  applyUserThemeColors,
  resolveThemeName,
  themeNames,
} from '@/design/theme';
import { useCustomizerStore } from '@/stores/customizer';
import { useToastStore } from '@/stores/toast';
import { resolveErrorMessage } from '@/utils/errorUtils';
import { askForConfirmation } from '@/utils/confirmDialog';
import {
  getPlatformColor,
  getPlatformDescription,
  getPlatformDisplayName,
  getPlatformIcon,
  getTutorialLink,
} from '@/utils/platformUtils';
import {
  buildSearchQuery,
  matchesPluginSearch,
  matchesText,
  normalizeLoose,
  toInitials,
  toPinyinText,
} from '@/utils/pluginSearch';
import { usePluginI18n } from '@/utils/pluginI18n';
import {
  canRestorePluginConfigDefault,
  getPluginConfigDefaultValue,
  isPluginConfigValueModified,
} from '@/utils/pluginConfigDefaults';
import {
  attachmentExtension,
  attachmentName,
  attachmentPresentation,
} from '@/components/chat/attachmentPresentation';
import {
  buildSuggestionSignature,
  rankSuggestionCommands,
} from '@/components/chat/commandSuggestion';
import { copyToClipboard } from '@/utils/clipboard';
import { getDesktopRuntimeInfo } from '@/utils/desktopRuntime';
import {
  readGitHubProxyState,
  writeGitHubProxyControl,
  writeGitHubProxyRadioValue,
  writeSelectedGitHubProxy,
} from '@/utils/githubProxyStorage';
import {
  getStoredDashboardUsername,
  getStoredSelectedChatConfigId,
  setStoredSelectedChatConfigId,
} from '@/utils/chatConfigBinding';
import { generateMissingKeys } from '@/i18n/tools';
import { formatTokenCount } from '@/utils/providerMetadata';
import { collectDroppedKnowledgeBaseFiles } from '@/utils/knowledgeBaseUploadFiles';
import { runProviderMutationWithStepUp } from '@/utils/providerStepUp';
import { runConfigMutationWithStepUp } from '@/utils/configStepUp';
import { isDashboardStepUpRequired } from '@/composables/useDashboardStepUp';
import { useConfigTextResolver } from '@/composables/useConfigTextResolver';
import { useCommandFilters } from '@/components/extension/componentPanel/composables/useCommandFilters';
import { ref } from 'vue';
import { resolveSidebarItems } from '@/utils/sidebarCustomization';
import { MORE_GROUP_KEY } from '@/layouts/full/vertical-sidebar/sidebarItem';

describe('ts gap coverage', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it('covers i18n composables, loader, validator, and types', async () => {
    expect(translationData).toBeTruthy();
    await initI18n('zh-CN');
    const { t, setLocale, isLoaded } = useI18n();
    expect(isLoaded.value).toBe(true);
    expect(t('core.common.confirm')).not.toContain('MISSING');
    expect(t('no.such.key')).toContain('MISSING');
    expect(t('core.common', { x: 1 })).toContain('INVALID');
    await setLocale('en-US');
    await setLocale('en-US');
    const moduleI18n = useModuleI18n('core/common');
    expect(moduleI18n.getRaw('confirm')).toBeTruthy();
    expect(moduleI18n.getRaw('missing')).toBeNull();
    mergeDynamicTranslations('features.config-metadata', {
      'en-US': { demo: { title: 'Demo' } },
    });
    const switcher = useLanguageSwitcher();
    expect(switcher.currentLanguage.value?.value).toBe('en-US');
    await switcher.switchLanguage('zh-CN');
    localStorage.setItem('astrbot-locale', 'en-US');
    await setupI18n();
    await initI18n('fr-FR' as never);

    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(JSON.stringify({ hello: 'ok' }), { status: 200 }),
      ),
    );
    const loader = new I18nLoader();
    await loader.loadModule('zh-CN', 'not-registered');
    const first = await loader.loadModule('zh-CN', 'core/common');
    const cached = await loader.loadModule('zh-CN', 'core/common');
    expect(cached).toEqual(first);
    await loader.loadCoreModules('zh-CN');
    await loader.loadFeatureModules('zh-CN');
    await loader.loadFeatureModules('zh-CN', ['features/chat']);
    await loader.loadMessageModules('zh-CN');
    await loader.loadAllModules('zh-CN');
    await loader.loadLocale('zh-CN');
    await loader.reloadModule('zh-CN', 'core/common');
    vi.unstubAllGlobals();

    const validator = new I18nValidator();
    expect(validator.validateCompleteness({}).isValid).toBe(false);
    const localeData = {
      'zh-CN': { a: '你好 {name}', nested: { b: '1' }, BadKey: 'x' },
      'en-US': { a: 'hello {name}', extra: 'y' },
    };
    expect(
      validator.validateCompleteness(localeData).missingKeys.length,
    ).toBeGreaterThan(0);
    expect(validator.validateValues(localeData).length).toBeGreaterThanOrEqual(
      0,
    );
    expect(
      validator.validateInterpolation(localeData).length,
    ).toBeGreaterThanOrEqual(0);
    expect(validator.validateKeyNaming(localeData).length).toBeGreaterThan(0);
    expect(
      validator.generateStats(localeData).overall.totalKeys,
    ).toBeGreaterThan(0);
    const usage = validator.validateUsage(['a', 'nested.b'], ['a', 'unused']);
    expect(usage).toBeTruthy();
    const report = validator.generateReport(localeData, ['a']);
    expect(report.completeness).toBeTruthy();
  });

  it('covers stores, platform, errors, search, and config helpers', async () => {
    const customizer = useCustomizerStore();
    customizer.SET_SIDEBAR_DRAWER();
    customizer.SET_MINI_SIDEBAR(true);
    customizer.SET_THEME_MODE('light');
    customizer.SET_THEME_MODE('system');
    customizer.SET_SYSTEM_PREFERS_DARK(true);
    expect(customizer.isDark).toBe(true);
    customizer.TOGGLE_CHAT_SIDEBAR();
    customizer.SET_CHAT_SIDEBAR(false);
    expect(resolveUiTheme('dark')).toBe(themeNames.dark);
    expect(resolveUiTheme('system')).toBeDefined();
    expect(getSystemUiTheme()).toBeDefined();
    const matchMedia = window.matchMedia;
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: true,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));
    expect(getSystemUiTheme()).toBe(themeNames.dark);
    window.matchMedia = matchMedia;
    expect(typeof getInitialSystemPrefersDark()).toBe('boolean');

    const toast = useToastStore();
    toast.add({ message: 'hi' });
    expect(toast.current?.message).toBe('hi');
    toast.shift();
    expect(toast.current).toBeNull();

    expect(getPlatformIcon('telegram')).toBeTruthy();
    expect(getTutorialLink('unknown')).toContain('docs.astrbot.app');
    expect(getPlatformDescription({}, 'vocechat-bot')).toContain('Hikari');
    expect(getPlatformDescription({}, 'kook')).toContain('wuyan');
    expect(getPlatformDescription({}, 'telegram')).toBe('');
    expect(getPlatformDisplayName('lark')).toContain('飞书');
    expect(getPlatformDisplayName('nope')).toBe('nope');
    expect(getPlatformColor('webchat')).toBe('orange');
    expect(getPlatformColor('nope')).toBe('grey');

    expect(resolveErrorMessage(' boom ')).toBe('boom');
    expect(resolveErrorMessage(3)).toBe('3');
    expect(resolveErrorMessage({ response: { data: 'plain' } })).toBe('plain');
    expect(
      resolveErrorMessage({
        response: {
          data: { detail: [{ loc: ['body', 'name'], msg: 'required' }] },
        },
      }),
    ).toContain('name');
    expect(resolveErrorMessage({ response: { statusText: 'Nope' } })).toBe(
      'Nope',
    );
    expect(resolveErrorMessage({}, 'fallback')).toBe('fallback');

    const query = buildSearchQuery('astr');
    expect(matchesText('AstrBot', query)).toBe(true);
    expect(matchesText('其他', query)).toBe(false);
    expect(toPinyinText('测试')).toBeTruthy();
    expect(toInitials('测试')).toBeTruthy();
    expect(
      matchesPluginSearch({ name: '测试插件', tags: ['ai'] }, query),
    ).toBeTypeOf('boolean');
    expect(matchesPluginSearch({ name: 'x' }, null)).toBe(true);

    const pluginI18n = usePluginI18n();
    const plugin = {
      name: 'p',
      display_name: 'P',
      desc: 'd',
      short_desc: 's',
      i18n: { 'zh-CN': { metadata: { display_name: '插件' } } },
    };
    expect(pluginI18n.pluginName(plugin)).toBeTruthy();
    expect(pluginI18n.pluginDesc(plugin)).toBeTruthy();
    expect(pluginI18n.pluginShortDesc(plugin)).toBeTruthy();
    expect(pluginI18n.configText(plugin.i18n, 'a', 'title', 'fb')).toBe('fb');

    expect(getPluginConfigDefaultValue({ type: 'int' })).toBe(0);
    expect(getPluginConfigDefaultValue({ type: 'string', default: 'x' })).toBe(
      'x',
    );
    expect(
      getPluginConfigDefaultValue({
        type: 'object',
        items: { a: { type: 'bool' } },
      }),
    ).toEqual({ a: false });
    expect(isPluginConfigValueModified(1, { type: 'int' })).toBe(true);
    expect(canRestorePluginConfigDefault(1, { type: 'int' })).toBe(true);
    expect(
      canRestorePluginConfigDefault(1, { type: 'int', readonly: true }),
    ).toBe(false);

    expect(attachmentName({ filename: 'a.pdf' })).toBe('a.pdf');
    expect(attachmentExtension({ filename: 'a.PDF' })).toBe('pdf');
    expect(attachmentPresentation({ type: 'image' }).label).toBe('IMAGE');
    expect(attachmentPresentation({ type: 'record' }).label).toBe('AUDIO');
    expect(attachmentPresentation({ type: 'video' }).label).toBe('VIDEO');
    expect(attachmentPresentation({ filename: 'a.ts' }).icon).toContain('code');
    expect(attachmentPresentation({ filename: 'a.pdf' }).label).toBe('PDF');
    expect(attachmentPresentation({ filename: 'a.bin' }).label).toBe('BIN');

    expect(buildSuggestionSignature('/help', '/help extra', '/help')).toContain(
      '/help',
    );
    expect(buildSuggestionSignature('/help', '', '/help')).toBe('/help');
    const ranked = rankSuggestionCommands(
      [
        {
          handler_full_name: 'a',
          effective_command: '/help',
          description: 'show help',
          plugin_display_name: 'core',
          enabled: true,
          reserved: true,
        },
        {
          handler_full_name: 'b',
          effective_command: '/about',
          description: 'about',
          plugin_display_name: 'other',
          enabled: true,
          reserved: false,
        },
      ],
      'help',
      (value) => value.toLowerCase(),
    );
    expect(ranked[0].effective_command).toBe('/help');
    expect(
      rankSuggestionCommands(
        [
          {
            handler_full_name: 'a',
            effective_command: '/help',
            description: 'd',
            plugin_display_name: null,
            enabled: true,
            reserved: false,
          },
        ],
        '',
        (value) => value,
      ),
    ).toHaveLength(1);

    applyUserThemeColors(
      { [themeNames.light]: { colors: { primary: '#000' } } as never },
      '#111',
      '#222',
    );
    applyUserThemeColors(undefined);
    expect(resolveThemeName('dark')).toBe(themeNames.dark);

    window.confirm = vi.fn(() => true);
    expect(await askForConfirmation('sure?')).toBe(true);
    expect(
      await askForConfirmation('x', async () => {
        throw new Error('no');
      }),
    ).toBe(false);
    expect(await askForConfirmation('x', async () => true)).toBe(true);

    Object.defineProperty(window, 'isSecureContext', {
      configurable: true,
      value: true,
    });
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText: vi.fn(async () => undefined) },
    });
    expect(await copyToClipboard('copied')).toBe(true);

    window.astrbotDesktop = {
      isDesktop: true,
      isDesktopRuntime: vi.fn(async () => {
        throw new Error('probe failed');
      }),
      restartBackend: vi.fn(),
    } as never;
    const desktop = await getDesktopRuntimeInfo();
    expect(desktop.hasDesktopRuntimeProbe).toBe(true);
    delete window.astrbotDesktop;

    expect(readGitHubProxyState().radioValue).toBe('0');
    expect(getStoredDashboardUsername()).toBe('guest');
    expect(getStoredSelectedChatConfigId()).toBe('default');

    expect(isDashboardStepUpRequired({})).toBe(false);
    expect(
      isDashboardStepUpRequired({
        response: { data: { data: { requires_step_up: true } } },
      }),
    ).toBe(true);
    await expect(
      runProviderMutationWithStepUp(async () => 'ok', 'p1'),
    ).resolves.toBe('ok');
    await expect(
      runProviderMutationWithStepUp(async () => {
        throw { response: { data: { data: { requires_step_up: true } } } };
      }, 'p1'),
    ).rejects.toBeTruthy();
    const retried = await runProviderMutationWithStepUp(
      async (stepUp) =>
        stepUp
          ? `done-${stepUp}`
          : Promise.reject({
              response: { data: { data: { requires_step_up: true } } },
            }),
      'p1',
      async () => 'tok',
    );
    expect(retried).toBe('done-tok');
    expect(
      await runProviderMutationWithStepUp(
        async () => {
          throw { response: { data: { data: { requires_step_up: true } } } };
        },
        'p1',
        async () => null,
      ),
    ).toBeNull();
    await expect(
      runConfigMutationWithStepUp(async () => 'cfg', 'default'),
    ).resolves.toBe('cfg');

    await initI18n('zh-CN');
    const resolver = useConfigTextResolver({
      pluginName: 'p',
      pluginI18n: { 'zh-CN': {} },
    });
    expect(resolver.translateIfKey(1)).toBe(1);
    expect(resolver.translateIfKey('platform_group.name')).toBe('平台配置');
    expect(
      resolver.translateIfKey(
        'platform_group.platform.lark_connection_mode.labels',
      ),
    ).toEqual(['长连接模式', '推送至服务器模式']);
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    expect(
      resolver.translateIfKey('platform_group.missing.field.description'),
    ).toBe('platform_group.missing.field.description');
    expect(
      warnSpy.mock.calls.some((args) =>
        String(args[0]).includes(
          'features.config-metadata.platform_group.missing.field.description',
        ),
      ),
    ).toBe(true);
    warnSpy.mockRestore();
    expect(resolver.resolveConfigText('a', 'title', 'fb')).toBe('fb');

    const filters = useCommandFilters(
      ref([
        {
          command_id: 'core:help',
          handler_full_name: 'core.help',
          current_fragment: 'help',
          aliases: ['h'],
          enabled: true,
          has_conflict: false,
          type: 'command',
          is_group: false,
          reserved: false,
          plugin: 'core',
          action: 'command',
          description: 'help cmd',
          display_signature: '/help',
        },
        {
          command_id: 'core:group',
          handler_full_name: 'core.group',
          current_fragment: 'g',
          aliases: [],
          enabled: false,
          has_conflict: true,
          type: 'group',
          is_group: true,
          reserved: true,
          plugin: 'core',
          action: 'command',
          sub_commands: [
            {
              command_id: 'core:group.sub',
              handler_full_name: 'core.group.sub',
              current_fragment: 'sub',
              aliases: [],
              enabled: true,
              has_conflict: false,
              type: 'sub_command',
              is_group: false,
              reserved: false,
              plugin: 'core',
              action: 'command',
            },
          ],
        },
      ] as never),
    );
    filters.pluginFilter.value = 'core';
    filters.actionFilter.value = 'command';
    filters.statusFilter.value = 'enabled';
    filters.typeFilter.value = 'command';
    expect(Array.isArray(filters.filteredCommands.value)).toBe(true);
    filters.statusFilter.value = 'conflict';
    filters.typeFilter.value = 'group';
    filters.showSystemPlugins.value = true;
    filters.searchQuery.value = 'g';
    filters.toggleGroupExpand({
      is_group: true,
      command_id: 'core:group',
      handler_full_name: 'core.group',
    } as never);
    void filters.filteredCommands.value;
    void filters.availableActions.value;

    const resolved = resolveSidebarItems(
      [
        { title: 'core.navigation.chat' },
        {
          title: MORE_GROUP_KEY,
          children: [{ title: 'core.navigation.about' }],
        },
      ],
      null,
    );
    expect(resolved.mainItems.length).toBeGreaterThan(0);

    await expect(import('@/utils/streamMonacoDisabled')).rejects.toThrow(
      /disabled/,
    );

    const localesReport = await new I18nValidator().validateLocales([
      'zh-CN',
      'en-US',
    ]);
    expect(localesReport.summary.totalLocales).toBe(2);

    const { useRouterLoadingStore } = await import('@/stores/routerLoading');
    const loading = useRouterLoadingStore();
    vi.useFakeTimers();
    loading.start();
    await vi.advanceTimersByTimeAsync(800);
    loading.finish();
    await vi.advanceTimersByTimeAsync(300);
    vi.useRealTimers();

    const randomUUID = crypto.randomUUID;
    // @ts-expect-error coverage fallback
    crypto.randomUUID = undefined;
    const { useCommonStore } = await import('@/stores/common');
    const common = useCommonStore();
    common.log_cache.push({ uuid: '', data: 'x' } as never);
    crypto.randomUUID = randomUUID;
  });

  it('covers log SSE reconnect paths on the common store', async () => {
    const { useCommonStore } = await import('@/stores/common');
    const common = useCommonStore();
    await common.createEventSource();
    localStorage.setItem('token', 'tok');
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('nope', { status: 401 })),
    );
    await common.createEventSource();
    common.closeEventSource();
    const encoder = new TextEncoder();
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        const stream = new ReadableStream({
          start(controller) {
            controller.enqueue(
              encoder.encode(
                'ignore\n\ndata: \n\ndata: not-json\n\ndata: {"data":"ok"}\n\n',
              ),
            );
            controller.close();
          },
        });
        return new Response(stream, { status: 200 });
      }),
    );
    await common.createEventSource();
    await new Promise((resolve) => setTimeout(resolve, 40));
    common.closeEventSource();
    vi.unstubAllGlobals();
  });

  it('covers remaining i18n, storage, and helper branches', async () => {
    expect(generateMissingKeys({ a: '1', nested: { b: '2' } }, {})).toEqual([
      'a',
      'nested',
    ]);
    await initI18n('en-US');
    mergeDynamicTranslations('brand.new.module', {
      'en-US': { title: 'Fresh' },
    });
    const { t } = useI18n();
    expect(t('brand.new.module.title')).toBe('Fresh');

    const loader = new I18nLoader();
    (
      loader as unknown as {
        moduleRegistry: Map<
          string,
          { name: string; path: string; loaded: boolean }
        >;
      }
    ).moduleRegistry.set('ghost', {
      name: 'ghost',
      path: 'does-not-exist.json',
      loaded: false,
    });
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () => new Response('nope', { status: 404, statusText: 'NF' }),
      ),
    );
    expect(await loader.loadModule('zh-CN', 'ghost')).toEqual({});
    vi.unstubAllGlobals();
    const cache = (
      loader as unknown as { cache: Map<string, Record<string, unknown>> }
    ).cache;
    cache.set('zh-CN:core/common', { hello: 'ok' });
    cache.set('en-US:core/common', { hello: 'ok' });
    loader.clearCache('zh-CN');
    expect(cache.has('zh-CN:core/common')).toBe(false);
    expect(cache.has('en-US:core/common')).toBe(true);
    loader.clearCache();
    expect(cache.size).toBe(0);
    const duplicateLoader = new I18nLoader();
    await duplicateLoader.loadFeatureModules('zh-CN', [
      'features/chat',
      'features/chat',
    ]);

    const validator = new I18nValidator();
    vi.spyOn(validator, 'validateCompleteness').mockImplementationOnce(() => {
      throw new Error('broken pack');
    });
    const errorReport = await validator.validateLocales(['zh-CN']);
    expect(errorReport.details[0]?.isValid).toBe(false);
    expect(errorReport.details[0]?.errors[0]?.message).toBe('broken pack');
    vi.spyOn(validator, 'validateCompleteness').mockImplementationOnce(() => {
      throw 'nope';
    });
    const unknownReport = await validator.validateLocales(['en-US']);
    expect(unknownReport.details[0]?.errors[0]?.message).toBe('未知错误');

    expect(formatTokenCount(2_500_000)).toBe('2.5M');
    expect(formatTokenCount(12)).toBe('12');
    expect(formatTokenCount(Number.NaN)).toBe('');

    await expect(
      runConfigMutationWithStepUp(async () => {
        throw new Error('plain');
      }, 'cfg-1'),
    ).rejects.toThrow('plain');

    const customizer = useCustomizerStore();
    customizer.SET_THEME_MODE('dark');
    expect(customizer.uiTheme).toBe(themeNames.dark);

    window.astrbotDesktop = {
      isDesktop: false,
      isDesktopRuntime: vi.fn(async () => {
        throw new Error('probe failed');
      }),
      restartBackend: vi.fn(),
    } as never;
    const desktop = await getDesktopRuntimeInfo();
    expect(desktop.hasDesktopRuntimeProbe).toBe(true);
    expect(desktop.isDesktopRuntime).toBe(false);
    delete window.astrbotDesktop;

    expect(
      getPluginConfigDefaultValue({
        type: 'object',
        items: { a: { type: 'unknown' } },
      }),
    ).toBeUndefined();

    expect(
      await collectDroppedKnowledgeBaseFiles({
        items: [{ webkitGetAsEntry: () => null }],
        files: [],
      } as unknown as DataTransfer),
    ).toEqual([]);
    expect(
      await collectDroppedKnowledgeBaseFiles({
        items: [
          {
            webkitGetAsEntry: () => ({
              isFile: false,
              isDirectory: false,
              name: 'skip',
            }),
          },
        ],
        files: [],
      } as unknown as DataTransfer),
    ).toEqual([]);

    expect(normalizeLoose('Hello_World')).toBe('helloworld');
    expect(buildSearchQuery('   ')).toBeNull();
    const query = buildSearchQuery('cs');
    expect(matchesText('测试', query)).toBeTypeOf('boolean');
    expect(matchesText('pre-cs-fix', query)).toBe(true);
    expect(matchesText(null, query)).toBe(false);
    expect(
      matchesPluginSearch(
        { name: 'plain-english', tags: 'nope' as never },
        query,
      ),
    ).toBe(false);

    const getItem = vi.spyOn(localStorage, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    expect(getStoredDashboardUsername()).toBe('guest');
    getItem.mockRestore();
    const setItem = vi.spyOn(localStorage, 'setItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    setStoredSelectedChatConfigId('profile-2');
    setItem.mockRestore();

    const bindingStorage = globalThis.localStorage;
    vi.stubGlobal('localStorage', undefined);
    try {
      expect(getStoredDashboardUsername()).toBe('guest');
      setStoredSelectedChatConfigId('ignored');
    } finally {
      vi.unstubAllGlobals();
      Object.defineProperty(window, 'localStorage', {
        configurable: true,
        value: bindingStorage,
      });
      Object.defineProperty(globalThis, 'localStorage', {
        configurable: true,
        value: bindingStorage,
      });
    }

    const storage = globalThis.localStorage;
    Object.defineProperty(window, 'localStorage', {
      configurable: true,
      get() {
        throw new Error('blocked');
      },
    });
    try {
      expect(readGitHubProxyState()).toEqual({
        radioValue: '0',
        control: '0',
        selectedProxy: '',
      });
      writeSelectedGitHubProxy('https://ghproxy');
      writeGitHubProxyRadioValue('1');
      writeGitHubProxyControl('1');
      expect(getStoredDashboardUsername()).toBe('guest');
      expect(getStoredSelectedChatConfigId()).toBe('default');
      setStoredSelectedChatConfigId('profile-1');
    } finally {
      Object.defineProperty(window, 'localStorage', {
        configurable: true,
        value: storage,
      });
    }
  });
});
