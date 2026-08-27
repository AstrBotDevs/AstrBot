import { beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises } from '@vue/test-utils';
import ConfigPage from '@/views/ConfigPage.vue';
import PlatformPage from '@/views/PlatformPage.vue';
import { mountWithVuetify } from './utils/mountWithVuetify';

const testState = vi.hoisted(() => ({
  routerPushMock: vi.fn(),
  routerReplaceMock: vi.fn(),
  configProfileListMock: vi.fn(),
  configProfileGetMock: vi.fn(),
  configProfileUpdateMock: vi.fn(),
  configProfileCreateMock: vi.fn(),
  configProfileDeleteMock: vi.fn(),
  configProfileRenameMock: vi.fn(),
  systemConfigGetMock: vi.fn(),
  systemConfigUpdateMock: vi.fn(),
  systemConfigRuntimeMock: vi.fn(),
  botStatsMock: vi.fn(),
  botDeleteMock: vi.fn(),
  botSetEnabledMock: vi.fn(),
  fileTokenUrlMock: vi.fn(),
}));

vi.mock('vue-router', async () => {
  const actual =
    await vi.importActual<typeof import('vue-router')>('vue-router');
  return {
    ...actual,
    useRoute: () => ({
      fullPath: '/config#normal',
      path: '/config',
    }),
    useRouter: () => ({
      push: testState.routerPushMock,
      replace: testState.routerReplaceMock,
    }),
    onBeforeRouteLeave: vi.fn(),
  };
});

vi.mock('@/api/v1', () => ({
  configProfileApi: {
    list: testState.configProfileListMock,
    get: testState.configProfileGetMock,
    update: testState.configProfileUpdateMock,
    create: testState.configProfileCreateMock,
    delete: testState.configProfileDeleteMock,
    rename: testState.configProfileRenameMock,
  },
  systemConfigApi: {
    get: testState.systemConfigGetMock,
    update: testState.systemConfigUpdateMock,
    runtime: testState.systemConfigRuntimeMock,
  },
  botApi: {
    stats: testState.botStatsMock,
    delete: testState.botDeleteMock,
    setEnabled: testState.botSetEnabledMock,
  },
  fileApi: {
    tokenUrl: testState.fileTokenUrlMock,
  },
}));

vi.mock('@/components/config/AstrBotCoreConfigWrapper.vue', () => ({
  default: {
    props: ['configData', 'metadata', 'searchKeyword'],
    template:
      '<div class="config-wrapper-stub">{{ searchKeyword }}|{{ Object.keys(configData || {}).length }}</div>',
  },
}));

vi.mock('@/components/chat/StandaloneChat.vue', () => ({
  default: {
    props: ['configId'],
    template: '<div class="standalone-chat-stub">{{ configId }}</div>',
  },
}));

vi.mock('@guolao/vue-monaco-editor', () => ({
  VueMonacoEditor: {
    props: ['value'],
    template: '<div class="monaco-editor-stub"></div>',
  },
}));

vi.mock('@/utils/monacoLoader', () => ({}));

vi.mock('@/utils/confirmDialog', () => ({
  askForConfirmation: vi.fn(),
  useConfirmDialog: () => undefined,
}));

vi.mock('@/components/config/UnsavedChangesConfirmDialog.vue', () => ({
  default: {
    template: '<div class="unsaved-changes-dialog-stub"></div>',
  },
}));

vi.mock('@/components/shared/DashboardTwoFactorDialog.vue', () => ({
  default: {
    template: '<div class="two-factor-dialog-stub"></div>',
  },
}));

vi.mock('@/components/shared/ConsoleDisplayer.vue', () => ({
  default: {
    template: '<div class="console-displayer-stub"></div>',
  },
}));

vi.mock('@/components/shared/ItemCard.vue', () => ({
  default: {
    props: ['item'],
    template:
      '<div class="item-card-stub"><div class="item-card-id">{{ item.id }}</div><slot name="item-details" :item="item" /></div>',
  },
}));

vi.mock('@/components/platform/AddNewPlatform.vue', () => ({
  default: {
    name: 'AddNewPlatform',
    props: ['show', 'metadata', 'config_data', 'updatingMode', 'requestStepUp'],
    template: '<div class="add-platform-stub"></div>',
  },
}));

vi.mock('@/components/platform/PlatformEditor.vue', () => ({
  default: {
    name: 'PlatformEditor',
    props: [
      'platform',
      'metadata',
      'runtimeStat',
      'hasQrPayload',
      'requestStepUp',
    ],
    template: '<div class="platform-editor-stub">{{ platform?.id }}</div>',
  },
}));

