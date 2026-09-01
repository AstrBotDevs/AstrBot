import { beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises } from '@vue/test-utils';
import KnowledgeBaseSelector from '@/components/shared/KnowledgeBaseSelector.vue';
import PluginSetSelector from '@/components/shared/PluginSetSelector.vue';
import ProviderSelector from '@/components/shared/ProviderSelector.vue';
import SidebarCustomizer from '@/components/shared/SidebarCustomizer.vue';
import ChangelogDialog from '@/components/shared/ChangelogDialog.vue';
import FileConfigItem from '@/components/shared/FileConfigItem.vue';
import ProviderConfigDialog from '@/components/chat/ProviderConfigDialog.vue';
import DetailsDialog from '@/components/extension/componentPanel/components/DetailsDialog.vue';
import { mountWithVuetify } from './utils/mountWithVuetify';

const testState = vi.hoisted(() => ({
  routerPushMock: vi.fn(),
  knowledgeListMock: vi.fn(),
  pluginListMock: vi.fn(),
  pluginListConfigFilesMock: vi.fn(),
  providerListByTypeMock: vi.fn(),
  statsVersionMock: vi.fn(),
  changelogGetMock: vi.fn(),
  changelogListVersionsMock: vi.fn(),
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

vi.mock('@/api/v1', () => ({
  knowledgeApi: {
    list: testState.knowledgeListMock,
  },
  pluginApi: {
    list: testState.pluginListMock,
    listConfigFiles: testState.pluginListConfigFilesMock,
    deleteConfigFile: vi.fn(),
    uploadConfigFiles: vi.fn(),
  },
  providerApi: {
    listByProviderType: testState.providerListByTypeMock,
  },
  statsApi: {
    version: testState.statsVersionMock,
  },
  changelogApi: {
    get: testState.changelogGetMock,
    listVersions: testState.changelogListVersionsMock,
  },
}));

vi.mock('markstream-vue', () => ({
  MarkdownRender: {
    props: ['content'],
    template: '<div class="markdown-render-stub">{{ content }}</div>',
  },
  enableKatex: vi.fn(),
  enableMermaid: vi.fn(),
}));

vi.mock('@/utils/pluginI18n', () => ({
  usePluginI18n: () => ({
    pluginName: (plugin: { name?: string }) => plugin.name || '',
    pluginDesc: (plugin: { desc?: string; description?: string }) =>
      plugin.description || plugin.desc || '',
  }),
}));

vi.mock('@/components/provider/ProviderChatCompletionPanel.vue', () => ({
  default: {
    template: '<div class="provider-chat-completion-panel-stub"></div>',
  },
}));

vi.mock('@/views/ProviderPage.vue', () => ({
  default: {
    props: ['defaultTab'],
    template: '<div class="provider-page-stub">{{ defaultTab }}</div>',
  },
}));

describe('shared dialog scroll layouts', () => {
  beforeEach(() => {
    testState.routerPushMock.mockReset();
    testState.knowledgeListMock.mockResolvedValue({
      data: {
        status: 'ok',
        data: {
          items: [
            { kb_id: 'kb-1', kb_name: 'Docs', description: 'Knowledge base' },
          ],
        },
      },
    });
    testState.pluginListMock.mockResolvedValue({
      data: {
        status: 'ok',
        data: [{ name: 'plugin.alpha', activated: true, reserved: false }],
      },
    });
    testState.pluginListConfigFilesMock.mockResolvedValue({
      data: {
        status: 'ok',
        data: {
          files: ['docs/manual.txt'],
        },
      },
    });
    testState.providerListByTypeMock.mockResolvedValue({
      data: {
        status: 'ok',
        data: [
          {
            id: 'openai-main',
            type: 'openai_chat_completions',
            provider_type: 'chat_completion',
            model: 'gpt-4.1-mini',
          },
        ],
      },
    });
    testState.statsVersionMock.mockResolvedValue({
      data: {
        status: 'ok',
        data: {
          version: '4.26.2',
        },
      },
    });
    testState.changelogListVersionsMock.mockResolvedValue({
      data: {
        status: 'ok',
        data: {
          versions: ['4.26.2', '4.26.1'],
        },
      },
    });
    testState.changelogGetMock.mockResolvedValue({
      data: {
        status: 'ok',
        data: {
          content: Array.from(
            { length: 30 },
            (_, index) => `Release note ${index}`,
          ).join('\n\n'),
        },
      },
    });
  });

  it('renders the knowledge base selector inside a constrained scrollable dialog', async () => {
    const wrapper = mountWithVuetify(KnowledgeBaseSelector, {
      props: {
        modelValue: [],
      },
    });

    await wrapper.find('button').trigger('click');
    await flushPromises();

    expect(
      document.body.querySelector('.selector-dialog__card'),
    ).not.toBeNull();
    expect(
      document.body.querySelector('.selector-dialog__content'),
    ).not.toBeNull();

    wrapper.unmount();
  });

  it('renders the provider selector inside a constrained scrollable dialog', async () => {
    const wrapper = mountWithVuetify(ProviderSelector, {
      props: {
        modelValue: '',
        providerType: 'chat_completion',
      },
    });

    await wrapper.find('button').trigger('click');
    await flushPromises();

    expect(wrapper.find('.provider-select-menu').exists()).toBe(true);
    expect(document.body.querySelector('.provider-menu-card')).not.toBeNull();
    expect(document.body.querySelector('.provider-menu-body')).not.toBeNull();

    wrapper.unmount();
  });

  it('renders the plugin set selector inside a constrained scrollable dialog', async () => {
    const wrapper = mountWithVuetify(PluginSetSelector, {
      props: {
        modelValue: [],
      },
    });

    await wrapper.find('button').trigger('click');
    await flushPromises();

    expect(
      document.body.querySelector('.plugin-set-dialog__card'),
    ).not.toBeNull();
    expect(
      document.body.querySelector('.plugin-set-dialog__content'),
    ).not.toBeNull();

    wrapper.unmount();
  });

  it('renders the command details dialog inside a bounded scroll container', async () => {
    mountWithVuetify(DetailsDialog, {
      props: {
        show: true,
        command: {
          type: 'group',
          handler_name: 'plugin.handler',
          module_path: 'plugins/example/handler.py',
          original_command: '/example',
          effective_command: '/example effective',
          parent_signature: 'root.example',
          aliases: Array.from({ length: 12 }, (_, index) => `alias-${index}`),
          is_group: true,
          sub_commands: Array.from({ length: 10 }, (_, index) => ({
            handler_full_name: `plugin.handler.${index}`,
            current_fragment: `sub-${index}`,
          })),
          permission: 'admin',
          has_conflict: true,
        },
      },
    });

    await flushPromises();

    expect(
      document.body.querySelector('.command-details-dialog'),
    ).not.toBeNull();
    expect(
      document.body.querySelector('.command-details-dialog__body'),
    ).not.toBeNull();
  });

  it('renders the sidebar customizer inside a constrained scrollable dialog', async () => {
    const wrapper = mountWithVuetify(SidebarCustomizer);

    await wrapper.find('button').trigger('click');
    await flushPromises();

    expect(
      document.body.querySelector('.sidebar-customizer-dialog'),
    ).not.toBeNull();
    expect(
      document.body.querySelector('.sidebar-customizer-dialog__content'),
    ).not.toBeNull();

    wrapper.unmount();
  });

  it('renders the changelog dialog inside a bounded scroll container', async () => {
    const wrapper = mountWithVuetify(ChangelogDialog, {
      props: {
        modelValue: true,
      },
    });

    await flushPromises();
    await flushPromises();

    expect(document.body.querySelector('.changelog-dialog')).not.toBeNull();
    expect(
      document.body.querySelector('.changelog-dialog__content'),
    ).not.toBeNull();
    expect(
      document.body.querySelector('.changelog-dialog__scroll'),
    ).not.toBeNull();
    expect(document.body.textContent).toContain('v4.26.2');
    expect(document.body.textContent).not.toContain('vundefined');

    wrapper.unmount();
  });

  it('renders the provider config dialog inside a constrained scrollable container', async () => {
    mountWithVuetify(ProviderConfigDialog, {
      props: {
        modelValue: true,
      },
    });

    await flushPromises();

    expect(
      document.body.querySelector('.provider-config-dialog'),
    ).not.toBeNull();
    expect(
      document.body.querySelector('.provider-config-dialog__body'),
    ).not.toBeNull();
    expect(
      document.body.querySelector('.provider-chat-completion-panel-stub'),
    ).not.toBeNull();
  });

  it('renders the file config dialog inside a bounded scroll container', async () => {
    const wrapper = mountWithVuetify(FileConfigItem, {
      props: {
        modelValue: ['docs/manual.txt'],
        itemMeta: {
          file_types: ['txt'],
        },
        pluginName: 'plugin.alpha',
        configKey: 'docs',
      },
    });

    await wrapper.find('button').trigger('click');
    await flushPromises();

    expect(document.body.querySelector('.file-dialog-card')).not.toBeNull();
    expect(document.body.querySelector('.file-dialog-body')).not.toBeNull();

    wrapper.unmount();
  });
});
