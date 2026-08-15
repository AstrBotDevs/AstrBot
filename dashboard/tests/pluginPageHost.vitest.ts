import { createPinia, setActivePinia } from 'pinia';
import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { computed, reactive } from 'vue';

import { initI18n, useI18n, useModuleI18n } from '@/i18n/composables';

const route = reactive({
  params: {
    extensionId: 'io.github.example.palette',
    pageId: 'settings',
  },
});
const routerPush = vi.fn();
const catalog = {
  protocol_version: 1 as const,
  extension_id: 'io.github.example.palette',
  plugin_name: 'astrbot_plugin_palette',
  plugin_generation: 'generation-1',
  pages: [
    {
      id: 'settings',
      title: 'Palette Settings',
      icon: 'mdi-palette',
      actions: ['config.read'],
    },
  ],
  actions: [
    {
      id: 'config.read',
      kind: 'json' as const,
      required_scope: 'plugin',
      description: 'Read config',
      input_schema: {},
      output_schema: {},
    },
  ],
};
const session = {
  protocol_version: 1 as const,
  instance_id: 'instance-1',
  plugin_generation: 'generation-1',
  iframe_url: '/api/plugin-pages/v1/sessions/session-handle/',
  handshake_nonce: 'nonce-1',
  expires_at: '2099-07-17T12:00:00Z',
};

const apiMocks = vi.hoisted(() => ({
  catalog: vi.fn(),
  createSession: vi.fn(),
  invoke: vi.fn(),
  upload: vi.fn(),
  createFileTicket: vi.fn(),
  readInlineTicket: vi.fn(),
  getPlugin: vi.fn(),
  readme: vi.fn(),
  changelog: vi.fn(),
}));

vi.mock('vue-router', async () => {
  const actual =
    await vi.importActual<typeof import('vue-router')>('vue-router');
  return {
    ...actual,
    useRoute: () => route,
    useRouter: () => ({ push: routerPush }),
    onBeforeRouteLeave: vi.fn(),
  };
});

vi.mock('vuetify', () => ({
  useTheme: () => ({
    global: {
      current: computed(() => ({
        colors: { primary: '#3c96ca', secondary: '#2f86bd' },
      })),
    },
  }),
}));

vi.mock('@/api/v1', () => ({
  PLUGIN_DASHBOARD_LIFECYCLE_EVENT: 'astrbot:plugin-dashboard-lifecycle',
  pluginDashboardApi: {
    catalog: apiMocks.catalog,
    createSession: apiMocks.createSession,
    invoke: apiMocks.invoke,
    upload: apiMocks.upload,
    createFileTicket: apiMocks.createFileTicket,
    readInlineTicket: apiMocks.readInlineTicket,
  },
  pluginApi: {
    get: apiMocks.getPlugin,
    readme: apiMocks.readme,
    changelog: apiMocks.changelog,
  },
}));

class FakePort {
  readonly sent: unknown[] = [];
  private listener: ((event: MessageEvent<unknown>) => void) | null = null;

  addEventListener(_type: 'message', listener: EventListener) {
    this.listener = listener as (event: MessageEvent<unknown>) => void;
  }

  removeEventListener() {
    this.listener = null;
  }

  start() {}
  close() {}

  postMessage(message: unknown) {
    this.sent.push(message);
  }

  dispatch(message: unknown) {
    this.listener?.(new MessageEvent('message', { data: message }));
  }
}

class FakeMessageChannel {
  static created: FakeMessageChannel[] = [];
  readonly port1 = new FakePort();
  readonly port2 = new FakePort();

  constructor() {
    FakeMessageChannel.created.push(this);
  }
}

const globalStubs = {
  VBtn: {
    emits: ['click'],
    template:
      '<button v-bind="$attrs" @click="$emit(\'click\')"><slot /></button>',
  },
  VChip: { template: '<span><slot /></span>' },
  VProgressCircular: { template: '<span />' },
  VAlert: { template: '<div v-bind="$attrs"><slot /></div>' },
  VIcon: { template: '<span><slot /></span>' },
  VCard: { template: '<div><slot /></div>' },
  VCardText: { template: '<div><slot /></div>' },
  VTable: { template: '<table><slot /></table>' },
};