vi.mock('@/components/shared/QrCodeViewer.vue', () => ({
  default: {
    props: ['value'],
    template: '<div class="qr-code-viewer-stub">{{ value }}</div>',
  },
}));

function hasAttrWarning(calls: unknown[][]) {
  return calls.some((args) =>
    args.some((arg) => String(arg).includes('Extraneous non-props attributes')),
  );
}

function hasCriticalRuntimeWarning(calls: unknown[][]) {
  const blockedWarnings = [
    'Extraneous non-props attributes',
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

describe('page smoke tests', () => {
  beforeEach(() => {
    vi.clearAllMocks();

    testState.configProfileListMock.mockResolvedValue({
      data: {
        data: {
          info_list: [{ id: 'default', name: 'Default Config' }],
        },
      },
    });
    testState.configProfileGetMock.mockResolvedValue({
      data: {
        data: {
          config: {
            provider: { model: 'gpt-4.1-mini' },
          },
          metadata: {
            provider: { items: {} },
          },
        },
      },
    });
    testState.configProfileUpdateMock.mockResolvedValue({
      data: { status: 'ok', message: 'saved' },
    });
    testState.systemConfigGetMock.mockResolvedValue({
      data: {
        data: {
          config: {},
          metadata: {},
        },
      },
    });
    testState.systemConfigUpdateMock.mockResolvedValue({
      status: 200,
      data: { status: 'ok', message: 'saved', data: {} },
    });

    testState.systemConfigRuntimeMock.mockResolvedValue({
      data: {
        data: {
          config: {
            callback_api_base: 'https://astrbot.example',
            platform: [
              {
                id: 'wecom-main',
                type: 'wecom',
                enable: true,
                webhook_uuid: 'wh-1',
              },
            ],
          },
          metadata: {
            platform_group: {
              metadata: {
                platform: {
                  config_template: {
                    wecom: {
                      logo_token: 'logo-token-1',
                    },
                  },
                },
              },
            },
          },
          platform_i18n_translations: {},
        },
      },
    });
    testState.botStatsMock.mockResolvedValue({
      data: {
        status: 'ok',
        data: {
          platforms: [
            {
              id: 'wecom-main',
              status: 'error',
              error_count: 2,
              last_error: {
                message: 'Webhook auth failed',
                timestamp: '2026-06-29T00:00:00Z',
              },
              unified_webhook: true,
              weixin_oc: {
                qrcode: 'qr://payload',
                qr_status: 'pending',
              },
            },
          ],
        },
      },
    });
    testState.fileTokenUrlMock.mockImplementation(
      (token: string) => `/tokens/${token}`,
    );
  });

  it('renders ConfigPage core content without fragment attr warnings', async () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    const wrapper = mountWithVuetify(ConfigPage, {
      attrs: {
        class: 'config-page-test',
      },
      props: {
        initialConfigId: 'default',
      },
    });

    await flushPromises();

    expect(wrapper.classes()).toContain('config-page-test');
    expect(wrapper.find('.config-wrapper-stub').exists()).toBe(true);
    expect(hasAttrWarning(warnSpy.mock.calls)).toBe(false);
    expect(hasCriticalRuntimeWarning(warnSpy.mock.calls)).toBe(false);
    expect(hasCriticalRuntimeWarning(errorSpy.mock.calls)).toBe(false);
  });

  it('renders PlatformPage status and action surfaces without crashing', async () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    const wrapper = mountWithVuetify(PlatformPage);

    await flushPromises();

    expect(wrapper.find('.bot-list-item__title').text()).toBe('wecom-main');

    const addPlatform = wrapper.findComponent({ name: 'AddNewPlatform' });
    expect(addPlatform.exists()).toBe(true);
    expect(typeof addPlatform.props('requestStepUp')).toBe('function');

    if (!wrapper.find('.platform-editor-stub').exists()) {
      await wrapper.find('.bot-list-item__main').trigger('click');
      await flushPromises();
    }

    const editor = wrapper.findComponent({ name: 'PlatformEditor' });
    expect(editor.exists()).toBe(true);
    expect(typeof editor.props('requestStepUp')).toBe('function');

    expect(hasCriticalRuntimeWarning(warnSpy.mock.calls)).toBe(false);
    expect(hasCriticalRuntimeWarning(errorSpy.mock.calls)).toBe(false);
  });
});
