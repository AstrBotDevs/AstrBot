import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { h } from 'vue';
import { flushPromises } from '@vue/test-utils';
import { createMemoryHistory, createRouter, RouterView } from 'vue-router';
import { createPinia, setActivePinia } from 'pinia';
import FullLayout from '@/layouts/full/FullLayout.vue';
import { mountWithVuetify } from './utils/mountWithVuetify';

vi.mock('axios', () => ({
  default: {
    get: vi.fn(),
    create: vi.fn(() => ({
      defaults: {},
      interceptors: {
        request: { use: vi.fn() },
        response: { use: vi.fn() },
      },
    })),
    defaults: {},
  },
}));

vi.mock('@/api/v1', () => ({
  statsApi: {
    version: vi.fn(async () => ({
      data: {
        status: 'ok',
        data: { version: '4.26.2', dashboard_version: '4.26.2' },
      },
    })),
    firstNotice: vi.fn(async () => ({
      data: { status: 'ok', data: { content: '' } },
    })),
  },
}));

const ProviderRoute = {
  name: 'ProviderRouteStub',
  render: () => h('div', { class: 'provider-route-stub' }, 'providers route'),
};

const ConfigRoute = {
  name: 'ConfigRouteStub',
  render: () => h('div', { class: 'config-route-stub' }, 'config route'),
};

const PlatformRoute = {
  name: 'PlatformRouteStub',
  render: () => h('div', { class: 'platform-route-stub' }, 'platforms route'),
};

const RouterHost = {
  name: 'RouterHost',
  render: () => h(RouterView),
};

describe('router layout smoke', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('swaps providers/config/platforms through FullLayout without critical warnings', async () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    const pinia = createPinia();
    setActivePinia(pinia);

    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        {
          path: '/',
          component: FullLayout,
          children: [
            { path: '', redirect: '/providers' },
            { path: 'providers', component: ProviderRoute },
            { path: 'config', component: ConfigRoute },
            { path: 'platforms', component: PlatformRoute },
          ],
        },
      ],
    });

    await router.push('/providers');
    await router.isReady();

    const wrapper = mountWithVuetify(RouterHost, {
      global: {
        plugins: [pinia, router],
        stubs: {
          VerticalHeaderVue: {
            template: '<div class="vertical-header-stub"></div>',
          },
          VerticalSidebarVue: {
            template: '<div class="vertical-sidebar-stub"></div>',
          },
          Chat: {
            template: '<div class="chat-view-stub"></div>',
          },
          ReadmeDialog: {
            template: '<div class="readme-dialog-stub"></div>',
          },
        },
      },
    });

    await flushPromises();

    expect(wrapper.find('.vertical-header-stub').exists()).toBe(true);
    expect(wrapper.find('.vertical-sidebar-stub').exists()).toBe(true);
    expect(wrapper.find('.provider-route-stub').exists()).toBe(true);
    expect(wrapper.find('.chat-view-stub').exists()).toBe(false);

    await router.push('/config');
    await flushPromises();
    expect(wrapper.find('.config-route-stub').exists()).toBe(true);

    await router.push('/platforms');
    await flushPromises();
    expect(wrapper.find('.platform-route-stub').exists()).toBe(true);

    const criticalMessages = [
      'Extraneous non-props attributes',
      'Component inside <Transition> renders non-element root node',
      'Unhandled error during execution',
      'theme.global.name.value',
    ];

    expect(
      warnSpy.mock.calls.some((args) =>
        args.some((arg) =>
          criticalMessages.some((message) => String(arg).includes(message)),
        ),
      ),
    ).toBe(false);
    expect(
      errorSpy.mock.calls.some((args) =>
        args.some((arg) =>
          criticalMessages.some((message) => String(arg).includes(message)),
        ),
      ),
    ).toBe(false);
  });
});