beforeEach(async () => {
  setActivePinia(createPinia());
  routerPush.mockReset();
  FakeMessageChannel.created = [];
  vi.stubGlobal('MessageChannel', FakeMessageChannel);
  apiMocks.catalog.mockReset().mockResolvedValue({
    data: { status: 'ok', data: catalog },
  });
  apiMocks.createSession.mockReset().mockResolvedValue({
    data: { status: 'ok', data: session },
  });
  apiMocks.invoke.mockReset().mockResolvedValue({
    data: { status: 'ok', data: { enabled: true } },
  });
  apiMocks.getPlugin.mockReset().mockResolvedValue({
    data: { status: 'ok', data: null },
  });
  apiMocks.readme.mockReset().mockResolvedValue({
    data: { status: 'ok', data: { content: '' } },
  });
  apiMocks.changelog.mockReset().mockResolvedValue({
    data: { status: 'ok', data: { content: '' } },
  });
  await initI18n('en-US');
});

describe('PluginPageHost', () => {
  it('creates a session before mounting the strictly sandboxed iframe', async () => {
    const { default: PluginPageHost } =
      await import('@/views/extension/PluginPageHost.vue');
    const wrapper = mount(PluginPageHost, {
      global: { stubs: globalStubs },
    });
    expect(wrapper.find('[data-testid="plugin-page-frame"]').exists()).toBe(
      false,
    );
    await flushPromises();

    expect(apiMocks.catalog).toHaveBeenCalledWith('io.github.example.palette');
    expect(apiMocks.createSession).toHaveBeenCalledAfter(apiMocks.catalog);
    const frame = wrapper.get('iframe');
    expect(frame.attributes('sandbox')).toBe('allow-scripts');
    expect(frame.attributes('sandbox')).not.toContain('allow-same-origin');
    expect(frame.attributes('referrerpolicy')).toBe('no-referrer');
    expect(frame.attributes('allow')).toBe('');
    expect(frame.attributes('src')).toContain(
      '/api/plugin-pages/v1/sessions/session-handle/#instance=instance-1&channel=nonce-1',
    );
    wrapper.unmount();
  });

  it('performs one source-bound handshake and forwards context and JSON Actions', async () => {
    const { default: PluginPageHost } =
      await import('@/views/extension/PluginPageHost.vue');
    const wrapper = mount(PluginPageHost, {
      global: { stubs: globalStubs },
    });
    await flushPromises();
    const frame = wrapper.get('iframe').element as HTMLIFrameElement;
    const frameWindow = { postMessage: vi.fn() } as unknown as Window;
    Object.defineProperty(frame, 'contentWindow', {
      configurable: true,
      value: frameWindow,
    });
    window.dispatchEvent(
      new MessageEvent('message', {
        source: frameWindow,
        data: {
          protocol: 'astrbot.dashboard-extension',
          version: 1,
          kind: 'ready',
          instance_id: 'instance-1',
          nonce: 'nonce-1',
        },
      }),
    );
    await flushPromises();

    expect(frameWindow.postMessage).toHaveBeenCalledOnce();
    const bridge = FakeMessageChannel.created[0];
    expect(bridge.port1.sent[0]).toMatchObject({
      kind: 'context',
      context: {
        locale: 'en-US',
        capabilities: { actions: ['config.read'] },
      },
    });

    bridge.port1.dispatch({
      protocol_version: 1,
      instance_id: 'instance-1',
      plugin_generation: 'generation-1',
      kind: 'request',
      request_id: '1d42f034-2fa1-4e49-9df3-5e15d1bf5d45',
      action_id: 'config.read',
      action_kind: 'json',
      payload: {},
    });
    await flushPromises();
    expect(apiMocks.invoke).toHaveBeenCalledWith(
      'io.github.example.palette',
      'config.read',
      'instance-1',
      'generation-1',
      {},
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    expect(bridge.port1.sent.at(-1)).toMatchObject({
      kind: 'response',
      ok: true,
      data: { enabled: true },
    });

    await useI18n().setLocale('zh-CN');
    await flushPromises();
    expect(bridge.port1.sent.at(-1)).toMatchObject({
      kind: 'context',
      context: { locale: 'zh-CN' },
    });
    wrapper.unmount();
  });

  it('destroys the instance after an unexpected second iframe load or lifecycle event', async () => {
    const { default: PluginPageHost } =
      await import('@/views/extension/PluginPageHost.vue');
    const wrapper = mount(PluginPageHost, {
      global: { stubs: globalStubs },
    });
    await flushPromises();
    const frame = wrapper.get('iframe');
    await frame.trigger('load');
    await frame.trigger('load');
    expect(wrapper.find('iframe').exists()).toBe(false);
    expect(wrapper.get('[data-testid="plugin-page-error"]').text()).toContain(
      'secure container',
    );
    wrapper.unmount();

    const nextWrapper = mount(PluginPageHost, {
      global: { stubs: globalStubs },
    });
    await flushPromises();
    window.dispatchEvent(
      new CustomEvent('astrbot:plugin-dashboard-lifecycle', {
        detail: {
          reason: 'plugin_changed',
          plugin_name: 'astrbot_plugin_palette',
        },
      }),
    );
    await flushPromises();
    expect(nextWrapper.find('iframe').exists()).toBe(false);
    expect(
      nextWrapper.get('[data-testid="plugin-page-error"]').text(),
    ).toContain('reloaded');
    nextWrapper.unmount();
  });

  it('keeps Page components in their own group and opens the v1 route', async () => {
    const { default: PluginDetailPage } =
      await import('@/views/extension/PluginDetailPage.vue');
    const { tm } = useModuleI18n('features.extension');
    const plugin = {
      name: 'astrbot_plugin_palette',
      display_name: 'Palette',
      activated: true,
      components: [
        {
          type: 'page',
          name: 'settings',
          title: 'Palette Settings',
          description: 'Configure Palette',
          extension_id: 'io.github.example.palette',
          page_id: 'settings',
        },
      ],
    };
    apiMocks.getPlugin.mockResolvedValue({
      data: { status: 'ok', data: plugin },
    });
    const wrapper = mount(PluginDetailPage, {
      props: {
        plugin,
        state: { tm, router: { push: routerPush } },
      },
      global: { stubs: globalStubs },
    });
    await flushPromises();

    expect(wrapper.text()).toContain('Pages');
    expect(wrapper.text()).toContain('Palette Settings');
    expect(wrapper.text()).not.toContain('Hooks Configure Palette');
    await wrapper
      .get('[data-testid="open-plugin-page-settings"]')
      .trigger('click');
    expect(routerPush).toHaveBeenCalledWith({
      name: 'PluginPageHost',
      params: {
        extensionId: 'io.github.example.palette',
        pageId: 'settings',
      },
    });
    wrapper.unmount();
  });

  it('shows a localized update time for marketplace plugin details', async () => {
    const { default: PluginDetailPage } =
      await import('@/views/extension/PluginDetailPage.vue');
    const { tm } = useModuleI18n('features.extension');
    const plugin = {
      name: 'astrbot_plugin_palette',
      display_name: 'Palette',
      updated_at: '2026-08-15T12:34:56Z',
    };
    const wrapper = mount(PluginDetailPage, {
      props: {
        plugin,
        sourceTab: 'market',
        state: { tm, router: { push: routerPush } },
      },
      global: { stubs: globalStubs },
    });
    await flushPromises();

    expect(wrapper.text()).toContain('Updated At');
    expect(wrapper.text()).toContain(
      new Intl.DateTimeFormat('en-US', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false,
      }).format(new Date(plugin.updated_at)),
    );
    wrapper.unmount();
  });
});
