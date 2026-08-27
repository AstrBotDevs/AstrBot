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
    installPip: vi.fn(),
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

  it('opens the account dialog without translation warnings', async () => {
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
          AboutPage: {
            template: '<div class="about-page-stub"></div>',
          },
        },
      },
    });

    await flushPromises();

    const accountTriggers = wrapper
      .findAll('.styled-menu-item')
      .filter((node) => node.text().includes('Modify Account'));
    expect(accountTriggers).toHaveLength(1);

    await accountTriggers[0].trigger('click');
    await flushPromises();

    expect(wrapper.text()).toContain('Modify Account');
    expect(hasCriticalWarning(warnSpy.mock.calls)).toBe(false);
    expect(hasCriticalWarning(errorSpy.mock.calls)).toBe(false);
  });
});
