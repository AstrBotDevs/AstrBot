import { beforeEach, describe, expect, it, vi } from 'vitest';
import { computed, ref } from 'vue';
import { flushPromises } from '@vue/test-utils';
import ProviderPage from '@/views/ProviderPage.vue';
import { mountWithVuetify } from './utils/mountWithVuetify';

const testState = vi.hoisted(() => ({
  pushMock: vi.fn(),
  providerSourcesState: null as unknown,
  dialogState: null as unknown,
  astrBotConfigStub: {
    props: ['metadataKey'],
    template:
      '<div class="astrbot-config-stub">config:{{ metadataKey || "unknown" }}</div>',
  },
  providerSourcesPanelStub: {
    props: ['displayedProviderSources'],
    template:
      '<div class="provider-sources-panel-stub">sources:{{ displayedProviderSources.length }}</div>',
  },
  providerModelsPanelStub: {
    props: ['entries'],
    template:
      '<div class="provider-models-panel-stub">models:{{ entries.length }}</div>',
  },
  addNewProviderStub: {
    template: '<div class="add-new-provider-stub"></div>',
  },
  itemCardStub: {
    props: ['item'],
    template:
      '<div class="item-card-stub"><div class="item-card-id">{{ item.id }}</div><slot name="item-details" :item="item" /><slot name="actions" :item="item" /></div>',
  },
}));

vi.mock('vue-router', () => ({
  useRouter: () => ({
    push: testState.pushMock,
  }),
}));

vi.mock('@/api/v1', () => ({
  providerApi: {
    create: vi.fn(),
    update: vi.fn(),
    setEnabled: vi.fn(),
    test: vi.fn(),
  },
}));

vi.mock('@/composables/useProviderSources', () => ({
  useProviderSources: () => testState.providerSourcesState,
}));

vi.mock('@/composables/useProviderModelConfigDialog', () => ({
  useProviderModelConfigDialog: () => testState.dialogState,
}));

vi.mock('@/components/shared/AstrBotConfig.vue', () => ({
  default: testState.astrBotConfigStub,
}));

vi.mock('@/components/provider/ProviderSourcesPanel.vue', () => ({
  default: testState.providerSourcesPanelStub,
}));

vi.mock('@/components/provider/ProviderModelsPanel.vue', () => ({
  default: testState.providerModelsPanelStub,
}));

vi.mock('@/components/provider/AddNewProvider.vue', () => ({
  default: testState.addNewProviderStub,
}));

vi.mock('@/components/shared/ItemCard.vue', () => ({
  default: testState.itemCardStub,
}));

vi.mock('@/utils/providerUtils', () => ({
  getProviderIcon: (provider: string) => `/icons/${provider}.svg`,
  isMonochromeProviderIcon: () => false,
}));

function createProviderSourcesState(overrides: Record<string, unknown> = {}) {
  return {
    providers: ref([]),
    selectedProviderType: ref('chat_completion'),
    selectedProviderSource: ref({
      id: 'openai-main',
      provider: 'openai',
      api_base: 'https://api.openai.com/v1',
    }),
    availableModels: ref([{ id: 'openai-main/gpt-4.1-mini' }]),
    loadingModels: ref(false),
    loadingSources: ref(false),
    savingSource: ref(false),
    testingProviders: ref([]),
    isSourceModified: computed(() => false),
    configSchema: ref({
      provider: {
        config_template: {},
      },
    }),
    providerSourceSchema: ref({ provider: { items: {} } }),
    manualModelId: ref(''),
    modelSearch: ref(''),
    providerTypes: [
      { value: 'chat_completion', label: 'Chat Completion', icon: 'mdi-chat' },
      { value: 'speech_to_text', label: 'STT', icon: 'mdi-microphone' },
    ],
    availableSourceTypes: [{ value: 'openai', label: 'OpenAI' }],
    displayedProviderSources: computed(() => [
      {
        id: 'openai-main',
        provider: 'openai',
        api_base: 'https://api.openai.com/v1',
      },
    ]),
    filteredMergedModelEntries: computed(() => [
      { id: 'openai-main/gpt-4.1-mini' },
    ]),
    filteredProviders: computed(() => [
      {
        id: 'whisper-main',
        enable: true,
        provider: 'openai',
        type: 'openai_stt',
        provider_type: 'speech_to_text',
      },
    ]),
    basicSourceConfig: computed(() => ({ id: 'openai-main' })),
    advancedSourceConfig: computed(() => ({ proxy: 'http://localhost:7890' })),
    manualProviderId: computed(() => 'openai-main/'),
    resolveSourceIcon: () => '/icons/openai.svg',
    isMonochromeSourceIcon: () => false,
    getSourceDisplayName: (source: { id?: string; templateKey?: string }) =>
      source.id || source.templateKey || 'unknown',
    supportsImageInput: computed(() => true),
    supportsAudioInput: computed(() => false),
    supportsToolCall: computed(() => true),
    supportsReasoning: computed(() => true),
    formatContextLimit: () => '128k',
    updateDefaultTab: vi.fn(),
    selectProviderSource: vi.fn(),
    addProviderSource: vi.fn(),
    deleteProviderSource: vi.fn(),
    saveProviderSource: vi.fn(),
    fetchAvailableModels: vi.fn(),
    buildModelProviderConfig: vi.fn(),
    deleteProvider: vi.fn(),
    modelAlreadyConfigured: vi.fn(() => false),
    testProvider: vi.fn(),
    toggleProviderEnable: vi.fn(),
    loadConfig: vi.fn(),
    ...overrides,
  };
}

