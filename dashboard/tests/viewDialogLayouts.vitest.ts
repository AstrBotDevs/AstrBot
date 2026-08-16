import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises } from '@vue/test-utils';
import ConsolePage from '@/views/ConsolePage.vue';
import ConversationPage from '@/views/ConversationPage.vue';
import WelcomePage from '@/views/WelcomePage.vue';
import KBList from '@/views/knowledge-base/KBList.vue';
import { mountWithVuetify } from './utils/mountWithVuetify';

const testState = vi.hoisted(() => ({
  routerPushMock: vi.fn(),
  knowledgeListMock: vi.fn(),
  providerListByTypeMock: vi.fn(),
  configProfileGetMock: vi.fn(),
  configProfileUpdateMock: vi.fn(),
  providerSchemaMock: vi.fn(),
  systemConfigRuntimeMock: vi.fn(),
  updatesInstallPipMock: vi.fn(),
  conversationListMock: vi.fn(),
  axiosGetMock: vi.fn(),
  toastSuccessMock: vi.fn(),
  toastErrorMock: vi.fn(),
}));

vi.mock('vue-router', async () => {
  const actual =
    await vi.importActual<typeof import('vue-router')>('vue-router');
  return {
    ...actual,
    useRouter: () => ({
      push: testState.routerPushMock,
    }),
  };
});

vi.mock('axios', () => ({
  default: {
    get: testState.axiosGetMock,
    create: vi.fn(() => ({ defaults: {} })),
    defaults: {},
  },
  isCancel: () => false,
}));

vi.mock('@/api/v1', () => ({
  knowledgeApi: {
    list: testState.knowledgeListMock,
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
  },
  providerApi: {
    listByProviderType: testState.providerListByTypeMock,
    schema: testState.providerSchemaMock,
  },
  configProfileApi: {
    get: testState.configProfileGetMock,
    update: testState.configProfileUpdateMock,
  },
  systemConfigApi: {
    runtime: testState.systemConfigRuntimeMock,
  },
  updatesApi: {
    installPip: testState.updatesInstallPipMock,
  },
  conversationApi: {
    list: testState.conversationListMock,
    get: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    batchDelete: vi.fn(),
    replaceMessages: vi.fn(),
    export: vi.fn(),
  },
}));

vi.mock('@/utils/toast', () => ({
  useToast: () => ({
    success: testState.toastSuccessMock,
    error: testState.toastErrorMock,
  }),
}));

vi.mock('markstream-vue', () => ({
  MarkdownRender: {
    props: ['content'],
    template: '<div class="markdown-render-stub">{{ content }}</div>',
  },
}));

vi.mock('@guolao/vue-monaco-editor', () => ({
  VueMonacoEditor: {
    props: ['value'],
    template: '<div class="monaco-editor-stub"></div>',
  },
}));

vi.mock('@/utils/monacoLoader', () => ({}));

vi.mock('@/stores/common', () => ({
  useCommonStore: () => ({}),
}));

vi.mock('@/stores/customizer', () => ({
  useCustomizerStore: () => ({
    uiTheme: 'AstrBotDark',
  }),
}));

vi.mock('@/components/platform/AddNewPlatform.vue', () => ({
  default: {
    template: '<div class="add-platform-stub"></div>',
  },
}));

vi.mock('@/components/chat/ProviderConfigDialog.vue', () => ({
  default: {
    props: ['modelValue'],
    template: '<div class="provider-config-dialog-stub">{{ modelValue }}</div>',
  },
}));

vi.mock('@/components/shared/ConsoleDisplayer.vue', () => ({
  default: {
    props: ['autoScroll'],
    template: '<div class="console-displayer-stub">{{ autoScroll }}</div>',
  },
}));

vi.mock('@/components/shared/OutlinedActionListItem.vue', () => ({
  default: {
    props: ['title', 'clickable'],
    template: `
      <div class="outlined-action-list-item-stub">
        <slot name="title-prepend" />
        <div class="outlined-action-list-item-title">{{ title }}</div>
        <slot />
        <slot name="actions" />
      </div>
    `,
  },
}));

