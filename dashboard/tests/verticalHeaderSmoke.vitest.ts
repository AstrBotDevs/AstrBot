import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises } from '@vue/test-utils';
import { defineComponent, ref } from 'vue';
import VerticalHeader from '@/layouts/full/vertical-header/VerticalHeader.vue';
import { mountWithVuetify } from './utils/mountWithVuetify';

const testState = vi.hoisted(() => ({
  routerPush: vi.fn(),
  logout: vi.fn(),
  setAstrBotVersion: vi.fn(),
  createEventSource: vi.fn(),
  getStartTime: vi.fn(() => -1),
  commonStore: {
    startTime: -1,
    setAstrBotVersion: vi.fn(),
    createEventSource: vi.fn(),
    getStartTime: vi.fn(() => -1),
  },
}));

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

vi.mock('vue-router', () => ({
  useRoute: () => ({
    path: '/welcome',
    fullPath: '/welcome',
    params: {},
  }),
}));

vi.mock('@/router', () => ({
  router: {
    push: testState.routerPush,
  },
}));

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    logout: testState.logout,
  }),
}));

vi.mock('@/stores/common', () => ({
  useCommonStore: () => testState.commonStore,
}));

vi.mock('@/utils/desktopRuntime', () => ({
  getDesktopRuntimeInfo: vi.fn(async () => ({
    bridge: undefined,
    hasDesktopRuntimeProbe: false,
    hasDesktopRestartCapability: false,
    isDesktopRuntime: false,
  })),
}));

vi.mock('@/utils/githubProxyStorage', () => ({
  readSelectedGitHubProxy: () => '',
}));

vi.mock('@/api/v1', () => ({
  authApi: {
    updateAccount: vi.fn(async () => ({
      data: { status: 'ok', message: 'updated' },
    })),
  },
  statsApi: {
    version: vi.fn(async () => ({
      data: {
        data: {
          version: '4.26.2',
          dashboard_version: '4.26.2',
          change_pwd_hint: false,
          md5_pwd_hint: false,
          password_upgrade_required: false,
        },
      },
    })),
    startTime: vi.fn(async () => ({
      data: { data: { start_time: 1 } },
    })),
  },
  updatesApi: {
    check: vi.fn(async () => ({
      data: {
        message: 'Current release notes',
        data: {
          has_new_version: true,
          dashboard_has_new_version: false,
        },
      },
    })),
    releases: vi.fn(async () => ({
      data: {
        data: [
          {
            tag_name: 'v4.26.2',
            published_at: '2026-06-30T00:00:00Z',
            body: 'Current release notes',
          },
        ],
      },
    })),
    progress: vi.fn(async () => ({
      data: { data: null },
    })),
    switchVersion: vi.fn(),
    updateDashboard: vi.fn(),
  },
}));

vi.mock('@/i18n/composables', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/i18n/composables')>();
  return {
    ...actual,
    useLanguageSwitcher: () => ({
      languageOptions: ref([
        { value: 'en-US', label: 'English', flag: 'EN' },
        { value: 'zh-CN', label: '中文', flag: 'ZH' },
      ]),
      currentLanguage: ref('en-US'),
      switchLanguage: vi.fn(async () => {}),
      locale: ref('en-US'),
    }),
  };
});

vi.mock('@/components/shared/Logo.vue', () => ({
  default: {
    template: '<div class="logo-stub"></div>',
  },
}));

vi.mock('@/components/shared/StyledMenu.vue', () => ({
  default: {
    template:
      '<div class="styled-menu-stub"><slot name="activator" :props="{}" /><slot /></div>',
  },
}));

const VerticalHeaderHost = defineComponent({
  name: 'VerticalHeaderHost',
  components: {
    VerticalHeader,
  },
  template: `
    <v-app>
      <v-layout>
        <VerticalHeader />
      </v-layout>
    </v-app>
  `,
});

function hasCriticalWarning(calls: unknown[][]) {
  const blockedWarnings = [
    'Translation key not found',
    'theme.global.name.value',
    'Unhandled error during execution',
  ];

  return calls.some((args) =>
    args.some((arg) =>
      blockedWarnings.some((warning) => String(arg).includes(warning)),
    ),
  );
}

describe('VerticalHeader smoke', () => {
  beforeEach(() => {
    testState.routerPush.mockReset();
    testState.logout.mockReset();
    testState.commonStore = {
      startTime: -1,
      setAstrBotVersion: vi.fn(),
      createEventSource: vi.fn(),
      getStartTime: vi.fn(() => -1),
    };
    localStorage.setItem('user', 'astrbot');
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('opens the update dialog without translation warnings', async () => {
    vi.spyOn(console, 'log').mockImplementation(() => {});
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    const wrapper = mountWithVuetify(VerticalHeaderHost, {
      global: {
        stubs: {
          VDialog: {
            props: ['modelValue'],
            template: '<div v-if="modelValue"><slot /></div>',
          },
          LazyMarkdownRender: {
            props: ['content'],
            template: '<div class="lazy-markdown-stub">{{ content }}</div>',
          },
          AboutPage: {
            template: '<div class="about-page-stub"></div>',
          },
        },
      },
    });

    await flushPromises();

    const updateTriggers = wrapper
      .findAll('.styled-menu-item')
      .filter((node) => node.text().includes('Update AstrBot'));
    expect(updateTriggers).toHaveLength(1);

    await updateTriggers[0].trigger('click');
    await flushPromises();

    expect(wrapper.text()).toContain('Update AstrBot');
    expect(wrapper.text()).toContain('Current Version');
    expect(wrapper.text()).toContain('AstrBot has a new version!');
    expect(wrapper.find('.lazy-markdown-stub').text()).toContain(
      'Current release notes',
    );
    expect(
      document.body.querySelector('.update-status-dialog'),
    ).not.toBeNull();
    expect(
      document.body.querySelector('.update-status-dialog__content'),
    ).not.toBeNull();
    expect(hasCriticalWarning(warnSpy.mock.calls)).toBe(false);
    expect(hasCriticalWarning(errorSpy.mock.calls)).toBe(false);
  });
});