function createDialogState() {
  return {
    showProviderEditDialog: ref(false),
    providerEditData: ref(null),
    savingProviders: ref([]),
    providerModelConfigSchema: ref({ provider: { items: {} } }),
    providerEditDialogTitle: ref('Edit Provider'),
    openProviderEdit: vi.fn(),
    openModelAddDialog: vi.fn(),
    saveEditedProvider: vi.fn(),
  };
}

describe('ProviderPage', () => {
  beforeEach(() => {
    testState.pushMock.mockReset();
    testState.providerSourcesState = createProviderSourcesState();
    testState.dialogState = createDialogState();
  });

  it('renders the chat completion workbench without crashing', async () => {
    const wrapper = mountWithVuetify(ProviderPage, {
      props: {
        defaultTab: 'chat_completion',
      },
    });

    await flushPromises();

    expect(wrapper.find('.provider-config-title').text()).toBe('openai-main');
    expect(wrapper.find('.provider-config-subtitle').text()).toBe(
      'https://api.openai.com/v1',
    );
    expect(wrapper.findAll('.astrbot-config-stub')).toHaveLength(2);
    expect(wrapper.find('.provider-models-panel-stub').text()).toContain(
      'models:1',
    );
  });

  it('shows the empty provider-source state when no source is selected', async () => {
    testState.providerSourcesState = createProviderSourcesState({
      selectedProviderSource: ref(null),
      basicSourceConfig: computed(() => null),
      advancedSourceConfig: computed(() => null),
    });

    const wrapper = mountWithVuetify(ProviderPage, {});

    await flushPromises();

    expect(wrapper.find('.provider-empty-state').exists()).toBe(true);
  });

  it('renders the non-chat workbench on alternate tabs', async () => {
    testState.providerSourcesState = createProviderSourcesState({
      selectedProviderType: ref('speech_to_text'),
    });

    const wrapper = mountWithVuetify(ProviderPage, {
      props: {
        defaultTab: 'speech_to_text',
      },
    });

    await flushPromises();

    expect(wrapper.find('.item-card-stub').exists()).toBe(false);
    expect(wrapper.find('.provider-empty-state').exists()).toBe(true);
    expect(wrapper.find('.provider-tabs').exists()).toBe(true);
  });

  it('keeps the configured-model edit dialog in a scrollable card layout', async () => {
    testState.dialogState = {
      ...createDialogState(),
      showProviderEditDialog: ref(true),
      providerEditData: ref({
        id: 'openai-main/gpt-4.1-mini',
        provider: 'openai',
      }),
    };

    const wrapper = mountWithVuetify(ProviderPage, {
      props: {
        defaultTab: 'chat_completion',
      },
    });

    await flushPromises();

    expect(
      document.body.querySelector('.provider-form-dialog__card'),
    ).not.toBeNull();
    expect(
      document.body.querySelector('.provider-form-dialog__content'),
    ).not.toBeNull();
    expect(
      document.body.querySelector(
        '.provider-form-dialog__content .astrbot-config-stub',
      ),
    ).not.toBeNull();

    wrapper.unmount();
  });
});