vi.mock('@/components/chat/MessageList.vue', () => ({
  default: {
    props: ['messages'],
    template:
      '<div class="message-list-stub">{{ messages?.length || 0 }}</div>',
  },
}));

vi.mock('@/components/shared/UmoDisplay.vue', () => ({
  default: {
    template: '<div class="umo-display-stub"></div>',
  },
}));

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

type KBListVm = {
  showCreateDialog: boolean;
  showEmojiPicker: boolean;
  showDeleteDialog: boolean;
};

type WelcomePageVm = {
  showComputerAccessHelpDialog: boolean;
};

type ConsolePageVm = {
  pipDialog: boolean;
};

type ConversationPageVm = {
  selectedConversation: {
    cid: string;
    user_id: string;
    title: string;
  };
  selectedItems: Array<{
    cid: string;
    user_id: string;
    title: string;
  }>;
  dialogEdit: boolean;
  dialogDelete: boolean;
  dialogBatchDelete: boolean;
  dialogView: boolean;
};

describe('view dialog layouts', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  beforeEach(() => {
    vi.clearAllMocks();

    testState.knowledgeListMock.mockResolvedValue({
      data: {
        status: 'ok',
        data: {
          items: [],
        },
      },
    });
    testState.providerListByTypeMock.mockResolvedValue({
      data: {
        status: 'ok',
        data: [
          {
            id: 'embed-1',
            provider_type: 'embedding',
            embedding_model: 'text-embedding-3-small',
          },
          {
            id: 'rerank-1',
            provider_type: 'rerank',
            rerank_model: 'rerank-v1',
          },
        ],
      },
    });
    testState.configProfileGetMock.mockResolvedValue({
      data: {
        data: {
          config: {
            provider_settings: {
              computer_use_runtime: 'none',
            },
          },
        },
      },
    });
    testState.configProfileUpdateMock.mockResolvedValue({
      data: {
        status: 'ok',
      },
    });
    testState.providerSchemaMock.mockResolvedValue({
      data: {
        status: 'ok',
        data: {
          providers: [
            {
              id: 'openai-main',
              provider_type: 'chat_completion',
              enable: true,
            },
          ],
        },
      },
    });
    testState.systemConfigRuntimeMock.mockResolvedValue({
      data: {
        data: {
          config: {
            platform: [],
          },
          metadata: {},
        },
      },
    });
    testState.updatesInstallPipMock.mockResolvedValue({
      data: {
        status: 'ok',
      },
    });
    testState.conversationListMock.mockResolvedValue({
      data: {
        status: 'ok',
        data: {
          conversations: [
            {
              cid: 'conv-1',
              user_id: 'discord:group:session-1',
              title: 'Conversation One',
              created_at: '2026-06-30T00:00:00Z',
              updated_at: '2026-06-30T00:00:00Z',
            },
          ],
          pagination: {
            total: 1,
            page: 1,
            page_size: 10,
            total_pages: 1,
          },
        },
      },
    });
    testState.axiosGetMock.mockResolvedValue({
      data: {
        data: {
          notice: {
            welcome_page: 'Welcome',
          },
        },
      },
    });
  });

  it('renders KBList dialogs inside bounded scroll containers', async () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    const wrapper = mountWithVuetify(KBList);
    const vm = wrapper.vm as unknown as KBListVm;

    await flushPromises();

    vm.showCreateDialog = true;
    vm.showEmojiPicker = true;
    vm.showDeleteDialog = true;
    await flushPromises();

    expect(document.body.querySelector('.kb-dialog-card')).not.toBeNull();
    expect(document.body.querySelector('.kb-dialog-body')).not.toBeNull();
    expect(document.body.querySelector('.kb-emoji-dialog-card')).not.toBeNull();
    expect(document.body.querySelector('.kb-emoji-dialog-body')).not.toBeNull();
    expect(
      document.body.querySelector('.kb-delete-dialog-card'),
    ).not.toBeNull();
    expect(
      document.body.querySelector('.kb-delete-dialog-body'),
    ).not.toBeNull();
    expect(hasCriticalRuntimeWarning(warnSpy.mock.calls)).toBe(false);
    expect(hasCriticalRuntimeWarning(errorSpy.mock.calls)).toBe(false);

    wrapper.unmount();
  });

  it('renders the welcome help dialog inside a bounded scroll container', async () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    const wrapper = mountWithVuetify(WelcomePage);
    const vm = wrapper.vm as unknown as WelcomePageVm;

    await flushPromises();

    vm.showComputerAccessHelpDialog = true;
    await flushPromises();

    expect(
      document.body.querySelector('.computer-access-help-dialog'),
    ).not.toBeNull();
    expect(
      document.body.querySelector('.computer-access-help-dialog__content'),
    ).not.toBeNull();
    expect(hasCriticalRuntimeWarning(warnSpy.mock.calls)).toBe(false);
    expect(hasCriticalRuntimeWarning(errorSpy.mock.calls)).toBe(false);

    wrapper.unmount();
  });

  it('renders the console pip dialog inside a bounded scroll container', async () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    const wrapper = mountWithVuetify(ConsolePage);
    const vm = wrapper.vm as unknown as ConsolePageVm;

    await flushPromises();

    vm.pipDialog = true;
    await flushPromises();

    expect(document.body.querySelector('.console-pip-dialog')).not.toBeNull();
    expect(
      document.body.querySelector('.console-pip-dialog__content'),
    ).not.toBeNull();
    expect(hasCriticalRuntimeWarning(warnSpy.mock.calls)).toBe(false);
    expect(hasCriticalRuntimeWarning(errorSpy.mock.calls)).toBe(false);

    wrapper.unmount();
  });

  it('renders conversation maintenance dialogs inside bounded scroll containers', async () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    const wrapper = mountWithVuetify(ConversationPage);
    const vm = wrapper.vm as unknown as ConversationPageVm;

    await flushPromises();

    vm.selectedConversation = {
      cid: 'conv-1',
      user_id: 'discord:group:session-1',
      title: 'Conversation One',
    };
    vm.selectedItems = [
      {
        cid: 'conv-1',
        user_id: 'discord:group:session-1',
        title: 'Conversation One',
      },
      {
        cid: 'conv-2',
        user_id: 'discord:friend:session-2',
        title: 'Conversation Two',
      },
    ];
    vm.dialogEdit = true;
    vm.dialogDelete = true;
    vm.dialogBatchDelete = true;
    await flushPromises();

    expect(
      document.body.querySelector('.conversation-edit-dialog'),
    ).not.toBeNull();
    expect(
      document.body.querySelector('.conversation-delete-dialog'),
    ).not.toBeNull();
    expect(
      document.body.querySelector('.conversation-batch-delete-dialog'),
    ).not.toBeNull();
    expect(
      document.body.querySelector('.conversation-modal-body'),
    ).not.toBeNull();
    expect(hasCriticalRuntimeWarning(warnSpy.mock.calls)).toBe(false);
    expect(hasCriticalRuntimeWarning(errorSpy.mock.calls)).toBe(false);

    wrapper.unmount();
  });

  it('lets the conversation card text own preview scrolling', async () => {
    const wrapper = mountWithVuetify(ConversationPage);
    const vm = wrapper.vm as unknown as ConversationPageVm;

    await flushPromises();

    vm.dialogView = true;
    await flushPromises();

    const detailCard = document.body.querySelector('.conversation-detail-card');
    const actionBar = detailCard?.querySelector(
      '.conversation-history-actions',
    );
    const cardText = detailCard?.querySelector('.v-card-text');
    const preview = cardText?.querySelector('.conversation-messages-container');

    expect(detailCard).not.toBeNull();
    expect(actionBar).not.toBeNull();
    expect(cardText).not.toBeNull();
    expect(preview).not.toBeNull();
    expect(actionBar?.parentElement).toBe(detailCard);
    expect(cardText?.contains(actionBar ?? null)).toBe(false);

    const wheelEvent = new WheelEvent('wheel', {
      bubbles: true,
      cancelable: true,
      deltaY: 24,
    });
    preview?.dispatchEvent(wheelEvent);

    expect(wheelEvent.defaultPrevented).toBe(false);

    wrapper.unmount();
  });
});
